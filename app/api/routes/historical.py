"""
Historical data discovery and download API endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.brokers.upstox.client import UpstoxClient
from app.data.storage import MarketDataStore
from app.data.validation import DataQualityReport, validate_candle_batch
from app.domain.candles import CandleInterval

router = APIRouter(prefix="/historical", tags=["Historical Data"])
store = MarketDataStore()


class DownloadRequest(BaseModel):
    instrument_key: str
    interval: str = "1minute"
    from_date: str
    to_date: str
    is_expired: bool = True


@router.get("/expiries")
async def get_expiries(
    underlying_key: str = Query("NSE_INDEX|Nifty 50", description="Underlying instrument key"),
) -> list[str]:
    """Retrieves expired contract dates from broker."""
    client = UpstoxClient()
    try:
        return await client.get_expiries(underlying_key=underlying_key)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/expired-futures")
async def get_expired_futures(
    underlying_key: str = Query("NSE_INDEX|Nifty 50"),
    expiry_date: str = Query(..., description="Expiry date in YYYY-MM-DD format"),
) -> list[dict[str, Any]]:
    """Retrieves expired futures for specified underlying and expiry."""
    client = UpstoxClient()
    try:
        contracts = await client.get_expired_future_contracts(underlying_key, expiry_date)
        return [c.model_dump() for c in contracts]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/expired-options")
async def get_expired_options(
    underlying_key: str = Query("NSE_INDEX|Nifty 50"),
    expiry_date: str = Query(..., description="Expiry date in YYYY-MM-DD format"),
) -> list[dict[str, Any]]:
    """Retrieves expired options for specified underlying and expiry."""
    client = UpstoxClient()
    try:
        contracts = await client.get_expired_option_contracts(underlying_key, expiry_date)
        return [c.model_dump() for c in contracts]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/download", response_model=DataQualityReport)
async def download_historical_candles(req: DownloadRequest) -> DataQualityReport:
    """Downloads historical candles, validates data quality, and persists to Parquet."""
    client = UpstoxClient()
    interval_enum = CandleInterval(req.interval)

    try:
        if req.is_expired:
            batch = await client.get_expired_candles(
                expired_instrument_key=req.instrument_key,
                interval=interval_enum,
                to_date=req.to_date,
                from_date=req.from_date,
            )
        else:
            batch = await client.get_historical_candles(
                instrument_key=req.instrument_key,
                interval=interval_enum,
                to_date=req.to_date,
                from_date=req.from_date,
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Broker download failed: {e}") from e

    # Validate data quality
    report = validate_candle_batch(batch)

    # Persist if valid
    if batch.count() > 0:
        store.save_candles(batch)
        store.save_quality_report(report)

    return report
