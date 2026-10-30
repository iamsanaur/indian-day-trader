---
name: idt-alerts
description: Price, stop, target, combined option P/L and square-off time alerts for open Indian intraday trades, checked against live broker quotes. Use while a trade is open, or when the user asks to be told when a symbol crosses a level.
---

# Price Alerts (`/idt-alerts`)

```bash
idt alerts add --from-plan                         # stop + target (underlying, premium or combined P/L) + square-off
idt alerts add --symbol NIFTY --above 26100 --label "OR extension"
idt alerts add --symbol "NIFTY 2026-11-03 26000 CE" --below 120
idt alerts check                                   # one pass, marks fired alerts
idt alerts watch --poll 15                         # loop until all fired (run in background)
idt alerts list | idt alerts clear
```

Alert kinds: `price` (any symbol, including option contracts), `pnl` (sum over strategy legs from live
leg prices), `time` (square-off, default 15:15 IST).

When an alert fires, tell the user immediately and plainly: "STOP hit: NIFTY 25,944 <= 25,945 - exit
the 26000 CE now", and so on. After a stop or target exit, record the result with
`idt journal close --pnl <rupees>` so the daily loss cap stays accurate. At the square-off alert,
remind the user to be flat before the broker's MIS auto square-off.
