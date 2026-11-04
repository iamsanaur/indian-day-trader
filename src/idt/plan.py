"""Exit planner: stop and target set before entry, for equity, futures, single options or strategies.

Every plan reduces to `risk_per_unit` / `reward_per_unit` in rupees so sizing is uniform:
  equity  unit = 1 share         future/option  unit = 1 lot         strategy  unit = 1 set of legs
"""

from __future__ import annotations

import math
from datetime import date, datetime

from . import fno
from .market import now_ist, years_to_expiry
from .strategy import Leg, analyze, legs_from_dicts, pnl_now


MIN_RISK_PCT = 0.05   # a stop closer than 0.05% of the price is inside normal noise and the spread
TICK = 0.05           # NSE/BSE F&O and most cash tick; equity plans pass the instrument's own tick


def _num(rule: str) -> float:
    return float(rule.split(":", 1)[1])


def to_tick(x: float, tick: float = TICK, mode: str = "nearest") -> float:
    """Round a price to the exchange tick. mode: nearest | down | up (orders off the tick are rejected)."""
    n = x / tick
    n = math.floor(n + 1e-9) if mode == "down" else math.ceil(n - 1e-9) if mode == "up" else math.floor(n + 0.5)
    return round(n * tick, 2)


def stop_to_tick(stop: float, side: str, tick: float = TICK) -> float:
    """A stop rounds AWAY from the entry: down for a long, up for a short (never tighter than the rule)."""
    return to_tick(stop, tick, "down" if side == "long" else "up")


def check_levels(side: str, entry: float, stop: float, target: float, what: str = "price") -> None:
    sign = 1 if side == "long" else -1
    if sign * (entry - stop) <= 0:
        raise ValueError(f"stop {stop:g} is on the wrong side of the entry {entry:g} for a {side}: "
                         "a long's stop must be below the entry, a short's above")
    if sign * (target - entry) <= 0:
        raise ValueError(f"target {target:g} is not beyond the entry {entry:g}: the move already happened. "
                         "Pick a farther target or skip the trade")
    if what == "price" and abs(entry - stop) < entry * MIN_RISK_PCT / 100:
        raise ValueError(f"stop {stop:g} is {abs(entry - stop):.2f} from the entry, under {MIN_RISK_PCT}% of the "
                         "price: normal noise and the spread would stop you out. Use a wider stop")


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
                contract: str, lot_size: int = 1, basis_offset: float = 0.0, tick: float = TICK) -> dict:
    """Equity or futures. basis_offset shifts index levels to the future's price (future - spot).

    The stop rounds to the tick away from the entry; the target is entry + R x risk on the rounded stop,
    rounded to the nearest tick.
    """
    side, entry = setup["side"], setup["entry"]
    stop = stop_to_tick(underlying_stop(stop_rule, side, entry, setup.get("range"), setup.get("atr")), side, tick)
    target = to_tick(target_from(target_rule, side, entry, stop), tick)
    check_levels(side, entry, stop, target)
    plan = _base(setup, kind, stop_rule, target_rule, squareoff)
    plan.update(basis="underlying", contract=contract, unit="share" if kind == "equity" else "lot",
                lot_size=lot_size, underlying_stop=stop, underlying_target=target,
                entry=to_tick(entry + basis_offset, tick), stop=stop_to_tick(stop + basis_offset, side, tick),
                target=to_tick(target + basis_offset, tick), tick=tick)
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
        stop = to_tick(leg.premium * (1 - _num(stop_rule) / 100), TICK, "down")
        target = to_tick(target_from(target_rule, "long", leg.premium, stop))
        check_levels("long", leg.premium, stop, target, "premium")
        plan.update(basis="premium", stop=stop, target=target)
    else:
        side, entry = setup["side"], setup["entry"]
        u_stop = stop_to_tick(underlying_stop(stop_rule, side, entry, setup.get("range"), setup.get("atr")), side)
        u_target = to_tick(target_from(target_rule, side, entry, u_stop))
        check_levels(side, entry, u_stop, u_target)
        t = years_to_expiry(date.fromisoformat(leg.expiry), moment)
        iv = max(leg.iv, 0.01)
        # Anchor the model to the traded premium so the stop/target are offsets from the real fill.
        model_entry = fno.bs_price(entry, leg.strike, t, r, iv, leg.kind)
        reprice = lambda s: max(TICK, leg.premium + fno.bs_price(s, leg.strike, t, r, iv, leg.kind) - model_entry)
        plan.update(basis="underlying", underlying_stop=u_stop, underlying_target=u_target,
                    stop=to_tick(reprice(u_stop), TICK, "down"), target=to_tick(reprice(u_target)))
        if plan["target"] <= plan["entry"] or plan["stop"] >= plan["entry"]:
            raise ValueError("the option barely moves between the stop and the target (deep OTM or near expiry); "
                             "pick a strike nearer the money or stop on premium (premium-pct:N)")
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
