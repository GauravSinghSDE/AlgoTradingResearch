# Data Sources Specification & Broker API Capabilities

This document details verified broker capabilities, official API endpoints, parameters, limits, and behavior for **Upstox API v2**.

---

## 1. Upstox API v2 Architecture

Upstox API v2 provides market data, account info, and expired derivatives data for backtesting via REST and WebSocket.

### Base URLs:
- Production REST: `https://api.upstox.com/v2`
- Login Dialog: `https://api.upstox.com/v2/login/authorization/dialog`
- Token Exchange: `https://api.upstox.com/v2/login/authorization/token`

---

## 2. Authentication Flow

- **Protocol:** OAuth 2.0 Authorization Code Flow.
- **Grant Type:** `authorization_code`.
- **Step 1:** Browser redirect to:
  `GET https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={API_KEY}&redirect_uri={REDIRECT_URI}&state={STATE}`
- **Step 2:** User completes 2FA/TOTP on Upstox; redirect returns `?code={AUTH_CODE}`.
- **Step 3:** Server-to-server exchange:
  `POST https://api.upstox.com/v2/login/authorization/token`
  - Headers: `Content-Type: application/x-www-form-urlencoded`, `Accept: application/json`
  - Body:
    - `code`: single-use authorization code
    - `client_id`: API Key
    - `client_secret`: API Secret
    - `redirect_uri`: Configured redirect URL
    - `grant_type`: `authorization_code`
- **Session Duration:** Tokens expire daily at ~03:30 AM IST.

---

## 3. Expired Derivatives Endpoints (Requires Upstox Plus)

Upstox provides special endpoints for accessing expired contracts and historical candle data for derivatives.

### A. Get Expiries
- **Method & URL:** `GET https://api.upstox.com/v2/expired-instruments/expiries`
- **Query Parameters:**
  - `instrument_key` (Required): e.g. `NSE_INDEX|Nifty 50` or `NSE_INDEX|Nifty Bank`
- **Headers:** `Authorization: Bearer {access_token}`
- **Response Format:**
  ```json
  {
    "status": "success",
    "data": [
      "2024-10-03",
      "2024-10-10",
      "2024-10-17",
      "2024-10-24",
      "2024-10-31"
    ]
  }
  ```
- **Coverage:** Up to 6 months of historical expiries.

### B. Get Expired Future Contracts
- **Method & URL:** `GET https://api.upstox.com/v2/expired-instruments/future/contract`
- **Query Parameters:**
  - `instrument_key` (Required): Underlying instrument key, e.g. `NSE_INDEX|Nifty 50`
  - `expiry_date` (Required): Format `YYYY-MM-DD`
- **Headers:** `Authorization: Bearer {access_token}`
- **Response Format:**
  ```json
  {
    "status": "success",
    "data": [
      {
        "name": "NIFTY",
        "segment": "NSE_FO",
        "exchange": "NSE",
        "expiry": "2024-10-31",
        "instrument_key": "NSE_FO|54452|31-10-2024",
        "exchange_token": "54452",
        "trading_symbol": "NIFTY 31 OCT 24 FUT",
        "tick_size": 5,
        "lot_size": 25,
        "instrument_type": "FUT",
        "freeze_quantity": 1800,
        "underlying_key": "NSE_INDEX|Nifty 50",
        "underlying_type": "INDEX",
        "underlying_symbol": "NIFTY"
      }
    ]
  }
  ```

### C. Get Expired Option Contracts
- **Method & URL:** `GET https://api.upstox.com/v2/expired-instruments/option/contract`
- **Query Parameters:**
  - `instrument_key` (Required): e.g. `NSE_INDEX|Nifty 50`
  - `expiry_date` (Required): Format `YYYY-MM-DD`
- **Headers:** `Authorization: Bearer {access_token}`
- **Response Format:** Array of option contracts with fields:
  `name`, `segment`, `exchange`, `expiry`, `instrument_key`, `exchange_token`, `trading_symbol`, `tick_size`, `lot_size`, `instrument_type` ("CE" or "PE"), `strike_price`, `weekly`, `freeze_quantity`, etc.

### D. Get Expired Historical Candle Data
- **Method & URL:**
  `GET https://api.upstox.com/v2/expired-instruments/historical-candle/{expired_instrument_key}/{interval}/{to_date}/{from_date}`
- **Path Parameters (Notice ordering: `to_date` precedes `from_date`):**
  - `expired_instrument_key`: Instrument key URL-encoded (e.g. `NSE_FO%7CNIFTY24O3124500CE` or `NSE_FO%7C54452%7C31-10-2024`)
  - `interval`: `1minute`, `3minute`, `5minute`, `15minute`, `30minute`, `day`
  - `to_date`: `YYYY-MM-DD` (inclusive end date)
  - `from_date`: `YYYY-MM-DD` (inclusive start date)
- **Headers:** `Authorization: Bearer {access_token}`
- **Response Format:**
  ```json
  {
    "status": "success",
    "data": {
      "candles": [
        [
          "2024-10-31T09:15:00+05:30",
          125.35,
          126.80,
          120.00,
          121.50,
          45000,
          1200000
        ]
      ]
    }
  }
  ```
  **Candle Tuple Index Schema:**
  - Index 0: `timestamp` (ISO 8601 string with IST timezone offset `+05:30`)
  - Index 1: `open` (float)
  - Index 2: `high` (float)
  - Index 3: `low` (float)
  - Index 4: `close` (float)
  - Index 5: `volume` (integer)
  - Index 6: `open_interest` (integer or 0 if unpopulated)

---

## 4. Standard Historical Data (Active / Underlying Spot)

For active instruments or cash indices (such as `NSE_INDEX|Nifty 50`):
- `GET https://api.upstox.com/v2/historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}`
- `GET https://api.upstox.com/v2/historical-candle/intraday/{instrument_key}/{interval}`

---

## 5. Rate Limits & Reliability

- Historical candle endpoints are subject to rate limiting (typically 10-25 requests/sec depending on tier).
- Implement exponential backoff on HTTP 429 (Too Many Requests).
- Implement chunking for requests spanning large date ranges.
- Store downloaded candles as normalized Apache Parquet files partitioned by `underlying/segment/contract/interval` to avoid redundant API queries.
