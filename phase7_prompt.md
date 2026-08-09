You are continuing a multi-phase research-engineering project. Read `CLAUDE.md` (the standing brief and single source of truth) and `PROJECT_PLAN.md` (the 25-phase blueprint) in the connected folder `C:\Users\saika\sports-risk-nlp` before doing any work. Also read `phase7_handover.md`, `docs/open_issues.md`, `docs/ethics.md`, `config/data_sources_allowlist.yaml`, and `docs/agents.md`. Your job this session is **Phase 7 only**. Do not start Phase 8.

## Context — where the project stands

**Project:** *Pre-Competition Psychological Risk Profiling of Athletes.* Construct-grounded NLP that detects validated sports-psychology constructs (cognitive/somatic anxiety, self-confidence, motivation orientation, perceived stress, attentional focus, burnout, coping style, resilience, appraisal orientation) in an athlete's pre-competition text and fuses them into an interpretable 0–1 risk index with span-level explanations. NOT sentiment analysis; NOT clinical diagnosis. Owner: Saikalyan, sophomore at SRMIST. Target: IEEE full paper (iTriply Explore), draft by the 1st week of September 2026. Confirmed stack: Python 3.11, CrewAI, OpenRouter (cost-tier routing), DeBERTa/RoBERTa via HuggingFace, scikit-learn baselines, SHAP, Streamlit, Docker, LaTeX.

**Phase 1 (repo reset & scaffold) — complete** (`fb87925`). One documented, owner-authorised deviation: no `legacy-backup` branch was created — the previous codebase was permanently deleted at the owner's instruction. Only `main` exists and there is still no off-machine backup (OPEN-003).

**Phase 2 (dev environment & tooling) — complete** (`07d77ab`, hardened in `b28873f`). Docker was found to have a second defect beyond the daemon being down: the original `Dockerfile` installed `torch` from the default PyPI index, which on Linux is the CUDA build (~2.5 GB plus `nvidia-*` runtime libraries, a ~6 GB image). Fixed by splitting into a light `Dockerfile` (agents, dashboard, dev tools) and a `Dockerfile.train` (CPU-only torch, behind a Compose `train` profile), with matching `requirements-base.txt` / `requirements-ml.txt` and a `requirements.lock.txt` of 180 exact versions. Full runbook in `docs/docker.md`.

**Phase 3 (related work & novelty) — complete** (`b104b8d`). `docs/related_work.md` holds the gap statement, five thematic sections, the three-part contribution, and a References table where all domain sources resolve to primary publisher records with DOIs. `paper/refs.bib` has 30 entries whose keys match the docs exactly. Important: `Toth2025` was mis-attributed by the original secondary source — the real authors are Nogueira, Morais, Mansell & Gomes; Tóth was the handling editor. The key is retained for stability; cite the correct authors in prose.

**Phase 4 (construct taxonomy) — complete** (`d238721`). `config/taxonomy.yaml` is locked at v2: 10 constructs plus an `interpretation_modifier`, each with definition, instrument anchor, `risk_direction`, ≥2 positive and ≥2 negative examples, edge cases, and label type. `docs/annotation_guidelines.md` is a complete annotator rubric. The construct set is formally frozen at Phase 12, not now.

**Phase 5 (ethics, data governance & risk plan) — complete** (`a28b7ba`). `docs/ethics.md` covers consent and licensing, the de-identification policy Phase 8 will implement, the non-diagnosis framing, misuse and bias risks. `config/data_sources_allowlist.yaml` (v1.1) defines which categories of text are permitted and which are forbidden. **Phase 7 ingestion must respect this allow-list.**

**Phase 6 (confirm decisions & wire agent framework) — complete** (`b28873f`). This is the layer you will build on:

- `config/model_routing.yaml` v2 locked with three real, price-verified OpenRouter tiers: cheap `openai/gpt-5.6-luna` ($0.10/$0.60 per 1M), mid `openai/gpt-5.6-terra` ($1.00/$6.00), premium `anthropic/claude-sonnet-5` ($2.00/$10.00). `python scripts/refresh_pricing.py --check` validates these against the live catalogue and passed on 2026-08-09 against 400 models.
- `src/agents/` — `config.py` (loads and validates routing + taxonomy, fails loudly), `roster.py` (agent contracts + an `ETHICS_PREAMBLE` prepended to every system prompt), `ledger.py` (append-only cost CSV with a hard $20/month cap that raises rather than truncating a batch), `llm.py` (`OfflineLLM` deterministic/free and `OpenRouterLLM` behind one interface), `crew.py` (sequential orchestrator with confidence-triggered tier escalation and taxonomy validation), `crewai_engine.py` (optional CrewAI backend, isolated).
- `scripts/run_crew.py` is the Phase 6 gate and passes offline: `python scripts/run_crew.py` → 3-agent run, deterministic, $0.00, logged to `logs/cost_ledger.csv`.
- 26 tests in `tests/test_agents.py`, all passing; ruff clean.
- **Offline is the default execution mode by design** — a reviewer reproducing the artifact must not need an API key, and `pytest` must never be able to spend money.

**The Harvester Agent contract already exists** in `src/agents/roster.py` as `HARVESTER` (cheap tier; reads `config/data_sources_allowlist.yaml`; writes `data/raw/` and `data/interim/`; phases 7–8). Reuse it. Do not build a parallel agent layer.

**Open issues you must read before planning** (`docs/open_issues.md` is the single source of truth): OPEN-003 no off-machine backup; OPEN-004 expert-rater recruitment not started and now overdue; OPEN-005 ethics exemption not in writing (blocks submission, not Phase 7); OPEN-006 withdrawal contact is a personal address (blocks public release); OPEN-007 CrewAI backend written but never executed; OPEN-008 no `OPENROUTER_API_KEY` in `.env` (blocks Phase 10, not Phase 7); OPEN-009 model/price drift monitoring.

## Phase 7 — objective, tasks, acceptance gate

**Objective (from `PROJECT_PLAN.md`):** Get raw text in with provenance **and lightweight temporal/context metadata**. This is the first phase that touches real data, so the governance work from Phase 5 stops being theoretical.

**Owning agent:** Harvester Agent (cheap tier).

**Tasks:**

1. **Before writing any code, resolve the data-strategy question with the owner.** `CLAUDE.md` §10 Q3 confirms "existing public/licensed datasets first", with a hybrid synthetic-plus-small-real-gold-set fallback, and explicitly says to *revisit that fallback at Phase 7*. So revisit it. Survey what is actually available and licence-compatible against `config/data_sources_allowlist.yaml`, report honestly on coverage, and **ask the owner to choose** before ingesting anything. Do not silently pick a source.

2. **Implement `src/ingestion/`.** Each source writes a `provenance.json` recording at minimum: source name, URL or dataset identifier, licence, access date, and the allow-list category it satisfies. A record without provenance must be impossible to create, not merely discouraged.

3. **Enforce the allow-list in code, not in a comment.** Ingestion must refuse any source not on `config/data_sources_allowlist.yaml`. Follow the pattern already used for the taxonomy guardrail in `src/agents/crew.py`, where an invented construct fails the task rather than producing a warning.

4. **Capture time-awareness while it is still possible.** Where the source allows, record `time_to_competition` (e.g. days before the event) and light context (sport, competition level, training-load or physiological hints) as optional, nullable metadata fields. This is contribution #3 in the paper and it is cheap to record now and impossible to backfill later. Sparse is fine; absent is not, where the source has it.

5. **Write `docs/data_sources.md`** documenting every source actually ingested: what it is, its licence, how many records, what temporal and context fields it does and does not carry, and any known bias in it (sport, gender, language, era). The paper's dataset section will be built from this.

6. **Tests.** Follow the Phase 6 pattern: offline, deterministic, no network in the test path. At minimum, cover that a disallowed source is rejected, that a record cannot be written without provenance, and that nullable temporal fields round-trip correctly.

7. **Do NOT write to `data/gold/`** — that directory is human-owned. Do not implement de-identification; that is Phase 8. But do not ingest anything the allow-list forbids on the grounds that Phase 8 will clean it later.

**Acceptance gate — Phase 7 counts as done when:**

- Every raw record in `data/raw/` is traceable to a licensed, consented, or synthetic source, with `provenance.json` present.
- Temporal and context fields are present where the source allows and explicitly null otherwise.
- A source not on the allow-list is rejected by code, demonstrated by a passing test.
- `docs/data_sources.md` documents every ingested source with licence and known bias.
- `pytest` passes and `ruff check` is clean.
- The working tree is committed and clean.

## How to work

- **Ask before assuming.** The data-strategy decision in task 1 is the owner's, not yours. So is any choice that constrains later acquisition. If coverage looks thin, say so plainly and present the options rather than quietly falling back to synthetic data.
- **Never fabricate.** No invented dataset names, licence terms, URLs, or record counts. If something cannot be verified, mark it `[UNVERIFIED]` and say what you tried. An honest gap is recoverable; a fabricated source in a paper is not.
- **Verify, don't assert.** Run the code you write. Check licences against the actual source page rather than from memory. In the last session, three OpenRouter model IDs that "looked right" turned out not to exist — checking caught it. Apply the same standard here.
- **Teach while doing.** The owner is a sophomore; explain why before how, and define jargon once.
- **Be concise and direct in chat**; put depth in the files.
- **Small, verifiable steps**, and end with a verification step.
- **Ethics is mandatory and must survive into the paper:** research and decision-support only, de-identified data, no mental-health claims about real named individuals. If a source would require claims about identifiable people, it does not belong in this corpus regardless of how convenient it is.
- **Never commit secrets.** Keys live only in `.env`, which is gitignored and excluded from Docker images. Pre-commit hooks including `detect-secrets` are active and passing; run `pre-commit run --all-files` before committing.
- If git reports a stale `.git/index.lock`, tell the owner to delete it — the sandbox cannot. This happened last session; the fix is `Remove-Item -LiteralPath ".git\index.lock" -Force` in PowerShell after killing any stray `git` processes, and closing VS Code if it persists.

## Deliverable format

- `src/ingestion/` — implemented, allow-list-enforcing, provenance-writing.
- `data/raw/` — populated, each source with `provenance.json`.
- `docs/data_sources.md` — per-source documentation including licence and known bias.
- `tests/test_ingestion.py` — offline, deterministic.
- `docs/open_issues.md` — updated with anything newly discovered.
- A commit with a clear message and a clean working tree.
- A concise chat summary: what was ingested, what was rejected and why, what remains open.
- **A `phase8_handover.md`** in the established Parts A / B / C format (project summary, current-session summary, next-phase brief), self-contained so a new session can continue without chat history.

**Do not proceed to Phase 8 until the owner confirms receipt of the handover file.**
