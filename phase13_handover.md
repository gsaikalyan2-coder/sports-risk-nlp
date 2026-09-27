# Handover - Phase 13: Baselines

**Date:** 2026-08-11 · **Week 4 of 8** · **Gate: PASSED** (every number PROVISIONAL)
**Previous:** `phase12_handover.md` · **Next:** Phase 14 - Transformer fine-tuning
**Do not start Phase 14 until the owner confirms receipt of this file.**

---

## PART A - Project Summary

**Pre-Competition Psychological Risk Profiling of Athletes.** Construct-grounded NLP that
detects validated sports-psychology constructs in an athlete's *pre-competition* text and
fuses them into an interpretable 0–1 risk index with span-level explanations. Not sentiment
analysis, not clinical diagnosis; research and decision-support only. `docs/ethics.md` binds
every phase.

**Owner:** Saikalyan, sophomore, SRMIST. **Target:** IEEE full paper (iTriply Explore), draft
by the 1st week of September 2026, code frozen ~Week 7.

**Stack (locked):** Python 3.11 · CrewAI · OpenRouter · HuggingFace transformers with
DeBERTa/RoBERTa · scikit-learn · SHAP · Streamlit · Docker · LaTeX · Potato 2.7.1.

**Contributions:** (1) construct-grounded athlete-text corpus with span→construct labels and
reported IAA; (2) two-level expert-validated interpretability; (3) time-aware, fusion-ready
design.

**Taxonomy:** 10 constructs, `config/taxonomy.yaml` v2, frozen at Phase 4/12.

### Status

| Phase | State |
|---|---|
| 1–9b | Complete and gated. 4,000 synthetic records → 9,302 utterances, de-ID leak rate 0% |
| 10 Weak labelling | Complete **offline only**. 9,302 silver labels - **and Phase 13 found they contain no signal (OPEN-028)** |
| 11 Gold verification | Tooling complete. Gate UNMEASURABLE - kappa needs a second human (OPEN-025) |
| 12 Taxonomy refinement | Tooling complete, tested, gated. `--refine` reports BLOCKED |
| **13 Baselines** | **Complete. Gate PASSED. All figures PROVISIONAL - planted-label corpus-property measurements, not accuracy** |
| 14 Transformer | Not started. **Blocked as written** - see Part C |

---

## PART B - Current Session Summary

### B1. The finding that reshaped the phase

The Phase 13 prompt assumed a silver-evaluated score would "measure agreement with a cheap
LLM." It does not. **No live OpenRouter call has ever been made** (OPEN-008), so all 9,302
silver labels came from `OfflineLLM._synthesise_silver` in `src/agents/llm.py`, which picks a
construct with `rng.randrange(...)` seeded from `sha256(prompt)`. **The label is a hash of the
text.**

Measured before writing any modelling code:

| Property | Value |
|---|---|
| Labels per non-abstained utterance | exactly 1, always - the data is not multi-label |
| Constructs attested | **6 of 10** (the four categorical ones are absent by design) |
| Abstention rate | 33.3% = the stub's hardcoded `rng.random() < 0.33` |
| Silver construct ∈ parent's planted set | 20.2% vs 16.7% chance |
| Distinct texts with conflicting label sets | **580** |

Consequences: a multi-label baseline cannot be trained on it; macro-F1 over 10 constructs is
capped at 0.6 before modelling; on a template-disjoint split a classifier scores ≈0 and that is
the *correct* answer. **`PROVISIONAL - silver-evaluated` would have understated the problem**,
because that stamp implies the labels carry some signal.

Raised as **OPEN-028** and put to the owner before implementing.

### B2. Owner decisions taken this session

1. **Build the harness, gate on `generation_spec.planted_constructs`** under the
   `scripts/run_benchmark_audit.py` precedent - explicitly a corpus-property measurement, never
   a results-table number. Recommended and chosen over running the live pilot first or refusing
   to produce any number.
2. **Template-disjoint remains the headline**, random the contrast; the gap is a paper result.

### B3. Why the unit is the raw record

`generation_spec.planted_constructs` records a construct and `template_id` **per record**, not
per utterance. There is no generator-recorded alignment from utterance to construct, so planted
labels are record-level by construction. This also means the record-level path reuses
`src/evaluation/splits.py` unchanged.

Record-level data turned out to be well-behaved: **4,000 records → 3,888 distinct texts, zero
label ambiguity**, genuinely multi-label (1–3 constructs), all 10 constructs attested with
446–885 support.

### B4. Files created

| File | Purpose |
|---|---|
| `src/models/dataset.py` | `load_planted` / `load_silver` / `load_gold`, `deduplicate`, `Dataset`. Owns the "which labels, and what does a score mean" question |
| `src/models/classical.py` | `TfidfLinearBaseline` + `LogisticRegressionBaseline` + `LinearSVCBaseline`, `training_fingerprint`, model persistence |
| `src/models/__init__.py` | Package exports and the torch/transformers boundary note |
| `scripts/run_baselines.py` | The Phase 13 gate |
| `tests/test_models.py` | 19 tests |
| `reports/baselines.md`, `reports/baselines.json` | Deliverables |

Files modified: `PROJECT_PLAN.md` (status board, live risks, Phase 13 outcome),
`docs/open_issues.md` (OPEN-028 + changelog row).

### B5. Design decisions worth carrying forward

- **`load_gold` refuses while `data/gold/` is empty** rather than falling back to silver, and
  the refusal message names the fallback it is declining - otherwise a future reader "fixes"
  the error by adding exactly that fallback. Two tests assert this.
- **`load_silver` requires `acknowledge_no_signal=True`.** Still callable, because
  demonstrating the collapse is better evidence than asserting it.
- **One-vs-rest is written out rather than imported.** `OneVsRestClassifier` raises on a
  single-class column, and silver has four all-negative columns. `_ConstantZero` keeps the
  macro-F1 denominator at 10 instead of silently averaging over the 6 attested constructs -
  dropping them is a real way papers overstate results.
- **Labels are looked up by `record_id`, never zipped positionally** against a shuffled split.
- **`solver="liblinear"`** so the score does not move with BLAS thread count.
- **Dedup drops texts whose copies disagree** rather than majority-voting them.

### B6. Gate results - the actual output

```
Phase 13 baselines  seed=42  sklearn=1.7.2
  synth_precomp_v1: n=3888 unit=record source=planted deduped 4000->3888
                    (collapsed=112, ambiguous_dropped=0) unattested_constructs=0
  STATUS: PROVISIONAL -- planted-label measurement, NOT model accuracy

Split: template_disjoint  train=2591 test=443 discarded=854 (22.0%) disjoint=True
Split: random             train=3110 test=778 discarded=0  shared_templates=149

| system                 | disjoint macro-F1 [95% CI]   | random  |    gap |
|------------------------|------------------------------|---------|--------|
| majority               | 0.000 [0.000, 0.000]         | 0.000   | +0.000 |
| stratified_random      | 0.104 [0.082, 0.126]         | 0.175   | +0.071 |
| memorisation_probe     | 0.197 [0.162, 0.228]         | 0.720   | +0.523 |
| lexicon                | 0.462 [0.432, 0.494]         | 0.562   | +0.100 |
| tfidf_logreg           | 0.222 [0.181, 0.259]         | 0.999   | +0.777 |
| tfidf_linearsvc        | 0.181 [0.150, 0.212]         | 1.000   | +0.819 |

Phase 13 gate: PASSED
```

**Three findings for the paper:**

1. **The bar for Phase 14 is the lexicon at 0.462, not the learned models.** Both classical
   models score *below* the lexicon on the honest split. The 0.462 independently reproduces the
   OPEN-021 floor of 0.461 measured by a different code path - a genuine cross-check.
2. **A linear model over TF-IDF memorises this corpus perfectly.** LinearSVC: 1.000 macro-F1
   random, 0.181 template-disjoint. The **+0.819** gap is the strongest OPEN-012 evidence the
   project has and belongs in the paper as a *result*. `run_benchmark_audit.py`'s note that
   1-NN's drop is "a LOWER BOUND on the inflation fine-tuning would show" is now confirmed:
   +0.523 for the probe, +0.819 for a linear model.
3. **The silver ablation collapses as predicted.** `--silver`: every system ~0.10, lexicon
   **0.040 - below stratified-random**.

### B7. Verification - everything that was run

| Check | Result |
|---|---|
| `scripts/run_baselines.py` | **PASSED**, exit 0 |
| `scripts/run_baselines.py --gold` | **REFUSED**, exit 2, names OPEN-025 and the declined fallback |
| `scripts/run_baselines.py --silver` | Runs, NO-SIGNAL banner, collapse demonstrated |
| `run_ingestion.py --verify-only` | Phase 7 gate PASSED |
| `run_preprocessing.py` | Phase 8 gate PASSED |
| `run_eda.py` | Phase 9 gate PASSED |
| `run_labeling.py` | Phase 10 gate PASSED |
| `run_taxonomy_refinement.py --status` | exit 0, still correctly BLOCKED |
| `run_benchmark_audit.py` | PASSED |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 126 files already formatted |
| `pytest` | **434 passed, 1 failed** (416 → 435 total) |

**Re-running the gates changed no data.** `git diff data/` shows only two `written_on` dates
and one `run_id`; `utterances.jsonl` and `silver.jsonl` are byte-identical. Determinism holds.

### B8. Two caveats on the verification, stated plainly

1. **The one test failure is `test_python_version_is_311`.** The Linux verification sandbox has
   only Python 3.10 (PyPI is reachable; the 3.11 standalone build is not). This is the exact
   case the Phase 13 prompt documents as "not a bug to fix". **The owner should re-run `pytest`
   on the Windows 3.11 venv and expect 435/435.**
2. **Running on 3.10 required a sandbox-only shim** (`sitecustomize.py` aliasing
   `datetime.UTC`, which is 3.11+). It lives outside the repo, in the sandbox home directory.
   **No repository file was modified for it.** On 3.11 it is unnecessary.
3. `ruff` was pinned to **0.16.2** to match `.pre-commit-config.yaml` / `requirements.lock.txt`.
   A newer ruff reports a pre-existing UP038 in `src/labeling/parser.py`; on the pinned version
   the tree is clean.

---

## PART C - What Phase 14 needs next

### C1. Phase 14 is blocked as written

`PROJECT_PLAN.md` specifies: *"Fine-tune DeBERTa/RoBERTa multi-label classifier on
gold+silver."* Today that reads **"train on nothing + noise"**:

- `data/gold/` is **empty** (OPEN-025 - no second annotator).
- `data/processed/silver/` is **PRNG output** (OPEN-028).

A transformer trained on this would produce a number, and the number would be meaningless. The
gate - *"Transformer > best baseline on macro-F1"* - cannot be honestly evaluated.

### C2. The three ways forward, for the owner to choose

1. **Unblock the data (correct, needs a person and a pilot).** Run the live labelling pilot
   (OPEN-008 steps 1–3, ~$1–12 per OPEN-023) *and* recruit the second annotator (OPEN-025).
   Both must happen; the pilot alone gives real silver but still no evaluation set.
2. **Run Phase 14 as a corpus-property measurement**, exactly as Phase 13 did - fine-tune
   against planted labels, report against the same template-disjoint split, and check whether a
   transformer beats **0.462**. Defensible, produces a real methods result, and every number
   carries the same provisional stamp. Cheapest path to a Week-4 deliverable.
3. **Reorder - do Phase 15/16 (risk fusion, explainability) scaffolding first** and hold
   Phase 14 until data exists. Keeps the critical path moving but leaves the paper's central
   model unbuilt closest to the freeze.

**Recommendation: 2, with 1 started in parallel today.** The pilot and the recruiting
conversation are both owner-actionable and have been deferred across six phases; neither gets
shorter by waiting.

### C3. What Phase 14 can reuse verbatim

- `src/models/dataset.py` - same loaders. `--gold` swaps the input path and nothing else.
- `src/evaluation/metrics.py::paired_bootstrap_p_value` - **the Phase 14 gate needs it.**
  "Transformer > best baseline" is not met by 0.48 vs 0.462 unless the gap survives resampling.
- `scripts/run_baselines.py` - the gate-script shape, the provisional stamping, the refusal
  behaviour. Copy the framing, not just the structure.
- `reports/baselines.json` - the numbers to beat, machine-readable.

### C4. Watch items specific to Phase 14

- **`requirements-ml.txt` is the boundary.** `src/models/` deliberately has no torch import so
  the classical baselines stay runnable in the light Docker image. Keep it that way.
- **A transformer will memorise harder than LinearSVC.** LinearSVC already hits 1.000 on a
  random split. Any Phase 14 number from a random split is uninformative by construction.
- **The three-instance pattern.** OPEN-007, OPEN-024, OPEN-027 and now OPEN-028 are all "a
  carefully written path that had never been run against its real input." Phase 14 introduces
  a GPU training path. Run it small before running it long.

---

## Open items, by urgency

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-025** | **No second annotator.** Blocks Phases 11, 12, and the honesty of every Phase 13+ number. | **now** |
| **OPEN-028** | **The entire silver set is PRNG output.** New this phase. | **Phase 14** |
| **OPEN-011** | **No real athlete text.** Corpus is 100% synthetic; contribution #1 claims otherwise. | **now** |
| **OPEN-004** | **No expert raters recruited.** Headline contribution, longest lead time. | Phase 17 |
| **OPEN-008** | Key exists; no live call ever made. Assume broken until executed. | live pilot |
| **OPEN-023** | Full live pass projects at 87% of the monthly cap. Owner decision. | now |
| OPEN-021 | Lexicon not independent of the corpus. **Reconfirmed at 0.462 this phase.** | Phase 18 |
| OPEN-012 | Template leakage. **Now quantified at +0.819 for a linear model.** | Phase 14 |
| OPEN-026 | Annotation burden half-measured. | Phase 12 freeze |
| OPEN-007, OPEN-022, OPEN-019, OPEN-009, OPEN-005, OPEN-006 | unchanged | - |
| OPEN-002 | Broken pixeltable hook; cosmetic, fired on every write this session. | - |

**Stated plainly.** Phase 13 delivered a working, tested, reproducible baseline harness and
three findings worth publishing. It also established that **two of the project's three data
assets are not what they appear to be**: gold does not exist, and silver is noise. The tooling
has not been the bottleneck for three phases. One SRMIST coach or sport-psychology
practitioner closes OPEN-025, OPEN-011 and OPEN-004 - and one $1–12 pilot closes OPEN-008 and
OPEN-028.

---

## Commit commands (PowerShell)

```powershell
cd C:\Users\x\sports-risk-nlp

# Re-verify on the real interpreter first -- expect 435/435 on Python 3.11.
.\.venv\Scripts\Activate.ps1
python -m pytest
ruff check .
ruff format --check .
python scripts\run_baselines.py     # expect: Phase 13 gate: PASSED

# 1 -- the modelling package
git add src/models/__init__.py src/models/dataset.py src/models/classical.py
git commit -m "feat(models): Phase 13 dataset assembler and classical baselines

Adds TF-IDF + one-vs-rest LogisticRegression and LinearSVC over the 10
constructs, plus the dataset layer that decides which labels a score is
computed against.

dataset.py owns the honesty question. load_gold() refuses while data/gold/
is empty (OPEN-025) rather than falling back to silver; load_silver()
requires acknowledge_no_signal=True because the silver set is PRNG output
(OPEN-028). A silent fallback there would relabel a chance-agreement score
as accuracy.

One-vs-rest is written out rather than imported: OneVsRestClassifier raises
on a single-class column and silver has four all-negative ones. _ConstantZero
keeps the macro-F1 denominator at 10 instead of quietly averaging over the 6
attested constructs.

Dedup runs before fitting (4,000 records -> 3,888 texts) so a repeated string
does not vote once per copy. Texts whose copies disagree are dropped, not
majority-voted."

# 2 -- the gate
git add scripts/run_baselines.py
git commit -m "feat(scripts): Phase 13 gate -- run_baselines.py

Trains six systems on the template-disjoint split, scores them with bootstrap
CIs, runs the leakage report, writes reports/baselines.{md,json}.

Every figure is stamped PROVISIONAL -- planted-label measurement, in the report
text and in the JSON. The word 'accuracy' appears next to no number. --gold
refuses with exit 2; --silver runs the ablation that demonstrates OPEN-028."

# 3 -- the tests
git add tests/test_models.py
git commit -m "test(models): 19 tests for the Phase 13 harness

Reproducibility is asserted at full float equality, not pytest.approx -- the
gate's word is 'reproducible' and an approximate check would pass while a
nondeterministic solver wandered in the sixth decimal.

Also asserts the memorisation gap directly: if random-vs-disjoint ever closes,
that is a corpus whose leakage properties changed and Phase 14 needs to know."

# 4 -- the results and the record
git add reports/baselines.md reports/baselines.json PROJECT_PLAN.md docs/open_issues.md phase13_handover.md
git commit -m "docs: Phase 13 results, OPEN-028, and handover

Honest floor is the lexicon at 0.462 macro-F1 on the template-disjoint split;
TF-IDF+LogReg 0.222, LinearSVC 0.181 -- both below it. LinearSVC scores 1.000
on the random split, a +0.819 memorisation gap that is the strongest OPEN-012
evidence yet and belongs in the paper as a result.

OPEN-028: the entire silver set is PRNG output keyed on the prompt hash, a
consequence of OPEN-008. Single-label, 6/10 constructs, chance agreement,
580 texts with conflicting labels. Phase 14's 'train on gold+silver' is
currently 'train on nothing + noise'.

435 tests. All six earlier gates re-run and passing."

git push
```

**Note on `models/`:** `.gitignore` excludes `models/*`, so the fitted `.joblib` artefacts the
gate writes are intentionally not committed. They are regenerated deterministically by
re-running the gate; the manifest beside each records the seed, sklearn version, feature
config and training fingerprint needed to confirm a regenerated model is the same one.
