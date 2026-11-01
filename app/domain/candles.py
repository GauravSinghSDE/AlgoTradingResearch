"""
Domain models for OHLCV candles, candle intervals, and candle batches.
Enforces strict price coherence and IST (Asia/Kolkata) timezone normalization.
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, field_validator

# Indian Standard Time Zone
IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class CandleInterval(str, Enum):
    MINUTE_1 = "1minute"
    MINUTE_3 = "3minute"
    MINUTE_5 = "5minute"
    MINUTE_15 = "15minute"
    MINUTE_30 = "30minute"
    DAY = "day"

    @property
    def minutes(self) -> int:
        mapping = {
            "1minute": 1,
            "3minute": 3,
            "5minute": 5,
            "15minute": 15,
            "30minute": 30,
            "day": 375,  # 09:15 to 15:30 = 375 trading minutes
        }
        return mapping[self.value]


class Candle(BaseModel):
    """Immutable single OHLCV observation."""

    timestamp: datetime = Field(..., description="Observation start time in IST")
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: int = Field(default=0, ge=0)
    open_interest: int = Field(default=0, ge=0)
    instrument_key: str = Field(..., description="Associated instrument key")

    model_config = {"frozen": True, "extra": "ignore"}

    @field_validator("timestamp", mode="before")
    @classmethod
    def normalize_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
        elif isinstance(v, datetime):
            dt = v
        else:
            raise ValueError(f"Unsupported timestamp type: {type(v)}")

        if dt.tzinfo is None:
            # Assume local IST if naive
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)
        return dt

    @field_validator("high")
    @classmethod
    def validate_high(cls, v: float, info: Any) -> float:
        # High must be >= open if open is already validated
        data = info.data
        if "open" in data and v < data["open"]:
            raise ValueError(f"High ({v}) cannot be less than Open ({data['open']})")
        return v

    @field_validator("low")
    @classmethod
    def validate_low(cls, v: float, info: Any) -> float:
        data = info.data
        if "open" in data and v > data["open"]:
            raise ValueError(f"Low ({v}) cannot be greater than Open ({data['open']})")
        if "high" in data and v > data["high"]:
            raise ValueError(f"Low ({v}) cannot be greater than High ({data['high']})")
        return v

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def candle_range(self) -> float:
        return self.high - self.low

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)


class CandleBatch(BaseModel):
    """Collection of candles for an instrument, sorted chronologically."""

    instrument_key: str
    interval: CandleInterval
    candles: list[Candle] = Field(default_factory=list)

    @classmethod
    def from_upstox_raw(
        cls,
        instrument_key: str,
        interval: CandleInterval,
        raw_candles: list[list[Any]],
    ) -> CandleBatch:
        """
        Parses Upstox raw API format:
        [timestamp_str, open, high, low, close, volume, open_interest]
        Upstox returns candles in reverse chronological order (newest first).
        We reverse to ensure strictly chronological order (oldest first).
        """
        parsed: list[Candle] = []
        for row in raw_candles:
            if len(row) < 5:
                continue
            ts = row[0]
            o = float(row[1])
            h = float(row[2])
            low_val = float(row[3])
            c = float(row[4])
            v = int(row[5]) if len(row) > 5 and row[5] is not None else 0
            oi = int(row[6]) if len(row) > 6 and row[6] is not None else 0

            # Price coherence safeguard
            h = max(h, o, c)
            low_val = min(low_val, o, c)

            parsed.append(
                Candle(
                    timestamp=ts,
                    open=o,
                    high=h,
                    low=low_val,
                    close=c,
                    volume=v,
                    open_interest=oi,
                    instrument_key=instrument_key,
                )
            )

        # Sort chronologically (oldest first)
        parsed.sort(key=lambda x: x.timestamp)
        return cls(instrument_key=instrument_key, interval=interval, candles=parsed)

    def to_dataframe(self) -> pd.DataFrame:
        """Converts candle batch into a standard pandas DataFrame indexed by timestamp."""
        if not self.candles:
            return pd.DataFrame(
                columns=[
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "open_interest",
                    "instrument_key",
                ]
            )
        data = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
                "open_interest": c.open_interest,
                "instrument_key": c.instrument_key,
            }
            for c in self.candles
        ]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df

    def count(self) -> int:
        return len(self.candles)

    def oldest_timestamp(self) -> datetime | None:
        return self.candles[0].timestamp if self.candles else None

    def newest_timestamp(self) -> datetime | None:
        return self.candles[-1].timestamp if self.candles else None
