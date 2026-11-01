"""
Historical Market Data Quality Validation Engine.
Analyzes candle series for duplicates, invalid prices, volume/OI gaps, and distinguishes
exchange holidays/closures from legitimate missing data.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.data.calendar import (
    IST,
    get_expected_minute_timestamps,
)
from app.domain.candles import CandleBatch, CandleInterval


class DataQualityReport(BaseModel):
    """Detailed quality validation report for a downloaded candle batch."""

    instrument_key: str
    interval: str
    total_candles: int
    oldest_timestamp: datetime | None = None
    newest_timestamp: datetime | None = None
    expected_candles_in_range: int = 0
    actual_coverage_pct: float = 0.0
    duplicate_timestamps_count: int = 0
    invalid_price_count: int = 0
    zero_volume_count: int = 0
    null_or_nan_count: int = 0
    missing_trading_minutes_count: int = 0
    missing_minute_samples: list[str] = Field(default_factory=list)
    status: str = "PENDING"  # "PASSED", "WARNING", "FAILED"
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def validate_candle_batch(batch: CandleBatch) -> DataQualityReport:
    """
    Performs comprehensive data validation on a CandleBatch.
    Returns structured DataQualityReport.
    """
    report = DataQualityReport(
        instrument_key=batch.instrument_key,
        interval=batch.interval.value,
        total_candles=batch.count(),
        oldest_timestamp=batch.oldest_timestamp(),
        newest_timestamp=batch.newest_timestamp(),
    )

    if batch.count() == 0:
        report.status = "FAILED"
        report.errors.append("Candle batch is empty. No observations received.")
        return report

    seen_timestamps: set[datetime] = set()
    timestamps_list: list[datetime] = []

    for c in batch.candles:
        # Timezone check
        ts = c.timestamp.astimezone(IST) if c.timestamp.tzinfo else c.timestamp.replace(tzinfo=IST)
        timestamps_list.append(ts)

        # Duplicate check
        if ts in seen_timestamps:
            report.duplicate_timestamps_count += 1
        else:
            seen_timestamps.add(ts)

        # Price sanity check
        if c.open <= 0 or c.high <= 0 or c.low <= 0 or c.close <= 0:
            report.invalid_price_count += 1
            report.errors.append(f"Non-positive price at {ts.isoformat()}")

        if c.high < c.low or c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
            report.invalid_price_count += 1
            report.errors.append(
                f"Incoherent OHLC values at {ts.isoformat()}: O={c.open}, H={c.high}, L={c.low}, C={c.close}"
            )

        # Volume check
        if c.volume == 0:
            report.zero_volume_count += 1

    # Trading hour gap analysis (for 1-minute data)
    if (
        batch.interval == CandleInterval.MINUTE_1
        and report.oldest_timestamp
        and report.newest_timestamp
    ):
        start_d = report.oldest_timestamp.date()
        end_d = report.newest_timestamp.date()
        expected_timestamps = get_expected_minute_timestamps(start_d, end_d)
        report.expected_candles_in_range = len(expected_timestamps)

        missing_ts = [
            ts
            for ts in expected_timestamps
            if ts not in seen_timestamps
            and report.oldest_timestamp <= ts <= report.newest_timestamp
        ]
        report.missing_trading_minutes_count = len(missing_ts)
        report.missing_minute_samples = [ts.strftime("%Y-%m-%d %H:%M") for ts in missing_ts[:10]]

        if report.expected_candles_in_range > 0:
            report.actual_coverage_pct = round(
                (report.total_candles / report.expected_candles_in_range) * 100.0, 2
            )
    else:
        report.actual_coverage_pct = 100.0

    # Determine validation status
    if report.duplicate_timestamps_count > 0:
        report.warnings.append(f"Found {report.duplicate_timestamps_count} duplicate timestamps.")
    if report.invalid_price_count > 0:
        report.errors.append(f"Found {report.invalid_price_count} price anomalies.")

    if report.errors:
        report.status = "FAILED"
    elif report.warnings or report.missing_trading_minutes_count > 10:
        report.status = "WARNING"
    else:
        report.status = "PASSED"

    return report
