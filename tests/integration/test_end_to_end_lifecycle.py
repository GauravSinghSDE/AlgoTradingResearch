"""
Comprehensive End-to-End Validation of Trading System Lifecycle.
Tests all 10 lifecycle stages plus negative live-order submission safety invariants:
1. Market data produces a strategy signal
2. Risk manager accepts or rejects the signal
3. Order intent is persisted
4. Mock broker accepts or rejects the order
5. Partial fills and complete fills update simulated position correctly (weighted average entry price)
6. Stop-loss and exit conditions are handled correctly
7. Broker positions and local positions are reconciled
8. Application restarts recover safely
9. Duplicate submissions are prevented when order outcome is uncertain
10. Emergency halt blocks new orders and handles positions per policy (HOLD and SQUARE_OFF)
11. Negative tests: live order submission is strictly impossible across config, API, and broker.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.brokers.mock import MockBroker
from app.core.config import Settings
from app.core.exceptions import LiveTradingDisabledError
from app.data.calendar import IST
from app.domain.candles import Candle, CandleInterval
from app.domain.instruments import (
    Exchange,
    InstrumentType,
    OptionContract,
    Segment,
)
from app.domain.trades import (
    OrderIntent,
    OrderSide,
    OrderStatus,
    TradeFill,
)
from app.paper_trading.engine import PaperTradingEngine
from app.risk.limits import RiskManager
from app.strategies.base import StrategyConfig
from app.strategies.examples.ma_crossover import MovingAverageCrossoverStrategy


@pytest.fixture
def sample_option_instrument() -> OptionContract:
    return OptionContract(
        instrument_key="NSE_FO|NIFTY24O3124500CE",
        trading_symbol="NIFTY 24500 CE",
        name="NIFTY",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
        expiry=datetime(2024, 10, 31).date(),
        underlying_key="NSE_INDEX|Nifty 50",
        underlying_symbol="NIFTY",
        instrument_type=InstrumentType.CALL_OPTION,
        strike_price=24500.0,
    )


# -----------------------------------------------------------------------------
# Stage 1: Market data produces a strategy signal
# -----------------------------------------------------------------------------
def test_stage_1_market_data_produces_strategy_signal(sample_option_instrument):
    from app.domain.portfolio import PortfolioState

    config = StrategyConfig(
        strategy_name="ma_crossover",
        parameters={
            "fast_period": 2,
            "slow_period": 4,
            "lot_size": 25,
            "stop_loss_points": 10.0,
            "target_points": 25.0,
        },
    )
    strategy = MovingAverageCrossoverStrategy(config)
    portfolio = PortfolioState(starting_capital=25000.0, cash=25000.0, day_start_equity=25000.0)

    # Deterministic sequence producing a bearish baseline followed by bullish crossover
    prices = [100.0, 100.0, 100.0, 95.0, 110.0]
    base_time = datetime(2024, 10, 24, 9, 30, tzinfo=IST)
    signals = []

    for i, p in enumerate(prices):
        candle = Candle(
            timestamp=base_time + timedelta(minutes=i),
            open=p - 1.0,
            high=p + 2.0,
            low=p - 2.0,
            close=p,
            volume=5000,
            open_interest=200000,
            interval=CandleInterval.MINUTE_1,
            instrument_key=sample_option_instrument.instrument_key,
        )
        intents = strategy.on_candle(candle, portfolio)
        signals.extend(intents)

    assert len(signals) >= 1
    sig = signals[0]
    assert sig.side == OrderSide.BUY
    assert sig.quantity == 25
    assert sig.instrument_key == "NSE_FO|NIFTY24O3124500CE"
    assert sig.stop_loss_price is not None
    assert sig.target_price is not None


# -----------------------------------------------------------------------------
# Stage 2: Risk manager accepts or rejects the signal
# -----------------------------------------------------------------------------
def test_stage_2_risk_manager_acceptance_and_rejection(sample_option_instrument):
    risk = RiskManager(max_risk_per_trade_pct=2.0)  # Max loss ₹500 on ₹25,000 capital
    from app.domain.portfolio import PortfolioState

    portfolio = PortfolioState(starting_capital=25000.0, cash=25000.0, day_start_equity=25000.0)

    # Valid Signal: 25 units @ 100 with 10 pt SL (Risk = 25 * 10 = ₹250 <= ₹500 limit)
    valid_intent = OrderIntent(
        order_id="VALID-1",
        timestamp=datetime.now(tz=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=90.0,
        target_price=125.0,
    )
    res_valid = risk.validate_order(
        valid_intent, portfolio, sample_option_instrument, current_price=100.0
    )
    assert res_valid.is_approved is True

    # Rejection Case A: Excessive Risk per Trade (SL at 60 -> Risk = 25 * 40 = ₹1,000 > ₹500 max limit)
    high_risk_intent = OrderIntent(
        order_id="HIGH-RISK",
        timestamp=datetime.now(tz=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=60.0,
        target_price=150.0,
    )
    res_rejected = risk.validate_order(
        high_risk_intent, portfolio, sample_option_instrument, current_price=100.0
    )
    assert res_rejected.is_approved is False
    assert res_rejected.rule_name == "MAX_RISK_PER_TRADE"

    # Rejection Case B: Insufficient Cash (Quantity 300 units @ 100 = ₹30,000 > ₹25,000 cash)
    oversized_intent = OrderIntent(
        order_id="OVERSIZED",
        timestamp=datetime.now(tz=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=300,
        stop_loss_price=95.0,
    )
    res_cash_rejected = risk.validate_order(
        oversized_intent, portfolio, sample_option_instrument, current_price=100.0
    )
    assert res_cash_rejected.is_approved is False
    assert res_cash_rejected.rule_name == "INSUFFICIENT_CASH"


# -----------------------------------------------------------------------------
# Stage 3: Order intent is persisted
# -----------------------------------------------------------------------------
def test_stage_3_order_intent_persisted(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)

    intent = OrderIntent(
        order_id="INTENT-001",
        timestamp=datetime(2024, 10, 24, 9, 35, tzinfo=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=90.0,
        target_price=125.0,
        tag="ORB_BREAKOUT",
    )
    engine.persist_order_intent(intent)

    assert "INTENT-001" in engine.order_intents
    assert engine.order_intents["INTENT-001"]["tag"] == "ORB_BREAKOUT"
    assert state_file.exists()


# -----------------------------------------------------------------------------
# Stage 4: Mock broker accepts or rejects the order
# -----------------------------------------------------------------------------
def test_stage_4_mock_broker_accept_and_reject(sample_option_instrument):
    broker = MockBroker(initial_cash=25000.0)

    intent = OrderIntent(
        order_id="ORD-MOCK-1",
        timestamp=datetime.now(tz=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )

    # Broker Acceptance
    ack_accept = broker.submit_order(intent, sample_option_instrument, current_price=100.0)
    assert ack_accept["status"] == OrderStatus.FILLED
    assert len(ack_accept["fills"]) == 1

    # Broker RMS Rejection
    reject_intent = OrderIntent(
        order_id="ORD-MOCK-2",
        timestamp=datetime.now(tz=IST),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )
    ack_reject = broker.submit_order(
        reject_intent,
        sample_option_instrument,
        current_price=100.0,
        behavior="REJECT",
        custom_rejection_reason="Price outside exchange circuit limits",
    )
    assert ack_reject["status"] == OrderStatus.REJECTED
    assert "outside exchange circuit limits" in ack_reject["reason"]


# -----------------------------------------------------------------------------
# Stage 5: Partial fills and complete fills update simulated position correctly
# -----------------------------------------------------------------------------
def test_stage_5_partial_fills_and_weighted_average_entry(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file, slippage_points=0.0)

    # Order for 50 units (2 lots)
    # Fill 1: 25 units @ Rs. 120.0
    fill1 = TradeFill(
        order_id="ORD-SPLIT",
        timestamp=datetime(2024, 10, 24, 9, 35),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        fill_price=120.0,
        brokerage=20.0,
        gst=3.6,
    )
    res1 = engine.apply_fill(fill1, lot_size=25)
    assert res1["status"] == "POSITION_OPENED"
    assert res1["current_quantity"] == 25
    assert res1["average_entry_price"] == 120.0

    # Fill 2: 25 units @ Rs. 124.0 (Accumulation)
    fill2 = TradeFill(
        order_id="ORD-SPLIT",
        timestamp=datetime(2024, 10, 24, 9, 36),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        fill_price=124.0,
        brokerage=20.0,
        gst=3.6,
    )
    res2 = engine.apply_fill(fill2, lot_size=25)
    assert res2["status"] == "POSITION_ACCUMULATED"
    assert res2["current_quantity"] == 50
    # Expected weighted average: (25 * 120 + 25 * 124) / 50 = 122.0
    assert res2["average_entry_price"] == 122.0


# -----------------------------------------------------------------------------
# Stage 6: Stop-loss and exit conditions handled correctly
# -----------------------------------------------------------------------------
def test_stage_6_stop_loss_exit_condition(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file, slippage_points=0.5)

    order = OrderIntent(
        order_id="ORD-SL-TEST",
        timestamp=datetime(2024, 10, 24, 9, 30),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=90.0,
        target_price=130.0,
    )
    engine.process_order(order, sample_option_instrument, current_price=100.0)

    pos = engine.portfolio.positions[sample_option_instrument.instrument_key]
    assert pos.quantity == 25

    # Price stays safe at 95.0 -> No exit
    no_exit = engine.check_exit_conditions(
        sample_option_instrument.instrument_key, current_price=95.0, timestamp=datetime(2024, 10, 24, 9, 35)
    )
    assert no_exit is None
    assert pos.is_open is True

    # Price drops to 89.0 (below SL of 90.0) -> Triggers STOP_LOSS exit
    exit_trade = engine.check_exit_conditions(
        sample_option_instrument.instrument_key, current_price=89.0, timestamp=datetime(2024, 10, 24, 9, 40)
    )
    assert exit_trade is not None
    assert exit_trade.exit_reason == "STOP_LOSS"
    assert pos.quantity == 0
    assert len(engine.portfolio.closed_trades) == 1
    assert exit_trade.net_pnl < 0  # Loss properly accounted for


# -----------------------------------------------------------------------------
# Stage 7: Broker positions and local positions are reconciled
# -----------------------------------------------------------------------------
def test_stage_7_position_reconciliation(tmp_path: Path, sample_option_instrument):
    broker = MockBroker()
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=tmp_path / "recon_state.json")

    # In-Sync initial state
    res_sync = broker.reconcile_positions(
        {k: v.quantity for k, v in engine.portfolio.positions.items() if v.is_open}
    )
    assert res_sync["in_sync"] is True
    assert len(res_sync["discrepancies"]) == 0

    # Discrepancy: Broker executed an orphan fill (+25 units) not recorded locally
    broker.positions[sample_option_instrument.instrument_key] = 25
    res_discrepancy = broker.reconcile_positions(
        {k: v.quantity for k, v in engine.portfolio.positions.items() if v.is_open}
    )
    assert res_discrepancy["in_sync"] is False
    assert len(res_discrepancy["discrepancies"]) == 1
    disc = res_discrepancy["discrepancies"][0]
    assert disc["broker_quantity"] == 25
    assert disc["local_quantity"] == 0
    assert disc["type"] == "MISSING_LOCALLY"


# -----------------------------------------------------------------------------
# Stage 8: Application restarts recover safely
# -----------------------------------------------------------------------------
def test_stage_8_crash_recovery_and_restart(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine1 = PaperTradingEngine(initial_capital=25000.0, state_file=state_file, slippage_points=0.5)

    order = OrderIntent(
        order_id="ORD-RESTART-1",
        timestamp=datetime(2024, 10, 24, 9, 30),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        stop_loss_price=90.0,
    )
    engine1.process_order(order, sample_option_instrument, current_price=100.0)
    saved_cash = engine1.portfolio.cash
    saved_qty = engine1.portfolio.positions[sample_option_instrument.instrument_key].quantity
    saved_avg_price = engine1.portfolio.positions[sample_option_instrument.instrument_key].average_entry_price

    # Simulate process crash / complete restart
    del engine1

    engine2 = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)
    assert engine2.portfolio.cash == saved_cash
    assert engine2.portfolio.positions[sample_option_instrument.instrument_key].quantity == saved_qty
    assert engine2.portfolio.positions[sample_option_instrument.instrument_key].average_entry_price == saved_avg_price
    assert "ORD-RESTART-1" in engine2.processed_order_ids
    assert "ORD-RESTART-1" in engine2.order_intents


# -----------------------------------------------------------------------------
# Stage 9: Duplicate submissions prevented when order outcome is uncertain
# -----------------------------------------------------------------------------
def test_stage_9_duplicate_prevention_on_uncertain_timeout(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)
    broker = MockBroker()

    order = OrderIntent(
        order_id="ORD-IDEMPOTENT-777",
        timestamp=datetime.now(),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )

    # 1. First attempt: Broker gateway timeout occurs
    with pytest.raises(TimeoutError):
        broker.submit_order(order, sample_option_instrument, current_price=100.0, behavior="TIMEOUT")

    # 2. Engine registers order intent
    engine.process_order(order, sample_option_instrument, current_price=100.0)

    # 3. Strategy / Client retries the identical order intent
    duplicate_res = engine.process_order(order, sample_option_instrument, current_price=100.0)
    assert duplicate_res["status"] == "REJECTED"
    assert "Duplicate order ID" in duplicate_res["reason"]


# -----------------------------------------------------------------------------
# Stage 10: Emergency halt blocks new orders and handles existing positions
# -----------------------------------------------------------------------------
def test_stage_10_emergency_halt_hold_and_square_off(tmp_path: Path, sample_option_instrument):
    state_file = tmp_path / "paper_state.json"
    engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)

    # Open a position of 25 units
    order = OrderIntent(
        order_id="ORD-HALT-INIT",
        timestamp=datetime.now(),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )
    engine.process_order(order, sample_option_instrument, current_price=100.0)
    assert engine.portfolio.positions[sample_option_instrument.instrument_key].is_open is True

    # Policy A: HOLD
    engine.emergency_halt(policy="HOLD")
    assert engine.kill_switch_active is True
    assert engine.portfolio.positions[sample_option_instrument.instrument_key].is_open is True  # Retained

    # Rejection of new orders during halt
    new_order = OrderIntent(
        order_id="ORD-NEW-BLOCKED",
        timestamp=datetime.now(),
        instrument_key=sample_option_instrument.instrument_key,
        trading_symbol=sample_option_instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
    )
    rejected_res = engine.process_order(new_order, sample_option_instrument, current_price=100.0)
    assert rejected_res["status"] == "REJECTED"
    assert "Kill switch is active" in rejected_res["reason"]

    # Policy B: SQUARE_OFF
    engine.emergency_halt(policy="SQUARE_OFF", square_off_prices={sample_option_instrument.instrument_key: 105.0})
    assert engine.portfolio.positions[sample_option_instrument.instrument_key].quantity == 0
    assert len(engine.portfolio.closed_trades) == 1
    assert engine.portfolio.closed_trades[0].exit_reason == "EMERGENCY_HALT_SQUARE_OFF"


# -----------------------------------------------------------------------------
# Negative Invariant Tests: Live order submission is impossible
# -----------------------------------------------------------------------------
def test_negative_live_order_submission_impossible():
    # 1. MockBroker explicitly raises LiveTradingDisabledError
    broker = MockBroker()
    with pytest.raises(LiveTradingDisabledError):
        broker.place_live_order()

    # 2. Pydantic Settings rejects EXECUTION_MODE='LIVE'
    with pytest.raises(ValidationError):
        Settings(EXECUTION_MODE="LIVE")  # type: ignore

    # 3. Only BACKTEST and PAPER modes allowed
    s_backtest = Settings(EXECUTION_MODE="BACKTEST")
    assert s_backtest.EXECUTION_MODE == "BACKTEST"
    s_paper = Settings(EXECUTION_MODE="PAPER")
    assert s_paper.EXECUTION_MODE == "PAPER"
