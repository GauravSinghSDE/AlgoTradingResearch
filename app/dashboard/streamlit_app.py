"""
Streamlit Research & Backtesting Dashboard for Indian Financial Markets.
AlgoTradingResearch Dashboard — Strictly Simulated / Non-Live Execution.
"""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.backtesting.engine import BacktestEngine
from app.core.config import settings
from app.data.storage import MarketDataStore
from app.domain.candles import CandleInterval
from app.domain.instruments import BaseInstrument, Exchange, Segment
from app.paper_trading.engine import PaperTradingEngine
from app.strategies.base import StrategyConfig
from app.strategies.registry import STRATEGY_REGISTRY, get_strategy_class

# Page configuration
st.set_page_config(
    page_title="AlgoTradingResearch — Indian Derivatives",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

store = MarketDataStore()
paper_engine = PaperTradingEngine()

# Top banner guardrail
st.warning(
    "⚠️ **RESEARCH & SIMULATION ENVIRONMENT**: Execution mode is locked to **BACKTEST / PAPER**. "
    "Live broker order execution is strictly disabled. No real money orders are placed."
)

st.title("AlgoTradingResearch Platform")
st.caption("Personal Algorithmic Trading Research, F&O Backtesting & Paper Trading")

# Sidebar navigation
PAGES = [
    "1. System Status & Connectivity",
    "2. Instrument & Data Explorer",
    "3. Data Quality Reports",
    "4. Strategy Configuration",
    "5. Backtest Execution",
    "6. Results & Comparison",
    "7. Equity Curve & Drawdown",
    "8. Trade Ledger",
    "9. Paper-Trading Portfolio",
    "10. Risk Settings & Rejected Trades",
]

selected_page = st.sidebar.radio("Navigation", PAGES)

# -----------------------------------------------------------------------------
# PAGE 1: System Status & Connectivity
# -----------------------------------------------------------------------------
if selected_page == "1. System Status & Connectivity":
    st.header("1. System Status & Data-Source Connectivity")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Execution Mode", settings.EXECUTION_MODE)
    col2.metric("Environment", settings.ENVIRONMENT)
    col3.metric("Starting Capital", f"₹{settings.STARTING_CAPITAL:,.2f}")
    col4.metric("Broker API", "Upstox v2 (Plus Activated)")

    st.subheader("Authentication & Broker Guardrails")
    has_token = bool(settings.UPSTOX_ACCESS_TOKEN)
    has_api_key = bool(settings.UPSTOX_API_KEY)

    st.write(f"- **API Key Configured:** {'✅ Yes' if has_api_key else '❌ Missing (.env)'}")
    st.write(
        f"- **Daily Access Token Active:** {'✅ Active (Masked)' if has_token else '⚠️ Token Missing / Daily Login Required'}"
    )
    st.write(f"- **Redirect URI:** `{settings.UPSTOX_REDIRECT_URI}`")
    st.write("- **Order Placement Endpoints:** 🛡️ *DISABLED BY ARCHITECTURE*")

    st.info(
        "To refresh daily Upstox authentication: open terminal and run `python scripts/verify_upstox_auth.py` "
        "or visit the login redirect URL."
    )

# -----------------------------------------------------------------------------
# PAGE 2: Instrument & Data Explorer
# -----------------------------------------------------------------------------
elif selected_page == "2. Instrument & Data Explorer":
    st.header("2. Instrument & Historical Data Explorer")

    available_keys = (
        [p.name for p in store.candles_dir.iterdir() if p.is_dir()]
        if store.candles_dir.exists()
        else []
    )

    if not available_keys:
        st.info("No local parquet datasets found in `./data/candles/`. Run data downloader first.")
    else:
        chosen_instrument = st.selectbox("Select Cached Instrument", available_keys)
        interval = st.selectbox("Interval", ["1minute", "day", "5minute", "15minute"])

        batch = store.load_candles(chosen_instrument, CandleInterval(interval))
        if batch and batch.count() > 0:
            df = batch.to_dataframe()
            st.metric("Total Cached Candles", len(df))
            st.dataframe(df.tail(100), use_container_width=True)

            # Candlestick chart
            fig = go.Figure(
                data=[
                    go.Candlestick(
                        x=df.index,
                        open=df["open"],
                        high=df["high"],
                        low=df["low"],
                        close=df["close"],
                        name=chosen_instrument,
                    )
                ]
            )
            fig.update_layout(
                title=f"{chosen_instrument} Price Action ({interval})",
                xaxis_rangeslider_visible=False,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data found for the selected interval.")

# -----------------------------------------------------------------------------
# PAGE 3: Data Quality Reports
# -----------------------------------------------------------------------------
elif selected_page == "3. Data Quality Reports":
    st.header("3. Historical Data Quality & Gap Reports")
    report_files = (
        list(store.reports_dir.glob("quality_*.json")) if store.reports_dir.exists() else []
    )

    if not report_files:
        st.info(
            "No data quality reports generated yet. Download historical candles to generate validation reports."
        )
    else:
        selected_report_file = st.selectbox("Select Report", [f.name for f in report_files])
        file_path = store.reports_dir / selected_report_file
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        status = data.get("status", "UNKNOWN")
        if status == "PASSED":
            st.success("Validation Status: PASSED (Zero Critical Defects)")
        elif status == "WARNING":
            st.warning("Validation Status: WARNING (Minor gaps or zero-volume bars detected)")
        else:
            st.error(f"Validation Status: {status}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Candles", data.get("total_candles", 0))
        c2.metric("Expected Candles", data.get("expected_candles_in_range", 0))
        c3.metric("Coverage %", f"{data.get('actual_coverage_pct', 0.0)}%")
        c4.metric("Missing Minutes", data.get("missing_trading_minutes_count", 0))

        st.json(data)

# -----------------------------------------------------------------------------
# PAGE 4: Strategy Configuration
# -----------------------------------------------------------------------------
elif selected_page == "4. Strategy Configuration":
    st.header("4. Strategy Parameters & Configuration")

    strategy_choice = st.selectbox("Strategy", list(STRATEGY_REGISTRY.keys()))
    st.subheader(f"Parameters for `{strategy_choice}`")

    if strategy_choice == "ma_crossover":
        fast = st.slider("Fast Period", 3, 50, 9)
        slow = st.slider("Slow Period", 10, 100, 21)
        lot_size = st.number_input("Lot Size", min_value=25, value=25, step=25)
        sl = st.number_input("Stop Loss Points", min_value=5.0, value=30.0, step=5.0)
        tp = st.number_input("Target Points", min_value=10.0, value=60.0, step=10.0)
        intraday = st.checkbox("Intraday Only (Square-off at 15:15 IST)", value=True)

        st.session_state["strategy_params"] = {
            "fast_period": fast,
            "slow_period": slow,
            "lot_size": lot_size,
            "stop_loss_points": sl,
            "target_points": tp,
            "intraday_only": intraday,
        }
    elif strategy_choice == "opening_range_breakout":
        lot_size = st.number_input("Lot Size", min_value=25, value=25, step=25)
        sl_pct = st.number_input("Stop Loss %", min_value=0.2, value=1.0, step=0.1)
        tp_pct = st.number_input("Target %", min_value=0.5, value=2.0, step=0.1)

        st.session_state["strategy_params"] = {
            "lot_size": lot_size,
            "stop_loss_pct": sl_pct,
            "target_pct": tp_pct,
        }

    st.success("Parameters saved in session state for backtest execution.")

# -----------------------------------------------------------------------------
# PAGE 5: Backtest Execution
# -----------------------------------------------------------------------------
elif selected_page == "5. Backtest Execution":
    st.header("5. Backtest Execution")

    available_keys = (
        [p.name for p in store.candles_dir.iterdir() if p.is_dir()]
        if store.candles_dir.exists()
        else []
    )

    if not available_keys:
        st.warning("Please download market data before running a backtest.")
    else:
        inst_key = st.selectbox("Instrument Key", available_keys)
        strat_key = st.selectbox("Strategy", list(STRATEGY_REGISTRY.keys()))
        capital = st.number_input("Starting Capital (₹)", value=25000.0, step=1000.0)
        slippage = st.number_input("Slippage Points", value=0.5, step=0.1)

        if st.button("🚀 Run Deterministic Backtest"):
            with st.spinner("Executing event-driven simulation (Zero Look-Ahead)..."):
                batch = store.load_candles(inst_key, CandleInterval.MINUTE_1)
                if not batch or batch.count() == 0:
                    st.error(f"No 1-minute data available for {inst_key}")
                else:
                    strat_cls = get_strategy_class(strat_key)
                    params = st.session_state.get("strategy_params", {})
                    strategy = strat_cls(config=StrategyConfig(name=strat_key, parameters=params))

                    instrument = BaseInstrument(
                        instrument_key=inst_key,
                        trading_symbol=inst_key,
                        name=inst_key,
                        segment=Segment.NSE_FO,
                        exchange=Exchange.NSE,
                        lot_size=int(params.get("lot_size", 25)),
                    )

                    engine = BacktestEngine(
                        initial_capital=capital,
                        slippage_points=slippage,
                    )
                    res = engine.run(strategy, batch, instrument)
                    st.session_state["latest_backtest"] = res
                    st.success("Backtest Completed Successfully!")

# -----------------------------------------------------------------------------
# PAGE 6: Results & Comparison
# -----------------------------------------------------------------------------
elif selected_page == "6. Results & Comparison":
    st.header("6. Backtest Results & Summary")

    res = st.session_state.get("latest_backtest")
    if not res:
        st.info("Run a backtest on Page 5 to view results.")
    else:
        m = res.metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Final Equity", f"₹{m.final_equity:,.2f}", f"{m.absolute_return_pct:+.2f}%")
        c2.metric("Net P&L", f"₹{m.net_pnl:,.2f}")
        c3.metric("Profit Factor", f"{m.profit_factor:.2f}")
        c4.metric("Max Drawdown", f"{m.max_drawdown_pct:.2f}%")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Total Trades", m.total_trades)
        c6.metric("Win Rate", f"{m.win_rate_pct:.1f}%")
        c7.metric("Avg Trade P&L", f"₹{m.average_trade_pnl:,.2f}")
        c8.metric("Total Costs", f"₹{m.total_costs:,.2f}")

        st.subheader("Monthly Returns")
        if m.monthly_returns:
            monthly_df = pd.DataFrame(
                list(m.monthly_returns.items()), columns=["Month", "Net P&L (₹)"]
            )
            st.dataframe(monthly_df, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 7: Equity Curve & Drawdown
# -----------------------------------------------------------------------------
elif selected_page == "7. Equity Curve & Drawdown":
    st.header("7. Equity Curve & Drawdown Analysis")

    res = st.session_state.get("latest_backtest")
    if not res or not res.equity_curve:
        st.info("Run a backtest on Page 5 to inspect equity curve.")
    else:
        eq_df = pd.DataFrame(res.equity_curve)
        eq_df["timestamp"] = pd.to_datetime(eq_df["timestamp"])

        fig = px.line(eq_df, x="timestamp", y="equity", title="Equity Curve (₹ INR)", markers=False)
        st.plotly_chart(fig, use_container_width=True)

        fig_dd = px.area(
            eq_df,
            x="timestamp",
            y="drawdown_pct",
            title="Drawdown (%)",
            color_discrete_sequence=["red"],
        )
        st.plotly_chart(fig_dd, use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 8: Trade Ledger
# -----------------------------------------------------------------------------
elif selected_page == "8. Trade Ledger":
    st.header("8. Trade-by-Trade Ledger")

    res = st.session_state.get("latest_backtest")
    if not res or not res.closed_trades:
        st.info("No closed trades recorded in the latest backtest run.")
    else:
        trades_data = [
            {
                "Entry Time": t.entry_timestamp.strftime("%Y-%m-%d %H:%M"),
                "Exit Time": t.exit_timestamp.strftime("%Y-%m-%d %H:%M"),
                "Side": t.side.value,
                "Qty": t.quantity,
                "Entry Price": t.entry_price,
                "Exit Price": t.exit_price,
                "Gross P&L": t.gross_pnl,
                "Costs": t.total_costs,
                "Net P&L": t.net_pnl,
                "Return %": t.return_pct,
                "Exit Reason": t.exit_reason,
            }
            for t in res.closed_trades
        ]
        st.dataframe(pd.DataFrame(trades_data), use_container_width=True)

# -----------------------------------------------------------------------------
# PAGE 9: Paper-Trading Portfolio
# -----------------------------------------------------------------------------
elif selected_page == "9. Paper-Trading Portfolio":
    st.header("9. Paper Trading Portfolio")

    p = paper_engine.portfolio
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cash Balance", f"₹{p.cash:,.2f}")
    col2.metric("Total Equity", f"₹{p.equity:,.2f}")
    col3.metric("Daily P&L", f"₹{p.daily_pnl:,.2f}")
    col4.metric("Open Positions", p.open_position_count)

    st.subheader("Kill Switch Status")
    if paper_engine.kill_switch_active:
        st.error("🚨 KILL SWITCH IS ACTIVE: All paper order placement is halted.")
        if st.button("Deactivate Kill Switch"):
            paper_engine.deactivate_kill_switch()
            st.rerun()
    else:
        st.success("Kill switch is inactive. System ready for simulated paper orders.")
        if st.button("🚨 Activate Kill Switch (Emergency Stop)"):
            paper_engine.activate_kill_switch("Manual UI button trigger")
            st.rerun()

    st.subheader("Open Positions")
    active_positions = [pos for pos in p.positions.values() if pos.is_open]
    if not active_positions:
        st.info("No open paper positions.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Instrument": pos.instrument_key,
                        "Qty": pos.quantity,
                        "Avg Entry": pos.average_entry_price,
                        "Current Price": pos.current_price,
                        "Unrealized P&L": round(pos.unrealized_pnl, 2),
                    }
                    for pos in active_positions
                ]
            ),
            use_container_width=True,
        )

# -----------------------------------------------------------------------------
# PAGE 10: Risk Settings & Rejected Trades
# -----------------------------------------------------------------------------
elif selected_page == "10. Risk Settings & Rejected Trades":
    st.header("10. Risk Settings & Rejected-Trade Log")

    st.subheader("Configured Risk Boundaries")
    r1, r2, r3 = st.columns(3)
    r1.metric("Max Risk / Trade", f"{settings.MAX_RISK_PER_TRADE_PCT}%")
    r2.metric("Daily Loss Circuit", f"{settings.MAX_DAILY_LOSS_PCT}%")
    r3.metric("Max Positions", settings.MAX_OPEN_POSITIONS)

    st.subheader("Rejected Trades in Latest Backtest")
    res = st.session_state.get("latest_backtest")
    if not res or not res.rejected_orders:
        st.info("Zero trades rejected by risk manager.")
    else:
        rejections = [
            {
                "Time": r.timestamp.strftime("%Y-%m-%d %H:%M"),
                "Instrument": r.instrument_key,
                "Side": r.side.value,
                "Qty": r.quantity,
                "Rule": r.rule_name,
                "Reason": r.reason,
            }
            for r in res.rejected_orders
        ]
        st.dataframe(pd.DataFrame(rejections), use_container_width=True)
