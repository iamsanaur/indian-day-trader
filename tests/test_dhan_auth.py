import json
import os
import stat
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from idt.data import dhan_auth
from idt.data.base import DataError
from idt.data.dhan import DhanData
from idt.data.instruments import Instruments
from idt.market import IST
from idt.server.app import create_app, fixed_clock, server_token

from .conftest import FIXTURES

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=IST)


class Resp:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class Sess:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.resp


@pytest.fixture
def creds(ws, monkeypatch):
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DHAN_CLIENT_ID", "1100000001")
    monkeypatch.setenv("DHAN_PIN", "123456")
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(dhan_auth, "_last_attempt", 0.0)
    return ws


def ok_body(expiry="2026-10-31T09:00:00"):
    return {"dhanClientId": "1100000001", "dhanClientName": "Demo User", "accessToken": "jwt-abc", "expiryTime": expiry}


def test_login_stores_private_token(creds):
    sess = Sess(Resp(200, ok_body()))
    st = dhan_auth.login("654321", session=sess, now=NOW)
    url, params = sess.calls[0]
    assert url == "https://auth.dhan.co/app/generateAccessToken"
    assert params == {"dhanClientId": "1100000001", "pin": "123456", "totp": "654321"}
    assert st["connected"] and st["source"] == "totp" and st["expires_in_seconds"] == 24 * 3600
    path = creds / "dhan_token.json"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert "654321" not in path.read_text()            # the TOTP itself is never stored
    assert dhan_auth.current_credentials(NOW) == ("1100000001", "jwt-abc")


def test_validation_and_rejection(creds):
    with pytest.raises(DataError, match="6-digit"):
        dhan_auth.login("12ab56")
    with pytest.raises(DataError, match="rejected"):
        dhan_auth.login("111111", session=Sess(Resp(401, {"errorMessage": "Invalid TOTP"})), now=NOW)
    assert dhan_auth.current_credentials(NOW) is None
    with pytest.raises(DataError, match="wait"):          # throttled right after a failure
        dhan_auth.login("222222", session=Sess(Resp(200, ok_body())), now=NOW)


def test_needs_client_id_and_pin(creds, monkeypatch):
    monkeypatch.delenv("DHAN_PIN")
    with pytest.raises(DataError, match="DHAN_PIN"):
        dhan_auth.login("123456")
    assert dhan_auth.status(NOW)["totp_login_available"] is False


def test_expiry_and_env_override(creds, monkeypatch):
    dhan_auth.save_session("1100000001", "jwt-old", NOW - timedelta(minutes=1))
    st = dhan_auth.status(NOW)
    assert not st["connected"] and "expired" in st["message"]
    assert dhan_auth.current_credentials(NOW) is None
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "manual-token")
    assert dhan_auth.current_credentials(NOW) == ("1100000001", "manual-token")
    assert dhan_auth.status(NOW)["source"] == "env"


def test_expiry_parsing():
    assert dhan_auth._parse_expiry("2026-10-31 09:00:00") == datetime(2026, 10, 31, 9, 0, tzinfo=IST)
    assert dhan_auth._parse_expiry("2026-10-31T03:30:00Z").astimezone(IST).hour == 9
    assert dhan_auth._parse_expiry(None) > datetime.now(IST) + timedelta(hours=23)


def test_adapter_uses_current_session(creds):
    inst = Instruments.from_csv(FIXTURES / "scrip-master.csv")
    with pytest.raises(DataError, match="TOTP"):
        DhanData(inst)
    dhan_auth.save_session("1100000001", "jwt-live", datetime.now(IST) + timedelta(hours=10))
    d = DhanData(inst)
    assert d._headers()["access-token"] == "jwt-live" and d.client_id == "1100000001"
    dhan_auth.save_session("1100000001", "jwt-renewed", datetime.now(IST) + timedelta(hours=24))
    assert d._headers()["access-token"] == "jwt-renewed"   # picked up without rebuilding the adapter


def test_api_endpoints(creds, monkeypatch):
    (creds / "config.json").write_text(json.dumps({}))
    monkeypatch.delenv("IDT_FIXTURES")
    c = TestClient(create_app(fixed_clock("2026-10-30T09:00")))
    c.headers["Authorization"] = f"Bearer {server_token()}"
    assert c.get("/api/dhan").json()["connected"] is False
    assert c.get("/api/status").json()["dhan"]["totp_login_available"] is True
    assert c.post("/api/dhan/login", json={"totp": "abc"}).status_code == 400
    monkeypatch.setattr(dhan_auth.requests, "post", lambda *a, **k: Resp(200, ok_body("2026-10-31T09:00:00")))
    st = c.post("/api/dhan/login", json={"totp": "123456"}).json()
    assert st["connected"] and st["client_name"] == "Demo User"
    assert "dhan_token.json" not in c.get("/api/status").json()["files"]
    assert c.delete("/api/dhan").json()["connected"] is False
