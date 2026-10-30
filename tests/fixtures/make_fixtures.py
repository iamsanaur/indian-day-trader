"""Generate deterministic offline fixtures in Dhan payload format.

Run: .venv/bin/python tests/fixtures/make_fixtures.py
Market story (session 2026-10-29, IST):
  NIFTY opens 25,940, 15-minute opening range 25,905-25,985, the 09:35 bar closes 25,995 (ORB long),
  then trends to ~26,060. RELIANCE triggers an ORB long, HDFCBANK an oversold bounce, TCS a bull flag.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent / "data"
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from idt import fno  # noqa: E402
from idt.market import IST  # noqa: E402

LAST = date(2026, 10, 29)
NOW = datetime(2026, 10, 29, 9, 45, tzinfo=IST)
WEEKLY = date(2026, 11, 3)
MONTHLY = date(2026, 11, 24)
SLOTS = [(9 * 60 + 15) + 5 * i for i in range(75)]  # 09:15 .. 15:25


def trading_days(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def epoch(d: date, minute: int) -> int:
    return int(datetime(d.year, d.month, d.day, minute // 60, minute % 60, tzinfo=IST).timestamp())


def bars_for_day(rng, d: date, open_px: float, drift: float, vol: float, base_volume: int, script=None):
    rows, px = [], open_px
    for i, m in enumerate(SLOTS):
        if script and i < len(script):
            o, h, l, c = script[i]
        else:
            o = px
            c = o * math.exp(drift / 75 + vol / math.sqrt(75) * rng.standard_normal())
            h = max(o, c) * (1 + abs(rng.normal(0, vol / 40)))
            l = min(o, c) * (1 - abs(rng.normal(0, vol / 40)))
        u_shape = 1.8 if i < 6 or i > 68 else 1.0
        v = int(base_volume * u_shape * rng.uniform(0.6, 1.4)) if base_volume else 0
        rows.append((epoch(d, m), round(o, 2), round(h, 2), round(l, 2), round(c, 2), v))
        px = c
    return rows, px


def series(rng, days: list[date], start: float, vol: float, base_volume: int, last_script=None, drift=0.0,
           last_open=None):
    rows, px = [], start
    for d in days:
        if d == days[-1] and last_open:
            px = last_open
        day_rows, px = bars_for_day(rng, d, px * (1 + rng.normal(0, vol / 6)) if d != days[-1] else px, drift, vol,
                                    base_volume, last_script if d == days[-1] else None)
        rows += day_rows
    return rows


def rescale(rows, last_close: float):
    """Scale a price history so its final close equals last_close (keeps the shape, removes gaps)."""
    f = last_close / rows[-1][4]
    return [(t, round(o * f, 2), round(h * f, 2), round(l * f, 2), round(c * f, 2), v) for t, o, h, l, c, v in rows]


def payload(rows, oi=False):
    return {"timestamp": [r[0] for r in rows], "open": [r[1] for r in rows], "high": [r[2] for r in rows],
            "low": [r[3] for r in rows], "close": [r[4] for r in rows], "volume": [r[5] for r in rows],
            "open_interest": [0] * len(rows)}


def daily_payload(rows, extra_days: list[date], rng, start_px: float, vol: float, base_volume: int, shape=None):
    """Synthetic older daily history + daily bars aggregated from intraday rows."""
    out, px = [], start_px
    for i, d in enumerate(extra_days):
        r = shape(i, len(extra_days)) if shape else rng.normal(0, vol)
        o = px
        c = o * math.exp(r)
        h, l = max(o, c) * (1 + abs(rng.normal(0, vol / 3))), min(o, c) * (1 - abs(rng.normal(0, vol / 3)))
        out.append((epoch(d, 555), round(o, 2), round(h, 2), round(l, 2), round(c, 2), int(base_volume * 75 * (0.6 + 40 * abs(r)))))
        px = c
    if out and rows:
        out = rescale(out, rows[0][1])
    by_day: dict[date, list] = {}
    for r in rows:
        by_day.setdefault(datetime.fromtimestamp(r[0], IST).date(), []).append(r)
    for d, rs in sorted(by_day.items()):
        out.append((epoch(d, 555), rs[0][1], max(x[2] for x in rs), min(x[3] for x in rs), rs[-1][4], sum(x[5] for x in rs)))
    return payload(out)


def scale_script(base: float, steps: list[tuple[float, float, float, float]]):
    return [(base + o, base + h, base + l, base + c) for o, h, l, c in steps]


# NIFTY last-session script, offsets from 25,940
NIFTY_SCRIPT = scale_script(25940, [
    (0, 30, -25, 20), (20, 45, 5, 35), (35, 40, -35, 10),        # 09:15-09:25 -> OR 25,905-25,985
    (10, 38, 0, 35), (35, 60, 30, 55),                            # 09:30 close 25,975; 09:35 close 25,995 (> OR high)
    (55, 70, 45, 65), (65, 85, 55, 80), (80, 95, 70, 90), (90, 110, 80, 105), (105, 120, 95, 112),
    (112, 125, 100, 118), (118, 130, 105, 120),
])


def main():
    rng = np.random.default_rng(7)
    ROOT.mkdir(parents=True, exist_ok=True)
    for sub in ("candles", "chains", "expiries", "nse"):
        (ROOT / sub).mkdir(exist_ok=True)
    days = trading_days(LAST, 61)
    older = trading_days(days[0] - timedelta(days=1), 260)

    # --- NIFTY spot (no volume) and future (volume, +60 basis)
    nifty = rescale(series(rng, days[:-1], 25600, 0.008, 0), 25925.0)
    last_close = nifty[-1][4]
    nifty += bars_for_day(rng, LAST, 25940, 0.0005, 0.006, 0, NIFTY_SCRIPT)[0]
    fut = [(t, o + 60, h + 60, l + 60, c + 60, int(rng.integers(40000, 90000)) * (2 if i % 75 < 6 else 1))
           for i, (t, o, h, l, c, _) in enumerate(nifty)]
    write("candles/NIFTY_5.json", payload(nifty))
    write("candles/NIFTY_FUT_5.json", payload(fut))
    write("candles/NIFTY_D.json", daily_payload(nifty, older, rng, 23800, 0.008, 0))
    write("candles/NIFTY_FUT_D.json", daily_payload(fut, older, rng, 23860, 0.008, 60000))

    # BANKNIFTY / others for the index board
    for sym, px, vol in (("BANKNIFTY", 58200, 0.01), ("FINNIFTY", 27400, 0.009), ("MIDCPNIFTY", 13300, 0.011),
                         ("SENSEX", 84900, 0.008), ("INDIAVIX", 12.4, 0.04)):
        rows = series(rng, days, px, vol, 0)
        write(f"candles/{sym}_5.json", payload(rows))
        write(f"candles/{sym}_D.json", daily_payload(rows, older, rng, px * 0.95, vol, 0))

    # --- stocks
    rel_script = scale_script(1480, [(0, 4, -3, 2), (2, 5, -2, 3), (3, 4.5, -1, 4), (4, 9, 3.5, 8.5)])
    rel = rescale(series(rng, days[:-1], 1450, 0.012, 120000), 1471.2)
    rel += bars_for_day(rng, LAST, 1480, 0.002, 0.008, 120000, rel_script)[0]
    write("candles/RELIANCE_5.json", payload(rel))
    write("candles/RELIANCE_D.json", daily_payload(rel, older, rng, 1300, 0.012, 120000))

    # HDFCBANK: sell-off into the last days then a reversal day (oversold bounce on daily)
    hd_shape = lambda i, n: -0.022 if i >= n - 9 else rng.normal(0.0005, 0.008)
    hd = series(rng, days[-1:], 1655, 0.004, 90000, drift=0.02)
    hd_daily = daily_payload([], older + days[:-1], rng, 1900, 0.009, 90000, hd_shape)
    f = 1640.0 / hd_daily["close"][-1]
    for k in ("open", "high", "low", "close"):
        hd_daily[k] = [round(x * f, 2) for x in hd_daily[k]]
    last_hd = [(epoch(LAST, 555), hd[0][1], max(r[2] for r in hd), min(r[3] for r in hd), hd[-1][4], sum(r[5] for r in hd))]
    hd_daily["timestamp"] += [last_hd[0][0]]
    for k, idx in (("open", 1), ("high", 2), ("low", 3), ("close", 4), ("volume", 5)):
        hd_daily[k] += [last_hd[0][idx]]
    hd_daily["open_interest"] += [0]
    prev_high = hd_daily["high"][-2]
    hd_daily["close"][-1] = max(hd_daily["close"][-1], round(prev_high * 1.004, 2))
    hd_daily["high"][-1] = max(hd_daily["high"][-1], hd_daily["close"][-1])
    write("candles/HDFCBANK_D.json", hd_daily)
    write("candles/HDFCBANK_5.json", payload(hd))

    # TCS: pole then tight flag on daily
    def tcs_shape(i, n):
        k = n - i
        if 9 < k <= 15:
            return 0.016
        if k <= 9:
            return [-0.004, 0.002, -0.003, 0.001, -0.002, 0.003, -0.001, 0.002, 0.001][9 - k]
        return rng.normal(0.0004, 0.007)
    tcs_daily = daily_payload([], older + days, rng, 3000, 0.008, 50000, tcs_shape)
    write("candles/TCS_D.json", tcs_daily)
    write("candles/TCS_5.json", payload(series(rng, days, 3300, 0.006, 50000)))

    # --- instrument master
    write_master()

    # --- option chains
    spot = 25995.0
    write(f"chains/NIFTY_{WEEKLY}.json", chain_payload(spot, WEEKLY, 25000, 27000, 50, 0.118, 65, peak_ce=26500, peak_pe=25500))
    write(f"chains/NIFTY_{MONTHLY}.json", chain_payload(spot, MONTHLY, 25000, 27000, 50, 0.125, 65, peak_ce=26800, peak_pe=25200))
    write(f"chains/BANKNIFTY_{MONTHLY}.json", chain_payload(58250, MONTHLY, 56000, 60500, 100, 0.14, 30, peak_ce=59500, peak_pe=57000))
    write(f"chains/RELIANCE_{MONTHLY}.json", chain_payload(1488.5, MONTHLY, 1380, 1600, 10, 0.22, 500, peak_ce=1550, peak_pe=1440))
    write("expiries/NIFTY.json", {"data": [str(WEEKLY), "2026-11-10", "2026-11-17", str(MONTHLY), "2026-12-29"]})
    write("expiries/BANKNIFTY.json", {"data": [str(MONTHLY), "2026-12-29"]})
    write("expiries/RELIANCE.json", {"data": [str(MONTHLY), "2026-12-29"]})

    ts = NOW.isoformat()
    write("quotes.json", {
        "NIFTY": {"ltp": spot, "open": 25940, "high": 26000, "low": 25905, "close": last_close, "ts": ts},
        "NIFTY FUT": {"ltp": spot + 60, "open": 26000, "high": 26060, "low": 25965, "close": last_close + 60, "ts": ts},
        "RELIANCE": {"ltp": 1488.5, "open": 1480, "high": 1489, "low": 1477, "close": 1471.2, "ts": ts},
        "BANKNIFTY": {"ltp": 58250, "open": 58200, "high": 58300, "low": 58120, "close": 58150, "ts": ts},
    })
    write("funds.json", {"available": 250000.0, "utilized": 0.0})
    write("margin.json", {"total": 3200.0, "span": 0.0, "exposure": 0.0, "source": "fixture"})

    # --- NSE public data
    write("nse/announcements.json", [
        {"symbol": "RELIANCE", "sm_name": "Reliance Industries Limited", "desc": "Outcome of Board Meeting",
         "attchmntText": "Board approved unaudited financial results for the quarter ended September 30, 2026",
         "an_dt": "29-Oct-2026 08:12:40", "attchmntFile": "https://nsearchives.nseindia.com/corporate/RELIANCE_29102026.pdf"},
        {"symbol": "RELIANCE", "sm_name": "Reliance Industries Limited", "desc": "Analysts/Institutional Investor Meet",
         "attchmntText": "Schedule of analyst meet", "an_dt": "27-Oct-2026 18:01:00", "attchmntFile": ""},
    ])
    (ROOT / "nse" / "fo_secban.txt").write_text("Securities in Ban For Trade Date 29-OCT-2026:\n1,RBLBANK\n2,IDEA\n")
    write("nse/large_deals.json", {
        "BULK_DEALS_DATA": [{"date": "29-Oct-2026", "symbol": "TCS", "name": "Tata Consultancy Services",
                             "clientName": "XYZ MUTUAL FUND", "buySell": "BUY", "qty": "1250000", "watp": "3412.55", "remarks": "-"}],
        "BLOCK_DEALS_DATA": [{"date": "29-Oct-2026", "symbol": "HDFCBANK", "name": "HDFC Bank",
                              "clientName": "ABC FPI", "buySell": "SELL", "qty": "3000000", "watp": "1652.10", "remarks": "-"}],
    })
    write("nse/insider.json", {"data": [
        {"symbol": "RELIANCE", "acqName": "Promoter Group Entity", "personCategory": "Promoter Group", "tdpTransactionType": "Buy",
         "secType": "Equity Shares", "secAcq": "500000", "secVal": "740000000", "acqMode": "Market Purchase",
         "acqfromDt": "24-Oct-2026", "acqtoDt": "24-Oct-2026", "intimDt": "27-Oct-2026"}]})
    write("nse/results.json", {"resCmpData": [
        {"re_to_dt": q, "re_net_sale": str(rev), "re_net_profit": str(np_), "re_basic_eps": str(eps), "re_res_type": "C"}
        for q, rev, np_, eps in [("30-Sep-2026", 2512000, 191200, 14.1), ("30-Jun-2026", 2448000, 184500, 13.6),
                                 ("31-Mar-2026", 2405000, 190100, 14.0), ("31-Dec-2025", 2391000, 185400, 13.7),
                                 ("30-Sep-2025", 2318000, 172300, 12.7), ("30-Jun-2025", 2290000, 168000, 12.4)]]})
    write("nse/holidays.json", {"CM": [{"tradingDate": "08-Nov-2026"}, {"tradingDate": "24-Nov-2026"}]})
    print(f"fixtures written to {ROOT}")


def chain_payload(spot, expiry, lo, hi, step, atm_iv, lot, peak_ce, peak_pe):
    t = max((datetime(expiry.year, expiry.month, expiry.day, 15, 30, tzinfo=IST) - NOW).total_seconds(), 60) / (365 * 86400)
    oc, sid = {}, 60000 + int(spot) % 1000 * 10
    for k in range(lo, hi + 1, step):
        m = k / spot - 1
        iv = atm_iv + 0.9 * m * m - (0.18 * m if m < 0 else 0.03 * m)
        entry = {}
        for kind, peak in (("ce", peak_ce), ("pe", peak_pe)):
            price = fno.bs_price(spot, k, t, 0.065, iv, kind.upper())
            g = fno.greeks(spot, k, t, 0.065, iv, kind.upper())
            oi = int(4_000_000 * math.exp(-((k - peak) / (6 * step)) ** 2) / lot) * lot + lot * 50
            prev_oi = int(oi * (0.82 if kind == "pe" else 0.9))
            ltp = max(round(price / 0.05) * 0.05, 0.05)
            sid += 1
            entry[kind] = {"average_price": round(ltp, 2), "last_price": round(ltp, 2), "implied_volatility": round(iv * 100, 2),
                           "greeks": {k2: round(v, 5) for k2, v in g.items()}, "oi": oi, "previous_oi": prev_oi,
                           "volume": oi * 3, "previous_volume": oi * 2,
                           "previous_close_price": round(ltp * (0.9 if kind == "ce" else 1.12), 2), "security_id": sid,
                           "top_bid_price": round(max(ltp - max(0.05, ltp * 0.003), 0.05), 2),
                           "top_ask_price": round(ltp + max(0.05, ltp * 0.003), 2),
                           "top_bid_quantity": lot * 10, "top_ask_quantity": lot * 12}
        oc[f"{k:.6f}"] = entry
    return {"data": {"last_price": spot, "oc": oc}, "status": "success", "ts": NOW.isoformat()}


def write_master():
    cols = ["SEM_EXM_EXCH_ID", "SEM_SEGMENT", "SEM_SMST_SECURITY_ID", "SEM_INSTRUMENT_NAME", "SEM_EXPIRY_CODE",
            "SEM_TRADING_SYMBOL", "SEM_LOT_UNITS", "SEM_CUSTOM_SYMBOL", "SEM_EXPIRY_DATE", "SEM_STRIKE_PRICE",
            "SEM_OPTION_TYPE", "SEM_TICK_SIZE", "SEM_EXPIRY_FLAG", "SEM_EXCH_INSTRUMENT_TYPE", "SEM_SERIES", "SM_SYMBOL_NAME"]
    rows = []
    for sym, sid in (("RELIANCE", 2885), ("HDFCBANK", 1333), ("TCS", 11536), ("INFY", 1594), ("SBIN", 3045)):
        rows.append(["NSE", "E", sid, "EQUITY", "", sym, 1, sym, "", "", "", 5, "", "ES", "EQ", sym])
    sid = 40000

    def deriv(exch, und, lot, expiry, strikes, flag, inst_fut, inst_opt):
        nonlocal sid
        mon = expiry.strftime("%b%Y")
        exp = f"{expiry} 14:30:00"
        sid += 1
        rows.append([exch, "D", sid, inst_fut, 0, f"{und}-{mon}-FUT", lot, f"{und} {expiry:%b} FUT", exp, -0.01, "XX", 10, "M", inst_fut, "", und])
        for k in strikes:
            for opt in ("CE", "PE"):
                sid += 1
                rows.append([exch, "D", sid, inst_opt, "", f"{und}-{mon}-{k}-{opt}", lot,
                             f"{und} {expiry:%d %b} {k} {'CALL' if opt == 'CE' else 'PUT'}", exp, float(k), opt, 5, flag, inst_opt, "", und])

    deriv("NSE", "NIFTY", 65, MONTHLY, range(25000, 27001, 50), "M", "FUTIDX", "OPTIDX")
    deriv("NSE", "NIFTY", 65, WEEKLY, range(25000, 27001, 50), "W", "FUTIDX", "OPTIDX")
    deriv("NSE", "BANKNIFTY", 30, MONTHLY, range(56000, 60501, 100), "M", "FUTIDX", "OPTIDX")
    deriv("NSE", "RELIANCE", 500, MONTHLY, range(1380, 1601, 10), "M", "FUTSTK", "OPTSTK")
    deriv("NSE", "HDFCBANK", 550, MONTHLY, range(1500, 1801, 10), "M", "FUTSTK", "OPTSTK")
    deriv("BSE", "SENSEX", 20, date(2026, 11, 5), range(84000, 86001, 100), "W", "FUTIDX", "OPTIDX")
    # Drop the duplicate weekly NIFTY future row (only monthly futures exist)
    rows = [r for r in rows if not (r[5] == f"NIFTY-{WEEKLY:%b%Y}-FUT" and r[8].startswith(str(WEEKLY)))]
    with open(ROOT / "scrip-master.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


def write(rel: str, obj) -> None:
    (ROOT / rel).write_text(json.dumps(obj, separators=(",", ":")))


if __name__ == "__main__":
    main()
