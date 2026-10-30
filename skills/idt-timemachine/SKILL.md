---
name: idt-timemachine
description: Simulate an Indian intraday trade plan before risking capital - 10,000 Monte Carlo sessions resampled from the same time of day over the prior ~59 sessions of 5-minute bars (fixed seed), plus a replay of the same ORB rule on past sessions. Options and strategies are repriced with Black-Scholes. Use after /idt-exit, or when the user asks the odds of a plan.
---

# Time Machine (`/idt-timemachine`)

```bash
idt timemachine run                      # 10,000 paths, seed 42, prior 59 sessions
idt timemachine run --paths 20000 --seed 7 --days 40 --write
```

Reads `idt/plan.json`. Paths start at the bar after the trigger and run to the square-off time
(default 15:15). Each bar keeps its open/high/low/close shape, so intrabar touches count. If the stop
and target are both touched in one bar, the stop is assumed first.

## Output

- `monte_carlo.p_target`, `p_stop`, `p_flat` (still open at square-off), `pnl_per_unit` mean/median/p5/p95,
  `expected_r`.
- `replay` (ORB plans with an underlying stop): how often the rule fired in prior sessions, win rate, average R
  (in underlying R terms).
- `sized.expected_pnl` if `orders.json` exists.

Report the odds plainly, including a negative expectancy. State the caveat: a simulation from about 60
sessions with constant IV for options, not a prediction. Volatility regimes and event days (RBI policy,
budget, results, expiry) can differ sharply.
