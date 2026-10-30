---
name: idt-options
description: Option chain analytics for Indian F&O (NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX and stock options) - OI, change in OI, PCR, max pain, ATM IV, IV skew, expected move from the ATM straddle, OI walls (support/resistance), long/short buildup per strike, Greeks. Use when the user asks about option chain, OI data, PCR, max pain, IV, where writers are positioned, or expiries.
---

# Options Analytics (`/idt-options`)

Read-only analysis of the live option chain from the broker data API (Dhan `/v2/optionchain`,
1 request per 3 seconds). Lot sizes and expiries come from the live instrument master and expiry
list - never quote remembered lot sizes; exchanges revise them.

## Commands

```bash
idt expiries NIFTY                       # upcoming expiries
idt chain NIFTY                          # nearest expiry
idt chain BANKNIFTY --expiry monthly     # near | next | monthly | YYYY-MM-DD
idt chain RELIANCE --strikes 8 --chart   # stock options, OI chart PNG
```

## Reading the output

| Field | Meaning |
|---|---|
| `atm`, `atm_iv`, `atm_straddle` | ATM strike, its IV (%), CE+PE premium |
| `expected_move` | +/- ATM straddle: the market-implied move to expiry (roughly 1 sigma) |
| `pcr.oi` / `pcr.oi_change` | put OI / call OI, total and today's additions |
| `max_pain` | expiry price where option buyers collectively lose most |
| `walls.resistance` / `support` | strikes with the highest call / put OI |
| `fresh_call_writing` / `fresh_put_writing` | biggest OI additions today |
| `table[].ce/pe.buildup` | long buildup, short buildup, short covering, long unwinding (price change vs OI change) |
| `skew` | IV ~3% OTM put vs call |
| `bias` | a descriptive read of positioning, not a signal |

Explain positioning in plain words, e.g. "heavy call writing at 26,500 caps upside near term; put
writers defend 25,500". Do not present PCR or max pain as predictions. Note `days_to_expiry`: near
expiry, gamma risk is high and premiums decay fast.

For trades, hand over to `/idt-strategy` (build/payoff) and the plan -> size -> risk -> ticket chain.
