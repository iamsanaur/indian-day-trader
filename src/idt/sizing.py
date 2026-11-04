"""Budget manager: units = floor(max loss / risk per unit), capped by capital and margin, with charges."""

from __future__ import annotations

import hashlib
import json
import math

from . import charges as chg
from .market import now_ist


def order_hash(orders: dict) -> str:
    core = {k: orders[k] for k in ("legs", "stop", "target", "units", "loss_at_stop") if k in orders}
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


def reprice(plan: dict, ltp: float | None) -> dict:
    """Risk and reward per unit measured from the WORSE of the plan's entry and a fresh price.

    A price that ran toward the target since the plan means more risk to the same stop and less reward
    left, so fewer units. A price that moved the other way never shrinks the risk. Underlying-basis plans
    (equity, futures, options stopped on the underlying) scale by distance on the underlying; premium-basis
    options compare the option's own price. Strategies are measured on combined P/L and are not repriced.
    """
    risk, reward = float(plan["risk_per_unit"]), float(plan["reward_per_unit"])
    out = {"risk_per_unit": risk, "reward_per_unit": reward, "entry_now": None, "note": None}
    if ltp is None or plan["kind"] == "strategy":
        return out
    if plan["basis"] == "underlying":
        sign = 1 if plan["side"] == "long" else -1
        entry, stop, target = plan["underlying_entry"], plan["underlying_stop"], plan["underlying_target"]
    elif plan["basis"] == "premium":
        sign, entry, stop, target = 1, plan["entry"], plan["stop"], plan["target"]
    else:
        return out
    worse = max(sign * ltp, sign * entry) * sign
    out["entry_now"] = round(worse, 2)
    if worse == entry:
        return out
    base = abs(entry - stop)
    out["risk_per_unit"] = round(risk * abs(worse - stop) / base, 2)
    out["reward_per_unit"] = round(reward * sign * (target - worse) / abs(target - entry), 2) if target != entry else 0.0
    out["note"] = (f"price moved to {ltp:g} since the plan's {entry:g}: risk and reward re-measured from {worse:g}")
    return out


def size(plan: dict, cfg: dict, margin_fn=None, available: float | None = None, quote_ts: str | None = None,
         exchange: str = "NSE", max_loss: float | None = None, now=None, ltp: float | None = None) -> dict:
    now = now or now_ist()
    max_loss = float(max_loss or cfg["max_loss_per_trade"])
    rp = reprice(plan, ltp)
    risk, reward = rp["risk_per_unit"], rp["reward_per_unit"]
    notes = [rp["note"]] if rp["note"] else []
    if reward <= 0:
        raise ValueError(f"the price ({rp['entry_now']:g}) is already at or past the target: the move happened. "
                         "Skip it or make a new plan.")
    units = math.floor(max_loss / risk)
    limits = {"max_loss": units}
    if units < 1:
        raise ValueError(f"risk per {plan['unit']} is Rs {risk:,.0f}, above the max loss of Rs {max_loss:,.0f}. "
                         "Tighten the stop, use a spread, or raise max_loss_per_trade.")

    product = cfg["product_intraday"]
    if plan["kind"] == "equity":
        cap = math.floor(cfg["capital"] * cfg["leverage_cap"] / plan["entry"])
        limits["leverage"] = cap
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
        limits["margin"] = fit
        if fit >= 1 and fit < units:
            units = fit
            notes.append("reduced to fit available margin")
            legs = _legs(plan, units, product)
            margin = {"total": round(per_unit * units, 2), "source": margin.get("source", "") + " (scaled)"}

    # Charges come out of the same max loss: drop units until the loss at the stop, charges included, fits.
    c_stop = _round_trip_charges(plan, legs, "stop", cfg, exchange)
    while units > 1 and risk * units + c_stop > max_loss:
        per_unit_margin = margin["total"] / units
        units -= 1
        legs = _legs(plan, units, product)
        margin = dict(margin, total=round(per_unit_margin * units, 2))
        c_stop = _round_trip_charges(plan, legs, "stop", cfg, exchange)
        limits["charges"] = units
    if risk * units + c_stop > max_loss:
        raise ValueError(f"one {plan['unit']} loses Rs {risk * units + c_stop:,.0f} at the stop including charges, "
                         f"above the max loss of Rs {max_loss:,.0f}. Tighten the stop or use a spread.")
    if "charges" in limits:
        notes.append("reduced so the loss at the stop including charges stays within the max loss")
    c_target = _round_trip_charges(plan, legs, "target", cfg, exchange)
    orders = {
        "created": now.isoformat(), "mode": cfg["mode"], "kind": plan["kind"], "symbol": plan["symbol"],
        "units": units, "unit": plan["unit"], "lot_size": plan["lot_size"], "legs": legs,
        "stop": plan.get("stop", plan.get("stop_pnl")), "target": plan.get("target", plan.get("target_pnl")),
        "basis": plan["basis"], "max_loss_budget": max_loss,
        "risk_per_unit": risk, "reward_per_unit": reward, "rr": round(reward / risk, 2), "entry_now": rp["entry_now"],
        "limits": limits, "decided_by": min(limits, key=lambda k: limits[k]),
        "loss_at_stop": round(risk * units + c_stop, 2), "profit_at_target": round(reward * units - c_target, 2),
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
