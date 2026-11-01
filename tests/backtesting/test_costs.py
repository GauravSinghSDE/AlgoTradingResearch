"""
Unit tests for Indian transaction cost modeling (Brokerage, STT, GST, Exchange charges, Stamp duty).
"""

from __future__ import annotations

from app.backtesting.costs import TransactionCostCalculator
from app.domain.instruments import InstrumentType
from app.domain.trades import OrderSide


def test_futures_charges_calculation():
    calc = TransactionCostCalculator(brokerage_per_order=20.0, default_slippage_points=0.5)

    # 1 lot NIFTY Future (qty 25) @ 24,000 -> Turnover ₹6,00,000
    buy_charges = calc.calculate(
        side=OrderSide.BUY,
        instrument_type=InstrumentType.FUTURE,
        quantity=25,
        price=24000.0,
    )
    assert buy_charges.turnover == 600000.0
    assert buy_charges.brokerage == 20.0  # capped at ₹20
    assert buy_charges.stt == 0.0  # No STT on BUY for futures
    assert buy_charges.stamp_duty > 0  # Stamp duty on BUY
    assert buy_charges.slippage == 25 * 0.5  # ₹12.50

    sell_charges = calc.calculate(
        side=OrderSide.SELL,
        instrument_type=InstrumentType.FUTURE,
        quantity=25,
        price=24100.0,
    )
    assert sell_charges.stt > 0  # STT is charged on SELL of futures (0.02%)
    assert sell_charges.stamp_duty == 0.0  # No Stamp duty on SELL


def test_options_charges_calculation():
    calc = TransactionCostCalculator(brokerage_per_order=20.0, default_slippage_points=0.5)

    # 1 lot NIFTY Option (qty 25) @ ₹100 -> Turnover ₹2,500
    buy_charges = calc.calculate(
        side=OrderSide.BUY,
        instrument_type=InstrumentType.CALL_OPTION,
        quantity=25,
        price=100.0,
    )
    # Brokerage is min(₹20, 0.05% of 2500 = ₹1.25)
    assert buy_charges.brokerage == 1.25
    assert buy_charges.stt == 0.0

    sell_charges = calc.calculate(
        side=OrderSide.SELL,
        instrument_type=InstrumentType.CALL_OPTION,
        quantity=25,
        price=120.0,
    )
    # STT on sell option premium (0.1% of ₹3000 = ₹3.00)
    assert sell_charges.stt == 3.0
