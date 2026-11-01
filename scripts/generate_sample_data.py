"""
Sample Historical Market Data Generator.
Creates a realistic 1-minute historical dataset for NIFTY 50 in Parquet format
for offline backtesting and dashboard exploration.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.data.calendar import get_expected_minute_timestamps
from app.data.storage import MarketDataStore
from app.data.validation import validate_candle_batch
from app.domain.candles import Candle, CandleBatch, CandleInterval


def generate_sample_nifty_data(
    instrument_key: str = "NSE_INDEX|Nifty 50",
    days: int = 5,
    start_price: float = 24500.0,
) -> Path:
    end_d = date(2024, 10, 31)
    start_d = end_d - timedelta(days=days + 3)

    timestamps = get_expected_minute_timestamps(start_d, end_d)
    # Take the last 5 trading days worth of timestamps (approx 5 * 375 = 1875 minutes)
    timestamps = timestamps[-days * 375:]

    random.seed(42)  # Deterministic seed
    current_price = start_price
    candles: list[Candle] = []

    for ts in timestamps:
        drift = random.gauss(0.1, 4.0)
        open_p = round(current_price, 2)
        close_p = round(open_p + drift, 2)
        high_p = round(max(open_p, close_p) + abs(random.gauss(1.0, 2.0)), 2)
        low_p = round(min(open_p, close_p) - abs(random.gauss(1.0, 2.0)), 2)
        volume = random.randint(500, 15000)
        oi = random.randint(1000000, 2500000)

        candles.append(
            Candle(
                timestamp=ts,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
                open_interest=oi,
                instrument_key=instrument_key,
            )
        )
        current_price = close_p

    batch = CandleBatch(
        instrument_key=instrument_key,
        interval=CandleInterval.MINUTE_1,
        candles=candles,
    )

    store = MarketDataStore()
    target_path = store.save_candles(batch)
    report = validate_candle_batch(batch)
    store.save_quality_report(report)

    print(f"Generated {batch.count()} realistic 1-minute sample candles for {instrument_key}")
    print(f"Saved to: {target_path}")
    print(f"Data Quality Report: {report.status} (Coverage: {report.actual_coverage_pct}%)")
    return target_path


def generate_sample_option_data(
    instrument_key: str = "NSE_FO|NIFTY24O3124500CE",
    days: int = 5,
    start_price: float = 120.0,
) -> Path:
    end_d = date(2024, 10, 31)
    start_d = end_d - timedelta(days=days + 3)

    timestamps = get_expected_minute_timestamps(start_d, end_d)
    timestamps = timestamps[-days * 375:]

    random.seed(99)
    current_price = start_price
    candles: list[Candle] = []

    for ts in timestamps:
        drift = random.gauss(0.05, 1.2)
        open_p = max(5.0, round(current_price, 2))
        close_p = max(5.0, round(open_p + drift, 2))
        high_p = round(max(open_p, close_p) + abs(random.gauss(0.5, 0.8)), 2)
        low_p = max(1.0, round(min(open_p, close_p) - abs(random.gauss(0.5, 0.8)), 2))
        volume = random.randint(1000, 50000)
        oi = random.randint(2000000, 5000000)

        candles.append(
            Candle(
                timestamp=ts,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=volume,
                open_interest=oi,
                instrument_key=instrument_key,
            )
        )
        current_price = close_p

    batch = CandleBatch(
        instrument_key=instrument_key,
        interval=CandleInterval.MINUTE_1,
        candles=candles,
    )

    store = MarketDataStore()
    target_path = store.save_candles(batch)
    report = validate_candle_batch(batch)
    store.save_quality_report(report)

    print(f"Generated {batch.count()} sample option candles for {instrument_key}")
    print(f"Saved to: {target_path}")
    return target_path


if __name__ == "__main__":
    generate_sample_nifty_data()
    generate_sample_option_data()
