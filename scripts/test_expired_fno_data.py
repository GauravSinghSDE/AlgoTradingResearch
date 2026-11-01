"""
Historical Data Proof-of-Concept & Capability Verifier (Rule B Compliance).
Discovers expired NIFTY futures and options, retrieves 1-minute historical candles,
analyzes data gaps and coverage, and generates a formal data provenance report.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.brokers.upstox.client import UpstoxClient
from app.core.config import settings
from app.data.storage import MarketDataStore
from app.data.validation import validate_candle_batch
from app.domain.candles import CandleInterval
from app.domain.instruments import FutureContract, OptionContract


async def run_proof_of_concept() -> int:
    print("=" * 70)
    print("AlgoTradingResearch -- Historical F&O Data Proof-of-Concept (Rule B)")
    print("=" * 70)

    has_token = bool(
        settings.UPSTOX_ACCESS_TOKEN and settings.UPSTOX_ACCESS_TOKEN != "your_access_token_here"
    )
    store = MarketDataStore()
    report_output_dir = settings.REPORTS_DIR / "poc_reports"
    report_output_dir.mkdir(parents=True, exist_ok=True)

    poc_summary = {
        "run_timestamp": datetime.now().isoformat(),
        "broker": "Upstox",
        "has_access_token": has_token,
        "underlying": "NSE_INDEX|Nifty 50",
        "steps": {},
        "limitations": [],
    }

    if not has_token:
        print("[WARN] No valid UPSTOX_ACCESS_TOKEN found in .env.")
        print(
            "Broker documentation verified, but live HTTP queries require daily authentication token."
        )
        print("To run with live broker API, authenticate first using:")
        print("   python scripts/verify_upstox_auth.py")
        print("\nDocumenting verified Upstox API endpoints & generating provenance schema...")

        poc_summary["steps"]["authentication"] = "SKIPPED_NO_TOKEN"
        poc_summary["limitations"].append(
            "Live API call skipped: UPSTOX_ACCESS_TOKEN not present. Run verify_upstox_auth.py with active token."
        )

        # Write provenance report documenting status
        poc_file = report_output_dir / "fno_historical_poc_report.json"
        with open(poc_file, "w", encoding="utf-8") as f:
            json.dump(poc_summary, f, indent=2)

        print(f"Report saved to: {poc_file}")
        return 0

    client = UpstoxClient(access_token=settings.UPSTOX_ACCESS_TOKEN)

    # -------------------------------------------------------------------------
    # STEP 1: Verify Authentication & Read-only profile
    # -------------------------------------------------------------------------
    print("\n[Step 1] Authenticating with Upstox API...")
    try:
        profile = await client.validate_session()
        print(f"[OK] Authenticated as UCC: {profile.get('user_id')}")
        poc_summary["steps"]["authentication"] = "SUCCESS"
    except Exception as e:
        print(f"[FAIL] Authentication failed: {e}")
        poc_summary["steps"]["authentication"] = f"FAILED: {e}"
        poc_summary["limitations"].append(f"Auth check failed: {e}")
        return 1

    # -------------------------------------------------------------------------
    # STEP 2: Discover Expired Contract Expiries
    # -------------------------------------------------------------------------
    print("\n[Step 2] Discovering expired dates for NIFTY 50...")
    expiries: list[str] = []
    try:
        expiries = await client.get_expiries("NSE_INDEX|Nifty 50")
        print(f"[OK] Found {len(expiries)} historical expiries: {expiries[:5]}...")
        poc_summary["steps"]["expiries_discovery"] = {
            "status": "SUCCESS",
            "count": len(expiries),
            "sample_expiries": expiries[:5],
        }
    except Exception as e:
        print(f"[FAIL] Expired dates discovery failed: {e}")
        poc_summary["steps"]["expiries_discovery"] = f"FAILED: {e}"
        poc_summary["limitations"].append(f"Expiries discovery failed: {e}")
        return 1

    if not expiries:
        print("[FAIL] No expired dates returned by broker.")
        return 1

    target_expiry = expiries[0]
    print(f"Selected target expiry date for testing: {target_expiry}")

    # -------------------------------------------------------------------------
    # STEP 3: Discover Expired Future Contract
    # -------------------------------------------------------------------------
    print(f"\n[Step 3] Discovering expired Futures for expiry {target_expiry}...")
    futures: list[FutureContract] = []
    try:
        futures = await client.get_expired_future_contracts("NSE_INDEX|Nifty 50", target_expiry)
        print(f"[OK] Discovered {len(futures)} expired future contract(s).")
        if futures:
            f_contract = futures[0]
            print(
                f"   Symbol: {f_contract.trading_symbol}, Key: {f_contract.instrument_key}, Lot: {f_contract.lot_size}"
            )
            poc_summary["steps"]["future_contract"] = {
                "symbol": f_contract.trading_symbol,
                "instrument_key": f_contract.instrument_key,
                "lot_size": f_contract.lot_size,
            }
    except Exception as e:
        print(f"[FAIL] Future contracts discovery failed: {e}")
        poc_summary["steps"]["future_contract"] = f"FAILED: {e}"
        poc_summary["limitations"].append(f"Future discovery error: {e}")

    # -------------------------------------------------------------------------
    # STEP 4: Discover Expired Options Contract
    # -------------------------------------------------------------------------
    print(f"\n[Step 4] Discovering expired Options for expiry {target_expiry}...")
    options: list[OptionContract] = []
    try:
        options = await client.get_expired_option_contracts("NSE_INDEX|Nifty 50", target_expiry)
        print(f"[OK] Discovered {len(options)} expired option contracts.")
        if options:
            opt_contract = options[0]
            print(
                f"   Sample: {opt_contract.trading_symbol}, Key: {opt_contract.instrument_key}, Strike: {opt_contract.strike_price}, Type: {opt_contract.instrument_type.value}"
            )
            poc_summary["steps"]["option_contract"] = {
                "symbol": opt_contract.trading_symbol,
                "instrument_key": opt_contract.instrument_key,
                "strike": opt_contract.strike_price,
                "type": opt_contract.instrument_type.value,
                "lot_size": opt_contract.lot_size,
            }
    except Exception as e:
        print(f"[FAIL] Option contracts discovery failed: {e}")
        poc_summary["steps"]["option_contract"] = f"FAILED: {e}"
        poc_summary["limitations"].append(f"Option discovery error: {e}")

    # -------------------------------------------------------------------------
    # STEP 5: Retrieve 1-minute historical candles for Expired Future
    # -------------------------------------------------------------------------
    if futures:
        fut = futures[0]
        print(f"\n[Step 5] Fetching 1-minute historical candles for Future {fut.instrument_key}...")
        try:
            to_date = target_expiry
            from_date = (datetime.strptime(target_expiry, "%Y-%m-%d") - timedelta(days=5)).strftime(
                "%Y-%m-%d"
            )
            batch_fut = await client.get_expired_candles(
                expired_instrument_key=fut.instrument_key,
                interval=CandleInterval.MINUTE_1,
                to_date=to_date,
                from_date=from_date,
            )
            print(f"[OK] Received {batch_fut.count()} candles for {fut.trading_symbol}")
            q_fut = validate_candle_batch(batch_fut)
            print(
                f"   Validation Status: {q_fut.status}, Duplicates: {q_fut.duplicate_timestamps_count}, Coverage: {q_fut.actual_coverage_pct}%"
            )

            store.save_candles(batch_fut)
            store.save_quality_report(q_fut)
            poc_summary["steps"]["future_candles"] = q_fut.model_dump()
        except Exception as e:
            print(f"[FAIL] Failed to retrieve candles for future: {e}")
            poc_summary["steps"]["future_candles"] = f"FAILED: {e}"
            poc_summary["limitations"].append(f"Future candle retrieval: {e}")

    # -------------------------------------------------------------------------
    # STEP 6: Retrieve 1-minute historical candles for Expired Option
    # -------------------------------------------------------------------------
    if options:
        opt = options[0]
        print(f"\n[Step 6] Fetching 1-minute historical candles for Option {opt.instrument_key}...")
        try:
            to_date = target_expiry
            from_date = (datetime.strptime(target_expiry, "%Y-%m-%d") - timedelta(days=3)).strftime(
                "%Y-%m-%d"
            )
            batch_opt = await client.get_expired_candles(
                expired_instrument_key=opt.instrument_key,
                interval=CandleInterval.MINUTE_1,
                to_date=to_date,
                from_date=from_date,
            )
            print(f"[OK] Received {batch_opt.count()} candles for {opt.trading_symbol}")
            q_opt = validate_candle_batch(batch_opt)
            print(
                f"   Validation Status: {q_opt.status}, Duplicates: {q_opt.duplicate_timestamps_count}, Coverage: {q_opt.actual_coverage_pct}%"
            )

            store.save_candles(batch_opt)
            store.save_quality_report(q_opt)
            poc_summary["steps"]["option_candles"] = q_opt.model_dump()
        except Exception as e:
            print(f"[FAIL] Failed to retrieve candles for option: {e}")
            poc_summary["steps"]["option_candles"] = f"FAILED: {e}"
            poc_summary["limitations"].append(f"Option candle retrieval: {e}")

    # Save summary report
    poc_file = report_output_dir / "fno_historical_poc_report.json"
    with open(poc_file, "w", encoding="utf-8") as f:
        json.dump(poc_summary, f, indent=2, default=str)

    print("\n" + "=" * 70)
    print(f"Historical F&O Proof-of-Concept complete! Report saved to {poc_file}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run_proof_of_concept()))
