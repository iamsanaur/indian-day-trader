---
name: idt-alerts
description: >-
  Price Alerts for open Indian intraday trades. Rings once when a price, the plan's stop or target
  (on the underlying, the option premium, or combined strategy P/L) or the square-off time hits,
  checked against live broker quotes. Use while a trade is open, after /idt-broker, or when the user
  says "alert me", "tell me when NIFTY crosses", "watch my stop", "remind me to square off".
argument-hint: "add --from-plan | add --symbol S --above X | check | watch"
---

# Price Alerts (`/idt-alerts`)

Alerts keep the plan honest while the trade is open: the stop, the target and the square-off were
decided before the entry, and an alert says the moment one of them is reached. It never exits a
position on its own.

```bash
idt alerts add --from-plan                         # stop + target (underlying, premium or combined P/L) + square-off
idt alerts add --symbol NIFTY --above 26100 --label "OR extension"
idt alerts add --symbol "NIFTY 2026-11-03 26000 CE" --below 120
idt alerts check                                   # one pass, marks fired alerts
idt alerts watch --poll 15                         # loop until all fired (run in background)
idt alerts list | idt alerts clear
```

## What it reads and writes

| file | what |
| --- | --- |
| `idt/plan.json` | `--from-plan`: the stop, the target and the square-off |
| live quotes | Dhan last traded prices for each symbol or leg |
| `idt/alerts.json` | the alerts and which have fired (each fires once) |

Alert kinds: `price` (any symbol, including option contracts), `pnl` (combined P/L per set, from live
leg prices), `time` (square-off, default 15:15 IST).

## Steps

1. Right after `idt ticket confirm`: `idt alerts add --from-plan`.
2. Run `idt alerts watch --poll 15` in the background, or `idt alerts check` on a `/loop` every minute.
3. When one fires, tell the user immediately and plainly, with the price that hit:
   "STOP hit: NIFTY 25,944 <= 25,945. Exit the 26000 CE now." / "TARGET hit ..." / "15:15: square off,
   be flat before the broker's MIS auto square-off."
4. After the exit, record it: `idt journal close --pnl <rupees> --symbol <SYMBOL>`. That keeps the daily
   loss cap and the duplicate check accurate. Then `idt alerts clear` so the other side does not ring later.

## Rules

- Quotes are last traded prices polled every few seconds, not every tick. A fast market can move past a
  level between polls. Say so when it matters.
- An alert is information. The user exits in their broker.

## What it never does

It never places or cancels an order, never moves a stop or target, and never stays silent about a
fired stop.

## Safety

- Education and tooling, not investment advice.
- Paper mode by default (`"mode": "paper"`).
- Nothing in this pack places an order; the user exits in their own broker.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
