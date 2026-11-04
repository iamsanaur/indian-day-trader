"""Entry timer: reports waiting / triggered / expired bar by bar on completed bars only.

The rule follows the original day-trader-skill entry timer, adapted to NSE/BSE hours:
  * only a completed bar counts (a 09:35 bar is complete at 09:40); a wick beyond the level is not a trigger
  * the trigger is the FIRST completed bar that CLOSES beyond the level (a close exactly at it is not beyond)
  * no entries on a bar that closes before `no_entries_before` or after `expire`
  * optional volume check: the trigger bar needs `min_volume_x` times the opening-range bars' average volume
  * one trigger per setup per day: later closes do not reset it
"""

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
          bar_minutes: int = BAR_MINUTES, no_entries_before: str | None = None,
          min_volume_x: float | None = None) -> dict:
    """df: intraday bars (bar_minutes) containing `day`. Returns state + trigger details.

    setups:
      orb    close beyond the opening range (09:15 + or_minutes)
      pdh    close beyond the previous day's high (long) / low (short); needs `prev`
      level  close above `above` (long) or below `below` (short)
    """
    day = day or now.date()
    if or_minutes <= 0 or or_minutes % bar_minutes:
        raise ValueError(f"or_minutes must be a whole number of {bar_minutes}-minute bars")
    session_bars = ind.session(df, day)
    bars = _completed(session_bars, now, bar_minutes)
    expiry = at(day, expire)
    earliest = at(day, no_entries_before) if no_entries_before else None
    out: dict = {"setup": setup, "day": day.isoformat(), "as_of": now.isoformat(), "bars_closed": len(bars)}
    forming = session_bars[(session_bars.index <= now) & (session_bars.index + timedelta(minutes=bar_minutes) > now)]
    if not forming.empty:
        out["forming"] = {"bar_start": forming.index[0].strftime("%H:%M"), "price": float(forming["close"].iloc[0]),
                          "closes": (forming.index[0] + timedelta(minutes=bar_minutes)).strftime("%H:%M"),
                          "note": "still forming; it does not count until it closes"}

    or_bars = session_bars[(session_bars.index >= at(day, "09:15"))
                           & (session_bars.index < at(day, "09:15") + timedelta(minutes=or_minutes))]
    avg_vol = float(or_bars["volume"].mean()) if not or_bars.empty and or_bars["volume"].sum() > 0 else None

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
    if min_volume_x:
        out["min_volume_x"] = min_volume_x
        if avg_vol is None:
            out["volume_note"] = "no volume on this instrument (spot index): the volume check is skipped"

    thin: list[str] = []
    for ts, bar in bars.iterrows():
        closes_at = ts + timedelta(minutes=bar_minutes)
        if closes_at > expiry:
            break
        if earliest and closes_at < earliest:
            continue
        side = level = None
        if up is not None and bar["close"] > up:
            side, level = "long", up
        elif allow_short and down is not None and bar["close"] < down:
            side, level = "short", down
        if side is None:
            continue
        vx = float(bar["volume"]) / avg_vol if avg_vol else None
        if min_volume_x and vx is not None and vx < min_volume_x:
            thin.append(f"{ts:%H:%M} bar closed beyond {level:g} on {vx:.2f}x the opening-range volume")
            continue
        last = float(bars["close"].iloc[-1])
        minutes_since = int((now - closes_at).total_seconds() // 60)
        res = dict(out, state="triggered", side=side, trigger_time=ts.isoformat(), trigger_close=closes_at.isoformat(),
                   entry=float(bar["close"]), trigger_level=level,
                   pct_beyond=round((bar["close"] / level - 1) * 100 * (1 if side == "long" else -1), 2),
                   volume_x=round(vx, 2) if vx is not None else None, minutes_since=minutes_since,
                   last=last, detail=f"the {ts:%H:%M} bar closed {bar['close']:.2f} "
                                     f"{'above' if side == 'long' else 'below'} {level:.2f} at {closes_at:%H:%M}")
        if minutes_since > bar_minutes:
            res["late"] = (f"triggered {minutes_since} minutes ago; the last close is {last:.2f}. A late entry is a "
                           "different trade: the price, the stop distance and the odds have moved.")
        if thin:
            res["skipped_thin"] = thin
        return res

    last = float(bars["close"].iloc[-1]) if not bars.empty else None
    if thin:
        out["skipped_thin"] = thin
    if now >= expiry:
        return dict(out, state="expired", last=last, detail=f"no qualifying close beyond {down} / {up} by {expire}")
    detail = f"watching for a close beyond {down} / {up}"
    if last is not None:
        gaps = []
        if up is not None:
            gaps.append(f"{up - last:+.2f} to {up:g} ({(up / last - 1) * 100:+.2f}%)")
        if down is not None and allow_short:
            gaps.append(f"{down - last:+.2f} to {down:g} ({(down / last - 1) * 100:+.2f}%)")
        detail = f"last close {last:.2f}; " + ", ".join(gaps)
    if earliest and now < earliest:
        detail += f"; no entries before {no_entries_before}"
    return dict(out, state="waiting", last=last, detail=detail)
