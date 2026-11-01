"""
CLI Paper Trading Engine Runner.
Demonstrates live paper simulation, risk limits enforcement, and state persistence.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console

from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.domain.trades import OrderIntent, OrderSide, OrderType
from app.paper_trading.engine import PaperTradingEngine


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Run simulated paper trading engine")
    parser.add_argument("--strategy", default="ma_crossover", help="Strategy name")
    parser.add_argument(
        "--key", "--instrument", dest="key", default="NSE_FO|NIFTY24O3124500CE", help="Instrument key"
    )
    parser.add_argument("--capital", type=float, default=25000.0, help="Initial capital in INR")
    parser.add_argument("--reset-state", action="store_true", help="Reset persisted paper trading state")
    args = parser.parse_args()

    console = Console()
    console.print("[bold yellow]Starting Paper Trading Session (Simulated Only)...[/bold yellow]")

    state_path = Path("data/paper_state.json")
    if args.reset_state and state_path.exists():
        state_path.unlink()
        console.print("[yellow]Cleared prior paper trading state file.[/yellow]")

    engine = PaperTradingEngine(initial_capital=args.capital)
    portfolio = engine.portfolio

    console.print(f"Current Cash: Rs. {portfolio.cash:,.2f}")
    console.print(f"Total Equity: Rs. {portfolio.equity:,.2f}")
    console.print(f"Kill Switch Active: {engine.kill_switch_active}")

    # Simulated instrument (e.g. NIFTY 24500 CE)
    instrument = BaseInstrument(
        instrument_key=args.key,
        trading_symbol="NIFTY 24500 CE",
        name="NIFTY",
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25,
    )

    # Place a simulated test paper order
    simulated_order = OrderIntent(
        timestamp=datetime.now(),
        instrument_key=instrument.instrument_key,
        trading_symbol=instrument.trading_symbol,
        side=OrderSide.BUY,
        quantity=25,
        order_type=OrderType.MARKET,
        stop_loss_price=90.0,
        target_price=150.0,
        tag="PAPER_TEST_SIGNAL",
    )

    console.print(f"Submitting simulated order: BUY 25 {instrument.trading_symbol} @ Rs. 110.00...")
    res = engine.process_order(simulated_order, instrument, current_price=110.0)

    console.print(f"Paper Order Execution Result: {res}")
    console.print(f"Updated Portfolio Cash: Rs. {engine.portfolio.cash:,.2f}")
    console.print(f"Open Positions: {engine.portfolio.open_position_count}")
    console.print(f"State safely persisted to: {engine.state_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
