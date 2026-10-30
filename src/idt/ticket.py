"""Broker-neutral order ticket. Built only from a fresh risk PASS whose hash matches orders.json.

Nothing here talks to a broker. The user places the ticket in their own broker app/API.
"""

from __future__ import annotations

from datetime import datetime

TICKET_MAX_AGE = 600  # seconds between risk PASS and ticket


class TicketError(RuntimeError):
    pass


def build(plan: dict, orders: dict, risk: dict | None, now: datetime, tick: float = 0.05) -> dict:
    if not risk or risk.get("verdict") != "PASS":
        raise TicketError("No risk PASS on file. Run `idt risk check` first.")
    if risk.get("order_hash") != orders.get("hash"):
        raise TicketError("orders.json changed since the risk check. Re-run `idt risk check`.")
    age = (now - datetime.fromisoformat(risk["ts"])).total_seconds()
    if age > TICKET_MAX_AGE:
        raise TicketError(f"Risk PASS is {age:.0f}s old (limit {TICKET_MAX_AGE}s). Re-run `idt size` and `idt risk check`.")

    entries = [{"action": l["side"], "symbol": l["symbol"], "exchange": orders.get("exchange", "NSE"),
                "segment": "EQ" if orders["kind"] == "equity" else "FNO", "product": l["product"],
                "order_type": "LIMIT", "price": l["price"], "quantity": l["quantity"], "lots": l.get("lots"),
                "validity": "DAY", "security_id": l.get("security_id", "")} for l in orders["legs"]]

    exits: list[dict] = []
    if plan["kind"] in ("equity", "future") or (plan["kind"] == "option" and plan["basis"] == "premium"):
        leg = orders["legs"][0]
        close_side = "SELL" if leg["side"] == "BUY" else "BUY"
        buffer = max(tick * 10, round(plan["stop"] * 0.002 / tick) * tick)
        sl_limit = plan["stop"] - buffer if close_side == "SELL" else plan["stop"] + buffer
        exits = [
            {"action": close_side, "symbol": leg["symbol"], "order_type": "SL", "trigger_price": plan["stop"],
             "price": round(round(max(sl_limit, tick) / tick) * tick, 2), "quantity": leg["quantity"],
             "product": leg["product"], "note": "stop-loss (SL-limit; SL-M is not allowed for options on NSE)"},
            {"action": close_side, "symbol": leg["symbol"], "order_type": "LIMIT", "price": plan["target"],
             "quantity": leg["quantity"], "product": leg["product"], "note": "target"},
        ]
        oco = "Stop and target are one-cancels-other: when one fills, cancel the other (or use your broker's GTT/OCO/bracket)."
    elif plan["kind"] == "option":
        exits = [{"action": "SELL", "symbol": orders["legs"][0]["symbol"], "order_type": "MARKET-ON-CONDITION",
                  "condition": f"{plan['symbol']} {'below' if plan['side'] == 'long' else 'above'} {plan['underlying_stop']}",
                  "estimated_premium": plan["stop"], "quantity": orders["legs"][0]["quantity"], "note": "stop on underlying"},
                 {"action": "SELL", "symbol": orders["legs"][0]["symbol"], "order_type": "LIMIT", "price": plan["target"],
                  "quantity": orders["legs"][0]["quantity"], "note": f"target (underlying ~{plan['underlying_target']})"}]
        oco = "Stop is on the underlying: `idt alerts` watches it. Exit the option when the alert fires."
    else:
        exits = [{"action": "CLOSE ALL LEGS", "condition": f"combined P/L <= Rs {orders['stop'] * orders['units']:,.0f}",
                  "note": "stop"},
                 {"action": "CLOSE ALL LEGS", "condition": f"combined P/L >= Rs {orders['target'] * orders['units']:,.0f}",
                  "note": "target"}]
        oco = ("Exit is on combined P/L: `idt alerts` watches it. Close buy-to-cover legs first, then sell longs, "
               "so margin is never short. Enter long (hedge) legs before short legs for margin benefit.")

    if plan["kind"] == "strategy":
        entries.sort(key=lambda e: 0 if e["action"] == "BUY" else 1)

    return {
        "mode": orders["mode"], "order_hash": orders["hash"], "symbol": plan["symbol"], "kind": plan["kind"],
        "entries": entries, "exits": exits, "oco": oco, "square_off": plan.get("squareoff"),
        "loss_at_stop": orders["loss_at_stop"], "profit_at_target": orders["profit_at_target"],
        "margin": orders["margin"], "charges": orders["charges"],
        "confirm": f"Type yes to confirm order {orders['hash']}. This records the decision; it does not place the order.",
    }
