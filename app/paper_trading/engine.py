"""
Paper Trading Simulation Engine.
Simulates orders using live or streaming market data without real broker order placement.
Provides state persistence and crash recovery across application restarts.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.backtesting.costs import TransactionCostCalculator
from app.core.config import settings
from app.core.logging import logger
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


class PaperTradingEngine:
    """
    Simulated Paper Trading execution engine.
    Persists state to local JSON file to guarantee safe recovery on restart.
    """

    def __init__(
        self,
        initial_capital: float = 25000.0,
        state_file: Path | None = None,
        cost_calculator: TransactionCostCalculator | None = None,
        risk_manager: RiskManager | None = None,
        slippage_points: float = 0.5,
    ):
        self.initial_capital = initial_capital
        self.state_file = state_file or (settings.DATA_DIR / "paper_state.json")
        self.costs = cost_calculator or TransactionCostCalculator(
            default_slippage_points=slippage_points
        )
        self.risk = risk_manager or RiskManager()
        self.slippage_points = slippage_points
        self.kill_switch_active: bool = False
        self.processed_order_ids: set[str] = set()
        self.order_intents: dict[str, dict[str, Any]] = {}
        self.position_exit_rules: dict[str, dict[str, float | None]] = {}

        self.portfolio = PortfolioState(
            starting_capital=initial_capital,
            cash=initial_capital,
            day_start_equity=initial_capital,
        )
        self._load_state()

    def _save_state(self) -> None:
        """Serializes current paper portfolio state to disk."""
        data = {
            "cash": self.portfolio.cash,
            "starting_capital": self.portfolio.starting_capital,
            "high_water_mark": self.portfolio.high_water_mark,
            "day_start_equity": self.portfolio.day_start_equity,
            "kill_switch_active": self.kill_switch_active,
            "processed_order_ids": list(self.processed_order_ids),
            "order_intents": self.order_intents,
            "position_exit_rules": self.position_exit_rules,
            "positions": {
                k: {
                    "instrument_key": v.instrument_key,
                    "trading_symbol": v.trading_symbol,
                    "quantity": v.quantity,
                    "average_entry_price": v.average_entry_price,
                    "current_price": v.current_price,
                    "realized_pnl": v.realized_pnl,
                    "lot_size": v.lot_size,
                }
                for k, v in self.portfolio.positions.items()
            },
            "closed_trades": [
                {
                    "trade_id": t.trade_id,
                    "instrument_key": t.instrument_key,
                    "trading_symbol": t.trading_symbol,
                    "side": t.side.value,
                    "quantity": t.quantity,
                    "entry_timestamp": t.entry_timestamp.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_timestamp": t.exit_timestamp.isoformat(),
                    "exit_price": t.exit_price,
                    "gross_pnl": t.gross_pnl,
                    "net_pnl": t.net_pnl,
                    "total_costs": t.total_costs,
                    "return_pct": t.return_pct,
                    "duration_seconds": t.duration.total_seconds(),
                    "exit_reason": t.exit_reason,
                }
                for t in self.portfolio.closed_trades
            ],
        }
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _load_state(self) -> None:
        """Recovers state from disk on application restart."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)

            self.portfolio.cash = float(data.get("cash", self.initial_capital))
            self.portfolio.starting_capital = float(
                data.get("starting_capital", self.initial_capital)
            )
            self.portfolio.high_water_mark = float(
                data.get("high_water_mark", self.initial_capital)
            )
            self.portfolio.day_start_equity = float(
                data.get("day_start_equity", self.initial_capital)
            )
            self.kill_switch_active = bool(data.get("kill_switch_active", False))
            self.processed_order_ids = set(data.get("processed_order_ids", []))
            self.order_intents = data.get("order_intents", {})
            self.position_exit_rules = data.get("position_exit_rules", {})

            positions_dict = data.get("positions", {})
            for k, v in positions_dict.items():
                self.portfolio.positions[k] = Position(
                    instrument_key=v["instrument_key"],
                    trading_symbol=v["trading_symbol"],
                    quantity=int(v["quantity"]),
                    average_entry_price=float(v["average_entry_price"]),
                    current_price=float(v["current_price"]),
                    realized_pnl=float(v.get("realized_pnl", 0.0)),
                    lot_size=int(v.get("lot_size", 1)),
                )

            logger.info(
                "Recovered paper trading state from %s (cash: Rs. %.2f)",
                self.state_file,
                self.portfolio.cash,
            )
        except Exception as e:
            logger.error(
                "Failed to load paper state from %s: %s. Starting fresh.", self.state_file, e
            )

    def activate_kill_switch(self, reason: str = "User manual trigger") -> None:
        """Manually halts all paper trading activity."""
        self.kill_switch_active = True
        logger.warning("Paper trading KILL SWITCH activated: %s", reason)
        self._save_state()

    def deactivate_kill_switch(self) -> None:
        """Resets kill switch."""
        self.kill_switch_active = False
        logger.info("Paper trading KILL SWITCH deactivated.")
        self._save_state()

    def persist_order_intent(self, order: OrderIntent) -> None:
        """Persists order intent to local memory and disk before transmission."""
        self.order_intents[order.order_id] = {
            "order_id": order.order_id,
            "timestamp": order.timestamp.isoformat(),
            "instrument_key": order.instrument_key,
            "trading_symbol": order.trading_symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "limit_price": order.limit_price,
            "stop_loss_price": order.stop_loss_price,
            "target_price": order.target_price,
            "tag": order.tag,
        }
        self._save_state()

    def apply_fill(
        self,
        fill: TradeFill,
        lot_size: int = 1,
        exit_reason: str = "SIGNAL",
    ) -> dict[str, Any]:
        """
        Applies a partial or complete trade fill to the portfolio.
        Handles weighted-average entry prices on accumulation,
        realized P&L and cash return on reduction/closure.
        """
        self.portfolio.fills.append(fill)
        self.processed_order_ids.add(fill.order_id)

        inst_key = fill.instrument_key
        pos = self.portfolio.positions.get(inst_key)
        charges = fill.total_charges

        if not pos or not pos.is_open:
            # Open new position
            signed_qty = fill.quantity if fill.side == OrderSide.BUY else -fill.quantity
            pos = Position(
                instrument_key=inst_key,
                trading_symbol=fill.trading_symbol,
                quantity=signed_qty,
                average_entry_price=fill.fill_price,
                current_price=fill.fill_price,
                lot_size=lot_size,
            )
            self.portfolio.positions[inst_key] = pos
            self.portfolio.cash -= (fill.fill_price * signed_qty) + charges
            status = "POSITION_OPENED"
            closed_trade = None
        elif (pos.is_long and fill.side == OrderSide.BUY) or (
            pos.is_short and fill.side == OrderSide.SELL
        ):
            # Same direction: Accumulating / Partial Fill of entry
            old_qty = abs(pos.quantity)
            add_qty = fill.quantity
            new_qty = old_qty + add_qty
            weighted_avg = (
                (old_qty * pos.average_entry_price) + (add_qty * fill.fill_price)
            ) / new_qty
            pos.average_entry_price = round(weighted_avg, 4)
            pos.current_price = fill.fill_price
            pos.quantity = new_qty if pos.is_long else -new_qty
            signed_qty = add_qty if pos.is_long else -add_qty
            self.portfolio.cash -= (fill.fill_price * signed_qty) + charges
            status = "POSITION_ACCUMULATED"
            closed_trade = None
        else:
            # Opposite direction: Reducing or closing position
            closed_qty = min(abs(pos.quantity), fill.quantity)
            entry_price = pos.average_entry_price
            gross_pnl = (
                (fill.fill_price - entry_price) * closed_qty
                if pos.is_long
                else (entry_price - fill.fill_price) * closed_qty
            )
            net_pnl = gross_pnl - charges
            pos.realized_pnl += net_pnl
            self.portfolio.cash += (fill.fill_price * closed_qty) - charges

            rem_qty = abs(pos.quantity) - closed_qty
            pos.quantity = rem_qty if pos.is_long else -rem_qty
            pos.current_price = fill.fill_price

            closed_trade = TradeRecord(
                instrument_key=inst_key,
                trading_symbol=pos.trading_symbol,
                side=OrderSide.BUY if pos.is_long else OrderSide.SELL,
                quantity=closed_qty,
                entry_timestamp=fill.timestamp,
                entry_price=entry_price,
                exit_timestamp=fill.timestamp,
                exit_price=fill.fill_price,
                gross_pnl=round(gross_pnl, 2),
                net_pnl=round(net_pnl, 2),
                total_costs=round(charges, 2),
                return_pct=round((net_pnl / (entry_price * closed_qty)) * 100.0, 2),
                duration=fill.timestamp - fill.timestamp,
                exit_reason=exit_reason,
            )
            self.portfolio.closed_trades.append(closed_trade)

            if pos.quantity == 0:
                status = "POSITION_CLOSED"
                self.position_exit_rules.pop(inst_key, None)
            else:
                status = "POSITION_REDUCED"

        self._save_state()
        return {
            "status": status,
            "instrument_key": inst_key,
            "current_quantity": pos.quantity if pos else 0,
            "average_entry_price": pos.average_entry_price if pos else 0.0,
            "cash": self.portfolio.cash,
            "closed_trade": closed_trade.model_dump() if closed_trade else None,
        }

    def check_exit_conditions(
        self,
        instrument_key: str,
        current_price: float,
        timestamp: datetime,
    ) -> TradeRecord | None:
        """
        Evaluates open position against active stop-loss and target price rules.
        If breached, executes simulated exit fill.
        """
        pos = self.portfolio.positions.get(instrument_key)
        if not pos or not pos.is_open:
            return None

        rules = self.position_exit_rules.get(instrument_key, {})
        sl = rules.get("stop_loss")
        tp = rules.get("target")

        exit_reason: str | None = None
        if pos.is_long:
            if sl is not None and current_price <= sl:
                exit_reason = "STOP_LOSS"
            elif tp is not None and current_price >= tp:
                exit_reason = "TARGET"
        elif pos.is_short:
            if sl is not None and current_price >= sl:
                exit_reason = "STOP_LOSS"
            elif tp is not None and current_price <= tp:
                exit_reason = "TARGET"

        if not exit_reason:
            return None

        # Execute exit fill
        exit_side = OrderSide.SELL if pos.is_long else OrderSide.BUY
        fill_price = (
            current_price - self.slippage_points
            if exit_side == OrderSide.SELL
            else current_price + self.slippage_points
        )
        charges = self.costs.calculate(
            side=exit_side,
            instrument_type=InstrumentType.CALL_OPTION,
            quantity=abs(pos.quantity),
            price=fill_price,
        )
        fill = TradeFill(
            fill_id=str(uuid4()),
            order_id=str(uuid4()),
            timestamp=timestamp,
            instrument_key=instrument_key,
            trading_symbol=pos.trading_symbol,
            side=exit_side,
            quantity=abs(pos.quantity),
            fill_price=fill_price,
            slippage=charges.slippage,
            brokerage=charges.brokerage,
            stt=charges.stt,
            exchange_charges=charges.exchange_charges,
            gst=charges.gst,
            sebi_charges=charges.sebi_charges,
            stamp_duty=charges.stamp_duty,
        )
        res = self.apply_fill(fill, lot_size=pos.lot_size, exit_reason=exit_reason)
        return self.portfolio.closed_trades[-1] if res.get("closed_trade") else None

    def emergency_halt(
        self,
        policy: str = "HOLD",
        square_off_prices: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        Emergency halt.
        Blocks new orders and handles existing positions per policy ('HOLD' or 'SQUARE_OFF').
        """
        self.kill_switch_active = True
        logger.critical("EMERGENCY HALT ACTIVATED (Policy: %s)", policy)

        closed_trades: list[TradeRecord] = []
        if policy == "SQUARE_OFF":
            for inst_key, pos in list(self.portfolio.positions.items()):
                if pos.is_open:
                    p = (square_off_prices or {}).get(inst_key, pos.current_price)
                    exit_side = OrderSide.SELL if pos.is_long else OrderSide.BUY
                    fill_price = (
                        p - self.slippage_points
                        if exit_side == OrderSide.SELL
                        else p + self.slippage_points
                    )
                    charges = self.costs.calculate(
                        side=exit_side,
                        instrument_type=InstrumentType.CALL_OPTION,
                        quantity=abs(pos.quantity),
                        price=fill_price,
                    )
                    fill = TradeFill(
                        fill_id=str(uuid4()),
                        order_id=str(uuid4()),
                        timestamp=datetime.now(),
                        instrument_key=inst_key,
                        trading_symbol=pos.trading_symbol,
                        side=exit_side,
                        quantity=abs(pos.quantity),
                        fill_price=fill_price,
                        slippage=charges.slippage,
                        brokerage=charges.brokerage,
                        stt=charges.stt,
                        exchange_charges=charges.exchange_charges,
                        gst=charges.gst,
                        sebi_charges=charges.sebi_charges,
                        stamp_duty=charges.stamp_duty,
                    )
                    self.apply_fill(
                        fill, lot_size=pos.lot_size, exit_reason="EMERGENCY_HALT_SQUARE_OFF"
                    )
                    closed_trades.append(self.portfolio.closed_trades[-1])

        self._save_state()
        return {
            "kill_switch_active": True,
            "policy": policy,
            "open_positions_count": len(
                [p for p in self.portfolio.positions.values() if p.is_open]
            ),
            "closed_trades_count": len(closed_trades),
        }

    def reconcile_positions(
        self,
        broker_positions: dict[str, int],
    ) -> dict[str, Any]:
        """Compares local portfolio positions against broker positions."""
        local_positions = {
            k: v.quantity for k, v in self.portfolio.positions.items() if v.is_open
        }
        broker_keys = set(broker_positions.keys())
        local_keys = set(local_positions.keys())
        all_keys = broker_keys.union(local_keys)

        discrepancies: list[dict[str, Any]] = []
        in_sync = True

        for k in all_keys:
            b_qty = broker_positions.get(k, 0)
            l_qty = local_positions.get(k, 0)
            if b_qty != l_qty:
                in_sync = False
                discrepancies.append({
                    "instrument_key": k,
                    "broker_quantity": b_qty,
                    "local_quantity": l_qty,
                    "difference": b_qty - l_qty,
                    "type": (
                        "MISSING_ON_BROKER"
                        if b_qty == 0
                        else ("MISSING_LOCALLY" if l_qty == 0 else "QUANTITY_MISMATCH")
                    ),
                })

        return {
            "in_sync": in_sync,
            "total_instruments_checked": len(all_keys),
            "discrepancies": discrepancies,
            "timestamp": datetime.now().isoformat(),
        }

    def process_order(
        self,
        order: OrderIntent,
        instrument: BaseInstrument,
        current_price: float,
    ) -> dict[str, Any]:
        """
        Simulates order processing against current price.
        Returns execution status and fill details.
        """
        # Kill switch check
        if self.kill_switch_active:
            return {"status": "REJECTED", "reason": "Kill switch is active"}

        # Duplicate order ID check (survives restarts)
        if order.order_id in self.processed_order_ids:
            return {
                "status": "REJECTED",
                "reason": f"Duplicate order ID {order.order_id} already processed",
            }

        # Risk verification
        risk_res = self.risk.validate_order(
            intent=order,
            portfolio=self.portfolio,
            instrument=instrument,
            current_price=current_price,
        )
        if not risk_res.is_approved:
            return {"status": "REJECTED", "reason": risk_res.rejection_reason}

        # Persist intent
        self.persist_order_intent(order)

        # Store exit rules
        if order.stop_loss_price is not None or order.target_price is not None:
            self.position_exit_rules[order.instrument_key] = {
                "stop_loss": order.stop_loss_price,
                "target": order.target_price,
            }

        # Calculate fill price with slippage
        fill_price = (
            current_price + self.slippage_points
            if order.side == OrderSide.BUY
            else current_price - self.slippage_points
        )

        inst_type = getattr(instrument, "instrument_type", InstrumentType.FUTURE)
        charges = self.costs.calculate(
            side=order.side,
            instrument_type=inst_type,
            quantity=order.quantity,
            price=fill_price,
        )

        fill = TradeFill(
            fill_id=str(uuid4()),
            order_id=order.order_id,
            timestamp=order.timestamp,
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

        res = self.apply_fill(fill, lot_size=instrument.lot_size)
        return {
            "status": "FILLED",
            "fill_price": fill_price,
            "quantity": order.quantity,
            "charges": charges.total_deduction,
            "position_status": res["status"],
        }
