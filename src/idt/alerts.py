"""Price, stop, target, P/L and square-off alerts stored in idt/alerts.json."""

from __future__ import annotations

import uuid
from datetime import datetime

from .market import at
from .strategy import legs_from_dicts


def new(kind: str, symbol: str | None, op: str | None, value, label: str, **extra) -> dict:
    return {"id": uuid.uuid4().hex[:8], "kind": kind, "symbol": symbol, "op": op, "value": value,
            "label": label, "fired": False, **extra}


def from_plan(plan: dict) -> list[dict]:
    out = []
    long_view = plan["side"] == "long"
    if plan["basis"] == "underlying":
        out.append(new("price", plan["symbol"], "<=" if long_view else ">=", plan["underlying_stop"], "STOP (underlying)"))
        out.append(new("price", plan["symbol"], ">=" if long_view else "<=", plan["underlying_target"], "TARGET (underlying)"))
    elif plan["basis"] == "premium":
        out.append(new("price", plan["contract"], "<=", plan["stop"], "STOP (premium)"))
        out.append(new("price", plan["contract"], ">=", plan["target"], "TARGET (premium)"))
    else:
        common = {"legs": plan["legs"], "lot_size": plan["lot_size"]}
        out.append(new("pnl", None, "<=", plan["stop_pnl"], "STOP (combined P/L per set)", **common))
        out.append(new("pnl", None, ">=", plan["target_pnl"], "TARGET (combined P/L per set)", **common))
    out.append(new("time", None, ">=", plan.get("squareoff", "15:15"), "SQUARE OFF: be flat"))
    return out


def symbols_needed(alerts: list[dict]) -> list[str]:
    syms = set()
    for a in alerts:
        if a["fired"]:
            continue
        if a["kind"] == "price":
            syms.add(a["symbol"])
        elif a["kind"] == "pnl":
            syms.update(l["symbol"] for l in a["legs"])
    return sorted(syms)


def _cmp(x: float, op: str, v: float) -> bool:
    return x <= v if op == "<=" else x >= v


def evaluate(alerts: list[dict], prices: dict[str, float], now: datetime) -> list[dict]:
    """Marks and returns newly fired alerts. prices: symbol -> last traded price."""
    fired = []
    for a in alerts:
        if a["fired"]:
            continue
        hit, observed = False, None
        if a["kind"] == "price" and a["symbol"] in prices:
            observed = prices[a["symbol"]]
            hit = _cmp(observed, a["op"], float(a["value"]))
        elif a["kind"] == "pnl" and all(l["symbol"] in prices for l in a["legs"]):
            legs = legs_from_dicts(a["legs"])
            observed = sum(l.side * (prices[l.symbol] - l.premium) * l.lots * a["lot_size"] for l in legs)
            hit = _cmp(observed, a["op"], float(a["value"]))
        elif a["kind"] == "time":
            observed = now.strftime("%H:%M")
            hit = now >= at(now.date(), a["value"])
        if hit:
            a.update(fired=True, fired_at=now.isoformat(), observed=round(observed, 2) if isinstance(observed, float) else observed)
            fired.append(a)
    return fired
