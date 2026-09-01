"""Quantum Scalper Pro - Core Configuration"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Quantum Scalper Pro"
    VERSION: str = "1.0.0"
    ENVIRONMENT: str = Field(default="development", pattern="^(development|staging|production)$")
    DEBUG: bool = Field(default=False)

    # Security
    SECRET_KEY: str = Field(default="change-me-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30

    # Database
    DATABASE_URL: str = Field(default="postgresql+asyncpg://qsp_admin:password@localhost:5432/quantum_scalper_pro")
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    REDIS_PASSWORD: str | None = None

    # API Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # Trading
    DEFAULT_RISK_PER_TRADE: float = 0.5  # Percentage
    MAX_DAILY_LOSS_PERCENT: float = 3.0
    MAX_WEEKLY_LOSS_PERCENT: float = 5.0
    MAX_MONTHLY_LOSS_PERCENT: float = 10.0
    MAX_DRAWDOWN_PERCENT: float = 15.0
    MAX_CONSECUTIVE_LOSSES: int = 5
    MAX_OPEN_TRADES: int = 10
    MANDATORY_STOP_LOSS: bool = True

    # Broker - Binance
    BINANCE_API_KEY: str | None = None
    BINANCE_SECRET_KEY: str | None = None
    BINANCE_TESTNET: bool = True
    BINANCE_FUTURES: bool = True

    # Broker - MT5
    MT5_SERVER: str | None = None
    MT5_LOGIN: int | None = None
    MT5_PASSWORD: str | None = None
    MT5_PATH: str | None = None

    # Notifications
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True

    # AI Filter
    AI_FILTER_ENABLED: bool = True
    AI_MIN_CONFIDENCE: float = 0.65
    AI_MODEL_PATH: str = "./data/models"

    # News Filter
    NEWS_FILTER_ENABLED: bool = True
    NEWS_API_KEY: str | None = None
    HIGH_IMPACT_EVENTS: list[str] = Field(default=["NFP", "CPI", "FOMC", "Interest Rate", "GDP", "Unemployment"])
    NEWS_BUFFER_MINUTES: int = 30

    # Backtesting
    BACKTEST_DATA_PATH: str = "./data/historical"
    DEFAULT_COMMISSION: float = 0.0004  # 0.04%
    DEFAULT_SLIPPAGE: float = 0.0001

    # Billing
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_STARTER_MONTHLY: str | None = None
    STRIPE_PRICE_STARTER_ANNUAL: str | None = None
    STRIPE_PRICE_PROFESSIONAL_MONTHLY: str | None = None
    STRIPE_PRICE_PROFESSIONAL_ANNUAL: str | None = None
    STRIPE_PRICE_ENTERPRISE_MONTHLY: str | None = None
    STRIPE_PRICE_ENTERPRISE_ANNUAL: str | None = None
    FRONTEND_URL: str = "http://localhost:3000"

    # Licensing
    LICENSE_SERVER_URL: str | None = None
    LICENSE_CHECK_INTERVAL_HOURS: int = 24

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    GRAFANA_PORT: int = 3001
    LOG_LEVEL: str = "INFO"

    # Paths
    DATA_DIR: str = "./data"
    LOGS_DIR: str = "./logs"
    BACKUPS_DIR: str = "./backups"

    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        if len(v) < 32 and os.getenv("ENVIRONMENT") == "production":
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
