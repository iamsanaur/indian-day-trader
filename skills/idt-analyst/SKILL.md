---
name: idt-analyst
description: Quarterly results analyst for NSE-listed companies - revenue, net profit and EPS by quarter with QoQ and YoY growth, from NSE results filings. Use when the user asks how a company's earnings are trending or before trading around results.
---

# Earnings Analyst (`/idt-analyst`)

```bash
idt results RELIANCE
idt results TCS --quarters 12
```

Returns quarters newest first: `period_end`, `revenue`, `net_profit`, `eps`, `consolidated` flag, and
`*_qoq_pct` / `*_yoy_pct` (YoY compares with the quarter four rows earlier).

Figures come from NSE results-comparison data; units are as filed (usually Rs lakh) and field
names vary across filings, so values are matched by keyword. Treat them as a summary and point to
the filing for anything decision-critical. Note the standalone vs consolidated mix. Avoid valuation
calls; describe the trend (accelerating, slowing, margin direction from profit vs revenue growth).
