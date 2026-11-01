"""
Abstract Base Strategy Interface.
Defines deterministic event handlers for candle events without look-ahead bias.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.domain.candles import Candle
from app.domain.portfolio import PortfolioState
from app.domain.trades import OrderIntent


class StrategyConfig(BaseModel):
    """Base parameter configuration for strategies."""

    name: str = "BaseStrategy"
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class BaseStrategy(ABC):
    """
    Base class for algorithmic trading strategies.
    Strategies must be strictly event-driven: they receive completed candles one at a time.
    """

    def __init__(self, config: StrategyConfig | None = None):
        self.config = config or StrategyConfig()

    @property
    def name(self) -> str:
        return self.config.name

    @abstractmethod
    def on_candle(self, candle: Candle, portfolio: PortfolioState) -> list[OrderIntent]:
        """
        Invoked deterministically when a new candle closes.
        Must return list of OrderIntent actions (entries/exits).
        Cannot inspect future candles.
        """
        pass

    def on_end_of_day(self, current_date: date, portfolio: PortfolioState) -> list[OrderIntent]:
        """
        Invoked at market close (15:29 IST) for intraday position square-off.
        Default implementation returns empty list (positional).
        """
        return []
