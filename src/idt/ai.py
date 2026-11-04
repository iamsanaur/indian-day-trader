"""AI trade explanations from a local Ollama model (DeepSeek-R1 1.5B by default).

The model explains; it never calculates or decides. Small models get arithmetic wrong often enough that
letting one size, price or gate a trade would be unsafe, so the split is strict:

  1. The engine computes every number (entry, stop, target, odds, size, charges, PASS/BLOCK) and they go
     into a fact sheet.
  2. The model writes the reason in plain words from that sheet only (program-aided: it copies numbers,
     it does not derive them). Its hidden <think> reasoning is dropped.
  3. A checker pulls every number out of the model's text. Any number that is not in the fact sheet (or a
     plain rounding of one), any forbidden phrase ("guaranteed", "sure profit", ...), or a verdict that
     contradicts the risk gate rejects the text. It retries once with the problems listed, then falls back
     to a deterministic explanation built from the same facts.

So the reason shown to the user is either verified model text or the template. Never unchecked numbers.
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Callable

import requests

DEFAULT_MODEL = "deepseek-r1:1.5b"
DEFAULT_HOST = "http://127.0.0.1:11434"

SYSTEM_PROMPT = """You explain Indian intraday trades to a trader. You are given a FACT SHEET computed by a
trading engine. Rules you must follow:
- Use ONLY numbers that appear in the FACT SHEET, copied exactly. Never calculate, estimate or round to new values.
- Never invent prices, percentages, levels, dates or probabilities.
- The risk verdict (PASS or BLOCK) is final. Never suggest overriding it. If it is BLOCK, explain why the
  trade should not be taken now.
- Never promise profit. Never say guaranteed, certain, sure shot, risk-free or can't lose.
- This is not investment advice and nothing places orders; the trader decides.
Write 4 to 7 short bullet lines, each starting with "- ":
  setup (what triggered), plan (entry, stop, target, reward:risk), odds (the Time Machine verdict),
  size and money at risk, the risk verdict, and the main thing that would make this trade wrong.
No headings, no preamble, no conclusion paragraph."""

FORBIDDEN = re.compile(
    r"\b(guarantee[ds]?|certain(ly)?|sure[- ]shot|risk[- ]free|can'?t lose|cannot lose|100% (safe|sure)|"
    r"definitely (go|will)|will (surely|definitely)|override the (risk|block)|ignore the (risk|block))\b",
    re.I)
NUMBER = re.compile(r"(?<![\w.])[-+]?(?:₹|rs\.?\s*)?\d[\d,]*(?:\.\d+)?%?", re.I)
TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


class AIError(RuntimeError):
    pass


# --- config / client ---------------------------------------------------------------------

def settings(cfg: dict) -> dict:
    ai = dict(cfg.get("ai") or {})
    return {"enabled": bool(ai.get("enabled", True)),
            "host": os.environ.get("OLLAMA_HOST") or ai.get("host") or DEFAULT_HOST,
            "model": os.environ.get("IDT_AI_MODEL") or ai.get("model") or DEFAULT_MODEL,
            "timeout": float(ai.get("timeout", 120)),
            "temperature": float(ai.get("temperature", 0.3)),
            "num_ctx": int(ai.get("num_ctx", 4096)),
            "seed": int(ai.get("seed", 7))}


def _host(url: str) -> str:
    url = url.rstrip("/")
    return url if url.startswith("http") else f"http://{url}"


def ollama_chat(messages: list[dict], s: dict, session: requests.Session | None = None) -> str:
    """POST /api/chat (non-streaming). Returns the answer text without the model's hidden reasoning."""
    http = session or requests
    body = {"model": s["model"], "messages": messages, "stream": False, "think": True,
            "options": {"temperature": s["temperature"], "num_ctx": s["num_ctx"], "seed": s["seed"]}}
    try:
        resp = http.post(f"{_host(s['host'])}/api/chat", json=body, timeout=s["timeout"])
    except requests.RequestException as exc:
        raise AIError(f"Ollama is not reachable at {s['host']} ({exc.__class__.__name__}). "
                      f"Start it with `ollama serve` and `ollama pull {s['model']}`.") from exc
    if resp.status_code == 404:
        raise AIError(f"Ollama has no model {s['model']}: run `ollama pull {s['model']}`.")
    if resp.status_code == 400 and "think" in resp.text.lower():   # older Ollama without the think option
        body = {k: v for k, v in body.items() if k != "think"}
        resp = http.post(f"{_host(s['host'])}/api/chat", json=body, timeout=s["timeout"])
    if resp.status_code >= 400:
        raise AIError(f"Ollama error {resp.status_code}: {resp.text[:200]}")
    return strip_thinking(resp.json().get("message", {}).get("content", ""))


def ollama_status(s: dict, session: requests.Session | None = None) -> dict:
    http = session or requests
    try:
        tags = http.get(f"{_host(s['host'])}/api/tags", timeout=5).json().get("models", [])
    except (requests.RequestException, ValueError):
        return {"reachable": False, "host": s["host"], "model": s["model"], "installed": False}
    names = {m.get("name") for m in tags} | {m.get("model") for m in tags}
    return {"reachable": True, "host": s["host"], "model": s["model"],
            "installed": s["model"] in names or f"{s['model']}:latest" in names}


def strip_thinking(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return text.split("</think>")[-1].strip()


# --- the fact sheet ------------------------------------------------------------------------

def _r(x: Any, nd: int = 2):
    return round(float(x), nd) if isinstance(x, (int, float)) and not isinstance(x, bool) else x


def facts(setup: dict | None, plan: dict | None, tm: dict | None, orders: dict | None, risk: dict | None) -> dict:
    """Everything the explanation may say, already computed by the engine."""
    f: dict[str, Any] = {}
    if setup:
        rng = setup.get("range") or {}
        f["setup"] = {k: v for k, v in {
            "symbol": setup.get("symbol"), "setup": setup.get("setup"), "state": setup.get("state"),
            "side": setup.get("side"), "trigger_price": _r(setup.get("entry")),
            "trigger_bar_closed_at": str(setup.get("trigger_close") or "")[11:16] or None,
            "level_broken": _r(setup.get("trigger_level")), "pct_beyond_level": _r(setup.get("pct_beyond")),
            "opening_range_high": _r(rng.get("high")), "opening_range_low": _r(rng.get("low")),
            "minutes_since_trigger": setup.get("minutes_since"), "late_warning": setup.get("late")}.items()
            if v not in (None, "")}
    if plan:
        p = {"instrument": plan.get("contract") or plan.get("strategy") or plan.get("symbol"),
             "kind": plan.get("kind"), "side": plan.get("side"), "basis": plan.get("basis"),
             "entry": _r(plan.get("entry")), "stop": _r(plan.get("stop", plan.get("stop_pnl"))),
             "target": _r(plan.get("target", plan.get("target_pnl"))),
             "stop_rule": plan.get("stop_rule"), "target_rule": plan.get("target_rule"),
             "reward_to_risk": _r(plan.get("rr")), "risk_per_unit_rs": _r(plan.get("risk_per_unit")),
             "reward_per_unit_rs": _r(plan.get("reward_per_unit")), "unit": plan.get("unit"),
             "lot_size": plan.get("lot_size"), "square_off": plan.get("squareoff"), "expiry": plan.get("expiry")}
        if plan.get("basis") == "underlying" and plan.get("kind") in ("option", "future"):
            p.update(underlying_stop=_r(plan.get("underlying_stop")), underlying_target=_r(plan.get("underlying_target")))
        f["plan"] = {k: v for k, v in p.items() if v is not None}
    if tm and tm.get("monte_carlo"):
        mc = tm["monte_carlo"]
        pct = lambda x: None if x is None else round(100 * x, 1)
        f["odds"] = {k: v for k, v in {
            "paths": mc.get("paths"), "seed": mc.get("seed"), "sessions_sampled": mc.get("sessions_sampled"),
            "target_first_pct": pct(mc.get("p_target")), "stop_first_pct": pct(mc.get("p_stop")),
            "neither_pct": pct(mc.get("p_flat")), "green_pct": pct(mc.get("p_green")),
            "average_r": mc.get("expected_r"), "verdict": tm.get("verdict"),
            "verdict_notes": tm.get("verdict_notes") or None, "history": tm.get("replay_line")}.items()
            if v is not None}
    if orders:
        f["size"] = {k: v for k, v in {
            "units": orders.get("units"), "unit": orders.get("unit"),
            "quantity": sum(l.get("quantity", 0) for l in orders.get("legs", [])[:1]) or None,
            "loss_at_stop_rs": _r(orders.get("loss_at_stop")), "profit_at_target_rs": _r(orders.get("profit_at_target")),
            "charges_if_stopped_rs": _r((orders.get("charges") or {}).get("if_stopped")),
            "margin_rs": _r((orders.get("margin") or {}).get("total")), "decided_by": orders.get("decided_by"),
            "reward_to_risk_now": _r(orders.get("rr")), "price_now": _r(orders.get("entry_now")),
            "max_loss_budget_rs": _r(orders.get("max_loss_budget"))}.items() if v is not None}
    if risk:
        f["risk"] = {"verdict": risk.get("verdict"), "failed_rules": risk.get("reasons") or []}
    return f


# --- verification --------------------------------------------------------------------------

def _num(token: str) -> float | None:
    t = re.sub(r"(?i)₹|rs\.?|,|%|\s", "", token)
    try:
        return float(t)
    except ValueError:
        return None


def allowed_numbers(f: dict) -> set[float]:
    """Every number in the fact sheet, plus the obvious forms a writer uses (rounded, %, lakh-free)."""
    out: set[float] = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool) or v is None:
            return
        elif isinstance(v, (int, float)):
            x = float(v)
            out.update({x, abs(x), round(x, 1), round(abs(x), 1), float(round(x)), float(round(abs(x)))})
        elif isinstance(v, str):
            for tok in NUMBER.findall(TIME.sub(" ", DATE.sub(" ", v))):
                x = _num(tok)
                if x is not None:
                    out.update({x, abs(x), round(abs(x), 1), float(round(abs(x)))})
    walk(f)
    return out


def check(text: str, f: dict) -> list[str]:
    """Problems in a model explanation; empty means it is safe to show."""
    problems = []
    if not text or len(text) < 40:
        return ["the answer is empty or too short"]
    if FORBIDDEN.search(text):
        problems.append(f"forbidden phrase: '{FORBIDDEN.search(text).group(0)}'")
    allowed = allowed_numbers(f)
    scrubbed = TIME.sub(" ", DATE.sub(" ", text))
    for tok in NUMBER.findall(scrubbed):
        x = _num(tok)
        if x is None or x in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100):   # counts and list markers
            continue
        if not any(math.isclose(abs(x), a, rel_tol=0.0005, abs_tol=0.005) for a in allowed):
            problems.append(f"number {tok.strip()} is not in the fact sheet")
    verdict = (f.get("risk") or {}).get("verdict")
    if verdict == "BLOCK" and re.search(r"\b(take|enter|buy|go ahead with) (this|the) trade\b", text, re.I) \
            and not re.search(r"\b(not|don'?t|do not|cannot|can'?t|should not|shouldn'?t)\b", text, re.I):
        problems.append("it encourages a trade the risk gate blocked")
    if verdict and verdict not in text.upper():
        problems.append(f"it does not state the risk verdict {verdict}")
    return list(dict.fromkeys(problems))


# --- deterministic fallback ----------------------------------------------------------------

def template(f: dict) -> str:
    """A plain explanation from the same facts, used when the model is off, unreachable or fails the checks."""
    lines = []
    s, p, o, z, r = (f.get(k) or {} for k in ("setup", "plan", "odds", "size", "risk"))
    if s:
        if s.get("state") == "triggered":
            lines.append(f"- Setup: {s.get('symbol')} {s.get('setup')} triggered {s.get('side')} at {s.get('trigger_price')}"
                         + (f" (bar closed {s['trigger_bar_closed_at']})" if s.get("trigger_bar_closed_at") else "")
                         + (f", {s['pct_beyond_level']}% beyond {s['level_broken']}" if s.get("level_broken") else "") + ".")
        else:
            lines.append(f"- Setup: {s.get('symbol')} {s.get('setup')} is {s.get('state')}.")
        if s.get("late_warning"):
            lines.append(f"- Late: {s['late_warning']}")
    if p:
        u = (f"; on the underlying, stop {p['underlying_stop']} and target {p['underlying_target']}"
             if p.get("underlying_stop") is not None else "")
        lines.append(f"- Plan: {p.get('instrument')} entry {p.get('entry')}, stop {p.get('stop')} ({p.get('stop_rule')}), "
                     f"target {p.get('target')} ({p.get('target_rule')}){u}; reward:risk {p.get('reward_to_risk')}, "
                     f"square off by {p.get('square_off')}.")
    if o:
        lines.append(f"- Odds: {o.get('verdict') or 'no verdict'} ({o.get('paths')} simulated paths, seed {o.get('seed')}, "
                     f"{o.get('sessions_sampled')} prior sessions).")
        if o.get("history"):
            lines.append(f"- {o['history']}")
    if z:
        lines.append(f"- Size: {z.get('units')} {z.get('unit')}(s); Rs {z.get('loss_at_stop_rs')} lost at the stop including "
                     f"charges, set by {z.get('decided_by')}.")
    if r:
        lines.append(f"- Risk: {r['verdict']}" + (": " + "; ".join(r["failed_rules"]) if r.get("failed_rules") else
                                                  ". Every rule passed; the decision is still yours."))
    lines.append("- What makes it wrong: price closing back through the stop level, or news and event risk the "
                 "simulation never saw.")
    return "\n".join(lines)


# --- entry point ---------------------------------------------------------------------------

def explain(f: dict, cfg: dict, chat: Callable[[list[dict], dict], str] | None = None, use_ai: bool = True) -> dict:
    """{reason, source: ai|template, model, problems, ...}. `chat` is injectable for tests."""
    s = settings(cfg)
    base = {"facts": f, "model": s["model"], "disclaimer": "Numbers come from the engine; the AI only explains them. "
            "Not investment advice. Nothing places orders."}
    if not (use_ai and s["enabled"]):
        return dict(base, reason=template(f), source="template", note="AI explanations are off")
    chat = chat or (lambda m, st: ollama_chat(m, st))
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "FACT SHEET (JSON):\n" + json.dumps(f, indent=1, ensure_ascii=False)
                 + "\n\nExplain this trade and its reason, following the rules."}]
    tried: list[list[str]] = []
    for _ in range(2):
        try:
            text = chat(messages, s)
        except AIError as exc:
            return dict(base, reason=template(f), source="template", note=str(exc))
        problems = check(text, f)
        if not problems:
            return dict(base, reason=text, source="ai", attempts=len(tried) + 1)
        tried.append(problems)
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Your answer broke the rules: " + "; ".join(problems)
                      + ". Rewrite it using only numbers copied from the FACT SHEET and state the risk verdict."}]
    return dict(base, reason=template(f), source="template",
                note="the model's answer failed the checks twice; showing the engine's explanation", rejected=tried)
