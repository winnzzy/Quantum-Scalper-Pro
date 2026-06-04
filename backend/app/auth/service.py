"""Authentication system for Quantum Scalper Pro."""
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from app.core.database import get_db
from app.core.logging import logger
from app.models.user import User, UserRole
from app.models.system import AuditLog, AuditAction

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current authenticated user."""
    token = credentials.credentials

    try:
        payload = decode_token(token)
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"}
            )

        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Check token type
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )

        # Get user from database
        result = await db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled"
            )

        if user.is_locked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is temporarily locked"
            )

        return user

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def get_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Get admin user."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


class AuthService:
    """Authentication service."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate user with email and password."""
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            return None

        if user.is_locked:
            return None

        if not verify_password(password, user.hashed_password):
            # Increment login attempts
            user.login_attempts += 1

            if user.login_attempts >= settings.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
                logger.warning(f"User {email} locked due to failed attempts")

            await self.db.commit()
            return None

        # Reset login attempts on success
        user.login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        await self.db.commit()

        # Log audit
        await self._log_audit(user.id, AuditAction.LOGIN, "success")

        return user

    async def create_user(
        self,
        email: str,
        username: str,
        password: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: UserRole = UserRole.TRADER
    ) -> User:
        """Create new user."""
        # Check if email exists
        result = await self.db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        user = User(
            email=email,
            username=username,
            hashed_password=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            role=role,
            is_active=True,
            is_verified=False
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        # Create default risk profile
        from app.models.risk import RiskProfile
        risk_profile = RiskProfile(user_id=user.id)
        self.db.add(risk_profile)
        await self.db.commit()

        logger.info(f"User created: {email}")
        return user

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> bool:
        """Change user password."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not verify_password(current_password, user.hashed_password):
            return False

        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()

        await self._log_audit(user_id, AuditAction.PASSWORD_CHANGE, "success")
        return True

    async def generate_tokens(self, user: User) -> Dict[str, str]:
        """Generate access and refresh tokens."""
        access_token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role.value})
        refresh_token = create_refresh_token({"sub": str(user.id)})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }

    async def refresh_access_token(self, refresh_token: str) -> Optional[str]:
        """Refresh access token."""
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        result = await self.db.execute(select(User).where(User.id == int(user_id)))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        return create_access_token({"sub": str(user.id), "email": user.email, "role": user.role.value})

    async def _log_audit(self, user_id: int, action: AuditAction, details: str):
        """Log audit event."""
        audit = AuditLog(
            user_id=user_id,
            action=action,
            details={"result": details},
            success=True
        )
        self.db.add(audit)
        await self.db.commit()


async def rate_limit_check(request: Request, db: AsyncSession = Depends(get_db)):
    """Rate limiting middleware."""
    client_ip = request.client.host
    key = f"rate_limit:{client_ip}"

    from app.core.redis import redis_client
    current = await redis_client.get(key)

    if current and int(current) >= settings.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )

    pipe = await redis_client._client.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60)
    await pipe.execute()
