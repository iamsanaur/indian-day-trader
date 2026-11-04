---
name: idt-budget
description: >-
  Budget Manager for Indian trades. Turns a plan into an exact size: shares or F&O lots from the max
  loss per trade, re-measured from a fresh price, capped by capital/leverage and available margin,
  with Indian charges (brokerage, STT, exchange fee, SEBI fee, stamp duty, GST) counted inside the
  max loss. Writes idt/orders.json for /idt-risk. Use after /idt-exit (and /idt-timemachine), or
  when the user asks "how many lots", "how many shares", "size this trade", "what are the charges".
argument-hint: "[--max-loss RUPEES] [--write]"
---

# Budget Manager (`/idt-budget`)

The Budget Manager turns a plan ("long NIFTY 26000 CE at 156.87, stop 132.00") into an exact order
("1 lot, 65 qty"), inside rules the user sets once. The stop decides the size: the further away the
stop, the fewer units. It writes a proposal only. `/idt-risk` checks it and `/idt-broker` asks the
user yes or no. Sizing to a max loss keeps each loss small; it does not make a trade win.

```bash
idt size                       # preview
idt size --write               # save idt/orders.json for the risk check
idt size --max-loss 2000       # what-if (the risk check still enforces config max_loss_per_trade)
idt charges --segment opt --buy 10196 --sell 12000            # one round trip
idt charges --segment eq_intraday --buy 148850 --sell 150150
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/plan.json` | today's plan from `/idt-exit` (a plan from another day is refused) |
| `idt/config.json` | `capital`, `max_loss_per_trade`, `leverage_cap`, `brokerage`, `charges_override`, `mode` |
| live quote | the underlying (or the option, for a premium stop): re-measures risk; its time feeds the stale-price check |
| broker margin API | basket margin with hedge benefit; a rough estimate if unavailable |
| funds | live mode: available funds from Dhan; paper mode: `capital` |
| `idt/orders.json` | with `--write`: legs, units, loss at stop incl. charges, margin, `rr`, `limits`, `decided_by`, hash |

## Step 1: set the rules once

If `idt/config.json` does not exist, run `idt init` and ask the user for each value in plain words:
`capital` (only money they can afford to lose), `max_loss_per_trade` (the most one trade may lose at
the stop, charges included), `daily_loss_cap`, `max_trades_per_day`, `min_reward_risk` (1.0),
`leverage_cap` for MIS equity, and keep `mode` on `paper` until they have watched it work.

## Step 2: size the trade

1. **Fresh price.** The risk is measured from the WORSE of the plan's entry and the live price: for a
   long, the higher one. A price that ran toward the target since the plan means more risk to the same
   stop and less reward left, so fewer units and a lower `rr`. A lower price never shrinks the risk.
   If the price is already at or past the target, it refuses: the move happened. Options stopped on the
   underlying are scaled by the distance on the underlying; premium stops use the option's own price.
2. **Max loss.** `units = floor(max_loss / risk_per_unit)`. Zero units: refused, with the fix.
3. **Caps.** Equity: `capital x leverage_cap / price`. F&O: available margin (units are reduced to fit).
4. **Charges.** Round-trip charges if stopped are computed for that size, and units drop one at a time
   until `loss_at_stop = risk x units + charges` fits inside the max loss.

`limits` shows each cap in units and `decided_by` names the one that set the size. F&O quantity is
always `lots x lot_size`, with the lot size read live from the instrument master. Never quote a
remembered lot size: exchanges revise them.

Charges (rates effective 2026-04-01, editable via `charges_override`): STT 0.025% on intraday equity
sells, 0.05% on futures sells, 0.15% of the premium on option sells; exchange fees; SEBI Rs 10 per
crore; buy-side stamp duty; 18% GST on brokerage and fees.

## Step 3: show the user

Show the units and which limit decided them, the quantity, the rupees at risk at the stop including
charges, the charges if stopped and if the target fills, the margin, and any `notes` (repriced from a
fresh price, reduced for charges or margin). Say plainly that a stop is an order, not a promise: in a
fast market it can fill past the stop. Then hand over to `/idt-risk`.

## Example (fixtures, 2026-10-29, `max_loss_per_trade` 3000)

| plan | risk a unit | size | loss at stop |
| --- | --- | --- | --- |
| 26000 CE, stop on NIFTY 25,945 | Rs 1,616.55 a lot | 1 lot (65), decided by max loss | Rs 1,684.71 incl. Rs 68.16 charges |
| bull call spread 26000/26200, stop -50% of max loss | Rs 2,702.05 a set | 1 set, decided by max loss | Rs 2,831.81 incl. Rs 129.76 charges |
| NIFTY future, stop 26,005 | Rs 3,250 a lot | refused: one lot is above the Rs 3,000 max loss | - |

A fresh price changes the answer. Same option plan, sized after NIFTY ran up:

- NIFTY at 26,025: risk to the same 25,945 stop re-measures to Rs 2,586.48 a lot and the reward left to
  Rs 1,648.92, so reward:risk is 0.64. It sizes 1 lot, and `/idt-risk` blocks it: "reward:risk: 0.64,
  under the minimum 1, measured from the current price 26025". The move it was waiting for has mostly happened.
- NIFTY at 26,040: Rs 3,071 a lot, above the Rs 3,000 max loss. No order.

## Rules

- Never round up to make a trade fit. If one unit exceeds the max loss, say so and suggest a tighter
  stop, a spread instead of a naked option, a cheaper strike, or skipping it.
- Every number comes from the plan, the config, the quote, the margin API or the charges table.

## What it never does

It never places an order, never changes the plan or the stop, and never raises a limit.

## Safety

- Education and tooling, not investment advice. A PASS from `/idt-risk` is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
