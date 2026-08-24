# Handover — Phase 7: Data Ingestion Pipeline

Self-contained. A new AI session can start from this file plus the repo; no chat history needed.

---

## PART A — Project Summary

**Project:** Pre-Competition Psychological Risk Profiling of Athletes.
Construct-grounded NLP that detects validated sports-psychology constructs in an athlete's
pre-competition text (interviews, press conferences, social posts, journals) and fuses them
into an interpretable 0–1 risk index with span-level explanations.

**Explicitly NOT** sentiment analysis and **NOT** clinical diagnosis. Research and
decision-support only.

**Owner:** Saikalyan, sophomore, SRMIST.
**Target:** IEEE full paper (iTriply Explore); draft by the 1st week of September 2026.
**Timeline:** 8 weeks; code frozen ~Week 7.

**Confirmed stack:** Python 3.11 · CrewAI · OpenRouter (cost-tier routing) · HuggingFace
transformers with DeBERTa/RoBERTa · scikit-learn baselines · SHAP · Streamlit · Docker · LaTeX.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, expert-validated
interpretability; (3) a time-aware, fusion-ready design.

**Governing documents:** `CLAUDE.md` (single source of truth) and `PROJECT_PLAN.md`
(25-phase blueprint). Read both before working.

### Phase status

| Phase | Status | Commit |
|---|---|---|
| 1 — Repo reset & scaffold | Complete | `fb87925` |
| 2 — Dev environment & tooling | **Complete — Docker gate MET 2026-08-09** (OPEN-001 resolved) | `07d77ab` + this session |
| 3 — Related work & novelty | Complete | `b104b8d` |
| 4 — Construct taxonomy | Complete | `d238721` |
| 5 — Ethics, data governance & risk plan | Complete | `a28b7ba` |
| **6 — Confirm decisions & wire agent framework** | **Complete** | **`b28873f`** (+ `ccba023` follow-up) |
| 7 — Data ingestion pipeline | **NEXT** | — |

**Carried-forward caveats:**

- **Phase 1 deviation:** no `legacy-backup` branch; the previous codebase was permanently
  deleted at the owner's instruction. Only `main` exists, no remote, no off-machine backup
  (OPEN-003).
- **Phase 3:** the key `Toth2025` is historical. László Tóth was the **handling editor**,
  not an author. Correct authors: Nogueira, Morais, Mansell & Gomes. Cite the correct
  authors in prose.

---

## PART B — Current Session Summary

Two pieces of work: finishing the outstanding **Phase 2 Docker gate**, then executing
**Phase 6** in full.

### B1. Phase 2 — the two failing Docker checks

**The stated problem** was that `verify_env.ps1` checks 7 (container build) and 8
(container hello-world) failed because Docker Desktop was not running.

**What was actually found.** The daemon being down was not the only problem. The old
`Dockerfile` ran `pip install -r requirements.txt`, and that manifest contained
`torch>=2.2`. On Linux the default PyPI wheel for torch is the **CUDA** build — roughly
2.5 GB plus a stack of `nvidia-*` CUDA runtime libraries that a CPU-only container never
loads. Estimated outcome: a ~6 GB image and a 30–60 minute build, with a real chance of
failing on disk space or a network timeout. Check 7 had never been exercised against a
real defect, exactly as the Phase 2 notes warned.

**Fixes applied:**

| Change | Reason |
|---|---|
| Split `Dockerfile` (light) + `Dockerfile.train` (heavy) | Phases 6–12 never pay the ML-stack cost |
| Split `requirements-base.txt` / `requirements-ml.txt` | mirrors the image split |
| torch from the PyTorch **CPU** wheel index | ~200 MB instead of ~2.5 GB |
| `train` service behind a Compose `profile` | plain `docker compose build` skips it |
| Shared `image:` name across app/agents/dashboard | compose builds once, not three times |
| `env_file: required: false` | a fresh clone with no `.env` no longer aborts compose |
| Dependency layer copied above source | code edits stop invalidating the pip cache |
| Non-root `appuser` (UID 1000) | image and secret hygiene |
| `docker info` replaces `docker --version` as check 2 | the old check passed with the daemon dead — that is why 7/8 failed while 2 passed |

**A bug I introduced and caught.** My first draft pinned `numpy>=1.26,<2.1`. Reading the
owner's actual venv showed **numpy 2.4.6** installed and working — the pin would have
forced a downgrade. Removed. Floors across both manifests were then reset to match the
versions actually installed on the owner machine, and `requirements.lock.txt` was created
(180 exact versions, captured from that venv; `pywin32` carries a `sys_platform` marker so
the lock also installs cleanly on Linux).

**Verified in the Linux sandbox** (no Docker binary there, so this is a proxy, not a
substitute): `requirements-base.txt` resolves with **zero dependency conflicts** — the
failure mode a build would most likely have hit next after the torch fix.

**New files:** `docs/docker.md` (runbook: why two images, daemon startup, WSL and
virtualization troubleshooting, everyday commands, five gotchas) and
`scripts/verify_docker.ps1` (focused re-run of checks 7/8 plus a daemon probe and an
in-container crew run).

### B2. Phase 6 — decisions confirmed and agent framework wired

**`config/model_routing.yaml` rewritten and locked (v2).**

The previous file had placeholder model IDs (`openrouter/<cheap-model-id>`). My first
draft replaced them with `openai/gpt-4o-mini`, `anthropic/claude-3.5-haiku` and
`anthropic/claude-sonnet-4` — and I wrote a comment claiming they were verified. They were
not. I then fetched the live OpenRouter catalogue and found **none of those three exist**.
Corrected to real, price-verified entries:

| Tier | Model | $/1M in | $/1M out |
|---|---|---|---|
| cheap | `openai/gpt-5.6-luna` | 0.10 | 0.60 |
| mid | `openai/gpt-5.6-terra` | 1.00 | 6.00 |
| premium | `anthropic/claude-sonnet-5` | 2.00 | 10.00 |

All three confirmed present in the live catalogue with exactly these prices, checked
programmatically. The config also carries the budget arithmetic that justifies tiered
routing: a 10,000-utterance labeling pass costs **~$1.12** on the cheap tier versus **~$20**
on premium — the entire monthly cap for one run.

**`src/agents/` built (6 modules, ~1,100 lines):**

- `config.py` — loads and **validates** routing + taxonomy at load time; a typo in a tier
  name stops the run immediately rather than surfacing as a `KeyError` three agents deep.
- `roster.py` — agent contracts per `CLAUDE.md` §4, plus `ETHICS_PREAMBLE` prepended to
  every agent's system prompt on every call.
- `ledger.py` — append-only CSV, thread-safe, **hard** monthly cap that raises rather than
  silently truncating a batch.
- `llm.py` — `OfflineLLM` (deterministic, seeded, free) and `OpenRouterLLM` behind one
  interface; handles ```json fences; pre-flight budget check before any paid call.
- `crew.py` — sequential orchestrator with confidence-triggered escalation and taxonomy
  validation.
- `crewai_engine.py` — optional CrewAI backend, isolated so nothing else imports crewai.

**`scripts/run_crew.py`** is the Phase 6 gate. **`scripts/refresh_pricing.py`** guards
against model/price drift.

### Key decisions made this session

1. **Offline is the default execution mode.** A reviewer reproducing the artifact should
   not need to buy API credit, and `pytest` must never be able to spend money. The stub
   still reports the token counts a live call *would* have used, so an offline run
   estimates a live run's cost before you commit to it.
2. **Two orchestration engines.** `simple` (built-in, verified, test-covered, offline) is
   the default; `crewai` is present because `CLAUDE.md` §10 confirms the framework. CrewAI
   went 0.x → 1.x during this project's lifetime, so keeping the contract in our own code
   means a breaking change cannot take down the pipeline.
3. **Escalation lives in the orchestrator, not the LLM client.** Phase 18 needs to ablate
   it, so the switch has to be somewhere it can be switched.
4. **The taxonomy guardrail is enforced in code, not requested in a prompt.** Every
   proposed label is checked against the ten locked construct keys; unknown constructs,
   out-of-range intensity, and out-of-range confidence all fail the task.
5. **Requirements floors match tested reality**, with upper bounds only at known breaking
   majors (`crewai<2.0`, `openai<3.0`, `transformers<6.0`).

### A real bug found by testing

The offline stub originally chose its response shape by sniffing the prompt for keywords.
The QA instruction contains "the **propos**ed label", which matched the labeling branch —
so the QA agent silently returned a *label proposal* instead of a *verdict*, and both
tasks escalated when only one should have. Fixed by declaring the expected shape
explicitly (`TaskSpec.kind`) and dispatching on that. There is a regression test.

### Verification performed

| Check | Result |
|---|---|
| `ruff check` on `src/ scripts/ tests/` | **All checks passed** |
| `ruff format --check` | 22 files already formatted |
| `pytest tests/test_agents.py` | **26/26 pass** |
| Full suite | 42/43 — the one failure is `test_python_version_is_311` under the sandbox's 3.10, which is the test working correctly |
| All 4 `config/*.yaml` + `docker-compose.yml` | parse as valid YAML |
| Phase 6 gate `run_crew.py` | **PASSED**, 3 ledger rows written |
| Offline determinism | same seed → identical output, confirmed |
| Escalation path | fires on 9 of 14 seeds; ledgered with the reason |
| Taxonomy guardrail | rejects an invented construct, out-of-range intensity, malformed JSON |
| Live-without-key | fails cleanly with an actionable message, exit 2 |
| `requirements-base.txt` | resolves on Linux with zero conflicts |
| Model IDs + prices | verified against the live OpenRouter catalogue |
| Secret scan | clean; the only match is the deliberately fake key in `docs/setup.md` carrying `# pragma: allowlist secret` |
| `.env` tracked by git | no |

**Sandbox caveat:** the sandbox runs Python 3.10, the project pins 3.11. `datetime.UTC`
(3.11+) is used in `ledger.py`, correct for the project. Tests were run with a shim
backfilling that alias. **Re-run `pytest` on your 3.11 machine to confirm natively** —
expect 43/43.

### Files changed

| File | Change |
|---|---|
| `Dockerfile` | rewritten — light image |
| `Dockerfile.train` | **new** — heavy ML image |
| `docker-compose.yml` | rewritten — 4 services, profiles, optional env_file |
| `requirements-base.txt` | **new** |
| `requirements-ml.txt` | **new** |
| `requirements.lock.txt` | **new** — 180 exact versions |
| `requirements.txt` | now a pointer to both layers |
| `config/model_routing.yaml` | rewritten and locked (v2), prices verified |
| `src/agents/{config,roster,ledger,llm,crew,crewai_engine}.py` | **new** |
| `src/agents/__init__.py` | public API |
| `scripts/run_crew.py` | **new** — the Phase 6 gate |
| `scripts/refresh_pricing.py` | **new** — drift guard |
| `scripts/verify_docker.ps1` | **new** |
| `scripts/verify_env.ps1` | updated — daemon probe, crew check |
| `tests/test_agents.py` | **new** — 26 tests |
| `docs/docker.md` | **new** |
| `docs/agents.md` | **new** |
| `docs/open_issues.md` | OPEN-001 updated; OPEN-007/008/009 added |
| `README.md` | layered install, cost-control section |
| `.env.example` | documented all keys |

### Blockers and unresolved issues

> **`docs/open_issues.md` is the single source of truth.** Read it before planning.

**BLOCKER — the work is not committed.** `.git/index.lock` exists and the sandbox cannot
delete it (`Operation not permitted`). All changes are on disk and verified but the tree
is dirty. **Delete `C:\Users\x\sports-risk-nlp\.git\index.lock`**, then:

```powershell
cd C:\Users\x\sports-risk-nlp
del .git\index.lock
.\.venv\Scripts\Activate.ps1
pytest                              # expect 43/43 on 3.11
python scripts\run_crew.py          # expect: Phase 6 gate PASSED
pre-commit run --all-files
git add -A
git commit -m "Phase 2 fix + Phase 6: layered Docker images, cost-aware agent framework, offline-first smoke crew"
```

**Open items, by urgency:**

- ~~**OPEN-001** Docker gate~~ — **RESOLVED 2026-08-09.** Docker Desktop started;
  `verify_env.ps1` checks 1–9 pass including container build and container hello-world.
  First successful build the `Dockerfile` has ever had.
- ~~**OPEN-010** detect-secrets false positive on `api_key_env`~~ — **RESOLVED
  2026-08-09** with an inline `# pragma: allowlist secret` and a stated justification.
- **OPEN-008** No `OPENROUTER_API_KEY` in `.env` (only `YOUTUBE_API_KEY`). Blocks
  **Phase 10**, not Phase 7–9.
- **OPEN-007** The CrewAI backend is written but never executed. Run
  `python scripts/run_crew.py --engine crewai --live` once a key exists (~$0.01).
- **OPEN-009** Model IDs and prices drift silently. Run `refresh_pricing.py --check`
  before any large batch.
- **OPEN-004** Expert-rater recruitment **still not started.** `PROJECT_PLAN.md` risk #4
  says Week 1–2; it is now Week 3. This is the headline contribution of the paper and the
  item with the longest lead time and least control. **This is the highest-value thing you
  could do today that is not code.**
- **OPEN-005** Ethics exemption not in writing — blocks submission, not Phase 7.
- **OPEN-006** Withdrawal contact is a personal address — blocks public release.
- **OPEN-003** No off-machine backup. Every artifact exists in one place on one machine.
  A private remote would close this in minutes.
- **OPEN-002** Broken pixeltable plugin hook, cosmetic, fires on every file write.

---

## PART C — Phase 7 Brief

**Objective (from `PROJECT_PLAN.md`):** Get raw text in with provenance **and lightweight
temporal/context metadata**.

**Owning agent:** Harvester Agent (cheap tier). Its contract is already defined in
`src/agents/roster.py` as `HARVESTER`.

**Tasks:**

1. Implement `src/ingestion/`. Each source writes a `provenance.json` recording source,
   date, and licence.
2. **Respect the Phase 5 allow-list** in `config/data_sources_allowlist.yaml`. Ingestion
   must refuse anything not on it. This is a hard rule, not a guideline.
3. **Capture timing relative to the competition** (e.g. `time_to_competition` in days) and
   light context (sport, level, training-load hints) as optional, nullable metadata. This
   makes the corpus temporal- and fusion-ready without committing to those models now —
   it is contribution #3 and it is cheap to record now and impossible to backfill later.
4. Data strategy is **existing public/licensed datasets first** (`CLAUDE.md` §10, Q3), with
   a hybrid synthetic-plus-small-real-gold-set fallback. §10 says to revisit that fallback
   at Phase 7 — **so revisit it explicitly and ask the owner** if coverage looks thin.

**Deliverable:** `data/raw/` populated, with provenance plus optional
`time_to_competition` / context fields.

**Gate:** Every raw record traceable to a licensed/consented/synthetic source; temporal and
context fields present where the source allows, nullable otherwise.

**Inputs to read first:** `CLAUDE.md` §1 and §10; `PROJECT_PLAN.md` Phase 7–8;
`config/data_sources_allowlist.yaml`; `docs/ethics.md` (consent, licensing, and the
de-identification policy Phase 8 will implement); `docs/agents.md` (how to wire a new agent
into the existing framework); `src/agents/roster.py` (`HARVESTER`).

**Constraints:**

- De-identification is **Phase 8**, but Phase 7 must not write anything to `data/raw/` that
  the allow-list forbids. When in doubt, ask before ingesting.
- `data/gold/` is human-owned. Agents never write there.
- Ask the owner before locking any data source that constrains later acquisition.
- Reuse the Phase 6 agent layer rather than building a parallel one — `build_llm`,
  `CostLedger`, and the `Crew` orchestrator are all in place and tested.

**Do not start Phase 8.**

---

## Commit status

**RESOLVED 2026-08-09. Working tree clean.**

| Commit | Contents |
|---|---|
| `b28873f` | The Phase 2 fix + Phase 6 work — 26 files, +3,600 / −72 |
| `ccba023` | Follow-up: `.pre-commit-config.yaml` auto-fix (1 line) |

The stale `.git/index.lock` that blocked the commit was cleared on the owner machine.
Pre-commit ran clean on the way in: trailing whitespace, end-of-files, check-yaml,
merge-conflict, large-files, detect-private-key, ruff, ruff-format and detect-secrets all
passed.

*Cosmetic:* both commits carry the same message. Harmless. If you want it tidy,
`git rebase -i HEAD~2` and squash, or `git commit --amend` the second one's message —
but only while nothing is pushed, and there is still no remote (OPEN-003).
