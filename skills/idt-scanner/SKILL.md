---
name: idt-scanner
description: >-
  Chart Scanner for NSE/BSE. Lists charts that match a rule: intraday opening-range breakouts (the
  09:15 IST range, on completed 5-minute bars) and daily setups on completed sessions (20-day
  closing-high breakout, bull flag, reclaim of the 20-day average, RSI oversold, oversold bounce).
  Universe = NSE F&O stocks, the watchlist, the F&O indices, or a list. Filters out illiquid stocks.
  Use when the user says "scan the market", "what is breaking out", "opening range breakouts",
  "find me setups", "bull flags", "oversold stocks", "pre-market scan", "what should I watch
  today", or at the start of a trading day before /idt-news and /idt-entry.
argument-hint: "[orb | daily | breakout | flag | reclaim | oversold | bounce] [--universe fno]"
---

# Chart Scanner (`/idt-scanner`)

The scanner is the first step of a day trade. It reads many charts and lists the ones that match a
rule. That is all it does. A scan is a list of charts that match a rule, not a list of things to buy,
and a setup on a chart is not a prediction. About 9 in 10 individual F&O traders lose money (SEBI,
FY22-FY24); the scanner does not change that. It only saves flipping through 200 charts by hand.

```bash
idt scan daily --universe fno                 # before 09:15 or after 15:30: every daily setup, F&O stocks
idt scan breakout --universe watchlist        # one daily setup
idt scan orb                                  # after ~09:35: opening-range breakouts so far (watchlist)
idt scan orb --universe fno --limit 15        # ~200 F&O stocks, about a minute
idt scan orb --universe indices               # NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, BANKEX
idt scan bounce --universe RELIANCE,HDFCBANK,SBIN --verbose
idt --now "2026-10-29 10:15" scan orb         # replay a past moment
```

## What it reads and writes

| source | what |
| --- | --- |
| `idt/watchlist.json` | the default universe (`idt init` seeds six large caps) |
| instrument master | `--universe fno`: every NSE stock with futures |
| `idt/config.json` | `or_minutes` (15), `entry_expiry` (11:30), `no_entries_before` (09:30), `min_volume_x`, `scan_min_price` (Rs 50), `scan_min_turnover_cr` (Rs 25 cr a day) |
| output | `scanned`, `fetched`, `failed`, `illiquid`, `matched`, `hits[]`, `partial` when some symbols failed |

## The setups

**Opening-range breakout (`orb`, during the session).** The range is the high and low of the bars
from 09:15 to 09:15 + `or_minutes` (09:15, 09:20, 09:25 for 15 minutes). A hit is the first
COMPLETED 5-minute bar after the range that CLOSES beyond it, before `entry_expiry`. A wick beyond
the range is not a hit; a close exactly at the high is not above it. Before the first bar after the
range has closed (09:35) it says "too early" and scans nothing. Each hit carries:

- `trigger_time` (bar start) and `trigger_close` (the time it closed, which is when it became a hit)
- `minutes_since` and `moved_since_pct`: how stale the hit is and how far price has run since
- `pct_beyond`, `range_pct` (range width as % of price), `rvol` (volume so far vs the same window over
  the prior 10 sessions; `null` for spot indices, which have no volume)

Short-side hits are listed too. For stocks, intraday shorts need `allow_short`; for indices a short
trigger maps to buying puts or a bear spread.

**Daily setups (before 09:15 or after 15:30).** On completed daily bars only: during the session
today's bar is still forming and is left out (`data_through` says so).

| setup | the rule |
| --- | --- |
| `breakout` | the last close is above every close of the 20 sessions before it |
| `flag` | a pole of 6%+ over ~6 sessions, then a 3-8 day flag retracing at most 50% on lower volume, close above EMA20. `trigger` = flag high, `stop_hint` = flag low |
| `reclaim` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI(14, Wilder) under 30. A condition, not an entry |
| `bounce` | RSI(14) under 30 in one of the prior two sessions, then a close above the prior high or a rising RSI |
| `daily` | all of the above in one pass |

Liquidity: a stock is skipped (counted under `illiquid`) when its last close is under `scan_min_price`
or its 20-session average traded value is under `scan_min_turnover_cr`. Indices skip the filter.

Ranking: ORB hits by relative volume, then the freshest trigger; daily hits by traded value (most
traded first), as the original scanner does.

## Steps

1. Before the open: `idt scan daily --universe fno`. Tell the user the counts (scanned, fetched,
   illiquid, matched) and the top few hits per setup, with the numbers that qualify each.
2. After 09:35 (10:00-10:15 is typical): `idt scan orb`. Say how many charts broke their range and
   when. Point out that an older hit (`minutes_since` large, `moved_since_pct` big) is a different
   trade from a fresh one: the stop distance and the odds have moved.
3. If `partial` is present, say so in those words. Never round a partial scan up to "the whole market".
4. The user picks one chart. Hand it on: `/idt-news SYMBOL` (anything moving it, ban list), then
   `/idt-entry SYMBOL`. Never pick for them.

## Example (fixtures, 2026-10-29)

`idt --now "2026-10-29 10:15" scan orb --universe NIFTY,BANKNIFTY,RELIANCE,HDFCBANK,TCS`:

```
5 scanned, 5 fetched, 0 failed; 5 matched
RELIANCE  long   09:30 bar closed 1488.50 above 1487 at 09:35 (+0.24%), 40 min ago, now +0.36%, rvol 1.11
TCS       short  09:50 bar closed 3268.59 below the range at 09:55, 20 min ago, rvol 1.03
NIFTY     long   09:35 bar closed 25995.00 above 25985 at 09:40 (+0.04%), 35 min ago, now +0.25%
```

Pre-market the same morning, `scan daily` tags TCS a bull flag (pole 6.7%, 6-day flag, retrace 23%,
trigger 4181.76, stop hint 4128.24) and HDFCBANK oversold (RSI 9.8).

## Rules

- Say what was scanned: how many symbols, how many came back, how many were usable, and the data time.
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure for a scan hit.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never sizes, checks or tickets a trade, never says which stock to buy, never calls the data real
time (Dhan 5-minute bars, bar by bar), and never promises that a setup works.

## Safety

- Education and tooling, not investment advice. A PASS from `/idt-risk` is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
