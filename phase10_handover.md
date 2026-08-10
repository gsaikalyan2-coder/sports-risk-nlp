# Handover — Phase 10: Weak / LLM Labelling Pipeline

Self-contained. A new AI session can start from this file plus the repo; no chat history
needed.

---

## PART A — Project Summary

**Project:** Pre-Competition Psychological Risk Profiling of Athletes.
Construct-grounded NLP that detects validated sports-psychology constructs in an athlete's
pre-competition text and fuses them into an interpretable 0–1 risk index with span-level
explanations.

**Explicitly NOT** sentiment analysis and **NOT** clinical diagnosis. Research and
decision-support only. `docs/ethics.md` is binding on every phase.

**Owner:** Saikalyan, sophomore, SRMIST.
**Target:** IEEE full paper (iTriply Explore); draft by the 1st week of September 2026.
**Timeline:** 8 weeks; code frozen ~Week 7. It is currently **Week 3**.

**Confirmed stack:** Python 3.11 · CrewAI · OpenRouter (cost-tier routing) · HuggingFace
transformers with DeBERTa/RoBERTa · scikit-learn baselines · SHAP · Streamlit · Docker ·
LaTeX.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, expert-validated
interpretability; (3) a time-aware, fusion-ready design.

**Governing documents:** `CLAUDE.md` (single source of truth) and `PROJECT_PLAN.md`
(25-phase blueprint). Read both before working. `docs/open_issues.md` is the single source
of truth for open items.

### Phase status

| Phase | Status | Commit |
|---|---|---|
| 1 — Repo reset & scaffold | Complete | `fb87925` |
| 2 — Dev environment & tooling | Complete | `07d77ab` + `b28873f` |
| 3 — Related work & novelty | Complete | `b104b8d` |
| 4 — Construct taxonomy | Complete (v2, locked; frozen at Phase 12) | `d238721` |
| 5 — Ethics, data governance & risk plan | Complete | `a28b7ba` |
| 6 — Confirm decisions & wire agent framework | Complete | `b28873f` (+ `ccba023`) |
| 7 — Data ingestion pipeline | Complete | `6f9561a` |
| 8 — Preprocessing & de-identification | Complete | see Phase 9 commits |
| **9 — EDA & quality profiling** | **Complete** | see Part B9 |
| **9b — Corpus hardening** | **NEXT** (~1 day, no API key needed) | — |
| 10 — Weak / LLM labelling | blocked on OPEN-008 | — |

**Carried-forward caveats:**

- **Phase 1 deviation:** no `legacy-backup` branch; the previous codebase was permanently
  deleted at the owner's instruction. **OPEN-003 is now closed** — the repo was pushed to a
  private GitHub remote (`gsaikalyan2-coder/sports-risk-nlp`) on 2026-08-10, the first
  off-machine backup this project has had. Push at the end of every phase from now on.
- **Phase 3:** the BibTeX key `Toth2025` is historical. László Tóth was the **handling
  editor**, not an author. Correct authors: Nogueira, Morais, Mansell & Gomes.
- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11.
  `datetime.UTC` (3.11+) is used in `src/agents/ledger.py` and `src/ingestion/allowlist.py`.
  Tests were run here with a `sitecustomize` shim backfilling that alias (not committed).
  **Re-run `pytest` on the 3.11 machine to confirm natively** — expect **251/251**.
- **OPEN-002** (broken pixeltable plugin hook) fired on every file write throughout Phase 9.
  Still cosmetic, still unfixed.

---

## PART B — Current Session Summary (Phase 9)

### B1. What Phase 9 was asked to do

From `PROJECT_PLAN.md`: *Objective — understand the corpus before labelling. Tasks —
notebook EDA covering length distributions, vocabulary, class-of-interest prevalence,
duplicates, junk; decide the sampling strategy for the gold set. Deliverable —
`reports/eda.md` plus figures. Gate — documented data-quality issues and a stratified
sampling plan.*

All delivered. The phase also found three defects large enough that the sampling plan had to
be designed around them.

### B2. OPEN-015 resolved first, before any numbers were published

The owner approved option (a): delete the offending synonym group, regenerate, re-gate.

- `("part", "portion", "corner", "piece")` **deleted** from `SYNONYM_GROUPS`. A version
  history block was added to `synthetic.py` and `GENERATOR_VERSION` bumped to **1.2** —
  which also records that v1.1 never bumped the constant, so artefacts from that run are
  stamped `@1.0` and mean 1.1.
- Corpus regenerated at seed 42. `corner of me`, `portion of me`, `piece of me`: **0, 0, 0**.
- Regeneration moves the RNG stream, so **every** downstream count changed. All three gates
  were re-run and are re-reported together in B5.

**Two published numbers were found to be wrong and were corrected, not glossed:**

1. The `synthetic.py` comment written when the group was removed said `corner of me` occurred
   in **11** records. True v1.1 count is **9** — verified by reconstructing the committed
   v1.1 generator via `git show 6f9561a:src/ingestion/synthetic.py` and regenerating at seed
   42. The other two counts in that comment (10, 14) are correct.
2. `docs/data_sources.md` reported the v1.1 corpus as **638** types / **1,163** distinct texts
   / **40,169** tokens / **106** construct-free records. The committed v1.1 generator produces
   **635 / 1,161 / 40,251 / 92**. Small, changes no conclusion — but `CLAUDE.md` §9 claims a
   reviewer can reproduce these numbers exactly, so a figure that does not reproduce is a
   defect regardless of size. Corrected, with the discrepancy recorded in the table's note.

### B3. The sweep — OPEN-015 was not an isolated defect (**OPEN-016**, new)

`src/ingestion/synonym_audit.py` (written by the prior session, executed and reported here)
replaces "a human read twenty records" with an **exhaustive** enumeration: 221 filled
template variants, **727 substitution events**, six mechanical probes (idiom membership,
article agreement, number agreement, particle/argument structure, inflected form, arity).

| Measure | Value |
|---|---|
| Distinct signatures flagged | 127 |
| `broken` / `degraded` / `acceptable` | 53 / 6 / 68 |
| Unreviewed signatures | **0** (a test fails the build otherwise) |
| Defective signatures realised in the v1.2 corpus | 55 |
| **Records containing ≥1 defect** | **190 / 1,200 (15.8%)** |
| Utterances containing ≥1 defect | 207 / 4,141 (5.0%) |

Examples: *"when I **figure about** the first ball"*, *"my **insides is** in knots"*,
*"we've got **a approach** for the first bell"*, *"I'm **on edge I'll** let everyone down"*.

**Removing the `part` group fixed 0.8% of records and left the other 15%.** The remedy —
repairing ~15 more synonym groups — shrinks the vocabulary OPEN-012's mitigation rests on and
regenerates the corpus a second time. **That is an owner trade-off, not an implementation
detail**, so it was raised as **OPEN-016** with four costed options rather than actioned. This
is the same reasoning under which Phase 8 declined to fix OPEN-015 mid-phase.

### B4. Three more findings, all new issues

**OPEN-018 — 73.6% of utterances are exact duplicates.** 4,141 utterances, **1,528 distinct
texts**. At record level the same corpus is 5.0% duplicated, so it is a *segmentation*
artefact invisible in every Phase 7 statistic: `DISCOURSE_SUFFIXES` and `NEUTRAL_SENTENCES`
are appended whole, are rendered **without** `_vary`, and Phase 8 cuts each into its own
utterance. `"It is what it is."` appears **268** times. Two annotators agreeing on that string
268 times is one agreement counted 268 times — this would have inflated Phase 11's kappa
invisibly. Mitigated in the sampling plan (deduplication before drawing, asserted by a test);
the corpus itself is unchanged.

**OPEN-017 — the gold pool is too small for a per-construct kappa.** See B6.

**OPEN-019 — `generation_spec` is replicated, not distributed.** Phase 8 copies the parent
record's spec onto every utterance byte-identically (verified, and now asserted by a test).
A record averaging 3.45 utterances and planting 2 constructs reports both on all 3.45,
including the neutral logistics sentence. **Any per-utterance count derived from
`generation_spec` is a per-record count × ~3.45.** Documented in `docs/preprocessing.md` next
to the schema and in `GeneratorMetadataProfile`; every downstream calculation uses
`planted_construct_records`.

### B5. Re-run gates, all together (v1.2)

| Gate | Result |
|---|---|
| `scripts/run_ingestion.py --verify-only` | **Phase 7 gate: PASSED** — **4,000** records, coverage 100% on all five required fields |
| `scripts/run_preprocessing.py` | **Phase 8 gate: PASSED** — 34/34 exact, precision/recall 100%, leak 0%, held-out probe 10/10; 4,000 → **13,651** utterances, 0 dropped |
| `scripts/run_benchmark_audit.py` | **PASSED** — see below |
| `scripts/run_eda.py` | **Phase 9 gate: PASSED** |
| `ruff check src/ scripts/ tests/` | All checks passed |
| `ruff format --check` | 54 files formatted |
| `pytest` | **250/251** — the one failure is `test_python_version_is_311` under the sandbox's 3.10, i.e. the test working correctly |
| Determinism | `run_eda.py` twice → byte-identical report, figures and candidates (md5) |

Benchmark audit, v1.3 at n=4,000 (v1.1 was 0.732 → 0.198; v1.2 0.738 → 0.146):

| System | Random split | Template-disjoint | Drop |
|---|---|---|---|
| memorisation_probe | 0.797 | **0.184** | +0.612 |
| lexicon (leakage-immune) | 0.762 | 0.780 | −0.018 |

Conclusion unchanged and slightly stronger: **Phases 13, 14 and 18 MUST use
`template_disjoint_split()`.**

### B6. The gold-set sampling plan — the actual deliverable

**The obvious plan fails, and it was measured rather than assumed.** Drawing the gold set from
the test side of `template_disjoint_split` gives 98 records / 228 utterances and **zero
records planting `appraisal_orientation`** — one of the ten locked constructs would have an
undefined kappa. Cause: that function shuffles all 85 templates as one pool, and with 7–12
templates per construct a global 20% holdout can miss one entirely. **It was not changed** —
it is the right tool for the leakage comparison it was built for. A stricter partitioner was
added beside it.

**The plan** (`src/evaluation/sampling.py`, six steps, all executable):

1. `construct_stratified_template_partition` holds out **35% of each construct's templates**
   independently, floor of one. Still a partition, so disjointness holds; coverage is now
   guaranteed by construction, not by luck.
2. Assign **records**, not utterances — a record joins the gold pool only if *every* template
   it uses is held out. Two utterances of one record share its templates, so drawing
   utterances independently would put siblings on both sides and reintroduce the leakage.
3. Filter: straddling/template-free, `too_short`, exact and near-duplicate (Jaccard ≥ 0.9).
4. Draw: construct quotas round-robin to a 40-positive floor, then greedy context balance on
   `time_band` → `sport` → `competition_level` → `region`. **Marginal** balance, not joint —
   1,250 cells and 400 items makes joint balance arithmetically impossible.
5. **100% double-annotated** by two annotators, so Cohen's kappa is computable per construct
   on the whole set. `generation_spec` is **stripped** from every written candidate.
6. Calibrate on `gold_dev` **first** — drawn from *training-side* templates, so arguing over
   the rubric on it costs zero evaluation power.

**What it yields today, and this is the blocker:**

| | Target | Drawn |
|---|---|---|
| `gold_eval` | 400 | **235** |
| `gold_dev` | 100 | 100 |
| Constructs meeting the 40-positive floor | 10/10 | **3/10** |

Only 235 of 4,141 utterances survive (3,649 straddle or are template-free, 251 duplicates,
6 junk). And those counts are an **upper bound**: by the lexicon-baseline proxy, **97 of 235
(41.3%) `gold_eval` items carry no construct cue at all** — the first drawn item is *"Kit
arrived yesterday, so that's one thing sorted."*, selected because its *parent record* plants
a construct (OPEN-019). Corrected at ~0.6×, **no construct meets the floor.**

**Measured remedy** (generator, seed, partition and draw held fixed):

| Generated records | Utterances | Eligible pool | Drawn | Below floor |
|---|---|---|---|---|
| 1,200 (current) | 4,141 | 235 | 235 | **7/10** |
| 2,400 | 8,214 | 408 | 400 | 1/10 |
| **4,000** | 13,651 | 599 | 400 | **0/10** |
| 8,000 | 27,367 | 933 | 400 | 0/10 |

**4,000 generated records is the minimum**, and a lower bound. Note the sub-linear growth:
6.7× the corpus buys 4× the pool, because deduplication bites harder as the grammar's ceiling
of distinct utterances is approached. **More records raise positives per template; only a
larger template bank raises phrasing diversity, and phrasing diversity is what a construct
kappa generalises over.**

### B7. Bugs found by running the code

1. **`bootstrap_statistic` was annotated `Sequence[T]` with no `T` in scope.** Invisible at
   runtime because of `from __future__ import annotations`; only ruff's F821 caught it. A
   `TypeVar` was added with a comment explaining why an unresolvable annotation is a comment
   that looks like a type.
2. **My own near-duplicate detector under-reported.** The first version bucketed each text
   under its single rarest token and the docstring claimed that was exact. It is not: *"...
   tomorrow morning **again**"* and *"... tomorrow morning **too**"* are Jaccard 0.8 and land
   in different buckets. A test caught it. Replaced with the standard **prefix filter**
   (index under the first `|A| − ceil(t·|A|) + 1` tokens in rarest-first order), which *is*
   exact. **The test was not weakened to match the code** — that is the failure mode
   `phase9_handover.md` §B5 warns about, and it was the specific temptation here.
3. **MATTR was returning 40.08.** Missing `/ window` in the accumulator. Caught by writing
   `test_mattr_is_a_ratio` before trusting the number.
4. **A field named `templates_per_record` counted constructs.** Renamed. A record plants at
   most one template per construct, so the two coincide *on this corpus* and would have
   diverged silently the moment the generator changed.

### B8. Design decisions worth defending in the paper

1. **The arithmetic is in `src/`, not the notebook.** A notebook's outputs are stored state:
   they drift from the code, and nothing fails when they do. `notebooks/01_eda.ipynb` is a
   thin viewer over tested functions; `scripts/run_eda.py` regenerates everything.
2. **Figures are hand-written SVG, not matplotlib.** matplotlib is not in
   `requirements-base.txt`, and adding a plotting stack to the light image every agent
   service pulls, to draw six bar charts, inverts the Phase 2 layering decision. SVG also
   diffs meaningfully in git and goes into the LaTeX build at any column width.
3. **MATTR is the headline, raw TTR is never quoted alone.** TTR falls mechanically as a
   corpus grows, so the TTR over 4,141 utterances is not comparable with Phase 7's over
   1,200 records even though the text is identical — and that is exactly the comparison a
   reader will make.
4. **Every headline rate carries a bootstrap CI**, including coverage rates at 100%.
   `[1.000, 1.000]` is a different statement from a bare "100%", and the first A3 donation
   with patchy metadata will show the difference with no code change.
5. **Under-powered constructs are reported, not failed.** A gate that refused to pass would
   block Phase 9 on a regeneration the owner has not approved; a silent gate would let an
   under-powered kappa reach the paper.
6. **Three fixed-corpus assertions in `tests/test_profile.py` are *meant* to fail** if the
   corpus is regenerated. That is the alarm that `reports/eda.md` has gone stale.

### B9. Files changed

| File | Change |
|---|---|
| `src/evaluation/profile.py` | **new** — corpus profiling (~700 lines) |
| `src/evaluation/sampling.py` | **new** — gold-set sampling plan (~470 lines) |
| `src/evaluation/figures.py` | **new** — pure-Python SVG charts |
| `src/evaluation/__init__.py` | public API extended to 47 exports |
| `src/evaluation/metrics.py` | `bootstrap_statistic`, `proportion_ci`, `_percentile_interval` (prior session); missing `TypeVar` fixed |
| `src/ingestion/synthetic.py` | **v1.3**: synonym group removed (v1.2), `_vary` guarded, version history, `corner of me` count corrected 11→9 |
| `src/ingestion/substitution_verdicts.py` | **new** — the verdict table as a generation-time guard, plus `RETIRED_DEFECTS` |
| `scripts/run_ingestion.py` | `DEFAULT_COUNT` 1,200 → **4,000** (OPEN-017) |
| `PROJECT_PLAN.md` | status board, live-risk table, **Phase 9b inserted**, Phases 7–11 rewritten against what was measured |
| `src/ingestion/synonym_audit.py` | **new** (prior session) — exhaustive substitution sweep + verdict ratchet |
| `scripts/run_eda.py` | **new** — the Phase 9 gate |
| `tests/test_profile.py` | **new** — 61 tests; three fixed-corpus assertions updated after regeneration |
| `tests/test_synonym_audit.py` | **new** (prior session) — 18 tests |
| `notebooks/01_eda.ipynb` | **new** — viewer |
| `reports/eda.md` | **new** — 550 lines, 9 sections |
| `reports/figures/*.svg` | **new** — 9 figures |
| `data/processed/gold_candidates/` | **new** — `gold_eval.jsonl` (235), `gold_dev.jsonl` (100), `sampling_plan.json` |
| `data/raw/`, `data/interim/` | regenerated at **v1.3, n=4,000** (4,000 records → 13,651 utterances) |
| `docs/open_issues.md` | OPEN-015/016/017 **closed**; OPEN-018/019 raised; **OPEN-020 raised**; change log |
| `docs/data_sources.md` | v1.2 statistics column; three v1.1 figures corrected; unit warning |
| `docs/preprocessing.md` | OPEN-019 replication note next to the schema |
| `.gitignore` | gold-candidate JSONL ignored, `sampling_plan.json` **kept** (it is the method) |

### B11. Phase 9 follow-up — OPEN-016 and OPEN-017 both resolved

The owner instructed both be actioned together in one regenerate-and-re-gate cycle, on the
reasoning that labelling a corpus about to be replaced spends tokens twice.

**OPEN-016 → option (c), the generation-time guard. Generator v1.3.**

New module `src/ingestion/substitution_verdicts.py` holds the ruled verdicts plus the shared
tokeniser. `_vary` now applies each candidate substitution, checks the result, and reverts it
if it would produce a ruled-defective frame. **Zero synonym groups deleted.**

The three-module arrangement is forced, not stylistic: `synonym_audit` imports `synthetic`, so
`synthetic` cannot import it back. A shared third module is the only way the generator can
consult the verdicts.

Both remedies were measured before choosing, at n=4,000 seed 42:

| | Synonym bank | Realised vocabulary | Defective records |
|---|---|---|---|
| v1.2, unguarded | 64 groups | 643 types | 630 (15.75%) |
| Option (a): delete the 34 implicated members | 57 groups | 594 types | 0 |
| **Option (c): guard — chosen** | **64, unchanged** | **625 types** | **0** |

Deleting costs 49 realised types, the guard costs 18. I had written "the guard costs zero
vocabulary" in the first draft of the docstrings; measuring showed that was wrong — a word
whose only frames in the bank were defective now never appears — and the claim was corrected
rather than left standing. The guard still keeps 31 more types than deletion and removes
nothing from the bank, so a future template using one of those words in a good frame gets it
back automatically.

**The RNG stream deliberately does not depend on the verdict table.** A rejected substitution
consumes its draw exactly as an accepted one does; there is no retry. Retrying would make the
corpus a function of the verdict table, and every future edit to that table would silently
reshuffle the whole corpus.

**OPEN-017 → option (a), `DEFAULT_COUNT` 1,200 → 4,000.**

| | Before | After |
|---|---|---|
| Records / utterances | 1,200 / 4,141 | **4,000 / 13,651** |
| Records with a defect | 190 (15.8%) | **0 (0.0%)** |
| Eligible gold pool | 235 | **559** |
| `gold_eval` drawn / target 400 | 235 | **400** |
| Constructs below the 40-positive floor | **7 / 10** | **0 / 10** |
| Utterance exact-duplicate rate | 73.6% | **87.4%** (worse, as predicted) |

**A test caught me breaking an invariant, and I fixed the code rather than the test.** I first
added the three OPEN-015 regression signatures straight into `VERDICTS`, which broke
`test_no_orphan_verdicts` — that test asserts every verdict corresponds to a frame the audit
can still produce, and the deleted group produces none of them. The invariant is correct: a
stale ruling is dead weight the ratchet cannot validate. A *guard* entry is deliberately for a
frame nothing currently produces, which is the opposite property. Two purposes, so two tables:
the guard entries moved to `RETIRED_DEFECTS`.

**The three fixed-corpus assertions did their job.** All three failed on regeneration, which is
exactly what they exist for, and were updated together with the report in the same change.

**What did NOT get fixed, and it is now the most important corpus item — OPEN-020.**

The stated 40-positive floor is met. The correction behind it is not. The lexicon proxy still
finds **153 of 400 (38.2%)** drawn `gold_eval` items carrying no construct cue, because that
fraction is a property of *records* — a record is ~3.4 utterances of which ~2 realise a
construct. Corrected at 0.62×, **7 of 10 constructs fall back below 40**.

Swept, correcting each draw by its own measured cue fraction:

| Records | Pool | Target | Drawn | Cue fraction | Corrected min | Below 40 |
|---|---|---|---|---|---|---|
| 1,200 | 235 | 400 | 235 | 0.59 | 10.0 | 10 / 10 |
| **4,000 (current)** | **559** | **400** | **400** | **0.62** | **28.4** | **7 / 10** |
| 4,000 | 559 | 559 | 559 | 0.61 | 32.3 | 3 / 10 |
| 6,000 | 694 | 500 | 500 | 0.61 | 34.2 | 4 / 10 |
| 8,000 | 838 | 400 | 400 | 0.59 | 28.2 | 7 / 10 |
| 8,000 | 838 | 600 | 600 | 0.59 | 37.8 | 2 / 10 |

The cue fraction sits at 0.59–0.62 regardless of corpus size. **Corpus size provably cannot fix
this; the template bank can.** Raised as OPEN-020 and scheduled as Phase 9b.

**One tempting shortcut was rejected outright.** The draw could prefer utterances the lexicon
detects, clearing the corrected floor immediately. It must not: selecting gold items by lexicon
detectability builds the lexicon baseline's strengths into the evaluation set, so the lexicon
would then beat the transformer on a test set chosen to suit it. That is not a gold set.

**`TARGET_GOLD_EVAL` was left at 400**, not raised to the full 559-item pool. That would take
the shortfall from 7 constructs to 3 at the cost of ~40% more annotation — the owner's time
budget, not a code decision. One-constant change in `src/evaluation/sampling.py`.

### B11. Phase 9 follow-up — OPEN-016 and OPEN-017 both resolved

The owner instructed both be actioned together in one regenerate-and-re-gate cycle, on the
reasoning that labelling a corpus about to be replaced spends tokens twice.

**OPEN-016 → option (c), the generation-time guard. Generator v1.3.**

New module `src/ingestion/substitution_verdicts.py` holds the ruled verdicts plus the shared
tokeniser. `_vary` now applies each candidate substitution, checks the result, and reverts it
if it would produce a ruled-defective frame. **Zero synonym groups deleted.**

The three-module arrangement is forced, not stylistic: `synonym_audit` imports `synthetic`, so
`synthetic` cannot import it back. A shared third module is the only way the generator can
consult the verdicts.

Both remedies were measured before choosing, at n=4,000 seed 42:

| | Synonym bank | Realised vocabulary | Defective records |
|---|---|---|---|
| v1.2, unguarded | 64 groups | 643 types | 630 (15.75%) |
| Option (a): delete the 34 implicated members | 57 groups | 594 types | 0 |
| **Option (c): guard — chosen** | **64, unchanged** | **625 types** | **0** |

Deleting costs 49 realised types, the guard costs 18. I had written "the guard costs zero
vocabulary" in the first draft of the docstrings; measuring showed that was wrong — a word
whose only frames in the bank were defective now never appears — and the claim was corrected
rather than left standing. The guard still keeps 31 more types than deletion and removes
nothing from the bank, so a future template using one of those words in a good frame gets it
back automatically.

**The RNG stream deliberately does not depend on the verdict table.** A rejected substitution
consumes its draw exactly as an accepted one does; there is no retry. Retrying would make the
corpus a function of the verdict table, and every future edit to that table would silently
reshuffle the whole corpus.

**OPEN-017 → option (a), `DEFAULT_COUNT` 1,200 → 4,000.**

| | Before | After |
|---|---|---|
| Records / utterances | 1,200 / 4,141 | **4,000 / 13,651** |
| Records with a defect | 190 (15.8%) | **0 (0.0%)** |
| Eligible gold pool | 235 | **559** |
| `gold_eval` drawn / target 400 | 235 | **400** |
| Constructs below the 40-positive floor | **7 / 10** | **0 / 10** |
| Utterance exact-duplicate rate | 73.6% | **87.4%** (worse, as predicted) |

**A test caught me breaking an invariant, and I fixed the code rather than the test.** I first
added the three OPEN-015 regression signatures straight into `VERDICTS`, which broke
`test_no_orphan_verdicts` — that test asserts every verdict corresponds to a frame the audit
can still produce, and the deleted group produces none of them. The invariant is correct: a
stale ruling is dead weight the ratchet cannot validate. A *guard* entry is deliberately for a
frame nothing currently produces, which is the opposite property. Two purposes, so two tables:
the guard entries moved to `RETIRED_DEFECTS`.

**The three fixed-corpus assertions did their job.** All three failed on regeneration, which is
exactly what they exist for, and were updated together with the report in the same change.

**What did NOT get fixed, and it is now the most important corpus item — OPEN-020.**

The stated 40-positive floor is met. The correction behind it is not. The lexicon proxy still
finds **153 of 400 (38.2%)** drawn `gold_eval` items carrying no construct cue, because that
fraction is a property of *records* — a record is ~3.4 utterances of which ~2 realise a
construct. Corrected at 0.62×, **7 of 10 constructs fall back below 40**.

Swept, correcting each draw by its own measured cue fraction:

| Records | Pool | Target | Drawn | Cue fraction | Corrected min | Below 40 |
|---|---|---|---|---|---|---|
| 1,200 | 235 | 400 | 235 | 0.59 | 10.0 | 10 / 10 |
| **4,000 (current)** | **559** | **400** | **400** | **0.62** | **28.4** | **7 / 10** |
| 4,000 | 559 | 559 | 559 | 0.61 | 32.3 | 3 / 10 |
| 6,000 | 694 | 500 | 500 | 0.61 | 34.2 | 4 / 10 |
| 8,000 | 838 | 400 | 400 | 0.59 | 28.2 | 7 / 10 |
| 8,000 | 838 | 600 | 600 | 0.59 | 37.8 | 2 / 10 |

The cue fraction sits at 0.59–0.62 regardless of corpus size. **Corpus size provably cannot fix
this; the template bank can.** Raised as OPEN-020 and scheduled as Phase 9b.

**One tempting shortcut was rejected outright.** The draw could prefer utterances the lexicon
detects, clearing the corrected floor immediately. It must not: selecting gold items by lexicon
detectability builds the lexicon baseline's strengths into the evaluation set, so the lexicon
would then beat the transformer on a test set chosen to suit it. That is not a gold set.

**`TARGET_GOLD_EVAL` was left at 400**, not raised to the full 559-item pool. That would take
the shortfall from 7 constructs to 3 at the cost of ~40% more annotation — the owner's time
budget, not a code decision. One-constant change in `src/evaluation/sampling.py`.

### B10. Commit commands

```powershell
cd C:\Users\saika\sports-risk-nlp
Remove-Item -LiteralPath ".git\index.lock" -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\Activate.ps1

pytest                                    # expect 250/250 on 3.11
ruff check src/ scripts/ tests/
python scripts\run_ingestion.py --verify-only
python scripts\run_preprocessing.py
python scripts\run_benchmark_audit.py
python scripts\run_eda.py

# 1 — Phase 8, still uncommitted from the previous session
git add src/preprocessing/ scripts/run_preprocessing.py tests/test_preprocessing.py `
        docs/preprocessing.md tests/fixtures/deid_cases.jsonl reports/deid_audit_sample.md
git commit -m "Phase 8: preprocessing and de-identification pipeline

- normalise -> segment -> language filter -> de-identify, nine modules
- deidentified=true is earned in one function; InterimRecord refuses false
- health detail removed clause-by-clause; body parts are NOT health data
  (somatic_anxiety surfaces almost entirely as body language)
- fixture gate: 34/34 exact, precision 100%, recall 100%, leak rate 0%
- fixture case name_01 corrected: role nouns are not names, per ethics.md 5.1;
  the implementation was NOT changed to chase the fixture
- language filter bug found by running it: unequal stopword profiles dropped
  two English records as Portuguese"

# 2 — OPEN-015 fix and the regeneration it forces
git add src/ingestion/synthetic.py src/ingestion/synonym_audit.py `
        tests/test_synonym_audit.py data/raw/synth_precomp_v1/provenance.json `
        data/interim/synth_precomp_v1/
git commit -m "Phase 9: close OPEN-015; generator v1.2; exhaustive synonym sweep

- delete (part, portion, corner, piece): every 'part' in the bank sits inside
  the idiom 'part of me', which does not survive substitution
- bump GENERATOR_VERSION to 1.2 with a version-history block recording that
  v1.1 never bumped the constant
- regenerate at seed 42: 4,110 -> 4,141 utterances; corner/portion/piece of me
  all now zero. Phase 7, Phase 8 and benchmark gates re-run and re-reported
- synonym_audit.py: exhaustive enumeration of all 727 single-token
  substitutions, six probes, and a verdict ratchet that fails the build on an
  unreviewed signature. Reading twenty records is luck; enumerating is a method
- correct the 'corner of me (11 records)' comment to 9, verified by
  reconstructing v1.1 from git show 6f9561a"

# 3 — the Phase 9 deliverable
git add src/evaluation/ scripts/run_eda.py tests/test_profile.py `
        notebooks/01_eda.ipynb reports/eda.md reports/figures/ `
        data/processed/gold_candidates/sampling_plan.json .gitignore
git commit -m "Phase 9: corpus profile, gold-set sampling plan, EDA report

- src/evaluation/{profile,sampling,figures}.py, pure Python, no new deps
- figures are hand-written SVG: no matplotlib in the light Docker image, and
  a regenerated figure with unchanged data produces an empty git diff
- MATTR reported alongside raw TTR: TTR is length-confounded, so Phase 7's
  per-record figure is not comparable with a per-utterance one
- gold plan: drawing from template_disjoint_split's test side leaves
  appraisal_orientation with ZERO records, so templates are partitioned PER
  CONSTRUCT instead. template_disjoint_split is unchanged
- gold_eval draws 235 of a target 400; 7/10 constructs below the kappa floor
- fixed a real bug in my own near-duplicate detector: rarest-token blocking is
  not exact and under-reported. Replaced with a prefix filter. The test was not
  weakened to match the code
- 60 new tests; three fixed-corpus assertions are MEANT to fail on regeneration"

# 4 — issues and docs
git add docs/ phase10_handover.md
git commit -m "Phase 9: OPEN-015 closed; OPEN-016/017/018/019 raised

- OPEN-016: 15.8% of records still carry a broken/degraded substitution after
  the OPEN-015 fix. Owner trade-off (grammaticality vs vocabulary), four options
- OPEN-017: gold pool supports 235 of 400 items, 7/10 constructs under-powered;
  4,000 generated records measured as the minimum. Bundle with OPEN-016
- OPEN-018: 73.6% utterance-level exact duplication, a segmentation artefact
  invisible at record level. Mitigated in the sampling plan, not in the corpus
- OPEN-019: generation_spec is replicated onto every utterance, so per-utterance
  counts derived from it are per-record counts x 3.45
- data_sources.md: three v1.1 figures corrected to the reproducible values
  (638->635 types, 1,163->1,161 distinct, 40,169->40,251 tokens)"
```

Note the recurring blocker: `.git/index.lock` has appeared in the Phase 6, 7, 8 and 9
sessions. Environment quirk, not a repo problem, but it costs time every session.

---

## PART C — Phase 9b Brief (do this before Phase 10)

**Phase 9b is new**, inserted into `PROJECT_PLAN.md` at the end of Phase 9. It needs **no API
key**, costs roughly a day, and is the last corpus-side work standing between this project and
a kappa a reviewer will believe.

**Objective:** make the corpus able to support a defensible per-construct kappa.

**Owning agent:** Taxonomy/Psych Agent (writes realisations), Evaluation Agent (re-profiles).

### The two tasks

**1. OPEN-020 — expand the template bank to ~15 realisations per construct** (from 7–12). This
is the one that matters, for two independent reasons:

- **Phrasing diversity.** A 35% holdout currently leaves **2–4 phrasings per construct** in the
  evaluation set. A kappa computed on 3 phrasings is a kappa about those 3 phrasings, not about
  the construct. Two annotators agreeing on *"I keep turning over what happens if I get the
  first half wrong"* tells you they read the same sentence the same way. It does not tell you
  the rubric separates `cognitive_anxiety` from `perceived_stress` in language they have not
  seen. **This is the weakest point in contribution #1 and a reviewer will find it.**
- **Coverage.** More construct realisations per record raises the 0.62 cue fraction directly,
  which is the only thing that will clear the corrected floor.

Write them against `docs/annotation_guidelines.md` and `config/taxonomy.yaml`. **The taxonomy
is frozen until Phase 12** — new realisations of existing constructs only, no new constructs
and no changed definitions.

**2. OPEN-018 option (a) — apply `_vary` to `DISCOURSE_SUFFIXES` and `NEUTRAL_SENTENCES`.**
They are emitted verbatim today, and Phase 8 segments each into its own utterance, so
`"It is what it is."` appears hundreds of times and 87.4% of utterances are exact duplicates.

### Sequencing, and one thing that will surprise you

New templates create new substitution frames. `scripts/run_eda.py` will therefore flag
signatures nobody has ruled on, and **the build will fail until each is ruled** in
`substitution_verdicts.VERDICTS`. That is the ratchet working as designed, not an obstacle —
but budget for it, and do not merge template work without re-running the sweep.

Then: regenerate at seed 42, re-run all four gates, and update `reports/eda.md`,
`docs/data_sources.md` and the fixed-corpus assertions in `tests/test_profile.py` **in the same
change**. Expect those three assertions to fail first — that is the alarm that the report has
gone stale, and it is the second time they will have earned their keep.

### Gate

≥14 templates per construct · utterance duplicate rate materially below 87.4% · cue-corrected
construct coverage ≥40 for at least 8 of 10 constructs · all four gates pass · synonym sweep
reports zero unruled signatures and zero realised defects.

---

## PART C2 — Phase 10 Brief (after 9b)

**Objective:** weak / LLM labelling — a cheap model proposes construct labels plus a rationale
per utterance (silver labels), under cost-aware routing.

**Owning agent:** Labelling Agent (cheap→mid, routed), `src/agents/roster.py::LABELING`, with
the Annotation-QA Agent flagging low-confidence and conflicting labels.

**Output:** `data/processed/silver/`. **Never** `data/gold/` — human-owned, guards refuse it.

### Read first

- `reports/eda.md` §3 (duplication), §5 (the guard), §7 (the sampling plan).
- `config/model_routing.yaml`, `src/agents/{config,llm,ledger,roster}.py` — the cost-aware
  routing layer exists and was built at Phase 6. **Reuse it; do not build a second one.**
- `docs/annotation_guidelines.md` and `config/taxonomy.yaml` — the rubric the LLM gets.

### Four things Phase 9 measured that change how this is built

1. **Deduplicate before the API call.** 87.4% of utterances are exact duplicates — 3,131
   distinct strings, not 13,651. Label the distinct set and fan results back out. That is a
   **~77% saving on the phase's entire budget** and it costs one `dict`. (After 9b the ratio
   improves, so re-measure rather than reusing this number.)
2. **Abstention must be a first-class answer.** ~38% of utterances carry no construct at all. A
   labeller that never returns "none" is broken, not thorough.
3. **Pass the parent record as context.** Median utterance is 9 tokens — too short to judge
   `appraisal_orientation` alone. `parent_record_id` is on every interim record for this.
4. **Placeholders must survive the prompt intact.** Tell the model what `[ATHLETE]` and
   `[EVENT_WINDOW]` mean rather than leaving it to guess.

### The circularity trap

This phase produces something that *is* a label, stored beside records carrying
`generation_spec`, which is not one. **Never evaluate silver against `generation_spec`** — that
measures whether an LLM can recover this project's own template choices. Silver is evaluated
against the Phase 11 human gold set and nothing else.

### Constraints, all inherited and non-negotiable

- **OPEN-008: no `OPENROUTER_API_KEY` in `.env`.** First phase that genuinely needs one. Until
  it exists Phase 10 can be written but not run, and `phase8_handover.md` records OPEN-007 as
  exactly the mistake of shipping an unexecuted path.
- **`pytest` must never be able to spend money.** No test may reach a live provider.
- Offline and deterministic from a fresh clone; fixed seeds.
- `data/gold/` is human-owned; no agent writes there.
- The allow-list enforcement path is never weakened and never gains a bypass flag.
- Pure Python where possible, so it imports in the light Docker image.
- Every agent writes a run log to `logs/`; cost to `logs/cost_ledger.csv`.

**Gate:** silver labels for the corpus, with a confidence and rationale per label, a routing
decision logged per call, and a cost ledger entry — plus the Annotation-QA review queue.

**Do not start Phase 11.**

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-011** | **No real athlete text in the corpus.** Contribution #1 needs some. Still the only unmitigated high-impact item. | **Phase 11** |
| **OPEN-004** | **Expert-rater recruitment not started.** Week 1–2 per the risk register; it is now Week 3. Headline contribution, longest lead time, least control. | **Phase 17** |
| **OPEN-020** | **New.** Template bank too small: 2–4 phrasings per construct in the eval set, and a 0.62 cue fraction that no corpus size fixes. The weakest point in contribution #1. | **Phase 9b (next)** |
| **OPEN-008** | No `OPENROUTER_API_KEY` in `.env`. **Now genuinely blocking.** | **Phase 10** |
| OPEN-018 | **Worsened as predicted:** 87.4% utterance duplication (was 73.6%). Mitigated in the sampling plan; ~77% Phase 10 cost saving available; root cause is Phase 9b task 2. | Phase 9b |
| OPEN-017 | ~~Gold pool too small~~ — **CLOSED at Phase 9** against its stated criterion (235→400 items, 7/10→0/10 below floor). Residual is OPEN-020. | closed |
| OPEN-016 | ~~15.8% broken substitutions~~ — **CLOSED at Phase 9** by a generation-time guard. 0/4,000 records. | closed |
| OPEN-019 | **New.** `generation_spec` replicated per utterance. Documentation only. | monitored |
| OPEN-007 | CrewAI backend written but never executed. | Phase 10 if chosen |
| OPEN-012 | Vocabulary bounded by the template bank; 625 types. Phase 9b's template work is the real remedy. | Phase 14 (monitored) |
| OPEN-015 | ~~"corner of me"~~ — **CLOSED at Phase 9.** | closed |
| OPEN-013 | ~~De-identification unvalidatable~~ — **CLOSED at Phase 8.** | closed |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-003 | ~~No off-machine backup~~ — **CLOSED 2026-08-10**, private GitHub remote. Keep pushing per phase. | closed |
| OPEN-009 | Model/price drift. | Any large batch |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic, fires on every file write. Confirmed still firing throughout Phase 9. | — |

**The two highest-value non-code actions available today are still OPEN-011 and OPEN-004, and
they are still the same conversation** — recruiting an SRMIST coach or sport-psychology
practitioner who could both broker pre-competition text under A3 consent *and* serve as the
Phase 17 expert rater. It was Week 3 at the start of Phase 8 and it is still Week 3. That
conversation has now been deferred across three phases and has the longest lead time of
anything left.
