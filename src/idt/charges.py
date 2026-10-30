"""Indian transaction charges: brokerage, STT, exchange fees, SEBI fee, stamp duty and GST.

Rates change with budgets and exchange circulars. Override any value via config
`charges_override`, e.g. {"stt": {"opt_sell": 0.0015}}. Verify against your broker's contract note.
"""

from __future__ import annotations

import copy

RATES = {
    "effective": "2026-04-01",
    "stt": {                       # Union Budget 2026-27 raised F&O STT from 2026-04-01
        "eq_intraday_sell": 0.00025,
        "eq_delivery": 0.001,      # both sides
        "fut_sell": 0.0005,
        "opt_sell": 0.0015,        # on premium
        "opt_exercise": 0.0015,    # on intrinsic value of ITM options exercised at expiry
    },
    "exchange": {                  # transaction charges (fraction of turnover / premium turnover)
        "NSE": {"eq": 0.0000297, "fut": 0.0000173, "opt": 0.0003503},
        "BSE": {"eq": 0.0000375, "fut": 0.0, "opt": 0.000325},
    },
    "sebi_per_crore": 10.0,
    "stamp_buy": {"eq_intraday": 0.00003, "eq_delivery": 0.00015, "fut": 0.00002, "opt": 0.00003},
    "gst": 0.18,
}

SEGMENTS = ("eq_intraday", "eq_delivery", "fut", "opt")


def rates(override: dict | None = None) -> dict:
    out = copy.deepcopy(RATES)
    for key, value in (override or {}).items():
        if isinstance(value, dict):
            out.setdefault(key, {}).update(value)
        else:
            out[key] = value
    return out


def compute(segment: str, buy_value: float, sell_value: float, exchange: str = "NSE", orders: int = 2,
            brokerage: dict | None = None, override: dict | None = None) -> dict:
    """Charges for a round trip. Values are turnover in INR (premium turnover for options)."""
    if segment not in SEGMENTS:
        raise ValueError(f"segment must be one of {SEGMENTS}")
    r = rates(override)
    brokerage = brokerage or {"per_order": 20.0, "equity_pct_cap": 0.0003}
    per_order = float(brokerage.get("per_order", 20.0))

    if segment == "eq_delivery":
        brok = 0.0
    elif segment == "eq_intraday":
        cap = float(brokerage.get("equity_pct_cap", 0.0003))
        brok = min(per_order, buy_value * cap) + min(per_order, sell_value * cap)
    else:
        brok = per_order * orders

    stt = {"eq_intraday": sell_value * r["stt"]["eq_intraday_sell"],
           "eq_delivery": (buy_value + sell_value) * r["stt"]["eq_delivery"],
           "fut": sell_value * r["stt"]["fut_sell"],
           "opt": sell_value * r["stt"]["opt_sell"]}[segment]
    kind = "eq" if segment.startswith("eq") else segment
    exch = (buy_value + sell_value) * r["exchange"][exchange][kind]
    sebi = (buy_value + sell_value) * r["sebi_per_crore"] / 1e7
    stamp = buy_value * r["stamp_buy"][segment]
    gst = (brok + exch + sebi) * r["gst"]
    total = brok + stt + exch + sebi + stamp + gst
    return {k: round(v, 2) for k, v in {"brokerage": brok, "stt": stt, "exchange_txn": exch, "sebi": sebi,
                                        "stamp": stamp, "gst": gst, "total": total}.items()}


def segment_for(instrument_kind: str, product: str = "MIS") -> str:
    if instrument_kind == "option":
        return "opt"
    if instrument_kind == "future":
        return "fut"
    return "eq_delivery" if product == "CNC" else "eq_intraday"
