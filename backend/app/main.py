"""Quantum Scalper Pro - Main FastAPI Application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.core.config import settings
from app.core.database import engine
from app.core.logging import logger
from app.core.redis import redis_client
from app.api import api_router
from app.brokers.factory import BrokerFactory


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.VERSION}")

    # Connect Redis
    await redis_client.connect()

    # Start news filter
    from app.engines.news import news_filter
    await news_filter.start()

    logger.info("Application startup complete")

    yield

    # Shutdown
    logger.info("Shutting down application")

    await news_filter.stop()
    await BrokerFactory.disconnect_all()
    await redis_client.disconnect()
    await engine.dispose()

    logger.info("Application shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Production-grade automated trading platform for Forex and Cryptocurrency",
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
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include API routes
app.include_router(api_router)


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
