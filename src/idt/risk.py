"""Risk manager: PASS or BLOCK for the sized order in orders.json. Any failed rule blocks."""

from __future__ import annotations

from datetime import date, datetime

from .market import at, index_info, parse_hhmm, phase
from .strategy import legs_from_dicts, naked_legs


def _today(entries: list[dict], day: date, kind: str) -> list[dict]:
    return [e for e in entries if e.get("type") == kind and str(e.get("ts", ""))[:10] == day.isoformat()]


def check(cfg: dict, plan: dict, orders: dict, journal: list[dict], now: datetime, *,
          ban_list: list[str] | None, available: float | None) -> dict:
    checks: list[dict] = []

    def rule(name: str, ok: bool, detail: str) -> None:
        checks.append({"rule": name, "ok": bool(ok), "detail": detail})

    day = now.date()
    realised = sum(float(e.get("pnl", 0)) for e in _today(journal, day, "close"))
    trades = len(_today(journal, day, "confirm"))

    rule("market open", phase(now, cfg.get("holidays")) == "open", f"phase: {phase(now, cfg.get('holidays'))}")
    rule("entry cutoff", now.time() < parse_hhmm(cfg["entry_cutoff"]), f"no new intraday entries after {cfg['entry_cutoff']}")
    rule("daily loss cap", realised > -cfg["daily_loss_cap"] and realised - orders["loss_at_stop"] >= -cfg["daily_loss_cap"],
         f"realised today Rs {realised:,.0f}; this trade can lose Rs {orders['loss_at_stop']:,.0f}; cap Rs {cfg['daily_loss_cap']:,.0f}")
    rule("max trades/day", trades < cfg["max_trades_per_day"], f"{trades} confirmed today, limit {cfg['max_trades_per_day']}")
    has_stop = plan.get("stop") is not None or plan.get("stop_pnl") is not None
    rule("stop defined", has_stop, "every trade needs a stop before entry")
    rule("loss within budget", orders["loss_at_stop"] <= cfg["max_loss_per_trade"] * 1.05,
         f"loss at stop incl. charges Rs {orders['loss_at_stop']:,.0f} vs max Rs {cfg['max_loss_per_trade']:,.0f}")
    rule("order matches plan", orders.get("symbol") == plan.get("symbol") and orders.get("kind") == plan.get("kind"),
         "orders.json was sized from the current plan.json")

    if plan["kind"] == "equity" and plan["side"] == "short":
        rule("shorting allowed", cfg["allow_short"], "allow_short is false in config")
    if plan["kind"] == "future" and plan["side"] == "short":
        rule("shorting allowed", cfg["allow_short"], "short futures need allow_short")
    if plan["kind"] == "equity":
        notional = sum(l["price"] * l["quantity"] for l in orders["legs"])
        rule("leverage cap", notional <= cfg["capital"] * cfg["leverage_cap"],
             f"notional Rs {notional:,.0f} vs {cfg['leverage_cap']}x capital")

    legs = legs_from_dicts(plan.get("legs") or [])
    shorts = [l for l in legs if l.side < 0 and l.kind in ("CE", "PE")]
    if legs:
        naked = naked_legs(legs)
        rule("naked options", cfg["allow_naked"] or not naked, "; ".join(naked) or "all short legs covered")
        cheap = [l.symbol for l in legs if l.kind != "FUT" and l.premium < cfg["min_premium"]]
        rule("minimum premium", not cheap, f"legs under Rs {cfg['min_premium']}: {', '.join(cheap)}" if cheap else "ok")
        if shorts and cfg["block_expiry_day_selling"]:
            on_expiry = any(l.expiry == day.isoformat() for l in shorts)
            rule("expiry-day selling", not on_expiry, "short options expiring today are blocked (block_expiry_day_selling)")

    if plan["kind"] in ("future", "option", "strategy") and index_info(plan["symbol"]) is None:
        if ban_list is None:
            rule("F&O ban list", not cfg["require_ban_check"], "ban list unavailable (require_ban_check)")
        else:
            rule("F&O ban list", plan["symbol"].upper() not in ban_list, f"{len(ban_list)} securities in ban today")

    need = float(orders["margin"]["total"])
    if available is None:
        rule("margin available", False, "available funds unknown")
    else:
        rule("margin available", need <= available, f"needs Rs {need:,.0f}, available Rs {available:,.0f} ({orders['margin'].get('source')})")

    if orders.get("quote_ts"):
        age = (now - datetime.fromisoformat(orders["quote_ts"])).total_seconds()
        rule("fresh prices", age <= cfg["stale_quote_seconds"], f"prices are {age:.0f}s old (limit {cfg['stale_quote_seconds']}s); re-run idt size")
    else:
        rule("fresh prices", False, "orders.json has no quote timestamp; re-run idt size")

    if plan.get("squareoff"):
        rule("time to square-off", now < at(day, plan["squareoff"]), f"square-off at {plan['squareoff']}")

    failed = [c for c in checks if not c["ok"]]
    return {"verdict": "BLOCK" if failed else "PASS", "reasons": [f"{c['rule']}: {c['detail']}" for c in failed],
            "checks": checks, "order_hash": orders["hash"], "ts": now.isoformat(), "mode": cfg["mode"]}
