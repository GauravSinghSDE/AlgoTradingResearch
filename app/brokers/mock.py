"""
Deterministic Mock Broker for End-to-End Trading System Validation.
Simulates realistic broker behaviors: order acceptance, rejection, partial fills,
network timeouts (uncertain outcome), position tracking, and position reconciliation.
Explicitly rejects live order execution to verify negative safety invariants.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.backtesting.costs import TransactionCostCalculator
from app.core.exceptions import LiveTradingDisabledError
from app.domain.instruments import BaseInstrument, InstrumentType
from app.domain.trades import OrderIntent, OrderSide, OrderStatus, TradeFill


class MockBroker:
    """
    In-memory simulated broker for end-to-end testing and integration tests.
    Does NOT require real broker credentials and does NOT connect to external networks.
    """

    def __init__(
        self,
        initial_cash: float = 25000.0,
        cost_calculator: TransactionCostCalculator | None = None,
        default_slippage: float = 0.5,
    ) -> None:
        self.cash: float = initial_cash
        self.initial_cash: float = initial_cash
        self.positions: dict[str, int] = {}  # instrument_key -> signed quantity
        self.orders: dict[str, dict[str, Any]] = {}  # order_id -> details
        self.costs = cost_calculator or TransactionCostCalculator(
            default_slippage_points=default_slippage
        )
        self.default_slippage = default_slippage

    def place_live_order(self, *args: Any, **kwargs: Any) -> None:
        """
        Safety invariant test hook: any attempt to place live orders
        through this broker must raise LiveTradingDisabledError immediately.
        """
        raise LiveTradingDisabledError("Live trading is strictly disabled in this platform version.")

    def get_positions(self) -> dict[str, int]:
        """Returns the broker's current signed positions by instrument key."""
        return dict(self.positions)

    def submit_order(
        self,
        order: OrderIntent,
        instrument: BaseInstrument,
        current_price: float,
        behavior: str = "FILL_ALL",
        custom_rejection_reason: str | None = None,
        partial_split: tuple[int, ...] | None = None,
    ) -> dict[str, Any]:
        """
        Submits an order to the mock broker.

        Parameters
        ----------
        order : OrderIntent
            The order intent to submit.
        instrument : BaseInstrument
            The instrument being traded.
        current_price : float
            Current market price.
        behavior : str
            'FILL_ALL' | 'PARTIAL_FILL' | 'REJECT' | 'TIMEOUT'
        custom_rejection_reason : str, optional
            Rejection explanation when behavior is 'REJECT'.
        partial_split : tuple[int, ...], optional
            Quantities for each partial fill when behavior is 'PARTIAL_FILL'.

        Returns
        -------
        dict[str, Any] containing order status and generated fills.
        """
        order_entry = {
            "order_id": order.order_id,
            "instrument_key": order.instrument_key,
            "side": order.side.value,
            "quantity": order.quantity,
            "submitted_at": datetime.now(),
            "status": OrderStatus.PENDING.value,
            "fills": [],
        }
        self.orders[order.order_id] = order_entry

        if behavior == "TIMEOUT":
            # Simulates network timeout or uncertain gateway response
            order_entry["status"] = "UNCERTAIN_TIMEOUT"
            raise TimeoutError(f"Broker gateway timed out for order {order.order_id}. State uncertain.")

        if behavior == "REJECT":
            reason = custom_rejection_reason or "Broker RMS: Exceeded exchange price collar"
            order_entry["status"] = OrderStatus.REJECTED.value
            order_entry["rejection_reason"] = reason
            return {
                "order_id": order.order_id,
                "status": OrderStatus.REJECTED,
                "reason": reason,
                "fills": [],
            }

        inst_type = getattr(instrument, "instrument_type", InstrumentType.FUTURE)

        if behavior == "PARTIAL_FILL":
            splits = partial_split or (order.quantity // 2, order.quantity - (order.quantity // 2))
            fills: list[TradeFill] = []
            cumulative_qty = 0

            for i, qty in enumerate(splits):
                if qty <= 0:
                    continue
                # Slight price tick variation between partial fills
                tick_price = current_price + (i * 0.25)
                fill_price = (
                    tick_price + self.default_slippage
                    if order.side == OrderSide.BUY
                    else tick_price - self.default_slippage
                )
                charges = self.costs.calculate(
                    side=order.side,
                    instrument_type=inst_type,
                    quantity=qty,
                    price=fill_price,
                )

                fill = TradeFill(
                    fill_id=str(uuid4()),
                    order_id=order.order_id,
                    timestamp=order.timestamp,
                    instrument_key=order.instrument_key,
                    trading_symbol=order.trading_symbol,
                    side=order.side,
                    quantity=qty,
                    fill_price=fill_price,
                    slippage=charges.slippage,
                    brokerage=charges.brokerage,
                    stt=charges.stt,
                    exchange_charges=charges.exchange_charges,
                    gst=charges.gst,
                    sebi_charges=charges.sebi_charges,
                    stamp_duty=charges.stamp_duty,
                )
                fills.append(fill)
                cumulative_qty += qty

                # Update broker internal position
                signed = qty if order.side == OrderSide.BUY else -qty
                self.positions[order.instrument_key] = (
                    self.positions.get(order.instrument_key, 0) + signed
                )

            status = (
                OrderStatus.FILLED if cumulative_qty >= order.quantity else OrderStatus.PARTIALLY_FILLED
            )
            order_entry["status"] = status.value
            order_entry["fills"] = [f.model_dump() for f in fills]

            return {
                "order_id": order.order_id,
                "status": status,
                "fills": fills,
                "filled_quantity": cumulative_qty,
            }

        # Default: FILL_ALL
        fill_price = (
            current_price + self.default_slippage
            if order.side == OrderSide.BUY
            else current_price - self.default_slippage
        )
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

        signed = order.quantity if order.side == OrderSide.BUY else -order.quantity
        self.positions[order.instrument_key] = self.positions.get(order.instrument_key, 0) + signed

        order_entry["status"] = OrderStatus.FILLED.value
        order_entry["fills"] = [fill.model_dump()]

        return {
            "order_id": order.order_id,
            "status": OrderStatus.FILLED,
            "fills": [fill],
            "filled_quantity": order.quantity,
        }

    def reconcile_positions(
        self,
        local_positions: dict[str, int],
    ) -> dict[str, Any]:
        """
        Reconciles mock broker positions against internal local portfolio positions.
        Identifies exact matches, quantity mismatches, and orphan positions.
        """
        broker_keys = set(self.positions.keys())
        local_keys = set(local_positions.keys())
        all_keys = broker_keys.union(local_keys)

        discrepancies: list[dict[str, Any]] = []
        in_sync = True

        for k in all_keys:
            b_qty = self.positions.get(k, 0)
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
