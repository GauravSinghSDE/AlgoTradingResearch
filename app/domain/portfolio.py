"""
Domain models for portfolio state, margin tracking, equity curve, and cash ledger.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.domain.trades import Position, TradeFill, TradeRecord


class PortfolioState(BaseModel):
    """Snapshot of portfolio cash, equity, and open positions."""

    starting_capital: float = 25000.0
    cash: float = 25000.0
    positions: dict[str, Position] = Field(default_factory=dict)
    closed_trades: list[TradeRecord] = Field(default_factory=list)
    fills: list[TradeFill] = Field(default_factory=list)
    high_water_mark: float = 25000.0
    current_date: date | None = None
    day_start_equity: float = 25000.0

    @property
    def total_unrealized_pnl(self) -> float:
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    @property
    def total_realized_pnl(self) -> float:
        return sum(trade.net_pnl for trade in self.closed_trades)

    @property
    def equity(self) -> float:
        """Total account equity = cash + market value of long positions - liabilities."""
        return self.cash + sum(pos.quantity * pos.current_price for pos in self.positions.values())

    @property
    def open_position_count(self) -> int:
        return sum(1 for pos in self.positions.values() if pos.is_open)

    @property
    def current_drawdown_amount(self) -> float:
        return max(0.0, self.high_water_mark - self.equity)

    @property
    def current_drawdown_pct(self) -> float:
        if self.high_water_mark <= 0:
            return 0.0
        return (self.current_drawdown_amount / self.high_water_mark) * 100.0

    @property
    def daily_pnl(self) -> float:
        return self.equity - self.day_start_equity

    @property
    def daily_loss_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        pnl = self.daily_pnl
        if pnl >= 0:
            return 0.0
        return (abs(pnl) / self.day_start_equity) * 100.0

    def update_prices(self, price_map: dict[str, float]) -> None:
        """Updates current mark-to-market prices for all open positions."""
        for key, price in price_map.items():
            if key in self.positions:
                self.positions[key].current_price = price
        # Update high water mark
        if self.equity > self.high_water_mark:
            self.high_water_mark = self.equity

    def on_new_day(self, current_date: date) -> None:
        """Resets daily P&L baseline at start of trading day."""
        if self.current_date != current_date:
            self.current_date = current_date
            self.day_start_equity = self.equity
