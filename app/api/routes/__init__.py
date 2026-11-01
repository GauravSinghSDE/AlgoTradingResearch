"""API routes package."""

from app.api.routes.auth import router as auth_router
from app.api.routes.backtest import router as backtest_router
from app.api.routes.historical import router as historical_router
from app.api.routes.paper import router as paper_router
from app.api.routes.system import router as system_router

__all__ = ["auth_router", "system_router", "historical_router", "backtest_router", "paper_router"]
