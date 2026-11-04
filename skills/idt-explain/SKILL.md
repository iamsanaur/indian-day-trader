---
name: idt-explain
description: >-
  Trade Reason. Explains why a planned Indian trade looks the way it does: the trigger, the plan, the
  Time Machine odds, the size and the risk verdict, in plain bullet points. Worded by a local Ollama
  model (DeepSeek-R1 1.5B by default) from a fact sheet the engine computed; every number in the
  model's text is checked against that sheet, and anything unverified falls back to the engine's own
  explanation. Use when the user asks "why this trade", "explain the trade", "give me the reason",
  "what does the AI think", or before /idt-broker shows a ticket.
argument-hint: "[--no-ai]"
---

# Trade Reason (`/idt-explain`)

The reason for a trade must never be more confident or more precise than the numbers behind it. So
the work is split: the engine computes everything (trigger, stop, target, odds, size, charges,
PASS/BLOCK) and the local model only puts those facts into words. A 1.5B model gets arithmetic wrong
often enough that it must never size, price or gate a trade. Here it never does.

```bash
idt explain                     # local model, verified; engine explanation if Ollama is off or the check fails
idt explain --no-ai             # the engine's explanation only
idt ticket show --reason        # the ticket plus the reason
idt ai status                   # is Ollama reachable, is the model pulled
```

## What it reads

| source | what |
| --- | --- |
| `idt/setup.json`, `idt/plan.json` | the trigger and the plan |
| `idt/timemachine.json` | the odds and verdict, if saved for this plan; otherwise a quick 2,000-path run |
| `idt/orders.json`, `idt/risk.json` | size and the verdict, only if they match the current plan and order hash |
| Ollama | `OLLAMA_HOST` (default `http://127.0.0.1:11434`), model `IDT_AI_MODEL` or `ai.model` (`deepseek-r1:1.5b`) |

## How the reason is checked

1. **Fact sheet.** The engine's numbers go to the model as JSON with strict rules: copy numbers, never
   calculate, the risk verdict is final, never promise profit. The model's hidden `<think>` text is dropped.
2. **Number check.** Every number in the answer must be in the fact sheet (or a plain rounding of one).
   Times, dates and small counts are allowed.
3. **Phrase check.** "guaranteed", "risk-free", "sure shot", "can't lose" and similar are rejected.
4. **Verdict check.** The answer must state the risk verdict, and may not encourage a trade the gate blocked.
5. **One retry** with the problems listed, then the **engine's explanation** if it still fails.

`source` says which one you got: `ai` (verified model text) or `template` (the engine's), with a
`note` on why (Ollama off, model missing, failed checks).

## Setup (once)

```bash
ollama pull deepseek-r1:1.5b
ollama create idt-trader -f deploy/ollama/Modelfile     # optional: low temperature, fixed seed
# then "ai": {"model": "idt-trader"} in idt/config.json, or IDT_AI_MODEL=idt-trader
```

Docker: `docker compose --profile ai up -d`, then
`docker compose exec ollama ollama pull deepseek-r1:1.5b` (and optionally
`docker compose exec ollama ollama create idt-trader -f /modelfiles/Modelfile`). It runs on CPU; a
reason takes from a few seconds to a minute depending on the machine.

## Steps

1. Run it after `/idt-risk`, so the reason includes the size and the verdict (it also works earlier).
2. Show the bullets as returned. Say whether they came from the model (`ai`) or the engine (`template`),
   and pass on the `note` if there is one.
3. Never add numbers of your own to the reason, and never soften a BLOCK or a "toward the stop" verdict.
4. Then `/idt-broker` if the user wants the ticket.

## What it never does

It never changes a number, a plan or a verdict, never picks a trade, never places an order, and never
shows model text that failed the checks.

## Safety

- Education and tooling, not investment advice. A PASS is a rules check, not a recommendation.
- The model runs locally; the fact sheet never leaves the machine.
- Nothing in this pack places an order. `/idt-broker` builds a ticket only after `/idt-risk` passed that
  exact order hash in the last 10 minutes and the user typed yes for that hash; the user places it themselves.
- Dhan credentials live in environment variables. Never store or repeat the user's TOTP.
