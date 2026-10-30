"""Chart scanner: opening-range breakouts (intraday), bull flags and oversold bounces (daily)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from . import entry as entry_mod
from . import indicators as ind


def rvol(df5: pd.DataFrame, day: date, until: datetime) -> float | None:
    """Volume so far today vs the average over the same window of prior sessions."""
    if df5["volume"].sum() == 0:
        return None
    window = lambda d: df5[(df5.index.date == d) & (df5.index.time < until.time())]["volume"].sum()
    prior = [window(d) for d in ind.sessions(df5) if d < day][-10:]
    avg = sum(prior) / len(prior) if prior else 0
    return round(window(day) / avg, 2) if avg else None


def orb(symbol: str, df5: pd.DataFrame, now: datetime, cfg: dict) -> dict | None:
    res = entry_mod.check(df5, now, "orb", or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"])
    if res["state"] != "triggered":
        return None
    rng = res["range"]
    return {"symbol": symbol, "setup": "orb", "side": res["side"], "entry": res["entry"], "trigger_time": res["trigger_time"],
            "range": rng, "range_pct": round(rng["width"] / rng["mid"] * 100, 2), "rvol": rvol(df5, now.date(), now)}


def bull_flag(symbol: str, daily: pd.DataFrame, pole_pct: float = 6.0, max_flag_days: int = 8) -> dict | None:
    if len(daily) < 30:
        return None
    close = daily["close"]
    for flag_days in range(3, max_flag_days + 1):
        flag = daily.iloc[-flag_days:]
        pole = daily.iloc[-flag_days - 6:-flag_days]
        if len(pole) < 6:
            continue
        pole_gain = (pole["close"].iloc[-1] / pole["low"].min() - 1) * 100
        if pole_gain < pole_pct:
            continue
        pole_top = pole["high"].max()
        flag_range = flag["high"].max() - flag["low"].min()
        retrace = (pole_top - flag["low"].min()) / (pole_top - pole["low"].min())
        vol_ok = flag["volume"].mean() < pole["volume"].mean() if daily["volume"].sum() else True
        above_ema = close.iloc[-1] > ind.ema(close, 20).iloc[-1]
        if retrace <= 0.5 and flag_range <= 0.6 * (pole_top - pole["low"].min()) and vol_ok and above_ema:
            pivot = float(flag["high"].max())
            return {"symbol": symbol, "setup": "flag", "side": "long", "pole_pct": round(pole_gain, 1),
                    "flag_days": flag_days, "retrace_pct": round(retrace * 100, 1), "trigger": pivot,
                    "stop_hint": float(flag["low"].min()), "close": float(close.iloc[-1])}
    return None


def oversold_bounce(symbol: str, daily: pd.DataFrame, level: float = 30.0) -> dict | None:
    if len(daily) < 30:
        return None
    r = ind.rsi(daily["close"], 14)
    last, prev = daily.iloc[-1], daily.iloc[-2]
    was_oversold = (r.iloc[-3:-1] < level).any()
    reversal = last["close"] > prev["high"] or (last["close"] > last["open"] and r.iloc[-1] > r.iloc[-2])
    if was_oversold and reversal:
        return {"symbol": symbol, "setup": "bounce", "side": "long", "rsi": round(float(r.iloc[-1]), 1),
                "rsi_prev": round(float(r.iloc[-2]), 1), "trigger": float(last["high"]), "stop_hint": float(daily["low"].iloc[-3:].min()),
                "close": float(last["close"]), "above_200sma": bool(last["close"] > ind.sma(daily["close"], 200).iloc[-1])
                if len(daily) >= 200 else None}
    return None


def rank(results: list[dict]) -> list[dict]:
    key = lambda r: (r.get("rvol") or 0, -(r.get("range_pct") or 0), r.get("pole_pct") or 0, -(r.get("rsi") or 100))
    return sorted(results, key=key, reverse=True)


def lookback(day: date, days: int) -> date:
    return day - timedelta(days=days)
