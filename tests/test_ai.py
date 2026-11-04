"""AI explanations: the model may only repeat the engine's numbers. A fake model stands in for Ollama."""

import json

import pytest

from idt import ai
from idt.config import DEFAULTS

FACTS = ai.facts(
    {"symbol": "NIFTY", "setup": "orb", "state": "triggered", "side": "long", "entry": 25995.0,
     "trigger_close": "2026-10-29T09:40:00+05:30", "trigger_level": 25985.0, "pct_beyond": 0.04,
     "range": {"high": 25985.0, "low": 25905.0}},
    {"contract": "NIFTY 2026-11-03 26000 CE", "kind": "option", "side": "long", "basis": "underlying",
     "entry": 156.87, "stop": 132.0, "target": 199.15, "stop_rule": "or-mid", "target_rule": "1.5R", "rr": 1.7,
     "risk_per_unit": 1616.55, "reward_per_unit": 2748.1, "unit": "lot", "lot_size": 65, "squareoff": "15:15",
     "underlying_stop": 25945.0, "underlying_target": 26070.0},
    {"monte_carlo": {"paths": 10000, "seed": 42, "sessions_sampled": 59, "p_target": 0.394, "p_stop": 0.606,
                     "p_flat": 0.0, "p_green": 0.394, "expected_r": 0.046},
     "verdict": "Close to break-even: at 1.7R the target has to come first in 37% of the paths; it did in 39%.",
     "replay_line": "History: fired 29 times: 12 target, 17 stop."},
    {"units": 1, "unit": "lot", "legs": [{"quantity": 65}], "loss_at_stop": 1684.71, "profit_at_target": 2672.0,
     "charges": {"if_stopped": 68.16}, "margin": {"total": 3200}, "decided_by": "max_loss", "rr": 1.7},
    {"verdict": "PASS", "reasons": []})

GOOD = """- Setup: NIFTY broke its opening range high of 25,985 and the 09:40 close was 25,995.
- Plan: buy the 26000 CE at 156.87, stop 132.00 (NIFTY 25,945), target 199.15 (NIFTY 26,070), reward:risk 1.7.
- Odds: close to break-even; target first 39.4% vs stop first 60.6% over 10,000 paths.
- Size: 1 lot of 65, Rs 1,684.71 at risk including charges.
- Risk verdict: PASS. It is wrong if NIFTY closes back below 25,945."""


def cfg(**ai_kw):
    return dict(DEFAULTS, ai=dict(DEFAULTS["ai"], **ai_kw))


def fake(*answers):
    calls = []

    def chat(messages, settings):
        calls.append(messages)
        return answers[min(len(calls) - 1, len(answers) - 1)]
    chat.calls = calls
    return chat


def test_verified_model_text_is_used():
    out = ai.explain(FACTS, cfg(), chat=fake(GOOD))
    assert out["source"] == "ai" and out["reason"] == GOOD and out["attempts"] == 1


def test_invented_number_is_rejected_then_retried():
    bad = GOOD.replace("199.15", "205.40")
    chat = fake(bad, GOOD)
    out = ai.explain(FACTS, cfg(), chat=chat)
    assert out["source"] == "ai" and out["attempts"] == 2
    assert "205.40" in chat.calls[1][-1]["content"]          # the retry names the bad number


def test_two_failures_fall_back_to_the_engine_template():
    out = ai.explain(FACTS, cfg(), chat=fake(GOOD + "\n- This is a guaranteed winner."))
    assert out["source"] == "template" and "guaranteed" in out["rejected"][0][0]
    assert ai.check(out["reason"], FACTS) == []              # the template itself passes the same checks


def test_block_verdict_must_be_stated_and_respected():
    blocked = dict(FACTS, risk={"verdict": "BLOCK", "failed_rules": ["reward:risk: 0.64, under the minimum 1"]})
    assert any("risk verdict" in p for p in ai.check(GOOD, blocked))
    push = GOOD.replace("PASS", "BLOCK") + "\n- Go ahead and take this trade anyway."
    assert any("blocked" in p for p in ai.check(push, blocked))


def test_rounded_forms_and_times_are_allowed():
    text = "- NIFTY 26000 CE: stop 132, target 199.2, target first 39%; risk verdict PASS at 09:40 on 2026-10-29."
    assert ai.check(text, FACTS) == []


def test_thinking_is_stripped():
    assert ai.strip_thinking("<think>2+2=5 so...</think>\n- answer") == "- answer"
    assert ai.strip_thinking("leftover reasoning</think>- answer") == "- answer"


def test_disabled_or_unreachable_uses_template(monkeypatch):
    off = ai.explain(FACTS, cfg(enabled=False))
    assert off["source"] == "template" and off["note"] == "AI explanations are off"

    def down(messages, settings):
        raise ai.AIError("Ollama is not reachable")
    assert ai.explain(FACTS, cfg(), chat=down)["source"] == "template"


class FakeResp:
    def __init__(self, code, payload):
        self.status_code, self._p, self.text = code, payload, json.dumps(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, *resps):
        self.resps, self.bodies = list(resps), []

    def post(self, url, json=None, timeout=None):
        self.bodies.append(json)
        return self.resps.pop(0)


def test_ollama_chat_request_and_old_server_fallback():
    s = ai.settings(cfg())
    sess = FakeSession(FakeResp(400, {"error": "invalid option: think"}),
                       FakeResp(200, {"message": {"content": "<think>x</think>- ok answer"}}))
    assert ai.ollama_chat([{"role": "user", "content": "hi"}], s, sess) == "- ok answer"
    first, second = sess.bodies
    assert first["model"] == "deepseek-r1:1.5b" and first["stream"] is False and first["think"] is True
    assert first["options"]["temperature"] == 0.3 and "think" not in second
    with pytest.raises(ai.AIError, match="ollama pull"):
        ai.ollama_chat([], s, FakeSession(FakeResp(404, {"error": "model not found"})))


def test_env_overrides_model_and_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "ollama:11434")
    monkeypatch.setenv("IDT_AI_MODEL", "idt-trader")
    s = ai.settings(cfg())
    assert (s["host"], s["model"], ai._host(s["host"])) == ("ollama:11434", "idt-trader", "http://ollama:11434")


def test_explain_end_to_end_on_fixtures(cli, ws):
    import json as _json
    cli("init")
    c = _json.loads((ws / "config.json").read_text())
    c["max_loss_per_trade"] = 3000
    (ws / "config.json").write_text(_json.dumps(c))
    cli("entry", "check", "NIFTY", "--write")
    cli("exit", "plan", "--write")
    code, out = cli("explain", "--no-ai")
    assert code == 0 and out["source"] == "template" and "25995" in out["reason"]
    assert out["facts"]["plan"]["entry"] == 156.87 and out["facts"]["odds"]["paths"] == 2000
