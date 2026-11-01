"""
CLI Backtest Runner.
Executes deterministic backtest on stored Parquet data and prints full metrics and ledger.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from rich.console import Console
from rich.table import Table

from app.backtesting.engine import BacktestEngine
from app.data.storage import MarketDataStore
from app.domain.candles import CandleInterval
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.strategies.base import StrategyConfig
from app.strategies.registry import STRATEGY_REGISTRY, get_strategy_class


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic backtest on historical data")
    parser.add_argument(
        "--strategy", default="ma_crossover", choices=list(STRATEGY_REGISTRY.keys())
    )
    parser.add_argument(
        "--key", "--instrument", dest="key", required=True, help="Instrument key with cached data"
    )
    parser.add_argument(
        "--interval", default="1minute", choices=["1minute", "5minute", "15minute", "day"]
    )
    parser.add_argument("--capital", type=float, default=25000.0, help="Starting capital in INR")
    parser.add_argument("--lot-size", type=int, default=25, help="Lot size (e.g. 25 for NIFTY)")
    parser.add_argument("--slippage", type=float, default=0.5, help="Slippage points")
    parser.add_argument("--stop-loss", type=float, default=15.0, help="Stop loss points")
    parser.add_argument("--target", type=float, default=30.0, help="Target points")

    args = parser.parse_args()
    console = Console()

    console.print(f"[bold cyan]Running Backtest: {args.strategy} on {args.key}[/bold cyan]")
    store = MarketDataStore()
    batch = store.load_candles(args.key, CandleInterval(args.interval))

    if not batch or batch.count() == 0:
        console.print(
            f"[bold red]Error: No cached {args.interval} data found for {args.key}.[/bold red]"
        )
        console.print("Run download_historical_data.py first to cache candles.")
        return 1

    strat_cls = get_strategy_class(args.strategy)
    strat_params = {
        "lot_size": args.lot_size,
        "stop_loss_points": args.stop_loss,
        "target_points": args.target,
    }
    cfg = StrategyConfig(name=args.strategy, parameters=strat_params)
    strategy = strat_cls(config=cfg)

    instrument = BaseInstrument(
        instrument_key=args.key,
        trading_symbol=args.key,
        name=args.key,
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=args.lot_size,
    )

    engine = BacktestEngine(
        initial_capital=args.capital,
        slippage_points=args.slippage,
    )

    result = engine.run(strategy, batch, instrument)
    m = result.metrics

    # Results Table
    table = Table(title=f"Backtest Performance Summary — {args.strategy}")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Initial Capital", f"Rs. {m.initial_capital:,.2f}")
    table.add_row("Final Equity", f"Rs. {m.final_equity:,.2f}")
    table.add_row("Gross P&L", f"Rs. {m.gross_pnl:,.2f}")
    table.add_row("Total Statutory & Brokerage Costs", f"Rs. {m.total_costs:,.2f}")
    table.add_row("Net P&L (After Costs)", f"Rs. {m.net_pnl:,.2f}")
    table.add_row("Absolute Return", f"{m.absolute_return_pct:+.2f}%")
    table.add_row("Max Drawdown", f"Rs. {m.max_drawdown_amount:,.2f} ({m.max_drawdown_pct:.2f}%)")
    table.add_row("Total Trades", str(m.total_trades))
    table.add_row("Win Rate", f"{m.win_rate_pct:.1f}% ({m.winning_trades}W / {m.losing_trades}L)")
    table.add_row("Profit Factor", f"{m.profit_factor:.2f}")
    table.add_row("Average Trade P&L", f"Rs. {m.average_trade_pnl:,.2f}")
    table.add_row("Largest Win", f"Rs. {m.largest_winning_trade:,.2f}")
    table.add_row("Largest Loss", f"Rs. {m.largest_losing_trade:,.2f}")
    table.add_row("Avg Holding Duration", m.average_trade_duration)
    table.add_row("Rejected Orders (Risk Breached)", str(len(result.rejected_orders)))

    console.print(table)

    # Persist to local database
    try:
        import json

        from app.database import BacktestRecord, SyncSessionLocal, TradeRecordModel, init_db

        init_db()
        with SyncSessionLocal() as session:
            record = BacktestRecord(
                id=result.backtest_id,
                strategy_name=args.strategy,
                instrument_key=args.key,
                interval=args.interval,
                start_time=result.start_time,
                end_time=result.end_time,
                initial_capital=m.initial_capital,
                final_equity=m.final_equity,
                net_pnl=m.net_pnl,
                gross_pnl=m.gross_pnl,
                total_costs=m.total_costs,
                max_drawdown_pct=m.max_drawdown_pct,
                win_rate_pct=m.win_rate_pct,
                total_trades=m.total_trades,
                profit_factor=m.profit_factor,
                parameters_json=json.dumps(strat_params),
            )
            session.add(record)
            for t in result.closed_trades:
                trade_row = TradeRecordModel(
                    id=t.trade_id,
                    backtest_id=result.backtest_id,
                    instrument_key=t.instrument_key,
                    trading_symbol=t.trading_symbol,
                    side=t.side.value,
                    quantity=t.quantity,
                    entry_time=t.entry_timestamp,
                    entry_price=t.entry_price,
                    exit_time=t.exit_timestamp,
                    exit_price=t.exit_price,
                    gross_pnl=t.gross_pnl,
                    net_pnl=t.net_pnl,
                    total_costs=t.total_costs,
                    return_pct=t.return_pct,
                    exit_reason=t.exit_reason,
                )
                session.add(trade_row)
            session.commit()
            console.print(f"[bold green]Backtest run safely saved to database (ID: {result.backtest_id})[/bold green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save to database: {e}[/yellow]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
