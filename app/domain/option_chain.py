"""
Option chain modeling and contract selection helper for Indian F&O markets.
Provides ATM/ITM/OTM strike calculation, nearest-expiry resolution, and option contract matching.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import Enum
from typing import Any

from app.core.exceptions import ConfigurationError
from app.domain.instruments import InstrumentType, OptionContract


class Moneyness(str, Enum):
    """Option moneyness classification."""
    ITM = "ITM"
    ATM = "ATM"
    OTM = "OTM"


# Standard strike intervals for Indian index derivatives
DEFAULT_STRIKE_STEPS: dict[str, float] = {
    "NIFTY": 50.0,
    "BANKNIFTY": 100.0,
    "FINNIFTY": 50.0,
    "MIDCPNIFTY": 25.0,
    "SENSEX": 100.0,
    "BANKEX": 100.0,
}


def get_strike_step(underlying: str) -> float:
    """Returns the exchange-specified strike price step for an underlying."""
    cleaned = underlying.upper().replace("NSE_INDEX|", "").replace(" ", "").strip()
    # Check longer/more specific underlying names first (e.g. BANKNIFTY, FINNIFTY before NIFTY)
    for key in sorted(DEFAULT_STRIKE_STEPS.keys(), key=len, reverse=True):
        if key in cleaned:
            return DEFAULT_STRIKE_STEPS[key]
    return 50.0  # Safe default fallback for index options


def calculate_atm_strike(spot_price: float, strike_step: float = 50.0) -> float:
    """
    Computes the At-The-Money (ATM) strike price nearest to the spot price.
    E.g. Spot 24523.50 with step 50.0 -> 24500.0.
    """
    if strike_step <= 0:
        raise ConfigurationError("Strike step must be strictly positive.")
    return round(spot_price / strike_step) * strike_step


def calculate_target_strike(
    spot_price: float,
    option_type: str | InstrumentType,
    offset_steps: int = 0,
    strike_step: float = 50.0,
) -> float:
    """
    Calculates target strike price based on moneyness offset steps:
    - offset_steps = 0: ATM strike.
    - offset_steps > 0: Out-of-the-money (OTM) by N steps.
    - offset_steps < 0: In-the-money (ITM) by N steps.

    For CE: Strike = ATM + (offset_steps * step)
    For PE: Strike = ATM - (offset_steps * step)
    """
    atm = calculate_atm_strike(spot_price, strike_step)
    opt_str = (
        option_type.value
        if isinstance(option_type, InstrumentType)
        else str(option_type).upper()
    )

    if opt_str in ("CE", "CALL"):
        return atm + (offset_steps * strike_step)
    elif opt_str in ("PE", "PUT"):
        return atm - (offset_steps * strike_step)
    else:
        raise ValueError(f"Unknown option type '{option_type}', expected 'CE' or 'PE'")


def classify_moneyness(
    strike_price: float,
    spot_price: float,
    option_type: str | InstrumentType,
    strike_step: float = 50.0,
) -> Moneyness:
    """Classifies an option contract strike as ITM, ATM, or OTM relative to spot."""
    atm = calculate_atm_strike(spot_price, strike_step)
    opt_str = (
        option_type.value
        if isinstance(option_type, InstrumentType)
        else str(option_type).upper()
    )

    if abs(strike_price - atm) < 1e-4:
        return Moneyness.ATM

    if opt_str in ("CE", "CALL"):
        return Moneyness.ITM if strike_price < atm else Moneyness.OTM
    elif opt_str in ("PE", "PUT"):
        return Moneyness.ITM if strike_price > atm else Moneyness.OTM
    else:
        raise ValueError(f"Unknown option type '{option_type}'")


class OptionChainSelector:
    """
    Indexes available option contracts and selects the optimal contract
    based on underlying spot price, target expiry, option type, and moneyness.
    """

    def __init__(self, contracts: Sequence[OptionContract] | None = None) -> None:
        self._contracts: list[OptionContract] = list(contracts) if contracts else []
        self._index_contracts()

    def add_contract(self, contract: OptionContract) -> None:
        """Adds a single option contract to the catalog."""
        self._contracts.append(contract)
        self._index_contracts()

    def add_contracts(self, contracts: Sequence[OptionContract]) -> None:
        """Adds multiple option contracts to the catalog."""
        self._contracts.extend(contracts)
        self._index_contracts()

    def _index_contracts(self) -> None:
        """Builds lookup dictionaries for fast lookup."""
        self._by_underlying: dict[str, list[OptionContract]] = {}
        for c in self._contracts:
            norm_und = self._normalize_underlying(c.underlying_symbol)
            self._by_underlying.setdefault(norm_und, []).append(c)

    @staticmethod
    def _normalize_underlying(symbol: str) -> str:
        s = symbol.upper().replace("NSE_INDEX|", "").strip()
        for idx in ("NIFTY 50", "NIFTY50", "NIFTY"):
            if s.startswith(idx):
                return "NIFTY"
        for bnk in ("BANKNIFTY", "NIFTY BANK"):
            if s.startswith(bnk):
                return "BANKNIFTY"
        return s

    def get_expiries(self, underlying: str) -> list[date]:
        """Returns sorted unique expiry dates available for an underlying."""
        norm = self._normalize_underlying(underlying)
        contracts = self._by_underlying.get(norm, [])
        return sorted({c.expiry for c in contracts})

    def get_nearest_expiry(
        self,
        underlying: str,
        as_of_date: date,
        min_days_to_expiry: int = 0,
    ) -> date | None:
        """
        Finds the nearest valid expiry on or after as_of_date.
        Respects optional min_days_to_expiry to avoid immediate expiry day gamma/theta risk.
        """
        expiries = self.get_expiries(underlying)
        for exp in expiries:
            days = (exp - as_of_date).days
            if days >= min_days_to_expiry:
                return exp
        return None

    def get_contracts_for_expiry(
        self,
        underlying: str,
        expiry: date,
    ) -> list[OptionContract]:
        """Returns all contracts for a specific underlying and expiry date."""
        norm = self._normalize_underlying(underlying)
        return [c for c in self._by_underlying.get(norm, []) if c.expiry == expiry]

    def select_contract(
        self,
        underlying: str,
        spot_price: float,
        option_type: str | InstrumentType,
        as_of_date: date,
        offset_steps: int = 0,
        expiry: date | None = None,
        strike_step: float | None = None,
    ) -> OptionContract | None:
        """
        Selects the exact or closest tradable option contract.

        Parameters
        ----------
        underlying : str
            E.g. 'NIFTY' or 'BANKNIFTY'
        spot_price : float
            Current underlying spot price at decision time
        option_type : str or InstrumentType
            'CE' or 'PE'
        as_of_date : date
            Current decision date
        offset_steps : int
            0 = ATM, >0 = OTM, <0 = ITM
        expiry : date, optional
            Target expiry date. If None, resolves to nearest expiry.
        strike_step : float, optional
            Step between strikes. If None, derived from underlying default.

        Returns
        -------
        OptionContract or None if no candidate contract matches.
        """
        target_expiry = expiry or self.get_nearest_expiry(underlying, as_of_date)
        if not target_expiry:
            return None

        step = strike_step or get_strike_step(underlying)
        target_strike = calculate_target_strike(
            spot_price=spot_price,
            option_type=option_type,
            offset_steps=offset_steps,
            strike_step=step,
        )

        opt_enum = (
            option_type
            if isinstance(option_type, InstrumentType)
            else (
                InstrumentType.CALL_OPTION
                if str(option_type).upper() in ("CE", "CALL")
                else InstrumentType.PUT_OPTION
            )
        )

        candidates = [
            c
            for c in self.get_contracts_for_expiry(underlying, target_expiry)
            if c.instrument_type == opt_enum
        ]

        if not candidates:
            return None

        # Exact strike match preferred
        for c in candidates:
            if abs(c.strike_price - target_strike) < 1e-4:
                return c

        # Closest strike fallback
        return min(candidates, key=lambda c: abs(c.strike_price - target_strike))

    def build_chain_snapshot(
        self,
        underlying: str,
        expiry: date,
        spot_price: float,
    ) -> list[dict[str, Any]]:
        """
        Constructs an option chain table for an expiry with strikes,
        paired CE/PE contracts, and moneyness flags.
        """
        contracts = self.get_contracts_for_expiry(underlying, expiry)
        step = get_strike_step(underlying)
        atm = calculate_atm_strike(spot_price, step)

        strikes = sorted({c.strike_price for c in contracts})
        rows: list[dict[str, Any]] = []

        ce_by_strike = {
            c.strike_price: c for c in contracts if c.instrument_type == InstrumentType.CALL_OPTION
        }
        pe_by_strike = {
            c.strike_price: c for c in contracts if c.instrument_type == InstrumentType.PUT_OPTION
        }

        for k in strikes:
            ce = ce_by_strike.get(k)
            pe = pe_by_strike.get(k)
            rows.append({
                "strike": k,
                "is_atm": abs(k - atm) < 1e-4,
                "ce_contract": ce.instrument_key if ce else None,
                "ce_symbol": ce.trading_symbol if ce else None,
                "ce_moneyness": (
                    classify_moneyness(k, spot_price, "CE", step).value if ce else None
                ),
                "pe_contract": pe.instrument_key if pe else None,
                "pe_symbol": pe.trading_symbol if pe else None,
                "pe_moneyness": (
                    classify_moneyness(k, spot_price, "PE", step).value if pe else None
                ),
            })

        return rows
