"""
SQLAlchemy relational models for backtests, trades, data provenance logs, and paper orders.
Supports SQLite and PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.session import Base


class BacktestRecord(Base):
    """Stores metadata and summary metrics for executed backtests."""
    __tablename__ = "backtest_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    strategy_name: Mapped[str] = mapped_column(String(100), index=True)
    instrument_key: Mapped[str] = mapped_column(String(100), index=True)
    interval: Mapped[str] = mapped_column(String(20), default="1minute")
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    initial_capital: Mapped[float] = mapped_column(Float, default=25000.0)
    final_equity: Mapped[float] = mapped_column(Float, default=25000.0)
    net_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    gross_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_costs: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate_pct: Mapped[float] = mapped_column(Float, default=0.0)
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship to individual trades
    trades: Mapped[list[TradeRecordModel]] = relationship(
        "TradeRecordModel", back_populates="backtest", cascade="all, delete-orphan"
    )


class TradeRecordModel(Base):
    """Stores individual closed trades belonging to a backtest."""
    __tablename__ = "trade_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    backtest_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("backtest_records.id", ondelete="CASCADE"), index=True
    )
    instrument_key: Mapped[str] = mapped_column(String(100), index=True)
    trading_symbol: Mapped[str] = mapped_column(String(100))
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    entry_time: Mapped[datetime] = mapped_column(DateTime)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_time: Mapped[datetime] = mapped_column(DateTime)
    exit_price: Mapped[float] = mapped_column(Float)
    gross_pnl: Mapped[float] = mapped_column(Float)
    net_pnl: Mapped[float] = mapped_column(Float)
    total_costs: Mapped[float] = mapped_column(Float)
    return_pct: Mapped[float] = mapped_column(Float)
    exit_reason: Mapped[str] = mapped_column(String(100), default="SIGNAL")

    backtest: Mapped[BacktestRecord] = relationship("BacktestRecord", back_populates="trades")


class DataDownloadLog(Base):
    """Tracks market data downloads, source provenance, and quality validation results."""
    __tablename__ = "data_download_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_key: Mapped[str] = mapped_column(String(100), index=True)
    interval: Mapped[str] = mapped_column(String(20))
    from_date: Mapped[str] = mapped_column(String(10))
    to_date: Mapped[str] = mapped_column(String(10))
    total_candles: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # PASSED, WARNING, FAILED
    validation_report_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PaperOrderLog(Base):
    """Logs simulated paper orders, fills, and risk rejection reasons."""
    __tablename__ = "paper_order_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instrument_key: Mapped[str] = mapped_column(String(100), index=True)
    trading_symbol: Mapped[str] = mapped_column(String(100))
    side: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # FILLED, REJECTED
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_charges: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
