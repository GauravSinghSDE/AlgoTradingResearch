"""
FastAPI application entry point for AlgoTradingResearch.
Provides RESTful APIs for authentication, historical market data discovery, backtesting, and paper trading.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes.auth import router as auth_router
from app.api.routes.backtest import router as backtest_router
from app.api.routes.historical import router as historical_router
from app.api.routes.paper import router as paper_router
from app.api.routes.system import router as system_router
from app.core.config import settings
from app.core.logging import logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup and shutdown lifecycle management."""
    settings.ensure_directories()
    logger.info(
        "Starting AlgoTradingResearch API (Environment: %s, Execution Mode: %s)",
        settings.ENVIRONMENT,
        settings.EXECUTION_MODE,
    )
    yield
    logger.info("AlgoTradingResearch API shut down cleanly.")


app = FastAPI(
    title="AlgoTradingResearch API",
    description="Algorithmic Trading Research and Backtesting Platform for Indian Financial Markets",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes under /api/v1
app.include_router(system_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(historical_router, prefix="/api/v1")
app.include_router(backtest_router, prefix="/api/v1")
app.include_router(paper_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")
