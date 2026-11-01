# Security Policy & Execution Safety — AlgoTradingResearch

## 1. Zero Accidental Live Trading Guardrail

AlgoTradingResearch is designed strictly as a personal research, backtesting, and paper-trading platform. 

### Hard Enforcement:
1. **Execution Mode Guard:** The core system reads `EXECUTION_MODE` from configuration. Permitted modes are strictly:
   - `BACKTEST` (default)
   - `PAPER`
2. **No Order Placement Path:** The broker client implementations in this platform do not implement or expose order placement APIs (`POST /v2/order/place`).
3. **No Auto-Trading on Token:** Presence of an Upstox access token grants read-only capabilities (market quotes, expired contract history, user profile status). It NEVER initiates live orders.
4. **UI Safety:** Streamlit and REST dashboards have no live trading triggers, buttons, or background loops.

---

## 2. Secrets & Credential Management

- **API Keys & Secrets:** Upstox `client_id` (API Key) and `client_secret` (API Secret) must NEVER be committed to version control.
- **`.gitignore` Enforced:** `.env`, `token.json`, and any certificate or key files are explicitly listed in `.gitignore`.
- **Placeholder Only in Version Control:** Only `.env.example` is committed with explicit placeholder values (`your_api_key_here`).
- **No Sensitive Logging:** 
  - Authorization headers (`Authorization: Bearer ***`) are masked in all logs.
  - API secrets and refresh tokens are scrubbed before writing to logs.
  - Token exchange responses log only token expiry and token status, never raw token strings.

---

## 3. Upstox OAuth 2.0 Security Flow

Upstox requires OAuth 2.0 authorization code flow:
1. User logs in via the official Upstox browser dialog (`https://api.upstox.com/v2/login/authorization/dialog`).
2. Upstox redirects to the user's configured local redirect URI (e.g., `http://127.0.0.1:8000/api/v1/auth/callback`) with a single-use authorization code.
3. The backend makes a server-to-server POST request to `https://api.upstox.com/v2/login/authorization/token`.
4. The access token is valid until market close/session expiry (daily at 3:30 AM IST).

### Reauthorization:
- Every morning, trading applications must generate a new access token via Upstox OAuth.
- If a token is expired, the platform raises `AuthenticationExpiredError` and safely falls back to offline cached data or simulation.

---

## 4. Local Database & File Permissions

- Research data, backtest logs, and trade ledgers are stored in `./data/algotrading.db` (SQLite) or a local PostgreSQL instance.
- No public open ports: FastAPI binds to `127.0.0.1` by default, preventing external network exposure.
