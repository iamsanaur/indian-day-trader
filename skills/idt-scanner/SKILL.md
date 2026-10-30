---
name: idt-scanner
description: Scan Indian stocks and indices for intraday opening-range breakouts (09:15 IST range), daily bull flags and oversold (RSI) bounces. Universe = NSE F&O stocks, the user's watchlist, the F&O indices, or a list. Use when the user asks what is breaking out, what to watch today, or for trade ideas on NSE.
---

# Chart Scanner (`/idt-scanner`)

## Commands

```bash
idt scan orb                                  # watchlist (idt/watchlist.json), ORB at the current time
idt scan orb --universe fno --limit 15        # all NSE F&O stocks (about 200; takes ~1 min)
idt scan orb --universe indices
idt scan flag --universe fno                  # daily bull flags (best after the close or pre-market)
idt scan bounce --universe RELIANCE,HDFCBANK,SBIN
idt --now "2026-10-29 10:15" scan orb         # replay a past moment
```

## Setups

- **orb**: the opening range is 09:15 to 09:15 + `or_minutes` (default 15). Triggered when a completed
  5-minute bar closes beyond it, before `entry_expiry` (default 11:30). Ranked by relative volume (`rvol`)
  then tighter range. Short-side triggers are listed too; for stocks, shorting is intraday-only and off unless
  `allow_short` is set. For index setups, a short trigger maps to buying puts or a bear spread.
- **flag**: pole of 6% or more in about 6 sessions, then a 3-8 day flag retracing at most 50% on lower volume,
  close above EMA20. `trigger` = flag high, `stop_hint` = flag low.
- **bounce**: RSI(14) below 30 in the prior two sessions, then a close above the prior high or a rising RSI.

Present a short ranked list with why each qualifies. Check `/idt-news` for anything that explains a
move. A scan hit is a candidate, not a recommendation. Next step: `/idt-entry` on the chosen symbol.
