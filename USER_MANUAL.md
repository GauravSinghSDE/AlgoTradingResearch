# AlgoTradingResearch: Complete End-to-End User Manual
### *A Beginner-to-Advanced Guide for Indian Market Quant Research, Backtesting & Paper Trading*

---

## 1. What is this Software? (In Plain English)

**AlgoTradingResearch** is a personal quantitative trading research and simulation laboratory built specifically for Indian financial markets (NSE/BSE).

Think of it like a **flight simulator for algorithmic trading**:
* Before an airline pilot flies a real ₹500-crore plane with passengers, they spend hundreds of hours in a high-fidelity simulator where bad weather, engine failures, and turbulence are simulated accurately.
* Similarly, before risking even ₹1 of your hard-earned money in volatile Indian derivatives (NIFTY / BANKNIFTY Options & Futures), this platform lets you test strategies on real historical tick-by-tick candle data, accounts for all real-world Indian taxes (STT, GST, Exchange charges, SEBI fees, Brokerage, and slippage), checks hard risk rules, and paper-trades them in real-time — **with zero financial risk**.

---

## 2. What Can this Software Do? (Full Feature List)

1. **Option Chain Analysis & Contract Selection**:
   * Automatically calculates At-The-Money (ATM), In-The-Money (ITM), and Out-Of-The-Money (OTM) strikes for NIFTY (50-point intervals) and BANKNIFTY (100-point intervals).
   * Automatically identifies the nearest weekly or monthly expiry.
2. **Zero Look-Ahead Bias Backtesting**:
   * Many rookie trading systems cheat by "peeking into the future" (using the closing price of a bar to trade that exact same bar). 
   * This engine executes strictly on the **Open of the next candle**, just like real life.
3. **Realistic Indian Transaction Costs**:
   * Models the official October 1, 2024 SEBI & Govt tax schedules:
     * Brokerage (capped at ₹20/order)
     * Securities Transaction Tax (STT): 0.1% on Option sell premiums, 0.02% on Futures
     * GST (18%)
     * Exchange turnover fees
     * SEBI turnover charges
     * Stamp duty
     * Realistic slippage (execution delay loss)
4. **Institutional Risk Circuit Breakers**:
   * **Daily Loss Limit**: Halts trading for the day if you lose more than a set percentage (default: 5%).
   * **Max Risk Per Trade**: Ensures no single trade risks more than e.g. 2% of your account.
   * **Margin & Cash Checks**: Prevents entering positions if you lack the required cash (e.g. buying a NIFTY Futures lot requires ~₹1.2 Lakh; with ₹25,000 capital, the risk manager will safely reject it and explain why).
   * **Anti-Duplicate Rule**: Blocks entering the exact same position twice.
5. **Paper Trading Engine**:
   * Simulates real-time order execution with virtual capital.
   * Tracks open positions, unrealized P&L, realized P&L, and peak drawdown.
   * Crash-recovery: saves state locally (`data/paper_state.json`) so if your computer restarts, your positions and portfolio are remembered.
   * **Emergency Kill Switch**: Instantly halts paper trading and closes positions if triggered.
6. **Relational Database & Parquet Storage**:
   * Stores high-speed tick/candle data in Apache Parquet files.
   * Automatically logs every backtest and individual trade into an SQLite database (`data/algotrading.db`) via SQLAlchemy and Alembic migrations.
7. **Interactive Web Dashboard & REST API**:
   * Beautiful Streamlit web interface with interactive Plotly charts, equity curves, drawdown graphs, and data health inspection.
   * High-performance FastAPI backend with full OpenAPI (`/docs`) swagger documentation.

---

## 3. Computer Prerequisites (What Your Friend Needs)

Your friend only needs a standard computer (Windows, Mac, or Linux):
1. **Python 3.10, 3.11, or 3.12** installed (make sure *"Add Python to PATH"* was checked during installation).
2. **Git** installed.
3. **Windows PowerShell** (or Terminal on Mac/Linux).
4. *(Optional but recommended)* A free **Upstox account** with an API app created if they want to download live/fresh historical candles from Upstox directly. If they don't have an Upstox account, **the platform still works out of the box** using the included historical sample datasets!

---

## 4. Step 1: Setting Up the Project (First 5 Minutes)

When your friend receives the `AlgoTradingResearch` folder, here are the exact steps to set it up:

### Open PowerShell in the project folder
1. Open Windows PowerShell.
2. Navigate to the project directory:
   ```powershell
   cd C:\Users\<YourUsername>\Path\To\AlgoTradingResearch
   ```

### Create the Python Virtual Environment
A virtual environment ensures the project's packages don't interfere with anything else on the computer:
```powershell
python -m venv .venv
```

### Install All Required Libraries
Install the dependencies in editable mode:
```powershell
.\.venv\Scripts\pip.exe install -e ".[dev]"
```
*(This installs FastAPI, Streamlit, Pandas, NumPy, PyArrow, SQLAlchemy, Plotly, Pytest, Ruff, and all supporting tools.)*

---

## 5. Step 2: Configuration & Where to Put Credentials and Money

All user settings are stored in a single file named `.env`.

### 1. Create the `.env` file
In PowerShell, copy the provided template:
```powershell
Copy-Item .env.example .env
```
Now open `.env` in any text editor (Notepad, VS Code, etc.).

### 2. Enter Upstox Credentials (If downloading broker data)
Log in to the [Upstox Developer Portal](https://upstox.com/developer/api-documentation/), create an app (e.g. named `AlgoTradingResearch`), and fill in:
```env
# Upstox API Credentials
UPSTOX_API_KEY="your_api_key_here"
UPSTOX_API_SECRET="your_api_secret_here"
UPSTOX_REDIRECT_URI="http://127.0.0.1:8000/api/v1/auth/callback"
UPSTOX_ACCESS_TOKEN=""
```
> [!NOTE]
> * You can leave these blank initially if you just want to run backtests and simulations on the included local data!
> * The system will **never** log or leak your API Secret or Access Token.

### 3. Tell the System How Much Money You Want to Trade With
Look for the section marked `# Risk Management Defaults` in `.env`:
```env
# Starting capital in Indian Rupees (INR)
STARTING_CAPITAL=25000.0

# Maximum risk allowed on any single trade (percentage of capital)
# 2.0% of Rs. 25,000 = Rs. 500 maximum loss per trade
MAX_RISK_PER_TRADE_PCT=2.0

# Circuit breaker: halt trading if daily loss reaches this percentage
# 5.0% of Rs. 25,000 = Rs. 1,250 maximum loss per day
MAX_DAILY_LOSS_PCT=5.0

# Maximum concurrent open positions allowed
MAX_OPEN_POSITIONS=2

# Maximum percentage of capital to tie up in margins
MAX_CAPITAL_ALLOCATION_PCT=80.0
```

> **Where does your friend decide their trading capital?**
> Right here in `STARTING_CAPITAL`. If they want to test with ₹50,000 or ₹1,00,000, they simply change `STARTING_CAPITAL=50000.0`. They can also override this on the fly in the command line or in the web dashboard!

---

## 6. Step 3: Run the Health Check & Tests

Before doing anything, verify that the environment is 100% healthy:

### 1. Run the Environment Verifier
```powershell
.\.venv\Scripts\python.exe scripts/verify_environment.py
```
*You will see a green checklist verifying Python, required libraries, directory storage, and safety invariants.*

### 2. Run the Full Test Suite
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```
*You should see **39 passed** tests confirming the mathematics, risk checks, tax formulas, database, and API endpoints are working properly.*

---

## 7. Step 4: How to Run Backtests (Testing a Strategy on Past Data)

Backtesting lets you test a trading rule against past market data to see if it would have made or lost money after all fees and taxes.

### Running via Command Line
Run the Moving Average Crossover strategy on 1-minute NIFTY option data with ₹25,000 capital:
```powershell
.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy ma_crossover --instrument "NSE_FO|NIFTY24O3124500CE" --capital 25000
```

#### What the Output Table Shows:
* **Initial Capital**: ₹25,000.00
* **Final Equity**: ₹25,407.15
* **Gross P&L**: ₹1,701.50 *(profit before taxes)*
* **Total Statutory & Brokerage Costs**: ₹794.34 *(brokerage + STT + GST + exchange fees deducted!)*
* **Net P&L**: ₹407.15 *(your true take-home profit after all friction)*
* **Max Drawdown**: Largest drop from peak (e.g. 5.01%)
* **Win Rate**: e.g. 40.0% (16 wins / 24 losses)
* **Profit Factor**: 1.40 *(ratio of gross profits to gross losses; > 1.0 means profitable)*
* **Rejected Orders**: Shows how many times your risk rules prevented bad trades.

Every backtest is automatically assigned a unique ID and saved into the SQLite database (`data/algotrading.db`).

---

## 8. Step 5: How to Use the Interactive Web Dashboard

If your friend prefers a visual user interface with buttons, charts, and tables rather than typing in a terminal, launch the Streamlit dashboard:

```powershell
.\.venv\Scripts\streamlit.exe run app/dashboard/streamlit_app.py
```
*Your web browser will automatically open to `http://localhost:8501`.*

### What You Can Do in the Dashboard:
1. **System & Safety Invariants**: Shows active mode (`BACKTEST` or `PAPER`), confirms that live execution is disabled, and displays system health.
2. **Strategy Backtesting Page**: Select any strategy from a dropdown, choose an instrument, adjust capital slider (e.g. ₹25,000 to ₹1,00,000), set stop-loss and target points, and click **"Run Backtest"**.
3. **Interactive Charts**: Zoom into candlestick charts with moving average overlays, buy/sell markers, equity growth curves, and drawdown charts.
4. **Option Chain Viewer**: View strike ladders for NIFTY & BANKNIFTY, see which strikes are ATM, ITM, or OTM, and inspect contract details.
5. **Trade Ledger & Cost Breakdown**: Inspect every single simulated trade with exact entry time, exit time, gross P&L, brokerage, STT, and net P&L.
6. **Data Quality Reports**: Inspect candle data health (missing minutes, gaps, price coherence).
7. **Paper Trading Monitor**: View open virtual positions, real-time P&L, and toggle the **Emergency Kill Switch**.

---

## 9. Step 6: How to Run the REST API Server

If your friend wants to integrate with other apps or use HTTP endpoints:
```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```
Open your browser to:
* **API Documentation (Swagger UI)**: `http://127.0.0.1:8000/docs`
* **System Status Endpoint**: `http://127.0.0.1:8000/api/v1/system/status`

---

## 10. Step 7: How Paper Trading Works (Simulated Live Trading)

Paper trading allows your friend to test their logic in a live simulation without risking real money:

```powershell
.\.venv\Scripts\python.exe scripts/run_paper_trading.py --strategy ma_crossover --instrument "NSE_FO|NIFTY24O3124500CE" --capital 25000
```

* **Virtual Portfolio**: Begins with ₹25,000 virtual cash.
* **State Persistence**: Current cash, equity, and positions are safely saved in `data/paper_state.json`.
* **Duplicate Prevention**: If an open position in that instrument already exists, the risk manager rejects a duplicate entry to prevent over-leverage.
* **To reset paper trading state**:
  ```powershell
  .\.venv\Scripts\python.exe scripts/run_paper_trading.py --reset-state
  ```

---

## 11. How to Download Fresh Historical Data from Upstox

To download real expired or active candle data from Upstox:

1. **Authenticate Once Per Day**:
   Run the auth helper:
   ```powershell
   .\.venv\Scripts\python.exe scripts/verify_upstox_auth.py
   ```
   Follow the prompt to log in via browser and paste the returned token/code into your `.env`.

2. **Download Candles**:
   ```powershell
   .\.venv\Scripts\python.exe scripts/download_historical_data.py --instrument "NSE_INDEX|Nifty 50" --interval 1minute --from-date 2024-10-01 --to-date 2024-10-31
   ```
   *For expired derivative contracts, add the `--expired` flag:*
   ```powershell
   .\.venv\Scripts\python.exe scripts/download_historical_data.py --instrument "NSE_FO|NIFTY24O3124500CE" --interval 1minute --from-date 2024-10-24 --to-date 2024-10-31 --expired
   ```
   The data is downloaded, validated for quality (no missing bars or bad prices), and stored as high-speed Apache Parquet files in `data/candles/`.

---

## 12. Crucial Question: "How Do I Do Actual / Real-Money Trading?"

> [!WARNING]
> ### Live Real-Money Trading is Deliberately Disabled by Default
> If your friend searches the codebase for an order placement button or an API call like `POST /v2/order/place`, **they will not find one**. This is an intentional architectural safety feature.

### Why is Live Trading Disabled?
1. **Capital Safety**: In options and futures, a simple software bug (like an infinite loop or a misplaced decimal) can wipe out an entire trading account in 30 seconds.
2. **SEBI Regulations in India**: Under SEBI circulars, algorithmic strategies interacting with exchange order books require formal broker empanelment, broker risk management approval, and exchange-assigned Strategy IDs. Offering or using unapproved automated black-box execution can lead to terminal freezing and exchange penalties.
3. **The `LiveTradingDisabledError` Guardrail**:
   In `app/core/config.py`, the platform only accepts two execution modes:
   ```python
   EXECUTION_MODE: Literal["BACKTEST", "PAPER"]
   ```
   If any script attempts live trading, the engine raises an immediate `LiveTradingDisabledError` and terminates.

### What is the Path to Live Trading?
Before ever connecting real money:
1. Your friend must prove a strategy's statistical edge across at least **6 to 12 months of historical data** across bull, bear, and sideways regimes.
2. The strategy must run in **Paper Trading mode** for at least 30 consecutive market days with positive risk-adjusted metrics.
3. Once proven, live order placement can be added via an authorized broker adapter complying with your broker's specific retail API guidelines and order rate limits.

---

## 13. Summary Quick Reference (Cheat Sheet)

| What You Want to Do | Command to Run in PowerShell |
| :--- | :--- |
| **Check system health** | `.\.venv\Scripts\python.exe scripts/verify_environment.py` |
| **Run all 39 tests** | `.\.venv\Scripts\python.exe -m pytest -v` |
| **Run a strategy backtest** | `.\.venv\Scripts\python.exe scripts/run_backtest.py --strategy ma_crossover --instrument "NSE_FO|NIFTY24O3124500CE" --capital 25000` |
| **Open the Web Dashboard** | `.\.venv\Scripts\streamlit.exe run app/dashboard/streamlit_app.py` |
| **Start the REST API server** | `.\.venv\Scripts\uvicorn.exe app.main:app --reload` |
| **Run paper trading** | `.\.venv\Scripts\python.exe scripts/run_paper_trading.py --capital 25000` |
| **Reset paper portfolio** | `.\.venv\Scripts\python.exe scripts/run_paper_trading.py --reset-state` |
| **Change capital/risk** | Edit `STARTING_CAPITAL`, `MAX_RISK_PER_TRADE_PCT` in `.env` |
