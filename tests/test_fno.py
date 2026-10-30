import math
from datetime import date

import numpy as np
import pytest

from idt import fno
from idt.data.base import ChainRow, OptionChain, OptionQuote


def test_black_scholes_reference_value():
    # Hull: S=100, K=100, T=1, r=5%, sigma=20% -> call 10.4506, put 5.5735
    assert fno.bs_price(100, 100, 1, 0.05, 0.2, "CE") == pytest.approx(10.4506, abs=1e-4)
    assert fno.bs_price(100, 100, 1, 0.05, 0.2, "PE") == pytest.approx(5.5735, abs=1e-4)


def test_put_call_parity():
    s, k, t, r, v = 26000, 26200, 5 / 365, 0.065, 0.12
    c, p = fno.bs_price(s, k, t, r, v, "CE"), fno.bs_price(s, k, t, r, v, "PE")
    assert c - p == pytest.approx(s - k * math.exp(-r * t), abs=1e-6)


def test_vectorised_matches_scalar():
    s = np.array([25500.0, 26000.0, 26500.0])
    vec = fno.bs_price_np(s, 26000, 5 / 365, 0.065, 0.12, "CE")
    scalar = [fno.bs_price(x, 26000, 5 / 365, 0.065, 0.12, "CE") for x in s]
    assert vec == pytest.approx(scalar, abs=1e-3)


def test_implied_vol_round_trip():
    price = fno.bs_price(26000, 26100, 7 / 365, 0.065, 0.135, "CE")
    assert fno.implied_vol(price, 26000, 26100, 7 / 365, 0.065, "CE") == pytest.approx(0.135, abs=1e-5)
    assert fno.implied_vol(0.0, 26000, 26100, 7 / 365, 0.065, "CE") is None


def test_greeks_signs():
    g_call = fno.greeks(26000, 26000, 5 / 365, 0.065, 0.12, "CE")
    g_put = fno.greeks(26000, 26000, 5 / 365, 0.065, 0.12, "PE")
    assert 0.45 < g_call["delta"] < 0.6 and -0.55 < g_put["delta"] < -0.4
    assert g_call["theta"] < 0 and g_call["gamma"] > 0 and g_call["vega"] > 0


def _q(oi, ltp=10.0, prev_oi=None, prev_close=0.0):
    return OptionQuote(ltp=ltp, iv=12, oi=oi, prev_oi=prev_oi if prev_oi is not None else oi, volume=oi, prev_close=prev_close)


def test_max_pain_and_pcr():
    rows = [ChainRow(100, _q(10), _q(500)), ChainRow(110, _q(100), _q(100)), ChainRow(120, _q(600), _q(5))]
    chain = OptionChain("X", date(2026, 11, 3), 110, rows)
    assert fno.max_pain(chain) == 110
    assert fno.pcr(chain)["oi"] == pytest.approx(605 / 710, abs=1e-3)


def test_buildup_labels():
    assert fno.buildup(+5, +100) == "long buildup"
    assert fno.buildup(-5, +100) == "short buildup"
    assert fno.buildup(+5, -100) == "short covering"
    assert fno.buildup(-5, -100) == "long unwinding"


def test_analyze_fixture_chain(data):
    chain = data.option_chain("NIFTY", date(2026, 11, 3))
    a = fno.analyze_chain(chain)
    assert a["atm"] == 26000
    assert a["walls"]["resistance"][0]["strike"] == 26500
    assert a["walls"]["support"][0]["strike"] == 25500
    assert a["expected_move"]["range"][0] < chain.spot < a["expected_move"]["range"][1]
