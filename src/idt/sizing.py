"""Budget manager: units = floor(max loss / risk per unit), capped by capital and margin, with charges."""

from __future__ import annotations

import hashlib
import json
import math

from . import charges as chg
from .market import now_ist


def order_hash(orders: dict) -> str:
    core = {k: orders[k] for k in ("legs", "stop", "target", "units") if k in orders}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _legs(plan: dict, units: int, product: str) -> list[dict]:
    if plan["kind"] in ("equity", "future"):
        side = "BUY" if plan["side"] == "long" else "SELL"
        lots = units if plan["kind"] == "future" else None
        qty = units * plan["lot_size"] if plan["kind"] == "future" else units
        return [{"symbol": plan["contract"], "side": side, "quantity": qty, "lots": lots,
                 "price": plan["entry"], "product": product}]
    return [{"symbol": l["symbol"], "side": "BUY" if l["side"] > 0 else "SELL", "lots": l["lots"] * units,
             "quantity": l["lots"] * units * plan["lot_size"], "price": l["premium"], "product": product,
             "security_id": l.get("security_id", "")}
            for l in plan["legs"]]


def _round_trip_charges(plan: dict, legs: list[dict], exit_kind: str, cfg: dict, exchange: str) -> float:
    """Charges if the whole position is closed at the stop or the target."""
    seg = chg.segment_for(plan["kind"] if plan["kind"] != "strategy" else "option", legs[0]["product"])
    total = 0.0
    for leg in legs:
        q = leg["quantity"]
        entry_val = leg["price"] * q
        if plan["kind"] in ("equity", "future", "option"):
            exit_price = plan["stop"] if exit_kind == "stop" else plan["target"]
        else:  # strategy: approximate exit value per leg by entry premium (charges are dominated by entry)
            exit_price = leg["price"]
        exit_val = exit_price * q
        buy, sell = (entry_val, exit_val) if leg["side"] == "BUY" else (exit_val, entry_val)
        total += chg.compute(seg, buy, sell, exchange, 2, cfg["brokerage"], cfg.get("charges_override"))["total"]
    return round(total, 2)


def size(plan: dict, cfg: dict, margin_fn=None, available: float | None = None, quote_ts: str | None = None,
         exchange: str = "NSE", max_loss: float | None = None, now=None) -> dict:
    max_loss = float(max_loss or cfg["max_loss_per_trade"])
    risk = float(plan["risk_per_unit"])
    units = math.floor(max_loss / risk)
    notes = []
    if units < 1:
        raise ValueError(f"risk per {plan['unit']} is Rs {risk:,.0f}, above the max loss of Rs {max_loss:,.0f}. "
                         "Tighten the stop, use a spread, or raise max_loss_per_trade.")

    product = cfg["product_intraday"]
    if plan["kind"] == "equity":
        cap = math.floor(cfg["capital"] * cfg["leverage_cap"] / plan["entry"])
        if units > cap:
            units = cap
            notes.append(f"capped by leverage {cfg['leverage_cap']}x on capital")

    legs = _legs(plan, units, product)
    margin = None
    if margin_fn and plan["kind"] != "equity":
        try:
            margin = margin_fn(legs)
        except Exception as exc:  # margin is advisory here; risk check enforces availability
            notes.append(f"margin API unavailable: {exc}")
    if margin is None:
        margin = {"total": _estimate_margin(plan, legs, units, cfg), "source": "estimate"}

    if available is not None and margin["total"] > available and units > 1:
        per_unit = margin["total"] / units
        fit = math.floor(available / per_unit)
        if fit >= 1 and fit < units:
            units = fit
            notes.append("reduced to fit available margin")
            legs = _legs(plan, units, product)
            margin = {"total": round(per_unit * units, 2), "source": margin.get("source", "") + " (scaled)"}

    c_stop = _round_trip_charges(plan, legs, "stop", cfg, exchange)
    c_target = _round_trip_charges(plan, legs, "target", cfg, exchange)
    orders = {
        "created": (now or now_ist()).isoformat(), "mode": cfg["mode"], "kind": plan["kind"], "symbol": plan["symbol"],
        "units": units, "unit": plan["unit"], "lot_size": plan["lot_size"], "legs": legs,
        "stop": plan.get("stop", plan.get("stop_pnl")), "target": plan.get("target", plan.get("target_pnl")),
        "basis": plan["basis"], "max_loss_budget": max_loss,
        "loss_at_stop": round(risk * units + c_stop, 2), "profit_at_target": round(plan["reward_per_unit"] * units - c_target, 2),
        "charges": {"if_stopped": c_stop, "if_target": c_target}, "margin": margin, "quote_ts": quote_ts, "notes": notes,
        "exchange": exchange,
    }
    orders["hash"] = order_hash(orders)
    return orders


def _estimate_margin(plan: dict, legs: list[dict], units: int, cfg: dict) -> float:
    if plan["kind"] == "equity":
        return round(legs[0]["price"] * legs[0]["quantity"] / cfg["leverage_cap"], 2)
    debit = sum(l["price"] * l["quantity"] * (1 if l["side"] == "BUY" else -1) for l in legs)
    shorts = [l for l in legs if l["side"] == "SELL"]
    if not shorts:
        return round(max(debit, 0.0), 2)
    # Rough SPAN-like fallback when the broker margin API is unavailable. Defined risk -> max loss.
    # Otherwise ~7% SPAN on the heavier short side (calls and puts offset) + ~2% exposure on all shorts.
    a = plan.get("analysis") or {}
    if plan["kind"] == "strategy" and a.get("max_loss") is not None:
        return round(abs(a["max_loss"]) * units, 2)
    notional = lambda kind: sum(plan["underlying_entry"] * l["quantity"] for l in shorts if l["symbol"].endswith(kind))
    calls, puts = notional("CE"), notional("PE")
    other = sum(plan["underlying_entry"] * l["quantity"] for l in shorts if not l["symbol"].endswith(("CE", "PE")))
    return round(0.07 * (max(calls, puts) + other) + 0.02 * (calls + puts + other), 2)
