"""`idt` command line. Every command prints JSON so Claude (and humans) can read it."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
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
from .data import DataError, get_data, get_nse
from .market import IST, INDICES, at, index_info, now_ist, phase

MAIN_INDICES = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "INDIAVIX"]


def emit(obj) -> None:
    print(json.dumps(obj, indent=2, default=_default))


def _default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, float) and math.isinf(o):
        return None
    return str(o)


def get_now(args) -> datetime:
    if getattr(args, "now", None):
        return datetime.fromisoformat(args.now).replace(tzinfo=IST)
    return now_ist()


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


# --- commands ------------------------------------------------------------------------

def cmd_init(args, cfg):
    path = workspace() / "config.json"
    if not path.exists():
        save_state("config.json", {k: v for k, v in DEFAULTS.items() if k != "nse_user_agent"})
    if not (workspace() / "watchlist.json").exists():
        save_state("watchlist.json", ["RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", "SBIN"])
    emit({"workspace": str(workspace().resolve()), "config": str(path), "mode": load_config()["mode"],
          "next": "Edit idt/config.json (capital, max_loss_per_trade, daily_loss_cap), then set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN."})


def cmd_status(args, cfg):
    now = get_now(args)
    journal = read_journal()
    today = now.date().isoformat()
    closes = [e for e in journal if e.get("type") == "close" and str(e.get("ts"))[:10] == today]
    emit({"now": now.isoformat(), "phase": phase(now, cfg["holidays"]), "mode": cfg["mode"],
          "data_provider": cfg["data_provider"], "trades_today": sum(1 for e in journal if e.get("type") == "confirm" and str(e.get("ts"))[:10] == today),
          "realised_today": sum(float(e.get("pnl", 0)) for e in closes),
          "limits": {k: cfg[k] for k in ("capital", "max_loss_per_trade", "daily_loss_cap", "max_trades_per_day", "allow_short", "allow_naked")},
          "files": sorted(p.name for p in workspace().glob("*.json"))})


def _index_view(data, symbol: str, now: datetime, cfg: dict, interval: int, days: int, chart: bool, html: bool,
                future: bool):
    traded = f"{symbol} FUT" if future else symbol
    day = now.date()
    df = intraday(data, traded, day, max(days, 10), interval)
    df = df[df.index < now]
    if df.empty:
        raise DataError(f"No intraday data for {traded}")
    last_day = df.index[-1].date()
    dly = daily(data, traded, last_day, 60)
    prev = ind.prev_day_levels(dly, last_day) or ind.prev_day_levels(ind.daily_from_intraday(df), last_day)
    rng = ind.opening_range(df, last_day, cfg["or_minutes"])
    piv = ind.cpr(prev["high"], prev["low"], prev["close"]) if prev else {}
    df["ema9"], df["ema21"], df["vwap"] = ind.ema(df["close"], 9), ind.ema(df["close"], 21), ind.vwap(df)
    today = ind.session(df, last_day)
    last = float(today["close"].iloc[-1])
    orb = entry_mod.check(df, now if now.date() == last_day else at(last_day, "15:30"), "orb", day=last_day,
                          or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"])
    out = {
        "symbol": traded, "as_of": today.index[-1].isoformat(), "last": last,
        "change_pct": round((last / prev["close"] - 1) * 100, 2) if prev else None,
        "day": {"open": float(today["open"].iloc[0]), "high": float(today["high"].max()), "low": float(today["low"].min())},
        "opening_range": rng, "orb": {k: orb.get(k) for k in ("state", "side", "trigger_time", "entry", "detail")},
        "prev_day": prev, "cpr": piv,
        "cpr_read": (("narrow CPR: trending day more likely" if piv["width_pct"] < 0.25 else
                      "wide CPR: range day more likely" if piv["width_pct"] > 0.6 else "normal CPR")
                     + f"; price {'above' if last > piv['tc'] else 'below' if last < piv['bc'] else 'inside'} CPR") if piv else None,
        "ema": {"ema9": round(float(df["ema9"].iloc[-1]), 2), "ema21": round(float(df["ema21"].iloc[-1]), 2),
                "trend": "up" if df["ema9"].iloc[-1] > df["ema21"].iloc[-1] and last > df["ema21"].iloc[-1]
                else "down" if df["ema9"].iloc[-1] < df["ema21"].iloc[-1] and last < df["ema21"].iloc[-1] else "mixed"},
        "vwap": round(float(df["vwap"].iloc[-1]), 2) if df["vwap"].notna().iloc[-1] else None,
    }
    if out["vwap"] is None and index_info(symbol) and not future:
        out["vwap_note"] = "spot indices have no volume; use --future for VWAP on the near-month future"
    if chart:
        show = df[df.index.date >= sorted(set(df.index.date))[-min(days, len(set(df.index.date)))]]
        levels = {"or_high": rng and rng["high"], "or_low": rng and rng["low"], "pdh": prev and prev["high"],
                  "pdl": prev and prev["low"], "pivot": piv.get("pivot"), "tc": piv.get("tc"), "bc": piv.get("bc"),
                  "r1": piv.get("r1"), "s1": piv.get("s1")}
        overlays = {"EMA 9": show["ema9"], "EMA 21": show["ema21"], "VWAP": show["vwap"]}
        name = traded.replace(" ", "_")
        paths = charts.price_chart(show, f"{traded} {interval}m  {last_day}", levels, overlays,
                                   workspace() / "charts" / f"{name}_{last_day}", html)
        out["charts"] = [str(p) for p in paths]
    return out


def cmd_index(args, cfg):
    data = get_data(cfg)
    now = get_now(args)
    if args.symbol:
        emit(_index_view(data, args.symbol.upper(), now, cfg, args.interval, args.days, True, args.html, args.future))
        return
    board = {}
    for sym in MAIN_INDICES:
        try:
            v = _index_view(data, sym, now, cfg, args.interval, 1, False, False, False)
            board[sym] = {k: v[k] for k in ("last", "change_pct", "orb", "ema", "cpr_read")}
        except DataError as exc:
            board[sym] = {"error": str(exc)}
    emit({"as_of": now.isoformat(), "indices": board})


def cmd_expiries(args, cfg):
    data = get_data(cfg)
    emit({"underlying": args.underlying.upper(), "expiries": [e.isoformat() for e in data.expiries(args.underlying)]})


def cmd_chain(args, cfg):
    data = get_data(cfg)
    now = get_now(args)
    expiry = pick_expiry(data, args.underlying, args.expiry, now.date())
    chain = data.option_chain(args.underlying, expiry)
    analysis = fno.analyze_chain(chain, cfg["risk_free_rate"], now, args.strikes)
    analysis["lot_size"] = data.instruments.lot_size(chain.underlying)
    if args.chart:
        analysis["chart"] = str(charts.oi_chart(analysis, workspace() / "charts" / f"{chain.underlying}_oi_{expiry}"))
    save_state("chain.json", analysis)
    emit(analysis)


def _view_of(name: str) -> str:
    if name in ("long-call", "bull-call-spread", "bull-put-spread", "short-put"):
        return "long"
    if name in ("long-put", "bear-put-spread", "bear-call-spread", "short-call"):
        return "short"
    return "neutral"


def cmd_strategy(args, cfg):
    if args.name == "list":
        emit(strat_mod.STRATEGIES)
        return
    data = get_data(cfg)
    now = get_now(args)
    expiry = pick_expiry(data, args.underlying, args.expiry, now.date())
    chain = data.option_chain(args.underlying, expiry)
    lot = data.instruments.lot_size(chain.underlying)
    if args.name == "custom":
        legs = [strat_mod.parse_leg_spec(s, chain) for s in args.leg]
    else:
        legs = strat_mod.build(args.name, chain, args.lots, args.offset, args.width, args.delta)
    a = strat_mod.analyze(legs, chain.spot, lot)
    result = {"name": args.name, "underlying": chain.underlying, "expiry": expiry.isoformat(), "spot": chain.spot,
              "lot_size": lot, "view": _view_of(args.name), "legs": [l.to_dict() for l in legs], "analysis": a,
              "greeks": strat_mod.aggregate_greeks(legs, chain.spot, now, cfg["risk_free_rate"], lot)}
    try:
        order_legs = [{"symbol": l.symbol, "side": "BUY" if l.side > 0 else "SELL", "quantity": l.lots * lot,
                       "price": l.premium, "product": cfg["product_intraday"]} for l in legs]
        result["margin"] = data.margin(order_legs)
    except DataError as exc:
        result["margin"] = {"error": str(exc)}
    if a["naked"] and not cfg["allow_naked"]:
        result["warning"] = "Naked short options: risk check will BLOCK unless allow_naked is true in config."
    if args.chart:
        grid = np.linspace(chain.spot * 0.9, chain.spot * 1.1, 400)
        result["chart"] = str(charts.payoff_chart(
            grid, strat_mod.pnl_at_expiry(legs, grid, lot), strat_mod.pnl_now(legs, grid, now, cfg["risk_free_rate"], lot),
            chain.spot, a["breakevens"], f"{args.name} {chain.underlying} {expiry} (1 set, lot {lot})",
            workspace() / "charts" / f"payoff_{chain.underlying}_{args.name}"))
    if args.write:
        save_state("strategy.json", result)
        result["written"] = "idt/strategy.json"
    emit(result)


def _universe(data, which: str) -> list[str]:
    if which == "fno":
        return data.instruments.fno_stocks()
    if which == "watchlist":
        return load_state("watchlist.json", [])
    if which == "indices":
        return [i for i in INDICES if INDICES[i].fno_segment]
    return [s.strip().upper() for s in which.split(",") if s.strip()]


def cmd_scan(args, cfg):
    data = get_data(cfg)
    now = get_now(args)
    symbols = _universe(data, args.universe)[: args.max_symbols]
    hits, errors = [], {}
    for sym in symbols:
        try:
            if args.setup == "orb":
                df = intraday(data, sym, now.date())
                hit = scanner.orb(sym, df[df.index < now], now, cfg)
            else:
                dly = daily(data, sym, now.date())
                dly = dly[dly.index.date < now.date()] if now.time() < at(now.date(), "15:30").time() else dly
                hit = scanner.bull_flag(sym, dly) if args.setup == "flag" else scanner.oversold_bounce(sym, dly)
            if hit:
                hits.append(hit)
        except (DataError, ValueError, KeyError) as exc:
            errors[sym] = str(exc)
    emit({"setup": args.setup, "as_of": now.isoformat(), "scanned": len(symbols), "hits": scanner.rank(hits)[: args.limit],
          "errors": errors if args.verbose else len(errors)})


def cmd_entry(args, cfg):
    data = get_data(cfg)
    while True:
        now = get_now(args)
        df = intraday(data, args.symbol, now.date())
        prev = None
        if args.setup == "pdh":
            prev = ind.prev_day_levels(daily(data, args.symbol, now.date(), 30), now.date())
        res = entry_mod.check(df[df.index < now], now, args.setup, or_minutes=cfg["or_minutes"], expire=cfg["entry_expiry"],
                              above=args.above, below=args.below, prev=prev)
        res["symbol"] = args.symbol.upper()
        if res["state"] == "triggered" and args.write:
            day_df = df[df.index < now]
            a = ind.atr(day_df, 14)
            res["atr"] = round(float(a.iloc[-1]), 2) if a.notna().any() else None
            save_state("setup.json", res)
            res["written"] = "idt/setup.json"
        if args.action == "check" or res["state"] != "waiting" or getattr(args, "now", None):
            emit(res)
            return
        print(json.dumps({"state": res["state"], "as_of": res["as_of"], "last": res.get("last")}), flush=True)
        time.sleep(args.poll)


def cmd_exit(args, cfg):
    data = get_data(cfg)
    now = get_now(args)
    kind = args.kind
    if kind == "strategy":
        strat = load_state("strategy.json")
        if not strat:
            raise DataError("No idt/strategy.json. Run `idt strategy NAME UNDERLYING --write` first.")
        p = plan_mod.strategy_plan(strat, args.stop or "maxloss-pct:50", args.target or "maxprofit-pct:60",
                                   cfg["squareoff"])
        setup = load_state("setup.json")
        if setup and setup.get("symbol") == p["symbol"] and setup.get("state") == "triggered":
            p["trigger_time"], p["setup"] = setup.get("trigger_time"), f"{setup['setup']} -> {p['strategy']}"
    else:
        setup = load_state("setup.json")
        if args.entry:
            setup = {"symbol": args.symbol.upper(), "side": args.side, "entry": args.entry, "setup": "manual",
                     "range": (setup or {}).get("range") if setup and setup.get("symbol") == args.symbol.upper() else None}
        if not setup:
            raise DataError("No idt/setup.json. Run `idt entry check SYMBOL --write` or pass --symbol/--side/--entry.")
        symbol = setup["symbol"]
        kind = kind or ("option" if index_info(symbol) else "equity")
        stop = args.stop or ("or-mid" if setup.get("range") else "pct:0.5")
        target = args.target or "1.5R"
        if kind == "equity":
            p = plan_mod.linear_plan(setup, "equity", stop, target, cfg["squareoff"], symbol)
        elif kind == "future":
            fut = data.instrument(f"{symbol} FUT")
            q = data.quote([symbol, f"{symbol} FUT"])
            offset = q[f"{symbol} FUT"].ltp - q[symbol].ltp if len(q) == 2 else 0.0
            p = plan_mod.linear_plan(setup, "future", stop, target, cfg["squareoff"], fut.symbol, fut.lot_size, offset)
        else:
            expiry = pick_expiry(data, symbol, args.expiry, now.date())
            chain = data.option_chain(symbol, expiry)
            opt = args.option if args.option != "auto" else ("CE" if setup["side"] == "long" else "PE")
            step = strat_mod.strike_step(chain)
            atm = min(chain.strikes(), key=lambda k: abs(k - setup["entry"]))
            strike = atm + args.strike_offset * step * (1 if opt == "CE" else -1)
            leg = strat_mod.make_leg(chain, strike, opt, +1, 1)
            p = plan_mod.option_plan(setup, leg, data.instruments.lot_size(symbol), stop, target, cfg["squareoff"],
                                     cfg["risk_free_rate"], now)
    p["created"] = now.isoformat()
    if args.write:
        save_state("plan.json", p)
        p["written"] = "idt/plan.json"
    emit(p)


def _plan_or_die() -> dict:
    p = load_state("plan.json")
    if not p:
        raise DataError("No idt/plan.json. Run `idt exit plan ... --write` first.")
    return p


def cmd_timemachine(args, cfg):
    data = get_data(cfg)
    p = _plan_or_die()
    now = get_now(args)
    day = datetime.fromisoformat(p["created"]).date()
    df5 = intraday(data, p["symbol"], day, args.days)
    if p.get("trigger_time"):
        start = datetime.fromisoformat(p["trigger_time"]) + timedelta(minutes=5)
    else:
        start = now.replace(second=0, microsecond=0)
        start += timedelta(minutes=(5 - start.minute % 5) % 5)
    sim = tm.simulate(p, df5, start, args.paths, args.seed, cfg["risk_free_rate"])
    rep = tm.replay(p, df5, day, cfg)
    orders = load_state("orders.json")
    out = {"plan": {k: p.get(k) for k in ("symbol", "kind", "side", "basis", "entry", "stop", "target", "stop_pnl",
                                          "target_pnl", "risk_per_unit", "reward_per_unit", "rr")},
           "monte_carlo": sim, "replay": rep,
           "caveat": "Simulation from prior sessions' 5-minute bars, constant IV for options. Not a prediction."}
    if orders and orders.get("units"):
        out["sized"] = {"units": orders["units"], "expected_pnl": round(sim["pnl_per_unit"]["mean"] * orders["units"], 2)}
    if args.write:
        save_state("timemachine.json", out)
    emit(out)


def _available(cfg, data) -> float | None:
    if cfg["mode"] == "live":
        try:
            return float(data.funds()["available"])
        except (DataError, KeyError):
            return None
    return float(cfg["capital"])


def cmd_size(args, cfg):
    data = get_data(cfg)
    p = _plan_or_die()
    now = get_now(args)
    probe = p["symbol"]
    quote_ts = None
    try:
        q = data.quote([probe]).get(probe)
        quote_ts = (q.ts or now).isoformat() if q else None
    except DataError:
        pass
    exchange = "BSE" if (index_info(p["symbol"]) and index_info(p["symbol"]).exchange == "BSE") else "NSE"
    orders = sizing.size(p, cfg, data.margin, _available(cfg, data), quote_ts, exchange, args.max_loss, now)
    if args.write:
        save_state("orders.json", orders)
        orders["written"] = "idt/orders.json"
    emit(orders)


def cmd_risk(args, cfg):
    data = get_data(cfg)
    p, orders = _plan_or_die(), load_state("orders.json")
    if not orders:
        raise DataError("No idt/orders.json. Run `idt size --write` first.")
    ban = None
    if not index_info(p["symbol"]) and p["kind"] != "equity":
        try:
            ban = get_nse(cfg).ban_list()
        except DataError:
            ban = None
    verdict = risk_mod.check(cfg, p, orders, read_journal(), get_now(args), ban_list=ban, available=_available(cfg, data))
    save_state("risk.json", verdict)
    emit(verdict)


def cmd_ticket(args, cfg):
    p, orders, risk = _plan_or_die(), load_state("orders.json"), load_state("risk.json")
    now = get_now(args)
    if not orders:
        raise DataError("No idt/orders.json.")
    t = ticket_mod.build(p, orders, risk, now)
    if args.action == "show":
        emit(t)
        return
    if args.hash != orders["hash"]:
        raise ticket_mod.TicketError(f"Hash mismatch: confirm needs {orders['hash']}")
    entry = {"type": "confirm", "ts": now.isoformat(), "hash": orders["hash"], "mode": cfg["mode"], "symbol": p["symbol"],
             "kind": p["kind"], "legs": orders["legs"], "loss_at_stop": orders["loss_at_stop"]}
    append_journal(entry)
    emit({"confirmed": orders["hash"], "mode": cfg["mode"],
          "next": ("Paper mode: recorded as a paper fill at the planned prices." if cfg["mode"] == "paper"
                   else "Place the ticket in your broker now. Nothing has been sent."),
          "ticket": t})


def cmd_journal(args, cfg):
    now = get_now(args)
    if args.action == "close":
        append_journal({"type": "close", "ts": now.isoformat(), "pnl": args.pnl, "symbol": args.symbol, "note": args.note})
    emit(read_journal()[-args.tail:])


def cmd_alerts(args, cfg):
    items = load_state("alerts.json", [])
    if args.action == "add":
        if args.from_plan:
            items += alerts_mod.from_plan(_plan_or_die())
        else:
            if not args.symbol or (args.above is None and args.below is None):
                raise DataError("alerts add needs --from-plan or --symbol with --above/--below")
            if args.above is not None:
                items.append(alerts_mod.new("price", args.symbol.upper(), ">=", args.above, args.label or f"{args.symbol} >= {args.above}"))
            if args.below is not None:
                items.append(alerts_mod.new("price", args.symbol.upper(), "<=", args.below, args.label or f"{args.symbol} <= {args.below}"))
        save_state("alerts.json", items)
        emit(items)
        return
    if args.action == "clear":
        save_state("alerts.json", [])
        emit([])
        return
    if args.action == "list":
        emit(items)
        return
    data = get_data(cfg)
    while True:
        now = get_now(args)
        syms = alerts_mod.symbols_needed(items)
        prices = {s: q.ltp for s, q in data.quote(syms).items()} if syms else {}
        fired = alerts_mod.evaluate(items, prices, now)
        save_state("alerts.json", items)
        if args.action == "check" or getattr(args, "now", None):
            emit({"as_of": now.isoformat(), "prices": prices, "fired": fired,
                  "pending": [a for a in items if not a["fired"]]})
            return
        for f in fired:
            print(json.dumps({"ALERT": f["label"], "observed": f.get("observed"), "at": f["fired_at"]}), flush=True)
        if all(a["fired"] for a in items):
            return
        time.sleep(args.poll)


def cmd_news(args, cfg):
    nse = get_nse(cfg)
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else load_state("watchlist.json", [])
    p = load_state("plan.json")
    if p and not args.symbols and not index_info(p["symbol"]) and p["symbol"] not in symbols:
        symbols.append(p["symbol"])
    cutoff = get_now(args) - timedelta(hours=args.hours)
    out, errors = [], {}
    for sym in symbols:
        try:
            for item in nse.announcements(sym, days=max(1, math.ceil(args.hours / 24))):
                try:
                    ts = datetime.strptime(item["time"], "%d-%b-%Y %H:%M:%S").replace(tzinfo=IST)
                except (TypeError, ValueError):
                    ts = None
                if ts is None or ts >= cutoff:
                    out.append(dict(item, time=ts.isoformat() if ts else item["time"]))
        except DataError as exc:
            errors[sym] = str(exc)
    out.sort(key=lambda x: str(x["time"]), reverse=True)
    emit({"symbols": symbols, "hours": args.hours, "announcements": out, "errors": errors})


def cmd_results(args, cfg):
    rows = get_nse(cfg).results(args.symbol)
    rows = [r for r in rows if r["revenue"] is not None or r["net_profit"] is not None][: args.quarters]
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
    emit({"symbol": args.symbol.upper(), "quarters": rows,
          "note": "From NSE results filings (units as filed, usually Rs lakh). Verify against the filing before acting."})


def cmd_insider(args, cfg):
    nse = get_nse(cfg)
    if args.action == "deals":
        deals = nse.large_deals()
        if args.symbol:
            deals = {k: [d for d in v if d["symbol"] == args.symbol.upper()] for k, v in deals.items()}
        emit(deals)
    else:
        emit(nse.insider(args.symbol, args.days))


def cmd_ban(args, cfg):
    emit({"ban_list": get_nse(cfg).ban_list()})


def cmd_charges(args, cfg):
    emit({"segment": args.segment, "exchange": args.exchange, "rates_effective": chg.RATES["effective"],
          **chg.compute(args.segment, args.buy, args.sell, args.exchange, args.orders, cfg["brokerage"],
                        cfg.get("charges_override"))})


# --- parser --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="idt", description="Indian Day Trader tools. Nothing here places orders.")
    ap.add_argument("--now", help="pretend it is this IST time, 'YYYY-MM-DD HH:MM' (backtests, demos)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    p = sub.add_parser("index", help="index dashboard, or one index with levels + chart")
    p.add_argument("symbol", nargs="?")
    p.add_argument("--interval", type=int, default=5, choices=[1, 5, 15, 25, 60])
    p.add_argument("--days", type=int, default=2, help="sessions to draw")
    p.add_argument("--html", action="store_true", help="also write an interactive HTML chart")
    p.add_argument("--future", action="store_true", help="chart the near-month future (has volume/VWAP)")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("expiries")
    p.add_argument("underlying")
    p.set_defaults(fn=cmd_expiries)

    p = sub.add_parser("chain", help="option chain analytics")
    p.add_argument("underlying")
    p.add_argument("--expiry", help="YYYY-MM-DD | near | next | monthly")
    p.add_argument("--strikes", type=int, default=10, help="strikes each side of ATM in the table")
    p.add_argument("--chart", action="store_true")
    p.set_defaults(fn=cmd_chain)

    p = sub.add_parser("strategy", help="build and analyse an options strategy")
    p.add_argument("name", choices=list(strat_mod.STRATEGIES) + ["custom", "list"])
    p.add_argument("underlying", nargs="?", default="NIFTY")
    p.add_argument("--expiry")
    p.add_argument("--lots", type=int, default=1)
    p.add_argument("--offset", type=int, default=0, help="strike steps from ATM")
    p.add_argument("--width", type=int, default=2, help="spread width / wing distance in strike steps")
    p.add_argument("--delta", type=float, help="pick short strikes by |delta| (strangle/condor)")
    p.add_argument("--leg", action="append", default=[], help="custom leg, e.g. +1x26000CE or -2x25800PE")
    p.add_argument("--chart", action="store_true")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_strategy)

    p = sub.add_parser("scan", help="chart scanner")
    p.add_argument("setup", choices=["orb", "flag", "bounce"])
    p.add_argument("--universe", default="watchlist", help="fno | watchlist | indices | comma list")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--max-symbols", type=int, default=250)
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("entry", help="entry timer")
    p.add_argument("action", choices=["check", "watch"])
    p.add_argument("symbol")
    p.add_argument("--setup", default="orb", choices=["orb", "pdh", "level"])
    p.add_argument("--above", type=float)
    p.add_argument("--below", type=float)
    p.add_argument("--poll", type=int, default=60)
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_entry)

    p = sub.add_parser("exit", help="exit planner")
    p.add_argument("action", choices=["plan"])
    p.add_argument("--kind", choices=["equity", "future", "option", "strategy"])
    p.add_argument("--stop", help="or-mid | or-low | atr:K | pct:N | price:X | premium-pct:N | maxloss-pct:N | credit-x:N | pnl:-X")
    p.add_argument("--target", help="NR | pct:N | price:X | maxprofit-pct:N | credit-pct:N | pnl:X")
    p.add_argument("--option", default="auto", choices=["auto", "CE", "PE"])
    p.add_argument("--strike-offset", type=int, default=0, help="strike steps OTM (negative = ITM)")
    p.add_argument("--expiry")
    p.add_argument("--symbol")
    p.add_argument("--side", choices=["long", "short"], default="long")
    p.add_argument("--entry", type=float, help="manual entry level instead of setup.json")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_exit)

    p = sub.add_parser("timemachine", help="simulate the plan")
    p.add_argument("action", choices=["run"])
    p.add_argument("--paths", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--days", type=int, default=59, help="prior sessions to sample")
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_timemachine)

    p = sub.add_parser("size", help="budget manager")
    p.add_argument("--max-loss", type=float)
    p.add_argument("--write", action="store_true")
    p.set_defaults(fn=cmd_size)

    p = sub.add_parser("risk", help="risk manager")
    p.add_argument("action", choices=["check"])
    p.set_defaults(fn=cmd_risk)

    p = sub.add_parser("ticket", help="broker-neutral order ticket")
    p.add_argument("action", choices=["show", "confirm"])
    p.add_argument("hash", nargs="?")
    p.set_defaults(fn=cmd_ticket)

    p = sub.add_parser("journal", help="trade journal")
    p.add_argument("action", choices=["show", "close"])
    p.add_argument("--pnl", type=float, default=0.0)
    p.add_argument("--symbol")
    p.add_argument("--note")
    p.add_argument("--tail", type=int, default=20)
    p.set_defaults(fn=cmd_journal)

    p = sub.add_parser("alerts", help="price / stop / target / square-off alerts")
    p.add_argument("action", choices=["add", "check", "watch", "list", "clear"])
    p.add_argument("--from-plan", action="store_true")
    p.add_argument("--symbol")
    p.add_argument("--above", type=float)
    p.add_argument("--below", type=float)
    p.add_argument("--label")
    p.add_argument("--poll", type=int, default=15)
    p.set_defaults(fn=cmd_alerts)

    p = sub.add_parser("news", help="NSE corporate announcements")
    p.add_argument("--symbols")
    p.add_argument("--hours", type=int, default=12)
    p.set_defaults(fn=cmd_news)

    p = sub.add_parser("results", help="quarterly results")
    p.add_argument("symbol")
    p.add_argument("--quarters", type=int, default=8)
    p.set_defaults(fn=cmd_results)

    p = sub.add_parser("insider", help="bulk/block deals and insider (PIT) disclosures")
    p.add_argument("action", choices=["deals", "pit"])
    p.add_argument("--symbol")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(fn=cmd_insider)

    sub.add_parser("ban", help="today's NSE F&O ban list").set_defaults(fn=cmd_ban)

    p = sub.add_parser("charges", help="transaction charges for a round trip")
    p.add_argument("--segment", required=True, choices=list(chg.SEGMENTS))
    p.add_argument("--buy", type=float, required=True, help="buy turnover in Rs (premium x qty for options)")
    p.add_argument("--sell", type=float, required=True)
    p.add_argument("--exchange", default="NSE", choices=["NSE", "BSE"])
    p.add_argument("--orders", type=int, default=2)
    p.set_defaults(fn=cmd_charges)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(args, load_config())
    except (DataError, ValueError, ticket_mod.TicketError) as exc:
        emit({"error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
