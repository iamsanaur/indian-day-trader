# Indian Day Trader — Design

Date: 2026-10-30
Source inspiration: https://github.com/Jakeschincariol/day-trader-skill (US, 11 skills, stdlib, Yahoo/SEC/Alpaca)

## Goal

A Claude Code plugin of 14 skills for intraday trading on Indian markets (NSE/BSE cash, index and
stock F&O), with index charts and full options analytics including option selling. Claude
assists; nothing places an order. Every trade passes a risk gate and an explicit user "yes" before
a broker-neutral order ticket is produced.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Scope | Full port of all 11 skills + new index, options and strategy skills |
| Market data | Broker API, pluggable adapter; Dhan v2 implemented first |
| Public data | NSE/BSE public endpoints for news, ban list, bulk/block deals, insider, results |
| Orders | Broker-neutral ticket only; no order placement |
| F&O depth | Analytics + buying + spreads + option selling (naked gated by config) |
| Dependencies | pip allowed: requests, numpy, pandas, matplotlib, plotly; pytest for tests |
| Layout | Shared package `idt` + thin skill folders calling the `idt` CLI |

## Architecture

```
.claude-plugin/plugin.json
pyproject.toml                    # console script: idt = idt.cli:main
src/idt/
  config.py      workspace (./idt/), config.json load + defaults, JSON state helpers
  market.py      IST clock, session phases, holidays, expiry helpers, index registry
  data/base.py   MarketData protocol + Candles/Quote/OptionChain dataclasses
  data/dhan.py   Dhan v2 REST adapter (requests), rate limiting, error mapping
  data/instruments.py  Dhan scrip-master loader/cache: lot size, tick, expiry, strikes, symbols
  data/nse.py    NSE public JSON (cookie handshake): announcements, ban list, bulk/block deals,
                 insider (PIT), financial results, holidays
  data/fixture.py offline adapter reading recorded JSON (tests + demo)
  indicators.py  EMA, SMA, RSI, ATR, VWAP, CPR/pivots, opening range, prev-day levels
  scanner.py     ORB, bull flag, oversold bounce
  fno.py         Black-Scholes price/Greeks, IV solver, PCR, max pain, OI buildup, OI walls
  strategy.py    legs, payoff, breakevens, max P/L, strategy builders, naked detection
  charges.py     Indian brokerage + statutory charges (rates table, dated)
  sizing.py      size in shares or lots against max loss and capital
  plan.py        exit plan (stop/target on underlying or premium)
  entry.py       waiting/triggered/expired state machine on bars
  timemachine.py Monte Carlo + historical replay (options repriced via BS)
  risk.py        PASS/BLOCK rules
  ticket.py      broker-neutral bracket ticket
  alerts.py      price/stop/target/square-off alerts
  charts.py      PNG (matplotlib) and HTML (plotly) charts with overlays
  cli.py         argparse subcommands, JSON/table output
skills/idt-*/SKILL.md
tests/ + tests/fixtures/
```

### Data adapter contract (`MarketData`)

- `candles(symbol, interval, start, end) -> Candles` (interval: 1,5,15,25,60 minutes or "D")
- `quote(symbols) -> dict[symbol, Quote]` (ltp, ohlc, ts)
- `expiries(underlying) -> list[date]`
- `option_chain(underlying, expiry) -> OptionChain` (spot, rows per strike with CE/PE ltp, iv,
  oi, prev_oi, volume, greeks, bid/ask, security_id)
- `funds() -> dict` (available balance)
- `margin(legs) -> dict` (total/span/exposure)

Symbols are human names (`NIFTY`, `RELIANCE`, `NIFTY 2026-11-04 24500 CE`); the instrument master
resolves them to Dhan `securityId` + `exchangeSegment` + `instrument`. Index IDs default to Dhan's
IDX_I IDs (NIFTY 13, BANKNIFTY 25, FINNIFTY 27, MIDCPNIFTY 442, SENSEX 51, INDIA VIX 21) and are
overridable in config.

Dhan specifics: base `https://api.dhan.co/v2`, headers `access-token` + `client-id` from env
`DHAN_ACCESS_TOKEN`, `DHAN_CLIENT_ID`. Option chain and expiry list: 1 req / 3 s. Quotes: 1 req/s.
Intraday history: max 90 days per call. Data errors 805 → backoff+retry; 806/807/808/809 → setup
message.

### Workspace state (`./idt/`)

`config.json`, `watchlist.json`, `plan.json`, `orders.json`, `alerts.json`, `journal.jsonl`,
`cache/` (scrip master, NSE responses), `charts/`.

## Skills

| Skill | CLI | Output |
|---|---|---|
| idt-scanner | `idt scan orb|flag|bounce [--universe fno|watchlist] [--at HH:MM]` | ranked candidates |
| idt-index | `idt index NIFTY [--interval 5] [--html]` | levels + chart file |
| idt-options | `idt chain NIFTY [--expiry]` | PCR, max pain, walls, buildup, IV skew |
| idt-strategy | `idt strategy bull-call-spread NIFTY ...` / `idt strategy custom --leg ...` | payoff, BE, max P/L, margin |
| idt-news | `idt news --symbols ... --hours 12` | announcements |
| idt-entry | `idt entry check SYMBOL --setup orb` | waiting/triggered/expired |
| idt-exit | `idt exit plan --stop or-mid --target 1.5R --write` | plan.json |
| idt-timemachine | `idt timemachine run` | win/loss/flat odds, replay stats |
| idt-budget | `idt size --write` | orders.json with qty/lots + charges |
| idt-risk | `idt risk check` | PASS/BLOCK + reasons |
| idt-broker | `idt ticket show` | broker-neutral ticket |
| idt-alerts | `idt alerts add --from-plan` / `check` | fired events |
| idt-analyst | `idt results SYMBOL` | quarterly revenue/profit/EPS trend |
| idt-insider | `idt insider deals|pit [--symbol]` | bulk/block + insider disclosures |

## Indian market rules encoded

- Session IST 09:15–15:30; pre-open 09:00–09:08; ORB default 09:15–09:30.
- MIS square-off cutoff configurable (default 15:15; no new intraday entries after 15:00).
- Lot sizes, freeze quantities, tick sizes, expiries: read live from the instrument master —
  never hardcoded (SEBI/exchange revisions, e.g. NIFTY lot 65 from Jan 2026; only NIFTY and SENSEX
  keep weekly expiries).
- F&O ban list (NSE) blocks fresh positions in stock F&O.
- Charges table (effective 2026-04-01): STT equity intraday 0.025% sell; futures 0.05% sell;
  options 0.15% of premium on sell; exchange txn NSE eq 0.00297%, fut 0.00173%, opt 0.03503% of
  premium; SEBI ₹10/crore; stamp duty buy-side eq intraday 0.003%, fut 0.002%, opt 0.003%; GST 18% on
  brokerage+exchange+SEBI; brokerage flat ₹20/order or 0.03% (configurable). All rates live in a
  dated table in `charges.py` and can be overridden in config.

## Risk rules (`idt risk check`)

BLOCK if any: daily loss cap reached; max trades/day reached; after entry cutoff; plan missing
stop; risk per trade > `max_loss_per_trade`; position value > capital × leverage cap; symbol in
F&O ban; naked short option while `allow_naked` false; short selling while `allow_short` false;
required margin > available funds (live or configured paper capital); quote stale > 60 s; expiry
day and `block_expiry_day_selling` true for short options; option premium < `min_premium`.

## Safety

Paper mode default (`mode: "paper"`). No order-placement code exists. Ticket requires a fresh
risk PASS bound to an order hash, and the skill requires the user to type yes for that exact order.
Keys only from environment.

## Error handling

Missing keys → explicit setup instructions. Rate limit → sleep and retry (max 3). Stale or empty
data → risk BLOCK, not silent defaults. NSE handshake failure → clear message; news/insider tools
degrade independently of trading tools.

## Testing

pytest, offline, via `FixtureData` adapter and recorded JSON. Units: indicators, BS/IV/Greeks vs
known values, max pain/PCR, payoff/breakevens, charges, sizing in lots, risk rules, entry state
machine, timemachine determinism (seeded), Dhan adapter request/response mapping (mocked HTTP),
CLI smoke tests. Worked example: NIFTY ORB → bull call spread sized against ₹1,000 max loss.

## Out of scope

Order placement, websockets/live streaming, commodity/currency segments, tax computation.
