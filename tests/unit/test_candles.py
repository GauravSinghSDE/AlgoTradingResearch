"""
Unit tests for OHLCV candles, timestamp normalization to Asia/Kolkata, and batch parsing.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.domain.candles import IST, Candle, CandleBatch, CandleInterval


def test_candle_price_coherence_validation():
    """Verify that candles enforce High >= max(Open, Close) and Low <= min(Open, Close)."""
    now = datetime(2024, 10, 31, 9, 15, tzinfo=IST)

    # Valid candle
    c = Candle(
        timestamp=now,
        open=100.0,
        high=105.0,
        low=98.0,
        close=102.0,
        volume=5000,
        instrument_key="TEST_KEY",
    )
    assert c.is_bullish is True
    assert c.candle_range == 7.0
    assert c.body_size == 2.0

    # Incoherent candle: High < Open
    with pytest.raises(ValueError):
        Candle(
            timestamp=now,
            open=100.0,
            high=95.0,  # Invalid
            low=90.0,
            close=92.0,
            volume=1000,
            instrument_key="TEST_KEY",
        )


def test_candle_batch_chronological_ordering():
    """
    Upstox API returns candles in reverse-chronological order (newest first).
    Verify that CandleBatch reverses them to strictly chronological order (oldest first).
    """
    raw_api_response = [
        ["2024-10-31T09:17:00+05:30", 102.0, 104.0, 101.5, 103.0, 1200, 50000],
        ["2024-10-31T09:16:00+05:30", 101.0, 102.5, 100.5, 102.0, 1500, 49000],
        ["2024-10-31T09:15:00+05:30", 100.0, 101.5, 99.5, 101.0, 2000, 48000],
    ]

    batch = CandleBatch.from_upstox_raw(
        instrument_key="TEST_KEY",
        interval=CandleInterval.MINUTE_1,
        raw_candles=raw_api_response,
    )

    assert batch.count() == 3
    # First candle must be 09:15
    assert batch.candles[0].timestamp.minute == 15
    # Last candle must be 09:17
    assert batch.candles[-1].timestamp.minute == 17
    # Verify timestamps are strictly increasing
    assert batch.candles[0].timestamp < batch.candles[1].timestamp < batch.candles[2].timestamp
