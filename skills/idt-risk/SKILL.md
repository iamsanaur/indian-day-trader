---
name: idt-risk
description: >-
  Risk Manager for Indian intraday and F&O trades. The gate between a sized proposal and a ticket:
  PASS or BLOCK for idt/orders.json against the entry window, entry cutoff and square-off, the daily
  loss cap (full max loss of every entry today), max trades, duplicates, loss at stop incl. charges,
  minimum reward:risk at the current price, leverage, shorting and naked-option permissions, F&O ban
  list, expiry-day selling, minimum premium, margin and stale prices. A BLOCK is final for that
  order. Use before any ticket, or when the user asks "can I take this trade", "check my limits",
  "is this within my risk".
argument-hint: "check"
---

# Risk Manager (`/idt-risk`)

The Risk Manager is the gate between a proposal and a ticket. Every order written by `/idt-budget`
passes through it. A BLOCK is final for that order: it does not go to the user for a yes and no ticket
is built. These limits keep each loss and each day's losses small. They do not make a trade win.

```bash
idt risk check        # reads idt/plan.json + idt/orders.json, writes idt/risk.json
idt status            # today's trades, realised P/L and limits
idt journal close --pnl -850 --symbol NIFTY     # record a closed trade (feeds the cap and duplicates)
idt ban               # today's NSE F&O ban list
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/plan.json`, `idt/orders.json` | the plan and the sized order (matched by symbol, kind and hash) |
| `idt/config.json` | the limits |
| `idt/journal.jsonl` | today's confirmed entries (`ticket confirm`) and closes (`journal close`) |
| NSE ban list | stock F&O only |
| funds | live mode: Dhan available funds; paper: `capital` |
| `idt/risk.json` | the verdict, bound to the order hash and timestamp |

## The checks (any failure = BLOCK)

| check | blocks when |
| --- | --- |
| market open | not 09:15-15:30 on a trading day (weekends, `holidays`) |
| entry window opens | before `no_entries_before` (09:30): the opening range is still forming |
| entry cutoff | at or after `entry_cutoff` (15:00) |
| time to square-off | at or after the plan's `squareoff` |
| daily loss cap | the max loss at the stop of every entry confirmed today, plus this one, over `daily_loss_cap`. Realised losses count too, whichever is larger |
| max trades/day | `max_trades_per_day` entries already confirmed today |
| no duplicate | the same symbol and kind already confirmed today and not closed |
| loss within budget | loss at the stop including charges over `max_loss_per_trade` |
| reward:risk | `rr` (measured from the current price by `/idt-budget`) under `min_reward_risk` (1.0) |
| stop defined | no stop |
| order matches plan / sized today | orders.json is from another plan or another day |
| shorting allowed | short equity or futures while `allow_short` is false |
| leverage cap | MIS equity notional over `capital x leverage_cap` |
| naked options | short options not covered lot for lot while `allow_naked` is false |
| minimum premium | a leg under `min_premium` (Rs 5): illiquid, wide spreads |
| expiry-day selling | short options expiring today while `block_expiry_day_selling` is true |
| F&O ban list | a stock in today's ban (no fresh F&O positions); ban list unavailable and `require_ban_check` true |
| margin available | margin needed over available funds, or funds unknown |
| fresh prices | the sizing quote is older than `stale_quote_seconds` (60): re-run `idt size` |

How the numbers work:

- **Daily loss** counts the full max loss of every entry confirmed today, win or lose, the way the
  original Risk Manager does: with a Rs 3,000 cap, three Rs 1,000 trades use up the day.
- **Duplicates** clear once `idt journal close --symbol SYMBOL` is logged after the entry.
- **Reward:risk** uses the price at sizing time, not the plan's, so a plan written at 09:40 cannot hide
  a move that already happened by 10:20.

## Steps

1. If the price may have moved since sizing, re-run `idt size --write` first (fresh prices are
   required anyway).
2. Run `idt risk check`.
3. Tell the user the result in plain words: the loss at the stop, reward:risk, and how much of today's
   limits it uses (trades and daily loss). For a BLOCK, give each reason and its fix (fewer lots, a
   closer stop from `/idt-exit`, wait for the window, close the open trade first, or skip it).
4. Never change a limit yourself, and never suggest editing the config just to get past a block. If
   the user changes limits themselves, that is their decision: re-run.
5. On PASS, offer `/idt-broker`. The verdict is bound to the order hash and expires after 10 minutes;
   any re-size needs a new check.

## Example (fixtures, 2026-10-29 09:45, `max_loss_per_trade` 3000)

```
PASS  NIFTY 2026-11-03 26000 CE, 1 lot (65)
      loss at stop Rs 1,684.71 incl. charges (max Rs 3,000), reward:risk 1.70 (min 1)
      today before this: 0 of 5 trades, Rs 0 of Rs 3,000 daily loss
```

The same order at 09:20 is blocked by the entry window. Sized after NIFTY ran to 26,025 it is blocked
by reward:risk (0.64, under the minimum 1). A second NIFTY option entry while the first is still open
is blocked as a duplicate.

## Rules

- A PASS only means the order may be shown to the user. It is not a yes and not a recommendation.
- Every number comes from the config, the order, the journal, the ban list or the broker.

## What it never does

It never places an order, never edits a limit, never re-sizes to make an order pass, and never treats
an old verdict as current.

## Safety

- Education and tooling, not investment advice. A PASS is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
