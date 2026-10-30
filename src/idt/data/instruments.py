"""Dhan scrip master: resolves human symbols to security ids, lot sizes, ticks and expiries.

Symbol grammar:
  NIFTY, BANKNIFTY, SENSEX ...          index (registry, overridable)
  RELIANCE  /  BSE:RELIANCE             cash equity (NSE by default)
  NIFTY FUT  /  NIFTY FUT 2026-11-24    nearest or given future
  NIFTY 2026-11-03 26000 CE             option
"""

from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from ..market import index_info
from .base import DataError, Instrument

SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
CACHE_TTL = 12 * 3600

_SEGMENTS = {("NSE", "E"): "NSE_EQ", ("BSE", "E"): "BSE_EQ", ("NSE", "D"): "NSE_FNO", ("BSE", "D"): "BSE_FNO",
             ("NSE", "I"): "IDX_I", ("BSE", "I"): "IDX_I"}


def _underlying_of(trading_symbol: str) -> str:
    return str(trading_symbol).split("-")[0].upper()


class Instruments:
    def __init__(self, frame: pd.DataFrame, index_overrides: dict | None = None):
        frame = frame.copy()
        frame.columns = [c.strip() for c in frame.columns]
        frame["SEM_TRADING_SYMBOL"] = frame["SEM_TRADING_SYMBOL"].astype(str).str.upper()
        frame["_und"] = frame["SEM_TRADING_SYMBOL"].map(_underlying_of)
        frame["_expiry"] = pd.to_datetime(frame.get("SEM_EXPIRY_DATE"), errors="coerce").dt.date
        self.df = frame
        self.index_overrides = index_overrides or {}

    # --- loading -------------------------------------------------------------
    @classmethod
    def load(cls, cache_dir: Path, session=None, index_overrides: dict | None = None) -> "Instruments":
        path = cache_dir / "scrip-master.csv"
        if not path.exists() or time.time() - path.stat().st_mtime > CACHE_TTL:
            import requests
            resp = (session or requests).get(SCRIP_MASTER_URL, timeout=60)
            resp.raise_for_status()
            cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
        return cls(pd.read_csv(path, low_memory=False), index_overrides)

    @classmethod
    def from_csv(cls, path: Path | str, index_overrides: dict | None = None) -> "Instruments":
        return cls(pd.read_csv(path, low_memory=False), index_overrides)

    # --- lookups -------------------------------------------------------------
    def _to_instrument(self, row: pd.Series, symbol: str) -> Instrument:
        seg = _SEGMENTS.get((row["SEM_EXM_EXCH_ID"], row["SEM_SEGMENT"]), "NSE_EQ")
        strike = float(row["SEM_STRIKE_PRICE"]) if pd.notna(row.get("SEM_STRIKE_PRICE")) and row["SEM_STRIKE_PRICE"] > 0 else None
        opt = row.get("SEM_OPTION_TYPE")
        return Instrument(
            symbol=symbol, security_id=str(int(row["SEM_SMST_SECURITY_ID"])), exchange_segment=seg,
            instrument=str(row["SEM_INSTRUMENT_NAME"]), lot_size=int(float(row.get("SEM_LOT_UNITS") or 1)),
            tick_size=float(row.get("SEM_TICK_SIZE") or 0.05) / (100 if float(row.get("SEM_TICK_SIZE") or 0) >= 5 else 1),
            trading_symbol=row["SEM_TRADING_SYMBOL"], underlying=row["_und"],
            expiry=row["_expiry"] if pd.notna(row["_expiry"]) else None, strike=strike,
            option_type=opt if opt in ("CE", "PE") else None,
        )

    def resolve(self, symbol: str) -> Instrument:
        text = " ".join(symbol.upper().split())
        exchange = "NSE"
        if ":" in text:
            exchange, text = text.split(":", 1)
        parts = text.split(" ")

        info = index_info(text, self.index_overrides)
        if info and len(parts) <= 2 and "FUT" not in parts:
            return Instrument(info.name, str(info.security_id), "IDX_I", "INDEX", lot_size=self.lot_size(info.name)
                              if info.fno_segment else 1, underlying=info.name)

        und = (index_info(parts[0]) or None)
        und_name = und.name if und else parts[0]
        deriv_exch = und.exchange if und else exchange
        d = self.df[(self.df["SEM_SEGMENT"] == "D") & (self.df["SEM_EXM_EXCH_ID"] == deriv_exch) & (self.df["_und"] == und_name)]

        if len(parts) >= 2 and parts[1] == "FUT":
            futs = d[d["SEM_INSTRUMENT_NAME"].astype(str).str.startswith("FUT")].sort_values("_expiry")
            if len(parts) >= 3:
                futs = futs[futs["_expiry"] == date.fromisoformat(parts[2])]
            else:
                futs = futs[futs["_expiry"] >= date.today()] if (futs["_expiry"] >= date.today()).any() else futs
            if futs.empty:
                raise DataError(f"No future found for {symbol}")
            return self._to_instrument(futs.iloc[0], text)

        if len(parts) == 4 and parts[3] in ("CE", "PE"):
            expiry, strike, opt = date.fromisoformat(parts[1]), float(parts[2]), parts[3]
            rows = d[(d["_expiry"] == expiry) & (d["SEM_OPTION_TYPE"] == opt) & ((d["SEM_STRIKE_PRICE"] - strike).abs() < 1e-6)]
            if rows.empty:
                raise DataError(f"No option contract {symbol} in the instrument master")
            return self._to_instrument(rows.iloc[0], text)

        eq = self.df[(self.df["SEM_SEGMENT"] == "E") & (self.df["SEM_EXM_EXCH_ID"] == exchange)
                     & (self.df["SEM_TRADING_SYMBOL"] == text)]
        if "SEM_SERIES" in eq and (eq["SEM_SERIES"] == "EQ").any():
            eq = eq[eq["SEM_SERIES"] == "EQ"]
        if eq.empty:
            raise DataError(f"Unknown symbol {symbol}. Use e.g. RELIANCE, NIFTY, 'NIFTY FUT' or 'NIFTY 2026-11-03 26000 CE'")
        return self._to_instrument(eq.iloc[0], text if exchange == "NSE" else f"{exchange}:{text}")

    def derivatives(self, underlying: str) -> pd.DataFrame:
        info = index_info(underlying)
        name = info.name if info else underlying.upper()
        return self.df[(self.df["SEM_SEGMENT"] == "D") & (self.df["_und"] == name)]

    def lot_size(self, underlying: str) -> int:
        d = self.derivatives(underlying)
        if d.empty:
            return 1
        upcoming = d[d["_expiry"] >= date.today()]
        row = (upcoming if not upcoming.empty else d).sort_values("_expiry").iloc[0]
        return int(float(row["SEM_LOT_UNITS"]))

    def option_contract(self, underlying: str, expiry: date, strike: float, opt: str) -> Instrument:
        return self.resolve(f"{underlying} {expiry.isoformat()} {strike:g} {opt}")

    def fno_stocks(self) -> list[str]:
        d = self.df[(self.df["SEM_SEGMENT"] == "D") & (self.df["SEM_INSTRUMENT_NAME"] == "OPTSTK")
                    & (self.df["SEM_EXM_EXCH_ID"] == "NSE")]
        return sorted(d["_und"].unique().tolist())

    def expiries_from_master(self, underlying: str, today: date | None = None) -> list[date]:
        today = today or datetime.now().date()
        d = self.derivatives(underlying)
        d = d[d["SEM_OPTION_TYPE"].isin(["CE", "PE"]) & (d["_expiry"] >= today)]
        return sorted(set(d["_expiry"].dropna()))
