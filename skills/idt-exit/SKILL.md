---
name: idt-exit
description: >-
  Exit Planner for NSE/BSE intraday trades. Decides how a trade ends before it starts: the stop
  (where the setup has failed), the target (an R multiple or a level) and the square-off time, for
  cash equity (MIS), index/stock futures, a single long option (stop on the underlying, repriced with
  Black-Scholes, or on premium) and multi-leg option strategies (stop/target on combined P/L). Rounds
  to the exchange tick, refuses a stop too tight to survive the spread or a target the price already
  passed, and writes idt/plan.json. Use right after /idt-entry triggers, or when the user asks "where
  do I put my stop", "set my target", "plan the exit", "what is my risk per lot".
argument-hint: "[--kind equity|future|option|strategy] [--stop RULE] [--target RULE]"
---

# Exit Planner (`/idt-exit`)

The Exit Planner decides how a trade ends before it starts. The stop is where the setup has failed.
The target is where you take what you came for. Both are set BEFORE the entry, written down and
handed on, so nobody decides anything in the middle of a fast move. A stop is a plan, not a
guarantee: a gap or a fast market can fill past it, and options can jump through a stop.

Every plan reduces to `risk_per_unit` and `reward_per_unit` in rupees, so sizing works the same way
for everything (unit = 1 share, 1 lot, or 1 set of strategy legs).

```bash
# From idt/setup.json (written by `idt entry check ... --write`)
idt exit plan --stop or-mid --target 1.5R --write                    # index -> ATM long CE/PE by default
idt exit plan --kind future --stop atr:1 --target 2R --write         # near-month future, basis-adjusted
idt exit plan --kind option --option CE --strike-offset 1 --stop premium-pct:30 --target 2R --write
idt exit plan --kind equity --stop or-low --target 2R --write        # stock cash, MIS
# Plan ahead without a trigger, or from manual levels
idt exit plan --symbol RELIANCE --side long --entry 1488.5 --kind equity --stop pct:0.5 --target 1R --write
# Strategy (from `idt strategy ... --write`)
idt exit plan --kind strategy --stop maxloss-pct:50 --target 1.5R --write
idt exit plan --kind strategy --stop credit-x:1 --target credit-pct:50 --write   # credit spreads/condors
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/setup.json` | the trigger from `/idt-entry`: symbol, side, entry, range, ATR, trigger time |
| `idt/strategy.json` | with `--kind strategy`: the legs from `/idt-strategy` |
| option chain | with `--kind option`: the strike's premium and IV |
| `idt/config.json` | `squareoff` (15:15), `risk_free_rate` |
| `idt/plan.json` | with `--write`: read by `/idt-timemachine`, `/idt-budget`, `/idt-risk`, `/idt-alerts` |

## Stops and targets

| stop | where it goes |
| --- | --- |
| `or-mid` | the opening-range midpoint (the default for an ORB) |
| `or-low` | the far side of the range (low for longs, high for shorts): wider, so fewer units |
| `atr:K` | K x ATR(14) of the 5-minute bars, from the entry |
| `pct:N` / `price:X` | N% from the entry / a price you name |
| `premium-pct:N` | single options: exit if the premium falls N% |
| `maxloss-pct:N` | strategies: N% of the defined max loss |
| `credit-x:N` | credit strategies: exit when the loss equals N x the credit |
| `pnl:-X` | strategies: a fixed rupee loss per set |

Targets: `NR` (R multiple, default 1.5R), `pct:N`, `price:X`, `maxprofit-pct:N`, `credit-pct:N`, `pnl:X`.
A manual setup without a range defaults to `pct:0.5`. A level setup has no range to lean on: ask the
user for a stop.

- **Rounding.** The stop rounds to the tick AWAY from the entry (down for a long, up for a short), so
  it is never tighter than the rule. The target is entry + R x risk on the rounded stop, rounded to the
  nearest tick. Equity uses the instrument's tick; F&O uses 0.05.
- **Futures** are planned on the index levels and shifted by the basis (future minus spot).
- **Options with an underlying stop** are repriced with Black-Scholes at the stop and target levels,
  anchored to the traded premium, so `rr` can differ from the R you asked for (convexity).
- **Refused, with the reason:** a stop on the wrong side of the entry; a target at or behind the entry
  (the move already happened); a stop under 0.05% of the price from the entry (inside normal noise and
  the spread); an option that barely moves between stop and target (deep OTM or near expiry); a
  setup.json that has not triggered (unless you pass `--entry`); a plan at or after the square-off.
- **Square-off.** `squareoff` (15:15) by default: flat by then, win or lose, before the broker's MIS
  auto square-off.

## Steps

1. Run it right after `/idt-entry` triggers. Before that, `--symbol/--side/--entry` plans ahead.
2. Use the default stop for an ORB unless the user names another. For an index, the default
   instrument is the ATM option in the trigger's direction; offer the future or a spread if the user
   prefers.
3. Run `idt exit plan ... --write`. Read back the entry, the stop and its rule, the target and its rule,
   rupees at risk per unit, reward:risk and the square-off time.
4. If it refuses, say the reason and the fix (a wider stop, a farther target, a nearer strike). Never
   loosen anything on your own.
5. Say once that the stop is a plan, not a guarantee.
6. Hand off to `/idt-timemachine` to replay the plan, then `/idt-budget` to size it.

## Example (fixtures, 2026-10-29)

NIFTY triggered long at 25,995 (09:40), range 25,905 to 25,985. `idt exit plan --stop or-mid --target 1.5R --write`:

```
NIFTY 2026-11-03 26000 CE, long, 1 lot = 65
  Entry      156.87 premium (NIFTY 25,995)
  Stop       132.00  when NIFTY hits 25,945 (range midpoint), repriced with Black-Scholes
  Target     199.15  when NIFTY hits 26,070 (1.5R on the index)
  Risk       Rs 1,616.55 a lot    Reward:risk 1.70    Flat by 15:15
```

The same trigger as a future (`--kind future`): entry 26,055, stop 26,005, target 26,130 on the
future (index 25,945 / 26,070 plus the 60-point basis), Rs 3,250 at risk a lot.

## Rules

- The stop and the target are set before the entry, never after.
- Never move a stop further from the entry once the trade is on.
- Plain numbers only: entry, stop, target, risk per unit, reward:risk. Never a P&L promise.
- A target is not a prediction that the price gets there.

## What it never does

It never places an order, never sizes a position, never widens a stop to make a plan pass, and never
calls a stop a guarantee.

## Safety

- Education and tooling, not investment advice. A PASS from `/idt-risk` is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
