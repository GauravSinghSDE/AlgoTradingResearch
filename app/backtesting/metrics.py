"""
Performance Metrics Calculation Engine.
Calculates CAGR, Win Rate, Profit Factor, Max Drawdown, and Cost Impact with edge-case safety.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from app.domain.trades import TradeRecord


class PerformanceMetrics(BaseModel):
    """Structured performance metrics output for a backtest or paper run."""

    initial_capital: float
    final_equity: float
    net_pnl: float
    gross_pnl: float
    total_costs: float
    costs_as_pct_of_gross_profit: float
    absolute_return_pct: float
    max_drawdown_amount: float
    max_drawdown_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: float
    average_trade_pnl: float
    average_win: float
    average_loss: float
    win_loss_ratio: float
    profit_factor: float
    largest_winning_trade: float
    largest_losing_trade: float
    average_trade_duration: str
    monthly_returns: dict[str, float] = Field(default_factory=dict)


def calculate_metrics(
    initial_capital: float,
    equity_curve: list[dict[str, Any]],
    closed_trades: list[TradeRecord],
) -> PerformanceMetrics:
    """Calculates all key trading metrics deterministically."""
    final_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital
    net_pnl = final_equity - initial_capital
    total_costs = sum(t.total_costs for t in closed_trades)
    gross_pnl = sum(t.gross_pnl for t in closed_trades)

    gross_profit = sum(t.gross_pnl for t in closed_trades if t.gross_pnl > 0)
    costs_pct_gross = (total_costs / gross_profit * 100.0) if gross_profit > 0 else 0.0

    abs_return_pct = (net_pnl / initial_capital) * 100.0 if initial_capital > 0 else 0.0

    # Max Drawdown calculation from equity series
    equities = [pt["equity"] for pt in equity_curve] if equity_curve else [initial_capital]
    peak = equities[0]
    max_dd_amount = 0.0
    max_dd_pct = 0.0

    for eq in equities:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = (dd / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd_amount:
            max_dd_amount = dd
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct

    # Trade statistics
    total_trades = len(closed_trades)
    wins = [t for t in closed_trades if t.net_pnl > 0]
    losses = [t for t in closed_trades if t.net_pnl < 0]
    breakevens = [t for t in closed_trades if t.net_pnl == 0]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100.0) if total_trades > 0 else 0.0

    avg_win = float(np.mean([t.net_pnl for t in wins])) if wins else 0.0
    avg_loss = float(np.mean([abs(t.net_pnl) for t in losses])) if losses else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else (avg_win if avg_win > 0 else 1.0)

    total_gross_wins = sum(t.net_pnl for t in wins)
    total_gross_losses = sum(abs(t.net_pnl) for t in losses)
    profit_factor = (
        (total_gross_wins / total_gross_losses)
        if total_gross_losses > 0
        else (float("inf") if total_gross_wins > 0 else 0.0)
    )

    largest_win = max([t.net_pnl for t in wins], default=0.0)
    largest_loss = min([t.net_pnl for t in losses], default=0.0)
    avg_trade_pnl = net_pnl / total_trades if total_trades > 0 else 0.0

    durations = [t.duration for t in closed_trades]
    avg_duration_td = (
        sum(durations, timedelta()) / total_trades if total_trades > 0 else timedelta()
    )
    avg_duration_str = str(avg_duration_td).split(".")[0]  # strip microseconds

    # Monthly returns table
    monthly: dict[str, float] = {}
    if closed_trades:
        for t in closed_trades:
            month_key = t.exit_timestamp.strftime("%Y-%m")
            monthly[month_key] = monthly.get(month_key, 0.0) + t.net_pnl

    return PerformanceMetrics(
        initial_capital=round(initial_capital, 2),
        final_equity=round(final_equity, 2),
        net_pnl=round(net_pnl, 2),
        gross_pnl=round(gross_pnl, 2),
        total_costs=round(total_costs, 2),
        costs_as_pct_of_gross_profit=round(costs_pct_gross, 2),
        absolute_return_pct=round(abs_return_pct, 2),
        max_drawdown_amount=round(max_dd_amount, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        total_trades=total_trades,
        winning_trades=win_count,
        losing_trades=loss_count,
        breakeven_trades=len(breakevens),
        win_rate_pct=round(win_rate, 2),
        average_trade_pnl=round(avg_trade_pnl, 2),
        average_win=round(avg_win, 2),
        average_loss=round(avg_loss, 2),
        win_loss_ratio=round(win_loss_ratio, 2),
        profit_factor=round(profit_factor, 2) if profit_factor != float("inf") else 999.99,
        largest_winning_trade=round(largest_win, 2),
        largest_losing_trade=round(largest_loss, 2),
        average_trade_duration=avg_duration_str,
        monthly_returns={k: round(v, 2) for k, v in monthly.items()},
    )
