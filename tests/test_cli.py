"""End-to-end worked example on fixtures: NIFTY ORB -> bull call spread -> plan -> size -> risk -> ticket."""

import json

from .conftest import run


def test_worked_example(cli, ws):
    assert cli("init")[0] == 0
    cfg = json.loads((ws / "config.json").read_text())
    cfg["max_loss_per_trade"] = 3000
    (ws / "config.json").write_text(json.dumps(cfg))

    code, setup = cli("entry", "check", "NIFTY", "--write")
    assert code == 0 and setup["state"] == "triggered" and setup["entry"] == 25995.0

    code, idx = cli("index", "NIFTY")
    assert code == 0 and idx["opening_range"]["high"] == 25985.0 and idx["orb"]["state"] == "triggered"
    assert all(p.endswith(".png") for p in idx["charts"])

    code, chain = cli("chain", "NIFTY", "--chart")
    assert code == 0 and chain["lot_size"] == 65 and chain["max_pain"] == 26000

    code, strat = cli("strategy", "bull-call-spread", "NIFTY", "--width", "4", "--write")
    assert code == 0 and [l["strike"] for l in strat["legs"]] == [26000, 26200]

    code, plan = cli("exit", "plan", "--kind", "strategy", "--stop", "maxloss-pct:50", "--target", "1.5R", "--write")
    assert code == 0 and plan["trigger_time"].startswith("2026-10-29T09:35") and plan["rr"] == 1.5

    code, tm = cli("timemachine", "run", "--paths", "2000")
    assert code == 0 and tm["monte_carlo"]["paths"] == 2000

    code, orders = cli("size", "--write")
    assert code == 0 and orders["units"] == 1 and orders["legs"][0]["quantity"] == 65

    code, verdict = cli("risk", "check")
    assert code == 0 and verdict["verdict"] == "PASS", verdict["reasons"]

    code, ticket = cli("ticket", "show")
    assert code == 0 and ticket["order_hash"] == orders["hash"]

    code, bad = cli("ticket", "confirm", "deadbeef")
    assert code == 2 and "mismatch" in bad["error"]
    code, ok = cli("ticket", "confirm", orders["hash"])
    assert code == 0 and ok["confirmed"] == orders["hash"]

    code, alerts = cli("alerts", "add", "--from-plan")
    assert code == 0 and [a["kind"] for a in alerts] == ["pnl", "pnl", "time"]


def test_risk_blocks_without_plan(cli):
    code, out = cli("risk", "check")
    assert code == 2 and "plan.json" in out["error"]


def test_scans_find_fixture_setups(cli):
    _, orb = cli("scan", "orb", "--universe", "RELIANCE,TCS")
    assert [h["symbol"] for h in orb["hits"]] == ["RELIANCE"]
    _, bounce = run("scan", "bounce", "--universe", "HDFCBANK,TCS", now="2026-10-29T15:35")
    assert [h["symbol"] for h in bounce["hits"]] == ["HDFCBANK"]
    _, flag = run("scan", "flag", "--universe", "HDFCBANK,TCS", now="2026-10-29T15:35")
    assert [h["symbol"] for h in flag["hits"]] == ["TCS"]


def test_public_data_commands(cli):
    assert cli("news", "--symbols", "RELIANCE", "--hours", "72")[1]["announcements"][0]["subject"] == "Outcome of Board Meeting"
    assert cli("ban")[1]["ban_list"] == ["RBLBANK", "IDEA"]
    assert cli("results", "RELIANCE")[1]["quarters"][0]["revenue_yoy_pct"] == 8.4
    assert cli("insider", "pit")[1][0]["category"] == "Promoter Group"
    assert cli("charges", "--segment", "opt", "--buy", "10000", "--sell", "12000")[1]["total"] > 0


def test_naked_strategy_warns(cli):
    _, out = cli("strategy", "short-strangle", "NIFTY", "--delta", "0.2")
    assert out["analysis"]["unlimited_loss"] and "allow_naked" in out["warning"]
