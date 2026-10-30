import json

import pytest
from fastapi.testclient import TestClient

from idt.server.app import create_app, fixed_clock, server_token
from idt.server.run import pairing_uri


@pytest.fixture
def client(ws):
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "config.json").write_text(json.dumps({"max_loss_per_trade": 3000}))
    c = TestClient(create_app(fixed_clock("2026-10-29T09:45"), demo=True))
    c.headers["Authorization"] = f"Bearer {server_token()}"
    return c


def test_auth_required(ws):
    anon = TestClient(create_app(fixed_clock("2026-10-29T09:45")))
    assert anon.get("/api/health").json()["ok"] is True
    assert anon.get("/api/status").status_code == 401
    assert anon.get("/api/status", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert anon.get(f"/api/status?token={server_token()}").status_code == 200


def test_markets_and_options(client):
    board = client.get("/api/indices").json()["indices"]
    assert board["NIFTY"]["orb"]["state"] == "triggered"
    idx = client.get("/api/index/NIFTY?days=1").json()
    assert idx["candles"][0]["o"] == 25940.0 and len(idx["series"]["ema9"]) == len(idx["candles"])
    chain = client.get("/api/chain/NIFTY").json()
    assert chain["max_pain"] == 26000 and chain["lot_size"] == 65
    assert "iron-condor" in client.get("/api/strategies").json()


def test_trade_flow_over_http(client):
    assert client.post("/api/entry/NIFTY", json={}).json()["state"] == "triggered"
    s = client.post("/api/strategy", json={"name": "bull-call-spread", "width": 4, "write": True}).json()
    assert len(s["curve"]["x"]) == len(s["curve"]["expiry"]) == len(s["curve"]["today"])
    plan = client.post("/api/plan", json={"kind": "strategy", "stop": "maxloss-pct:50", "target": "1.5R"}).json()
    assert plan["rr"] == 1.5
    assert client.post("/api/timemachine", json={"paths": 1000}).json()["monte_carlo"]["paths"] == 1000
    orders = client.post("/api/size", json={}).json()
    assert client.post("/api/risk").json()["verdict"] == "PASS"
    assert client.get("/api/ticket").json()["order_hash"] == orders["hash"]

    refused = client.post("/api/ticket/confirm", json={"hash": orders["hash"], "typed": "ok"})
    assert refused.status_code == 400 and "yes" in refused.json()["detail"]
    done = client.post("/api/ticket/confirm", json={"hash": orders["hash"], "typed": "yes"}).json()
    assert done["confirmed"] == orders["hash"]
    assert client.get("/api/status").json()["trades_today"] == 1

    alerts = client.post("/api/alerts", json={"from_plan": True}).json()
    assert len(alerts) == 3
    assert client.post("/api/journal/close", json={"pnl": -500}).json()[-1]["pnl"] == -500


def test_errors_are_400_json(client):
    r = client.post("/api/risk")
    assert r.status_code == 400 and "plan.json" in r.json()["error"]


def test_config_whitelist(client):
    assert client.patch("/api/config", json={"allow_naked": True}).json()["config"]["allow_naked"] is True
    assert client.patch("/api/config", json={"data_provider": "x"}).status_code == 400
    assert client.patch("/api/config", json={"mode": "yolo"}).status_code == 400


def test_research(client):
    assert client.get("/api/ban").json()["ban_list"] == ["RBLBANK", "IDEA"]
    assert client.get("/api/news?symbols=RELIANCE&hours=72").json()["announcements"]
    assert client.get("/api/insider/deals").json()["bulk"][0]["symbol"] == "TCS"


def test_pairing_uri():
    assert pairing_uri("http://192.168.1.5:8742", "a b") == "idt://pair?u=http%3A%2F%2F192.168.1.5%3A8742&t=a%20b"
