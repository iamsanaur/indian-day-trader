"""Entry timer: reports waiting / triggered / expired bar by bar on completed bars only."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from . import indicators as ind
from .market import at

BAR_MINUTES = 5


def _completed(df: pd.DataFrame, now: datetime, bar_minutes: int) -> pd.DataFrame:
    return df[df.index + timedelta(minutes=bar_minutes) <= now]


def check(df: pd.DataFrame, now: datetime, setup: str = "orb", *, day: date | None = None,
          or_minutes: int = 15, expire: str = "11:30", allow_short: bool = True,
          above: float | None = None, below: float | None = None, prev: dict | None = None,
          bar_minutes: int = BAR_MINUTES) -> dict:
    """df: intraday bars (bar_minutes) containing `day`. Returns state + trigger details.

    setups:
      orb    close beyond the opening range (09:15 + or_minutes)
      pdh    close beyond the previous day's high (long) / low (short); needs `prev`
      level  close above `above` (long) or below `below` (short)
    """
    day = day or now.date()
    bars = _completed(ind.session(df, day), now, bar_minutes)
    expiry = at(day, expire)
    out: dict = {"setup": setup, "day": day.isoformat(), "as_of": now.isoformat()}

    if setup == "orb":
        rng = ind.opening_range(df, day, or_minutes)
        if rng is None or now < at(day, "09:15") + timedelta(minutes=or_minutes):
            return dict(out, state="waiting", detail=f"building the {or_minutes}-minute opening range", range=rng)
        out["range"] = rng
        up, down = rng["high"], rng["low"]
        bars = bars[bars.index >= at(day, "09:15") + timedelta(minutes=or_minutes)]
    elif setup == "pdh":
        if not prev:
            raise ValueError("pdh setup needs previous-day levels")
        up, down = prev["high"], prev["low"]
        out["levels"] = prev
    elif setup == "level":
        if above is None and below is None:
            raise ValueError("level setup needs --above and/or --below")
        up, down = above, below
    else:
        raise ValueError(f"unknown setup {setup}")

    for ts, bar in bars.iterrows():
        if ts >= expiry:
            break
        if up is not None and bar["close"] > up:
            return dict(out, state="triggered", side="long", trigger_time=ts.isoformat(), entry=float(bar["close"]),
                        trigger_level=up, detail=f"{bar_minutes}m close {bar['close']:.2f} > {up:.2f}")
        if allow_short and down is not None and bar["close"] < down:
            return dict(out, state="triggered", side="short", trigger_time=ts.isoformat(), entry=float(bar["close"]),
                        trigger_level=down, detail=f"{bar_minutes}m close {bar['close']:.2f} < {down:.2f}")
    if now >= expiry:
        return dict(out, state="expired", detail=f"no trigger before {expire}")
    last = float(bars["close"].iloc[-1]) if not bars.empty else None
    return dict(out, state="waiting", last=last, detail=f"watching for a close beyond {down} / {up}")
