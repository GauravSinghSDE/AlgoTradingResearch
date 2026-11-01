"""
Unit tests for OptionChainSelector, ATM/ITM/OTM strike calculation, and contract selection.
"""

from __future__ import annotations

from datetime import date

from app.domain.instruments import Exchange, InstrumentType, OptionContract, Segment
from app.domain.option_chain import (
    Moneyness,
    OptionChainSelector,
    calculate_atm_strike,
    calculate_target_strike,
    classify_moneyness,
    get_strike_step,
)


def _make_dummy_option(
    symbol: str,
    strike: float,
    opt_type: str,
    expiry_date: date,
    underlying: str = "NIFTY",
) -> OptionContract:
    return OptionContract(
        instrument_key=f"NSE_FO|{symbol}",
        trading_symbol=symbol,
        name=symbol,
        segment=Segment.NSE_FO,
        exchange=Exchange.NSE,
        lot_size=25 if underlying == "NIFTY" else 15,
        expiry=expiry_date,
        underlying_key=f"NSE_INDEX|{underlying}",
        underlying_symbol=underlying,
        instrument_type=InstrumentType.CALL_OPTION if opt_type == "CE" else InstrumentType.PUT_OPTION,
        strike_price=strike,
    )


def test_get_strike_step():
    assert get_strike_step("NIFTY 50") == 50.0
    assert get_strike_step("NSE_INDEX|Nifty 50") == 50.0
    assert get_strike_step("BANKNIFTY") == 100.0
    assert get_strike_step("UNKNOWN_INDEX") == 50.0


def test_calculate_atm_strike():
    assert calculate_atm_strike(24523.50, 50.0) == 24500.0
    assert calculate_atm_strike(24530.00, 50.0) == 24550.0
    assert calculate_atm_strike(51249.00, 100.0) == 51200.0
    assert calculate_atm_strike(51260.00, 100.0) == 51300.0


def test_calculate_target_strike():
    spot = 24520.0  # ATM = 24500
    # Calls
    assert calculate_target_strike(spot, "CE", offset_steps=0, strike_step=50.0) == 24500.0
    assert calculate_target_strike(spot, "CE", offset_steps=1, strike_step=50.0) == 24550.0  # OTM
    assert calculate_target_strike(spot, "CE", offset_steps=-1, strike_step=50.0) == 24450.0  # ITM

    # Puts
    assert calculate_target_strike(spot, "PE", offset_steps=0, strike_step=50.0) == 24500.0
    assert calculate_target_strike(spot, "PE", offset_steps=1, strike_step=50.0) == 24450.0  # OTM
    assert calculate_target_strike(spot, "PE", offset_steps=-1, strike_step=50.0) == 24550.0  # ITM


def test_classify_moneyness():
    spot = 24500.0
    assert classify_moneyness(24500.0, spot, "CE") == Moneyness.ATM
    assert classify_moneyness(24400.0, spot, "CE") == Moneyness.ITM
    assert classify_moneyness(24600.0, spot, "CE") == Moneyness.OTM

    assert classify_moneyness(24500.0, spot, "PE") == Moneyness.ATM
    assert classify_moneyness(24600.0, spot, "PE") == Moneyness.ITM
    assert classify_moneyness(24400.0, spot, "PE") == Moneyness.OTM


def test_option_chain_selector_resolution():
    exp1 = date(2024, 10, 24)
    exp2 = date(2024, 10, 31)

    contracts = [
        _make_dummy_option("NIFTY24O2424500CE", 24500.0, "CE", exp1),
        _make_dummy_option("NIFTY24O2424500PE", 24500.0, "PE", exp1),
        _make_dummy_option("NIFTY24O2424550CE", 24550.0, "CE", exp1),
        _make_dummy_option("NIFTY24O2424550PE", 24550.0, "PE", exp1),
        _make_dummy_option("NIFTY24O3124500CE", 24500.0, "CE", exp2),
        _make_dummy_option("NIFTY24O3124500PE", 24500.0, "PE", exp2),
    ]

    selector = OptionChainSelector(contracts)

    # Expiries
    expiries = selector.get_expiries("NIFTY")
    assert expiries == [exp1, exp2]

    # Nearest expiry
    as_of = date(2024, 10, 20)
    assert selector.get_nearest_expiry("NIFTY", as_of) == exp1
    assert selector.get_nearest_expiry("NIFTY", as_of, min_days_to_expiry=5) == exp2

    # Select ATM Call for exp1
    c_ce_atm = selector.select_contract(
        underlying="NIFTY",
        spot_price=24510.0,
        option_type="CE",
        as_of_date=as_of,
        offset_steps=0,
    )
    assert c_ce_atm is not None
    assert c_ce_atm.strike_price == 24500.0
    assert c_ce_atm.expiry == exp1

    # Select OTM Call (+1 step)
    c_ce_otm = selector.select_contract(
        underlying="NIFTY",
        spot_price=24510.0,
        option_type="CE",
        as_of_date=as_of,
        offset_steps=1,
    )
    assert c_ce_otm is not None
    assert c_ce_otm.strike_price == 24550.0

    # Build chain snapshot
    snapshot = selector.build_chain_snapshot("NIFTY", exp1, 24510.0)
    assert len(snapshot) == 2  # strikes 24500 and 24550
    assert snapshot[0]["strike"] == 24500.0
    assert snapshot[0]["is_atm"] is True
    assert snapshot[0]["ce_moneyness"] == "ATM"
