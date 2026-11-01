"""
Unit tests for Upstox OAuth 2.0 authentication, error handling, and live order safety invariants.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.brokers.upstox.auth import UpstoxAuthManager
from app.brokers.upstox.client import UpstoxClient
from app.core.exceptions import (
    AuthenticationExpiredError,
    EntitlementError,
)


def test_auth_url_construction():
    mgr = UpstoxAuthManager(
        api_key="test_api_key",
        api_secret="test_secret",
        redirect_uri="http://127.0.0.1:8000/callback",
    )
    url = mgr.get_authorization_url(state="test_state")
    assert "https://api.upstox.com/v2/login/authorization/dialog" in url
    assert "client_id=test_api_key" in url
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A8000%2Fcallback" in url
    assert "response_type=code" in url
    assert "state=test_state" in url


@pytest.mark.asyncio
@respx.mock
async def test_token_exchange_success():
    respx.post("https://api.upstox.com/v2/login/authorization/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "mocked_jwt_token_12345",
                "user_id": "UCC9999",
                "user_name": "Test User",
                "email": "user@example.com",
                "is_active": True,
            },
        )
    )

    mgr = UpstoxAuthManager(api_key="key", api_secret="secret", redirect_uri="http://callback")
    res = await mgr.exchange_code_for_token("single_use_auth_code")
    assert res["status"] == "success"
    assert res["user_id"] == "UCC9999"
    assert res["access_token"] == "mocked_jwt_token_12345"


@pytest.mark.asyncio
@respx.mock
async def test_client_error_mappings():
    """Verify 401 raises AuthenticationExpiredError and 403 raises EntitlementError."""
    client = UpstoxClient(access_token="mock_token")

    # 401 Unauthorized
    respx.get("https://api.upstox.com/v2/user/profile").mock(
        return_value=httpx.Response(401, json={"status": "error", "message": "Token expired"})
    )
    with pytest.raises(AuthenticationExpiredError):
        await client.validate_session()

    # 403 Forbidden
    respx.get("https://api.upstox.com/v2/expired-instruments/expiries").mock(
        return_value=httpx.Response(
            403, json={"status": "error", "message": "Upstox Plus required"}
        )
    )
    with pytest.raises(EntitlementError):
        await client.get_expiries()


def test_safety_invariant_zero_live_order_endpoints():
    """
    Critical Safety Guarantee:
    Verify that UpstoxClient and BaseBrokerClient do NOT declare or implement any live order placement methods.
    """
    client = UpstoxClient(access_token="dummy")
    forbidden_methods = [
        "place_order",
        "order_place",
        "submit_order",
        "execute_live_order",
        "modify_order",
        "cancel_order",
    ]
    for method in forbidden_methods:
        assert not hasattr(client, method), (
            f"Safety Invariant Violated: {method} found on UpstoxClient!"
        )
