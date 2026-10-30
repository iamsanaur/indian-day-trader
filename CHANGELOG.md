# Changelog

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
