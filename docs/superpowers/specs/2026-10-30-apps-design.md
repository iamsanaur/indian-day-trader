# Indian Day Trader Apps — Design

Date: 2026-10-30 · Builds on `2026-10-30-indian-day-trader-design.md`

## Goal

Web, native iOS and native Android clients for the `idt` engine, backed by a self-hosted API
server. Same full trading workflow as the Claude skills. Still never places orders.

## Decisions

| Topic | Decision |
|---|---|
| Backend | Self-hosted FastAPI (`idt serve`) wrapping the `idt` package; single user |
| Auth | Personal bearer token in `idt/server.json`; QR pairing (`idt://pair?u=<url>&t=<token>`) |
| Web | React + Vite + TypeScript, served by the API at `/` |
| iOS | SwiftUI, iOS 17+, Swift Charts, Keychain, camera QR pairing |
| Android | Kotlin, Jetpack Compose, Material 3, OkHttp + kotlinx.serialization, Canvas charts |
| Scope | Markets, Options, Strategy, Trade stepper, Alerts, Journal, Research, Settings |
| Look | Clean light (white surfaces, soft cards, generous spacing), dark mode follows system |
| Push | Out of scope; live alerts via server-sent events while the app is open |

## Server

- Command logic moves from `cli.py` into `service.py` (pure functions returning dicts). The CLI and
  the API both call it, so outputs are identical.
- `idt serve [--host 0.0.0.0] [--port 8742] [--demo]`. `--demo` uses the repo fixtures and pins the
  clock to 2026-10-29 09:45 IST so every screen has data without a Dhan account.
- JSON endpoints under `/api` (bearer auth, except `/api/health`):
  status · indices · index/{symbol} (levels + candles + EMA/VWAP series) · expiries/{u} · chain/{u} ·
  strategies · strategy (preview/write, with payoff curve) · scan/{setup} · entry/{symbol} · plan ·
  timemachine · size · orders · risk · ticket · ticket/confirm · journal · alerts (+check) ·
  events (SSE) · news · ban · results/{s} · insider/{kind} · config (GET/PATCH whitelist) · charges.
- `ticket/confirm` requires `{"hash": <orders hash>, "typed": "yes"}`: the type-to-confirm rule is
  enforced server-side, not just in the UI.
- Errors: HTTP 400 `{"error": "..."}` for DataError/ValueError/TicketError; 401 for a bad token.
- CORS open (token-protected) so the Vite dev server and mobile apps can call it.

## Clients

Navigation: mobile bottom tabs **Markets · Options · Trade · Alerts · More** (More = Strategy
shortcut, Research, Journal, Settings); web sidebar with the same sections.

- **Markets**: index cards (last, % change, ORB state, trend); detail = candle chart with OR band,
  PDH/PDL, CPR lines, EMA 9/21, levels list, CPR read.
- **Options**: underlying + expiry pickers; header (spot, ATM IV, PCR, max pain, expected move);
  chain table around ATM with CE/PE OI bars, OI change, LTP, IV, buildup tags; walls.
- **Strategy**: template picker + params (lots, offset, width, delta) or custom legs; payoff chart
  (expiry + today), breakevens, max P/L, Greeks, margin, naked warning; "Use for trade" writes it.
- **Trade**: stepper Setup → Plan → Odds → Size → Risk → Ticket. Risk shows a PASS/BLOCK banner with
  each check. Ticket shows legs and exits; confirm needs typing `yes`.
- **Alerts**: list with pending/fired, add price alert, add from plan, live updates via SSE.
- **Journal**: today's realised P/L, trades, record a close.
- **Research**: news, F&O ban list, bulk/block deals, insider (PIT), results.
- **Settings**: server URL + token (QR scan on mobile), mode, limits (editable whitelist), demo badge.

Formatting everywhere: ₹ with Indian grouping (1,23,456.00), IST times, tabular numerals, green/red
only for direction/P&L, one indigo accent for actions.

## Layout

```
src/idt/service.py            shared command logic
src/idt/server/app.py         FastAPI app, auth, SSE, static web
apps/web/                     React + Vite + TS
apps/ios/                     SwiftUI app (XcodeGen project.yml or checked-in .xcodeproj)
apps/android/                 Gradle project, Compose
```

## Testing

Server: pytest + FastAPI TestClient on fixtures (auth, each endpoint, confirm needs "yes").
Web: `tsc --noEmit`, vitest for formatters, `vite build`. iOS: `xcodebuild` build + unit tests for
decoding/formatting, simulator screenshot against `idt serve --demo`. Android: `gradlew
assembleDebug testDebugUnitTest`, emulator screenshot against the demo server.
