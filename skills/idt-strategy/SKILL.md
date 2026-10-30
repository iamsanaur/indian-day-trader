---
name: idt-strategy
description: Build and analyse Indian F&O option strategies - long/short calls and puts, bull/bear spreads, straddles, strangles, iron condors, iron flies and custom legs - with payoff at expiry, breakevens, max profit/loss, net Greeks, margin from the broker API and a payoff chart. Includes option selling; naked shorts are blocked by the risk check unless allow_naked is enabled. Use when the user wants to set up an options trade or compare strategies.
---

# Options Strategy Builder (`/idt-strategy`)

## Commands

```bash
idt strategy list
idt strategy bull-call-spread NIFTY --width 4 --chart          # buy ATM CE, sell 4 strikes higher
idt strategy bear-put-spread BANKNIFTY --expiry monthly --width 2
idt strategy iron-condor NIFTY --delta 0.15 --width 2          # short strikes by |delta|, wings 2 strikes out
idt strategy short-strangle NIFTY --delta 0.2                  # naked: needs allow_naked
idt strategy short-straddle SENSEX --lots 1
idt strategy custom NIFTY --leg +1x26000CE --leg -1x26200CE --leg -1x25800PE --leg +1x25600PE
idt strategy bull-call-spread NIFTY --width 4 --write          # saves idt/strategy.json for /idt-exit
```

`--offset` = strike steps from ATM, `--width` = spread width / wing distance in steps, `--lots` = lots per leg.
Legs are priced at the ask when buying and the bid when selling.

## Reading the output

- `analysis.net_premium` (+ debit / - credit, in Rs for one set), `max_profit`, `max_loss`
  (`null` + `unlimited_*: true` when unbounded), `breakevens`, `naked`.
- `greeks` - position delta (in units of underlying), gamma, theta (Rs/day), vega (Rs per 1 IV point).
- `margin` - broker margin for the whole basket (hedge benefit included when the API supports it).
- `warning` - shown for naked shorts.

## Selling options - say this every time

Short options have large or unlimited losses, margin can be several lakh per lot, and expiry-day
gamma moves are violent. Prefer defined-risk (spreads, iron condor/fly) unless the user explicitly
wants naked and has set `allow_naked: true`. Expiry-day short entries are blocked by default
(`block_expiry_day_selling`). Never imply a credit is "free money".

Next: `/idt-exit` with `--kind strategy` to set the combined-P/L stop and target.
