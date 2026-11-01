"""
Domain models for order intents, executions, fills, positions, and closed trades.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class OrderIntent(BaseModel):
    """Strategy output expressing intent to trade."""

    order_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime
    instrument_key: str
    trading_symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    quantity: int = Field(
        ..., gt=0, description="Quantity in units (must be integer multiple of lot size)"
    )
    limit_price: float | None = None
    stop_loss_price: float | None = None
    target_price: float | None = None
    tag: str = Field(default="", description="Strategy or rule identifier")


class TradeFill(BaseModel):
    """Record of an executed order fill."""

    fill_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: str
    timestamp: datetime
    instrument_key: str
    trading_symbol: str
    side: OrderSide
    quantity: int
    fill_price: float
    slippage: float = 0.0
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    gst: float = 0.0
    sebi_charges: float = 0.0
    stamp_duty: float = 0.0

    @property
    def total_charges(self) -> float:
        return (
            self.brokerage
            + self.stt
            + self.exchange_charges
            + self.gst
            + self.sebi_charges
            + self.stamp_duty
        )

    @property
    def turnover(self) -> float:
        return self.quantity * self.fill_price


class Position(BaseModel):
    """Live or backtested open position in an instrument."""

    instrument_key: str
    trading_symbol: str
    quantity: int = 0  # positive for long, negative for short
    average_entry_price: float = 0.0
    current_price: float = 0.0
    realized_pnl: float = 0.0
    lot_size: int = 1

    @property
    def is_open(self) -> bool:
        return self.quantity != 0

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity == 0:
            return 0.0
        return (self.current_price - self.average_entry_price) * self.quantity

    @property
    def market_value(self) -> float:
        return abs(self.quantity) * self.current_price


class TradeRecord(BaseModel):
    """Completed round-trip closed trade for reporting and metrics."""

    trade_id: str = Field(default_factory=lambda: str(uuid4()))
    instrument_key: str
    trading_symbol: str
    side: OrderSide  # Entry side
    quantity: int
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: datetime
    exit_price: float
    gross_pnl: float
    net_pnl: float
    total_costs: float
    return_pct: float
    duration: timedelta
    exit_reason: str = "SIGNAL"  # "SIGNAL", "STOP_LOSS", "TARGET", "EXPIRY_SQUAREOFF"
