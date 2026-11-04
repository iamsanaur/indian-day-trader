---
name: idt-insider
description: Tracks NSE bulk and block deals and SEBI PIT insider-trading disclosures (promoters, directors, KMP buying or selling) for Indian stocks. The Indian replacement for a congressional-trade tracker. Use when the user asks who is buying/selling a stock, about promoter activity, or large institutional deals.
---

# Insider & Large Deals (`/idt-insider`)

```bash
idt insider deals                         # today's bulk + block deals
idt insider deals --symbol TCS
idt insider pit --symbol RELIANCE --days 90   # SEBI (PIT) Regulations disclosures
```

- **Bulk deal**: a trade of more than 0.5% of a company's shares in one session, reported by the
  exchange. **Block deal**: a large negotiated trade done in the block window.
- **PIT disclosures**: trades by promoters, the promoter group, directors and KMP. They must be
  disclosed within 2 trading days. Fields: person, category, buy/sell, quantity, value, mode (market,
  pledge, ESOP, and so on) and dates.

Interpretation: promoter market purchases are more informative than ESOP allotments or pledge
creation/release, so separate them. Disclosures lag the trade. Never present insider activity as a
trade signal by itself. Public NSE endpoint, unofficial: if it fails, say so.

## Rules

- Say the disclosure date and the trade date: disclosures lag the trade by days.
- Separate market purchases from ESOP, pledge and inter-se transfers before drawing any read.
- Never present insider or bulk-deal activity as a trade signal by itself.

## Safety

- Education and tooling, not investment advice. Describe what the data shows; never call it a signal to buy or sell.
- Paper mode by default (`"mode": "paper"`). Nothing in this pack places an order: trades go through
  `/idt-exit` -> `/idt-timemachine` -> `/idt-budget` -> `/idt-risk` -> `/idt-broker`, and the user places them.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
