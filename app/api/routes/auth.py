"""
OAuth 2.0 authentication endpoints for Upstox integration.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.brokers.upstox.auth import UpstoxAuthManager
from app.brokers.upstox.client import UpstoxClient
from app.core.config import settings
from app.core.exceptions import AuthenticationError

router = APIRouter(prefix="/auth", tags=["Authentication"])
auth_manager = UpstoxAuthManager()


@router.get("/url")
async def get_login_url(state: str = "AlgoTradingResearch") -> dict[str, str]:
    """Returns the Upstox OAuth 2.0 authorization URL for browser login."""
    try:
        url = auth_manager.get_authorization_url(state=state)
        return {"authorization_url": url}
    except AuthenticationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/callback", response_class=HTMLResponse)
async def auth_callback(
    code: str = Query(..., description="Authorization code from Upstox"),
    state: str | None = Query(None),
) -> HTMLResponse:
    """
    Callback URL registered in Upstox Developer App.
    Exchanges code for access token and confirms session.
    """
    try:
        res = await auth_manager.exchange_code_for_token(code)
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Upstox Authorization Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background-color: #f7f9fc;">
                    <div style="max-width: 500px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                        <h2 style="color: #2e7d32;">Authentication Successful</h2>
                        <p>User UCC: <b>{res.get("user_id", "N/A")}</b></p>
                        <p>Name: <b>{res.get("user_name", "N/A")}</b></p>
                        <p style="color: #555;">Daily access token is active. You may return to the dashboard or close this window.</p>
                    </div>
                </body>
            </html>
            """
        )
    except Exception as e:
        return HTMLResponse(
            content=f"""
            <html>
                <head><title>Authorization Failed</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <div style="max-width: 500px; margin: auto; background: white; padding: 30px; border-radius: 8px;">
                        <h2 style="color: #c62828;">Authentication Failed</h2>
                        <p style="color: #555;">{str(e)}</p>
                    </div>
                </body>
            </html>
            """,
            status_code=400,
        )


@router.get("/status")
async def get_auth_status() -> dict[str, Any]:
    """Checks whether access token is configured and validates connectivity."""
    has_token = bool(settings.UPSTOX_ACCESS_TOKEN)
    if not has_token:
        return {
            "authenticated": False,
            "message": "No Upstox access token configured for today. Please log in via OAuth.",
        }

    client = UpstoxClient(access_token=settings.UPSTOX_ACCESS_TOKEN)
    try:
        profile = await client.validate_session()
        return {
            "authenticated": True,
            "user_id": profile.get("user_id"),
            "user_name": profile.get("user_name"),
            "broker": "Upstox",
            "execution_mode": settings.EXECUTION_MODE,
        }
    except Exception as e:
        return {
            "authenticated": False,
            "error": str(e),
            "message": "Token is present but validation failed. Reauthorization required.",
        }
