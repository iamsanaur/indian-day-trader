---
name: idt-exit
description: Exit planner for Indian intraday trades - sets the stop and target before entry for cash equity, index/stock futures, single long options (stop on the underlying or on premium) and multi-leg option strategies (stop/target on combined P/L). Writes idt/plan.json. Use after a setup triggers or when the user asks where to put the stop/target.
---

# Exit Planner (`/idt-exit`)

Every trade gets a stop before entry. The plan reduces to `risk_per_unit` and `reward_per_unit` in
rupees (unit = 1 share, 1 lot, or 1 set of strategy legs).

## Commands

```bash
# From idt/setup.json (written by `idt entry check ... --write`)
idt exit plan --stop or-mid --target 1.5R --write                    # index -> long CE/PE by default
idt exit plan --kind equity --stop or-low --target 2R --write        # stock cash, MIS
idt exit plan --kind future --stop atr:1 --target 2R --write         # near-month future, basis-adjusted
idt exit plan --kind option --option CE --strike-offset 1 --stop premium-pct:30 --target 2R --write
# Manual levels
idt exit plan --symbol RELIANCE --side long --entry 1488.5 --kind equity --stop pct:0.5 --target 1R --write
# Strategy (from `idt strategy ... --write`)
idt exit plan --kind strategy --stop maxloss-pct:50 --target 1.5R --write
idt exit plan --kind strategy --stop credit-x:1 --target credit-pct:50 --write   # credit spreads/condors
```

### Rules

| Stop | Meaning |
|---|---|
| `or-mid` / `or-low` | opening-range midpoint / far side of the range |
| `atr:K` / `pct:N` / `price:X` | K x ATR(14, 5m) / N% from entry / fixed level |
| `premium-pct:N` | options: exit if premium falls N% |
| `maxloss-pct:N` | strategies: N% of the defined max loss |
| `credit-x:N` | credit strategies: exit when the loss equals N x credit |
| `pnl:-X` | strategies: fixed rupee loss per set |

Targets: `NR` (R multiple), `pct:N`, `price:X`, `maxprofit-pct:N`, `credit-pct:N`, `pnl:X`.

Options with an underlying stop are repriced with Black-Scholes at the stop/target levels, anchored to
the traded premium. Show the user entry, stop, target, R:R and rupees at risk per unit. Next: `/idt-timemachine`.
