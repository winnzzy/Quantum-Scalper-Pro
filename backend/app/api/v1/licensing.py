"""Licensing API routes."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.auth.service import get_current_active_user, get_admin_user
from app.models.user import User
from app.models.licensing import License, LicenseStatus

router = APIRouter()


class LicenseCreate(BaseModel):
    license_key: str
    plan: str
    max_accounts: int = 1
    max_strategies: int = 3


@router.get("/my-license")
async def get_my_license(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's license."""
    if not current_user.license_key:
        return {"license": None}

    result = await db.execute(
        select(License).where(License.license_key == current_user.license_key)
    )
    license = result.scalar_one_or_none()

    return {"license": license}


@router.post("/activate")
async def activate_license(
    license_key: str,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Activate license for user."""
    result = await db.execute(
        select(License).where(License.license_key == license_key)
    )
    license = result.scalar_one_or_none()

    if not license:
        raise HTTPException(status_code=404, detail="License not found")

    if license.status != LicenseStatus.PENDING:
        raise HTTPException(status_code=400, detail="License already activated or expired")

    license.status = LicenseStatus.ACTIVE
    license.user_id = current_user.id
    license.activated_at = datetime.now(timezone.utc)

    current_user.license_key = license_key
    current_user.subscription_plan = license.plan

    await db.commit()

    return {"success": True, "license": license}


@router.post("/create", dependencies=[Depends(get_admin_user)])
async def create_license(
    data: LicenseCreate,
    admin: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db)
):
    """Create new license (admin only)."""
    from datetime import datetime, timezone, timedelta
    from app.core.security import generate_api_key

    license_key = data.license_key or generate_api_key()

    license = License(
        license_key=license_key,
        plan=data.plan,
        max_accounts=data.max_accounts,
        max_strategies=data.max_strategies,
        status=LicenseStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )

    db.add(license)
    await db.commit()
    await db.refresh(license)

    return {"success": True, "license": license}
