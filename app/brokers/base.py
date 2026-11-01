"""
Abstract base class defining broker client interface.
Enforces read-only operations for data retrieval and explicitly forbids live order placement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.domain.candles import CandleBatch, CandleInterval
from app.domain.instruments import FutureContract, OptionContract


class BaseBrokerClient(ABC):
    """Abstract interface for broker data providers."""

    @abstractmethod
    def get_auth_url(self, state: str | None = None) -> str:
        """Returns browser URL for OAuth login."""
        pass

    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchanges single-use authorization code for access token."""
        pass

    @abstractmethod
    async def validate_session(self) -> dict[str, Any]:
        """Validates current token with a read-only profile request."""
        pass

    @abstractmethod
    async def get_expiries(self, underlying_key: str) -> list[str]:
        """Fetches available expired dates (up to 6 months historical) for underlying."""
        pass

    @abstractmethod
    async def get_expired_future_contracts(
        self, underlying_key: str, expiry_date: str
    ) -> list[FutureContract]:
        """Fetches expired future contracts for an expiry date."""
        pass

    @abstractmethod
    async def get_expired_option_contracts(
        self, underlying_key: str, expiry_date: str
    ) -> list[OptionContract]:
        """Fetches expired option contracts for an expiry date."""
        pass

    @abstractmethod
    async def get_expired_candles(
        self,
        expired_instrument_key: str,
        interval: CandleInterval,
        to_date: str,
        from_date: str,
    ) -> CandleBatch:
        """Fetches historical candles for an expired contract."""
        pass

    @abstractmethod
    async def get_historical_candles(
        self,
        instrument_key: str,
        interval: CandleInterval,
        to_date: str,
        from_date: str,
    ) -> CandleBatch:
        """Fetches historical candles for active or spot index instrument."""
        pass
