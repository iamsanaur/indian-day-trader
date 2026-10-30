"""Exit planner: stop and target set before entry, for equity, futures, single options or strategies.

Every plan reduces to `risk_per_unit` / `reward_per_unit` in rupees so sizing is uniform:
  equity  unit = 1 share         future/option  unit = 1 lot         strategy  unit = 1 set of legs
"""

from __future__ import annotations

from datetime import date, datetime

from . import fno
from .market import now_ist, years_to_expiry
from .strategy import Leg, analyze, legs_from_dicts, pnl_now


def _num(rule: str) -> float:
    return float(rule.split(":", 1)[1])


def underlying_stop(rule: str, side: str, entry: float, rng: dict | None = None, atr: float | None = None) -> float:
    sign = 1 if side == "long" else -1
    if rule == "or-mid":
        return _need(rng, rule)["mid"]
    if rule == "or-low":     # the far side of the range: low for longs, high for shorts
        return _need(rng, rule)["low" if side == "long" else "high"]
    if rule.startswith("atr:"):
        return round(entry - sign * _num(rule) * _need(atr, rule), 2)
    if rule.startswith("pct:"):
        return round(entry * (1 - sign * _num(rule) / 100), 2)
    if rule.startswith("price:"):
        return _num(rule)
    raise ValueError(f"unknown stop rule {rule}")


def _need(value, rule):
    if value is None:
        raise ValueError(f"stop rule {rule} needs setup data (run `idt entry check ... --write` first)")
    return value


def target_from(rule: str, side: str, entry: float, stop: float) -> float:
    sign = 1 if side == "long" else -1
    if rule.upper().endswith("R"):
        return round(entry + sign * float(rule[:-1]) * abs(entry - stop), 2)
    if rule.startswith("pct:"):
        return round(entry * (1 + sign * _num(rule) / 100), 2)
    if rule.startswith("price:"):
        return _num(rule)
    raise ValueError(f"unknown target rule {rule}")


def _base(setup: dict, kind: str, stop_rule: str, target_rule: str, squareoff: str) -> dict:
    return {"symbol": setup["symbol"], "kind": kind, "side": setup["side"], "setup": setup.get("setup", "manual"),
            "underlying_entry": setup["entry"], "stop_rule": stop_rule, "target_rule": target_rule,
            "squareoff": squareoff, "created": now_ist().isoformat(), "trigger_time": setup.get("trigger_time")}


def _finish(plan: dict) -> dict:
    risk, reward = plan["risk_per_unit"], plan["reward_per_unit"]
    if risk <= 0:
        raise ValueError("stop is on the wrong side of entry: risk per unit must be positive")
    plan["rr"] = round(reward / risk, 2)
    return plan


def linear_plan(setup: dict, kind: str, stop_rule: str, target_rule: str, squareoff: str,
                contract: str, lot_size: int = 1, basis_offset: float = 0.0) -> dict:
    """Equity or futures. basis_offset shifts index levels to the future's price (future - spot)."""
    side, entry = setup["side"], setup["entry"]
    stop = underlying_stop(stop_rule, side, entry, setup.get("range"), setup.get("atr"))
    target = target_from(target_rule, side, entry, stop)
    plan = _base(setup, kind, stop_rule, target_rule, squareoff)
    plan.update(basis="underlying", contract=contract, unit="share" if kind == "equity" else "lot",
                lot_size=lot_size, underlying_stop=stop, underlying_target=target,
                entry=round(entry + basis_offset, 2), stop=round(stop + basis_offset, 2), target=round(target + basis_offset, 2))
    plan["risk_per_unit"] = round(abs(entry - stop) * lot_size, 2)
    plan["reward_per_unit"] = round(abs(target - entry) * lot_size, 2)
    return _finish(plan)


def option_plan(setup: dict, leg: Leg, lot_size: int, stop_rule: str, target_rule: str, squareoff: str,
                r: float, moment: datetime | None = None) -> dict:
    """Long CE/PE. Stop either on the underlying (repriced via Black-Scholes) or on premium (premium-pct:N)."""
    moment = moment or now_ist()
    plan = _base(setup, "option", stop_rule, target_rule, squareoff)
    plan.update(contract=leg.symbol, unit="lot", lot_size=lot_size, legs=[leg.to_dict()], expiry=leg.expiry,
                entry=leg.premium)
    if stop_rule.startswith("premium-pct:"):
        stop = round(leg.premium * (1 - _num(stop_rule) / 100), 2)
        target = target_from(target_rule, "long", leg.premium, stop)
        plan.update(basis="premium", stop=stop, target=target)
    else:
        side, entry = setup["side"], setup["entry"]
        u_stop = underlying_stop(stop_rule, side, entry, setup.get("range"), setup.get("atr"))
        u_target = target_from(target_rule, side, entry, u_stop)
        t = years_to_expiry(date.fromisoformat(leg.expiry), moment)
        iv = max(leg.iv, 0.01)
        # Anchor the model to the traded premium so the stop/target are offsets from the real fill.
        model_entry = fno.bs_price(entry, leg.strike, t, r, iv, leg.kind)
        reprice = lambda s: round(max(0.05, leg.premium + fno.bs_price(s, leg.strike, t, r, iv, leg.kind) - model_entry), 2)
        plan.update(basis="underlying", underlying_stop=u_stop, underlying_target=u_target,
                    stop=reprice(u_stop), target=reprice(u_target))
    plan["risk_per_unit"] = round((plan["entry"] - plan["stop"]) * lot_size, 2)
    plan["reward_per_unit"] = round((plan["target"] - plan["entry"]) * lot_size, 2)
    return _finish(plan)


def strategy_plan(strat: dict, stop_rule: str, target_rule: str, squareoff: str, side: str | None = None) -> dict:
    """Multi-leg: stop/target as combined P/L per set, in rupees.

    stop rules:   maxloss-pct:N  (N% of defined max loss)   credit-x:N  (loss = N x credit received)
                  pnl:-AMOUNT
    target rules: maxprofit-pct:N   credit-pct:N (keep N% of credit)   NR   pnl:AMOUNT
    """
    legs = legs_from_dicts(strat["legs"])
    lot = int(strat["lot_size"])
    a = analyze(legs, strat["spot"], lot)
    credit = -a["net_premium"] if a["premium_type"] == "credit" else 0.0

    if stop_rule.startswith("maxloss-pct:"):
        if a["unlimited_loss"]:
            raise ValueError("max loss is unlimited; use credit-x:N or pnl:-AMOUNT")
        stop_pnl = a["max_loss"] * _num(stop_rule) / 100
    elif stop_rule.startswith("credit-x:"):
        if not credit:
            raise ValueError("credit-x applies to credit strategies only")
        stop_pnl = -credit * _num(stop_rule)
    elif stop_rule.startswith("pnl:"):
        stop_pnl = -abs(_num(stop_rule))
    else:
        raise ValueError(f"unknown strategy stop rule {stop_rule}")

    if target_rule.startswith("maxprofit-pct:"):
        if a["unlimited_profit"]:
            raise ValueError("max profit is unlimited; use NR or pnl:AMOUNT")
        target_pnl = a["max_profit"] * _num(target_rule) / 100
    elif target_rule.startswith("credit-pct:"):
        target_pnl = credit * _num(target_rule) / 100
    elif target_rule.upper().endswith("R"):
        target_pnl = abs(stop_pnl) * float(target_rule[:-1])
    elif target_rule.startswith("pnl:"):
        target_pnl = abs(_num(target_rule))
    else:
        raise ValueError(f"unknown strategy target rule {target_rule}")

    setup = {"symbol": strat["underlying"], "side": side or strat.get("view", "neutral"), "entry": strat["spot"],
             "setup": strat["name"]}
    plan = _base(setup, "strategy", stop_rule, target_rule, squareoff)
    plan.update(basis="pnl", contract=None, unit="set", lot_size=lot, legs=strat["legs"], expiry=strat["expiry"],
                strategy=strat["name"], entry=a["net_premium"], stop_pnl=round(stop_pnl, 2),
                target_pnl=round(target_pnl, 2), analysis=a,
                risk_per_unit=round(abs(stop_pnl), 2), reward_per_unit=round(target_pnl, 2))
    return _finish(plan)


def plan_pnl_now(plan: dict, spot: float, moment: datetime, r: float) -> float:
    """Model P/L per unit for an option/strategy plan at a given underlying price."""
    return float(pnl_now(legs_from_dicts(plan["legs"]), spot, moment, r, plan["lot_size"]))
