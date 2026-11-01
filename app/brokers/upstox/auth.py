"""
Upstox OAuth 2.0 authentication manager.
Implements official Upstox OAuth 2.0 authorization code flow securely.
"""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AuthenticationError, BrokerError
from app.core.logging import logger


class UpstoxAuthManager:
    """Handles OAuth 2.0 dialog URL creation, code exchange, and token validation."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        redirect_uri: str | None = None,
    ):
        self.api_key = api_key or settings.UPSTOX_API_KEY
        self.api_secret = api_secret or settings.UPSTOX_API_SECRET
        self.redirect_uri = redirect_uri or settings.UPSTOX_REDIRECT_URI

    def get_authorization_url(self, state: str = "AlgoTradingResearchState") -> str:
        """
        Builds the Upstox login dialog URL for user login.
        Official format:
        https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={api_key}&redirect_uri={redirect_uri}&state={state}
        """
        api_key = self.api_key or settings.UPSTOX_API_KEY
        if not api_key:
            raise AuthenticationError(
                "UPSTOX_API_KEY is not configured in environment or .env file."
            )

        params = {
            "response_type": "code",
            "client_id": api_key,
            "redirect_uri": self.redirect_uri or settings.UPSTOX_REDIRECT_URI,
            "state": state,
        }
        encoded = urllib.parse.urlencode(params)
        return f"{settings.UPSTOX_AUTH_DIALOG_URL}?{encoded}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """
        Exchanges single-use authorization code for access token via server-to-server POST.
        Official endpoint: POST https://api.upstox.com/v2/login/authorization/token
        """
        if not self.api_key or not self.api_secret:
            raise AuthenticationError("Both UPSTOX_API_KEY and UPSTOX_API_SECRET must be set.")
        if not code or not code.strip():
            raise AuthenticationError("Authorization code is empty or missing.")

        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = {
            "code": code.strip(),
            "client_id": self.api_key,
            "client_secret": self.api_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }

        logger.info("Exchanging OAuth authorization code for access token with Upstox...")
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    settings.UPSTOX_TOKEN_URL,
                    headers=headers,
                    data=payload,
                )
            except httpx.RequestError as exc:
                raise BrokerError(f"Network error during Upstox token exchange: {exc}") from exc

        if response.status_code != 200:
            error_text = response.text
            logger.error(
                "Token exchange failed with status %d: %s", response.status_code, error_text
            )
            raise AuthenticationError(
                f"Upstox token exchange failed (HTTP {response.status_code}): {error_text}"
            )

        data = response.json()
        access_token = data.get("access_token")
        if not access_token:
            raise AuthenticationError(f"No access_token found in Upstox response: {data}")

        # Update runtime settings securely in-memory
        settings.UPSTOX_ACCESS_TOKEN = access_token
        logger.info(
            "Upstox access token successfully acquired. User UCC: %s, User Name: %s",
            data.get("user_id", "N/A"),
            data.get("user_name", "N/A"),
        )
        return {
            "status": "success",
            "user_id": data.get("user_id"),
            "user_name": data.get("user_name"),
            "email": data.get("email"),
            "access_token": access_token,
            "is_active": data.get("is_active", True),
        }
