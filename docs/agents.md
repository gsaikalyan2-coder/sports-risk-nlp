# The agent layer (Phase 6)

How the multi-agent pipeline is wired, why it is wired that way, and how to run it.
Written 2026-08-09. Companion to `config/model_routing.yaml` and `CLAUDE.md` §4–5.

---

## 1. Run it

```bash
python scripts/run_crew.py                 # offline, free, deterministic (default)
python scripts/run_crew.py --live          # real OpenRouter calls
python scripts/run_crew.py --seed 4        # different offline draw
python scripts/run_crew.py --show-ledger   # what has been spent
python scripts/refresh_pricing.py --check  # are the model IDs and prices still real?
```

In Docker:

```bash
docker compose run --rm agents                                  # offline
docker compose run --rm agents python scripts/run_crew.py --live
```

A passing run ends with `Phase 6 gate: PASSED`.

---

## 2. What the pieces are

```
config/model_routing.yaml        cost tiers, budget cap, escalation policy
config/taxonomy.yaml             the 10 locked constructs (Phase 4)
        │
        ▼
src/agents/config.py             loads + VALIDATES both, fails loudly
src/agents/roster.py             agent contracts; ethics preamble
src/agents/ledger.py             append-only cost CSV + hard monthly cap
src/agents/llm.py                OfflineLLM | OpenRouterLLM behind one interface
src/agents/crew.py               sequential orchestrator + escalation + validation
src/agents/crewai_engine.py      optional CrewAI backend (live only, UNVERIFIED)
        │
        ▼
scripts/run_crew.py              the Phase 6 gate
logs/cost_ledger.csv             one row per model call
```

---

## 3. Five design decisions worth defending in the paper

### 3.1 Offline is the default

The default run makes no network call, needs no API key, and costs nothing. A
deterministic stub LLM, seeded from the prompt, produces well-formed synthetic
answers.

This is not a convenience. `CLAUDE.md` §9 makes a reproducible artifact part of
"publication-ready", and an artifact a reviewer cannot run without buying API
credit is not reproducible in any useful sense. It also means `pytest` can never
accidentally spend money.

The stub reports the token counts a real call *would* have used, so an offline
run tells you what a live run would cost before you commit to it.

### 3.2 Cost tiers, and the arithmetic that justifies them

Three tiers. Bulk work goes to the cheap one; only low-confidence cases escalate.

For a 10,000-utterance labeling pass at ~400 input and ~120 output tokens each:

| Tier | Model | Estimated pass cost |
|---|---|---|
| cheap | `openai/gpt-5.6-luna` | **~$1.12** |
| premium | `anthropic/claude-sonnet-5` | ~$20 - the entire monthly cap |

That ratio is the whole argument for tiered routing, and it is a real number
rather than a claim.

### 3.3 The budget cap is a hard stop

When a call would push month-to-date spend past the cap, the ledger raises
instead of trimming the batch.

A job that dies with a clear message is recoverable. A labeling run that quietly
processed 6,000 of 10,000 utterances produces a corrupted dataset that may not be
noticed until the results look strange weeks later - by which point the cause is
buried. Loud failure is the cheaper error.

### 3.4 Escalation is an orchestration decision, not a model decision

If a cheap-tier answer reports confidence below `escalation.confidence_threshold`
(currently 0.65), the orchestrator re-runs it one tier up, once, and writes both
calls to the ledger with the reason.

It lives in `crew.py` rather than inside the LLM client because Phase 18 needs to
ablate it - "with vs. without escalation" is a result, so the switch has to be
somewhere it can be switched.

**The 0.65 threshold is a starting value, not an evidence-backed one.** Phase 10
calibrates it against the gold set and Phase 18 should report sensitivity to it.

### 3.5 The taxonomy guardrail is enforced in code

`CLAUDE.md` §3 says agents must never invent constructs. That is enforced, not
merely requested: every proposed label is checked against the ten keys in
`config/taxonomy.yaml`, and an unknown construct fails the task. Intensity outside
0–3 and confidence outside [0, 1] fail too.

A rule stated only in a prompt is a suggestion. This one is a check.

---

## 4. Ethics is in the prompt, every time

`roster.ETHICS_PREAMBLE` is prepended to every agent's system prompt on every
call:

1. You label **language, not people**. Never diagnose.
2. You never invent constructs.
3. Research and decision support, not clinical assessment. Report uncertainty
   rather than resolving it with a guess.

A test asserts this text is present for every agent in the roster, so it cannot
be dropped by accident. The smoke-test utterance is synthetic - written for the
test, not taken from any real athlete.

---

## 5. Two engines, and which to use

| | `simple` (default) | `crewai` |
|---|---|---|
| Status | **verified**, test-covered | written, **never executed** (OPEN-007) |
| Offline | yes | no - real calls only |
| Cost rows | one per call | one coarse summary row |
| Depends on | nothing external | crewai 1.15.x |

`CLAUDE.md` §10 confirms CrewAI as the framework, so the integration lives in the
repo. But CrewAI went 0.x → 1.x during this project's lifetime, and keeping the
*contract* in our own code means a future breaking change cannot take down the
pipeline. Only `crewai_engine.py` imports crewai; nothing else does.

**For Phase 10 bulk labeling, prefer `simple`** - CrewAI calls the provider
itself, so per-record cost attribution is not available through it, and that
attribution is what the cost analysis in the paper rests on.

---

## 6. Adding an agent

1. Add an `AgentSpec` in `src/agents/roster.py` and register it in `ROSTER`.
2. Add its default tier to `agent_defaults` in `config/model_routing.yaml`.
3. Add a `TaskSpec` where it is used, declaring `kind` (`label`, `verdict`, or
   `prose`) and `expects_json`.

`kind` declares the expected answer shape explicitly. Do not infer it from prompt
text - the offline stub originally sniffed for the word "propose", which also
matches "the propos**ed** label" in the QA instruction, so the QA step silently
returned a label proposal instead of a verdict. There is a regression test for
exactly that.
