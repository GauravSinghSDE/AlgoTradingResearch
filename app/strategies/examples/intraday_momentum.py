"""
Intraday Range Breakout / Momentum Strategy.
Identifies opening range (e.g. first 15 or 30 minutes) and enters on confirmed high/low breakout.
"""

from __future__ import annotations

from datetime import date, time

from app.domain.candles import Candle
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide, OrderType
from app.strategies.base import BaseStrategy, StrategyConfig

OPENING_RANGE_END = time(9, 45)  # 30-min opening range (09:15 - 09:45)
INTRADAY_CUTOFF = time(15, 15)


class OpeningRangeBreakoutStrategy(BaseStrategy):
    """
    Opening Range Breakout (ORB) Strategy.
    Parameters:
    - lot_size: int (default 25)
    - stop_loss_pct: float (default 1.0%)
    - target_pct: float (default 2.0%)
    """

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        params = self.config.parameters
        self.lot_size = int(params.get("lot_size", 25))
        self.stop_loss_pct = float(params.get("stop_loss_pct", 1.0))
        self.target_pct = float(params.get("target_pct", 2.0))

        self.current_date: date | None = None
        self.range_high: float | None = None
        self.range_low: float | None = None
        self.traded_today: bool = False

    def on_candle(self, candle: Candle, portfolio: PortfolioState) -> list[OrderIntent]:
        c_date = candle.timestamp.date()
        c_time = candle.timestamp.time()
        orders: list[OrderIntent] = []

        # Reset daily state on new trading day
        if self.current_date != c_date:
            self.current_date = c_date
            self.range_high = None
            self.range_low = None
            self.traded_today = False

        pos = portfolio.positions.get(candle.instrument_key)

        # 1. Square-off at end of day
        if c_time >= INTRADAY_CUTOFF:
            if pos and pos.is_open:
                exit_side = OrderSide.SELL if pos.is_long else OrderSide.BUY
                orders.append(
                    OrderIntent(
                        timestamp=candle.timestamp,
                        instrument_key=candle.instrument_key,
                        trading_symbol=pos.trading_symbol,
                        side=exit_side,
                        quantity=abs(pos.quantity),
                        order_type=OrderType.MARKET,
                        tag="EOD_SQUAREOFF",
                    )
                )
            return orders

        # 2. Build opening range
        if c_time < OPENING_RANGE_END:
            if self.range_high is None or candle.high > self.range_high:
                self.range_high = candle.high
            if self.range_low is None or candle.low < self.range_low:
                self.range_low = candle.low
            return orders

        # 3. Check for breakout after range establishment (1 trade per day)
        if (
            not self.traded_today
            and (not pos or not pos.is_open)
            and self.range_high
            and self.range_low
        ):
            # Bullish Breakout above range high
            if candle.close > self.range_high:
                sl = candle.close * (1.0 - (self.stop_loss_pct / 100.0))
                tp = candle.close * (1.0 + (self.target_pct / 100.0))
                orders.append(
                    OrderIntent(
                        timestamp=candle.timestamp,
                        instrument_key=candle.instrument_key,
                        trading_symbol=candle.instrument_key,
                        side=OrderSide.BUY,
                        quantity=self.lot_size,
                        order_type=OrderType.MARKET,
                        stop_loss_price=round(sl, 2),
                        target_price=round(tp, 2),
                        tag="ORB_LONG_BREAKOUT",
                    )
                )
                self.traded_today = True

        return orders
