# AlgoTradingResearch — Personal Algorithmic Trading Research Platform for Indian Financial Markets

A complete, locally runnable personal quantitative research, backtesting, and paper-trading platform tailored for Indian financial markets (NSE Index Derivatives: NIFTY/BANKNIFTY options and futures) integrated with Upstox API v2.

---

## 1. What This Platform Does & Does NOT Do

### What It Does:
- **Zero Look-Ahead Bias Backtesting:** Event-driven simulation where signals generated on completed candle $T$ execute strictly at the **Open of candle $T+1$**.
- **Historical Expired F&O Data Integration:** Implements verified Upstox API v2 endpoints for discovering expired option contracts, expired futures, and 1-minute historical OHLCV candles.
- **Indian Market Realistic Transaction Costs:** Accurately models Upstox discount brokerage (₹20 cap), STT (revised rates), Exchange Turnover Charges, GST (18%), SEBI Turnover Charges, Stamp Duty, and customizable slippage.
- **Strict Risk Management:** Independent risk engine enforcing whole-lot sizes (e.g. 25 for NIFTY), daily loss circuit breakers (kill switches), maximum open positions, and capital caps for starting capital (₹25,000 INR default).
- **Fast Columnar Storage:** Stores historical candles in deduplicated, idempotent Apache Parquet files with Data Quality reports.
- **Paper Trading Engine:** Simulated execution with state persistence, surviving application crashes and restarts without duplicate orders.
- **Interactive Visual Research Dashboard:** 10-page Streamlit application and FastAPI REST backend.

### What It Deliberately Does NOT Do:
- **NO Real-Money Live Order Placement:** Real-money live trading endpoints (`POST /v2/order/place`) are strictly disabled and not implemented as an operational order path in this version.
- **NO Look-Ahead Bias:** Strategies never receive future candles or intrabar peaks.
- **NO Synthetic Candle Fabrication:** If historical data is missing or inaccessible, the platform flags gaps in a data quality report rather than fabricating fake prices.

---

## 2. Prerequisites & Windows Setup

- **Operating System:** Windows 10/11 (or Linux/macOS)
- **Python:** Python 3.10+ (tested on Python 3.10.6)
- **Shell:** PowerShell or CMD
- **Broker Account:** Upstox account with Upstox Plus activated, and an API application created under the name `AlgoTradingResearch`.

---

## 3. Installation & Environment Setup

Run the following commands in PowerShell from the project root:

```powershell
# 1. Create Python virtual environment
python -m venv .venv

# 2. Upgrade pip and install pinned dependencies
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -e ".[dev]"

# Or install directly:
.\.venv\Scripts\pip.exe install fastapi "uvicorn[standard]" streamlit pandas numpy pyarrow httpx pydantic pydantic-settings sqlalchemy aiosqlite python-dotenv plotly pytz python-dateutil rich pytest pytest-asyncio respx ruff
```

---

## 4. Configuration & Credentials

1. Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

2. Open `.env` and fill in your Upstox API credentials:
```ini
ENVIRONMENT=development
LOG_LEVEL=INFO
EXECUTION_MODE=BACKTEST

# Upstox Developer App Credentials
UPSTOX_API_KEY=your_actual_api_key
UPSTOX_API_SECRET=your_actual_api_secret
UPSTOX_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/callback

# Daily Access Token (populated after OAuth login)
UPSTOX_ACCESS_TOKEN=
```

---

## 5. Daily Upstox OAuth Authentication

Upstox requires a daily OAuth 2.0 access token (valid until 03:30 AM IST).

1. Run the verification script:
```powershell
.\.venv\Scripts\python.exe scripts/verify_upstox_auth.py
```
2. If no token is configured, the script outputs the authorization URL. Open it in your web browser.
3. Log in with your Upstox mobile number, PIN, and TOTP.
4. After authorization, copy the `code` parameter from the redirect URL and run:
```powershell
.\.venv\Scripts\python.exe scripts/verify_upstox_auth.py --code <YOUR_CODE>
```
5. Add the returned access token to `.env` as `UPSTOX_ACCESS_TOKEN`.

---

## 6. Running the Historical Data Proof-of-Concept (Rule B)

Run the dedicated proof-of-concept script to verify broker historical data access for expired options and futures:

```powershell
.\.venv\Scripts\python.exe scripts/test_expired_fno_data.py
```

This executable:
- Validates read-only connectivity with Upstox.
- Discovers historical expired dates for `NSE_INDEX|Nifty 50`.
- Discovers expired NIFTY future and option contracts.
- Downloads 1-minute historical candles.
- Runs data quality validation (gap detection, duplicates, volume, and open interest).
- Saves provenance reports to `./reports/poc_reports/`.

---

## 7. Downloading Market Data

To download candles for any instrument and persist to Parquet:

```powershell
# Download expired future candles
.\.venv\Scripts\python.exe scripts/download_historical_data.py --key "NSE_FO|54452|31-10-2024" --interval 1minute --from-date 2024-10-25 --to-date 2024-10-31 --expired

# Download spot index candles
.\.venv\Scripts\python.exe scripts/download_historical_data.py --key "NSE_INDEX|Nifty 50" --interval 1minute --from-date 2024-10-01 --to-date 2024-10-31
```

---

## 8. Running Automated Tests

Run the full pytest suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

The automated test suite verifies:
- Pydantic configuration and execution mode rejection.
- Upstox OAuth URL construction, token exchange, and error handling.
- Invariant check: Upstox client contains zero live order methods.
- Instrument and raw candle parsing into typed domain models.
- Reverse-chronological to chronological candle batch sorting.
- Zero look-ahead bias (next-candle execution).
- Conservative intrabar stop/target resolution.
- Indian transaction costs and STT calculations.
- Hard risk limits (lot size, daily circuit breaker, duplicate entry, margin).
- Paper trading state persistence and crash recovery.

---

## 9. Running Backtests

Execute a deterministic backtest from the command line:

```powershell
.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy ma_crossover --key "NSE_INDEX|Nifty 50" --interval 1minute --capital 25000 --lot-size 25
```

---

## 10. Launching the Web Dashboard & API

### Streamlit Research Dashboard:
```powershell
.\.venv\Scripts\python.exe -m streamlit run app/dashboard/streamlit_app.py
```
Opens in your browser at `http://localhost:8501`.

### FastAPI Backend:
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive OpenAPI Swagger docs available at `http://127.0.0.1:8000/docs`.

---

## 11. Regulatory & Operational Disclaimers

Before any future consideration of live trading, retail traders must comply with applicable **SEBI and NSE algorithmic trading regulations**:
- SEBI circulars require brokers to provide approved API access and client-level order tagging.
- Automated strategy testing must adhere to risk controls and order rate restrictions.
- All testing in this platform is simulated. Past backtested performance is no guarantee of future returns.
