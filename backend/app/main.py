"""Quantum Scalper Pro - Main FastAPI Application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.database import engine, AsyncSessionLocal
from app.core.logging import logger
from app.core.redis import redis_client
from app.api import api_router
from app.api.websocket import router as websocket_router
from app.brokers.factory import BrokerFactory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}")

    if settings.COMMERCIAL_FEATURES_ENABLED:
        from app.services.subscription_service import subscription_service
        await subscription_service.seed_default_plans()

    # Connect Redis
    await redis_client.connect()

    # Start news filter
    from app.engines.news import news_filter
    await news_filter.start()

    # Never resume a real-money process without reconciling persisted trades
    # against broker state after a restart.
    if settings.LIVE_TRADING_ENABLED and settings.STARTUP_RECOVERY_REQUIRED:
        from app.core.startup_recovery import StartupRecovery
        recovery = await StartupRecovery(AsyncSessionLocal, BrokerFactory).recover()
        if recovery["errors"]:
            from sqlalchemy import select
            from app.core.operational_state import activate_emergency_stop
            from app.models.user import User
            from app.notifications.engine import NotificationEngine
            await activate_emergency_stop()
            logger.critical("Startup recovery failed; emergency stop activated")
            async with AsyncSessionLocal() as session:
                owners = (await session.execute(select(User))).scalars().all()
                for owner in owners:
                    await NotificationEngine(session).send_alert(
                        owner.id,
                        "Startup recovery failed",
                        "; ".join(recovery["errors"]),
                        priority="critical",
                    )

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application")

    await news_filter.stop()
    from app.engines.trading import trading_engine_manager
    await trading_engine_manager.stop_all()
    await BrokerFactory.disconnect_all()
    await redis_client.disconnect()
    await engine.dispose()

    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Risk-controlled Bitcoin and spot-gold trading and validation platform",
    version=settings.VERSION,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://quantumscalper.pro"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Trusted hosts
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else ["quantumscalper.pro", "*.quantumscalper.pro"]
)

# Prometheus metrics
if settings.METRICS_ENABLED:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Include API routes
app.include_router(api_router)
app.include_router(websocket_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "running",
        "environment": settings.ENVIRONMENT
    }
