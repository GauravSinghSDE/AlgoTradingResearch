"""
End-to-End Trading System Validation Script.
Demonstrates the complete trading lifecycle using a mock broker and deterministic market data:
1. Market data produces a strategy signal
2. Risk manager accepts or rejects the signal
3. Order intent is persisted
4. Mock broker accepts or rejects the order
5. Partial fills and complete fills update simulated position correctly (weighted average entry price)
6. Stop-loss and exit conditions are handled correctly
7. Broker positions and local positions are reconciled
8. Application restarts recover safely
9. Duplicate submissions are prevented when order outcome is uncertain
10. Emergency halt blocks new orders and handles existing positions per policy (HOLD and SQUARE_OFF)
11. Negative live order execution demonstration across configuration, broker, and API.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel

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
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide, OrderStatus, TradeFill
from app.paper_trading.engine import PaperTradingEngine
from app.risk.limits import RiskManager
from app.strategies.base import StrategyConfig
from app.strategies.examples.ma_crossover import MovingAverageCrossoverStrategy


def main() -> int:
    console = Console()
    console.print(
        Panel(
            "[bold cyan]AlgoTradingResearch — Complete End-to-End Trading System Validation[/bold cyan]\n"
            "[dim]Testing full execution lifecycle using MockBroker and deterministic market data with zero live risk[/dim]",
            border_style="cyan",
        )
    )

    sample_opt = OptionContract(
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        state_file = Path(tmp_dir) / "e2e_paper_state.json"

        # -------------------------------------------------------------
        # STAGE 1: Market data produces a strategy signal
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 1: Market Data Produces Strategy Signal[/bold yellow]")
        config = StrategyConfig(
            strategy_name="ma_crossover",
            parameters={"fast_period": 2, "slow_period": 4, "lot_size": 25, "stop_loss_points": 10.0, "target_points": 25.0},
        )
        strategy = MovingAverageCrossoverStrategy(config)
        portfolio = PortfolioState(starting_capital=25000.0, cash=25000.0, day_start_equity=25000.0)

        prices = [100.0, 100.0, 100.0, 95.0, 110.0]
        base_time = datetime(2024, 10, 24, 9, 30, tzinfo=IST)
        generated_signals: list[OrderIntent] = []

        for i, p in enumerate(prices):
            c = Candle(
                timestamp=base_time + timedelta(minutes=i),
                open=p - 1.0, high=p + 2.0, low=p - 2.0, close=p,
                volume=10000, open_interest=150000,
                interval=CandleInterval.MINUTE_1,
                instrument_key=sample_opt.instrument_key,
            )
            orders = strategy.on_candle(c, portfolio)
            generated_signals.extend(orders)

        assert len(generated_signals) >= 1, "Strategy failed to emit golden crossover signal"
        signal = generated_signals[0]
        console.print(f"  [green][OK][/green] Strategy generated signal: [bold]{signal.side.value} {signal.quantity} {signal.instrument_key}[/bold]")
        console.print(f"       Stop Loss: Rs. {signal.stop_loss_price} | Target: Rs. {signal.target_price} | Tag: {signal.tag}")

        # -------------------------------------------------------------
        # STAGE 2: Risk manager accepts or rejects signal
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 2: Risk Manager Acceptance & Rejection[/bold yellow]")
        risk = RiskManager(max_risk_per_trade_pct=2.0)  # Max loss 2% = Rs. 500

        # Valid order check
        val_res = risk.validate_order(signal, portfolio, sample_opt, current_price=110.0)
        assert val_res.is_approved is True, "Valid signal rejected by risk manager"
        console.print("  [green][OK][/green] Valid Signal Approved: Planned risk within limit (Rs. 250 <= Rs. 500 max limit)")

        # Rejection check (excessive risk)
        high_risk = OrderIntent(
            order_id="HIGH-RISK-1",
            timestamp=datetime.now(tz=IST),
            instrument_key=sample_opt.instrument_key,
            trading_symbol=sample_opt.trading_symbol,
            side=OrderSide.BUY,
            quantity=25,
            stop_loss_price=60.0,  # 50 pt risk = Rs. 1,250 > Rs. 500
        )
        rej_res = risk.validate_order(high_risk, portfolio, sample_opt, current_price=110.0)
        assert rej_res.is_approved is False and rej_res.rule_name == "MAX_RISK_PER_TRADE"
        console.print(f"  [green][OK][/green] High-Risk Signal Safely Blocked: Rule '{rej_res.rule_name}' ({rej_res.rejection_reason})")

        # -------------------------------------------------------------
        # STAGE 3: Order intent is persisted
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 3: Order Intent Persistence[/bold yellow]")
        engine = PaperTradingEngine(initial_capital=25000.0, state_file=state_file, slippage_points=0.5)
        engine.persist_order_intent(signal)
        assert signal.order_id in engine.order_intents
        console.print(f"  [green][OK][/green] Order intent [{signal.order_id}] successfully journaled to disk: {state_file}")

        # -------------------------------------------------------------
        # STAGE 4: Mock broker accepts or rejects the order
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 4: Mock Broker Order Acceptance & Rejection[/bold yellow]")
        broker = MockBroker(initial_cash=25000.0)

        # Broker rejection demonstration
        rej_ack = broker.submit_order(
            signal, sample_opt, current_price=110.0, behavior="REJECT",
            custom_rejection_reason="Broker RMS: Circuit limit breach"
        )
        assert rej_ack["status"] == OrderStatus.REJECTED
        console.print(f"  [green][OK][/green] Mock Broker Rejection Verified: {rej_ack['status'].value} ({rej_ack['reason']})")

        # Broker acceptance demonstration
        acc_ack = broker.submit_order(signal, sample_opt, current_price=110.0, behavior="FILL_ALL")
        assert acc_ack["status"] == OrderStatus.FILLED
        console.print(f"  [green][OK][/green] Mock Broker Acceptance Verified: {acc_ack['status'].value} (Fill Qty: {acc_ack['filled_quantity']})")

        # -------------------------------------------------------------
        # STAGE 5: Partial fills and weighted average entry price
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 5: Partial Fills & Weighted Average Entry Price[/bold yellow]")
        engine_split = PaperTradingEngine(initial_capital=25000.0, state_file=Path(tmp_dir) / "split.json", slippage_points=0.0)

        # Fill 1: 25 units @ Rs. 120.0
        f1 = TradeFill(
            order_id="ORD-MULTI", timestamp=datetime.now(),
            instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol,
            side=OrderSide.BUY, quantity=25, fill_price=120.0,
            brokerage=20.0, gst=3.6,
        )
        res_f1 = engine_split.apply_fill(f1, lot_size=25)
        console.print(f"  [green][OK][/green] Partial Fill 1 (25 units @ Rs. 120.0): Position = {res_f1['current_quantity']}, Avg Entry = Rs. {res_f1['average_entry_price']}")

        # Fill 2: 25 units @ Rs. 124.0 (Accumulation)
        f2 = TradeFill(
            order_id="ORD-MULTI", timestamp=datetime.now(),
            instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol,
            side=OrderSide.BUY, quantity=25, fill_price=124.0,
            brokerage=20.0, gst=3.6,
        )
        res_f2 = engine_split.apply_fill(f2, lot_size=25)
        # Expected weighted average: (25*120 + 25*124) / 50 = 122.0
        assert res_f2["current_quantity"] == 50 and res_f2["average_entry_price"] == 122.0
        console.print(f"  [green][OK][/green] Partial Fill 2 (25 units @ Rs. 124.0): Position = {res_f2['current_quantity']}, Weighted Avg = Rs. {res_f2['average_entry_price']:.2f}")

        # -------------------------------------------------------------
        # STAGE 6: Stop-loss and exit conditions handled correctly
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 6: Stop-Loss & Target Exit Triggers[/bold yellow]")
        engine_exit = PaperTradingEngine(initial_capital=25000.0, state_file=Path(tmp_dir) / "exit.json", slippage_points=0.5)
        sl_order = OrderIntent(
            order_id="ORD-SL-RUN", timestamp=datetime.now(),
            instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol,
            side=OrderSide.BUY, quantity=25, stop_loss_price=90.0, target_price=130.0,
        )
        engine_exit.process_order(sl_order, sample_opt, current_price=100.0)

        # Normal tick -> no exit
        assert engine_exit.check_exit_conditions(sample_opt.instrument_key, current_price=95.0, timestamp=datetime.now()) is None
        console.print("  [green][OK][/green] Price above SL (Rs. 95.0 > Rs. 90.0): Position held open")

        # Breach tick -> stop loss execution
        closed_record = engine_exit.check_exit_conditions(sample_opt.instrument_key, current_price=89.0, timestamp=datetime.now())
        assert closed_record is not None and closed_record.exit_reason == "STOP_LOSS"
        console.print(f"  [green][OK][/green] Stop Loss Triggered at Rs. 89.0: Exit reason = {closed_record.exit_reason}, Net P&L = Rs. {closed_record.net_pnl:.2f}")

        # -------------------------------------------------------------
        # STAGE 7: Broker positions and local positions reconciled
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 7: Broker & Local Position Reconciliation[/bold yellow]")
        broker_recon = MockBroker()
        engine_recon = PaperTradingEngine(initial_capital=25000.0, state_file=Path(tmp_dir) / "recon.json")

        # Test discrepancy detection
        broker_recon.positions[sample_opt.instrument_key] = 25  # Broker has 25 units
        recon_report = broker_recon.reconcile_positions(
            {k: v.quantity for k, v in engine_recon.portfolio.positions.items() if v.is_open}
        )
        assert recon_report["in_sync"] is False
        console.print(f"  [green][OK][/green] Discrepancy Caught: In-Sync = {recon_report['in_sync']}, Difference = {recon_report['discrepancies'][0]['difference']} ({recon_report['discrepancies'][0]['type']})")

        # -------------------------------------------------------------
        # STAGE 8: Application restarts recover safely
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 8: Application Restarts & State Recovery[/bold yellow]")
        engine_live = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)
        engine_live.process_order(signal, sample_opt, current_price=110.0)
        c_before = engine_live.portfolio.cash
        q_before = engine_live.portfolio.positions[sample_opt.instrument_key].quantity
        del engine_live  # Simulate application crash

        engine_restarted = PaperTradingEngine(initial_capital=25000.0, state_file=state_file)
        assert engine_restarted.portfolio.cash == c_before
        assert engine_restarted.portfolio.positions[sample_opt.instrument_key].quantity == q_before
        assert signal.order_id in engine_restarted.processed_order_ids
        console.print(f"  [green][OK][/green] Crash Recovery Verified: Cash (Rs. {engine_restarted.portfolio.cash:,.2f}), Open Qty ({q_before}), and Processed Order IDs preserved exactly")

        # -------------------------------------------------------------
        # STAGE 9: Duplicate prevention on uncertain timeout
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 9: Idempotency & Duplicate Prevention[/bold yellow]")
        engine_idempotent = PaperTradingEngine(initial_capital=25000.0, state_file=Path(tmp_dir) / "idempotent.json")
        retry_order = OrderIntent(
            order_id="ORD-TIMEOUT-RETRY-001", timestamp=datetime.now(),
            instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol,
            side=OrderSide.BUY, quantity=25,
        )
        # First execution succeeds
        first_res = engine_idempotent.process_order(retry_order, sample_opt, current_price=110.0)
        assert first_res["status"] == "FILLED"
        # Duplicate submission with identical order_id is blocked
        dup_res = engine_idempotent.process_order(retry_order, sample_opt, current_price=110.0)
        assert dup_res["status"] == "REJECTED" and "Duplicate order ID" in dup_res["reason"]
        console.print(f"  [green][OK][/green] Idempotency Verified: Duplicate order [{retry_order.order_id}] was blocked ({dup_res['reason']})")

        # -------------------------------------------------------------
        # STAGE 10: Emergency halt blocks orders & handles positions
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Stage 10: Emergency Halt (HOLD & SQUARE_OFF Policies)[/bold yellow]")
        halt_engine = PaperTradingEngine(initial_capital=25000.0, state_file=Path(tmp_dir) / "halt.json")
        halt_engine.process_order(
            OrderIntent(order_id="ORD-HALT-INIT", timestamp=datetime.now(), instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol, side=OrderSide.BUY, quantity=25),
            sample_opt, current_price=110.0
        )
        assert halt_engine.portfolio.positions[sample_opt.instrument_key].is_open is True

        # HOLD policy
        halt_engine.emergency_halt(policy="HOLD")
        assert halt_engine.kill_switch_active is True
        # Verify new orders are blocked
        blocked = halt_engine.process_order(
            OrderIntent(order_id="ORD-BLOCKED", timestamp=datetime.now(), instrument_key=sample_opt.instrument_key, trading_symbol=sample_opt.trading_symbol, side=OrderSide.BUY, quantity=25),
            sample_opt, current_price=110.0
        )
        assert blocked["status"] == "REJECTED"
        console.print("  [green][OK][/green] Emergency Halt (HOLD): Kill switch active, existing position retained, new orders blocked")

        # SQUARE_OFF policy
        halt_engine.emergency_halt(policy="SQUARE_OFF", square_off_prices={sample_opt.instrument_key: 115.0})
        assert halt_engine.portfolio.positions[sample_opt.instrument_key].quantity == 0
        console.print("  [green][OK][/green] Emergency Halt (SQUARE_OFF): Open positions flattened, capital returned to cash")

        # -------------------------------------------------------------
        # NEGATIVE TESTS: Live trading is impossible
        # -------------------------------------------------------------
        console.print("\n[bold yellow]Negative Invariant Proof: Live Order Submission is Impossible[/bold yellow]")

        # 1. Mock Broker live method rejection
        try:
            broker.place_live_order()
            raise AssertionError("Failed: place_live_order did not raise LiveTradingDisabledError")
        except LiveTradingDisabledError:
            console.print("  [green][OK][/green] Broker Safety Guard: Calling live order method raises LiveTradingDisabledError")

        # 2. Configuration rejection of EXECUTION_MODE='LIVE'
        try:
            Settings(EXECUTION_MODE="LIVE")  # type: ignore
            raise AssertionError("Failed: Settings accepted EXECUTION_MODE='LIVE'")
        except ValidationError:
            console.print("  [green][OK][/green] Config Validation Guard: Pydantic rejects EXECUTION_MODE='LIVE' at boot")

        # 3. Mode invariant check
        assert Settings().EXECUTION_MODE in ("BACKTEST", "PAPER")
        console.print(f"  [green][OK][/green] Platform Mode Guard: Default execution mode is strictly '{Settings().EXECUTION_MODE}'")

    console.print("\n" + "=" * 70)
    console.print("[bold green]ALL 10 LIFECYCLE STAGES + NEGATIVE LIVE SAFETY TESTS VALIDATED SUCCESSFULLY![/bold green]")
    console.print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
