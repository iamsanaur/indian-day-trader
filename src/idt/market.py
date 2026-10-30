"""Indian market clock, session phases and the index registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

PRE_OPEN = time(9, 0)
OPEN = time(9, 15)
CLOSE = time(15, 30)


@dataclass(frozen=True)
class IndexInfo:
    name: str
    security_id: int          # Dhan IDX_I security id
    exchange: str             # NSE | BSE
    fno_segment: str | None   # NSE_FNO | BSE_FNO | None (not tradable)
    strike_step: int


# Lot sizes and expiry days are deliberately absent: they are revised by the exchanges and are
# read from the live instrument master and expiry list instead.
INDICES: dict[str, IndexInfo] = {
    "NIFTY": IndexInfo("NIFTY", 13, "NSE", "NSE_FNO", 50),
    "BANKNIFTY": IndexInfo("BANKNIFTY", 25, "NSE", "NSE_FNO", 100),
    "FINNIFTY": IndexInfo("FINNIFTY", 27, "NSE", "NSE_FNO", 50),
    "MIDCPNIFTY": IndexInfo("MIDCPNIFTY", 442, "NSE", "NSE_FNO", 25),
    "SENSEX": IndexInfo("SENSEX", 51, "BSE", "BSE_FNO", 100),
    "BANKEX": IndexInfo("BANKEX", 69, "BSE", "BSE_FNO", 100),
    "INDIAVIX": IndexInfo("INDIAVIX", 21, "NSE", None, 1),
}

ALIASES = {"NIFTY50": "NIFTY", "NIFTY 50": "NIFTY", "NIFTYBANK": "BANKNIFTY", "BANK NIFTY": "BANKNIFTY",
           "INDIA VIX": "INDIAVIX", "VIX": "INDIAVIX", "MIDCAP": "MIDCPNIFTY"}


def index_info(name: str, overrides: dict | None = None) -> IndexInfo | None:
    key = ALIASES.get(name.upper(), name.upper())
    info = INDICES.get(key)
    if info and overrides and key in overrides:
        info = IndexInfo(info.name, int(overrides[key]), info.exchange, info.fno_segment, info.strike_step)
    return info


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_hhmm(text: str) -> time:
    hh, mm = text.split(":")
    return time(int(hh), int(mm))


def at(day: date, hhmm: str | time) -> datetime:
    t = parse_hhmm(hhmm) if isinstance(hhmm, str) else hhmm
    return datetime.combine(day, t, tzinfo=IST)


def is_trading_day(day: date, holidays: list[str] | None = None) -> bool:
    return day.weekday() < 5 and day.isoformat() not in set(holidays or [])


def phase(moment: datetime, holidays: list[str] | None = None) -> str:
    moment = moment.astimezone(IST)
    if not is_trading_day(moment.date(), holidays):
        return "holiday"
    t = moment.time()
    if t < PRE_OPEN:
        return "before-open"
    if t < OPEN:
        return "pre-open"
    if t < CLOSE:
        return "open"
    return "closed"


def previous_trading_day(day: date, holidays: list[str] | None = None) -> date:
    day -= timedelta(days=1)
    while not is_trading_day(day, holidays):
        day -= timedelta(days=1)
    return day


def years_to_expiry(expiry: date, moment: datetime) -> float:
    """Calendar-time to the 15:30 IST expiry, in years (floored at ~1 minute)."""
    end = at(expiry, CLOSE)
    seconds = (end - moment.astimezone(IST)).total_seconds()
    return max(seconds, 60.0) / (365.0 * 24 * 3600)


def to_ist(ts: float | int) -> datetime:
    return datetime.fromtimestamp(float(ts), IST)
