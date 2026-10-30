"""Dhan v2 REST adapter (market data, funds, margin). Read-only: no order endpoints are used."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta

import pandas as pd
import requests

from ..market import index_info, now_ist
from .base import DataError, Instrument, OptionChain, Quote, parse_candles, parse_chain
from .instruments import Instruments

BASE = "https://api.dhan.co/v2"

# Minimum spacing between calls per endpoint family (seconds), per Dhan docs.
_SPACING = {"optionchain": 3.0, "marketfeed": 1.0, "charts": 0.25, "other": 0.25}

_SETUP_HELP = ("Dhan data access failed: {msg}\n"
               "Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN (web.dhan.co > My Profile > Access DhanHQ APIs). "
               "Market data APIs need an active Dhan data subscription. Tokens expire daily.")
_AUTH_CODES = {"806", "807", "808", "809", "810", "DH-901", "DH-902"}
_RETRY_CODES = {"805", "DH-904"}


class DhanData:
    def __init__(self, instruments: Instruments, client_id: str | None = None, token: str | None = None,
                 session: requests.Session | None = None, sleep=time.sleep):
        self.client_id = client_id or os.environ.get("DHAN_CLIENT_ID", "")
        self.token = token or os.environ.get("DHAN_ACCESS_TOKEN", "")
        if not (self.client_id and self.token):
            raise DataError(_SETUP_HELP.format(msg="DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN not set"))
        self.instruments = instruments
        self.http = session or requests.Session()
        self.sleep = sleep
        self._last: dict[str, float] = {}

    # --- transport -------------------------------------------------------------
    def _headers(self) -> dict:
        return {"access-token": self.token, "client-id": self.client_id,
                "Accept": "application/json", "Content-Type": "application/json"}

    def _throttle(self, path: str) -> None:
        family = next((k for k in _SPACING if path.startswith("/" + k)), "other")
        wait = _SPACING[family] - (time.monotonic() - self._last.get(family, 0.0))
        if wait > 0:
            self.sleep(wait)
        self._last[family] = time.monotonic()

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        for attempt in range(4):
            self._throttle(path)
            resp = self.http.request(method, BASE + path, json=body, headers=self._headers(), timeout=30)
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            code = _error_code(payload)
            if resp.status_code == 429 or code in _RETRY_CODES:
                self.sleep(2 ** attempt)
                continue
            if code in _AUTH_CODES or resp.status_code in (401, 403):
                raise DataError(_SETUP_HELP.format(msg=_error_message(payload) or f"HTTP {resp.status_code}"))
            if resp.status_code >= 400 or code:
                raise DataError(f"Dhan {path} failed: {_error_message(payload) or resp.text[:200]}")
            return payload
        raise DataError(f"Dhan {path}: rate limited after retries")

    # --- MarketData ----------------------------------------------------------
    def instrument(self, symbol: str) -> Instrument:
        return self.instruments.resolve(symbol)

    def candles(self, symbol: str, interval: int | str, start: date, end: date) -> pd.DataFrame:
        inst = self.instrument(symbol)
        base = {"securityId": inst.security_id, "exchangeSegment": inst.exchange_segment,
                "instrument": inst.instrument, "oi": inst.is_option or inst.is_future}
        if str(interval).upper() == "D":
            body = dict(base, expiryCode=0, fromDate=start.isoformat(), toDate=(end + timedelta(days=1)).isoformat())
            return parse_candles(self._call("POST", "/charts/historical", body))
        frames, cursor = [], start
        while cursor <= end:  # intraday history is limited to 90 days per call
            chunk_end = min(cursor + timedelta(days=89), end)
            body = dict(base, interval=str(int(interval)), fromDate=f"{cursor} 09:00:00", toDate=f"{chunk_end} 15:30:00")
            frames.append(parse_candles(self._call("POST", "/charts/intraday", body)))
            cursor = chunk_end + timedelta(days=1)
        frames = [f for f in frames if not f.empty]
        return pd.concat(frames).sort_index() if frames else parse_candles({})

    def quote(self, symbols: list[str]) -> dict[str, Quote]:
        insts = {s: self.instrument(s) for s in symbols}
        body: dict[str, list[int]] = {}
        for inst in insts.values():
            body.setdefault(inst.exchange_segment, []).append(int(inst.security_id))
        data = self._call("POST", "/marketfeed/ohlc", body).get("data", {})
        stamp = now_ist()
        out = {}
        for sym, inst in insts.items():
            raw = data.get(inst.exchange_segment, {}).get(inst.security_id)
            if raw:
                o = raw.get("ohlc", {})
                out[sym] = Quote(sym, float(raw["last_price"]), float(o.get("open", 0)), float(o.get("high", 0)),
                                 float(o.get("low", 0)), float(o.get("close", 0)), stamp)
        return out

    def _underlying_body(self, underlying: str) -> dict:
        info = index_info(underlying, self.instruments.index_overrides)
        if info:
            return {"UnderlyingScrip": info.security_id, "UnderlyingSeg": "IDX_I"}
        inst = self.instrument(underlying)
        return {"UnderlyingScrip": int(inst.security_id), "UnderlyingSeg": inst.exchange_segment}

    def expiries(self, underlying: str) -> list[date]:
        data = self._call("POST", "/optionchain/expirylist", self._underlying_body(underlying)).get("data", [])
        return sorted(date.fromisoformat(d) for d in data)

    def option_chain(self, underlying: str, expiry: date) -> OptionChain:
        body = dict(self._underlying_body(underlying), Expiry=expiry.isoformat())
        name = index_info(underlying).name if index_info(underlying) else underlying.upper()
        return parse_chain(self._call("POST", "/optionchain", body), name, expiry, now_ist())

    def funds(self) -> dict:
        raw = self._call("GET", "/fundlimit")
        # Dhan spells the field "availabelBalance".
        return {"available": float(raw.get("availabelBalance", raw.get("availableBalance", 0))),
                "utilized": float(raw.get("utilizedAmount", 0)), "raw": raw}

    def margin(self, legs: list[dict]) -> dict:
        """legs: [{symbol, side BUY|SELL, quantity, price, product}] -> total margin incl. hedge benefit."""
        scripts = []
        for leg in legs:
            inst = self.instrument(leg["symbol"])
            scripts.append({"exchangeSegment": inst.exchange_segment, "transactionType": leg["side"],
                            "quantity": int(leg["quantity"]), "productType": _dhan_product(leg.get("product", "MIS")),
                            "securityId": inst.security_id, "price": float(leg.get("price", 0))})
        try:
            raw = self._call("POST", "/margincalculator/multi",
                             {"includePosition": False, "includeOrders": False, "scripts": scripts})
            return {"total": float(raw.get("total_margin") or 0), "span": float(raw.get("span_margin") or 0),
                    "exposure": float(raw.get("exposure_margin") or 0), "source": "dhan-multi"}
        except DataError:
            total = 0.0
            for s in scripts:  # no hedge benefit when summing single-order margins
                raw = self._call("POST", "/margincalculator", dict(s, dhanClientId=self.client_id))
                total += float(raw.get("totalMargin") or 0)
            return {"total": total, "source": "dhan-single-sum"}


def _dhan_product(product: str) -> str:
    return {"MIS": "INTRADAY", "NRML": "MARGIN", "CNC": "CNC"}.get(product.upper(), product.upper())


def _error_code(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    if payload.get("errorCode"):
        return str(payload["errorCode"])
    if payload.get("status") == "failure" and isinstance(payload.get("data"), dict):
        return next(iter(payload["data"]), "")
    return ""


def _error_message(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    if payload.get("errorMessage"):
        return str(payload["errorMessage"])
    if payload.get("status") == "failure" and isinstance(payload.get("data"), dict):
        return "; ".join(f"{k}: {v}" for k, v in payload["data"].items())
    return ""
