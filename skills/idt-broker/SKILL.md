---
name: idt-broker
description: >-
  Order Ticket for Indian trades. Builds a broker-neutral ticket (exchange, segment, symbol, product
  MIS/NRML, LIMIT entries on the tick, SL-limit stop and target exits or alert-based exits, quantity
  in lots x lot size) for a trade that passed /idt-risk, shows it in plain words, and records the
  user's explicit yes for that exact order hash. It never places an order: the user places it in
  their own broker. Use when the user says "place the trade", "show me the order", "execute",
  "confirm", or after a PASS from /idt-risk.
argument-hint: "show | confirm HASH"
---

# Order Ticket (`/idt-broker`)

This pack never sends orders. It produces a ticket the user places in their own broker (Zerodha,
Upstox, Dhan, Angel, Groww, ...) and logs the decision. Three things must hold before a ticket even
exists: `/idt-risk` passed this exact order (same hash), that PASS is under 10 minutes old, and the
user types yes for that hash in the chat.

```bash
idt ticket show                  # the ticket, or the reason there is none
idt ticket confirm <hash>        # only after the user typed yes for that hash
idt alerts add --from-plan       # then watch the stop, target and square-off
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/risk.json` | must be a PASS for the current `orders.json` hash, under 10 minutes old |
| `idt/orders.json`, `idt/plan.json` | legs, quantities, stop, target, charges, margin |
| `idt/journal.jsonl` | `confirm` appends the decision (feeds trades/day, daily loss and duplicates) |

## The ticket

- **Entries**: one LIMIT order per leg at the planned price, rounded to the tick (a buy rounds up, a
  sell down, so it is never less marketable than planned). Quantity = lots x lot size.
- **Exits** depend on the plan:
  - equity, futures, options with a premium stop: an SL-limit stop (trigger at the stop, limit a buffer
    past it; NSE does not allow SL-M for options) and a LIMIT target. They are one-cancels-other.
  - options with an underlying stop: exit the option when the underlying crosses the stop (alert-based),
    plus a LIMIT target on the premium.
  - strategies: close all legs when the combined P/L reaches the stop or the target (alert-based).
- **Order of legs**: for strategies, buy the long (hedge) legs first, then sell the shorts, for margin
  benefit. On exit, buy back the shorts first, then sell the longs.

## Steps

1. `idt ticket show`. If it fails, say why (no PASS, the order changed, the PASS is old) and go back to
   `/idt-budget` and `/idt-risk`. Never work around it.
2. Show the ticket in plain words: each entry leg (BUY/SELL, symbol, quantity = lots x lot size, LIMIT
   price, product), each exit (SL trigger and limit, target, or the alert condition), the loss at the
   stop, the profit at the target, the margin and the charges. Say the mode (paper or live).
3. Ask: **"Type yes to confirm order <hash>."** Proceed only on an explicit yes for that exact hash.
   Anything else ("ok", "sure", "go", silence, a yes for another hash) means no.
4. On yes: `idt ticket confirm <hash>`. Paper mode records a paper fill at the planned prices. Live
   mode: remind the user to place it in their broker now; nothing has been sent.
5. If the user wants the reason behind it, `idt ticket show --reason` (or `/idt-explain`) adds the
   explanation. Show it as returned; never add numbers to it.
6. Offer `/idt-alerts` (`idt alerts add --from-plan`) for the stop, the target and the square-off.

## Example (fixtures, 2026-10-29 09:45)

```
PAPER  order <hash>  NIFTY 2026-11-03 26000 CE
  BUY   65 (1 lot)  NIFTY 2026-11-03 26000 CE  LIMIT 156.90  MIS  NSE FNO
  Stop: SELL 65 when NIFTY falls below 25,945 (premium about 132.00). `idt alerts` watches it.
  Target: SELL 65 LIMIT 199.15 (NIFTY about 26,070).
  Loss at stop Rs 1,684.71 incl. charges. Square off by 15:15.
Type yes to confirm order <hash>.
```

## Notes for the user

- Stop and target are one-cancels-other: when one fills, cancel the other. Use the broker's GTT/OCO or
  bracket feature if it has one.
- MIS positions are auto squared off by the broker near the close (usually 15:15-15:25), often with a fee.
- A stop is an order, not a guarantee: in a fast market or a gap it can fill past the stop.

## What it never does

It never sends an order, never confirms without an explicit yes for that hash, never builds a ticket
from a BLOCK or an old PASS, and never runs from a background job: nobody is there to say yes.

## Safety

- Education and tooling, not investment advice. A PASS is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. A ticket exists only after `/idt-risk` passed that exact order
  hash in the last 10 minutes, and is confirmed only when the user typed yes for that hash.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
