"""Provider-neutral market data types and the MarketData protocol."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from ..market import IST

CANDLE_COLUMNS = ["open", "high", "low", "close", "volume", "oi"]


class DataError(RuntimeError):
    """Raised for provider errors with a message meant for the user."""


@dataclass
class Instrument:
    symbol: str                    # human symbol, e.g. NIFTY, RELIANCE, "NIFTY 2026-11-03 26000 CE"
    security_id: str
    exchange_segment: str          # IDX_I, NSE_EQ, NSE_FNO, BSE_EQ, BSE_FNO
    instrument: str                # INDEX, EQUITY, FUTIDX, OPTIDX, FUTSTK, OPTSTK
    lot_size: int = 1
    tick_size: float = 0.05
    trading_symbol: str = ""
    underlying: str | None = None
    expiry: date | None = None
    strike: float | None = None
    option_type: str | None = None  # CE | PE

    @property
    def exchange(self) -> str:
        return "BSE" if self.exchange_segment.startswith("BSE") or self.symbol in ("SENSEX", "BANKEX") else "NSE"

    @property
    def is_option(self) -> bool:
        return self.option_type in ("CE", "PE")

    @property
    def is_future(self) -> bool:
        return self.instrument.startswith("FUT")


@dataclass
class Quote:
    symbol: str
    ltp: float
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0             # previous close
    ts: datetime | None = None

    @property
    def change_pct(self) -> float:
        return (self.ltp / self.close - 1) * 100 if self.close else 0.0


@dataclass
class OptionQuote:
    ltp: float
    iv: float                      # percent, as published (e.g. 13.4)
    oi: int
    prev_oi: int
    volume: int
    prev_close: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    security_id: str = ""

    @property
    def oi_change(self) -> int:
        return self.oi - self.prev_oi

    @property
    def price_change(self) -> float:
        return self.ltp - self.prev_close if self.prev_close else 0.0


@dataclass
class ChainRow:
    strike: float
    ce: OptionQuote | None
    pe: OptionQuote | None


@dataclass
class OptionChain:
    underlying: str
    expiry: date
    spot: float
    rows: list[ChainRow] = field(default_factory=list)
    ts: datetime | None = None

    def row(self, strike: float) -> ChainRow | None:
        return next((r for r in self.rows if abs(r.strike - strike) < 1e-6), None)

    def strikes(self) -> list[float]:
        return [r.strike for r in self.rows]

    def atm(self) -> float:
        return min(self.strikes(), key=lambda k: abs(k - self.spot))

    def to_dict(self) -> dict:
        return asdict(self)


class MarketData(Protocol):
    def candles(self, symbol: str, interval: int | str, start: date, end: date) -> pd.DataFrame: ...
    def quote(self, symbols: list[str]) -> dict[str, Quote]: ...
    def expiries(self, underlying: str) -> list[date]: ...
    def option_chain(self, underlying: str, expiry: date) -> OptionChain: ...
    def funds(self) -> dict: ...
    def margin(self, legs: list[dict]) -> dict: ...
    def instrument(self, symbol: str) -> Instrument: ...


# --- Dhan payload parsing (shared by the live adapter and the fixture adapter) ---

def parse_candles(payload: dict) -> pd.DataFrame:
    """Dhan returns parallel arrays keyed open/high/low/close/volume/timestamp/open_interest."""
    data = payload.get("data", payload)
    ts = data.get("timestamp") or []
    if not ts:
        return pd.DataFrame(columns=CANDLE_COLUMNS, index=pd.DatetimeIndex([], tz=IST))
    frame = pd.DataFrame({
        "open": data["open"], "high": data["high"], "low": data["low"], "close": data["close"],
        "volume": data.get("volume") or [0] * len(ts),
        "oi": data.get("open_interest") or [0] * len(ts),
    }, index=pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST))
    frame.index.name = "time"
    return frame.astype(float).sort_index()


def _opt(raw: dict | None) -> OptionQuote | None:
    if not raw:
        return None
    greeks = raw.get("greeks") or {}
    return OptionQuote(
        ltp=float(raw.get("last_price") or 0), iv=float(raw.get("implied_volatility") or 0),
        oi=int(raw.get("oi") or 0), prev_oi=int(raw.get("previous_oi") or 0),
        volume=int(raw.get("volume") or 0), prev_close=float(raw.get("previous_close_price") or 0),
        delta=float(greeks.get("delta") or 0), gamma=float(greeks.get("gamma") or 0),
        theta=float(greeks.get("theta") or 0), vega=float(greeks.get("vega") or 0),
        bid=float(raw.get("top_bid_price") or 0), ask=float(raw.get("top_ask_price") or 0),
        security_id=str(raw.get("security_id") or ""),
    )


def parse_chain(payload: dict, underlying: str, expiry: date, ts: datetime | None = None) -> OptionChain:
    data = payload.get("data", payload)
    rows = [ChainRow(float(k), _opt(v.get("ce")), _opt(v.get("pe"))) for k, v in (data.get("oc") or {}).items()]
    rows.sort(key=lambda r: r.strike)
    return OptionChain(underlying, expiry, float(data.get("last_price") or 0), rows, ts)
