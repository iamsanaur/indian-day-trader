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
