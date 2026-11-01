"""
Domain models for financial instruments, derivatives, futures, and options.
Normalizes broker-specific representations into clean, typed domain objects.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"


class Segment(str, Enum):
    NSE_EQ = "NSE_EQ"
    NSE_FO = "NSE_FO"
    NSE_INDEX = "NSE_INDEX"
    BSE_EQ = "BSE_EQ"
    BSE_FO = "BSE_FO"
    BSE_INDEX = "BSE_INDEX"
    MCX_FO = "MCX_FO"


class InstrumentType(str, Enum):
    EQUITY = "EQ"
    INDEX = "INDEX"
    FUTURE = "FUT"
    CALL_OPTION = "CE"
    PUT_OPTION = "PE"


class BaseInstrument(BaseModel):
    """Base financial instrument representation."""

    instrument_key: str = Field(
        ..., description="Unique broker instrument key, e.g. NSE_INDEX|Nifty 50"
    )
    exchange_token: str | None = Field(default=None, description="Exchange-specific numeric token")
    trading_symbol: str = Field(..., description="Human-readable ticker symbol")
    name: str = Field(..., description="Display / company name")
    segment: Segment
    exchange: Exchange
    lot_size: int = Field(default=1, ge=1, description="Minimum tradable lot size")
    tick_size: float = Field(default=0.05, gt=0, description="Minimum price movement")
    freeze_quantity: int | None = Field(default=None, description="Exchange order freeze quantity")

    model_config = {"frozen": True, "extra": "ignore"}


class IndexInstrument(BaseInstrument):
    """Cash market underlying index (e.g. NIFTY 50, BANKNIFTY)."""

    segment: Segment = Segment.NSE_INDEX
    exchange: Exchange = Exchange.NSE
    instrument_type: InstrumentType = InstrumentType.INDEX


class EquityInstrument(BaseInstrument):
    """Cash equity stock."""

    segment: Segment = Segment.NSE_EQ
    exchange: Exchange = Exchange.NSE
    instrument_type: InstrumentType = InstrumentType.EQUITY
    isin: str | None = None


class DerivativeContract(BaseInstrument):
    """Derivative contract with expiry date and underlying link."""

    segment: Segment = Segment.NSE_FO
    exchange: Exchange = Exchange.NSE
    expiry: date
    underlying_key: str
    underlying_symbol: str
    is_expired: bool = False

    @field_validator("expiry", mode="before")
    @classmethod
    def parse_expiry(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            from datetime import datetime

            for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return datetime.strptime(v[:10], fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Unable to parse expiry date: {v}")
        raise ValueError(f"Invalid expiry type: {type(v)}")


class FutureContract(DerivativeContract):
    """Index or stock futures contract."""

    instrument_type: InstrumentType = InstrumentType.FUTURE


class OptionContract(DerivativeContract):
    """Call or Put option contract."""

    instrument_type: InstrumentType
    strike_price: float = Field(..., gt=0)
    weekly: bool = False

    @field_validator("instrument_type", mode="before")
    @classmethod
    def parse_option_type(cls, v: Any) -> InstrumentType:
        if isinstance(v, InstrumentType):
            return v
        v_str = str(v).upper()
        if v_str in ("CE", "CALL"):
            return InstrumentType.CALL_OPTION
        if v_str in ("PE", "PUT"):
            return InstrumentType.PUT_OPTION
        raise ValueError(f"Invalid option type '{v}', expected CE or PE")

    @property
    def is_call(self) -> bool:
        return self.instrument_type == InstrumentType.CALL_OPTION

    @property
    def is_put(self) -> bool:
        return self.instrument_type == InstrumentType.PUT_OPTION


def parse_upstox_contract(raw: dict[str, Any], is_expired: bool = False) -> DerivativeContract:
    """Factory function converting Upstox API response dictionary into typed domain models."""
    inst_type = str(raw.get("instrument_type", "")).upper()
    common_args = {
        "instrument_key": raw["instrument_key"],
        "exchange_token": str(raw.get("exchange_token", "")),
        "trading_symbol": raw.get("trading_symbol") or raw.get("symbol", raw["instrument_key"]),
        "name": raw.get("name", ""),
        "segment": Segment(raw.get("segment", "NSE_FO")),
        "exchange": Exchange(raw.get("exchange", "NSE")),
        "lot_size": int(raw.get("lot_size", 1)),
        "tick_size": float(raw.get("tick_size", 0.05)),
        "freeze_quantity": int(raw["freeze_quantity"]) if raw.get("freeze_quantity") else None,
        "expiry": raw["expiry"],
        "underlying_key": raw.get("underlying_key", ""),
        "underlying_symbol": raw.get("underlying_symbol", raw.get("name", "")),
        "is_expired": is_expired,
    }

    if inst_type in ("FUT", "FUTURE"):
        return FutureContract(**common_args)
    elif inst_type in ("CE", "PE"):
        return OptionContract(
            **common_args,
            instrument_type=inst_type,
            strike_price=float(raw["strike_price"]),
            weekly=bool(raw.get("weekly", False)),
        )
    else:
        raise ValueError(f"Unknown derivative instrument_type: {inst_type}")
