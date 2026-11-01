"""
Upstox Authentication Verification & Daily Login Script.
Tests read-only connectivity and assists in obtaining today's OAuth access token.
Never prints or logs raw secrets.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.brokers.upstox.auth import UpstoxAuthManager
from app.brokers.upstox.client import UpstoxClient
from app.core.config import settings


async def main() -> int:
    print("=" * 60)
    print("Upstox Authentication & Connectivity Check")
    print("=" * 60)

    auth = UpstoxAuthManager()

    # 1. Check API Key
    if not settings.UPSTOX_API_KEY or settings.UPSTOX_API_KEY == "your_api_key_here":
        print("[FAIL] UPSTOX_API_KEY is not configured in .env.")
        print("Please copy .env.example to .env and set your Upstox API credentials.")
        return 1

    print(
        f"[OK] UPSTOX_API_KEY configured: {settings.UPSTOX_API_KEY[:4]}...{settings.UPSTOX_API_KEY[-4:]}"
    )
    print(f"[OK] Redirect URI configured: {settings.UPSTOX_REDIRECT_URI}")

    # 2. Check Access Token
    if not settings.UPSTOX_ACCESS_TOKEN or settings.UPSTOX_ACCESS_TOKEN == "your_access_token_here":
        print("\n[WARN] UPSTOX_ACCESS_TOKEN is missing in .env.")
        print("To generate your daily access token:")
        print("1. Open the following URL in your web browser:")
        try:
            auth_url = auth.get_authorization_url()
            print(f"\n{auth_url}\n")
        except Exception as e:
            print(f"Error generating auth URL: {e}")
            return 1

        print("2. Log in with your Upstox mobile number, PIN, and TOTP.")
        print(
            "3. After login, your browser will redirect to your redirect URI with a ?code= parameter."
        )
        print("4. Copy that 'code' value and run:")
        print("   python scripts/verify_upstox_auth.py --code <YOUR_CODE>")
        return 0

    # 3. If code was provided via command line
    if len(sys.argv) >= 3 and sys.argv[1] == "--code":
        code = sys.argv[2]
        print("Exchanging authorization code...")
        try:
            res = await auth.exchange_code_for_token(code)
            print("[OK] Access token successfully acquired and loaded in memory!")
            print(f"User UCC: {res.get('user_id')}")
            print(f"User Name: {res.get('user_name')}")
            print(
                "\nPlease add UPSTOX_ACCESS_TOKEN to your .env file to persist it for today's session."
            )
        except Exception as e:
            print(f"[FAIL] Failed to exchange code for token: {e}")
            return 1
        return 0

    # 4. Verify existing token with read-only profile call
    client = UpstoxClient(access_token=settings.UPSTOX_ACCESS_TOKEN)
    print("\nValidating active token via read-only /v2/user/profile...")
    try:
        profile = await client.validate_session()
        print("[OK] Session is ACTIVE and VALID!")
        print(f"User UCC: {profile.get('user_id', 'N/A')}")
        print(f"User Name: {profile.get('user_name', 'N/A')}")
        print(f"Email: {profile.get('email', 'N/A')}")
        print(f"Broker Segment Access: {', '.join(profile.get('exchanges', []))}")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"[FAIL] Token validation failed: {e}")
        print("Your token may have expired (session tokens reset daily at 03:30 AM IST).")
        print("Run again without a token to get a new authorization login link.")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
