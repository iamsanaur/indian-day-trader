---
name: idt-entry
description: Entry timer for Indian intraday setups - reports waiting, triggered or expired bar by bar for an opening-range breakout, previous-day high/low break, or a custom level, on completed 5-minute bars in IST. Use when the user asks whether a setup has triggered, or wants to wait for an entry.
---

# Entry Timer (`/idt-entry`)

## Commands

```bash
idt entry check NIFTY                              # ORB, default
idt entry check RELIANCE --setup pdh               # close beyond previous day's high/low
idt entry check BANKNIFTY --setup level --above 58500 --below 57900
idt entry check NIFTY --write                      # on trigger, save idt/setup.json for /idt-exit
idt entry watch NIFTY --write --poll 60            # loop until triggered or expired
```

Only completed bars count (a 09:35 bar is complete at 09:40). ORB setups expire at `entry_expiry`
(default 11:30); the config `entry_cutoff` (15:00) blocks any new intraday entry in the risk check.

## Output

`state`: waiting / triggered / expired. On trigger: `side` (long/short), `entry` (trigger bar close),
`trigger_time`, `range` (OR high/low/mid) and `atr`. With `--write`, `idt/setup.json` feeds the next step.

Tell the user the state in one line. When triggered, move to `/idt-exit` to set the stop and target
**before** any order. For `watch`, run it in the background and report when it changes state.
