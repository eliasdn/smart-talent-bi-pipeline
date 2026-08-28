"""Logging configuration module for the talent analytics pipeline."""

import logging
import sys
from typing import Optional


def setup_logger(name: str = "smart_talent_bi", level: Optional[str] = None) -> logging.Logger:
    """Configure and return a structured console logger.

    Args:
        name: Name of the logger instance.
        level: Optional log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to INFO if not provided.

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(name)
    resolved_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logger.setLevel(resolved_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(resolved_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
