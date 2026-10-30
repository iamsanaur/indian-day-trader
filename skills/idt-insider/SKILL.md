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
