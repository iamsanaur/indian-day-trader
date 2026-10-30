"""FastAPI app. Thin HTTP layer over idt.service with bearer-token auth and an SSE alert stream."""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import __version__
from .. import service as svc
from ..config import load_config, load_state, save_state
from ..data import DataError, get_data
from ..market import IST, now_ist
from ..strategy import STRATEGIES
from ..ticket import TicketError

WEB_DIST = Path(__file__).parent / "web_dist"


def server_token() -> str:
    state = load_state("server.json") or {}
    if not state.get("token"):
        state["token"] = secrets.token_urlsafe(24)
        save_state("server.json", state)
    return state["token"]


# --- request bodies ------------------------------------------------------------------

class StrategyBody(BaseModel):
    name: str
    underlying: str = "NIFTY"
    expiry: str | None = None
    lots: int = 1
    offset: int = 0
    width: int = 2
    delta: float | None = None
    legs: list[str] = []
    write: bool = False


class EntryBody(BaseModel):
    setup: str = "orb"
    above: float | None = None
    below: float | None = None
    write: bool = True


class PlanBody(BaseModel):
    kind: str | None = None
    stop: str | None = None
    target: str | None = None
    option: str = "auto"
    strike_offset: int = 0
    expiry: str | None = None
    symbol: str | None = None
    side: str = "long"
    entry: float | None = None
    write: bool = True


class TimeMachineBody(BaseModel):
    paths: int = 10000
    seed: int = 42
    days: int = 59


class SizeBody(BaseModel):
    max_loss: float | None = None
    write: bool = True


class ConfirmBody(BaseModel):
    hash: str
    typed: str


class CloseBody(BaseModel):
    pnl: float
    symbol: str | None = None
    note: str | None = None


class TotpBody(BaseModel):
    totp: str


class AlertBody(BaseModel):
    from_plan: bool = False
    symbol: str | None = None
    above: float | None = None
    below: float | None = None
    label: str | None = None


def create_app(clock: Callable[[], datetime] | None = None, demo: bool = False) -> FastAPI:
    app = FastAPI(title="Indian Day Trader API", version=__version__,
                  description="Self-hosted API for the Indian Day Trader apps. Never places orders.")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    clock = clock or now_ist
    cache: dict = {}

    def cfg() -> dict:
        return load_config()

    def data():
        c = cfg()
        key = (c["data_provider"], c.get("fixtures_dir"))
        if cache.get("key") != key:
            cache.update(key=key, data=get_data(c))
        return cache["data"]

    def auth(authorization: str | None = Header(None), token: str | None = Query(None)) -> None:
        given = (authorization or "").removeprefix("Bearer ").strip() or (token or "")
        if not secrets.compare_digest(given, server_token()):
            raise HTTPException(401, "invalid or missing token")

    @app.exception_handler(DataError)
    @app.exception_handler(ValueError)
    @app.exception_handler(TicketError)
    async def user_error(_: Request, exc: Exception):
        return JSONResponse({"error": str(exc)}, status_code=400)

    def ok(obj):
        return JSONResponse(svc.jsonable(obj))

    api = "/api"
    guard = [Depends(auth)]

    @app.get(f"{api}/health")
    def health():
        return {"ok": True, "version": __version__, "demo": demo, "now": clock().isoformat()}

    @app.get(f"{api}/status", dependencies=guard)
    def status():
        return ok(dict(svc.status(cfg(), clock()), demo=demo))

    @app.get(f"{api}/config", dependencies=guard)
    def get_config():
        return ok(svc.get_config(cfg()))

    @app.patch(f"{api}/config", dependencies=guard)
    def patch_config(changes: dict):
        return ok(svc.update_config(changes))

    @app.get(f"{api}/dhan", dependencies=guard)
    def dhan_status():
        return ok(svc.dhan_status(clock()))

    @app.post(f"{api}/dhan/login", dependencies=guard)
    def dhan_login(body: TotpBody):
        return ok(svc.dhan_login(body.totp, clock()))

    @app.delete(f"{api}/dhan", dependencies=guard)
    def dhan_logout():
        return ok(svc.dhan_logout(clock()))

    @app.get(f"{api}/indices", dependencies=guard)
    def indices():
        return ok(svc.index_board(data(), cfg(), clock()))

    @app.get(f"{api}/index/{{symbol}}", dependencies=guard)
    def index(symbol: str, interval: int = 5, days: int = 2, future: bool = False):
        return ok(svc.index_view(data(), cfg(), symbol, clock(), interval, days, future=future, candles=True))

    @app.get(f"{api}/expiries/{{underlying}}", dependencies=guard)
    def expiries(underlying: str):
        return ok(svc.expiries(data(), underlying))

    @app.get(f"{api}/chain/{{underlying}}", dependencies=guard)
    def chain(underlying: str, expiry: str | None = None, strikes: int = 10):
        return ok(svc.chain(data(), cfg(), underlying, clock(), expiry, strikes))

    @app.get(f"{api}/strategies", dependencies=guard)
    def strategies():
        return STRATEGIES

    @app.post(f"{api}/strategy", dependencies=guard)
    def strategy(body: StrategyBody):
        return ok(svc.strategy(data(), cfg(), body.name, body.underlying, clock(), body.expiry, body.lots, body.offset,
                               body.width, body.delta, body.legs, write=body.write, curve=True))

    @app.get(f"{api}/scan/{{setup}}", dependencies=guard)
    def scan(setup: str, universe: str = "watchlist", limit: int = 20):
        return ok(svc.scan(data(), cfg(), setup, clock(), universe, limit))

    @app.post(f"{api}/entry/{{symbol}}", dependencies=guard)
    def entry(symbol: str, body: EntryBody):
        return ok(svc.entry_check(data(), cfg(), symbol, clock(), body.setup, body.above, body.below, body.write))

    @app.get(f"{api}/plan", dependencies=guard)
    def get_plan():
        return ok(svc.get_plan())

    @app.post(f"{api}/plan", dependencies=guard)
    def plan(body: PlanBody):
        return ok(svc.exit_plan(data(), cfg(), clock(), body.kind, body.stop, body.target, body.option,
                                body.strike_offset, body.expiry, body.symbol, body.side, body.entry, body.write))

    @app.post(f"{api}/timemachine", dependencies=guard)
    def timemachine(body: TimeMachineBody):
        return ok(svc.timemachine(data(), cfg(), clock(), min(body.paths, 50000), body.seed, body.days))

    @app.post(f"{api}/size", dependencies=guard)
    def size(body: SizeBody):
        return ok(svc.size(data(), cfg(), clock(), body.max_loss, body.write))

    @app.get(f"{api}/orders", dependencies=guard)
    def orders():
        return ok({"orders": load_state("orders.json"), "risk": load_state("risk.json")})

    @app.post(f"{api}/risk", dependencies=guard)
    def risk():
        return ok(svc.risk(data(), cfg(), clock()))

    @app.get(f"{api}/ticket", dependencies=guard)
    def ticket():
        return ok(svc.ticket_show(clock()))

    @app.post(f"{api}/ticket/confirm", dependencies=guard)
    def confirm(body: ConfirmBody):
        if body.typed.strip().lower() != "yes":
            raise HTTPException(400, 'type "yes" to confirm this order')
        return ok(svc.ticket_confirm(cfg(), clock(), body.hash))

    @app.get(f"{api}/journal", dependencies=guard)
    def journal(tail: int = 50):
        return ok(svc.journal(clock(), tail=tail))

    @app.post(f"{api}/journal/close", dependencies=guard)
    def journal_close(body: CloseBody):
        return ok(svc.journal(clock(), body.pnl, body.symbol, body.note))

    @app.get(f"{api}/alerts", dependencies=guard)
    def alerts():
        return ok(svc.alerts_list())

    @app.post(f"{api}/alerts", dependencies=guard)
    def add_alert(body: AlertBody):
        return ok(svc.alerts_add(body.from_plan, body.symbol, body.above, body.below, body.label))

    @app.delete(f"{api}/alerts", dependencies=guard)
    def clear_alerts():
        return ok(svc.alerts_clear())

    @app.post(f"{api}/alerts/check", dependencies=guard)
    def check_alerts():
        return ok(svc.alerts_check(data(), clock()))

    @app.get(f"{api}/events", dependencies=guard)
    async def events(request: Request, interval: float = 15.0):
        """Server-sent events: `alert` when an alert fires, `tick` heartbeat with pending count."""
        async def stream():
            while not await request.is_disconnected():
                try:
                    res = await asyncio.to_thread(svc.alerts_check, data(), clock())
                    for f in res["fired"]:
                        yield f"event: alert\ndata: {json.dumps(svc.jsonable(f))}\n\n"
                    yield f"event: tick\ndata: {json.dumps({'as_of': res['as_of'], 'pending': len(res['pending'])})}\n\n"
                except (DataError, ValueError) as exc:
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                await asyncio.sleep(max(interval, 2.0))
        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get(f"{api}/news", dependencies=guard)
    def news(symbols: str | None = None, hours: int = 24):
        return ok(svc.news(cfg(), clock(), symbols, hours))

    @app.get(f"{api}/ban", dependencies=guard)
    def ban():
        return ok(svc.ban(cfg()))

    @app.get(f"{api}/results/{{symbol}}", dependencies=guard)
    def results(symbol: str, quarters: int = 8):
        return ok(svc.results(cfg(), symbol, quarters))

    @app.get(f"{api}/insider/{{kind}}", dependencies=guard)
    def insider(kind: str, symbol: str | None = None, days: int = 30):
        return ok(svc.insider(cfg(), kind, symbol, days))

    @app.get(f"{api}/charges", dependencies=guard)
    def charges(segment: str, buy: float, sell: float, exchange: str = "NSE"):
        return ok(svc.charges(cfg(), segment, buy, sell, exchange))

    if WEB_DIST.exists():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def web(path: str):
            target = WEB_DIST / path
            return FileResponse(target if path and target.is_file() else WEB_DIST / "index.html")

    return app


def fixed_clock(text: str) -> Callable[[], datetime]:
    moment = datetime.fromisoformat(text).replace(tzinfo=IST)
    return lambda: moment
