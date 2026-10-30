"""Public NSE endpoints: corporate announcements, F&O ban list, bulk/block deals, insider (PIT)
disclosures, quarterly results and the holiday calendar.

These are unofficial JSON endpoints behind the nseindia.com website. They need a cookie handshake
with a browser-like User-Agent and may rate limit or change shape; every caller degrades
independently of the trading tools. Responses are cached under idt/cache/nse.
"""

from __future__ import annotations

import csv
import io
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from .base import DataError

HOME = "https://www.nseindia.com"
BAN_CSV = "https://nsearchives.nseindia.com/content/fo/fo_secban.csv"


def _ddmmyyyy(d: date) -> str:
    return d.strftime("%d-%m-%Y")


class NSE:
    def __init__(self, cache_dir: Path, user_agent: str, session: requests.Session | None = None,
                 fixture_dir: Path | None = None):
        self.cache = cache_dir / "nse"
        self.ua = user_agent
        self.http = session or requests.Session()
        self.fixture_dir = fixture_dir
        self._primed = False

    def _prime(self) -> None:
        if self._primed:
            return
        self.http.headers.update({"User-Agent": self.ua, "Accept": "application/json, text/plain, */*",
                                  "Accept-Language": "en-US,en;q=0.9", "Referer": HOME + "/"})
        try:
            self.http.get(HOME, timeout=15)
        except requests.RequestException as exc:
            raise DataError(f"NSE handshake failed: {exc}") from exc
        self._primed = True

    def _get(self, name: str, url: str, params: dict | None = None, ttl: int = 900, raw: bool = False):
        if self.fixture_dir:
            path = self.fixture_dir / f"{name}.{'txt' if raw else 'json'}"
            if not path.exists():
                raise DataError(f"fixture missing: {path}")
            return path.read_text() if raw else json.loads(path.read_text())
        key = name + ("_" + "_".join(f"{k}-{v}" for k, v in sorted((params or {}).items())) if params else "")
        cached = self.cache / f"{key.replace('/', '_')}.{'txt' if raw else 'json'}"
        if cached.exists() and time.time() - cached.stat().st_mtime < ttl:
            return cached.read_text() if raw else json.loads(cached.read_text())
        self._prime()
        try:
            resp = self.http.get(url, params=params, timeout=20)
        except requests.RequestException as exc:
            raise DataError(f"NSE request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataError(f"NSE {name}: HTTP {resp.status_code} (endpoint may be rate limited or changed)")
        self.cache.mkdir(parents=True, exist_ok=True)
        cached.write_text(resp.text)
        return resp.text if raw else resp.json()

    # --- endpoints ---------------------------------------------------------------
    def announcements(self, symbol: str | None = None, days: int = 1) -> list[dict]:
        today = date.today()
        params = {"index": "equities", "from_date": _ddmmyyyy(today - timedelta(days=days)), "to_date": _ddmmyyyy(today)}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("announcements", HOME + "/api/corporate-announcements", params)
        rows = data if isinstance(data, list) else data.get("data", [])
        return [{"symbol": r.get("symbol"), "company": r.get("sm_name"), "subject": r.get("desc"),
                 "detail": r.get("attchmntText"), "time": r.get("an_dt") or r.get("sort_date"),
                 "attachment": r.get("attchmntFile")} for r in rows]

    def ban_list(self) -> list[str]:
        text = self._get("fo_secban", BAN_CSV, ttl=3600, raw=True)
        out = []
        for row in csv.reader(io.StringIO(text)):
            if len(row) >= 2 and row[0].strip().isdigit():
                out.append(row[1].strip().upper())
        return out

    def large_deals(self) -> dict[str, list[dict]]:
        data = self._get("large_deals", HOME + "/api/snapshot-capital-market-largedeal")
        fields = ("date", "symbol", "name", "clientName", "buySell", "qty", "watp", "remarks")
        return {kind: [{f: r.get(f) for f in fields} for r in data.get(f"{kind.upper()}_DEALS_DATA", []) or []]
                for kind in ("bulk", "block")}

    def insider(self, symbol: str | None = None, days: int = 30) -> list[dict]:
        today = date.today()
        params = {"index": "equities", "from_date": _ddmmyyyy(today - timedelta(days=days)), "to_date": _ddmmyyyy(today)}
        if symbol:
            params["symbol"] = symbol.upper()
        data = self._get("insider", HOME + "/api/corporates-pit", params, ttl=3600)
        rows = data.get("data", []) if isinstance(data, dict) else data
        return [{"symbol": r.get("symbol"), "person": r.get("acqName"), "category": r.get("personCategory"),
                 "type": r.get("tdpTransactionType"), "security": r.get("secType"), "quantity": r.get("secAcq"),
                 "value": r.get("secVal"), "mode": r.get("acqMode"), "from": r.get("acqfromDt"),
                 "to": r.get("acqtoDt"), "intimated": r.get("intimDt")} for r in rows]

    def results(self, symbol: str) -> list[dict]:
        data = self._get("results", HOME + "/api/results-comparision", {"symbol": symbol.upper()}, ttl=6 * 3600)
        rows = data.get("resCmpData", []) if isinstance(data, dict) else data
        return [_normalise_result(r) for r in rows]

    def holidays(self) -> list[str]:
        data = self._get("holidays", HOME + "/api/holiday-master", {"type": "trading"}, ttl=7 * 86400)
        out = set()
        for seg in ("CM", "FO"):
            for r in data.get(seg, []):
                try:
                    out.add(datetime.strptime(r["tradingDate"], "%d-%b-%Y").date().isoformat())
                except (KeyError, ValueError):
                    continue
        return sorted(out)


def _pick(row: dict, *needles: str):
    for key, value in row.items():
        k = key.lower()
        if all(n in k for n in needles):
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return None


def _normalise_result(r: dict) -> dict:
    """Result field names vary across filings; match them by keyword."""
    return {
        "period_end": r.get("re_to_dt") or r.get("toDate"),
        "revenue": _pick(r, "net_sale") or _pick(r, "revenue") or _pick(r, "total_inc"),
        "net_profit": _pick(r, "net_profit") or _pick(r, "pro_loss_aft_tax"),
        "eps": _pick(r, "basic_eps") or _pick(r, "eps"),
        "consolidated": r.get("re_res_type") or r.get("consolidated"),
    }
