"""Device fingerprinting and license activation service.

Features:
- Device fingerprint generation (hardware hash)
- Device registration with activation limits
- License key activation/deactivation
- Heartbeat-based activation validation
- Remote deactivation
- Device management (list, revoke, block)
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy import select, update, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session
from app.core.logging import logger
from app.core.redis import redis_client
from app.models.subscription import (
    Device, DeviceStatus, LicenseActivation,
    CustomerSubscription, SubscriptionStatus,
)
from app.models.user import User


class DeviceService:
    """Device fingerprinting and license activation management."""

    ACTIVATION_TOKEN_TTL = 86400 * 30  # 30 days
    HEARTBEAT_INTERVAL = 3600  # 1 hour
    HEARTBEAT_GRACE_PERIOD = 7200  # 2 hours

    # ──────────────────────────────────────────────────────────────────
    # Fingerprint Generation
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def generate_fingerprint(components: Dict[str, str]) -> str:
        """
        Generate device fingerprint from hardware components.

        Expected components:
        - hostname: Machine hostname
        - os: Operating system
        - cpu_id: CPU identifier
        - mac_address: Primary MAC address
        - disk_serial: Disk serial number
        - bios_serial: BIOS/UEFI serial

        The fingerprint is a HMAC-SHA256 hash that is deterministic
        for the same hardware but resistant to spoofing.
        """
        # Canonical ordering of components
        canonical_keys = sorted(components.keys())
        raw = "|".join(f"{k}={components.get(k, '')}" for k in canonical_keys)

        # HMAC with server-side secret to prevent client-side fabrication
        secret = settings.SECRET_KEY.encode()
        fingerprint = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()

        return f"fp-{fingerprint[:32]}"

    @staticmethod
    def validate_fingerprint_format(fingerprint: str) -> bool:
        """Validate fingerprint format."""
        if not fingerprint or not fingerprint.startswith("fp-"):
            return False
        hex_part = fingerprint[3:]
        return len(hex_part) == 32 and all(c in "0123456789abcdef" for c in hex_part)

    # ──────────────────────────────────────────────────────────────────
    # Device Registration
    # ──────────────────────────────────────────────────────────────────

    async def register_device(
        self,
        user_id: int,
        fingerprint: str,
        device_name: Optional[str] = None,
        device_type: Optional[str] = None,
        os_info: Optional[str] = None,
        app_version: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a device for a user."""
        if not self.validate_fingerprint_format(fingerprint):
            raise ValueError("Invalid fingerprint format")

        async with async_session() as session:
            # Check if device already registered
            existing = await session.execute(
                select(Device).where(
                    Device.user_id == user_id,
                    Device.device_fingerprint == fingerprint,
                )
            )
            device = existing.scalar_one_or_none()

            if device:
                # Reactivate if deactivated
                if device.status == DeviceStatus.DEACTIVATED:
                    device.status = DeviceStatus.ACTIVE
                    device.last_seen_at = datetime.now(timezone.utc)
                    device.activated_at = datetime.now(timezone.utc)
                    device.deactivated_at = None
                    device.ip_address = ip_address
                    await session.commit()
                    logger.info(f"Reactivated device {device.id} for user {user_id}")
                    return self._device_to_dict(device)
                elif device.status == DeviceStatus.BLOCKED:
                    raise ValueError("Device is blocked. Contact support.")
                else:
                    # Already active — update heartbeat
                    device.last_seen_at = datetime.now(timezone.utc)
                    device.ip_address = ip_address
                    await session.commit()
                    return self._device_to_dict(device)

            # Check activation limits
            active_count = await session.execute(
                select(func.count(Device.id)).where(
                    Device.user_id == user_id,
                    Device.status == DeviceStatus.ACTIVE,
                )
            )
            current_count = active_count.scalar() or 0

            # Get user's subscription limits
            max_devices = await self._get_max_devices(user_id, session)

            if current_count >= max_devices:
                raise ValueError(
                    f"Device limit reached ({current_count}/{max_devices}). "
                    f"Deactivate a device or upgrade your plan."
                )

            # Register new device
            device = Device(
                user_id=user_id,
                device_fingerprint=fingerprint,
                device_name=device_name,
                device_type=device_type,
                os_info=os_info,
                app_version=app_version,
                ip_address=ip_address,
                status=DeviceStatus.ACTIVE,
            )
            session.add(device)
            await session.commit()
            await session.refresh(device)

            logger.info(f"Registered device {device.id} ({fingerprint[:12]}...) for user {user_id}")
            return self._device_to_dict(device)

    async def deactivate_device(
        self,
        user_id: int,
        device_id: int,
    ) -> Dict[str, Any]:
        """Deactivate a device."""
        async with async_session() as session:
            result = await session.execute(
                select(Device).where(
                    Device.id == device_id,
                    Device.user_id == user_id,
                )
            )
            device = result.scalar_one_or_none()
            if not device:
                raise ValueError("Device not found")

            device.status = DeviceStatus.DEACTIVATED
            device.deactivated_at = datetime.now(timezone.utc)

            # Deactivate associated license activations
            await session.execute(
                update(LicenseActivation)
                .where(
                    LicenseActivation.device_id == device_id,
                    LicenseActivation.deactivated_at.is_(None),
                )
                .values(deactivated_at=datetime.now(timezone.utc))
            )

            await session.commit()
            logger.info(f"Deactivated device {device_id} for user {user_id}")

            return {"device_id": device_id, "status": "deactivated"}

    async def deactivate_all_devices(self, user_id: int) -> int:
        """Deactivate all devices for a user (used for remote deactivation)."""
        async with async_session() as session:
            result = await session.execute(
                update(Device)
                .where(
                    Device.user_id == user_id,
                    Device.status == DeviceStatus.ACTIVE,
                )
                .values(
                    status=DeviceStatus.DEACTIVATED,
                    deactivated_at=datetime.now(timezone.utc),
                )
                .returning(Device.id)
            )
            deactivated_ids = [row[0] for row in result.fetchall()]

            # Deactivate all license activations
            await session.execute(
                update(LicenseActivation)
                .where(
                    LicenseActivation.user_id == user_id,
                    LicenseActivation.deactivated_at.is_(None),
                )
                .values(deactivated_at=datetime.now(timezone.utc))
            )

            await session.commit()
            count = len(deactivated_ids)
            logger.info(f"Deactivated all {count} devices for user {user_id}")
            return count

    async def block_device(
        self,
        user_id: int,
        device_id: int,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Block a device (admin action)."""
        async with async_session() as session:
            result = await session.execute(
                select(Device).where(Device.id == device_id)
            )
            device = result.scalar_one_or_none()
            if not device:
                raise ValueError("Device not found")

            device.status = DeviceStatus.BLOCKED
            device.deactivated_at = datetime.now(timezone.utc)
            device.metadata = {
                **(device.metadata or {}),
                "block_reason": reason,
                "blocked_at": datetime.now(timezone.utc).isoformat(),
            }

            await session.commit()
            logger.warning(f"Blocked device {device_id}: {reason}")

            return {"device_id": device_id, "status": "blocked", "reason": reason}

    async def list_user_devices(
        self,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """List all devices for a user."""
        async with async_session() as session:
            result = await session.execute(
                select(Device)
                .where(Device.user_id == user_id)
                .order_by(Device.last_seen_at.desc())
            )
            devices = result.scalars().all()
            return [self._device_to_dict(d) for d in devices]

    # ──────────────────────────────────────────────────────────────────
    # License Activation
    # ──────────────────────────────────────────────────────────────────

    async def activate_license(
        self,
        user_id: int,
        license_key: str,
        device_fingerprint: str,
        ip_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Activate a license key on a device."""
        async with async_session() as session:
            # Verify license belongs to user
            user = await session.get(User, user_id)
            if not user or user.license_key != license_key:
                raise ValueError("Invalid license key")

            # Verify subscription is active
            sub_result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == user_id,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]),
                )
            )
            subscription = sub_result.scalar_one_or_none()
            if not subscription:
                raise ValueError("No active subscription")

            # Get or register device
            device_result = await session.execute(
                select(Device).where(
                    Device.user_id == user_id,
                    Device.device_fingerprint == device_fingerprint,
                    Device.status == DeviceStatus.ACTIVE,
                )
            )
            device = device_result.scalar_one_or_none()

            if not device:
                # Try to register
                reg_result = await self.register_device(
                    user_id=user_id,
                    fingerprint=device_fingerprint,
                    ip_address=ip_address,
                )
                device_result = await session.execute(
                    select(Device).where(Device.id == reg_result["id"])
                )
                device = device_result.scalar_one_or_none()

            if not device:
                raise ValueError("Device registration failed")

            # Generate activation token
            activation_token = secrets.token_urlsafe(48)
            now = datetime.now(timezone.utc)

            # Create activation record
            activation = LicenseActivation(
                user_id=user_id,
                license_key=license_key,
                device_id=device.id,
                activation_token=activation_token,
                ip_address=ip_address,
                activated_at=now,
                expires_at=now + timedelta(days=self.ACTIVATION_TOKEN_TTL // 86400),
                last_heartbeat=now,
            )
            session.add(activation)

            # Update device
            device.last_seen_at = now
            device.ip_address = ip_address

            await session.commit()

            # Cache activation for fast lookups
            cache_data = {
                "user_id": user_id,
                "license_key": license_key,
                "device_id": device.id,
                "active": True,
                "plan_tier": subscription.plan_id,
                "features": [],  # Will be populated from plan
            }
            await redis_client.set_json(
                f"activation:{activation_token}",
                cache_data,
                expire=self.ACTIVATION_TOKEN_TTL,
            )

            logger.info(f"License activated for user {user_id} on device {device.id}")

            return {
                "activation_token": activation_token,
                "device_id": device.id,
                "expires_at": activation.expires_at.isoformat(),
                "status": "activated",
            }

    async def deactivate_license(
        self,
        user_id: int,
        activation_token: str,
    ) -> Dict[str, Any]:
        """Deactivate a specific license activation."""
        async with async_session() as session:
            result = await session.execute(
                select(LicenseActivation).where(
                    LicenseActivation.activation_token == activation_token,
                    LicenseActivation.user_id == user_id,
                    LicenseActivation.deactivated_at.is_(None),
                )
            )
            activation = result.scalar_one_or_none()
            if not activation:
                raise ValueError("Activation not found")

            activation.deactivated_at = datetime.now(timezone.utc)

            # Remove from cache
            await redis_client.delete(f"activation:{activation_token}")

            await session.commit()
            logger.info(f"Deactivated license activation {activation.id}")

            return {"status": "deactivated"}

    async def validate_activation(
        self,
        activation_token: str,
        device_fingerprint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate an activation token (called by client heartbeat)."""
        # Check cache first
        cached = await redis_client.get_json(f"activation:{activation_token}")
        if cached and cached.get("active"):
            # Update heartbeat in background
            return {"valid": True, **cached}

        async with async_session() as session:
            result = await session.execute(
                select(LicenseActivation).where(
                    LicenseActivation.activation_token == activation_token,
                    LicenseActivation.deactivated_at.is_(None),
                )
            )
            activation = result.scalar_one_or_none()

            if not activation:
                return {"valid": False, "reason": "Activation not found or deactivated"}

            # Check expiry
            if activation.expires_at and activation.expires_at < datetime.now(timezone.utc):
                return {"valid": False, "reason": "Activation expired"}

            # Update heartbeat
            now = datetime.now(timezone.utc)
            activation.last_heartbeat = now
            activation.heartbeat_count += 1

            # Get subscription status
            sub_result = await session.execute(
                select(CustomerSubscription).where(
                    CustomerSubscription.user_id == activation.user_id,
                    CustomerSubscription.status.in_([
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ]),
                )
            )
            subscription = sub_result.scalar_one_or_none()

            if not subscription:
                activation.deactivated_at = now
                await session.commit()
                return {"valid": False, "reason": "Subscription inactive"}

            # Re-cache
            cache_data = {
                "user_id": activation.user_id,
                "license_key": activation.license_key,
                "device_id": activation.device_id,
                "active": True,
            }
            await redis_client.set_json(
                f"activation:{activation_token}",
                cache_data,
                expire=self.ACTIVATION_TOKEN_TTL,
            )

            await session.commit()
            return {"valid": True, **cache_data}

    async def heartbeat(
        self,
        activation_token: str,
        device_fingerprint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process heartbeat from client to keep activation alive."""
        return await self.validate_activation(activation_token, device_fingerprint)

    # ──────────────────────────────────────────────────────────────────
    # Remote Deactivation
    # ──────────────────────────────────────────────────────────────────

    async def remote_deactivate_user(self, user_id: int) -> Dict[str, Any]:
        """Remotely deactivate all licenses and devices for a user (admin)."""
        devices_count = await self.deactivate_all_devices(user_id)

        async with async_session() as session:
            # Expire all activation tokens
            result = await session.execute(
                select(LicenseActivation).where(
                    LicenseActivation.user_id == user_id,
                    LicenseActivation.deactivated_at.is_(None),
                )
            )
            activations = result.scalars().all()
            for act in activations:
                act.deactivated_at = datetime.now(timezone.utc)
                await redis_client.delete(f"activation:{act.activation_token}")

            await session.commit()

        return {
            "user_id": user_id,
            "devices_deactivated": devices_count,
            "activations_revoked": len(activations),
        }

    # ──────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────

    async def _get_max_devices(self, user_id: int, session: AsyncSession) -> int:
        """Get max devices allowed for user's subscription."""
        result = await session.execute(
            select(CustomerSubscription)
            .where(
                CustomerSubscription.user_id == user_id,
                CustomerSubscription.status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ]),
            )
            .order_by(CustomerSubscription.created_at.desc())
            .limit(1)
        )
        sub = result.scalar_one_or_none()
        if sub:
            from app.models.subscription import SubscriptionPlanConfig
            plan = await session.get(SubscriptionPlanConfig, sub.plan_id)
            if plan:
                return plan.max_devices
        return 1  # Free tier default

    @staticmethod
    def _device_to_dict(device: Device) -> Dict[str, Any]:
        """Convert device to dict."""
        return {
            "id": device.id,
            "device_fingerprint": device.device_fingerprint[:16] + "...",
            "device_name": device.device_name,
            "device_type": device.device_type,
            "os_info": device.os_info,
            "app_version": device.app_version,
            "ip_address": device.ip_address,
            "status": device.status.value,
            "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
            "activated_at": device.activated_at.isoformat() if device.activated_at else None,
        }


# Global instance
device_service = DeviceService()