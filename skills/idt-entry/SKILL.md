---
name: idt-entry
description: >-
  Entry Timer for NSE/BSE intraday setups. Watches a setup bar by bar and says the moment to get in:
  builds the 09:15 IST opening range (15 minutes by default) and calls the entry on the first
  COMPLETED 5-minute bar that CLOSES beyond it, beyond the previous day's high/low, or beyond a level
  you give, with an optional volume check. Says waiting (and how far), triggered (time, price, how
  stale), expired, or closed, and writes idt/setup.json for /idt-exit. It never places an order. Use
  when the user says "tell me when to get in", "watch NIFTY", "has it broken out", "did it break the
  opening range", "entry signal", "time my entry", or after /idt-scanner and /idt-news.
argument-hint: "SYMBOL [--setup orb|pdh|level] [--above X] [--below Y]"
---

# Entry Timer (`/idt-entry`)

The Entry Timer turns a setup into one moment: the bar that confirms it. It waits for each 5-minute
bar to finish. A price that pokes beyond the level in the middle of a bar is not an entry. A bar that
CLOSES beyond it is. Then it says the time and the price, writes them down for the Exit Planner, and
stops. It never buys anything. A clean signal does not make a trade win.

```bash
idt entry check NIFTY                               # opening-range breakout (default)
idt entry check NIFTY --write                       # on trigger, save idt/setup.json for /idt-exit
idt entry check RELIANCE --setup pdh                # close beyond the previous day's high / low
idt entry check BANKNIFTY --setup level --above 58500 --below 57900
idt entry check RELIANCE --min-volume-x 1.5         # trigger bar needs 1.5x the range bars' average volume
idt entry watch NIFTY --write --poll 60             # loop until triggered or expired (run in background)
idt --now "2026-10-29 09:45" entry check NIFTY      # replay a past moment
```

## What it reads and writes

| file | what |
| --- | --- |
| Dhan intraday bars | today's 5-minute bars (and recent sessions for ATR) |
| `idt/config.json` | `or_minutes` (15), `entry_expiry` (11:30, ORB only), `entry_cutoff` (15:00, pdh/level), `no_entries_before` (09:30), `min_volume_x` (off), `holidays` |
| `idt/setup.json` | with `--write` on a trigger: symbol, setup, side, entry, `trigger_time`, `trigger_close`, range, `atr` |

## The rule

- **Opening range (`orb`).** High and low of the bars from 09:15 to 09:15 + `or_minutes`: the 09:15,
  09:20 and 09:25 bars for 15 minutes. Long above the high, short below the low.
- **Previous day (`pdh`).** Above the previous session's high, or below its low.
- **Level (`level`).** `--above` and/or `--below` a price you give (a scanner `trigger`, a CPR level).
- **The trigger** is the first completed bar after the range that CLOSES beyond the level. A wick is
  not a trigger. A close exactly at the level is not beyond it.
- **The time** is the bar's close (`trigger_close`): the 09:35 bar closes at 09:40. The price is its close.
- **Only closed bars count.** A bar counts once the clock passes its start + 5 minutes. The bar still
  forming is shown under `forming` with "it does not count until it closes".
- **Time limits.** No entry on a bar that closes before `no_entries_before`. ORB setups expire at
  `entry_expiry`; pdh/level setups at `entry_cutoff`. Weekends and holidays: `closed`.
- **Volume, if you want it.** `--min-volume-x 1.5` also needs the trigger bar's volume at 1.5x the
  opening-range bars' average; thinner closes are listed under `skipped_thin`. The 09:15 bar holds the
  pre-open auction, so 1.0 is already strict. Spot indices have no volume: the check is skipped and
  `volume_note` says so (use the future for volume).
- **One trigger per setup per day:** the first qualifying close. Later closes do not reset it.

## Output

`state`: waiting / triggered / expired / closed. Waiting gives `last` and the distance to each level
in points and %. Triggered gives `side`, `entry`, `trigger_close`, `pct_beyond`, `volume_x`,
`minutes_since`, `last`, and `late` when the trigger is more than one bar old.

## Steps

1. Get the symbol from the user, or the one they picked from `/idt-scanner`. Check `/idt-news` first.
2. Run `idt entry check SYMBOL`. Tell the user the state in one line: waiting and how far, triggered
   at what time and price, or expired.
3. To wait for it, run `idt entry watch SYMBOL --write` in the background, or `idt entry check SYMBOL
   --write` on a `/loop` every 5 minutes. Report when the state changes.
4. When it triggers, say the time and the price, and that nothing was placed. If `late` is present,
   say it plainly: a late entry is a different trade.
5. Hand off to `/idt-exit` to set the stop and the target BEFORE anything is bought.

## Example (fixtures, 2026-10-29)

NIFTY's range is 25,905 to 25,985. At 09:38 the 09:35 bar is still forming, so it waits:

```
waiting  last close 25,975.00 (09:30 bar): +10.00 to the range high 25,985 (+0.04%), -70.00 to the low 25,905.
The 09:35 bar is still forming (25,995 so far, closes 09:40); it does not count until it closes.
```

At 09:45:

```
triggered long: the 09:35 bar closed 25,995.00 above 25,985.00 at 09:40 (+0.04%), 5 minutes ago.
Nothing was placed. Next: /idt-exit to set the stop and target first.
```

## Rules

- Bar by bar on Dhan 5-minute bars, which can lag. Say so when a minute matters.
- A signal is information, not an order, and not a promise.
- Never call an entry early because a bar looks like it will close beyond the level.

## What it never does

It never places an order, never sizes a position, never sets the stop (that is `/idt-exit`), never
moves the level after the fact, never counts a bar that has not closed, and never runs `/idt-broker`
from a background watch: nobody is there to say yes.

## Safety

- Education and tooling, not investment advice. A PASS from `/idt-risk` is a rules check, not a recommendation.
- Paper mode by default (`"mode": "paper"`). Live mode only changes where funds come from.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- No shorting or naked options unless the config allows it and the user confirms.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
