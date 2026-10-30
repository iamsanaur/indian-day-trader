"""Multi-leg option/futures strategies: builders, payoff, breakevens, Greeks and naked-risk detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

import numpy as np

from . import fno
from .data.base import OptionChain, OptionQuote
from .market import years_to_expiry


@dataclass
class Leg:
    kind: str            # CE | PE | FUT
    strike: float        # 0 for FUT
    side: int            # +1 buy, -1 sell
    lots: int
    premium: float       # entry price per unit (option premium, or futures price)
    expiry: str          # YYYY-MM-DD
    iv: float = 0.0      # decimal (0.13)
    security_id: str = ""
    symbol: str = ""

    def value_at_expiry(self, s: np.ndarray | float):
        if self.kind == "CE":
            return np.maximum(np.asarray(s) - self.strike, 0.0)
        if self.kind == "PE":
            return np.maximum(self.strike - np.asarray(s), 0.0)
        return np.asarray(s, dtype=float)

    def to_dict(self) -> dict:
        return asdict(self)


def legs_from_dicts(items: list[dict]) -> list[Leg]:
    return [Leg(**{k: v for k, v in it.items() if k in Leg.__dataclass_fields__}) for it in items]


def pnl_at_expiry(legs: list[Leg], s, lot_size: int) -> np.ndarray:
    s = np.asarray(s, dtype=float)
    total = np.zeros_like(s)
    for leg in legs:
        total += leg.side * (leg.value_at_expiry(s) - leg.premium) * leg.lots * lot_size
    return total


def pnl_now(legs: list[Leg], s, moment: datetime, r: float, lot_size: int, iv_shift: float = 0.0) -> np.ndarray:
    """Mark-to-model P/L before expiry (Black-Scholes, constant IV + optional shift)."""
    s = np.asarray(s, dtype=float)
    total = np.zeros_like(s)
    for leg in legs:
        if leg.kind == "FUT":
            value = s
        else:
            t = years_to_expiry(date.fromisoformat(leg.expiry), moment)
            value = fno.bs_price_np(s, leg.strike, t, r, max(leg.iv + iv_shift, 0.01), leg.kind)
        total += leg.side * (value - leg.premium) * leg.lots * lot_size
    return total


def net_debit(legs: list[Leg], lot_size: int) -> float:
    """> 0: premium paid. < 0: credit received."""
    return float(sum(l.side * l.premium * l.lots * lot_size for l in legs if l.kind != "FUT"))


def naked_legs(legs: list[Leg]) -> list[str]:
    """Short options not covered lot-for-lot by longs of the same type (calls may be covered by long futures)."""
    lots = lambda kind, side: sum(l.lots for l in legs if l.kind == kind and l.side == side)
    issues = []
    if lots("CE", -1) > lots("CE", +1) + lots("FUT", +1):
        issues.append("uncovered short call (unlimited upside risk)")
    if lots("PE", -1) > lots("PE", +1) + lots("FUT", -1):
        issues.append("uncovered short put (large downside risk)")
    if lots("FUT", -1) > lots("CE", +1):
        issues.append("short futures")
    return issues


def analyze(legs: list[Leg], spot: float, lot_size: int) -> dict:
    strikes = [l.strike for l in legs if l.kind != "FUT"]
    hi = max([spot * 1.5] + [k * 1.5 for k in strikes])
    grid = np.unique(np.concatenate([np.linspace(0, hi, 3001), np.array(strikes + [spot])]))
    pnl = pnl_at_expiry(legs, grid, lot_size)

    slope_right = sum(l.side * l.lots for l in legs if l.kind in ("CE", "FUT"))
    breakevens = []
    for i in range(1, len(grid)):
        a, b = pnl[i - 1], pnl[i]
        if b == 0 and a != 0:
            breakevens.append(float(grid[i]))
        elif a * b < 0:
            breakevens.append(float(grid[i - 1] + (grid[i] - grid[i - 1]) * (-a) / (b - a)))
    max_profit = float("inf") if slope_right > 0 else float(pnl.max())
    max_loss = float("-inf") if slope_right < 0 else float(pnl.min())
    return {
        "lot_size": lot_size,
        "net_premium": round(net_debit(legs, lot_size), 2),
        "premium_type": "debit" if net_debit(legs, lot_size) > 0 else "credit",
        "max_profit": None if max_profit == float("inf") else round(max_profit, 2),
        "max_loss": None if max_loss == float("-inf") else round(max_loss, 2),
        "unlimited_profit": max_profit == float("inf"),
        "unlimited_loss": max_loss == float("-inf"),
        "breakevens": [round(b, 2) for b in breakevens],
        "pnl_at_spot": round(float(pnl_at_expiry(legs, spot, lot_size)), 2),
        "naked": naked_legs(legs),
    }


def aggregate_greeks(legs: list[Leg], spot: float, moment: datetime, r: float, lot_size: int) -> dict:
    out = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for leg in legs:
        units = leg.side * leg.lots * lot_size
        if leg.kind == "FUT":
            out["delta"] += units
            continue
        t = years_to_expiry(date.fromisoformat(leg.expiry), moment)
        g = fno.greeks(spot, leg.strike, t, r, max(leg.iv, 0.01), leg.kind)
        for k in out:
            out[k] += g[k] * units
    return {k: round(v, 2) for k, v in out.items()}


# --- builders ------------------------------------------------------------------------

def strike_step(chain: OptionChain) -> float:
    s = chain.strikes()
    diffs = [b - a for a, b in zip(s, s[1:]) if b > a]
    return min(diffs) if diffs else 50.0


def _price(q: OptionQuote, side: int) -> float:
    """Pay the ask when buying, receive the bid when selling, if a two-sided quote exists."""
    if q.bid > 0 and q.ask > 0:
        return q.ask if side > 0 else q.bid
    return q.ltp


def make_leg(chain: OptionChain, strike: float, kind: str, side: int, lots: int = 1) -> Leg:
    row = chain.row(strike)
    q = getattr(row, kind.lower()) if row else None
    if q is None or q.ltp <= 0:
        raise ValueError(f"No live quote for {chain.underlying} {chain.expiry} {strike:g} {kind}")
    return Leg(kind, strike, side, lots, round(_price(q, side), 2), chain.expiry.isoformat(), round(q.iv / 100, 4),
               q.security_id, f"{chain.underlying} {chain.expiry.isoformat()} {strike:g} {kind}")


def strike_by_delta(chain: OptionChain, kind: str, target: float) -> float:
    rows = [r for r in chain.rows if getattr(r, kind.lower()) and getattr(r, kind.lower()).delta]
    return min(rows, key=lambda r: abs(abs(getattr(r, kind.lower()).delta) - target)).strike


STRATEGIES = {
    "long-call": "Buy CE (ATM + offset)",
    "long-put": "Buy PE (ATM - offset)",
    "short-call": "Sell CE (naked; needs allow_naked)",
    "short-put": "Sell PE (naked; needs allow_naked)",
    "bull-call-spread": "Buy ATM CE, sell CE `width` steps higher (debit)",
    "bear-put-spread": "Buy ATM PE, sell PE `width` steps lower (debit)",
    "bull-put-spread": "Sell PE `offset` steps below ATM, buy PE `width` further (credit)",
    "bear-call-spread": "Sell CE `offset` steps above ATM, buy CE `width` further (credit)",
    "long-straddle": "Buy ATM CE + PE",
    "short-straddle": "Sell ATM CE + PE (naked)",
    "long-strangle": "Buy CE/PE `offset` steps OTM (or by --delta)",
    "short-strangle": "Sell CE/PE `offset` steps OTM or by --delta (naked)",
    "iron-condor": "Short strangle `offset` + long wings `width` further (defined risk)",
    "iron-fly": "Short ATM straddle + long wings `width` away (defined risk)",
}


def build(name: str, chain: OptionChain, lots: int = 1, offset: int = 0, width: int = 2,
          delta: float | None = None) -> list[Leg]:
    step = strike_step(chain)
    atm = chain.atm()
    up = lambda n: atm + n * step
    dn = lambda n: atm - n * step
    ce = lambda k, side: make_leg(chain, k, "CE", side, lots)
    pe = lambda k, side: make_leg(chain, k, "PE", side, lots)
    otm = max(offset, 1)
    call_k = strike_by_delta(chain, "CE", delta) if delta else up(otm)
    put_k = strike_by_delta(chain, "PE", delta) if delta else dn(otm)

    table = {
        "long-call": lambda: [ce(up(offset), +1)],
        "long-put": lambda: [pe(dn(offset), +1)],
        "short-call": lambda: [ce(call_k if delta else up(offset), -1)],
        "short-put": lambda: [pe(put_k if delta else dn(offset), -1)],
        "bull-call-spread": lambda: [ce(up(offset), +1), ce(up(offset + width), -1)],
        "bear-put-spread": lambda: [pe(dn(offset), +1), pe(dn(offset + width), -1)],
        "bull-put-spread": lambda: [pe(dn(offset), -1), pe(dn(offset + width), +1)],
        "bear-call-spread": lambda: [ce(up(offset), -1), ce(up(offset + width), +1)],
        "long-straddle": lambda: [ce(atm, +1), pe(atm, +1)],
        "short-straddle": lambda: [ce(atm, -1), pe(atm, -1)],
        "long-strangle": lambda: [ce(call_k, +1), pe(put_k, +1)],
        "short-strangle": lambda: [ce(call_k, -1), pe(put_k, -1)],
        "iron-condor": lambda: [ce(call_k, -1), ce(call_k + width * step, +1),
                                pe(put_k, -1), pe(put_k - width * step, +1)],
        "iron-fly": lambda: [ce(atm, -1), pe(atm, -1), ce(up(width), +1), pe(dn(width), +1)],
    }
    if name not in table:
        raise ValueError(f"Unknown strategy {name}. Choose from: {', '.join(table)}")
    return table[name]()


def parse_leg_spec(spec: str, chain: OptionChain) -> Leg:
    """'+1x26000CE' / '-2x25800PE' -> Leg priced from the chain."""
    sign = -1 if spec.startswith("-") else 1
    body = spec.lstrip("+-")
    lots_text, rest = body.split("x", 1) if "x" in body else ("1", body)
    kind = rest[-2:].upper()
    return make_leg(chain, float(rest[:-2]), kind, sign, int(lots_text))
