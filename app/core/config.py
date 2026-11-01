"""
Application settings and configuration management using Pydantic.
Enforces execution mode guards, directory provisioning, and environment parsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform configuration with strict safety validations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: str = "INFO"

    # Execution Mode: Critical Safety Guardrail
    EXECUTION_MODE: Literal["BACKTEST", "PAPER"] = "BACKTEST"

    # Upstox API Credentials
    UPSTOX_API_KEY: str = Field(default="", description="Upstox API Key / Client ID")
    UPSTOX_API_SECRET: str = Field(default="", description="Upstox API Secret")
    UPSTOX_REDIRECT_URI: str = Field(
        default="http://127.0.0.1:8000/api/v1/auth/callback",
        description="Registered OAuth redirect URI",
    )
    UPSTOX_ACCESS_TOKEN: str = Field(default="", description="Daily access token")

    # Upstox API Endpoints
    UPSTOX_BASE_URL: str = "https://api.upstox.com/v2"
    UPSTOX_AUTH_DIALOG_URL: str = "https://api.upstox.com/v2/login/authorization/dialog"
    UPSTOX_TOKEN_URL: str = "https://api.upstox.com/v2/login/authorization/token"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/algotrading.db"
    SYNC_DATABASE_URL: str = "sqlite:///./data/algotrading.db"

    # Storage Directories
    DATA_DIR: Path = Path("./data")
    REPORTS_DIR: Path = Path("./reports")
    CACHE_DIR: Path = Path("./data/cache")

    # Risk Management Defaults (tuned for ₹25,000 INR account)
    STARTING_CAPITAL: float = 25000.0
    MAX_RISK_PER_TRADE_PCT: float = 2.0  # Max 2% per trade
    MAX_DAILY_LOSS_PCT: float = 5.0  # Max 5% per day
    MAX_OPEN_POSITIONS: int = 2  # Conservative for ₹25k
    MAX_CAPITAL_ALLOCATION_PCT: float = 80.0

    # Backtesting & Execution Defaults
    DEFAULT_SLIPPAGE_POINTS: float = 0.5
    DEFAULT_TRANSACTION_COST_MODEL: str = "upstox_standard_equity_derivatives"

    @field_validator("EXECUTION_MODE")
    @classmethod
    def validate_execution_mode(cls, v: str) -> str:
        v_upper = v.upper()
        if v_upper not in ("BACKTEST", "PAPER"):
            raise ValueError(
                f"Execution mode '{v}' is forbidden. AlgoTradingResearch strictly permits only 'BACKTEST' or 'PAPER'."
            )
        return v_upper

    def ensure_directories(self) -> None:
        """Create storage directories if they do not exist."""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)


# Global settings singleton
settings = Settings()
settings.ensure_directories()
