"""
Centralized structured logging with secret masking.
Ensures API secrets, access tokens, and authorization headers are never logged.
"""

from __future__ import annotations

import logging
import re
import sys

# Patterns to mask in logs
SECRET_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), r"\1[MASKED_TOKEN]"),
    (
        re.compile(r"(['\"]?client_secret['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
        r"\1[MASKED_SECRET]\2",
    ),
    (
        re.compile(r"(['\"]?access_token['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
        r"\1[MASKED_TOKEN]\2",
    ),
    (
        re.compile(r"(['\"]?api_secret['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE),
        r"\1[MASKED_SECRET]\2",
    ),
]


class SecretMaskingFormatter(logging.Formatter):
    """Custom logging formatter that scrubs sensitive keys and credentials."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        masked = original
        for pattern, replacement in SECRET_PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configures root logger with secret masking and standardized formatting."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger = logging.getLogger("algotrading")
    logger.setLevel(log_level)

    # Avoid duplicate handlers if setup_logging is called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = SecretMaskingFormatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = setup_logging()
