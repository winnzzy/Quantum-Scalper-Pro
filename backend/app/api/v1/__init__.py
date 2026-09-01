"""API Routes for Quantum Scalper Pro."""
from fastapi import APIRouter

from app.api.v1 import auth, users, trading, strategies, risk, analytics, admin, system, licensing, billing

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(trading.router, prefix="/trading", tags=["Trading"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["Strategies"])
api_router.include_router(risk.router, prefix="/risk", tags=["Risk Management"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(licensing.router, prefix="/licensing", tags=["Licensing"])
api_router.include_router(billing.router, prefix="/billing", tags=["Billing"])
