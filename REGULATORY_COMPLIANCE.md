# Regulatory Compliance & Legal Framework (Indian Financial Markets)

This document outlines the regulatory landscape, statutory guidelines, risk controls, and ethical boundaries governing algorithmic research and trading software interacting with Indian financial exchanges (NSE, BSE, MCX) and registered intermediaries under the purview of the **Securities and Exchange Board of India (SEBI)**.

---

## 1. Regulatory Context & SEBI Guidelines

### 1.1 SEBI Position on Retail Algorithmic Trading
Under SEBI guidelines (including circulars `SEBI/HO/MRD/DP/CIR/P/2018/62` and subsequent consultation papers on retail algorithmic trading):
1. **Exchange-Approved vs. Retail API Trading**:
   - Institutional and broker-hosted algorithmic strategies require formal audit, empanelment, and Exchange Strategy ID registration with NSE/BSE.
   - Broker APIs provided to retail investors (such as Upstox API v2) are categorized as **Direct Market Access (DMA) / Retail API feeds** intended for discretionary manual order placement or individual automation by the registered account holder.
2. **Third-Party Commercial Prohibitions**:
   - Offering automated trading services, black-box trading bots, or pool-capital execution to third parties without SEBI Research Analyst (RA), Investment Adviser (IA), or Portfolio Management Service (PMS) registration is strictly prohibited by law.
   - This platform (`AlgoTradingResearch`) is strictly designed as a **personal, private research tool** for individual research, backtesting, and paper simulation. It is **not** a multi-tenant commercial service.

### 1.2 Broker API Order Tagging
Exchanges require brokers to tag API orders distinct from terminal orders:
- Orders routed through broker APIs are tagged with specific client and source identifiers.
- Exchanges and brokers implement throttle caps (e.g., maximum requests per second, maximum orders per minute).
- Broker risk management systems (RMS) enforce real-time pre-trade risk controls (order quantity freezes, circuit limit filters, exposure margin validation).

---

## 2. Platform Safety Architecture (Zero Live Orders)

To ensure strict compliance and protect against financial exposure or regulatory breach, `AlgoTradingResearch` enforces the following hard invariants:

### 2.1 Complete Disabling of Live Order Execution
- The codebase deliberately implements **zero broker order placement methods** (no `POST /v2/order/place`, no bracket order, no modified order endpoints).
- Only two operational execution modes are permitted in configuration:
  - `EXECUTION_MODE=BACKTEST`
  - `EXECUTION_MODE=PAPER`
- Any code path that attempts live order transmission raises an uncatchable `LiveTradingDisabledError` that immediately terminates execution.
- No UI controls, buttons, or API routes exist that can toggle or authorize real-money execution.

### 2.2 Protection Against Runaway Algorithmic Loops
Runaway loops (infinite order loops caused by logic bugs or rapid message retries) are a primary reason for exchange regulatory scrutiny and broker terminal disabling. By strictly separating strategy signal generation from live broker routing:
- Signals are logged and evaluated exclusively against offline Parquet market data or local paper trading journals.
- Paper trading includes an **Emergency Kill Switch** that halts execution immediately upon detecting state discrepancies or manual trigger.

---

## 3. Derivative Market Realities & Margin Norms

### 3.1 Peak Margin and SEBI Margin Mandates
- **SPAN + Exposure Margin**: Trading index futures or writing (selling) options requires upfront margin matching exchange SPAN and exposure requirements.
  - 1 lot of NIFTY Futures (~₹6,00,000 contract value) requires approx. ₹1,20,000–₹1,40,000 margin.
  - An account with ₹25,000 starting capital **cannot legally or practically initiate futures positions or naked short options**.
- **Options Buying**:
  - Buying Call or Put options requires only the premium value (e.g., 1 lot NIFTY @ ₹120 premium = ₹3,000 cash).
  - The platform's `RiskManager` validates cash and margin prior to every order intent. If an order's cash requirement exceeds available portfolio liquidity, it is rejected with `INSUFFICIENT_CASH`.

### 3.2 Statutory Indian Transaction Costs Schedule
Realistic backtesting requires accurate modeling of statutory taxes levied under Indian law. Effective October 1, 2024, the tax schedule is modeled as follows:

| Component | Equity Intraday | Equity Delivery | Futures | Options (on Premium) |
| :--- | :--- | :--- | :--- | :--- |
| **Brokerage** | Up to ₹20 / order | Up to ₹20 / order | Up to ₹20 / order | Up to ₹20 / order |
| **STT / CTT** | 0.025% (Sell) | 0.1% (Buy & Sell) | 0.02% (Sell) | 0.1% (Sell Premium) |
| **Exchange Charges** | ~0.00297% | ~0.00297% | ~0.00173% | ~0.03503% (Premium) |
| **GST** | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) | 18% on (Brokerage + Exch + SEBI) |
| **SEBI Turnover Fee**| ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) | ₹10 per crore (0.0001%) |
| **Stamp Duty** | 0.003% (Buy) | 0.015% (Buy) | 0.002% (Buy) | 0.003% (Buy Premium) |

The `TransactionCostCalculator` in `app/backtesting/costs.py` enforces this exact statutory schedule on every simulated fill.

---

## 4. Taxation & Income Classification

Under the Indian Income Tax Act, 1961:
1. **Derivatives Trading (F&O)**:
   - Defined under **Section 43(5)** as **non-speculative business income**.
   - Profits are taxed according to the individual's or entity's applicable slab rate.
   - Legitimate trading expenses (brokerage, exchange fees, software expenses, internet, advisory costs) are tax-deductible against gross turnover/profits.
   - Net business losses can be carried forward for up to 8 consecutive assessment years, provided the tax return (ITR-3) is filed on or before the due date under Section 139(1).
2. **Equity Intraday**:
   - Treated as **speculative business income**, subject to separate loss set-off rules.

---

## 5. Transition Path to Formal Algo Certification

If an individual or quantitative firm intends to deploy live algorithmic strategies in Indian markets:
1. **Broker Partnership & Strategy Empanelment**:
   - The strategy logic must be submitted to an empanelled broker.
   - The broker conducts mock testing and functional verification in the exchange test environment.
2. **Exchange Strategy ID**:
   - The exchange (NSE/BSE) issues an alphanumeric Strategy ID upon approval.
   - Every live order sent to the exchange order book must include this Strategy ID.
3. **Annual Algorithm Audit**:
   - Algorithmic facilities and systems are subject to annual system audit by a CERT-In empanelled or CISA-certified auditor pursuant to SEBI guidelines.
4. **Colocation & Low Latency**:
   - High-frequency and low-latency algorithmic trading typically requires colocation (colo) facilities at NSE/BSE data centers.

---

## 6. Disclaimers & Limitations of Liability

> [!WARNING]
> **Financial & Market Risk Disclaimer**
> 1. Trading in financial markets, especially derivatives (Futures and Options), carries substantial financial risk, including the loss of invested capital.
> 2. Past performance in backtests or paper simulations does not guarantee future market returns. Real-world market execution involves unpredictable slippage, liquidity gaps, volatility spikes, and exchange outages.
> 3. This software is provided strictly for academic, research, and educational purposes. It does not constitute investment advice, financial advisory, portfolio management, or a solicitation to buy or sell securities.
> 4. The user assumes 100% responsibility and liability for any financial decisions, simulations, or future implementations derived from this repository.
