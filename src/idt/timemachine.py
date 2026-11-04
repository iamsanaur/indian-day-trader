"""Time Machine: simulate the plan before risking capital.

1. Monte Carlo: 10,000 sessions built by resampling 5-minute bars from the same time of day
   (plus or minus `window` bars, default 2, as in the original day-trader-skill) across the prior
   full sessions (fixed seed). Each bar keeps its open/high/low/close shape relative to the previous
   close, so intrabar stop/target touches are modelled. If stop and target are both touched in one
   bar, the stop is assumed first (the conservative call).
2. Replay: rerun the same setup rule on each prior session where it fired.
3. Verdict: the target's share of the paths that hit a side, against the share that breaks even at
   the plan's reward:risk, 1 / (1 + R): 50% at 1R, 40% at 1.5R, 33% at 2R.

Options and strategies are repriced along each path with Black-Scholes at constant IV.
A simulation from ~60 sessions of data, not a prediction.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from . import entry as entry_mod
from . import indicators as ind
from . import plan as plan_mod
from .market import at
from .strategy import legs_from_dicts, pnl_now


MIN_SESSIONS = 20      # fewer full prior sessions than this is too thin a pool to be fair
COIN_FLIP = 0.05       # verdict thresholds, in share points away from break-even
STRONG = 0.15
MANY_NEITHER = 0.40


def _slots(start: datetime, squareoff: str, bar: int = 5) -> list[str]:
    t, end, out = start, at(start.date(), squareoff), []
    while t < end:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=bar)
    return out


def _ratios(df5: pd.DataFrame, slots: list[str], max_sessions: int | None = None) -> np.ndarray:
    """(sessions, slots, 4) array of open/high/low/close divided by the previous bar's close.

    Only sessions that have every slot are kept (a missing bar means a halt or bad data), and only the
    most recent `max_sessions` of those.
    """
    prev_close = df5["close"].shift()
    rel = df5[["open", "high", "low", "close"]].div(prev_close, axis=0)
    rel["day"], rel["slot"] = df5.index.date, df5.index.strftime("%H:%M")
    out = []
    for _, g in rel.dropna().groupby("day"):
        g = g.set_index("slot").reindex(slots)
        if g[["open", "high", "low", "close"]].isna().any().any():
            continue
        out.append(g[["open", "high", "low", "close"]].to_numpy())
    if max_sessions:
        out = out[-max_sessions:]
    if len(out) < MIN_SESSIONS:
        raise ValueError(f"only {len(out)} complete prior sessions to simulate from (need {MIN_SESSIONS}); "
                         "fetch more history or check the data")
    return np.stack(out)


def lean(p_target: float, p_stop: float, r_target: float) -> tuple[float, float, float] | None:
    """(gap, share, break_even): the target's share of the paths that hit a side minus the share that
    breaks even at the target's R. None when nothing hit a side."""
    if p_target + p_stop <= 0:
        return None
    share, even = p_target / (p_target + p_stop), 1.0 / (1.0 + r_target)
    return share - even, share, even


def verdict(mc: dict) -> dict:
    """One plain line from the numbers (the original Time Machine's thresholds), plus notes under it."""
    pt, ps, r = mc["p_target"], mc["p_stop"], mc.get("r_at_target") or 1.0
    lv = lean(pt, ps, r)
    until = mc["to"][11:16]
    if lv is None:
        return {"line": f"No path reached the target or the stop by {until}: the price at {until} decides every one.",
                "notes": []}
    gap, share, even = lv
    one_r = abs(r - 1.0) < 0.005
    if abs(gap) < COIN_FLIP:
        head = "Close to a coin flip" if one_r else "Close to break-even"
    elif abs(gap) < STRONG:
        head = "Leans toward the target" if gap > 0 else "Leans toward the stop"
    else:
        head = "Strongly toward the target" if gap > 0 else "Strongly toward the stop"
    odds = f"target first {pt * 100:.1f}% vs stop first {ps * 100:.1f}%"
    line = (f"{head}: {odds}." if one_r else
            f"{head}: at {r:g}R the target has to come first in {even * 100:.0f}% of the paths that hit a side; "
            f"it did in {share * 100:.0f}% ({odds}).")
    notes = []
    if mc["p_flat"] > MANY_NEITHER:
        notes.append(f"{mc['p_flat'] * 100:.1f}% of the paths hit neither by {until}; the price at {until} decides those.")
    avg = mc.get("expected_r")
    if abs(gap) >= COIN_FLIP and avg and (avg > 0) != (gap > 0):
        notes.append(f"Average R is {avg:+.3f} all the same: the paths that hit neither pull it the other way.")
    return {"line": line, "notes": notes, "share_needed": round(even, 3), "share_got": round(share, 3),
            "gap_points": round(gap * 100, 1)}


def _instrument_value(plan: dict, s: np.ndarray, moment: datetime, r: float, anchor: float = 0.0) -> np.ndarray:
    """Per-unit P/L in rupees of the traded position at underlying prices s.

    For options, `anchor` is the model P/L at entry, subtracted so the path starts at zero
    despite bid/ask and model error in the traded premiums.
    """
    if plan["kind"] in ("equity", "future"):
        sign = 1 if plan["side"] == "long" else -1
        return sign * (s - plan["underlying_entry"]) * plan["lot_size"]
    return pnl_now(legs_from_dicts(plan["legs"]), s, moment, r, plan["lot_size"]) - anchor


def simulate(plan: dict, df5: pd.DataFrame, start: datetime, n: int = 10000, seed: int = 42, r: float = 0.065,
             window: int = 2, max_sessions: int | None = None) -> dict:
    slots = _slots(start, plan["squareoff"])
    if not slots:
        raise ValueError(f"the simulation starts at {start:%H:%M}, at or after the square-off {plan['squareoff']}: "
                         "nothing left to simulate")
    # Pool: the same time of day plus or minus `window` bars, never the 09:15 bar (it carries the overnight gap).
    first = min(start, max(at(start.date(), "09:20"), start - timedelta(minutes=5 * window)))
    last_end = min(at(start.date(), plan["squareoff"]) + timedelta(minutes=5 * window), at(start.date(), "15:30"))
    pool_slots = _slots(first, last_end.strftime("%H:%M"))
    ratios = _ratios(df5[df5.index.date < start.date()], pool_slots, max_sessions)
    rng = np.random.default_rng(seed)
    base = np.array([pool_slots.index(sl) for sl in slots])
    jitter = rng.integers(-window, window + 1, size=(n, len(slots))) if window else np.zeros((n, len(slots)), int)
    col = np.clip(base + jitter, 0, len(pool_slots) - 1)
    pick = rng.integers(0, ratios.shape[0], size=(n, len(slots)))
    bars = ratios[pick, col]                                         # (n, steps, 4)
    closes = plan["underlying_entry"] * np.cumprod(bars[:, :, 3], axis=1)
    prev = np.concatenate([np.full((n, 1), plan["underlying_entry"]), closes[:, :-1]], axis=1)
    highs, lows = prev * bars[:, :, 1], prev * bars[:, :, 2]

    anchor = 0.0
    if plan["kind"] in ("option", "strategy"):
        anchor = float(_instrument_value(plan, np.array([plan["underlying_entry"]]), start, r)[0])
    value = lambda prices, moment: _instrument_value(plan, prices, moment, r, anchor)

    outcome = np.zeros(n, dtype=int)          # 0 flat at square-off, -1 stop, +1 target
    pnl = np.full(n, np.nan)
    long_view = plan["side"] != "short"
    for j, slot in enumerate(slots):
        open_ = outcome == 0
        if not open_.any():
            break
        moment = at(start.date(), slot) + timedelta(minutes=5)
        if plan["basis"] == "underlying":
            us, ut = plan["underlying_stop"], plan["underlying_target"]
            stop_hit = (lows[:, j] <= us) if long_view else (highs[:, j] >= us)
            tgt_hit = (highs[:, j] >= ut) if long_view else (lows[:, j] <= ut)
            stop_val = value(np.full(n, us), moment)
            tgt_val = value(np.full(n, ut), moment)
        else:
            v_hi = value(highs[:, j], moment)
            v_lo = value(lows[:, j], moment)
            worst, best = np.minimum(v_hi, v_lo), np.maximum(v_hi, v_lo)
            stop_lvl = -plan["risk_per_unit"]
            tgt_lvl = plan["reward_per_unit"]
            stop_hit, tgt_hit = worst <= stop_lvl, best >= tgt_lvl
            stop_val, tgt_val = np.full(n, stop_lvl), np.full(n, tgt_lvl)
        s_now = open_ & stop_hit
        t_now = open_ & ~stop_hit & tgt_hit
        outcome[s_now], pnl[s_now] = -1, stop_val[s_now]
        outcome[t_now], pnl[t_now] = 1, tgt_val[t_now]

    flat = outcome == 0
    end = at(start.date(), plan["squareoff"])
    if flat.any():
        pnl[flat] = value(closes[flat, -1], end)
    risk = plan["risk_per_unit"]
    last = closes[:, -1]
    mc = {
        "paths": n, "seed": seed, "window": window, "sessions_sampled": int(ratios.shape[0]),
        "bars_per_path": len(slots), "from": start.isoformat(), "to": end.isoformat(),
        "p_target": round(float((outcome == 1).mean()), 4), "p_stop": round(float((outcome == -1).mean()), 4),
        "p_flat": round(float(flat.mean()), 4),
        # green: target first, or still open and in profit at square-off
        "p_green": round(float(((outcome == 1) | (flat & (pnl > 0))).mean()), 4),
        "r_at_target": round(plan["reward_per_unit"] / risk, 4) if risk else None,
        "underlying_at_squareoff": {"median": round(float(np.median(last)), 2), "p5": round(float(np.percentile(last, 5)), 2),
                                    "p95": round(float(np.percentile(last, 95)), 2)},
        "pnl_per_unit": {"mean": round(float(pnl.mean()), 2), "median": round(float(np.median(pnl)), 2),
                         "p5": round(float(np.percentile(pnl, 5)), 2), "p95": round(float(np.percentile(pnl, 95)), 2)},
        "expected_r": round(float(pnl.mean() / risk), 3) if risk else None,
    }
    mc["verdict"] = verdict(mc)
    return mc


def replay(plan: dict, df5: pd.DataFrame, before: date, cfg: dict, max_sessions: int | None = None) -> dict:
    """Rerun an ORB plan's rules on prior sessions (underlying-basis plans only). This is what really happened."""
    if plan.get("setup") != "orb" or plan["basis"] != "underlying":
        return {"skipped": "replay supports ORB plans with an underlying stop"}
    trades = []
    days = [d for d in ind.sessions(df5) if d < before]
    if max_sessions:
        days = days[-max_sessions:]
    for day in days:
        res = entry_mod.check(df5, at(day, "15:29"), "orb", day=day, or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"],
                              no_entries_before=cfg.get("no_entries_before"))
        if res["state"] != "triggered" or res["side"] != plan["side"]:
            continue
        side, e = res["side"], res["entry"]
        try:
            stop = plan_mod.stop_to_tick(plan_mod.underlying_stop(plan["stop_rule"], side, e, res["range"]), side)
        except ValueError:
            return {"skipped": f"stop rule {plan['stop_rule']} cannot be replayed"}
        tgt = plan_mod.to_tick(plan_mod.target_from(plan["target_rule"], side, e, stop))
        risk = abs(e - stop)
        after = df5[(df5.index > datetime.fromisoformat(res["trigger_time"])) & (df5.index.date == day)
                    & (df5.index < at(day, plan["squareoff"]))]
        result, r_mult = "flat", None
        for _, bar in after.iterrows():
            hit_stop = bar["low"] <= stop if side == "long" else bar["high"] >= stop
            hit_tgt = bar["high"] >= tgt if side == "long" else bar["low"] <= tgt
            if hit_stop:
                result, r_mult = "stop", -1.0
                break
            if hit_tgt:
                result, r_mult = "target", abs(tgt - e) / risk
                break
        if r_mult is None and not after.empty and risk:
            last = float(after["close"].iloc[-1])
            r_mult = (last - e) / risk * (1 if side == "long" else -1)
        trades.append({"day": day.isoformat(), "entry": e, "result": result, "r": round(r_mult or 0.0, 2)})
    wins = sum(1 for t in trades if t["r"] > 0)
    count = lambda what: sum(1 for t in trades if t["result"] == what)
    return {"sessions": len(days), "fired": len(trades),
            "target": count("target"), "stop": count("stop"), "flat": count("flat"),
            "win_rate": round(wins / len(trades), 3) if trades else None,
            "avg_r": round(sum(t["r"] for t in trades) / len(trades), 3) if trades else None, "trades": trades}
