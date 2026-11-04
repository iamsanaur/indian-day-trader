"""Behaviour carried over from the original day-trader-skill: entry rule details, tick-rounded plans with
refusals, the Time Machine verdict, fresh-price sizing, charge-inclusive sizing and the stricter risk gate."""

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from idt import entry, plan, risk, scanner, sizing, timemachine
from idt.config import DEFAULTS
from idt.market import IST, at

from .conftest import NOW

DAY = date(2026, 10, 29)


def bars(day, closes, volume=1000, start="09:15"):
    idx = pd.DatetimeIndex([at(day, start) + timedelta(minutes=5 * i) for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": [c + 1 for c in closes], "low": [c - 1 for c in closes],
                         "close": closes, "volume": volume if isinstance(volume, list) else [volume] * len(closes),
                         "oi": 0.0}, index=idx)


# --- entry -----------------------------------------------------------------------------

def test_entry_wick_and_equal_close_do_not_trigger():
    # range 09:15-09:30 high 101; the 09:30 bar wicks to 102 but closes at 101 (equal is not above)
    df = bars(DAY, [100, 100, 100, 101, 101.5])
    df.loc[at(DAY, "09:30"), "high"] = 102
    res = entry.check(df, at(DAY, "09:39"), "orb", allow_short=False)
    assert res["state"] == "waiting" and "last close 101.00" in res["detail"]
    res = entry.check(df, at(DAY, "09:45"), "orb", allow_short=False)
    assert res["state"] == "triggered" and res["entry"] == 101.5
    assert res["trigger_close"].startswith("2026-10-29T09:40") and res["minutes_since"] == 5


def test_entry_reports_forming_bar_and_late_trigger():
    df = bars(DAY, [100, 100, 100, 103, 104, 105, 106])
    early = entry.check(df, at(DAY, "09:33"), "orb")
    assert early["state"] == "waiting" and early["forming"]["bar_start"] == "09:30"
    late = entry.check(df, at(DAY, "09:55"), "orb")
    assert late["state"] == "triggered" and late["minutes_since"] == 20 and "late" in late


def test_entry_volume_filter_moves_the_trigger():
    df = bars(DAY, [100, 100, 100, 103, 104], volume=[1000, 1000, 1000, 500, 3000])
    res = entry.check(df, at(DAY, "09:45"), "orb", min_volume_x=1.0)
    assert res["entry"] == 104 and res["volume_x"] == 3.0 and res["skipped_thin"]


def test_entry_no_entries_before_skips_early_level_breaks():
    df = bars(DAY, [105, 106, 107])
    res = entry.check(df, at(DAY, "09:35"), "level", above=104, no_entries_before="09:30", expire="15:00")
    assert res["state"] == "triggered" and res["trigger_close"].startswith("2026-10-29T09:30")


# --- exit ------------------------------------------------------------------------------

def setup(**kw):
    return dict({"symbol": "RELIANCE", "side": "long", "entry": 1488.5, "setup": "orb",
                 "range": {"high": 1487, "low": 1477, "mid": 1482.33}}, **kw)


def test_stop_rounds_away_from_entry_to_tick():
    p = plan.linear_plan(setup(), "equity", "or-mid", "2R", "15:15", "RELIANCE")
    assert p["stop"] == 1482.3            # 1482.33 rounds DOWN for a long
    assert p["target"] == round(1488.5 + 2 * (1488.5 - 1482.3), 2)
    s = plan.linear_plan(setup(side="short", entry=1470, range={"high": 1487, "low": 1477, "mid": 1482.33}),
                         "equity", "or-mid", "1R", "15:15", "RELIANCE")
    assert s["stop"] == 1482.35           # rounds UP for a short


def test_plan_refusals():
    with pytest.raises(ValueError, match="wrong side"):
        plan.linear_plan(setup(entry=1480), "equity", "or-mid", "1R", "15:15", "RELIANCE")
    with pytest.raises(ValueError, match="noise"):
        plan.linear_plan(setup(), "equity", "pct:0.01", "1R", "15:15", "RELIANCE")
    with pytest.raises(ValueError, match="move already happened"):
        plan.linear_plan(setup(), "equity", "or-mid", "price:1480", "15:15", "RELIANCE")


# --- time machine ----------------------------------------------------------------------

def test_verdict_uses_break_even_share():
    mc = {"p_target": 0.394, "p_stop": 0.606, "p_flat": 0.0, "r_at_target": 1.5, "expected_r": -0.01,
          "to": "2026-10-29T15:15:00+05:30"}
    v = timemachine.verdict(mc)
    assert v["line"].startswith("Close to break-even") and v["share_needed"] == 0.4
    assert timemachine.verdict(dict(mc, r_at_target=1.0))["line"].startswith("Leans toward the stop")
    assert timemachine.verdict(dict(mc, p_target=0.3, p_stop=0.7, r_at_target=1.0))["line"].startswith("Strongly toward the stop")
    assert timemachine.verdict(dict(mc, p_target=0.30, p_stop=0.25, r_at_target=1.0))["line"].startswith("Close to a coin flip")
    notes = timemachine.verdict(dict(mc, p_target=0.2, p_stop=0.1, p_flat=0.7, r_at_target=1.0, expected_r=-0.05))["notes"]
    assert len(notes) == 2


def test_simulation_reports_green_window_and_session_cap(data):
    df = data.candles("NIFTY", 5, DAY - timedelta(days=100), DAY)
    p = plan.linear_plan({"symbol": "NIFTY", "side": "long", "entry": 25995.0, "setup": "orb",
                          "range": {"high": 25985.0, "low": 25905.0, "mid": 25945.0}}, "future", "or-mid", "1R",
                         "15:15", "NIFTY FUT", 65)
    mc = timemachine.simulate(p, df, datetime(2026, 10, 29, 9, 40, tzinfo=IST), n=2000, seed=19, max_sessions=40)
    assert mc["sessions_sampled"] == 40 and mc["window"] == 2 and mc["r_at_target"] == 1.0
    assert mc["p_green"] >= mc["p_target"] and "line" in mc["verdict"]
    with pytest.raises(ValueError, match="complete prior sessions"):
        timemachine.simulate(p, df[df.index.date >= date(2026, 10, 20)], datetime(2026, 10, 29, 9, 40, tzinfo=IST))


# --- sizing ----------------------------------------------------------------------------

@pytest.fixture
def cfg():
    return dict(DEFAULTS, max_loss_per_trade=3000)


def eq_plan(**kw):
    return plan.linear_plan(setup(**kw), "equity", "or-mid", "2R", "15:15", "RELIANCE")


def test_fresh_price_above_entry_shrinks_size(cfg):
    p = eq_plan()
    base = sizing.size(p, dict(cfg, capital=10_000_000), now=NOW)
    moved = sizing.size(p, dict(cfg, capital=10_000_000), now=NOW, ltp=1491.0)
    assert moved["units"] < base["units"] and moved["rr"] < base["rr"] and moved["entry_now"] == 1491.0
    lower = sizing.size(p, dict(cfg, capital=10_000_000), now=NOW, ltp=1485.0)   # never shrinks the risk
    assert lower["units"] == base["units"]
    with pytest.raises(ValueError, match="move happened"):
        sizing.size(p, cfg, now=NOW, ltp=1501.0)


def test_charges_fit_inside_max_loss(cfg):
    p = eq_plan()
    o = sizing.size(p, dict(cfg, capital=10_000_000, max_loss_per_trade=1000), now=NOW)
    assert o["loss_at_stop"] <= 1000 and o["units"] < 1000 // p["risk_per_unit"] + 1


# --- risk ------------------------------------------------------------------------------

def checked(cfg, journal=(), now=NOW, **plan_kw):
    p = eq_plan(**plan_kw)
    p["created"] = now.isoformat()
    o = sizing.size(p, cfg, quote_ts=now.isoformat(), now=now)
    return risk.check(cfg, p, o, list(journal), now, ban_list=None, available=1e6), o


def test_risk_min_reward_risk_and_window(cfg):
    ok, _ = checked(cfg)
    assert ok["verdict"] == "PASS", ok["reasons"]
    low, _ = checked(dict(cfg, min_reward_risk=3))
    assert any(r.startswith("reward:risk") for r in low["reasons"])
    early, _ = checked(cfg, now=at(DAY, "09:20"))
    assert any(r.startswith("entry window opens") for r in early["reasons"])


def test_risk_daily_cap_counts_full_max_loss_of_entries(cfg):
    _, o = checked(cfg)
    entries = [{"type": "confirm", "ts": NOW.isoformat(), "symbol": f"S{i}", "kind": "equity",
                "loss_at_stop": o["loss_at_stop"]} for i in range(2)]
    res, _ = checked(dict(cfg, daily_loss_cap=o["loss_at_stop"] * 2.5), entries)
    assert any("daily loss cap" in r for r in res["reasons"])


def test_risk_blocks_duplicate_open_entry(cfg):
    dup = [{"type": "confirm", "ts": NOW.isoformat(), "symbol": "RELIANCE", "kind": "equity", "loss_at_stop": 1}]
    res, _ = checked(cfg, dup)
    assert any("no duplicate" in r for r in res["reasons"])
    closed = dup + [{"type": "close", "ts": (NOW + timedelta(seconds=1)).isoformat(), "symbol": "RELIANCE", "pnl": 10}]
    res, _ = checked(cfg, closed)
    assert not any("no duplicate" in r for r in res["reasons"])


# --- scanner ---------------------------------------------------------------------------

def daily_frame(closes, volume=1e6):
    idx = pd.DatetimeIndex([at(DAY - timedelta(days=len(closes) - i), "09:15") for i in range(len(closes))])
    return pd.DataFrame({"open": closes, "high": [c * 1.01 for c in closes], "low": [c * 0.99 for c in closes],
                         "close": closes, "volume": volume, "oi": 0.0}, index=idx)


def test_daily_breakout_reclaim_oversold_and_liquidity():
    up = daily_frame([100.0] * 25 + [101.0])
    assert scanner.breakout("X", up)["prior_high_close"] == 100.0
    dip = daily_frame([100.0] * 24 + [95.0, 104.0])
    assert scanner.reclaim("X", dip)
    falling = daily_frame([200 - 3 * i for i in range(40)])
    assert scanner.oversold("X", falling)["rsi"] < 30
    assert scanner.liquid(daily_frame([100.0] * 25, volume=1000), 50, 25)[0] is False
    assert scanner.liquid(daily_frame([100.0] * 25, volume=5e6), 50, 25)[0] is True
