"""Logging configuration for Quantum Scalper Pro."""
import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path

from app.core.config import settings


def setup_logging() -> logging.Logger:
    """Configure application logging."""
    logger = logging.getLogger("quantum_scalper")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL))

    if logger.handlers:
        return logger

    # Ensure logs directory exists
    logs_dir = Path(settings.LOGS_DIR)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
    )
    simple_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)
    logger.addHandler(console_handler)

    # File handler - rotating
    file_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / f"qsp_{datetime.now().strftime('%Y%m%d')}.log",
        maxBytes=10_000_000,  # 10MB
        backupCount=30,
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Error file handler
    error_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / "errors.log",
        maxBytes=10_000_000,
        backupCount=10,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(detailed_formatter)
    logger.addHandler(error_handler)

    # Trading activity log
    trade_handler = logging.handlers.RotatingFileHandler(
        filename=logs_dir / "trades.log",
        maxBytes=50_000_000,
        backupCount=50,
        encoding="utf-8"
    )
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(detailed_formatter)
    trade_logger = logging.getLogger("quantum_scalper.trades")
    trade_logger.addHandler(trade_handler)
    trade_logger.setLevel(logging.INFO)

    return logger


logger = setup_logging()
trade_logger = logging.getLogger("quantum_scalper.trades")
