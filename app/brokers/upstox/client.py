"""
Upstox API v2 Client implementation.
Provides read-only access to market data and expired F&O contracts with retry and error handling.
Does NOT implement order execution endpoints.
"""

from __future__ import annotations

import asyncio
import urllib.parse
from typing import Any

import httpx

from app.brokers.base import BaseBrokerClient
from app.brokers.upstox.auth import UpstoxAuthManager
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    AuthenticationExpiredError,
    BrokerError,
    EntitlementError,
    RateLimitExceededError,
)
from app.core.logging import logger
from app.domain.candles import CandleBatch, CandleInterval
from app.domain.instruments import (
    FutureContract,
    OptionContract,
    parse_upstox_contract,
)


class UpstoxClient(BaseBrokerClient):
    """
    HTTP client for Upstox v2 API.
    Handles rate-limiting, retries, and data conversion.
    """

    def __init__(
        self,
        access_token: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
    ):
        self.access_token = access_token or settings.UPSTOX_ACCESS_TOKEN
        self.base_url = (base_url or settings.UPSTOX_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.auth_manager = UpstoxAuthManager()

    def get_auth_url(self, state: str | None = None) -> str:
        return self.auth_manager.get_authorization_url(state=state or "AlgoTradingResearch")

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        result = await self.auth_manager.exchange_code_for_token(code)
        self.access_token = result["access_token"]
        return result

    def _get_headers(self, requires_auth: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if requires_auth:
            token = self.access_token or settings.UPSTOX_ACCESS_TOKEN
            if not token:
                raise AuthenticationError(
                    "Upstox access token is not set. Please authenticate via OAuth flow first."
                )
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        requires_auth: bool = True,
    ) -> dict[str, Any]:
        """Internal HTTP requester with exponential backoff on transient errors."""
        url = f"{self.base_url}{path}"
        headers = self._get_headers(requires_auth=requires_auth)

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                    )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "error":
                        error_msg = "; ".join(
                            e.get("message", "Unknown error") for e in data.get("errors", [])
                        )
                        raise BrokerError(f"Upstox API error: {error_msg}")
                    return data

                elif response.status_code == 401:
                    raise AuthenticationExpiredError(
                        "Upstox token expired or invalid (HTTP 401). Please re-authenticate."
                    )
                elif response.status_code == 403:
                    raise EntitlementError(
                        f"Forbidden (HTTP 403) accessing {path}. Verify Upstox Plus activation."
                    )
                elif response.status_code == 429:
                    wait_time = 1.5**attempt
                    logger.warning("Rate limit (HTTP 429) hit. Backing off for %.1fs...", wait_time)
                    if attempt == self.max_retries:
                        raise RateLimitExceededError(
                            "Upstox rate limit exceeded after maximum retries."
                        )
                    await asyncio.sleep(wait_time)
                    continue
                elif response.status_code >= 500:
                    wait_time = 1.5**attempt
                    logger.warning(
                        "Server error (HTTP %d). Retry %d/%d...",
                        response.status_code,
                        attempt,
                        self.max_retries,
                    )
                    if attempt == self.max_retries:
                        raise BrokerError(
                            f"Upstox server error (HTTP {response.status_code}): {response.text}"
                        )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise BrokerError(
                        f"Upstox HTTP {response.status_code} error from {path}: {response.text}"
                    )

            except httpx.RequestError as exc:
                if attempt == self.max_retries:
                    raise BrokerError(f"Network error communicating with Upstox: {exc}") from exc
                await asyncio.sleep(1.0 * attempt)

        raise BrokerError("Unexpected request failure in UpstoxClient._request")

    async def validate_session(self) -> dict[str, Any]:
        """
        Validates API connectivity using read-only profile endpoint.
        GET /v2/user/profile
        """
        logger.info("Validating Upstox session via /v2/user/profile...")
        res = await self._request("GET", "/user/profile", requires_auth=True)
        return res.get("data", {})

    async def get_expiries(self, underlying_key: str = "NSE_INDEX|Nifty 50") -> list[str]:
        """
        Retrieves all available expired dates for an underlying instrument.
        GET /v2/expired-instruments/expiries?instrument_key=...
        """
        logger.info("Fetching expiries for %s...", underlying_key)
        params = {"instrument_key": underlying_key}
        res = await self._request(
            "GET", "/expired-instruments/expiries", params=params, requires_auth=True
        )
        return res.get("data", [])

    async def get_expired_future_contracts(
        self, underlying_key: str, expiry_date: str
    ) -> list[FutureContract]:
        """
        Retrieves expired future contracts for underlying on expiry_date (YYYY-MM-DD).
        GET /v2/expired-instruments/future/contract?instrument_key=...&expiry_date=...
        """
        logger.info("Fetching expired futures for %s on %s...", underlying_key, expiry_date)
        params = {
            "instrument_key": underlying_key,
            "expiry_date": expiry_date,
        }
        res = await self._request(
            "GET", "/expired-instruments/future/contract", params=params, requires_auth=True
        )
        contracts: list[FutureContract] = []
        for item in res.get("data", []):
            try:
                contract = parse_upstox_contract(item, is_expired=True)
                if isinstance(contract, FutureContract):
                    contracts.append(contract)
            except Exception as e:
                logger.warning("Could not parse future contract %s: %s", item, e)
        return contracts

    async def get_expired_option_contracts(
        self, underlying_key: str, expiry_date: str
    ) -> list[OptionContract]:
        """
        Retrieves expired option contracts for underlying on expiry_date (YYYY-MM-DD).
        GET /v2/expired-instruments/option/contract?instrument_key=...&expiry_date=...
        """
        logger.info("Fetching expired options for %s on %s...", underlying_key, expiry_date)
        params = {
            "instrument_key": underlying_key,
            "expiry_date": expiry_date,
        }
        res = await self._request(
            "GET", "/expired-instruments/option/contract", params=params, requires_auth=True
        )
        contracts: list[OptionContract] = []
        for item in res.get("data", []):
            try:
                contract = parse_upstox_contract(item, is_expired=True)
                if isinstance(contract, OptionContract):
                    contracts.append(contract)
            except Exception as e:
                logger.warning("Could not parse option contract %s: %s", item, e)
        return contracts

    async def get_expired_candles(
        self,
        expired_instrument_key: str,
        interval: CandleInterval,
        to_date: str,
        from_date: str,
    ) -> CandleBatch:
        """
        Fetches historical candles for an expired contract.
        Official endpoint:
        GET /v2/expired-instruments/historical-candle/{expired_instrument_key}/{interval}/{to_date}/{from_date}
        Notice: to_date precedes from_date in path.
        """
        encoded_key = urllib.parse.quote(expired_instrument_key, safe="")
        path = f"/expired-instruments/historical-candle/{encoded_key}/{interval.value}/{to_date}/{from_date}"
        logger.info(
            "Requesting expired candles for %s (%s) from %s to %s",
            expired_instrument_key,
            interval.value,
            from_date,
            to_date,
        )
        res = await self._request("GET", path, requires_auth=True)
        raw_candles = res.get("data", {}).get("candles", [])
        return CandleBatch.from_upstox_raw(
            instrument_key=expired_instrument_key,
            interval=interval,
            raw_candles=raw_candles,
        )

    async def get_historical_candles(
        self,
        instrument_key: str,
        interval: CandleInterval,
        to_date: str,
        from_date: str,
    ) -> CandleBatch:
        """
        Fetches historical candles for standard active instrument or underlying cash index.
        Official endpoint:
        GET /v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
        """
        encoded_key = urllib.parse.quote(instrument_key, safe="")
        path = f"/historical-candle/{encoded_key}/{interval.value}/{to_date}/{from_date}"
        logger.info(
            "Requesting historical candles for %s (%s) from %s to %s",
            instrument_key,
            interval.value,
            from_date,
            to_date,
        )
        # Standard historical candles can work with or without auth
        has_token = bool(self.access_token or settings.UPSTOX_ACCESS_TOKEN)
        res = await self._request("GET", path, requires_auth=has_token)
        raw_candles = res.get("data", {}).get("candles", [])
        return CandleBatch.from_upstox_raw(
            instrument_key=instrument_key,
            interval=interval,
            raw_candles=raw_candles,
        )
