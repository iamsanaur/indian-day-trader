from datetime import date

import pytest

from idt.data.base import DataError
from idt.data.dhan import DhanData
from idt.data.instruments import Instruments

from .conftest import FIXTURES


@pytest.fixture
def inst():
    return Instruments.from_csv(FIXTURES / "scrip-master.csv")


def test_resolve_symbols(inst):
    n = inst.resolve("NIFTY")
    assert (n.security_id, n.exchange_segment, n.instrument, n.lot_size) == ("13", "IDX_I", "INDEX", 65)
    eq = inst.resolve("reliance")
    assert (eq.security_id, eq.exchange_segment, eq.tick_size) == ("2885", "NSE_EQ", 0.05)
    fut = inst.resolve("NIFTY FUT 2026-11-24")
    assert fut.is_future and fut.lot_size == 65
    opt = inst.resolve("NIFTY 2026-11-03 26000 CE")
    assert (opt.strike, opt.option_type, opt.expiry, opt.exchange_segment) == (26000.0, "CE", date(2026, 11, 3), "NSE_FNO")
    sx = inst.resolve("SENSEX 2026-11-05 85000 PE")
    assert sx.exchange_segment == "BSE_FNO" and sx.lot_size == 20
    assert inst.lot_size("BANKNIFTY") == 30 and inst.lot_size("RELIANCE") == 500
    assert "RELIANCE" in inst.fno_stocks()
    with pytest.raises(DataError):
        inst.resolve("NOTASTOCK")


class FakeResp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, str(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def request(self, method, url, json=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        return self.responses.pop(0)


def dhan(inst, responses):
    sess = FakeSession(responses)
    return DhanData(inst, "1100", "tok", session=sess, sleep=lambda s: None), sess


def test_option_chain_request_and_parse(inst):
    payload = {"data": {"last_price": 26000.5, "oc": {"26000.000000": {
        "ce": {"last_price": 150, "implied_volatility": 12.1, "oi": 1000, "previous_oi": 800, "volume": 5,
               "greeks": {"delta": 0.52, "theta": -15, "gamma": 0.001, "vega": 12}, "security_id": 42,
               "top_bid_price": 149.5, "top_ask_price": 150.5},
        "pe": {"last_price": 140, "implied_volatility": 12.6, "oi": 1200, "previous_oi": 1300, "volume": 7}}}},
        "status": "success"}
    d, sess = dhan(inst, [FakeResp(200, payload)])
    chain = d.option_chain("NIFTY", date(2026, 11, 3))
    call = sess.calls[0]
    assert call["url"].endswith("/v2/optionchain")
    assert call["json"] == {"UnderlyingScrip": 13, "UnderlyingSeg": "IDX_I", "Expiry": "2026-11-03"}
    assert call["headers"]["access-token"] == "tok" and call["headers"]["client-id"] == "1100"
    row = chain.rows[0]
    assert chain.spot == 26000.5 and row.ce.delta == 0.52 and row.ce.oi_change == 200 and row.pe.oi_change == -100


def test_stock_underlying_uses_equity_segment(inst):
    d, sess = dhan(inst, [FakeResp(200, {"data": ["2026-11-24"], "status": "success"})])
    assert d.expiries("RELIANCE") == [date(2026, 11, 24)]
    assert sess.calls[0]["json"] == {"UnderlyingScrip": 2885, "UnderlyingSeg": "NSE_EQ"}


def test_intraday_history_is_chunked_to_90_days(inst):
    empty = {"open": [], "high": [], "low": [], "close": [], "volume": [], "timestamp": []}
    d, sess = dhan(inst, [FakeResp(200, empty)] * 3)
    d.candles("NIFTY", 5, date(2026, 5, 1), date(2026, 10, 29))
    bodies = [c["json"] for c in sess.calls]
    assert len(bodies) == 3 and all(b["interval"] == "5" for b in bodies)
    assert bodies[0]["fromDate"] == "2026-05-01 09:00:00" and bodies[0]["exchangeSegment"] == "IDX_I"


def test_funds_misspelt_field_and_margin_fallback(inst):
    d, _ = dhan(inst, [FakeResp(200, {"availabelBalance": 98440.0, "utilizedAmount": 15202.0})])
    assert d.funds()["available"] == 98440.0
    d, sess = dhan(inst, [FakeResp(400, {"errorCode": "DH-905", "errorMessage": "bad"}),
                          FakeResp(200, {"totalMargin": 1000.0}), FakeResp(200, {"totalMargin": 500.0})])
    m = d.margin([{"symbol": "NIFTY 2026-11-03 26000 CE", "side": "BUY", "quantity": 65, "price": 150},
                  {"symbol": "NIFTY 2026-11-03 26200 CE", "side": "SELL", "quantity": 65, "price": 70}])
    assert m == {"total": 1500.0, "source": "dhan-single-sum"}
    assert sess.calls[1]["json"]["productType"] == "INTRADAY"


def test_auth_error_gives_setup_help_and_rate_limit_retries(inst):
    d, _ = dhan(inst, [FakeResp(401, {"status": "failure", "data": {"807": "Access token is expired"}})])
    with pytest.raises(DataError, match="TOTP"):
        d.funds()
    d, sess = dhan(inst, [FakeResp(429, {}), FakeResp(200, {"availabelBalance": 1.0})])
    assert d.funds()["available"] == 1.0 and len(sess.calls) == 2


def test_missing_credentials(inst, ws, monkeypatch):
    for k in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "DHAN_PIN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(DataError, match="DHAN_PIN"):
        DhanData(inst)


def test_nse_fixture_parsing(tmp_path):
    from idt.data.nse import NSE
    nse = NSE(tmp_path, "ua", fixture_dir=FIXTURES / "nse")
    assert nse.ban_list() == ["RBLBANK", "IDEA"]
    assert nse.large_deals()["bulk"][0]["symbol"] == "TCS"
    assert nse.results("RELIANCE")[0]["eps"] == 14.1
    assert "2026-11-24" in nse.holidays()
