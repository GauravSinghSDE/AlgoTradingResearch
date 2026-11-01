"""
Unit tests for relational database models, session management, and CRUD persistence.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.database import (
    BacktestRecord,
    SyncSessionLocal,
    TradeRecordModel,
    init_db,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    init_db()


def test_backtest_record_persistence():
    """Verify persisting and querying a BacktestRecord and associated TradeRecordModel."""
    with SyncSessionLocal() as session:
        # Create backtest record
        rec = BacktestRecord(
            strategy_name="test_ma_strategy",
            instrument_key="NSE_FO|NIFTY24O3124500CE",
            interval="1minute",
            initial_capital=25000.0,
            final_equity=25800.0,
            net_pnl=800.0,
            gross_pnl=950.0,
            total_costs=150.0,
            max_drawdown_pct=1.8,
            win_rate_pct=60.0,
            total_trades=5,
            profit_factor=2.1,
            parameters_json='{"fast_period": 9, "slow_period": 21}',
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)

        # Create child trade records
        trade1 = TradeRecordModel(
            backtest_id=rec.id,
            instrument_key="NSE_FO|NIFTY24O3124500CE",
            trading_symbol="NIFTY 24500 CE",
            side="BUY",
            quantity=25,
            entry_time=datetime(2024, 10, 24, 9, 30),
            entry_price=120.0,
            exit_time=datetime(2024, 10, 24, 10, 0),
            exit_price=140.0,
            gross_pnl=500.0,
            net_pnl=460.0,
            total_costs=40.0,
            return_pct=16.67,
            exit_reason="TARGET_HIT",
        )
        session.add(trade1)
        session.commit()

        # Query back and verify
        stmt = select(BacktestRecord).where(BacktestRecord.id == rec.id)
        fetched = session.scalars(stmt).first()
        assert fetched is not None
        assert fetched.strategy_name == "test_ma_strategy"
        assert fetched.net_pnl == 800.0
        assert len(fetched.trades) == 1
        assert fetched.trades[0].trading_symbol == "NIFTY 24500 CE"
        assert fetched.trades[0].gross_pnl == 500.0
