"""Authenticated real-time snapshots for the trading frontend."""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, desc, select

from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.core.security import decode_token
from app.models.system import Notification
from app.models.trading import Position, Trade, TradeStatus
from app.models.user import User


router = APIRouter()


async def _authenticate(token: str | None) -> User | None:
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != "access" or not payload.get("sub"):
        return None

    async with AsyncSessionLocal() as session:
        user = await session.get(User, int(payload["sub"]))
        if not user or not user.is_active or user.is_locked:
            return None
        session.expunge(user)
        return user


async def _snapshot(user_id: int) -> dict:
    async with AsyncSessionLocal() as session:
        positions_result = await session.execute(
            select(Position)
            .where(and_(Position.user_id == user_id, Position.is_open.is_(True)))
            .order_by(desc(Position.opened_at))
        )
        trades_result = await session.execute(
            select(Trade)
            .where(and_(Trade.user_id == user_id, Trade.status == TradeStatus.OPEN))
            .order_by(desc(Trade.created_at))
            .limit(100)
        )
        notifications_result = await session.execute(
            select(Notification)
            .where(and_(Notification.user_id == user_id, Notification.is_read.is_(False)))
            .order_by(desc(Notification.created_at))
            .limit(20)
        )

        return {
            "type": "snapshot",
            "positions": jsonable_encoder(positions_result.scalars().all()),
            "trades": jsonable_encoder(trades_result.scalars().all()),
            "notifications": jsonable_encoder(notifications_result.scalars().all()),
        }


@router.websocket("/ws")
async def realtime_updates(websocket: WebSocket):
    """Stream user-scoped snapshots; the access token is supplied by the browser."""
    protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if value.strip()
    ]
    bearer_protocol = next(
        (value for value in protocols if value.startswith("bearer.")),
        None,
    )
    token = bearer_protocol.removeprefix("bearer.") if bearer_protocol else None
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    await websocket.accept(subprotocol=bearer_protocol)
    logger.info(f"WebSocket connected for user {user.id}")

    try:
        while True:
            payload = await _snapshot(user.id)
            await websocket.send_json(payload)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user.id}")
    except Exception as exc:
        logger.error(f"WebSocket failure for user {user.id}: {exc}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            pass
