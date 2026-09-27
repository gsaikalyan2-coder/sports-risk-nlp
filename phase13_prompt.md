# Phase 13 - ready-to-paste prompt

Copy everything below the line into a fresh session.

---

You are continuing work on an existing research codebase. **Read `CLAUDE.md`, `PROJECT_PLAN.md`,
`phase12_handover.md` and `docs/open_issues.md` before writing any code.** They are the single
source of truth and they override anything in this prompt that contradicts them.

## 1. The project

**Pre-Competition Psychological Risk Profiling of Athletes** - construct-grounded NLP that
detects validated sports-psychology constructs in an athlete's *pre-competition* text
(interviews, pressers, journals) and fuses them into an interpretable 0–1 risk index with
span-level explanations.

It is **not** sentiment analysis and **not** clinical diagnosis. Research and decision-support
only; `docs/ethics.md` is binding on every phase. Never infer a real named person's mental
health.

- **Owner:** Saikalyan, sophomore, SRMIST. Teach while doing; explain *why* before *how*.
- **Target:** IEEE full paper (iTriply Explore), draft by the 1st week of September 2026.
  8-week timeline, code frozen ~Week 7. It is currently **Week 4**.
- **Stack (locked):** Python 3.11 · CrewAI · OpenRouter (cost-tier routing) · HuggingFace
  transformers with DeBERTa/RoBERTa · scikit-learn · SHAP · Streamlit · Docker · LaTeX ·
  Potato 2.7.1 for annotation.
- **Contributions:** (1) a construct-grounded athlete-text corpus with span→construct labels
  and reported inter-annotator agreement; (2) two-level, expert-validated interpretability;
  (3) a time-aware, fusion-ready design.
- **Taxonomy:** 10 constructs in `config/taxonomy.yaml`, v2, locked at Phase 4 - cognitive
  anxiety, somatic anxiety, self-confidence, motivation orientation, perceived stress,
  attentional focus, burnout signal, coping style, resilience, appraisal orientation - plus an
  interpretation modifier (facilitative/debilitative).

## 2. Where the project actually stands

| Phase | State |
|---|---|
| 1–9b | Complete and gated. 4,000 synthetic records → **9,302 utterances**, de-ID leak rate 0%, gold sample drawn (400 `gold_eval` + 100 `gold_dev`) |
| 10 Weak labelling | Complete **offline only** - 9,302 silver labels. **No live OpenRouter call has ever been made** (OPEN-008 / OPEN-023) |
| 11 Gold verification | Tooling complete and verified against real Potato output. **Gate UNMEASURABLE** - kappa needs a second human |
| 12 Taxonomy refinement | Tooling complete, tested, gated. `--burden` and `--propose` run today; `--refine` reports BLOCKED |
| **13 Baselines** | **This phase. Not started.** |

**The one fact that shapes everything below: `data/gold/` is empty.** OPEN-025 (no second
annotator) has blocked Phases 11 and 12 and now constrains 13. There is no human-labelled
evaluation set. Silver labels exist for the whole corpus.

**Two hard-won lessons this codebase has already paid for, and you must not repeat:**

1. **OPEN-021 - the lexicon baseline is not independent of the corpus.** Its cues and the
   synthetic template bank were both written from `taxonomy.yaml`'s `positive_examples`, so it
   was scoring partly by matching its own cousin. Macro-F1 fell 0.780 → **0.461** on a
   template-disjoint split once the bank stopped reusing those phrasings. **0.461 is the
   honest floor.** Any baseline that beats it needs a check on whether it is beating it for a
   real reason.
2. **A carefully written, never-executed path is broken until proven otherwise.** This project
   has found that twice (OPEN-024, the O(n²) cost ledger; OPEN-027, the Potato ingest that
   silently dropped every span). Run what you write.

## 3. What already exists - read it before building anything

- `src/evaluation/splits.py` - `random_split`, **`template_disjoint_split`**, `leakage_report`
  (4/6/8-gram overlap). The template-disjoint split is the honest one; the random split
  inflates scores through shared templates.
- `src/evaluation/metrics.py` - `per_label_prf`, `macro_f1`, `micro_f1`, `subset_accuracy`,
  `bootstrap_ci`, `paired_bootstrap_p_value`.
- `src/evaluation/baselines.py` - `MajorityBaseline`, `StratifiedRandomBaseline`,
  `LexiconBaseline`, `MemorisationProbe`, all behind a shared `Baseline` interface.
- `src/labeling/store.py` - `SilverStore` for reading silver labels.
- `src/models/` - **empty. This is where Phase 13's new code goes.**
- `scripts/run_*.py` - the gate-script pattern to follow: offline, deterministic, exit 0
  pass / 1 fail / 2 config error, prints a `Phase N gate: PASSED|FAILED` line.
- `scikit-learn>=1.4` is already in `requirements-base.txt`. **Do not add torch or
  transformers** - those are Phase 14 and live in `requirements-ml.txt`.

## 4. Phase 13, exactly

From `PROJECT_PLAN.md`:

> **Objective:** Establish the bar the transformer must beat.
> **Tasks:** Mod Agent trains a lexicon baseline and TF-IDF + LogReg/SVM multi-label baselines
> with fixed seeds and a held-out split.
> **Deliverable:** Baseline metrics in `reports/`.
> **Gate:** Reproducible baseline macro-F1 recorded.

The lexicon baseline already exists. **The new work is the classical multi-label baselines and
the harness that makes their numbers reproducible and honest.** Concretely:

1. **`src/models/classical.py`** - TF-IDF + One-vs-Rest LogisticRegression and LinearSVC over
   the 10 constructs, fixed seed, wrapped in the existing `Baseline` interface so every
   baseline is evaluated by one code path. Persist fitted models to `models/` with the seed,
   the sklearn version, the feature config and the training-set fingerprint.
2. **`src/models/dataset.py`** (or similar) - assemble `(text, label-set)` pairs from
   `SilverStore`, honouring abstention (~38% of utterances carry no construct - "none" is a
   real answer, not a missing one) and the dedup structure (87.4% of utterances were exact
   duplicates before Phase 9b; **deduplicate before fitting, or the same string votes hundreds
   of times and the score is a popularity contest**).
3. **`scripts/run_baselines.py`** - the Phase 13 gate. Trains every baseline on the
   **template-disjoint** split, reports per-construct P/R/F1, macro/micro F1 with **bootstrap
   confidence intervals**, runs `leakage_report` on the split, and writes
   `reports/baselines.md` + `reports/baselines.json`.
4. **`tests/test_models.py`** - including a **reproducibility test**: same seed, same data,
   identical metrics to full float precision. "Reproducible" is the gate's actual word.

### The thing you must get right, and it is not the modelling

**There is no gold set, so these baselines can only be evaluated against silver - and a
silver-evaluated score measures agreement with a cheap LLM, not accuracy.** State that in the
report's own text, in the JSON, and in the paper framing. Specifically:

- Label every number produced in this phase **`PROVISIONAL - silver-evaluated`**, with a
  one-line explanation of what that does and does not mean. A provisional number that does not
  announce itself becomes a cited number.
- **Never call it accuracy.** It is agreement with the Phase 10 labeller.
- Build the harness so that swapping in `data/gold/` later changes an input path and nothing
  else, and re-running produces the real numbers. Leave a `--gold` flag that **refuses with a
  clear message** while the directory is empty rather than silently falling back to silver.
- Report against the **template-disjoint** split as the headline and the random split only as
  a contrast, with the gap between them stated - that gap is the memorisation story and it is
  a paper result, not a diagnostic.
- Include the existing trivial baselines (majority, stratified-random) in the table. A macro-F1
  that looks respectable next to nothing looks different next to `MajorityBaseline`.

## 5. How to work

- **Small, verifiable steps.** Every non-trivial step ends with a way to check it worked.
- **Ask before locking any new tool, library or model** that is not already in `CLAUDE.md` §6.
- **Academic rigor first** - prefer the choice that is easier to defend to a reviewer.
- **Reproducibility:** fixed seeds, pinned versions, deterministic from a fresh clone, offline.
  `pytest` must never be able to spend money.
- **`data/gold/` is human-owned.** No agent writes there, ever.
- **Never commit secrets.** Keys live only in `.env` (gitignored).
- Be concise and direct in chat; put the depth in files and docstrings. Docstrings in this
  codebase explain *why a choice was made and what failure it prevents* - match that.
- Note: the environment has a broken pixeltable plugin hook (OPEN-002) that errors on every
  file write. It is cosmetic; ignore it and keep going.

## 6. What I want from you, in order

1. Read the governing docs and the existing `src/evaluation/` and `src/labeling/store.py`.
   Tell me briefly what you found and anything in this prompt that turns out to be wrong.
2. Ask me any question whose answer would change the design - especially anything about
   evaluating on silver, or about which split is the headline.
3. Implement Phase 13 in the existing style and architecture.
4. **Run it.** Execute the gate, run `pytest`, run `ruff check` and `ruff format --check`, and
   re-run the earlier gates (`run_ingestion.py --verify-only`, `run_preprocessing.py`,
   `run_eda.py`, `run_labeling.py`, `run_taxonomy_refinement.py --status`) to prove nothing
   regressed. Report the real output, including anything that failed.
5. Update `PROJECT_PLAN.md`'s status board and `docs/open_issues.md` if this phase opens,
   closes or changes an issue.
6. Produce **`phase13_handover.md`** in the same structure as `phase12_handover.md`
   (Part A project summary · Part B session summary with findings, files changed and gate
   results · Part C what the next phase needs), self-contained enough that a new session can
   continue without this chat. Give me the exact PowerShell commit commands at the end.
7. **Do not start Phase 14** until I confirm receipt of the handover.

Expected test count before your changes: **416** passing on Python 3.11. If `pytest` reports
415 with `test_python_version_is_311` failing, you are on the wrong interpreter - that is not a
bug to fix.
