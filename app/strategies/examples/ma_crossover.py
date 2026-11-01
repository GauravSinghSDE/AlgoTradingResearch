"""
Moving Average Crossover Strategy with Intraday Square-off.
Generates BUY signals when Fast MA crosses above Slow MA, and SELL/EXIT when Fast MA crosses below Slow MA.
"""

from __future__ import annotations

from collections import deque
from datetime import time

from app.domain.candles import Candle
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide, OrderType
from app.strategies.base import BaseStrategy, StrategyConfig

INTRADAY_SQUAREOFF_TIME = time(15, 15)


class MovingAverageCrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover.
    Parameters:
    - fast_period: int (default 9)
    - slow_period: int (default 21)
    - lot_size: int (default 25)
    - stop_loss_points: float (default 30.0)
    - target_points: float (default 60.0)
    - intraday_only: bool (default True)
    """

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(config)
        params = self.config.parameters
        self.fast_period = int(params.get("fast_period", 9))
        self.slow_period = int(params.get("slow_period", 21))
        self.lot_size = int(params.get("lot_size", 25))
        self.stop_loss_points = float(params.get("stop_loss_points", 30.0))
        self.target_points = float(params.get("target_points", 60.0))
        self.intraday_only = bool(params.get("intraday_only", True))

        self.closes = deque(maxlen=self.slow_period + 2)
        self.prev_fast: float | None = None
        self.prev_slow: float | None = None

    def _calculate_sma(self, period: int) -> float | None:
        if len(self.closes) < period:
            return None
        recent = list(self.closes)[-period:]
        return sum(recent) / period

    def on_candle(self, candle: Candle, portfolio: PortfolioState) -> list[OrderIntent]:
        self.closes.append(candle.close)
        orders: list[OrderIntent] = []

        # Check Intraday Square-off
        candle_time = candle.timestamp.time()
        pos = portfolio.positions.get(candle.instrument_key)

        if self.intraday_only and candle_time >= INTRADAY_SQUAREOFF_TIME:
            if pos and pos.is_open:
                # Square off existing position
                exit_side = OrderSide.SELL if pos.is_long else OrderSide.BUY
                orders.append(
                    OrderIntent(
                        timestamp=candle.timestamp,
                        instrument_key=candle.instrument_key,
                        trading_symbol=pos.trading_symbol,
                        side=exit_side,
                        quantity=abs(pos.quantity),
                        order_type=OrderType.MARKET,
                        tag="INTRADAY_SQUAREOFF",
                    )
                )
            return orders

        fast_ma = self._calculate_sma(self.fast_period)
        slow_ma = self._calculate_sma(self.slow_period)

        if fast_ma is None or slow_ma is None:
            return orders

        if self.prev_fast is not None and self.prev_slow is not None:
            # Bullish crossover: Fast crosses above Slow
            if self.prev_fast <= self.prev_slow and fast_ma > slow_ma:
                if not (pos and pos.is_long):
                    # Close short if open
                    if pos and pos.is_short:
                        orders.append(
                            OrderIntent(
                                timestamp=candle.timestamp,
                                instrument_key=candle.instrument_key,
                                trading_symbol=pos.trading_symbol,
                                side=OrderSide.BUY,
                                quantity=abs(pos.quantity),
                                order_type=OrderType.MARKET,
                                tag="EXIT_SHORT_ON_CROSSOVER",
                            )
                        )
                    # Enter long
                    orders.append(
                        OrderIntent(
                            timestamp=candle.timestamp,
                            instrument_key=candle.instrument_key,
                            trading_symbol=candle.instrument_key,
                            side=OrderSide.BUY,
                            quantity=self.lot_size,
                            order_type=OrderType.MARKET,
                            stop_loss_price=candle.close - self.stop_loss_points,
                            target_price=candle.close + self.target_points,
                            tag="ENTRY_LONG_CROSSOVER",
                        )
                    )

            # Bearish crossover: Fast crosses below Slow
            elif self.prev_fast >= self.prev_slow and fast_ma < slow_ma:
                if pos and pos.is_long:
                    # Close long
                    orders.append(
                        OrderIntent(
                            timestamp=candle.timestamp,
                            instrument_key=candle.instrument_key,
                            trading_symbol=pos.trading_symbol,
                            side=OrderSide.SELL,
                            quantity=abs(pos.quantity),
                            order_type=OrderType.MARKET,
                            tag="EXIT_LONG_ON_CROSSOVER",
                        )
                    )

        self.prev_fast = fast_ma
        self.prev_slow = slow_ma
        return orders
