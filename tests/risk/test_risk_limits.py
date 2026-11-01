"""
Unit tests for the independent Risk Management Engine.
Enforces lot size, daily loss limit, duplicate entry, and risk-per-trade rules.
"""

from __future__ import annotations

from datetime import datetime

from app.domain.candles import IST
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide, Position
from app.risk.limits import RiskManager


def get_mock_instrument(lot_size: int = 25) -> BaseInstrument:
    return BaseInstrument(
        instrument_key="NSE_FO|NIFTY24O3124500CE",
        trading_symbol="NIFTY 24500 CE",
        name="NIFTY",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=lot_size,
    )


def test_lot_size_violation_rejected():
    """Quantity must be an exact multiple of contract lot size."""
    risk = RiskManager()
    portfolio = PortfolioState(starting_capital=25000.0, cash=25000.0, day_start_equity=25000.0)
    inst = get_mock_instrument(lot_size=25)

    # 30 is not a multiple of 25
    order = OrderIntent(
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=30,
    )

    res = risk.validate_order(order, portfolio, inst, current_price=100.0)
    assert res.is_approved is False
    assert res.rule_name == "LOT_SIZE"


def test_daily_loss_circuit_breaker():
    """Trading must halt when daily loss threshold (5%) is reached."""
    risk = RiskManager(max_daily_loss_pct=5.0)
    # Start day with 25000, now cash is 23500 -> 1500 loss = 6% loss
    portfolio = PortfolioState(
        starting_capital=25000.0,
        day_start_equity=25000.0,
        cash=23500.0,
    )
    inst = get_mock_instrument(lot_size=25)

    order = OrderIntent(
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )

    res = risk.validate_order(order, portfolio, inst, current_price=100.0)
    assert res.is_approved is False
    assert res.rule_name == "DAILY_LOSS_LIMIT"


def test_duplicate_entry_rejected():
    """Cannot place a second entry in the same direction on an open position."""
    risk = RiskManager()
    inst = get_mock_instrument(lot_size=25)

    # 20000 cash + 25 * 105 (2625) = 22625 equity
    equity = 22625.0
    portfolio = PortfolioState(
        starting_capital=25000.0,
        day_start_equity=equity,
        cash=20000.0,
        positions={
            inst.instrument_key: Position(
                instrument_key=inst.instrument_key,
                trading_symbol=inst.trading_symbol,
                quantity=25,
                average_entry_price=100.0,
                current_price=105.0,
            )
        },
    )

    order = OrderIntent(
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )

    res = risk.validate_order(order, portfolio, inst, current_price=105.0)
    assert res.is_approved is False
    assert res.rule_name == "DUPLICATE_ENTRY"


def test_insufficient_cash_rejected():
    """Order requiring more cash than available balance must be rejected."""
    risk = RiskManager()
    portfolio = PortfolioState(starting_capital=1000.0, cash=1000.0, day_start_equity=1000.0)
    inst = get_mock_instrument(lot_size=25)

    # 25 units * 100 price = 2500 required, but only 1000 cash
    order = OrderIntent(
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )

    res = risk.validate_order(order, portfolio, inst, current_price=100.0)
    assert res.is_approved is False
    assert res.rule_name == "INSUFFICIENT_CASH"


def test_max_risk_per_trade_rejected():
    """Planned loss at stop loss cannot exceed max_risk_per_trade_pct (2% of 25000 = ₹500)."""
    risk = RiskManager(max_risk_per_trade_pct=2.0)
    portfolio = PortfolioState(starting_capital=25000.0, cash=25000.0, day_start_equity=25000.0)
    inst = get_mock_instrument(lot_size=25)

    # Entry 100, SL 70 -> risk 30 pts * 25 = ₹750 risk > ₹500 allowed
    order = OrderIntent(
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=70.0,
    )

    res = risk.validate_order(order, portfolio, inst, current_price=100.0)
    assert res.is_approved is False
    assert res.rule_name == "MAX_RISK_PER_TRADE"
