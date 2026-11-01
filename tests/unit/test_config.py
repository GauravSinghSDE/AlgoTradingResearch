"""
Unit tests for configuration validation and logging secret masking.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import SecretMaskingFormatter


def test_execution_mode_allowed_modes():
    """Verify that only BACKTEST and PAPER modes are accepted."""
    s1 = Settings(EXECUTION_MODE="BACKTEST")
    assert s1.EXECUTION_MODE == "BACKTEST"

    s2 = Settings(EXECUTION_MODE="PAPER")
    assert s2.EXECUTION_MODE == "PAPER"


def test_execution_mode_rejects_live():
    """Verify that LIVE or other arbitrary execution modes are strictly rejected."""
    with pytest.raises(ValidationError):
        Settings(EXECUTION_MODE="LIVE")

    with pytest.raises(ValidationError):
        Settings(EXECUTION_MODE="PRODUCTION")


def test_secret_masking_formatter():
    """Verify that access tokens, authorization headers, and secrets are masked in logs."""
    formatter = SecretMaskingFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=1,
        msg="Calling API with Bearer eyJhbGciOiJIUzI1NiJ9.test and client_secret='SuperSecretKey123'",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "eyJhbGciOiJIUzI1NiJ9" not in formatted
    assert "SuperSecretKey123" not in formatted
    assert "[MASKED_TOKEN]" in formatted
    assert "[MASKED_SECRET]" in formatted
