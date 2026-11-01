"""
Historical candle storage using Apache Parquet and JSON provenance metadata.
Provides idempotent writes, fast columnar reads, and deduplication.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.core.config import settings
from app.core.logging import logger
from app.data.validation import DataQualityReport
from app.domain.candles import Candle, CandleBatch, CandleInterval


def _sanitize_filename(name: str) -> str:
    """Sanitizes instrument key for filesystem paths."""
    return re.sub(r'[\\/*?:"<>| ]', "_", name)


class MarketDataStore:
    """Manages local storage and retrieval of historical market data."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.DATA_DIR
        self.candles_dir = self.base_dir / "candles"
        self.reports_dir = self.base_dir / "reports"
        self.candles_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _get_parquet_path(self, instrument_key: str, interval: CandleInterval) -> Path:
        safe_key = _sanitize_filename(instrument_key)
        instrument_dir = self.candles_dir / safe_key
        instrument_dir.mkdir(parents=True, exist_ok=True)
        return instrument_dir / f"{interval.value}.parquet"

    def save_candles(self, batch: CandleBatch) -> Path:
        """
        Saves candle batch to Parquet with deduplication against existing data.
        Ensures idempotent rerun capability.
        """
        target_path = self._get_parquet_path(batch.instrument_key, batch.interval)
        new_df = batch.to_dataframe()

        if new_df.empty:
            logger.warning("Attempted to save empty candle batch for %s", batch.instrument_key)
            return target_path

        if target_path.exists():
            # Merge and deduplicate
            try:
                existing_df = pd.read_parquet(target_path)
                combined = pd.concat([existing_df, new_df])
                combined = combined[~combined.index.duplicated(keep="last")]
                combined.sort_index(inplace=True)
                combined.to_parquet(target_path, compression="snappy")
                logger.info(
                    "Updated %s with %d total candles (added %d)",
                    target_path.name,
                    len(combined),
                    len(new_df),
                )
                return target_path
            except Exception as e:
                logger.error("Error reading existing parquet %s: %s. Overwriting.", target_path, e)

        # Write fresh
        new_df.sort_index(inplace=True)
        new_df.to_parquet(target_path, compression="snappy")
        logger.info("Saved %d candles to %s", len(new_df), target_path)
        return target_path

    def load_candles(
        self,
        instrument_key: str,
        interval: CandleInterval,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> CandleBatch | None:
        """Loads candles from local Parquet file."""
        target_path = self._get_parquet_path(instrument_key, interval)
        if not target_path.exists():
            return None

        df = pd.read_parquet(target_path)
        if start_date:
            df = df[df.index >= pd.Timestamp(start_date, tz="Asia/Kolkata")]
        if end_date:
            df = df[df.index <= pd.Timestamp(end_date, tz="Asia/Kolkata")]

        if df.empty:
            return CandleBatch(instrument_key=instrument_key, interval=interval, candles=[])

        candles: list[Candle] = []
        for ts, row in df.iterrows():
            candles.append(
                Candle(
                    timestamp=ts.to_pydatetime(),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    open_interest=int(row["open_interest"]),
                    instrument_key=instrument_key,
                )
            )

        return CandleBatch(instrument_key=instrument_key, interval=interval, candles=candles)

    def save_quality_report(self, report: DataQualityReport) -> Path:
        """Saves JSON data quality report."""
        safe_key = _sanitize_filename(report.instrument_key)
        target = self.reports_dir / f"quality_{safe_key}_{report.interval}.json"
        with open(target, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        logger.info("Quality report saved to %s", target)
        return target
