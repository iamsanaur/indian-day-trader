from datetime import date

import pytest

from idt import strategy as s


def L(kind, strike, side, premium, lots=1):
    return s.Leg(kind, strike, side, lots, premium, "2026-11-03", 0.12)


def test_bull_call_spread_economics():
    legs = [L("CE", 26000, +1, 150), L("CE", 26200, -1, 70)]
    a = s.analyze(legs, 26000, 65)
    assert a["net_premium"] == pytest.approx(80 * 65)
    assert a["max_loss"] == pytest.approx(-80 * 65)
    assert a["max_profit"] == pytest.approx(120 * 65)
    assert a["breakevens"] == [pytest.approx(26080, abs=0.5)]
    assert not a["naked"]


def test_short_strangle_is_naked_and_unlimited():
    legs = [L("CE", 26400, -1, 30), L("PE", 25600, -1, 32)]
    a = s.analyze(legs, 26000, 65)
    assert a["unlimited_loss"] and a["max_loss"] is None
    assert a["premium_type"] == "credit"
    assert len(a["naked"]) == 2
    assert a["breakevens"] == [pytest.approx(25538, abs=0.5), pytest.approx(26462, abs=0.5)]


def test_iron_condor_is_defined_risk():
    legs = [L("CE", 26400, -1, 30), L("CE", 26500, +1, 17), L("PE", 25600, -1, 32), L("PE", 25500, +1, 19)]
    a = s.analyze(legs, 26000, 65)
    assert not a["naked"] and not a["unlimited_loss"]
    assert a["max_profit"] == pytest.approx(26 * 65)
    assert a["max_loss"] == pytest.approx(-(100 - 26) * 65)


def test_covered_call_with_future_is_not_naked():
    legs = [s.Leg("FUT", 0, +1, 1, 26050, "2026-11-24"), L("CE", 26400, -1, 30)]
    assert s.naked_legs(legs) == []


def test_builders_and_leg_spec(data):
    chain = data.option_chain("NIFTY", date(2026, 11, 3))
    ic = s.build("iron-condor", chain, offset=4, width=2)
    assert [l.side for l in ic] == [-1, +1, -1, +1]
    assert ic[1].strike - ic[0].strike == 100
    leg = s.parse_leg_spec("-2x25800PE", chain)
    assert (leg.side, leg.lots, leg.strike, leg.kind) == (-1, 2, 25800, "PE")
    buy = s.make_leg(chain, 26000, "CE", +1)
    sell = s.make_leg(chain, 26000, "CE", -1)
    assert buy.premium > sell.premium  # buy at ask, sell at bid
