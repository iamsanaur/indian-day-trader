"""`idt` command line. Every command prints JSON so Claude (and humans) can read it.

Command logic lives in service.py and is shared with the API server (`idt serve`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from . import service as svc
from . import strategy as strat_mod
from . import ticket as ticket_mod
from .config import load_config
from .data import DataError, get_data
from .market import IST, now_ist


def emit(obj) -> None:
    print(json.dumps(svc.jsonable(obj), indent=2, default=str))


def get_now(args) -> datetime:
    if getattr(args, "now", None):
        return datetime.fromisoformat(args.now).replace(tzinfo=IST)
    return now_ist()


# --- commands ------------------------------------------------------------------------

def cmd_init(args, cfg):
    emit(svc.init())


def cmd_status(args, cfg):
    emit(svc.status(cfg, get_now(args)))


def cmd_index(args, cfg):
    data, now = get_data(cfg), get_now(args)
    if args.symbol:
        emit(svc.index_view(data, cfg, args.symbol, now, args.interval, args.days, True, args.html, args.future))
    else:
        emit(svc.index_board(data, cfg, now))


def cmd_expiries(args, cfg):
    emit(svc.expiries(get_data(cfg), args.underlying))


def cmd_chain(args, cfg):
    emit(svc.chain(get_data(cfg), cfg, args.underlying, get_now(args), args.expiry, args.strikes, args.chart))


def cmd_strategy(args, cfg):
    if args.name == "list":
        emit(strat_mod.STRATEGIES)
        return
    emit(svc.strategy(get_data(cfg), cfg, args.name, args.underlying, get_now(args), args.expiry, args.lots,
                      args.offset, args.width, args.delta, args.leg, args.chart, args.write))


def cmd_scan(args, cfg):
    emit(svc.scan(get_data(cfg), cfg, args.setup, get_now(args), args.universe, args.limit, args.max_symbols,
                  args.verbose))


def cmd_entry(args, cfg):
    data = get_data(cfg)
    while True:
        res = svc.entry_check(data, cfg, args.symbol, get_now(args), args.setup, args.above, args.below, args.write)
        if args.action == "check" or res["state"] != "waiting" or getattr(args, "now", None):
            emit(res)
            return
        print(json.dumps({"state": res["state"], "as_of": res["as_of"], "last": res.get("last")}), flush=True)
        time.sleep(args.poll)


def cmd_exit(args, cfg):
    emit(svc.exit_plan(get_data(cfg), cfg, get_now(args), args.kind, args.stop, args.target, args.option,
                       args.strike_offset, args.expiry, args.symbol, args.side, args.entry, args.write))


def cmd_timemachine(args, cfg):
    emit(svc.timemachine(get_data(cfg), cfg, get_now(args), args.paths, args.seed, args.days, args.write))


def cmd_size(args, cfg):
    emit(svc.size(get_data(cfg), cfg, get_now(args), args.max_loss, args.write))


def cmd_risk(args, cfg):
    emit(svc.risk(get_data(cfg), cfg, get_now(args)))


def cmd_ticket(args, cfg):
    if args.action == "show":
        emit(svc.ticket_show(get_now(args)))
    else:
        emit(svc.ticket_confirm(cfg, get_now(args), args.hash or ""))


def cmd_journal(args, cfg):
    pnl = args.pnl if args.action == "close" else None
    emit(svc.journal(get_now(args), pnl, args.symbol, args.note, args.tail))


def cmd_alerts(args, cfg):
    if args.action == "add":
        emit(svc.alerts_add(args.from_plan, args.symbol, args.above, args.below, args.label))
    elif args.action == "clear":
        emit(svc.alerts_clear())
    elif args.action == "list":
        emit(svc.alerts_list())
    else:
        data = get_data(cfg)
        while True:
            res = svc.alerts_check(data, get_now(args))
            if args.action == "check" or getattr(args, "now", None):
                emit(res)
                return
            for f in res["fired"]:
                print(json.dumps({"ALERT": f["label"], "observed": f.get("observed"), "at": f["fired_at"]}), flush=True)
            if not res["pending"]:
                return
            time.sleep(args.poll)


def cmd_news(args, cfg):
    emit(svc.news(cfg, get_now(args), args.symbols, args.hours))


def cmd_results(args, cfg):
    emit(svc.results(cfg, args.symbol, args.quarters))


def cmd_insider(args, cfg):
    emit(svc.insider(cfg, args.action, args.symbol, args.days))


def cmd_ban(args, cfg):
    emit(svc.ban(cfg))


def cmd_charges(args, cfg):
    emit(svc.charges(cfg, args.segment, args.buy, args.sell, args.exchange, args.orders))


def cmd_serve(args, cfg):
    from .server.run import serve
    serve(args.host, args.port, args.demo, args.now)


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
    p.add_argument("--segment", required=True, choices=list(svc.chg.SEGMENTS))
    p.add_argument("--buy", type=float, required=True, help="buy turnover in Rs (premium x qty for options)")
    p.add_argument("--sell", type=float, required=True)
    p.add_argument("--exchange", default="NSE", choices=["NSE", "BSE"])
    p.add_argument("--orders", type=int, default=2)
    p.set_defaults(fn=cmd_charges)

    p = sub.add_parser("serve", help="run the API server for the web/iOS/Android apps")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8742)
    p.add_argument("--demo", action="store_true", help="offline fixtures, clock pinned to 2026-10-29 09:45 IST")
    p.set_defaults(fn=cmd_serve)
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
