"""
Deterministic, Event-Driven Backtesting Engine.
Enforces zero look-ahead bias (next-candle execution), conservative intrabar stop/target resolution,
and Indian market transaction costs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.backtesting.costs import TransactionCostCalculator
from app.backtesting.metrics import PerformanceMetrics, calculate_metrics
from app.core.exceptions import LookAheadBiasError
from app.domain.candles import CandleBatch
from app.domain.instruments import BaseInstrument, InstrumentType
from app.domain.portfolio import PortfolioState
from app.domain.trades import (
    OrderIntent,
    OrderSide,
    Position,
    TradeFill,
    TradeRecord,
)
from app.risk.limits import RiskManager


class RejectedOrderLog(BaseModel):
    """Log entry for an order rejected by risk management."""

    timestamp: datetime
    instrument_key: str
    side: OrderSide
    quantity: int
    rule_name: str
    reason: str


class BacktestResult(BaseModel):
    """Complete result of a deterministic backtest run."""

    backtest_id: str = Field(default_factory=lambda: str(uuid4()))
    strategy_name: str
    instrument_key: str
    candle_count: int
    start_time: datetime | None = None
    end_time: datetime | None = None
    metrics: PerformanceMetrics
    equity_curve: list[dict[str, Any]] = Field(default_factory=list)
    closed_trades: list[TradeRecord] = Field(default_factory=list)
    fills: list[TradeFill] = Field(default_factory=list)
    rejected_orders: list[RejectedOrderLog] = Field(default_factory=list)


class BacktestEngine:
    """Deterministic event-driven backtesting execution engine."""

    def __init__(
        self,
        initial_capital: float = 25000.0,
        cost_calculator: TransactionCostCalculator | None = None,
        risk_manager: RiskManager | None = None,
        slippage_points: float = 0.5,
    ):
        self.initial_capital = initial_capital
        self.costs = cost_calculator or TransactionCostCalculator(
            default_slippage_points=slippage_points
        )
        self.risk = risk_manager or RiskManager()
        self.slippage_points = slippage_points

    def run(
        self,
        strategy: Any,
        candle_batch: CandleBatch,
        instrument: BaseInstrument,
    ) -> BacktestResult:
        """Executes full backtest over candle batch with next-candle order execution."""
        candles = candle_batch.candles
        if not candles:
            raise ValueError(f"No candles provided for backtest on {instrument.instrument_key}")

        # Ensure candles are strictly sorted chronologically
        for i in range(len(candles) - 1):
            if candles[i].timestamp > candles[i + 1].timestamp:
                raise LookAheadBiasError(
                    "Candles provided to BacktestEngine are not in chronological order!"
                )

        portfolio = PortfolioState(
            starting_capital=self.initial_capital,
            cash=self.initial_capital,
            day_start_equity=self.initial_capital,
        )

        equity_curve: list[dict[str, Any]] = []
        pending_orders: list[OrderIntent] = []
        rejected_orders: list[RejectedOrderLog] = []
        active_trade_entries: dict[str, dict[str, Any]] = {}  # key -> {entry_fill, sl, target}

        inst_key = instrument.instrument_key
        inst_type = getattr(instrument, "instrument_type", InstrumentType.FUTURE)

        for candle in candles:
            c_date = candle.timestamp.date()
            portfolio.on_new_day(c_date)

            # -------------------------------------------------------------
            # STEP 1: Intrabar Stop Loss / Target Execution for open positions
            # -------------------------------------------------------------
            pos = portfolio.positions.get(inst_key)
            if pos and pos.is_open and inst_key in active_trade_entries:
                entry_info = active_trade_entries[inst_key]
                sl_price = entry_info.get("stop_loss_price")
                tp_price = entry_info.get("target_price")
                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""

                if pos.is_long:
                    sl_hit = sl_price is not None and candle.low <= sl_price
                    tp_hit = tp_price is not None and candle.high >= tp_price

                    if sl_hit and tp_hit:
                        # Ambiguity resolution: conservative assumption that Stop-Loss was hit first
                        exit_triggered = True
                        exit_price = sl_price - self.slippage_points
                        exit_reason = "STOP_LOSS (AMBIGUOUS_BAR_CONSERVATIVE)"
                    elif sl_hit:
                        exit_triggered = True
                        exit_price = sl_price - self.slippage_points
                        exit_reason = "STOP_LOSS"
                    elif tp_hit:
                        exit_triggered = True
                        exit_price = tp_price - self.slippage_points
                        exit_reason = "TARGET"

                    if exit_triggered:
                        self._close_position(
                            portfolio,
                            instrument,
                            inst_type,
                            pos,
                            candle.timestamp,
                            exit_price,
                            exit_reason,
                            entry_info,
                        )
                        del active_trade_entries[inst_key]

                elif pos.is_short:
                    sl_hit = sl_price is not None and candle.high >= sl_price
                    tp_hit = tp_price is not None and candle.low <= tp_price

                    if sl_hit and tp_hit:
                        exit_triggered = True
                        exit_price = sl_price + self.slippage_points
                        exit_reason = "STOP_LOSS (AMBIGUOUS_BAR_CONSERVATIVE)"
                    elif sl_hit:
                        exit_triggered = True
                        exit_price = sl_price + self.slippage_points
                        exit_reason = "STOP_LOSS"
                    elif tp_hit:
                        exit_triggered = True
                        exit_price = tp_price + self.slippage_points
                        exit_reason = "TARGET"

                    if exit_triggered:
                        self._close_position(
                            portfolio,
                            instrument,
                            inst_type,
                            pos,
                            candle.timestamp,
                            exit_price,
                            exit_reason,
                            entry_info,
                        )
                        del active_trade_entries[inst_key]

            # -------------------------------------------------------------
            # STEP 2: Execute Pending Orders from Previous Candle at OPEN
            # -------------------------------------------------------------
            if pending_orders:
                orders_to_execute = list(pending_orders)
                pending_orders.clear()

                for order in orders_to_execute:
                    # Risk Check
                    risk_res = self.risk.validate_order(
                        intent=order,
                        portfolio=portfolio,
                        instrument=instrument,
                        current_price=candle.open,
                    )
                    if not risk_res.is_approved:
                        rejected_orders.append(
                            RejectedOrderLog(
                                timestamp=candle.timestamp,
                                instrument_key=order.instrument_key,
                                side=order.side,
                                quantity=order.quantity,
                                rule_name=risk_res.rule_name or "RISK",
                                reason=risk_res.rejection_reason or "Risk violation",
                            )
                        )
                        continue

                    # Execute order fill at candle.open with slippage
                    fill_price = (
                        candle.open + self.slippage_points
                        if order.side == OrderSide.BUY
                        else candle.open - self.slippage_points
                    )
                    charges = self.costs.calculate(
                        side=order.side,
                        instrument_type=inst_type,
                        quantity=order.quantity,
                        price=fill_price,
                    )

                    fill = TradeFill(
                        order_id=order.order_id,
                        timestamp=candle.timestamp,
                        instrument_key=order.instrument_key,
                        trading_symbol=order.trading_symbol,
                        side=order.side,
                        quantity=order.quantity,
                        fill_price=fill_price,
                        slippage=charges.slippage,
                        brokerage=charges.brokerage,
                        stt=charges.stt,
                        exchange_charges=charges.exchange_charges,
                        gst=charges.gst,
                        sebi_charges=charges.sebi_charges,
                        stamp_duty=charges.stamp_duty,
                    )
                    portfolio.fills.append(fill)

                    current_pos = portfolio.positions.get(inst_key)
                    if not current_pos or not current_pos.is_open:
                        # New position entry
                        signed_qty = (
                            order.quantity if order.side == OrderSide.BUY else -order.quantity
                        )
                        portfolio.positions[inst_key] = Position(
                            instrument_key=inst_key,
                            trading_symbol=order.trading_symbol,
                            quantity=signed_qty,
                            average_entry_price=fill_price,
                            current_price=fill_price,
                            lot_size=instrument.lot_size,
                        )
                        portfolio.cash -= (fill_price * signed_qty) + charges.total_deduction
                        active_trade_entries[inst_key] = {
                            "fill": fill,
                            "stop_loss_price": order.stop_loss_price,
                            "target_price": order.target_price,
                        }
                    else:
                        # Closing or flipping existing position
                        if (current_pos.is_long and order.side == OrderSide.SELL) or (
                            current_pos.is_short and order.side == OrderSide.BUY
                        ):
                            entry_data = active_trade_entries.get(inst_key, {})
                            self._close_position(
                                portfolio,
                                instrument,
                                inst_type,
                                current_pos,
                                candle.timestamp,
                                fill_price,
                                order.tag or "SIGNAL_EXIT",
                                entry_data,
                            )
                            if inst_key in active_trade_entries:
                                del active_trade_entries[inst_key]

            # -------------------------------------------------------------
            # STEP 3: Mark to Market Portfolio at Candle Close
            # -------------------------------------------------------------
            portfolio.update_prices({inst_key: candle.close})
            equity_curve.append(
                {
                    "timestamp": candle.timestamp.isoformat(),
                    "equity": round(portfolio.equity, 2),
                    "cash": round(portfolio.cash, 2),
                    "drawdown_pct": round(portfolio.current_drawdown_pct, 2),
                }
            )

            # -------------------------------------------------------------
            # STEP 4: Call Strategy on Completed Candle (NO LOOK-AHEAD)
            # -------------------------------------------------------------
            new_orders = strategy.on_candle(candle, portfolio)
            if new_orders:
                pending_orders.extend(new_orders)

        # Final square-off of any remaining open position at backtest conclusion
        final_pos = portfolio.positions.get(inst_key)
        if final_pos and final_pos.is_open:
            last_candle = candles[-1]
            entry_data = active_trade_entries.get(inst_key, {})
            self._close_position(
                portfolio,
                instrument,
                inst_type,
                final_pos,
                last_candle.timestamp,
                last_candle.close,
                "END_OF_BACKTEST_SQUAREOFF",
                entry_data,
            )

        metrics = calculate_metrics(
            initial_capital=self.initial_capital,
            equity_curve=equity_curve,
            closed_trades=portfolio.closed_trades,
        )

        return BacktestResult(
            strategy_name=getattr(strategy, "name", "Strategy"),
            instrument_key=inst_key,
            candle_count=len(candles),
            start_time=candles[0].timestamp if candles else None,
            end_time=candles[-1].timestamp if candles else None,
            metrics=metrics,
            equity_curve=equity_curve,
            closed_trades=portfolio.closed_trades,
            fills=portfolio.fills,
            rejected_orders=rejected_orders,
        )

    def _close_position(
        self,
        portfolio: PortfolioState,
        instrument: BaseInstrument,
        inst_type: InstrumentType,
        pos: Position,
        timestamp: datetime,
        exit_price: float,
        exit_reason: str,
        entry_info: dict[str, Any],
    ) -> None:
        """Closes an open position, records TradeRecord, and updates cash/equity."""
        exit_side = OrderSide.SELL if pos.is_long else OrderSide.BUY
        qty = abs(pos.quantity)

        exit_charges = self.costs.calculate(
            side=exit_side,
            instrument_type=inst_type,
            quantity=qty,
            price=exit_price,
        )

        entry_fill: TradeFill | None = entry_info.get("fill")
        entry_charges = entry_fill.total_charges if entry_fill else 0.0
        entry_ts = entry_fill.timestamp if entry_fill else timestamp
        entry_price = pos.average_entry_price

        if pos.is_long:
            gross_pnl = (exit_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - exit_price) * qty

        total_costs = entry_charges + exit_charges.total_deduction
        net_pnl = gross_pnl - total_costs
        cost_basis = entry_price * qty
        ret_pct = (net_pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0

        trade_record = TradeRecord(
            instrument_key=pos.instrument_key,
            trading_symbol=pos.trading_symbol,
            side=OrderSide.BUY if pos.is_long else OrderSide.SELL,
            quantity=qty,
            entry_timestamp=entry_ts,
            entry_price=entry_price,
            exit_timestamp=timestamp,
            exit_price=exit_price,
            gross_pnl=round(gross_pnl, 2),
            net_pnl=round(net_pnl, 2),
            total_costs=round(total_costs, 2),
            return_pct=round(ret_pct, 2),
            duration=timestamp - entry_ts,
            exit_reason=exit_reason,
        )
        portfolio.closed_trades.append(trade_record)

        # Update cash: credit back cost basis + gross PnL - exit charges
        portfolio.cash += (pos.quantity * exit_price) - exit_charges.total_deduction
        pos.quantity = 0
        pos.realized_pnl += net_pnl
