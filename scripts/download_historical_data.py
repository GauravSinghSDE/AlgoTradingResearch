"""
CLI Downloader for Historical Candle Data (Active or Expired F&O).
Fetches candles from Upstox, validates data quality, and persists deduplicated Parquet files.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.brokers.upstox.client import UpstoxClient
from app.data.storage import MarketDataStore
from app.data.validation import validate_candle_batch
from app.domain.candles import CandleInterval


async def main() -> int:
    parser = argparse.ArgumentParser(description="Download historical candles from Upstox")
    parser.add_argument("--key", required=True, help="Instrument key, e.g. 'NSE_INDEX|Nifty 50'")
    parser.add_argument(
        "--interval",
        default="1minute",
        choices=["1minute", "5minute", "15minute", "30minute", "day"],
    )
    parser.add_argument("--from-date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to-date", required=True, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--expired", action="store_true", help="Set flag if instrument is an expired derivative"
    )

    args = parser.parse_args()

    print(
        f"Downloading {args.interval} candles for {args.key} from {args.from_date} to {args.to_date}..."
    )
    client = UpstoxClient()
    store = MarketDataStore()
    interval_enum = CandleInterval(args.interval)

    try:
        if args.expired:
            batch = await client.get_expired_candles(
                expired_instrument_key=args.key,
                interval=interval_enum,
                to_date=args.to_date,
                from_date=args.from_date,
            )
        else:
            batch = await client.get_historical_candles(
                instrument_key=args.key,
                interval=interval_enum,
                to_date=args.to_date,
                from_date=args.from_date,
            )

        print(f"[OK] Received {batch.count()} candles.")
        report = validate_candle_batch(batch)
        print(
            f"Data Quality: {report.status} (Coverage: {report.actual_coverage_pct}%, Duplicates: {report.duplicate_timestamps_count})"
        )

        if batch.count() > 0:
            target = store.save_candles(batch)
            store.save_quality_report(report)
            print(f"Persisted to: {target}")

        return 0
    except Exception as e:
        print(f"[FAIL] Download failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
