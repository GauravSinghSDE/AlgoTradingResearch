"""
Data quality, gap detection, and Parquet storage deduplication tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from app.data.calendar import IST, is_market_hours, is_trading_day
from app.data.storage import MarketDataStore
from app.data.validation import validate_candle_batch
from app.domain.candles import Candle, CandleBatch, CandleInterval


def test_duplicate_and_anomaly_detection():
    base_ts = datetime(2024, 10, 31, 9, 15, tzinfo=IST)
    candles = [
        Candle(
            timestamp=base_ts,
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=100,
            instrument_key="K1",
        ),
        # Duplicate timestamp
        Candle(
            timestamp=base_ts,
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume=100,
            instrument_key="K1",
        ),
        # Normal candle
        Candle(
            timestamp=base_ts + timedelta(minutes=1),
            open=101.0,
            high=103.0,
            low=100.5,
            close=102.5,
            volume=150,
            instrument_key="K1",
        ),
    ]

    batch = CandleBatch(instrument_key="K1", interval=CandleInterval.MINUTE_1, candles=candles)
    report = validate_candle_batch(batch)

    assert report.total_candles == 3
    assert report.duplicate_timestamps_count == 1
    assert report.status == "WARNING"


def test_calendar_trading_hours_and_holidays():
    """Verify that market hours and holidays are correctly identified."""
    # Diwali holiday 2024-11-01
    diwali = datetime(2024, 11, 1).date()
    assert is_trading_day(diwali) is False

    # Normal trading day 2024-10-31 (Thursday)
    normal_day = datetime(2024, 10, 31).date()
    assert is_trading_day(normal_day) is True

    # 09:14 IST is outside market hours
    pre_market = datetime(2024, 10, 31, 9, 14, tzinfo=IST)
    assert is_market_hours(pre_market) is False

    # 09:15 IST is market open
    market_open = datetime(2024, 10, 31, 9, 15, tzinfo=IST)
    assert is_market_hours(market_open) is True

    # 15:30 IST is market closed
    market_close = datetime(2024, 10, 31, 15, 30, tzinfo=IST)
    assert is_market_hours(market_close) is False


def test_parquet_store_idempotency_and_deduplication(tmp_path: Path):
    """Verify that saving data twice does not duplicate rows in Parquet."""
    store = MarketDataStore(base_dir=tmp_path)
    base_ts = datetime(2024, 10, 31, 9, 15, tzinfo=IST)

    batch1 = CandleBatch(
        instrument_key="NIFTY_FUT",
        interval=CandleInterval.MINUTE_1,
        candles=[
            Candle(
                timestamp=base_ts,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=10,
                instrument_key="NIFTY_FUT",
            ),
            Candle(
                timestamp=base_ts + timedelta(minutes=1),
                open=100.5,
                high=102.0,
                low=100.0,
                close=101.5,
                volume=20,
                instrument_key="NIFTY_FUT",
            ),
        ],
    )

    store.save_candles(batch1)
    loaded1 = store.load_candles("NIFTY_FUT", CandleInterval.MINUTE_1)
    assert loaded1 is not None
    assert loaded1.count() == 2

    # Save overlapping batch (batch1 + new candle)
    batch2 = CandleBatch(
        instrument_key="NIFTY_FUT",
        interval=CandleInterval.MINUTE_1,
        candles=[
            Candle(
                timestamp=base_ts + timedelta(minutes=1),
                open=100.5,
                high=102.0,
                low=100.0,
                close=101.5,
                volume=20,
                instrument_key="NIFTY_FUT",
            ),
            Candle(
                timestamp=base_ts + timedelta(minutes=2),
                open=101.5,
                high=103.0,
                low=101.0,
                close=102.0,
                volume=30,
                instrument_key="NIFTY_FUT",
            ),
        ],
    )
    store.save_candles(batch2)

    loaded2 = store.load_candles("NIFTY_FUT", CandleInterval.MINUTE_1)
    assert loaded2 is not None
    # 2 original + 1 new = 3 (deduplicated!)
    assert loaded2.count() == 3
