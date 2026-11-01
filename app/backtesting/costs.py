"""
Indian Markets Transaction Cost & Statutory Taxes Engine.
Models Upstox discount brokerage, STT/CTT, Exchange charges, GST, SEBI fees, and Stamp duty.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.domain.instruments import InstrumentType
from app.domain.trades import OrderSide


class TradeCharges(BaseModel):
    """Itemized breakdown of transaction charges for an executed order."""

    turnover: float
    brokerage: float
    stt: float
    exchange_charges: float
    gst: float
    sebi_charges: float
    stamp_duty: float
    slippage: float = 0.0

    @property
    def total_statutory_charges(self) -> float:
        return self.stt + self.exchange_charges + self.gst + self.sebi_charges + self.stamp_duty

    @property
    def total_deduction(self) -> float:
        """Total cost deducted from account equity."""
        return self.brokerage + self.total_statutory_charges + self.slippage


class TransactionCostCalculator:
    """
    Computes precise transaction costs for Indian Equity and Derivative markets.
    Rates reflect official NSE and SEBI schedules (with revised STT rates).
    """

    def __init__(
        self,
        brokerage_per_order: float = 20.0,
        brokerage_pct_cap: float = 0.05,
        default_slippage_points: float = 0.5,
    ):
        self.brokerage_per_order = brokerage_per_order
        self.brokerage_pct_cap = brokerage_pct_cap
        self.default_slippage_points = default_slippage_points

    def calculate(
        self,
        side: OrderSide,
        instrument_type: InstrumentType,
        quantity: int,
        price: float,
        slippage_points: float | None = None,
    ) -> TradeCharges:
        """Calculates itemized charges for an execution fill."""
        turnover = quantity * price
        slippage_pts = (
            slippage_points if slippage_points is not None else self.default_slippage_points
        )
        slippage_cost = quantity * slippage_pts

        # 1. Brokerage: ₹20 flat or 0.05% whichever is lower
        pct_brokerage = (self.brokerage_pct_cap / 100.0) * turnover
        brokerage = min(self.brokerage_per_order, pct_brokerage)

        # 2. STT / CTT
        stt = 0.0
        if side == OrderSide.SELL:
            if instrument_type == InstrumentType.FUTURE:
                # 0.02% on sell turnover for futures
                stt = round(turnover * 0.0002, 2)
            elif instrument_type in (InstrumentType.CALL_OPTION, InstrumentType.PUT_OPTION):
                # 0.1% on sell option premium turnover
                stt = round(turnover * 0.001, 2)
            elif instrument_type == InstrumentType.EQUITY:
                # 0.1% on equity delivery / 0.025% intraday
                stt = round(turnover * 0.00025, 2)

        # 3. Exchange Turnover Charges
        if instrument_type == InstrumentType.FUTURE:
            exchange_charges = round(turnover * 0.000019, 2)  # 0.0019%
        elif instrument_type in (InstrumentType.CALL_OPTION, InstrumentType.PUT_OPTION):
            exchange_charges = round(turnover * 0.0005, 2)  # 0.05% on premium
        else:
            exchange_charges = round(turnover * 0.0000325, 2)  # 0.00325%

        # 4. SEBI Turnover Charges: ₹10 per crore (0.0001%)
        sebi_charges = round(turnover * 0.000001, 2)

        # 5. GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
        gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)

        # 6. Stamp Duty (Levied on BUY side only)
        stamp_duty = 0.0
        if side == OrderSide.BUY:
            if instrument_type == InstrumentType.FUTURE:
                stamp_duty = round(turnover * 0.00002, 2)  # 0.002%
            elif instrument_type in (InstrumentType.CALL_OPTION, InstrumentType.PUT_OPTION):
                stamp_duty = round(turnover * 0.00003, 2)  # 0.003%
            else:
                stamp_duty = round(turnover * 0.00003, 2)

        return TradeCharges(
            turnover=turnover,
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            gst=gst,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            slippage=slippage_cost,
        )
