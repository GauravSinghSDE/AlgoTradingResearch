# Strategy Guide & Evaluation Methodology

This guide explains how strategies are defined, backtested, and evaluated in **AlgoTradingResearch**.

---

## 1. Zero Look-Ahead Bias Guarantee

Look-ahead bias is the most common reason why algorithmic trading strategies look profitable on paper but fail in real trading. 

### Mandatory Rules Enforced by the Backtesting Engine:
1. **Candle Completion Before Signal:** A strategy receives candle $T$ only after candle $T$ has closed. It can never inspect candle $T+1$ while making a decision.
2. **Next-Candle Execution:** When a signal is generated at the close of candle $T$, the execution fill occurs at the **Open of candle $T+1$** (plus configured slippage). It is never filled at candle $T$'s close unless using an explicit realistic intrabar execution model.
3. **No Future Contract Knowledge:** When selecting historical options or futures contracts, contract selection algorithms use only information known at timestamp $T$ (e.g., current spot price, historical volatility, and contract days-to-expiry).
4. **Independent Risk Evaluation:** Risk limits (maximum daily loss, position count, capital caps) are verified before an order is placed. The strategy cannot override risk boundaries.

---

## 2. Indian Derivatives Realities (F&O)

### Real-Money Capital Constraints (Starting ₹25,000 INR)
- **Futures Margin:** NSE NIFTY futures contract value is typically ₹24,000 $\times 25 \approx ₹6,00,000$. Span + Exposure margin requirement is ~₹1,20,000+. Therefore, naked intraday or positional futures cannot be traded with ₹25,000 capital in live markets. The platform correctly computes and rejects trades when required margin exceeds available free cash.
- **Options Buying:** Buying 1 lot of NIFTY option (e.g., premium ₹100, lot size 25) requires ₹2,500 premium. This fits within a ₹25,000 account.
- **Lot Sizes:**
  - NIFTY lot size: 25 (or historical lot size 50/75 depending on the era). The engine reads the exact historical `lot_size` directly from the instrument metadata!
  - BANKNIFTY lot size: 15 / 30.
- **Expiry Conventions:**
  - Weekly and Monthly expiries expire on Thursdays (or Wednesdays for certain indices/dates).
  - Trading concludes at 15:30 IST on expiry day, after which in-the-money (ITM) options are cash-settled against the final underlying settlement price.

---

## 3. Transaction Costs Model (Indian Markets)

The cost engine (`app/backtesting/costs.py`) supports detailed Indian statutory and brokerage charges:

| Component | Standard Rate (NSE Equity Futures) | Standard Rate (NSE Equity Options) |
|---|---|---|
| **Brokerage** | ₹20 per executed order (or 0.05% whichever is lower) | ₹20 per executed order flat |
| **STT / CTT** | 0.02% on sell turnover | 0.1% on sell option premium (effective Oct 2024 revised rates) |
| **Exchange Turnover Charges** | 0.0019% | 0.05% on premium turnover |
| **GST** | 18% on (Brokerage + Exchange charges + SEBI charges) | 18% on (Brokerage + Exchange charges + SEBI charges) |
| **SEBI Turnover Charges** | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) |
| **Stamp Duty** | 0.002% on buy turnover | 0.003% on buy premium |
| **Slippage** | Configurable (default 0.5 - 1.0 point for NIFTY) | Configurable |

---

## 4. Strategy Architecture

All strategies inherit from `BaseStrategy`:
```python
class BaseStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config

    @abstractmethod
    def on_candle(self, candle: Candle, portfolio: PortfolioState) -> list[Signal]:
        """Called deterministically on each completed candle."""
        pass
```

Signals return structured intents:
- `BUY` / `SELL`
- Instrument key or derivative selector rule
- Target & Stop-loss points
- Time-in-force
