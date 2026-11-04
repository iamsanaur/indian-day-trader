# Changelog

## 0.1.2 — 2026-11-04 — parity pass against the original day-trader-skill

Rechecked every skill against [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) and
ported the behaviour that was missing or simplified away.

- **Time Machine**: one-line verdict against break-even for the plan's reward:risk (1 / (1 + R)) plus notes
  when many paths hit neither; `p_green`, `r_at_target`, price percentiles at square-off; bars drawn from the
  same time of day ±2 bars (`--window`); `--days` now caps the pool; refuses with fewer than 20 full sessions;
  replay counts target / stop / neither and prints a history line.
- **Sizing**: risk re-measured from the worse of the plan's entry and a fresh price (a run-up means fewer
  units and a lower reward:risk; past the target is refused); units reduced until the loss at the stop
  including charges fits the max loss; `limits` and `decided_by`; plans from another day are refused.
- **Risk gate**: new `min_reward_risk` (1.0), `no_entries_before` (09:30), duplicate open entries, sized-today
  checks; the daily loss cap now counts the full max loss of every entry confirmed today (as the original
  does), not only logged closes; the 5% tolerance over `max_loss_per_trade` is gone.
- **Exit planner**: stops round to the tick away from the entry, targets to the nearest tick; refuses a stop on
  the wrong side, a target the price already passed, a stop under 0.05% of the price, an untriggered setup,
  and a plan after square-off. Equity uses the instrument's tick.
- **Entry timer**: `no_entries_before`, optional `--min-volume-x`, the bar still forming, distance to each
  level while waiting, `trigger_close`, `minutes_since` and a `late` warning; pdh/level setups run to
  `entry_cutoff` instead of the ORB expiry; closed days say so.
- **Scanner**: the original's daily setups `breakout` (20-day closing high), `reclaim` (20-day average) and
  `oversold`, plus `daily` for all at once; liquidity floor (`scan_min_price`, `scan_min_turnover_cr`); ORB
  hits carry freshness (`trigger_close`, `minutes_since`, `moved_since_pct`); partial scans say so; "too early"
  before the first bar after the range closes.
- **Tickets**: entry, stop and target prices on the tick (buy limits round up, sell limits down).
- **Skills**: the trade-pipeline playbooks (scanner, entry, exit, timemachine, budget, risk, broker, alerts)
  rewritten with the original's structure: what each reads and writes, the exact rule, steps, a worked
  example on the fixture day, rules, what it never does, and safety. Research skills gained rules and safety.
- 72 Python tests (14 new in `tests/test_parity.py`)
- **Web**: Trade › Odds shows the verdict banner, green odds and history line; Trade › Size shows reward:risk
- **Docker**: image `indian-day-trader:0.1.2`; README covers updating an existing deployment in place

## 0.1.1 — 2026-10-30

- **Dhan TOTP login**: `DHAN_CLIENT_ID` + `DHAN_PIN` in the environment, then a 6-digit TOTP once a day gets a
  24-hour token (`idt dhan login|status|logout`, `/api/dhan`). The TOTP is never stored; the token is kept in
  `idt/dhan_token.json` (0600). `DHAN_ACCESS_TOKEN` still works as a manual override.
- Web, iOS and Android: "Connect Dhan for today" banner and Settings › Dhan session
- Web: server token vs Dhan token is now unmistakable (label + pairing banner on 401)
- Docker + Cloudflare Tunnel deployment (`docker compose up -d`), `idt serve --public-url`
- Signed Android release build; iOS Ad Hoc export
- 58 Python tests

## 0.1.0 — 2026-10-30

- 14 Claude skills for NSE/BSE intraday and F&O
- Dhan v2 data adapter, scrip-master resolution of lots/expiries
- Index charts, option chain analytics, strategy builder incl. option selling
- Entry timer, exit planner, Monte Carlo Time Machine + replay
- Sizing in lots with Indian charges (STT rates effective 2026-04-01)
- PASS/BLOCK risk gate, broker-neutral tickets bound to a risk hash
- NSE announcements, F&O ban list, bulk/block deals, PIT insider, quarterly results
- Offline fixtures, 44 tests, CI
