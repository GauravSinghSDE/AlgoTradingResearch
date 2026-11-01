"""
Unit tests for instrument models, futures, options, and Upstox dictionary parsing.
"""

from __future__ import annotations

from datetime import date

from app.domain.instruments import (
    FutureContract,
    InstrumentType,
    OptionContract,
    parse_upstox_contract,
)


def test_parse_upstox_future_contract():
    raw_future = {
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
        "underlying_symbol": "NIFTY",
    }
    contract = parse_upstox_contract(raw_future, is_expired=True)
    assert isinstance(contract, FutureContract)
    assert contract.trading_symbol == "NIFTY 31 OCT 24 FUT"
    assert contract.instrument_key == "NSE_FO|54452|31-10-2024"
    assert contract.lot_size == 25
    assert contract.expiry == date(2024, 10, 31)
    assert contract.is_expired is True
    assert contract.instrument_type == InstrumentType.FUTURE


def test_parse_upstox_option_contract():
    raw_option = {
        "name": "NIFTY",
        "segment": "NSE_FO",
        "exchange": "NSE",
        "expiry": "2024-10-31",
        "instrument_key": "NSE_FO|47982|31-10-2024",
        "exchange_token": "47982",
        "trading_symbol": "NIFTY 24500 CE 31 OCT 24",
        "tick_size": 5,
        "lot_size": 25,
        "instrument_type": "CE",
        "freeze_quantity": 1800,
        "underlying_key": "NSE_INDEX|Nifty 50",
        "underlying_symbol": "NIFTY",
        "strike_price": 24500.0,
        "weekly": False,
    }
    contract = parse_upstox_contract(raw_option, is_expired=True)
    assert isinstance(contract, OptionContract)
    assert contract.is_call is True
    assert contract.is_put is False
    assert contract.strike_price == 24500.0
    assert contract.lot_size == 25
    assert contract.expiry == date(2024, 10, 31)
