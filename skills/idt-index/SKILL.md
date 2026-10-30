---
name: idt-index
description: Indian index dashboard and charts - NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, INDIA VIX. Opening range, previous-day high/low, CPR and pivots, EMA trend, VWAP on futures, PNG and interactive HTML charts. Use when the user asks how the market or an index is doing, wants an index chart, levels, or "what is Nifty doing".
---

# Index Charts (`/idt-index`)

Reads index candles from the configured broker data API (Dhan by default) and reports levels a
day trader uses on NSE/BSE indices. Read-only. Not advice.

## Commands

```bash
idt index                         # board: all main indices, last, % change, ORB state, trend, CPR read
idt index NIFTY                   # one index: levels + PNG chart in idt/charts/
idt index BANKNIFTY --html        # also an interactive HTML chart (plotly)
idt index NIFTY --future          # chart the near-month future instead (has volume, so VWAP works)
idt index SENSEX --interval 15 --days 5
```

Intervals: 1, 5, 15, 25, 60 minutes. `--days` = sessions drawn.

## Reading the output

- `opening_range` - high/low of 09:15 to 09:15 + `or_minutes` (default 15). `orb.state` is waiting / triggered / expired.
- `prev_day` - PDH / PDL / PDC. `cpr` - pivot, BC/TC (central pivot range), R1-R3, S1-S3.
  `cpr_read`: narrow CPR (< 0.25%) often precedes trending days; wide CPR (> 0.6%) range days.
- `ema.trend` - up when EMA9 > EMA21 and price above EMA21; down for the reverse; else mixed.
- `vwap` is null for spot indices (no volume). Say so and offer `--future`.
- `charts` - file paths. Show the PNG to the user (Read the image) when they asked for a chart.

Summarise in plain words: where price is vs OR, PDH/PDL and CPR, trend, and what level would
change the picture. Mention INDIA VIX from the board when discussing option premiums.

## Setup

`idt` must be on PATH (`uv tool install <path-to-indian-day-trader>` or `pip install -e .`).
Dhan: `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` env vars (token expires daily). If a command
returns `{"error": ...}`, relay the setup instructions in it. `idt init` creates `idt/config.json`.
