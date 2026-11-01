"""
Domain-specific exceptions for AlgoTradingResearch.
Provides clear, actionable error hierarchies.
"""

from __future__ import annotations


class AlgoTradingError(Exception):
    """Base class for all application exceptions."""

    pass


class ConfigurationError(AlgoTradingError):
    """Raised when configuration or domain parameter values are invalid."""

    pass


# --- Authentication & Broker Exceptions ---
class BrokerError(AlgoTradingError):
    """Base error for broker communications."""

    pass


class AuthenticationError(BrokerError):
    """Raised when authentication credentials are invalid or missing."""

    pass


class AuthenticationExpiredError(AuthenticationError):
    """Raised when the daily broker session/access token has expired."""

    pass


class RateLimitExceededError(BrokerError):
    """Raised when API rate limit (429) is encountered."""

    pass


class EntitlementError(BrokerError):
    """Raised when user lacks subscription/plus tier for the requested endpoint."""

    pass


# --- Data Layer Exceptions ---
class DataError(AlgoTradingError):
    """Base error for data operations."""

    pass


class InstrumentNotFoundError(DataError):
    """Raised when an instrument key cannot be resolved."""

    pass


class DataQualityError(DataError):
    """Raised when historical candles fail validation (gaps, nulls, invalid order)."""

    pass


class MissingHistoricalDataError(DataError):
    """Raised when no historical data exists for requested range."""

    pass


# --- Backtesting & Strategy Exceptions ---
class BacktestError(AlgoTradingError):
    """Base error for backtesting engine."""

    pass


class LookAheadBiasError(BacktestError):
    """Raised when strategy or engine attempts to access future candles or information."""

    pass


class InsufficientMarginError(BacktestError):
    """Raised when portfolio lacks required margin/cash for derivative trade."""

    pass


class RiskLimitBreachedError(BacktestError):
    """Raised when a trade violates hard risk limits."""

    def __init__(self, rule_name: str, reason: str, details: dict | None = None):
        super().__init__(f"Risk rule '{rule_name}' breached: {reason}")
        self.rule_name = rule_name
        self.reason = reason
        self.details = details or {}


# --- Execution Safety Guard ---
class LiveTradingDisabledError(AlgoTradingError):
    """Raised immediately if any code attempts live order execution."""

    def __init__(
        self, message: str = "Live trading is strictly disabled in this platform version."
    ):
        super().__init__(message)
