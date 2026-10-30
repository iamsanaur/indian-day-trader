"""Command logic shared by the `idt` CLI and the API server. Every function returns a JSON-able dict.

Functions raise DataError / ValueError / TicketError with user-facing messages.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np

from . import alerts as alerts_mod
from . import charges as chg
from . import charts
from . import entry as entry_mod
from . import fno
from . import indicators as ind
from . import plan as plan_mod
from . import risk as risk_mod
from . import scanner
from . import sizing
from . import strategy as strat_mod
from . import ticket as ticket_mod
from . import timemachine as tm
from .config import DEFAULTS, append_journal, load_config, load_state, read_journal, save_state, workspace
from .data import DataError, get_nse
from .market import IST, INDICES, at, index_info, phase

MAIN_INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "INDIAVIX"]

# Config keys the apps may change. Data provider and paths stay CLI/file-only.
EDITABLE_CONFIG = {"mode", "capital", "max_loss_per_trade", "daily_loss_cap", "max_trades_per_day", "leverage_cap",
                   "or_minutes", "entry_expiry", "entry_cutoff", "squareoff", "allow_short", "allow_naked",
                   "block_expiry_day_selling", "min_premium", "stale_quote_seconds", "require_ban_check"}


def jsonable(o):
    """Recursively convert numpy scalars and non-finite floats for JSON."""
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        o = o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def intraday(data, symbol: str, day: date, sessions_back: int = 10, interval: int = 5):
    return data.candles(symbol, interval, day - timedelta(days=int(sessions_back * 1.6) + 4), day)


def daily(data, symbol: str, day: date, days: int = 400):
    return data.candles(symbol, "D", day - timedelta(days=days), day)


def pick_expiry(data, underlying: str, wanted: str | None, today: date) -> date:
    expiries = [e for e in data.expiries(underlying) if e >= today]
    if not expiries:
        raise DataError(f"No upcoming expiries for {underlying}")
    if not wanted or wanted == "near":
        return expiries[0]
    if wanted == "next":
        return expiries[min(1, len(expiries) - 1)]
    if wanted == "monthly":  # last expiry of the nearest month that has one
        month = expiries[0].month
        return [e for e in expiries if e.month == month][-1]
    return date.fromisoformat(wanted)


def _plan_or_die() -> dict:
    p = load_state("plan.json")
    if not p:
        raise DataError("No idt/plan.json. Run `idt exit plan ... --write` first.")
    return p


def _available(cfg, data) -> float | None:
    if cfg["mode"] == "live":
        try:
            return float(data.funds()["available"])
        except (DataError, KeyError):
            return None
    return float(cfg["capital"])


# --- workspace -------------------------------------------------------------------------

def init() -> dict:
    path = workspace() / "config.json"
    if not path.exists():
        save_state("config.json", {k: v for k, v in DEFAULTS.items() if k != "nse_user_agent"})
    if not (workspace() / "watchlist.json").exists():
        save_state("watchlist.json", ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN"])
    return {"workspace": str(workspace().resolve()), "config": str(path), "mode": load_config()["mode"],
            "next": "Edit idt/config.json (capital, max_loss_per_trade, daily_loss_cap), then set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN."}


def status(cfg: dict, now: datetime) -> dict:
    journal = read_journal()
    today = now.date().isoformat()
    closes = [e for e in journal if e.get("type") == "close" and str(e.get("ts"))[:10] == today]
    return {"now": now.isoformat(), "phase": phase(now, cfg["holidays"]), "mode": cfg["mode"],
            "data_provider": cfg["data_provider"],
            "trades_today": sum(1 for e in journal if e.get("type") == "confirm" and str(e.get("ts"))[:10] == today),
            "realised_today": sum(float(e.get("pnl", 0)) for e in closes),
            "limits": {k: cfg[k] for k in ("capital", "max_loss_per_trade", "daily_loss_cap", "max_trades_per_day",
                                           "allow_short", "allow_naked")},
            "files": sorted(p.name for p in workspace().glob("*.json"))}


def get_config(cfg: dict) -> dict:
    return {"config": {k: cfg[k] for k in sorted(EDITABLE_CONFIG)}, "editable": sorted(EDITABLE_CONFIG),
            "data_provider": cfg["data_provider"]}


def update_config(changes: dict) -> dict:
    bad = sorted(set(changes) - EDITABLE_CONFIG)
    if bad:
        raise ValueError(f"not editable from the app: {', '.join(bad)}")
    if "mode" in changes and changes["mode"] not in ("paper", "live"):
        raise ValueError("mode must be paper or live")
    current = load_state("config.json", {}) or {}
    current.update(changes)
    save_state("config.json", current)
    return get_config(load_config())


# --- markets ---------------------------------------------------------------------------

def _series(s) -> list:
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 2) for v in s]


def index_view(data, cfg: dict, symbol: str, now: datetime, interval: int = 5, days: int = 2, chart: bool = False,
               html: bool = False, future: bool = False, candles: bool = False) -> dict:
    symbol = symbol.upper()
    traded = f"{symbol} FUT" if future else symbol
    df = intraday(data, traded, now.date(), max(days, 10), interval)
    df = df[df.index < now]
    if df.empty:
        raise DataError(f"No intraday data for {traded}")
    last_day = df.index[-1].date()
    dly = daily(data, traded, last_day, 60)
    prev = ind.prev_day_levels(dly, last_day) or ind.prev_day_levels(ind.daily_from_intraday(df), last_day)
    rng = ind.opening_range(df, last_day, cfg["or_minutes"])
    piv = ind.cpr(prev["high"], prev["low"], prev["close"]) if prev else {}
    df = df.assign(ema9=ind.ema(df["close"], 9), ema21=ind.ema(df["close"], 21), vwap=ind.vwap(df))
    today = ind.session(df, last_day)
    last = float(today["close"].iloc[-1])
    orb = entry_mod.check(df, now if now.date() == last_day else at(last_day, "15:30"), "orb", day=last_day,
                          or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"])
    ema9, ema21 = float(df["ema9"].iloc[-1]), float(df["ema21"].iloc[-1])
    out = {
        "symbol": traded, "as_of": today.index[-1].isoformat(), "last": last,
        "change_pct": round((last / prev["close"] - 1) * 100, 2) if prev else None,
        "day": {"open": float(today["open"].iloc[0]), "high": float(today["high"].max()), "low": float(today["low"].min())},
        "opening_range": rng, "orb": {k: orb.get(k) for k in ("state", "side", "trigger_time", "entry", "detail")},
        "prev_day": prev, "cpr": piv,
        "cpr_read": (("narrow CPR: trending day more likely" if piv["width_pct"] < 0.25 else
                      "wide CPR: range day more likely" if piv["width_pct"] > 0.6 else "normal CPR")
                     + f"; price {'above' if last > piv['tc'] else 'below' if last < piv['bc'] else 'inside'} CPR") if piv else None,
        "ema": {"ema9": round(ema9, 2), "ema21": round(ema21, 2),
                "trend": "up" if ema9 > ema21 and last > ema21 else "down" if ema9 < ema21 and last < ema21 else "mixed"},
        "vwap": round(float(df["vwap"].iloc[-1]), 2) if df["vwap"].notna().iloc[-1] else None,
    }
    if out["vwap"] is None and index_info(symbol) and not future:
        out["vwap_note"] = "spot indices have no volume; use --future for VWAP on the near-month future"
    sessions = sorted(set(df.index.date))
    show = df[df.index.date >= sessions[-min(days, len(sessions))]]
    if candles:
        out["candles"] = [{"t": int(ts.timestamp()), "o": r.open, "h": r.high, "l": r.low, "c": r.close, "v": r.volume}
                          for ts, r in show.iterrows()]
        out["series"] = {"ema9": _series(show["ema9"]), "ema21": _series(show["ema21"]), "vwap": _series(show["vwap"])}
    if chart:
        levels = {"or_high": rng and rng["high"], "or_low": rng and rng["low"], "pdh": prev and prev["high"],
                  "pdl": prev and prev["low"], "pivot": piv.get("pivot"), "tc": piv.get("tc"), "bc": piv.get("bc"),
                  "r1": piv.get("r1"), "s1": piv.get("s1")}
        overlays = {"EMA 9": show["ema9"], "EMA 21": show["ema21"], "VWAP": show["vwap"]}
        paths = charts.price_chart(show, f"{traded} {interval}m  {last_day}", levels, overlays,
                                   workspace() / "charts" / f"{traded.replace(' ', '_')}_{last_day}", html)
        out["charts"] = [str(p) for p in paths]
    return out


def index_board(data, cfg: dict, now: datetime) -> dict:
    board = {}
    for sym in MAIN_INDICES:
        try:
            v = index_view(data, cfg, sym, now, 5, 1)
            board[sym] = {k: v[k] for k in ("last", "change_pct", "orb", "ema", "cpr_read", "day")}
        except DataError as exc:
            board[sym] = {"error": str(exc)}
    return {"as_of": now.isoformat(), "indices": board}


def expiries(data, underlying: str) -> dict:
    return {"underlying": underlying.upper(), "expiries": [e.isoformat() for e in data.expiries(underlying)]}


def chain(data, cfg: dict, underlying: str, now: datetime, expiry: str | None = None, strikes: int = 10,
          chart: bool = False) -> dict:
    exp = pick_expiry(data, underlying, expiry, now.date())
    ch = data.option_chain(underlying, exp)
    analysis = fno.analyze_chain(ch, cfg["risk_free_rate"], now, strikes)
    analysis["lot_size"] = data.instruments.lot_size(ch.underlying)
    if chart:
        analysis["chart"] = str(charts.oi_chart(analysis, workspace() / "charts" / f"{ch.underlying}_oi_{exp}"))
    save_state("chain.json", analysis)
    return analysis


# --- strategy & trade flow ---------------------------------------------------------------

def view_of(name: str) -> str:
    if name in ("long-call", "bull-call-spread", "bull-put-spread", "short-put"):
        return "long"
    if name in ("long-put", "bear-put-spread", "bear-call-spread", "short-call"):
        return "short"
    return "neutral"


def strategy(data, cfg: dict, name: str, underlying: str, now: datetime, expiry: str | None = None, lots: int = 1,
             offset: int = 0, width: int = 2, delta: float | None = None, legs: list[str] | None = None,
             chart: bool = False, write: bool = False, curve: bool = False) -> dict:
    exp = pick_expiry(data, underlying, expiry, now.date())
    ch = data.option_chain(underlying, exp)
    lot = data.instruments.lot_size(ch.underlying)
    built = ([strat_mod.parse_leg_spec(s, ch) for s in (legs or [])] if name == "custom"
             else strat_mod.build(name, ch, lots, offset, width, delta))
    if not built:
        raise ValueError("custom strategy needs at least one leg, e.g. +1x26000CE")
    a = strat_mod.analyze(built, ch.spot, lot)
    result = {"name": name, "underlying": ch.underlying, "expiry": exp.isoformat(), "spot": ch.spot, "lot_size": lot,
              "view": view_of(name), "legs": [l.to_dict() for l in built], "analysis": a,
              "greeks": strat_mod.aggregate_greeks(built, ch.spot, now, cfg["risk_free_rate"], lot)}
    try:
        order_legs = [{"symbol": l.symbol, "side": "BUY" if l.side > 0 else "SELL", "quantity": l.lots * lot,
                       "price": l.premium, "product": cfg["product_intraday"]} for l in built]
        result["margin"] = data.margin(order_legs)
    except DataError as exc:
        result["margin"] = {"error": str(exc)}
    if a["naked"] and not cfg["allow_naked"]:
        result["warning"] = "Naked short options: risk check will BLOCK unless allow_naked is true in config."
    if chart or curve:
        grid = np.linspace(ch.spot * 0.92, ch.spot * 1.08, 161)
        at_expiry = strat_mod.pnl_at_expiry(built, grid, lot)
        today = strat_mod.pnl_now(built, grid, now, cfg["risk_free_rate"], lot)
        if curve:
            result["curve"] = {"x": _series(grid), "expiry": _series(at_expiry), "today": _series(today)}
        if chart:
            result["chart"] = str(charts.payoff_chart(grid, at_expiry, today, ch.spot, a["breakevens"],
                                                      f"{name} {ch.underlying} {exp} (1 set, lot {lot})",
                                                      workspace() / "charts" / f"payoff_{ch.underlying}_{name}"))
    if write:
        save_state("strategy.json", {k: v for k, v in result.items() if k != "curve"})
        result["written"] = "idt/strategy.json"
    return result


def _universe(data, which: str) -> list[str]:
    if which == "fno":
        return data.instruments.fno_stocks()
    if which == "watchlist":
        return load_state("watchlist.json", [])
    if which == "indices":
        return [i for i in INDICES if INDICES[i].fno_segment]
    return [s.strip().upper() for s in which.split(",") if s.strip()]


def scan(data, cfg: dict, setup: str, now: datetime, universe: str = "watchlist", limit: int = 20,
         max_symbols: int = 250, verbose: bool = False) -> dict:
    if setup not in ("orb", "flag", "bounce"):
        raise ValueError("setup must be orb, flag or bounce")
    symbols = _universe(data, universe)[:max_symbols]
    hits, errors = [], {}
    for sym in symbols:
        try:
            if setup == "orb":
                df = intraday(data, sym, now.date())
                hit = scanner.orb(sym, df[df.index < now], now, cfg)
            else:
                dly = daily(data, sym, now.date())
                dly = dly[dly.index.date < now.date()] if now.time() < at(now.date(), "15:30").time() else dly
                hit = scanner.bull_flag(sym, dly) if setup == "flag" else scanner.oversold_bounce(sym, dly)
            if hit:
                hits.append(hit)
        except (DataError, ValueError, KeyError) as exc:
            errors[sym] = str(exc)
    return {"setup": setup, "as_of": now.isoformat(), "scanned": len(symbols), "hits": scanner.rank(hits)[:limit],
            "errors": errors if verbose else len(errors)}


def entry_check(data, cfg: dict, symbol: str, now: datetime, setup: str = "orb", above: float | None = None,
                below: float | None = None, write: bool = False) -> dict:
    df = intraday(data, symbol, now.date())
    prev = ind.prev_day_levels(daily(data, symbol, now.date(), 30), now.date()) if setup == "pdh" else None
    seen = df[df.index < now]
    res = entry_mod.check(seen, now, setup, or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"],
                          above=above, below=below, prev=prev)
    res["symbol"] = symbol.upper()
    if res["state"] == "triggered" and write:
        a = ind.atr(seen, 14)
        res["atr"] = round(float(a.iloc[-1]), 2) if a.notna().any() else None
        save_state("setup.json", res)
        res["written"] = "idt/setup.json"
    return res


def exit_plan(data, cfg: dict, now: datetime, kind: str | None = None, stop: str | None = None,
              target: str | None = None, option: str = "auto", strike_offset: int = 0, expiry: str | None = None,
              symbol: str | None = None, side: str = "long", entry: float | None = None, write: bool = False) -> dict:
    if kind == "strategy":
        strat = load_state("strategy.json")
        if not strat:
            raise DataError("No idt/strategy.json. Run `idt strategy NAME UNDERLYING --write` first.")
        p = plan_mod.strategy_plan(strat, stop or "maxloss-pct:50", target or "maxprofit-pct:60", cfg["squareoff"])
        setup = load_state("setup.json")
        if setup and setup.get("symbol") == p["symbol"] and setup.get("state") == "triggered":
            p["trigger_time"], p["setup"] = setup.get("trigger_time"), f"{setup['setup']} -> {p['strategy']}"
    else:
        setup = load_state("setup.json")
        if entry:
            if not symbol:
                raise ValueError("--entry needs --symbol")
            same = setup and setup.get("symbol") == symbol.upper()
            setup = {"symbol": symbol.upper(), "side": side, "entry": entry, "setup": "manual",
                     "range": setup.get("range") if same else None}
        if not setup:
            raise DataError("No idt/setup.json. Run `idt entry check SYMBOL --write` or pass --symbol/--side/--entry.")
        sym = setup["symbol"]
        kind = kind or ("option" if index_info(sym) else "equity")
        stop = stop or ("or-mid" if setup.get("range") else "pct:0.5")
        target = target or "1.5R"
        if kind == "equity":
            p = plan_mod.linear_plan(setup, "equity", stop, target, cfg["squareoff"], sym)
        elif kind == "future":
            fut = data.instrument(f"{sym} FUT")
            q = data.quote([sym, f"{sym} FUT"])
            offset = q[f"{sym} FUT"].ltp - q[sym].ltp if len(q) == 2 else 0.0
            p = plan_mod.linear_plan(setup, "future", stop, target, cfg["squareoff"], fut.symbol, fut.lot_size, offset)
        else:
            exp = pick_expiry(data, sym, expiry, now.date())
            ch = data.option_chain(sym, exp)
            opt = option if option != "auto" else ("CE" if setup["side"] == "long" else "PE")
            step = strat_mod.strike_step(ch)
            atm = min(ch.strikes(), key=lambda k: abs(k - setup["entry"]))
            strike = atm + strike_offset * step * (1 if opt == "CE" else -1)
            leg = strat_mod.make_leg(ch, strike, opt, +1, 1)
            p = plan_mod.option_plan(setup, leg, data.instruments.lot_size(sym), stop, target, cfg["squareoff"],
                                     cfg["risk_free_rate"], now)
    p["created"] = now.isoformat()
    if write:
        save_state("plan.json", p)
        p["written"] = "idt/plan.json"
    return p


def get_plan() -> dict:
    return {"plan": load_state("plan.json"), "setup": load_state("setup.json"), "strategy": load_state("strategy.json")}


def timemachine(data, cfg: dict, now: datetime, paths: int = 10000, seed: int = 42, days: int = 59,
                write: bool = False) -> dict:
    p = _plan_or_die()
    day = datetime.fromisoformat(p["created"]).date()
    df5 = intraday(data, p["symbol"], day, days)
    if p.get("trigger_time"):
        start = datetime.fromisoformat(p["trigger_time"]) + timedelta(minutes=5)
    else:
        start = now.replace(second=0, microsecond=0)
        start += timedelta(minutes=(5 - start.minute % 5) % 5)
    sim = tm.simulate(p, df5, start, paths, seed, cfg["risk_free_rate"])
    rep = tm.replay(p, df5, day, cfg)
    orders = load_state("orders.json")
    out = {"plan": {k: p.get(k) for k in ("symbol", "kind", "side", "basis", "entry", "stop", "target", "stop_pnl",
                                          "target_pnl", "risk_per_unit", "reward_per_unit", "rr")},
           "monte_carlo": sim, "replay": rep,
           "caveat": "Simulation from prior sessions' 5-minute bars, constant IV for options. Not a prediction."}
    if orders and orders.get("units"):
        out["sized"] = {"units": orders["units"], "expected_pnl": round(sim["pnl_per_unit"]["mean"] * orders["units"], 2)}
    if write:
        save_state("timemachine.json", out)
    return out


def size(data, cfg: dict, now: datetime, max_loss: float | None = None, write: bool = False) -> dict:
    p = _plan_or_die()
    quote_ts = None
    try:
        q = data.quote([p["symbol"]]).get(p["symbol"])
        quote_ts = (q.ts or now).isoformat() if q else None
    except DataError:
        pass
    info = index_info(p["symbol"])
    exchange = "BSE" if info and info.exchange == "BSE" else "NSE"
    orders = sizing.size(p, cfg, data.margin, _available(cfg, data), quote_ts, exchange, max_loss, now)
    if write:
        save_state("orders.json", orders)
        orders["written"] = "idt/orders.json"
    return orders


def risk(data, cfg: dict, now: datetime) -> dict:
    p, orders = _plan_or_die(), load_state("orders.json")
    if not orders:
        raise DataError("No idt/orders.json. Run `idt size --write` first.")
    ban = None
    if not index_info(p["symbol"]) and p["kind"] != "equity":
        try:
            ban = get_nse(cfg).ban_list()
        except DataError:
            ban = None
    verdict = risk_mod.check(cfg, p, orders, read_journal(), now, ban_list=ban, available=_available(cfg, data))
    save_state("risk.json", verdict)
    return verdict


def ticket_show(now: datetime) -> dict:
    p, orders, r = _plan_or_die(), load_state("orders.json"), load_state("risk.json")
    if not orders:
        raise DataError("No idt/orders.json.")
    return ticket_mod.build(p, orders, r, now)


def ticket_confirm(cfg: dict, now: datetime, order_hash: str) -> dict:
    t = ticket_show(now)
    orders, p = load_state("orders.json"), load_state("plan.json")
    if order_hash != orders["hash"]:
        raise ticket_mod.TicketError(f"Hash mismatch: confirm needs {orders['hash']}")
    append_journal({"type": "confirm", "ts": now.isoformat(), "hash": orders["hash"], "mode": cfg["mode"],
                    "symbol": p["symbol"], "kind": p["kind"], "legs": orders["legs"], "loss_at_stop": orders["loss_at_stop"]})
    return {"confirmed": orders["hash"], "mode": cfg["mode"],
            "next": ("Paper mode: recorded as a paper fill at the planned prices." if cfg["mode"] == "paper"
                     else "Place the ticket in your broker now. Nothing has been sent."),
            "ticket": t}


def journal(now: datetime, close_pnl: float | None = None, symbol: str | None = None, note: str | None = None,
            tail: int = 50) -> list:
    if close_pnl is not None:
        append_journal({"type": "close", "ts": now.isoformat(), "pnl": close_pnl, "symbol": symbol, "note": note})
    return read_journal()[-tail:]


# --- alerts ----------------------------------------------------------------------------

def alerts_list() -> list:
    return load_state("alerts.json", [])


def alerts_add(from_plan: bool = False, symbol: str | None = None, above: float | None = None,
               below: float | None = None, label: str | None = None) -> list:
    items = alerts_list()
    if from_plan:
        items += alerts_mod.from_plan(_plan_or_die())
    else:
        if not symbol or (above is None and below is None):
            raise DataError("alerts add needs --from-plan or --symbol with --above/--below")
        if above is not None:
            items.append(alerts_mod.new("price", symbol.upper(), ">=", above, label or f"{symbol.upper()} >= {above}"))
        if below is not None:
            items.append(alerts_mod.new("price", symbol.upper(), "<=", below, label or f"{symbol.upper()} <= {below}"))
    save_state("alerts.json", items)
    return items


def alerts_clear() -> list:
    save_state("alerts.json", [])
    return []


def alerts_check(data, now: datetime) -> dict:
    items = alerts_list()
    syms = alerts_mod.symbols_needed(items)
    prices = {s: q.ltp for s, q in data.quote(syms).items()} if syms else {}
    fired = alerts_mod.evaluate(items, prices, now)
    save_state("alerts.json", items)
    return {"as_of": now.isoformat(), "prices": prices, "fired": fired, "pending": [a for a in items if not a["fired"]]}


# --- research --------------------------------------------------------------------------

def news(cfg: dict, now: datetime, symbols: str | None = None, hours: int = 12) -> dict:
    nse = get_nse(cfg)
    syms = [s.strip().upper() for s in symbols.split(",")] if symbols else load_state("watchlist.json", [])
    p = load_state("plan.json")
    if p and not symbols and not index_info(p["symbol"]) and p["symbol"] not in syms:
        syms.append(p["symbol"])
    cutoff = now - timedelta(hours=hours)
    out, errors = [], {}
    for sym in syms:
        try:
            for item in nse.announcements(sym, days=max(1, math.ceil(hours / 24))):
                try:
                    ts = datetime.strptime(item["time"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
                except (TypeError, ValueError):
                    ts = None
                if ts is None or ts >= cutoff:
                    out.append(dict(item, time=ts.isoformat() if ts else item["time"]))
        except DataError as exc:
            errors[sym] = str(exc)
    out.sort(key=lambda x: str(x["time"]), reverse=True)
    return {"symbols": syms, "hours": hours, "announcements": out, "errors": errors}


def results(cfg: dict, symbol: str, quarters: int = 8) -> dict:
    rows = get_nse(cfg).results(symbol)
    rows = [r for r in rows if r["revenue"] is not None or r["net_profit"] is not None][:quarters]
    for cur, older in zip(rows, rows[1:]):
        for k in ("revenue", "net_profit"):
            if cur[k] and older[k]:
                cur[f"{k}_qoq_pct"] = round((cur[k] / older[k] - 1) * 100, 1)
    for i, cur in enumerate(rows):
        if i + 4 < len(rows):
            yoy = rows[i + 4]
            for k in ("revenue", "net_profit", "eps"):
                if cur[k] and yoy[k]:
                    cur[f"{k}_yoy_pct"] = round((cur[k] / yoy[k] - 1) * 100, 1)
    return {"symbol": symbol.upper(), "quarters": rows,
            "note": "From NSE results filings (units as filed, usually Rs lakh). Verify against the filing before acting."}


def insider(cfg: dict, kind: str, symbol: str | None = None, days: int = 30):
    nse = get_nse(cfg)
    if kind == "deals":
        deals = nse.large_deals()
        if symbol:
            deals = {k: [d for d in v if d["symbol"] == symbol.upper()] for k, v in deals.items()}
        return deals
    if kind == "pit":
        return nse.insider(symbol, days)
    raise ValueError("kind must be deals or pit")


def ban(cfg: dict) -> dict:
    return {"ban_list": get_nse(cfg).ban_list()}


def charges(cfg: dict, segment: str, buy: float, sell: float, exchange: str = "NSE", orders: int = 2) -> dict:
    return {"segment": segment, "venue": exchange, "rates_effective": chg.RATES["effective"],
            **chg.compute(segment, buy, sell, exchange, orders, cfg["brokerage"], cfg.get("charges_override"))}
