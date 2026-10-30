from datetime import date, datetime, timedelta

import pytest

from idt import entry, plan, risk, sizing, ticket, timemachine
from idt.market import IST, at
from idt.strategy import build

from .conftest import NOW

DAY = date(2026, 10, 29)


def nifty(data):
    return data.candles("NIFTY", 5, DAY - timedelta(days=100), DAY)


def test_entry_states(data):
    df = nifty(data)
    assert entry.check(df, at(DAY, "09:25"), "orb")["state"] == "waiting"
    assert entry.check(df, at(DAY, "09:38"), "orb")["state"] == "waiting"   # 09:35 bar not complete
    res = entry.check(df, at(DAY, "09:45"), "orb")
    assert (res["state"], res["side"], res["entry"]) == ("triggered", "long", 25995.0)
    assert res["trigger_time"].startswith("2026-10-29T09:35")
    assert entry.check(df, at(DAY, "12:00"), "level", above=99999)["state"] == "expired"


def setup():
    return {"symbol": "NIFTY", "side": "long", "entry": 25995.0, "setup": "orb",
            "range": {"high": 25985.0, "low": 25905.0, "mid": 25945.0}, "trigger_time": "2026-10-29T09:35:00+05:30"}


def test_linear_plan_and_sizing(cfg):
    p = plan.linear_plan(dict(setup(), symbol="RELIANCE", entry=1488.5, range={"high": 1487, "low": 1477, "mid": 1482}),
                         "equity", "or-mid", "2R", "15:15", "RELIANCE")
    assert (p["stop"], p["target"], p["risk_per_unit"]) == (1482, 1501.5, 6.5)
    o = sizing.size(p, cfg, quote_ts=NOW.isoformat(), now=NOW)
    assert o["units"] == 335  # 3000 / 6.5 = 461 shares, capped at 100000 * 5x / 1488.5 = 335
    assert o["legs"][0]["quantity"] == o["units"]


def test_equity_size_is_capped_by_leverage(cfg):
    p = plan.linear_plan(dict(setup(), symbol="RELIANCE", entry=1488.5), "equity", "pct:0.1", "1R", "15:15", "RELIANCE")
    o = sizing.size(p, dict(cfg, capital=20000, leverage_cap=5), now=NOW)
    assert o["units"] == int(20000 * 5 / 1488.5)
    assert "leverage" in o["notes"][0]


def test_option_plan_underlying_basis(data, cfg):
    chain = data.option_chain("NIFTY", date(2026, 11, 3))
    from idt.strategy import make_leg
    leg = make_leg(chain, 26000, "CE", +1)
    p = plan.option_plan(setup(), leg, 65, "or-mid", "1.5R", "15:15", 0.065, NOW)
    assert p["underlying_stop"] == 25945.0 and p["underlying_target"] == 26070.0
    assert p["stop"] < p["entry"] < p["target"]
    assert p["risk_per_unit"] == pytest.approx((p["entry"] - p["stop"]) * 65)


def strat(data, name="bull-call-spread", **kw):
    chain = data.option_chain("NIFTY", date(2026, 11, 3))
    legs = build(name, chain, **kw)
    return {"name": name, "underlying": "NIFTY", "expiry": "2026-11-03", "spot": chain.spot, "lot_size": 65,
            "view": "long", "legs": [l.to_dict() for l in legs]}


def test_strategy_plan_rules(data):
    p = plan.strategy_plan(strat(data, width=4), "maxloss-pct:50", "1.5R", "15:15")
    assert p["stop_pnl"] == pytest.approx(p["analysis"]["max_loss"] / 2)
    assert p["target_pnl"] == pytest.approx(abs(p["stop_pnl"]) * 1.5, abs=0.01)
    with pytest.raises(ValueError):
        plan.strategy_plan(strat(data, "short-strangle", offset=4), "maxloss-pct:50", "1R", "15:15")
    credit = plan.strategy_plan(strat(data, "short-strangle", offset=4), "credit-x:1", "credit-pct:50", "15:15")
    assert credit["stop_pnl"] == pytest.approx(credit["analysis"]["net_premium"])


def test_sizing_rejects_oversized_risk(data, cfg):
    p = plan.strategy_plan(strat(data, width=4), "maxloss-pct:100", "1R", "15:15")
    with pytest.raises(ValueError, match="above the max loss"):
        sizing.size(p, dict(cfg, max_loss_per_trade=1000), now=NOW)


def sized(data, cfg, name="bull-call-spread", **kw):
    p = plan.strategy_plan(strat(data, name, **kw), "maxloss-pct:50" if "spread" in name else "pnl:-2500", "1R", "15:15")
    o = sizing.size(p, cfg, quote_ts=NOW.isoformat(), now=NOW, available=250000)
    return p, o


def test_risk_pass_and_blocks(data, cfg):
    p, o = sized(data, cfg, width=4)
    ok = risk.check(cfg, p, o, [], NOW, ban_list=None, available=250000)
    assert ok["verdict"] == "PASS", ok["reasons"]

    late = risk.check(cfg, p, o, [], at(DAY, "15:05"), ban_list=None, available=250000)
    assert late["verdict"] == "BLOCK" and any("entry cutoff" in r for r in late["reasons"])

    stale = risk.check(cfg, p, o, [], NOW + timedelta(minutes=5), ban_list=None, available=250000)
    assert any("fresh prices" in r for r in stale["reasons"])

    cap = [{"type": "close", "ts": NOW.isoformat(), "pnl": -2000}]
    assert any("daily loss cap" in r for r in risk.check(cfg, p, o, cap, NOW, ban_list=None, available=250000)["reasons"])

    poor = risk.check(cfg, p, o, [], NOW, ban_list=None, available=100)
    assert any("margin" in r for r in poor["reasons"])


def test_risk_blocks_naked_unless_allowed(data, cfg):
    p, o = sized(data, cfg, "short-strangle", offset=4)
    assert any("naked" in r for r in risk.check(cfg, p, o, [], NOW, ban_list=None, available=250000)["reasons"])
    assert risk.check(dict(cfg, allow_naked=True), p, o, [], NOW, ban_list=None, available=250000)["verdict"] == "PASS"


def test_risk_ban_list_for_stock_fno(cfg):
    p = {"symbol": "IDEA", "kind": "future", "side": "long", "stop": 9, "legs": [], "squareoff": "15:15"}
    o = {"symbol": "IDEA", "kind": "future", "legs": [], "loss_at_stop": 500, "hash": "x", "margin": {"total": 1},
         "quote_ts": NOW.isoformat()}
    res = risk.check(cfg, p, o, [], NOW, ban_list=["IDEA"], available=1e6)
    assert any("ban" in r for r in res["reasons"])


def test_ticket_requires_matching_fresh_pass(data, cfg):
    p, o = sized(data, cfg, width=4)
    with pytest.raises(ticket.TicketError):
        ticket.build(p, o, None, NOW)
    r = risk.check(cfg, p, o, [], NOW, ban_list=None, available=250000)
    with pytest.raises(ticket.TicketError, match="changed"):
        ticket.build(p, dict(o, hash="other"), r, NOW)
    with pytest.raises(ticket.TicketError, match="old"):
        ticket.build(p, o, r, NOW + timedelta(minutes=11))
    t = ticket.build(p, o, r, NOW)
    assert t["entries"][0]["action"] == "BUY"  # hedge/long legs first
    assert t["order_hash"] == o["hash"]


def test_ticket_single_leg_sl_limit(cfg):
    p = plan.linear_plan(dict(setup(), symbol="RELIANCE", entry=1488.5, range={"high": 1487, "low": 1477, "mid": 1482}),
                         "equity", "or-mid", "2R", "15:15", "RELIANCE")
    o = sizing.size(p, cfg, quote_ts=NOW.isoformat(), now=NOW)
    r = risk.check(cfg, p, o, [], NOW, ban_list=None, available=100000)
    t = ticket.build(p, o, r, NOW)
    sl = t["exits"][0]
    assert sl["order_type"] == "SL" and sl["trigger_price"] == 1482 and sl["price"] < 1482


def test_timemachine_is_deterministic(data):
    p = plan.linear_plan(setup(), "future", "or-mid", "1.5R", "15:15", "NIFTY FUT", 65)
    start = datetime(2026, 10, 29, 9, 40, tzinfo=IST)
    a = timemachine.simulate(p, nifty(data), start, n=2000, seed=1)
    b = timemachine.simulate(p, nifty(data), start, n=2000, seed=1)
    assert a == b
    assert a["p_target"] + a["p_stop"] + a["p_flat"] == pytest.approx(1.0, abs=1e-3)
    rep = timemachine.replay(p, nifty(data), DAY, {"or_minutes": 15, "entry_expiry": "11:30"})
    assert rep["fired"] > 0 and all(t["r"] in (-1.0, 1.5) or t["result"] == "flat" for t in rep["trades"])
