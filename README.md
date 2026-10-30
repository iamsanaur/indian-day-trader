# Indian Day Trader

14 Claude skills for intraday trading on Indian markets (NSE/BSE cash, index and stock F&O).
Adapted from [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) (US) for the
Indian market. It adds index charts, option-chain analytics and F&O strategies, including option selling.

**Nothing in this pack can place an order.** Every trade passes a risk gate and needs your explicit
"yes" before a broker-neutral ticket is produced, which you place yourself. Paper mode is the default.

> Not investment advice. SEBI's studies found that about 9 in 10 individual F&O traders lost money
> (FY22-FY24). Stops are not guaranteed fills. Data from broker APIs and public NSE endpoints can lag,
> rate limit or be wrong.

## Skills

| Command | Job |
|---|---|
| `/idt-index` | Index board and charts: NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY, SENSEX, INDIA VIX. Opening range, PDH/PDL, CPR and pivots, EMA trend, VWAP on futures. PNG and HTML |
| `/idt-options` | Option chain: OI, change in OI, PCR, max pain, ATM IV, skew, expected move, OI walls, buildup, Greeks |
| `/idt-strategy` | Long/short options, spreads, straddles, strangles, iron condor/fly, custom legs. Payoff, breakevens, Greeks, margin |
| `/idt-scanner` | ORB (09:15 range), bull flags, oversold bounces over F&O stocks, a watchlist or indices |
| `/idt-entry` | Waiting / triggered / expired on completed 5-minute bars (IST) |
| `/idt-exit` | Stop and target before entry. Equity, futures, options (underlying or premium stop), strategies (combined P/L) |
| `/idt-timemachine` | 10,000 seeded Monte Carlo sessions plus a replay of the rule on prior sessions |
| `/idt-budget` | Size in shares or lots from max loss, capped by leverage and margin, with full Indian charges |
| `/idt-risk` | PASS / BLOCK: loss caps, trade count, cutoff, ban list, naked/short permissions, expiry-day selling, margin, stale prices |
| `/idt-broker` | Broker-neutral ticket (MIS/NRML, LIMIT/SL-limit, lots) and a confirmation log |
| `/idt-alerts` | Price, stop, target, combined-P/L and square-off alerts |
| `/idt-news` | NSE corporate announcements and the F&O ban list |
| `/idt-analyst` | Quarterly revenue, profit and EPS with QoQ/YoY growth |
| `/idt-insider` | Bulk/block deals and SEBI PIT insider disclosures |

Pipeline: scanner → news → entry → exit → timemachine → budget → risk → broker, with alerts while
the trade is open. Every step writes to `idt/` in your project: `setup.json`, `strategy.json`,
`plan.json`, `orders.json`, `risk.json`, `alerts.json` and `journal.jsonl`.

## Install

```bash
git clone <this repo> indian-day-trader && cd indian-day-trader
uv tool install .            # or: pip install -e .   (Python 3.10+)
idt init                     # creates idt/config.json and idt/watchlist.json in the current folder
```

Load the skills as a Claude Code plugin (`/plugin` → add this folder), or copy `skills/*` into
`~/.claude/skills/` or a project's `.claude/skills/`.

### Data: Dhan v2 API

```bash
export DHAN_CLIENT_ID=1000000000
export DHAN_ACCESS_TOKEN=eyJ...     # web.dhan.co → My Profile → Access DhanHQ APIs (expires daily)
```

The data APIs (historical, quotes, option chain) need Dhan's data subscription. Only read
endpoints are called: candles, OHLC quotes, option chain and expiry list, fund limit, and the
margin calculator. Lot sizes, tick sizes and expiries come from Dhan's scrip master (cached for 12 hours),
so exchange revisions are picked up automatically (for example NIFTY 65 and BANKNIFTY 30 from January 2026).

The adapter is pluggable (`src/idt/data/base.py` → `MarketData`). Adding another broker means writing one class.

News, the ban list, deals, insider data and results come from public NSE endpoints. They are
unofficial and can rate limit.

## Worked example (offline fixtures)

Session 2026-10-29, as of 09:45 IST. NIFTY's 15-minute opening range is 25,905–25,985 and the
09:35 bar closes at 25,995, which triggers the breakout.

```bash
export IDT_FIXTURES=tests/fixtures/data          # offline data; drop this for live Dhan
alias idt='idt --now 2026-10-29T09:45'
idt init && # set max_loss_per_trade to 3000 in idt/config.json
idt entry check NIFTY --write                    # triggered long @ 25,995 (OR mid 25,945)
idt chain NIFTY                                  # max pain 26,000; call wall 26,500; put wall 25,500; ATM IV 11.8
idt strategy bull-call-spread NIFTY --width 4 --write
#   +26000 CE @ 156.87, −26200 CE @ 73.73 → debit ₹5,404 per lot (65), max profit ₹7,596, BE 26,083
idt exit plan --kind strategy --stop maxloss-pct:50 --target 1.5R --write
#   stop −₹2,702 per set, target +₹4,053 (1.5R)
idt timemachine run                              # MC: target 9.5%, stop 28.4%, flat at 15:15 62.1%
idt size --write                                 # 1 set; loss at stop ₹2,832 incl. ₹130 charges
idt risk check                                   # PASS
idt ticket show                                  # BUY 65 × 26000 CE LMT 156.87, SELL 65 × 26200 CE LMT 73.73
idt ticket confirm <hash>                        # only after you type yes
idt alerts add --from-plan
```

The same setup as a single long call with the stop on the underlying:

```bash
idt exit plan --stop or-mid --target 1.5R --write
#   26000 CE @ 156.87, stop ≈ 132.04 (NIFTY 25,945), target ≈ 199.17 (NIFTY 26,070), ₹1,614 risk per lot
```

## Option selling

Short options are supported: `short-straddle`, `short-strangle`, credit spreads, `iron-condor`, `iron-fly`, `custom`.
The safety defaults are:

- `allow_naked: false`. Uncovered short calls and puts are blocked; defined-risk structures pass.
- `block_expiry_day_selling: true`. No fresh short options that expire the same day.
- Credit stops use `credit-x:N` (exit when the loss equals N × the credit) or `pnl:-X`.
- Margin comes from Dhan's basket margin calculator. If it is unavailable, a rough SPAN-like estimate is used.

## Charges

From `src/idt/charges.py`, rates effective 2026-04-01:

| | STT | Exchange (NSE) | Stamp (buy) |
|---|---|---|---|
| Equity intraday | 0.025% sell | 0.00297% | 0.003% |
| Futures | 0.05% sell | 0.00173% | 0.002% |
| Options | 0.15% of premium, sell | 0.03503% of premium | 0.003% |

Also SEBI ₹10 per crore and 18% GST on brokerage and fees. Brokerage defaults to ₹20 per order,
or 0.03% for intraday equity if that is lower. Override any rate with `charges_override` in config.
Check against your broker's contract note.

## Config (`idt/config.json`)

See `config.example.json`. Key settings: `mode` (paper/live), `capital`, `max_loss_per_trade`,
`daily_loss_cap`, `max_trades_per_day`, `entry_cutoff`, `squareoff`, `allow_short`, `allow_naked`,
`min_premium`, `stale_quote_seconds`, `require_ban_check`.

## Tests

```bash
uv pip install -e ".[dev]" && pytest -q
python tests/fixtures/make_fixtures.py      # regenerate the deterministic fixtures
```

The tests run offline on generated fixtures in Dhan payload format, with mocked HTTP for the Dhan adapter.

## Tax note

Intraday equity profits are speculative business income. F&O profits are non-speculative business
income. Losses and audit thresholds follow different rules. This is not tax advice; ask a CA.
