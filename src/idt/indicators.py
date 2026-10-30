"""Technical indicators on OHLCV DataFrames indexed by IST timestamps."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .market import IST, at


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return out.mask((loss == 0) & gain.notna(), 100.0)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def vwap(df: pd.DataFrame) -> pd.Series:
    """Session VWAP, reset daily. Returns NaN when volume is absent (spot indices have none)."""
    if df.empty or df["volume"].sum() == 0:
        return pd.Series(np.nan, index=df.index)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.date
    pv = (tp * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol.replace(0, np.nan)


def session(df: pd.DataFrame, day: date) -> pd.DataFrame:
    return df[df.index.date == day]


def sessions(df: pd.DataFrame) -> list[date]:
    return sorted(set(df.index.date))


def opening_range(df: pd.DataFrame, day: date, minutes: int = 15) -> dict | None:
    """High/low of bars starting in [09:15, 09:15+minutes)."""
    start = at(day, "09:15")
    bars = df[(df.index >= start) & (df.index < start + timedelta(minutes=minutes))]
    if bars.empty:
        return None
    hi, lo = float(bars["high"].max()), float(bars["low"].min())
    return {"high": hi, "low": lo, "mid": round((hi + lo) / 2, 2), "width": round(hi - lo, 2),
            "end": (start + timedelta(minutes=minutes)).isoformat()}


def prev_day_levels(daily: pd.DataFrame, day: date) -> dict | None:
    prior = daily[daily.index.date < day]
    if prior.empty:
        return None
    row = prior.iloc[-1]
    return {"date": prior.index[-1].date().isoformat(), "high": float(row["high"]),
            "low": float(row["low"]), "close": float(row["close"])}


def cpr(high: float, low: float, close: float) -> dict:
    """Central pivot range and classic floor pivots from the previous session."""
    pivot = (high + low + close) / 3
    bc = (high + low) / 2
    tc = 2 * pivot - bc
    rng = high - low
    out = {"pivot": pivot, "bc": min(bc, tc), "tc": max(bc, tc),
           "r1": 2 * pivot - low, "s1": 2 * pivot - high,
           "r2": pivot + rng, "s2": pivot - rng,
           "r3": high + 2 * (pivot - low), "s3": low - 2 * (high - pivot)}
    out["width_pct"] = (out["tc"] - out["bc"]) / pivot * 100
    return {k: round(v, 2) for k, v in out.items()}


def daily_from_intraday(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    grouped = df.groupby(df.index.date)
    daily = pd.DataFrame({"open": grouped["open"].first(), "high": grouped["high"].max(),
                          "low": grouped["low"].min(), "close": grouped["close"].last(),
                          "volume": grouped["volume"].sum(), "oi": grouped["oi"].last()})
    daily.index = pd.DatetimeIndex([at(d, "09:15") for d in daily.index]).tz_convert(IST)
    return daily
