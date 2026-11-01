"""Strategy Registry mapping names to strategy classes."""

from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.strategies.examples.intraday_momentum import OpeningRangeBreakoutStrategy
from app.strategies.examples.ma_crossover import MovingAverageCrossoverStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "ma_crossover": MovingAverageCrossoverStrategy,
    "opening_range_breakout": OpeningRangeBreakoutStrategy,
}


def get_strategy_class(name: str) -> type[BaseStrategy]:
    """Resolves strategy class by registered name."""
    if name not in STRATEGY_REGISTRY:
        available = ", ".join(STRATEGY_REGISTRY.keys())
        raise KeyError(f"Strategy '{name}' not found. Available strategies: {available}")
    return STRATEGY_REGISTRY[name]
