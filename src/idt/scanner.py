"""Chart scanner: opening-range breakouts (intraday) and daily setups.

Daily setups, on completed daily bars (run before 09:15 or after 15:30):
  breakout   last close above every close of the 20 sessions before it   (original: breakout_20d)
  flag       pole of 6%+ then a tight 3-8 day flag on lower volume, above EMA20
  reclaim    the close before was under its 20-day average, the last close is above it
  oversold   RSI(14, Wilder) under 30
  bounce     RSI(14) under 30 in the prior two sessions, then a reversal close
A hit matched a rule. It is not a recommendation, and a setup on a chart is not a prediction.
"""

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
    res = entry_mod.check(df5, now, "orb", or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"],
                          no_entries_before=cfg.get("no_entries_before"), min_volume_x=cfg.get("min_volume_x"))
    if res["state"] != "triggered":
        return None
    rng = res["range"]
    sign = 1 if res["side"] == "long" else -1
    return {"symbol": symbol, "setup": "orb", "side": res["side"], "entry": res["entry"], "trigger_time": res["trigger_time"],
            "trigger_close": res["trigger_close"], "minutes_since": res["minutes_since"], "last": res["last"],
            "moved_since_pct": round(sign * (res["last"] / res["entry"] - 1) * 100, 2),
            "pct_beyond": res["pct_beyond"], "range": rng, "range_pct": round(rng["width"] / rng["mid"] * 100, 2),
            "rvol": rvol(df5, now.date(), now)}


def liquid(daily: pd.DataFrame, min_price: float, min_turnover_cr: float) -> tuple[bool, str]:
    """Price floor and 20-session average traded value (close x volume) in Rs crore. Indices have no volume."""
    if daily.empty:
        return False, "no daily bars"
    last = float(daily["close"].iloc[-1])
    if daily["volume"].sum() == 0:
        return True, "no volume (index)"
    turnover = float((daily["close"] * daily["volume"]).iloc[-20:].mean()) / 1e7
    if last < min_price:
        return False, f"price {last:.2f} under Rs {min_price:g}"
    if turnover < min_turnover_cr:
        return False, f"average traded value Rs {turnover:.1f} cr under Rs {min_turnover_cr:g} cr"
    return True, f"Rs {turnover:.0f} cr a day"


def _turnover(daily: pd.DataFrame) -> float:
    return round(float((daily["close"] * daily["volume"]).iloc[-20:].mean()) / 1e7, 1) if daily["volume"].sum() else 0.0


def breakout(symbol: str, daily: pd.DataFrame, n: int = 20) -> dict | None:
    if len(daily) < n + 1:
        return None
    close = daily["close"]
    prior = float(close.iloc[-n - 1:-1].max())
    last = float(close.iloc[-1])
    if last > prior:
        return {"symbol": symbol, "setup": "breakout", "side": "long", "close": last, "prior_high_close": prior,
                "pct_over": round((last / prior - 1) * 100, 2), "trigger": float(daily["high"].iloc[-1]),
                "stop_hint": float(daily["low"].iloc[-1]), "turnover_cr": _turnover(daily)}
    return None


def reclaim(symbol: str, daily: pd.DataFrame, n: int = 20) -> dict | None:
    if len(daily) < n + 1:
        return None
    ma = ind.sma(daily["close"], n)
    prev_c, last_c = float(daily["close"].iloc[-2]), float(daily["close"].iloc[-1])
    if prev_c < ma.iloc[-2] and last_c > ma.iloc[-1]:
        return {"symbol": symbol, "setup": "reclaim", "side": "long", "close": last_c, "ma20": round(float(ma.iloc[-1]), 2),
                "pct_over": round((last_c / ma.iloc[-1] - 1) * 100, 2), "trigger": float(daily["high"].iloc[-1]),
                "stop_hint": float(daily["low"].iloc[-1]), "turnover_cr": _turnover(daily)}
    return None


def oversold(symbol: str, daily: pd.DataFrame, level: float = 30.0) -> dict | None:
    if len(daily) < 30:
        return None
    r = ind.rsi(daily["close"], 14)
    if r.iloc[-1] < level:
        return {"symbol": symbol, "setup": "oversold", "side": "long", "rsi": round(float(r.iloc[-1]), 1),
                "close": float(daily["close"].iloc[-1]), "turnover_cr": _turnover(daily),
                "note": "oversold is a condition, not an entry: wait for a bounce or an intraday trigger"}
    return None


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
                    "stop_hint": float(flag["low"].min()), "close": float(close.iloc[-1]), "turnover_cr": _turnover(daily)}
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
                "close": float(last["close"]), "turnover_cr": _turnover(daily), "above_200sma": bool(last["close"] > ind.sma(daily["close"], 200).iloc[-1])
                if len(daily) >= 200 else None}
    return None


DAILY = {"breakout": breakout, "flag": bull_flag, "reclaim": reclaim, "oversold": oversold, "bounce": oversold_bounce}


def rank(results: list[dict]) -> list[dict]:
    """ORB: higher relative volume first, then the freshest trigger. Daily: most traded first (as the original)."""
    key = lambda r: (r.get("rvol") or 0, -(r.get("minutes_since") or 0), r.get("turnover_cr") or 0,
                     r.get("pole_pct") or 0, -(r.get("rsi") or 100))
    return sorted(results, key=key, reverse=True)


def lookback(day: date, days: int) -> date:
    return day - timedelta(days=days)
