"""
Unit tests for Paper Trading Simulation:
- Simulated order execution
- State persistence and crash recovery
- Kill-switch activation
- Duplicate order ID rejection
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.domain.candles import IST
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.domain.trades import OrderIntent, OrderSide
from app.paper_trading.engine import PaperTradingEngine


def test_paper_trading_execution_and_persistence(tmp_path: Path):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file, slippage_points=0.5)

    inst = BaseInstrument(
        instrument_key="NSE_FO|NIFTY_OPT",
        trading_symbol="NIFTY_OPT",
        name="NIFTY",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
    )

    # 1. Place Buy Order
    order1 = OrderIntent(
        order_id="ORD-101",
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )
    res1 = engine.process_order(order1, inst, current_price=100.0)
    assert res1["status"] == "FILLED"
    assert res1["fill_price"] == 100.5  # 100 + 0.5 slippage

    # Check that state file exists
    assert state_file.exists()

    # 2. Test restart / recovery: create new engine instance reading same state_file
    recovered_engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)
    assert recovered_engine.portfolio.open_position_count == 1
    pos = recovered_engine.portfolio.positions[inst.instrument_key]
    assert pos.quantity == 25
    assert pos.average_entry_price == 100.5

    # 3. Duplicate Order ID rejection after restart
    res_dup = recovered_engine.process_order(order1, inst, current_price=100.0)
    assert res_dup["status"] == "REJECTED"
    assert "Duplicate order ID" in res_dup["reason"]

    # 4. Test Kill Switch
    recovered_engine.activate_kill_switch("Manual test")
    order2 = OrderIntent(
        order_id="ORD-102",
        timestamp=datetime.now(tz=IST),
        instrument_key=inst.instrument_key,
        trading_symbol=inst.trading_symbol,
        side=OrderSide.SELL,
        quantity=25,
    )
    res_kill = recovered_engine.process_order(order2, inst, current_price=110.0)
    assert res_kill["status"] == "REJECTED"
    assert "Kill switch is active" in res_kill["reason"]
