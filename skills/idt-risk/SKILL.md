---
name: idt-risk
description: Risk manager for Indian intraday and F&O trades - returns PASS or BLOCK for the sized order against daily loss cap, max trades, entry cutoff and square-off time, loss budget, leverage, shorting and naked-option permissions, F&O ban list, expiry-day selling, minimum premium, available margin and stale prices. Use before any order ticket; nothing proceeds on BLOCK.
---

# Risk Manager (`/idt-risk`)

```bash
idt risk check        # reads idt/plan.json + idt/orders.json, writes idt/risk.json
idt status            # today's trades, realised P/L and limits
idt journal close --pnl -850 --symbol NIFTY     # record a closed trade (feeds the daily loss cap)
```

## Rules (any failure = BLOCK)

market open; before `entry_cutoff`; daily loss cap (realised P/L today plus this trade's loss at stop);
`max_trades_per_day`; stop defined; loss at stop including charges within `max_loss_per_trade`;
orders match the plan; shorting needs `allow_short`; naked short options need `allow_naked`; option premium
of at least `min_premium`; no short options expiring today when `block_expiry_day_selling` is set; stock F&O
not in today's NSE ban list; margin within available funds; prices fresher than `stale_quote_seconds`;
before square-off.

## How to respond

- **PASS**: say so in one line and offer `/idt-broker` to build the ticket.
- **BLOCK**: list each reason in plain words with what would fix it. Never suggest editing the config just
  to get past a block in the same breath. If the user changes limits themselves, that is their decision; re-run.

The verdict is bound to the order hash. Any re-size invalidates it.
