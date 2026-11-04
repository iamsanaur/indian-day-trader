---
name: idt-news
description: NSE corporate announcements (board meetings, results, orders won, pledges, management changes) for watched Indian stocks over the last N hours. Use before trading a stock, when a stock moves sharply, or on a schedule for the watchlist.
---

# News Monitor (`/idt-news`)

```bash
idt news                                   # watchlist + the plan's stock, last 12 hours
idt news --symbols RELIANCE,TCS --hours 48
idt ban                                    # today's NSE F&O ban list (no fresh F&O positions)
```

Source: public NSE corporate-announcement endpoints (cookie handshake; unofficial; can rate limit or
change). Dhan has no news feed. Each item has the subject, detail, time (IST) and attachment link.

Summarise what matters for intraday: results timing (most companies report after market hours),
board outcomes, large orders, regulatory actions, pledge changes. Flag event risk: avoid fresh
positions into a scheduled results release unless the user intends to trade the event. If an
endpoint errors, say so and continue; trading tools do not depend on it.

## Rules

- Times are IST. Say how old each item is and link the attachment.
- An announcement explains a move after the fact at best. Never infer a direction from a headline.
- Results and board meetings are event risk: say so when the plan's symbol has one today.

## Safety

- Education and tooling, not investment advice. Describe what the data shows; never call it a signal to buy or sell.
- Paper mode by default (`"mode": "paper"`). Nothing in this pack places an order: trades go through
  `/idt-exit` -> `/idt-timemachine` -> `/idt-budget` -> `/idt-risk` -> `/idt-broker`, and the user places them.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
