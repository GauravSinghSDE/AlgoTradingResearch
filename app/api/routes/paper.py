"""
Paper trading API endpoints for monitoring and simulation control.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.paper_trading.engine import PaperTradingEngine

router = APIRouter(prefix="/paper", tags=["Paper Trading"])
paper_engine = PaperTradingEngine()


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "User manual update"


class PaperOrderRequest(BaseModel):
    instrument_key: str
    side: str
    quantity: int
    current_price: float
    lot_size: int = 25


@router.get("/portfolio")
async def get_paper_portfolio() -> dict[str, Any]:
    """Returns live paper portfolio state, open positions, and kill switch status."""
    p = paper_engine.portfolio
    return {
        "cash": round(p.cash, 2),
        "equity": round(p.equity, 2),
        "unrealized_pnl": round(p.total_unrealized_pnl, 2),
        "realized_pnl": round(p.total_realized_pnl, 2),
        "open_positions_count": p.open_position_count,
        "daily_pnl": round(p.daily_pnl, 2),
        "kill_switch_active": paper_engine.kill_switch_active,
        "positions": [
            {
                "instrument_key": pos.instrument_key,
                "trading_symbol": pos.trading_symbol,
                "quantity": pos.quantity,
                "average_entry_price": pos.average_entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": round(pos.unrealized_pnl, 2),
            }
            for pos in p.positions.values()
            if pos.is_open
        ],
        "closed_trades_count": len(p.closed_trades),
    }


@router.post("/kill-switch")
async def toggle_kill_switch(req: KillSwitchRequest) -> dict[str, Any]:
    """Activates or deactivates paper trading kill switch."""
    if req.active:
        paper_engine.activate_kill_switch(req.reason)
    else:
        paper_engine.deactivate_kill_switch()

    return {
        "kill_switch_active": paper_engine.kill_switch_active,
        "message": f"Kill switch is now {'ACTIVE' if paper_engine.kill_switch_active else 'INACTIVE'}.",
    }
