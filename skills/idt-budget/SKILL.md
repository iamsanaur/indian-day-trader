---
name: idt-budget
description: Position sizing for Indian trades - shares or F&O lots from max loss per trade, capped by capital/leverage and available margin, with full Indian charges (brokerage, STT, exchange transaction fee, SEBI fee, stamp duty, GST). Writes idt/orders.json. Use after a plan exists, or when the user asks how many shares/lots to trade or what charges will be.
---

# Budget Manager (`/idt-budget`)

```bash
idt size                       # preview
idt size --write               # save idt/orders.json for the risk check
idt size --max-loss 2000       # what-if (the risk check still enforces config max_loss_per_trade)
idt charges --segment opt --buy 10196 --sell 12000           # one round trip
idt charges --segment eq_intraday --buy 148850 --sell 150150
```

`units = floor(max_loss / risk_per_unit)`. Equity is capped at `capital x leverage_cap / price`.
F&O quantity is always `lots x lot_size`, with the lot size read live from the instrument master.
Margin comes from the broker margin API (basket, with hedge benefit when available), with a rough
fallback estimate otherwise. Live mode reads available funds from the broker; paper mode uses `capital`.

If one unit already exceeds the max loss, say so and suggest a tighter stop, a spread instead of a naked
option, a cheaper strike, or a smaller-lot underlying. Never round up to make a trade fit.

Charges (rates effective 2026-04-01, editable via `charges_override`): STT 0.025% on intraday equity sells,
0.05% on futures sells, 0.15% of the premium on option sells. Plus exchange fees, SEBI Rs 10 per crore,
buy-side stamp duty, and 18% GST on brokerage and fees. `loss_at_stop` includes charges. Next: `/idt-risk`.
