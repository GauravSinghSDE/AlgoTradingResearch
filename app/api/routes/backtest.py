"""
Backtesting execution and reporting API endpoints.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.backtesting.engine import BacktestEngine, BacktestResult
from app.data.storage import MarketDataStore
from app.domain.candles import CandleInterval
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.strategies.base import StrategyConfig
from app.strategies.registry import STRATEGY_REGISTRY, get_strategy_class

router = APIRouter(prefix="/backtest", tags=["Backtesting"])
store = MarketDataStore()


class BacktestRunRequest(BaseModel):
    strategy_name: str = "ma_crossover"
    instrument_key: str
    interval: str = "1minute"
    start_date: str | None = None
    end_date: str | None = None
    initial_capital: float = 25000.0
    slippage_points: float = 0.5
    parameters: dict[str, Any] = Field(default_factory=dict)


@router.get("/strategies")
async def list_strategies() -> list[str]:
    """Returns list of registered strategies."""
    return list(STRATEGY_REGISTRY.keys())


@router.post("/run", response_model=BacktestResult)
async def run_backtest(req: BacktestRunRequest) -> BacktestResult:
    """Executes deterministic backtest on stored historical candles."""
    # 1. Resolve strategy
    try:
        strat_cls = get_strategy_class(req.strategy_name)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    cfg = StrategyConfig(name=req.strategy_name, parameters=req.parameters)
    strategy = strat_cls(config=cfg)

    # 2. Load historical candles
    interval_enum = CandleInterval(req.interval)
    batch = store.load_candles(
        instrument_key=req.instrument_key,
        interval=interval_enum,
        start_date=req.start_date,
        end_date=req.end_date,
    )
    if not batch or batch.count() == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No local candle data found for {req.instrument_key} ({req.interval}). Please download data first.",
        )

    # 3. Instrument metadata representation
    lot_size = int(req.parameters.get("lot_size", 25))
    instrument = BaseInstrument(
        instrument_key=req.instrument_key,
        trading_symbol=req.instrument_key,
        name=req.instrument_key,
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=lot_size,
    )

    # 4. Execute backtest
    engine = BacktestEngine(
        initial_capital=req.initial_capital,
        slippage_points=req.slippage_points,
    )
    result = engine.run(strategy=strategy, candle_batch=batch, instrument=instrument)
    return result
