---
name: idt-timemachine
description: >-
  Time Machine for NSE/BSE intraday plans. Before anything is sized, replays the rest of the session
  10,000 times from the instrument's own prior ~59 sessions of 5-minute bars (same time of day, plus
  or minus 2 bars, fixed seed), plus the same ORB rule on every past session, and gives the honest
  odds: target first, stop first, neither, green, average R, and a one-line verdict measured against
  break-even for the plan's reward:risk. Options and strategies are repriced with Black-Scholes. Use
  after /idt-exit, or when the user asks "what are the odds", "is this a good trade", "backtest
  this", "simulate the plan", "how often does this work".
argument-hint: "[--paths N] [--seed N] [--days N] [--window N]"
---

# Time Machine (`/idt-timemachine`)

The Time Machine sits between the plan and the money. `/idt-exit` has set the entry, the stop and the
target. Before anything is sized, this skill asks one question: if today plays out like this
instrument's own last ~60 sessions, how often does this plan hit the target first, the stop first,
or neither? It answers with 10,000 replays and with the real record of the same rule on every past
session. It is a simulation built from recent bars, not a prediction. A good-looking replay does not
make a trade win.

```bash
idt timemachine run                          # idt/plan.json, 10,000 paths, seed 42, prior 59 sessions
idt timemachine run --write                  # also save idt/timemachine.json
idt timemachine run --paths 20000 --seed 7 --days 40 --window 1
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/plan.json` | the plan from `/idt-exit`: entry, stop, target, trigger time, square-off, legs |
| Dhan intraday bars | ~100 calendar days of 5-minute bars for the plan's underlying |
| `idt/orders.json` | optional: if sized, `sized.expected_pnl` scales the mean by the units |
| `idt/timemachine.json` | with `--write` |

## How it works

1. **The pool.** Only FULL prior sessions (every 5-minute bar in the window is present; a missing bar
   means a halt or bad data), the most recent `--days` (59) of them; today is left out. Every bar
   becomes four ratios to the bar before: open, high, low and close over the previous close. The 09:15
   bar is never drawn for a later slot (it carries the overnight gap). Fewer than 20 full sessions:
   refused.
2. **One path.** Start at the entry, at the bar after the trigger bar closed. For each bar to the
   square-off, pick a past bar from the same time of day plus or minus `--window` (2) bars at random
   and scale it to the current price. Bar by bar it checks the stop first, then the target: a bar
   that touches both counts as the stop (the conservative call). Options and strategies are marked to
   Black-Scholes at constant IV along the path.
3. **The odds.** `p_target`, `p_stop`, `p_flat` (still open at square-off) and `p_green` (target first,
   or in profit at square-off). `expected_r`: +R at the target, -1 at the stop, otherwise P/L at
   square-off over the risk. A gap through the stop still counts as -1R here; a real fill can be worse.
   `underlying_at_squareoff`: median and 5th-95th percentile of the price.
4. **The history (`replay`).** ORB plans with an underlying stop: the same opening range, stop rule and
   target R on each of those past sessions, first close beyond the range = entry. What really happened,
   not a simulation: `fired`, `target`, `stop`, `flat`, `avg_r`, and `replay_line` in words.
5. **The verdict** looks only at the paths that hit one side and compares the target's share with the
   share that breaks even at the plan's R, 1 / (1 + R): 50% at 1R, 40% at 1.5R, 33% at 2R. Under 5
   points away: "Close to a coin flip" (1R) or "Close to break-even". 5 to 15: "Leans toward the target /
   stop". 15 or more: "Strongly toward" one side. `verdict_notes` add a line when over 40% of the paths
   hit neither, and when the average R points the other way from the lean.

**The seed.** Same plan, same data, same seed: the same numbers. Say the seed with every result.

## Steps

1. Make sure `idt/plan.json` is today's plan from `/idt-exit`.
2. Run `idt timemachine run`.
3. Tell the user, in this order: target first / stop first / neither / green, the median and 5-95%
   range of the price at square-off, the average R, the `replay_line`, then the `verdict` and every
   `verdict_notes` line exactly as printed. Say the seed and how many sessions were sampled.
4. If the verdict is a coin flip, close to break-even or toward the stop, say so plainly. Do not dress
   it up. If the history and the paths disagree, say that too.
5. Say once that this is built from the last ~60 sessions with constant IV, not a prediction: results
   days, RBI policy, the budget, expiry days and global gaps can do what those sessions never did.
   Check `/idt-news` before going on.
6. If the user still wants the trade, hand off to `/idt-budget`.

## Example (fixtures, 2026-10-29, seed 42, 59 sessions)

The NIFTY 26000 CE plan (stop on NIFTY 25,945, target 26,070, 1.7R after repricing):

```
target first 39.4%  stop first 60.6%  neither 0.0%  green 39.4%   average R +0.046
History: the same rule on 59 real sessions fired 29 times: 12 target, 17 stop, 0 neither. Average R +0.034.
Close to break-even: at 1.7R the target has to come first in 37% of the paths that hit a side; it did in 39%.
```

The bull call spread on the same trigger (stop -Rs 2,702, target +Rs 4,053 per set, 1.5R):

```
target first 8.9%  stop first 29.0%  neither 62.1%  green 42.5%   average R -0.090
Strongly toward the stop: at 1.5R the target has to come first in 40% of the paths that hit a side; it did in 23%.
62.1% of the paths hit neither by 15:15; the price at 15:15 decides those.
```

Same trigger, two instruments, two honest answers: the long call is close to break-even, the spread
leans clearly toward its stop by the square-off. That is what the user should hear before sizing.

## Rules

- Report the numbers as printed, including a negative average R. Never round toward the target.
- Never call a simulation a forecast, a probability of profit, or a backtest result.
- Never re-run with a different seed or window to get a nicer answer.

## What it never does

It never sizes, checks or tickets a trade, never changes the plan, and never promises the odds hold.

## Safety

- Education and tooling, not investment advice. A PASS from `/idt-risk` is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
