"""Authentication API routes."""
from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.auth.service import AuthService, get_current_user, get_current_active_user
from app.models.user import User, UserRole
from app.core.config import settings
from app.auth.totp import (
    decrypt_secret, encrypt_secret, generate_secret, provisioning_uri, verify_code,
)

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    first_name: str | None = None
    last_name: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int


class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    first_name: str | None
    last_name: str | None
    role: str
    is_active: bool
    subscription_plan: str
    two_factor_enabled: bool


class MfaCode(BaseModel):
    code: str


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Create the owner account; public sign-up is disabled in private mode."""
    if settings.PRIVATE_MODE and not settings.PUBLIC_REGISTRATION_ENABLED:
        if settings.OWNER_EMAIL and user_data.email.lower() != settings.OWNER_EMAIL.lower():
            raise HTTPException(status_code=403, detail="Registration is restricted to the configured owner")
        user_count = await db.scalar(select(func.count(User.id)))
        if user_count:
            raise HTTPException(status_code=403, detail="Private owner account already exists")
    auth_service = AuthService(db)
    user = await auth_service.create_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        role=UserRole.ADMIN if settings.PRIVATE_MODE else UserRole.TRADER,
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    otp_code: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Login and get tokens."""
    auth_service = AuthService(db)
    user = await auth_service.authenticate_user(
        form_data.username, form_data.password, otp_code=otp_code
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    tokens = await auth_service.generate_tokens(user)
    return tokens


@router.post("/refresh")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_db)):
    """Refresh access token."""
    auth_service = AuthService(db)
    new_token = await auth_service.refresh_access_token(refresh_token)

    if not new_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )

    return {"access_token": new_token, "token_type": "bearer"}


@router.post("/mfa/setup")
async def setup_mfa(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a pending authenticator secret; enabling still requires a valid code."""
    if current_user.two_factor_enabled:
        raise HTTPException(status_code=409, detail="Two-factor authentication is already enabled")
    secret = generate_secret()
    current_user.two_factor_secret = encrypt_secret(secret)
    await db.commit()
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(secret, current_user.email),
    }


@router.post("/mfa/enable")
async def enable_mfa(
    payload: MfaCode,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    secret = decrypt_secret(current_user.two_factor_secret or "")
    if not secret or not verify_code(secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    current_user.two_factor_enabled = True
    await db.commit()
    return {"two_factor_enabled": True}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_active_user)):
    """Get current user info."""
    return current_user


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Change password."""
    auth_service = AuthService(db)
    success = await auth_service.change_password(current_user.id, current_password, new_password)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    return {"message": "Password changed successfully"}
