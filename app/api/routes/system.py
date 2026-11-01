"""
System status, configuration, and execution mode verification endpoints.
"""

from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/status")
async def system_status() -> dict[str, Any]:
    """Returns platform operational status, version, and execution guardrails."""
    return {
        "status": "online",
        "app_name": "AlgoTradingResearch",
        "environment": settings.ENVIRONMENT,
        "execution_mode": settings.EXECUTION_MODE,
        "python_version": sys.version.split()[0],
        "starting_capital": settings.STARTING_CAPITAL,
        "data_directory": str(settings.DATA_DIR),
        "reports_directory": str(settings.REPORTS_DIR),
        "live_orders_allowed": False,  # Hardcoded invariant
    }
