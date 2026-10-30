"""Offline adapter reading recorded Dhan-format JSON. Used by tests and `IDT_FIXTURES=... idt ...` demos.

Layout:
  scrip-master.csv
  candles/<SYMBOL>_<interval>.json      Dhan charts payload (spaces in symbol -> _)
  chains/<UNDERLYING>_<YYYY-MM-DD>.json Dhan optionchain payload
  expiries/<UNDERLYING>.json            {"data": ["YYYY-MM-DD", ...]}
  quotes.json                           {"SYMBOL": {"ltp":..,"open":..,"high":..,"low":..,"close":..,"ts":"iso"}}
  funds.json, margin.json, nse/*.json
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..market import IST, index_info
from .base import DataError, Instrument, OptionChain, Quote, parse_candles, parse_chain
from .instruments import Instruments


def _key(symbol: str) -> str:
    return symbol.upper().replace(" ", "_").replace(":", "_")


class FixtureData:
    def __init__(self, root: Path | str, index_overrides: dict | None = None):
        self.root = Path(root)
        self.instruments = Instruments.from_csv(self.root / "scrip-master.csv", index_overrides)

    def _json(self, rel: str):
        path = self.root / rel
        if not path.exists():
            raise DataError(f"fixture missing: {path}")
        return json.loads(path.read_text())

    def instrument(self, symbol: str) -> Instrument:
        return self.instruments.resolve(symbol)

    def candles(self, symbol: str, interval: int | str, start: date, end: date) -> pd.DataFrame:
        frame = parse_candles(self._json(f"candles/{_key(symbol)}_{str(interval).upper()}.json"))
        days = frame.index.date
        return frame[(days >= start) & (days <= end)]

    def quote(self, symbols: list[str]) -> dict[str, Quote]:
        raw = self._json("quotes.json")
        out = {}
        for s in symbols:
            q = raw.get(s.upper())
            if q:
                ts = datetime.fromisoformat(q["ts"]) if q.get("ts") else None
                out[s] = Quote(s, q["ltp"], q.get("open", 0), q.get("high", 0), q.get("low", 0), q.get("close", 0), ts)
        return out

    def expiries(self, underlying: str) -> list[date]:
        return sorted(date.fromisoformat(d) for d in self._json(f"expiries/{_key(underlying)}.json")["data"])

    def option_chain(self, underlying: str, expiry: date) -> OptionChain:
        name = index_info(underlying).name if index_info(underlying) else underlying.upper()
        payload = self._json(f"chains/{name}_{expiry.isoformat()}.json")
        ts = datetime.fromisoformat(payload["ts"]) if payload.get("ts") else datetime.now(IST)
        return parse_chain(payload, name, expiry, ts)

    def funds(self) -> dict:
        return self._json("funds.json")

    def margin(self, legs: list[dict]) -> dict:
        return self._json("margin.json")
