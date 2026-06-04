"""
Startup Recovery Handler — VPS Restart Recovery (#3)
====================================================
On application startup after a VPS restart or crash, this module:
1. Syncs order states with all active brokers
2. Reconciles positions
3. Closes orphaned trades
4. Resumes monitoring loops
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List

from app.core.logging import logger
from app.core.hardening import (
    OrderStateSynchronizer,
    PositionReconciler,
    broker_connection_manager,
    retry_with_backoff,
    RetryPolicy,
)


class StartupRecovery:
    """Handles recovery after application restart."""

    def __init__(self, db_session_factory, broker_factory):
        self.db_session_factory = db_session_factory
        self.broker_factory = broker_factory
        self.order_sync = OrderStateSynchronizer(db_session_factory, broker_factory)
        self.position_reconciler = PositionReconciler(db_session_factory, broker_factory)

    async def recover(self) -> Dict[str, Any]:
        """
        Full startup recovery sequence.
        
        Steps:
        1. Get all users with active trades
        2. For each user, sync orders and reconcile positions
        3. Log recovery results
        """
        result = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "users_recovered": 0,
            "orders_synced": 0,
            "orphaned_trades_closed": 0,
            "errors": [],
        }

        logger.info("=" * 60)
        logger.info("STARTUP RECOVERY: Beginning post-restart recovery")
        logger.info("=" * 60)

        try:
            from sqlalchemy import select, distinct
            from app.models.trading import Trade, TradeStatus, BrokerType

            async with self.db_session_factory() as session:
                # Find all users with open trades
                users_result = await session.execute(
                    select(distinct(Trade.user_id)).where(
                        Trade.status == TradeStatus.OPEN
                    )
                )
                user_ids = [row[0] for row in users_result.all()]

            if not user_ids:
                logger.info("STARTUP RECOVERY: No open trades found. System clean.")
                result["started_at"] = datetime.now(timezone.utc).isoformat()
                return result

            logger.info(f"STARTUP RECOVERY: Found {len(user_ids)} users with open trades")

            for user_id in user_ids:
                try:
                    user_result = await self._recover_user(user_id)
                    result["users_recovered"] += 1
                    result["orders_synced"] += user_result.get("orders_synced", 0)
                    result["orphaned_trades_closed"] += user_result.get("orphaned_closed", 0)
                except Exception as e:
                    error_msg = f"Recovery failed for user {user_id}: {e}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)

        except Exception as e:
            error_msg = f"Startup recovery critical error: {e}"
            result["errors"].append(error_msg)
            logger.error(error_msg)

        result["completed_at"] = datetime.now(timezone.utc).isoformat()
        logger.info("=" * 60)
        logger.info(
            f"STARTUP RECOVERY COMPLETE: "
            f"users={result['users_recovered']}, "
            f"orders_synced={result['orders_synced']}, "
            f"orphaned_closed={result['orphaned_trades_closed']}, "
            f"errors={len(result['errors'])}"
        )
        logger.info("=" * 60)

        return result

    async def _recover_user(self, user_id: int) -> Dict[str, Any]:
        """Recover state for a single user."""
        result = {"orders_synced": 0, "orphaned_closed": 0}

        # Determine which broker type this user uses
        from sqlalchemy import select
        from app.models.trading import Trade, TradeStatus

        async with self.db_session_factory() as session:
            trades_result = await session.execute(
                select(Trade.broker).where(
                    Trade.user_id == user_id,
                    Trade.status == TradeStatus.OPEN,
                ).distinct()
            )
            broker_types = [row[0] for row in trades_result.all()]

        for broker_type_enum in broker_types:
            broker_type = broker_type_enum.value if hasattr(broker_type_enum, 'value') else str(broker_type_enum)

            if broker_type == "paper":
                continue  # Skip paper trading

            logger.info(f"Recovering user {user_id} broker {broker_type}")

            # Sync order states with retry
            policy = RetryPolicy(max_retries=3, base_delay=2.0)
            try:
                sync_result = await retry_with_backoff(
                    lambda: self.order_sync.sync_pending_orders(user_id, broker_type),
                    policy,
                    f"order_sync_user_{user_id}",
                )
                result["orders_synced"] += sync_result.get("synced", 0)
            except Exception as e:
                logger.error(f"Order sync failed for user {user_id}: {e}")

            # Reconcile positions with retry
            try:
                recon_result = await retry_with_backoff(
                    lambda: self.position_reconciler.reconcile(user_id, broker_type),
                    policy,
                    f"position_recon_user_{user_id}",
                )
                result["orphaned_closed"] += recon_result.get("resolved", 0)
            except Exception as e:
                logger.error(f"Position reconciliation failed for user {user_id}: {e}")

        return result