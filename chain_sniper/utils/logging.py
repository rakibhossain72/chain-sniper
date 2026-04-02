"""
Logging utilities for Chain Sniper.
"""

import logging
from typing import Optional

# disable logging from external libraries to reduce noise
logging.getLogger("web3").setLevel(logging.WARNING)


def setup_logging(
    level: str = "INFO",
    format_str: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    logger_name: Optional[str] = None,
) -> logging.Logger:
    """
    Set up logging with consistent formatting.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        format_str: Format string for log messages
        logger_name: Name for the logger, defaults to root logger

    Returns:
        Configured logger instance
    """
    # Convert string level to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        level=numeric_level,
        format=format_str,
        datefmt="%H:%M",
    )

    logger = logging.getLogger(logger_name or __name__)
    logger.setLevel(numeric_level)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
