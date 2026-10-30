---
name: idt-broker
description: Builds a broker-neutral order ticket (exchange, segment, symbol, product MIS/NRML/CNC, LIMIT/SL orders, quantity in lots, stop and target exits) for an Indian trade that passed the risk check, and records the user's explicit confirmation. Never places orders. Use when the user wants to execute or see the order for a planned trade.
---

# Order Ticket (`/idt-broker`)

This pack never sends orders. It produces a ticket the user places in their own broker
(Zerodha, Upstox, Dhan, Angel, Groww, ...), and logs the decision.

## Flow

1. `idt ticket show`. This fails unless `idt/risk.json` is a PASS for the current `orders.json` hash and under 10 minutes old.
2. Show the ticket clearly: each entry leg (BUY/SELL, symbol, qty = lots x lot size, LIMIT price, product),
   the exits (SL-limit trigger/limit, target, or the alert-based condition), loss at stop, profit at
   target, margin, charges.
3. Ask: **"Type yes to confirm order <hash>."** Proceed only on an explicit yes for that exact hash.
   Anything else (including "ok", "sure" or silence) means no.
4. On yes: `idt ticket confirm <hash>`. In paper mode this records a paper fill. In live mode, remind
   the user to place it in their broker now; nothing has been sent.
5. Offer `/idt-alerts` (`idt alerts add --from-plan`) to watch the stop, target and square-off.

## Notes for the user

- Stop and target are one-cancels-other: when one fills, cancel the other. Use the broker's GTT/OCO or
  bracket feature if available.
- NSE does not allow SL-M orders for options. The ticket uses SL-limit with a buffer.
- For multi-leg strategies, place the long (hedge) legs first, then the shorts, to get margin benefit.
  Exit shorts first.
- MIS positions are auto squared off by the broker near the close (usually 15:15-15:25), often with a fee.
