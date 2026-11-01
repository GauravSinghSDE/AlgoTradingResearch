"""
Backtesting Engine Tests:
- Zero Look-Ahead Bias Verification
- Intrabar Stop Loss / Target Ambiguity Resolution
- Portfolio Accounting Consistency
- Deterministic Reproducibility
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.backtesting.engine import BacktestEngine
from app.domain.candles import IST, Candle, CandleBatch, CandleInterval
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide
from app.strategies.base import BaseStrategy


class ImmediateSignalStrategy(BaseStrategy):
    """Test strategy that fires a single BUY order on the very first candle."""

    def __init__(self):
        super().__init__()
        self.fired = False

    def on_candle(self, candle: Candle, portfolio: PortfolioState) -> list[OrderIntent]:
        if not self.fired:
            self.fired = True
            return [
                OrderIntent(
                    timestamp=candle.timestamp,
                    instrument_key=candle.instrument_key,
                    trading_symbol=candle.instrument_key,
                    side=OrderSide.BUY,
                    quantity=25,
                    stop_loss_price=90.0,
                    target_price=120.0,
                )
            ]
        return []


def test_zero_look_ahead_bias_next_candle_fill():
    """
    Verification that signals generated on candle T NEVER fill at candle T.
    They must fill at candle T+1's Open!
    """
    t0 = datetime(2024, 10, 31, 9, 15, tzinfo=IST)
    candles = [
        # Candle 0 (09:15): Strategy fires BUY signal here
        Candle(
            timestamp=t0,
            open=100.0,
            high=105.0,
            low=99.0,
            close=102.0,
            volume=1000,
            instrument_key="TEST",
        ),
        # Candle 1 (09:16): Order MUST be executed at this open (103.0) + slippage
        Candle(
            timestamp=t0 + timedelta(minutes=1),
            open=103.0,
            high=106.0,
            low=101.0,
            close=104.0,
            volume=1000,
            instrument_key="TEST",
        ),
        # Candle 2 (09:17)
        Candle(
            timestamp=t0 + timedelta(minutes=2),
            open=104.0,
            high=107.0,
            low=103.0,
            close=105.0,
            volume=1000,
            instrument_key="TEST",
        ),
    ]
    batch = CandleBatch(instrument_key="TEST", interval=CandleInterval.MINUTE_1, candles=candles)
    inst = BaseInstrument(
        instrument_key="TEST",
        trading_symbol="TEST",
        name="TEST",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
    )

    engine = BacktestEngine(initial_capital=25000.0, slippage_points=0.5)
    result = engine.run(ImmediateSignalStrategy(), batch, inst)

    assert len(result.fills) >= 1
    first_fill = result.fills[0]

    # Fill timestamp must match Candle 1 (09:16), NOT Candle 0 (09:15)
    assert first_fill.timestamp == candles[1].timestamp
    # Fill price must be Candle 1's Open (103.0) + slippage (0.5) = 103.5
    assert first_fill.fill_price == 103.5


def test_intrabar_stop_target_ambiguity_conservative():
    """
    When a candle breaches both SL and Target, the conservative assumption
    (Stop-loss hit first) must be applied.
    """
    t0 = datetime(2024, 10, 31, 9, 15, tzinfo=IST)
    candles = [
        # Candle 0: Entry signal
        Candle(
            timestamp=t0,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=100,
            instrument_key="TEST",
        ),
        # Candle 1: Filled at open=100.0, SL=90, TP=120
        Candle(
            timestamp=t0 + timedelta(minutes=1),
            open=100.0,
            high=102.0,
            low=98.0,
            close=101.0,
            volume=100,
            instrument_key="TEST",
        ),
        # Candle 2: Wild bar! Low is 85 (breaches SL 90) AND High is 125 (breaches TP 120)
        Candle(
            timestamp=t0 + timedelta(minutes=2),
            open=101.0,
            high=125.0,
            low=85.0,
            close=110.0,
            volume=100,
            instrument_key="TEST",
        ),
    ]
    batch = CandleBatch(instrument_key="TEST", interval=CandleInterval.MINUTE_1, candles=candles)
    inst = BaseInstrument(
        instrument_key="TEST",
        trading_symbol="TEST",
        name="TEST",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
    )

    engine = BacktestEngine(initial_capital=25000.0, slippage_points=0.0)
    result = engine.run(ImmediateSignalStrategy(), batch, inst)

    # Verify closed trade
    assert len(result.closed_trades) == 1
    trade = result.closed_trades[0]
    # Exit reason must be STOP_LOSS under conservative assumption
    assert "STOP_LOSS" in trade.exit_reason
    assert trade.exit_price == 90.0  # SL price


def test_deterministic_reproducibility():
    """Running backtest twice on the same data and strategy yields identical results."""
    t0 = datetime(2024, 10, 31, 9, 15, tzinfo=IST)
    candles = [
        Candle(
            timestamp=t0 + timedelta(minutes=m),
            open=100.0 + m,
            high=102.0 + m,
            low=99.0 + m,
            close=101.0 + m,
            volume=100,
            instrument_key="TEST",
        )
        for m in range(20)
    ]
    batch = CandleBatch(instrument_key="TEST", interval=CandleInterval.MINUTE_1, candles=candles)
    inst = BaseInstrument(
        instrument_key="TEST",
        trading_symbol="TEST",
        name="TEST",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
    )

    engine1 = BacktestEngine(initial_capital=25000.0)
    res1 = engine1.run(ImmediateSignalStrategy(), batch, inst)

    engine2 = BacktestEngine(initial_capital=25000.0)
    res2 = engine2.run(ImmediateSignalStrategy(), batch, inst)

    assert res1.metrics.net_pnl == res2.metrics.net_pnl
    assert res1.metrics.final_equity == res2.metrics.final_equity
    assert res1.metrics.total_trades == res2.metrics.total_trades
    assert len(res1.closed_trades) == len(res2.closed_trades)
