from datetime import date

import numpy as np
import pandas as pd
import pytest

from idt import charges, indicators as ind


def test_option_round_trip_charges():
    c = charges.compute("opt", buy_value=10000, sell_value=12000)
    assert c["brokerage"] == 40
    assert c["stt"] == pytest.approx(18.0)            # 0.15% of sell premium
    assert c["exchange_txn"] == pytest.approx(7.71, abs=0.01)
    assert c["stamp"] == pytest.approx(0.3)
    assert c["gst"] == pytest.approx((40 + 7.7066 + 0.022) * 0.18, abs=0.01)


def test_equity_intraday_brokerage_cap_and_futures_stt():
    small = charges.compute("eq_intraday", 20000, 20100)
    assert small["brokerage"] == pytest.approx(6 + 6.03)  # 0.03% below the Rs 20 cap
    fut = charges.compute("fut", 1_690_000, 1_700_000)
    assert fut["stt"] == pytest.approx(850.0)            # 0.05% of sell


def test_override_rates():
    c = charges.compute("opt", 0, 10000, override={"stt": {"opt_sell": 0.001}})
    assert c["stt"] == pytest.approx(10.0)


def test_cpr_and_pivots():
    p = ind.cpr(high=26235.4, low=25836.54, close=25925.0)
    assert p["pivot"] == pytest.approx((26235.4 + 25836.54 + 25925.0) / 3, abs=0.01)
    assert p["bc"] <= p["pivot"] <= p["tc"]
    assert p["s1"] < p["pivot"] < p["r1"]


def test_opening_range_and_vwap(data):
    df = data.candles("NIFTY", 5, date(2026, 10, 29), date(2026, 10, 29))
    rng = ind.opening_range(df, date(2026, 10, 29), 15)
    assert (rng["high"], rng["low"], rng["mid"]) == (25985.0, 25905.0, 25945.0)
    assert ind.vwap(df).isna().all()              # spot index: no volume
    fut = data.candles("NIFTY FUT", 5, date(2026, 10, 29), date(2026, 10, 29))
    assert ind.vwap(fut).notna().all()


def test_rsi_bounds():
    s = pd.Series(np.linspace(100, 200, 50))
    assert ind.rsi(s).iloc[-1] == 100
    r = ind.rsi(pd.Series(np.sin(np.arange(100)) * 10 + 100))
    assert r.dropna().between(0, 100).all()
