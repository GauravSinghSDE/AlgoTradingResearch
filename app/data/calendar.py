"""
NSE (National Stock Exchange of India) Trading Calendar & Session Manager.
Enforces Indian market hours (09:15 - 15:30 IST) and distinguishes market closures from data gaps.
"""

from __future__ import annotations

import zoneinfo
from datetime import date, datetime, time, timedelta

IST = zoneinfo.ZoneInfo("Asia/Kolkata")

MARKET_OPEN_TIME = time(9, 15)
MARKET_CLOSE_TIME = time(15, 30)

# Official NSE Holidays (2024 & 2025 standard observed holidays)
NSE_HOLIDAYS: set[date] = {
    # 2024 Holidays
    date(2024, 1, 22),  # Special Holiday
    date(2024, 1, 26),  # Republic Day
    date(2024, 3, 8),  # Maha Shivratri
    date(2024, 3, 25),  # Holi
    date(2024, 3, 29),  # Good Friday
    date(2024, 4, 11),  # Id-Ul-Fitr (Ramzan Id)
    date(2024, 4, 17),  # Shri Ram Navami
    date(2024, 5, 1),  # Maharashtra Day
    date(2024, 5, 20),  # General Elections (Mumbai)
    date(2024, 6, 17),  # Bakri Id
    date(2024, 7, 17),  # Muharram
    date(2024, 8, 15),  # Independence Day
    date(2024, 10, 2),  # Mahatma Gandhi Jayanti
    date(2024, 11, 1),  # Diwali Laxmi Pujan (Muhurat Trading only)
    date(2024, 11, 15),  # Gurunanak Jayanti
    date(2024, 11, 20),  # Maharashtra Assembly Elections
    date(2024, 12, 25),  # Christmas
    # 2025 Holidays
    date(2025, 2, 26),  # Maha Shivratri
    date(2025, 3, 14),  # Holi
    date(2025, 3, 31),  # Id-Ul-Fitr
    date(2025, 4, 10),  # Shri Mahavir Jayanti
    date(2025, 4, 14),  # Dr. Baba Saheb Ambedkar Jayanti
    date(2025, 4, 18),  # Good Friday
    date(2025, 5, 1),  # Maharashtra Day
    date(2025, 8, 15),  # Independence Day
    date(2025, 8, 27),  # Ganesh Chaturthi
    date(2025, 10, 2),  # Mahatma Gandhi Jayanti / Dussehra
    date(2025, 10, 21),  # Diwali Laxmi Pujan
    date(2025, 10, 22),  # Diwali Balipratipada
    date(2025, 11, 5),  # Prakash Gurpurb
    date(2025, 12, 25),  # Christmas
}


def is_weekend(d: date) -> bool:
    """True if Saturday (5) or Sunday (6)."""
    return d.weekday() >= 5


def is_trading_day(d: date) -> bool:
    """True if date is a regular weekday and not an exchange holiday."""
    if is_weekend(d):
        return False
    if d in NSE_HOLIDAYS:
        return False
    return True


def is_market_hours(dt: datetime) -> bool:
    """True if datetime is within standard market hours 09:15 to 15:30 IST."""
    local_dt = dt.astimezone(IST) if dt.tzinfo else dt.replace(tzinfo=IST)
    if not is_trading_day(local_dt.date()):
        return False
    t = local_dt.time()
    return MARKET_OPEN_TIME <= t < MARKET_CLOSE_TIME


def get_expected_minute_timestamps(start_date: date, end_date: date) -> list[datetime]:
    """
    Generates exact expected 1-minute candle timestamps (09:15 to 15:29 inclusive)
    for all trading days between start_date and end_date.
    Total per normal trading day: 375 candles.
    """
    expected: list[datetime] = []
    current_date = start_date

    while current_date <= end_date:
        if is_trading_day(current_date):
            session_start = datetime.combine(current_date, MARKET_OPEN_TIME, tzinfo=IST)
            for m in range(375):  # 375 minutes from 09:15 to 15:29
                expected.append(session_start + timedelta(minutes=m))
        current_date += timedelta(days=1)

    return expected
