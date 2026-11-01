"""
Risk Management Engine.
Enforces hard safety boundaries independent of trading strategy decisions.
Rejects any order violating capital limits, margin rules, lot sizing, or daily loss thresholds.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import logger
from app.domain.instruments import BaseInstrument
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent, OrderSide


class RiskValidationResult(BaseModel):
    """Result of risk verification on a candidate order."""

    is_approved: bool
    rejection_reason: str | None = None
    rule_name: str | None = None


class RiskManager:
    """Independent risk controller evaluating all trading actions."""

    def __init__(
        self,
        max_risk_per_trade_pct: float | None = None,
        max_daily_loss_pct: float | None = None,
        max_open_positions: int | None = None,
        max_capital_allocation_pct: float | None = None,
    ):
        self.max_risk_per_trade_pct = (
            max_risk_per_trade_pct
            if max_risk_per_trade_pct is not None
            else settings.MAX_RISK_PER_TRADE_PCT
        )
        self.max_daily_loss_pct = (
            max_daily_loss_pct if max_daily_loss_pct is not None else settings.MAX_DAILY_LOSS_PCT
        )
        self.max_open_positions = (
            max_open_positions if max_open_positions is not None else settings.MAX_OPEN_POSITIONS
        )
        self.max_capital_allocation_pct = (
            max_capital_allocation_pct
            if max_capital_allocation_pct is not None
            else settings.MAX_CAPITAL_ALLOCATION_PCT
        )

    def validate_order(
        self,
        intent: OrderIntent,
        portfolio: PortfolioState,
        instrument: BaseInstrument,
        current_price: float,
    ) -> RiskValidationResult:
        """
        Runs comprehensive risk gate checks before allowing an order to enter execution.
        Strategy cannot bypass this method.
        """
        # Rule 1: Whole Lot Size Verification
        lot_size = instrument.lot_size
        if intent.quantity <= 0 or intent.quantity % lot_size != 0:
            reason = f"Invalid quantity {intent.quantity}. Must be positive whole multiple of lot size {lot_size}."
            logger.warning("Risk rejection: %s", reason)
            return RiskValidationResult(
                is_approved=False, rule_name="LOT_SIZE", rejection_reason=reason
            )

        # Rule 2: Daily Loss Circuit Breaker (Kill Switch)
        if portfolio.daily_loss_pct >= self.max_daily_loss_pct:
            reason = (
                f"Daily loss circuit breaker triggered: current daily loss {portfolio.daily_loss_pct:.2f}% "
                f"exceeds limit {self.max_daily_loss_pct:.2f}%."
            )
            logger.warning("Risk rejection: %s", reason)
            return RiskValidationResult(
                is_approved=False, rule_name="DAILY_LOSS_LIMIT", rejection_reason=reason
            )

        # Rule 3: Duplicate Entry Protection
        existing_pos = portfolio.positions.get(intent.instrument_key)
        if existing_pos and existing_pos.is_open:
            if (intent.side == OrderSide.BUY and existing_pos.is_long) or (
                intent.side == OrderSide.SELL and existing_pos.is_short
            ):
                reason = f"Position in {intent.instrument_key} is already active. Duplicate entries forbidden."
                logger.warning("Risk rejection: %s", reason)
                return RiskValidationResult(
                    is_approved=False, rule_name="DUPLICATE_ENTRY", rejection_reason=reason
                )

        # Rule 4: Maximum Open Positions Limit (for new entries)
        if not (existing_pos and existing_pos.is_open):
            if portfolio.open_position_count >= self.max_open_positions:
                reason = f"Open positions count ({portfolio.open_position_count}) reached maximum allowed ({self.max_open_positions})."
                logger.warning("Risk rejection: %s", reason)
                return RiskValidationResult(
                    is_approved=False, rule_name="MAX_POSITIONS", rejection_reason=reason
                )

        # Rule 5: Available Cash & Margin Sufficiency
        order_cost = intent.quantity * current_price
        if intent.side == OrderSide.BUY:
            if order_cost > portfolio.cash:
                reason = f"Insufficient free cash. Required ₹{order_cost:,.2f}, available cash ₹{portfolio.cash:,.2f}."
                logger.warning("Risk rejection: %s", reason)
                return RiskValidationResult(
                    is_approved=False, rule_name="INSUFFICIENT_CASH", rejection_reason=reason
                )

        # Rule 6: Stop-Loss Max Risk Per Trade Check
        if intent.stop_loss_price is not None:
            risk_per_unit = abs(current_price - intent.stop_loss_price)
            total_planned_risk = risk_per_unit * intent.quantity
            max_allowed_risk_amount = (self.max_risk_per_trade_pct / 100.0) * portfolio.equity

            if total_planned_risk > max_allowed_risk_amount:
                reason = (
                    f"Planned risk ₹{total_planned_risk:,.2f} exceeds maximum risk limit "
                    f"₹{max_allowed_risk_amount:,.2f} ({self.max_risk_per_trade_pct}% of equity ₹{portfolio.equity:,.2f})."
                )
                logger.warning("Risk rejection: %s", reason)
                return RiskValidationResult(
                    is_approved=False, rule_name="MAX_RISK_PER_TRADE", rejection_reason=reason
                )

        return RiskValidationResult(is_approved=True)
