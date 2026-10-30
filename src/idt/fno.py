"""Options math (Black-Scholes, IV, Greeks) and option-chain analytics for Indian F&O."""

from __future__ import annotations

import math
from datetime import datetime

import numpy as np

from .data.base import OptionChain
from .market import years_to_expiry

SQRT2 = math.sqrt(2.0)


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / SQRT2))


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def norm_cdf_np(x: np.ndarray) -> np.ndarray:
    """Vectorised normal CDF (Abramowitz-Stegun 7.1.26 erf, |error| < 1.5e-7)."""
    z = np.abs(x) / SQRT2
    t = 1.0 / (1.0 + 0.3275911 * z)
    poly = t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429))))
    erf = 1.0 - poly * np.exp(-z * z)
    return 0.5 * (1.0 + np.sign(x) * erf)


def _d1d2(s, k, t, r, sigma, q=0.0):
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    return d1, d1 - sigma * math.sqrt(t)


def bs_price(s: float, k: float, t: float, r: float, sigma: float, kind: str, q: float = 0.0) -> float:
    if t <= 0 or sigma <= 0:
        return max(0.0, s - k) if kind == "CE" else max(0.0, k - s)
    d1, d2 = _d1d2(s, k, t, r, sigma, q)
    if kind == "CE":
        return s * math.exp(-q * t) * norm_cdf(d1) - k * math.exp(-r * t) * norm_cdf(d2)
    return k * math.exp(-r * t) * norm_cdf(-d2) - s * math.exp(-q * t) * norm_cdf(-d1)


def bs_price_np(s: np.ndarray, k: float, t: np.ndarray | float, r: float, sigma: float, kind: str) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    t = np.maximum(np.asarray(t, dtype=float), 1e-9)
    sq = sigma * np.sqrt(t)
    d1 = (np.log(s / k) + (r + 0.5 * sigma * sigma) * t) / sq
    d2 = d1 - sq
    disc = k * np.exp(-r * t)
    if kind == "CE":
        return s * norm_cdf_np(d1) - disc * norm_cdf_np(d2)
    return disc * norm_cdf_np(-d2) - s * norm_cdf_np(-d1)


def greeks(s: float, k: float, t: float, r: float, sigma: float, kind: str, q: float = 0.0) -> dict:
    """Delta, gamma, theta per calendar day, vega per 1 vol point."""
    d1, d2 = _d1d2(s, k, max(t, 1e-9), r, max(sigma, 1e-6), q)
    sqt = math.sqrt(max(t, 1e-9))
    pdf = norm_pdf(d1)
    gamma = math.exp(-q * t) * pdf / (s * sigma * sqt)
    vega = s * math.exp(-q * t) * pdf * sqt / 100
    if kind == "CE":
        delta = math.exp(-q * t) * norm_cdf(d1)
        theta = (-s * pdf * sigma * math.exp(-q * t) / (2 * sqt) - r * k * math.exp(-r * t) * norm_cdf(d2)
                 + q * s * math.exp(-q * t) * norm_cdf(d1))
    else:
        delta = -math.exp(-q * t) * norm_cdf(-d1)
        theta = (-s * pdf * sigma * math.exp(-q * t) / (2 * sqt) + r * k * math.exp(-r * t) * norm_cdf(-d2)
                 - q * s * math.exp(-q * t) * norm_cdf(-d1))
    return {"delta": delta, "gamma": gamma, "theta": theta / 365, "vega": vega}


def implied_vol(price: float, s: float, k: float, t: float, r: float, kind: str) -> float | None:
    """Bisection on [0.1%, 500%]; None if price is outside no-arbitrage bounds."""
    intrinsic = max(0.0, s - k * math.exp(-r * t)) if kind == "CE" else max(0.0, k * math.exp(-r * t) - s)
    if price <= intrinsic + 1e-9 or t <= 0:
        return None
    lo, hi = 0.001, 5.0
    if bs_price(s, k, t, r, hi, kind) < price:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if bs_price(s, k, t, r, mid, kind) > price:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-6:
            break
    return (lo + hi) / 2


# --- chain analytics ---------------------------------------------------------------

def pcr(chain: OptionChain) -> dict:
    ce_oi = sum(r.ce.oi for r in chain.rows if r.ce)
    pe_oi = sum(r.pe.oi for r in chain.rows if r.pe)
    ce_vol = sum(r.ce.volume for r in chain.rows if r.ce)
    pe_vol = sum(r.pe.volume for r in chain.rows if r.pe)
    ce_chg = sum(r.ce.oi_change for r in chain.rows if r.ce)
    pe_chg = sum(r.pe.oi_change for r in chain.rows if r.pe)
    return {"oi": round(pe_oi / ce_oi, 3) if ce_oi else None,
            "volume": round(pe_vol / ce_vol, 3) if ce_vol else None,
            "oi_change": round(pe_chg / ce_chg, 3) if ce_chg > 0 else None,
            "ce_oi": ce_oi, "pe_oi": pe_oi}


def max_pain(chain: OptionChain) -> float:
    """Expiry price that minimises total intrinsic value paid to option holders."""
    strikes = chain.strikes()
    best, best_pain = strikes[0], float("inf")
    for x in strikes:
        pain = sum((r.ce.oi * max(0.0, x - r.strike) if r.ce else 0) + (r.pe.oi * max(0.0, r.strike - x) if r.pe else 0)
                   for r in chain.rows)
        if pain < best_pain:
            best, best_pain = x, pain
    return best


def buildup(price_change: float, oi_change: float) -> str:
    if oi_change > 0:
        return "long buildup" if price_change > 0 else "short buildup"
    if oi_change < 0:
        return "short covering" if price_change > 0 else "long unwinding"
    return "neutral"


def oi_walls(chain: OptionChain, n: int = 3) -> dict:
    ce = sorted((r for r in chain.rows if r.ce), key=lambda r: r.ce.oi, reverse=True)[:n]
    pe = sorted((r for r in chain.rows if r.pe), key=lambda r: r.pe.oi, reverse=True)[:n]
    ce_add = sorted((r for r in chain.rows if r.ce), key=lambda r: r.ce.oi_change, reverse=True)[:n]
    pe_add = sorted((r for r in chain.rows if r.pe), key=lambda r: r.pe.oi_change, reverse=True)[:n]
    return {"resistance": [{"strike": r.strike, "oi": r.ce.oi, "oi_change": r.ce.oi_change} for r in ce],
            "support": [{"strike": r.strike, "oi": r.pe.oi, "oi_change": r.pe.oi_change} for r in pe],
            "fresh_call_writing": [{"strike": r.strike, "oi_change": r.ce.oi_change} for r in ce_add if r.ce.oi_change > 0],
            "fresh_put_writing": [{"strike": r.strike, "oi_change": r.pe.oi_change} for r in pe_add if r.pe.oi_change > 0]}


def window(chain: OptionChain, strikes_each_side: int = 10) -> list:
    rows = chain.rows
    i = min(range(len(rows)), key=lambda j: abs(rows[j].strike - chain.spot))
    return rows[max(0, i - strikes_each_side): i + strikes_each_side + 1]


def analyze_chain(chain: OptionChain, r: float = 0.065, now: datetime | None = None, strikes_each_side: int = 10) -> dict:
    now = now or chain.ts or datetime.now()
    t = years_to_expiry(chain.expiry, now)
    atm = chain.atm()
    row = chain.row(atm)
    straddle = (row.ce.ltp if row.ce else 0) + (row.pe.ltp if row.pe else 0)
    atm_iv = np.mean([x.iv for x in (row.ce, row.pe) if x and x.iv]) if row else None
    if not atm_iv and row and row.ce and row.ce.ltp:
        iv = implied_vol(row.ce.ltp, chain.spot, atm, t, r, "CE")
        atm_iv = iv * 100 if iv else None

    table = []
    for rw in window(chain, strikes_each_side):
        entry = {"strike": rw.strike}
        for side, q in (("ce", rw.ce), ("pe", rw.pe)):
            if q:
                entry[side] = {"ltp": q.ltp, "iv": q.iv, "oi": q.oi, "oi_change": q.oi_change, "volume": q.volume,
                               "delta": round(q.delta, 3), "buildup": buildup(q.price_change, q.oi_change)}
        table.append(entry)

    otm_put = next((rw for rw in reversed(chain.rows) if rw.strike <= atm * 0.97 and rw.pe and rw.pe.iv), None)
    otm_call = next((rw for rw in chain.rows if rw.strike >= atm * 1.03 and rw.ce and rw.ce.iv), None)
    p = pcr(chain)
    mp = max_pain(chain)
    return {
        "underlying": chain.underlying, "expiry": chain.expiry.isoformat(), "spot": chain.spot,
        "days_to_expiry": round(t * 365, 2), "atm": atm, "atm_iv": round(float(atm_iv), 2) if atm_iv else None,
        "atm_straddle": round(straddle, 2),
        "expected_move": {"points": round(straddle, 2), "range": [round(chain.spot - straddle, 2), round(chain.spot + straddle, 2)]},
        "pcr": p, "max_pain": mp, "max_pain_distance_pct": round((mp / chain.spot - 1) * 100, 2),
        "walls": oi_walls(chain),
        "skew": {"put_3pct_iv": otm_put.pe.iv if otm_put else None, "call_3pct_iv": otm_call.ce.iv if otm_call else None},
        "bias": _bias(p["oi"], chain.spot, mp),
        "table": table,
    }


def _bias(pcr_oi: float | None, spot: float, mp: float) -> str:
    """A descriptive read of positioning, not a signal."""
    if pcr_oi is None:
        return "unknown"
    if pcr_oi > 1.3:
        tone = "put-heavy (writers defending downside; can turn contrarian-bearish if extreme)"
    elif pcr_oi < 0.7:
        tone = "call-heavy (writers capping upside)"
    else:
        tone = "balanced"
    drift = "above" if spot > mp else "below"
    return f"{tone}; spot is {drift} max pain"
