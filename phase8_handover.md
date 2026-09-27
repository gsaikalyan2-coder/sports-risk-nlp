# Handover - Phase 8: Preprocessing & De-identification

Self-contained. A new AI session can start from this file plus the repo; no chat history
needed.

---

## PART A - Project Summary

**Project:** Pre-Competition Psychological Risk Profiling of Athletes.
Construct-grounded NLP that detects validated sports-psychology constructs in an athlete's
pre-competition text and fuses them into an interpretable 0–1 risk index with span-level
explanations.

**Explicitly NOT** sentiment analysis and **NOT** clinical diagnosis. Research and
decision-support only.

**Owner:** Saikalyan, sophomore, SRMIST.
**Target:** IEEE full paper (iTriply Explore); draft by the 1st week of September 2026.
**Timeline:** 8 weeks; code frozen ~Week 7. It is currently Week 3.

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
| 1 - Repo reset & scaffold | Complete | `fb87925` |
| 2 - Dev environment & tooling | Complete (Docker gate met 2026-08-09) | `07d77ab` + `b28873f` |
| 3 - Related work & novelty | Complete | `b104b8d` |
| 4 - Construct taxonomy | Complete (v2, locked; frozen at Phase 12) | `d238721` |
| 5 - Ethics, data governance & risk plan | Complete | `a28b7ba` |
| 6 - Confirm decisions & wire agent framework | Complete | `b28873f` (+ `ccba023`) |
| **7 - Data ingestion pipeline** | **Complete - PENDING COMMIT** | see Part B blocker |
| 8 - Preprocessing & de-identification | **NEXT** | - |

**Carried-forward caveats:**

- **Phase 1 deviation:** no `legacy-backup` branch; the previous codebase was permanently
  deleted at the owner's instruction. Only `main` exists, no remote, no off-machine backup
  (**OPEN-003**).
- **Phase 3:** the BibTeX key `Toth2025` is historical. László Tóth was the **handling
  editor**, not an author. Correct authors: Nogueira, Morais, Mansell & Gomes. Cite the
  correct authors in prose.
- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11.
  `datetime.UTC` (3.11+) is used in `src/agents/ledger.py` and `src/ingestion/allowlist.py`
  - correct for the project. Tests were run here with a shim backfilling that alias.
  **Re-run `pytest` on the 3.11 machine to confirm natively.**

---

## PART B - Current Session Summary (Phase 7)

### B1. The data-strategy decision, which changed the plan

`CLAUDE.md` §10 Q3 confirmed "existing public/licensed datasets first" (allow-list category
A1) and explicitly said to revisit the synthetic fallback at Phase 7. It was revisited.

**Survey finding: no public corpus of *pre-competition* athlete text exists.** Every
athlete-speech corpus located is **post-match**.

That is a construct-validity problem, not a licensing inconvenience. The taxonomy is
anticipatory - `appraisal_orientation` asks whether an athlete frames an *upcoming*
competition as challenge or threat; `cognitive_anxiety` is worry about an outcome that has
not happened. Post-match speech carries relief, disappointment, and attribution instead.

Four candidates surveyed, **all four rejected** (full table in `docs/data_sources.md` §4):

| Candidate | Rejected because |
|---|---|
| Cornell Tennis Transcripts (6,467 post-match pressers) | **No licence statement anywhere** - page and README carry only a BibTeX request. Fails A1, triggers P7. |
| iMiGUE-Speech (359 post-match interviews + ASR) | Gated behind an **unsigned licence agreement** with U. Oulu. |
| ASAP Sports direct collection | `terms.php` and `robots.txt` both returned empty; ToS **unverifiable** → P4/P5, fail closed. |
| YouTube captions via the Data API | `captions.download` requires **channel-owner OAuth**; 403 otherwise. Any other method breaches ToS → P4. |

**Owner decisions, 2026-08-09:**

1. **Synthetic-first (A2).** Pre-competition framing retained, full taxonomy retained.
2. **Real-text acquisition routes declined for now** (Cornell email, iMiGUE agreement, A3
   consent form). → **OPEN-011**, the project's live highest risk.
3. **DataRobot stays at Phase 16.** No account, SDK, endpoint, or token exists. Ingestion
   is local and offline.

> **A note the next session should carry.** The owner's first set of answers selected
> post-match corpora *and* declined every route to obtain them, plus DataRobot as the
> ingestion layer with no credentials. Those answers were internally contradictory and
> would have produced either an empty `data/raw/` or a fabricated integration. The
> contradiction was raised rather than coded around, and the second round resolved it
> coherently. Raising it was correct and should be repeated if it recurs.

### B2. What was built

`src/ingestion/` - six modules, ~1,150 lines:

| Module | Responsibility |
|---|---|
| `allowlist.py` | Loads and validates `config/data_sources_allowlist.yaml`; `check_source` is the gate; `refuse()` logs then raises. Refuses to load a policy whose `default_action` is not `deny`. |
| `provenance.py` | `Provenance` dataclass + `validate_provenance`. Required-field list is **read from the policy**, not hardcoded, so policy and enforcement cannot drift. |
| `records.py` | `RawRecord` schema with nullable temporal/context fields; vocabulary validation; `metadata_coverage`. |
| `store.py` | `RawStore` / `SourceWriter` - the **only** write path into `data/raw/`. Refuses any root inside `data/gold/`. |
| `sources.py` | Generic `.jsonl` / `.csv` loaders so the real gold set lands through the same controls later. |
| `synthetic.py` | The A2 construct-grounded template generator. |

Plus `scripts/run_ingestion.py` (the Phase 7 gate), `tests/test_ingestion.py` (53 tests),
`docs/data_sources.md`.

**Design decisions worth defending in the paper:**

1. **No record can exist without provenance - structurally.** `open_source()` runs the
   allow-list check and writes `provenance.json` *before* returning anything that can write
   a record. There is no public API taking a path and some text, so "forgot the provenance"
   is not a mistake a caller can make; it is a call they cannot express.
2. **All seven prohibitions must be declared against explicitly.** An absent declaration is
   refused (`MISSING_DECLARATION`), not defaulted to compliant. Silence is not consent.
   A test asserts no prohibition can be added to the YAML without a code guard.
3. **No bypass flag**, per the instruction written into the policy file itself.
4. **`deidentified` is hardcoded `False` at ingestion.** Phase 8 sets it. Writing `true`
   here would put a claim in the artefact that no code has earned.
5. **Template grammar rather than an LLM**, for byte-level reproducibility, because
   OPEN-008 leaves no key to verify an LLM path against, and because a template grammar
   cannot pass itself off as naturalistic speech.
6. **Theory-grounded coherence constraints in the generator.** A first draft produced
   records pairing a *challenge* appraisal with a strongly *debilitative* interpretation -
   incoherent under the Theory of Challenge and Threat States in Athletes
   [JonesMeijen2009], which the taxonomy cites. Now challenge admits only facilitative and
   threat only debilitative; the modifier requires a parent anxiety at intensity ≥ 2; and
   opposed constructs cannot both be maximal. Verified: **0 incoherent records** in 1,200.

### B3. What was ingested

`data/raw/synth_precomp_v1/` - **1,200 records**, A2 synthetic, seed 42.

| Metric | Value |
|---|---|
| Distinct texts | 976 (81.3%) |
| Tokens / types | 30,367 / **444** |
| Type–token ratio | **0.0146** |
| Words per record | mean 25.3, median 24, range 8–64 |
| Records with no construct | 106 (8.8%) |
| Construct prevalence | 12.0%–21.2% across all ten |
| `time_to_competition_days` | **100%** coverage, 0–30 days |
| `sport` / `competition_level` / `region` | **100%** each |
| `training_load_hint` | 62.3% (deliberately sparse) |

Rebuild: `python scripts/run_ingestion.py --count 1200 --seed 42`.

### B4. Bugs found by running the code

1. **`notes` is a policy-required provenance field** and the first test fixture omitted it.
   The enforcement refused correctly; the fixture was wrong. Kept as-is - requiring a human
   sentence per source is right for a corpus paper.
2. **The name-detection test flagged "Thursday".** The heuristic was too crude. Weekdays
   are legitimate athlete speech and are not identifiers (`docs/ethics.md` §5.1 asks for
   *exact dates* to be replaced, which they are). Whitelisted.
3. **`.gitignore` hid the provenance record.** `data/raw/*` ignored everything, so a fresh
   clone would show no evidence of what was ingested. Changed to commit `provenance.json`
   (metadata only, never source text) while keeping `records.jsonl` out - the seed is the
   reproducibility guarantee, not the blob.

### B5. Verification performed

| Check | Result |
|---|---|
| `ruff check src/ scripts/ tests/` | **All checks passed** |
| `ruff format --check` | 30 files already formatted |
| `pytest tests/test_ingestion.py` | **53/53 pass** |
| Full suite | **95/96** - the one failure is `test_python_version_is_311` under the sandbox's 3.10, i.e. the test working correctly |
| Phase 7 gate `run_ingestion.py` | **PASSED** |
| `--demo-refusal` | Unlisted source refused with `UNLISTED_SOURCE`, logged |
| Determinism | Same seed → identical records, confirmed |
| Generator vs. taxonomy | Every planted construct is one of the ten locked keys |
| Coherence audit | 0 incoherent records in 1,200 |
| `data/gold/` guard | Refuses the gold root and any subdirectory |
| Licences | Checked against actual source pages, not memory |

### B6. Files changed

| File | Change |
|---|---|
| `src/ingestion/{allowlist,provenance,records,store,sources,synthetic}.py` | **new** |
| `src/ingestion/__init__.py` | public API |
| `scripts/run_ingestion.py` | **new** - the Phase 7 gate |
| `tests/test_ingestion.py` | **new** - 53 tests |
| `docs/data_sources.md` | **new** |
| `data/raw/synth_precomp_v1/provenance.json` | **new** (records.jsonl gitignored) |
| `docs/open_issues.md` | OPEN-011, OPEN-012, OPEN-013 added |
| `CLAUDE.md` | §10 Q3 resolved; DataRobot reconfirmed at Phase 16 |
| `.gitignore` | commit `provenance.json`, keep the corpus out |
| `phase7_handover.md` | owner's own Phase 6 commit-status update, uncommitted |

### B6b. Phase 7 addendum - OPEN-012 and OPEN-013 addressed in-session

Both were raised during Phase 7 and both were mitigated before handover rather than pushed
to Phase 8.

**OPEN-012 - memorisation / low vocabulary. Substantially mitigated.**

*Generator v1.1* adds a construct-preserving lexical-variation layer (near-synonym
substitution + discourse framing) after template rendering:

| Metric | v1.0 | v1.1 |
|---|---|---|
| Vocabulary (types) | 444 | **638** |
| Distinct texts | 81.3% | **96.9%** |
| MATTR-50 | - | **0.819** |

Raw TTR moved only 0.0146 → 0.0159, which is a property of that metric (length-confounded
denominator), not of the corpus. `docs/data_sources.md` §2.1 says so rather than quoting the
flattering number. Synonym groups are restricted to shared part-of-speech **and** argument
structure - a first pass produced "fixating *about* the result", "I must *to* not mess this
up", and "Sessions *has* been"; those groups were deleted, with the reasoning recorded inline.

*The real fix* is `src/evaluation/` - new this session, pure Python, no numpy or sklearn so
it imports in the light Docker image:

- `metrics.py` - multi-label P/R/F1, bootstrap CIs, **paired bootstrap significance test**.
- `splits.py` - `template_disjoint_split` partitions templates before records; leakage report.
- `baselines.py` - majority, stratified-random, lexicon, and a **memorisation probe** (1-NN).
- `scripts/run_benchmark_audit.py` - the measurement.

Result, `synth_precomp_v1`, seed 42:

| System | Random | Disjoint | Drop |
|---|---|---|---|
| Memorisation probe | 0.732 | **0.198** | **+0.534** |
| Lexicon (leakage-immune) | 0.729 | 0.757 | −0.028 |

Templates on both sides 85 → **0**; verbatim test texts in train 3.8% → **0.0%**; 8-gram
overlap 60.3% → 11.8%.

A pure memoriser loses 0.53 macro-F1 once templates are held out; a system that cannot
memorise is unchanged. **A transformer memorises more readily than 1-NN, so 0.53 is a lower
bound** on what Phase 14 would otherwise have over-reported.

> Design note worth carrying: the first version of the audit used the *lexicon* baseline,
> which ignores training labels entirely and therefore cannot memorise - it showed no
> inflation and appeared to exonerate the random split. The `MemorisationProbe` exists
> because a leakage audit needs a *learning* system to be meaningful.

**Binding on Phases 13/14/18** (also in `docs/data_sources.md` §2.2):

1. Use `template_disjoint_split`. `random_split`'s docstring says it is a foil only.
2. Report **both** numbers - the gap is a contribution, not an embarrassment.
3. Every headline number carries a bootstrap CI.
4. "Transformer > baseline" is met only when `paired_bootstrap_p_value` says so.
5. Compare against the **lexicon** specifically. Barely beating a keyword matcher on a
   disjoint split means the templates were learned, not the constructs.

**OPEN-013 - de-identification unvalidatable. Fixture delivered.**

`tests/fixtures/deid_cases.jsonl` - 34 cases covering every category in the
`docs/ethics.md` §5.1 removal table, across easy/medium/hard bands. All names invented.

**Eight are negatives** that must come back unchanged: "**Mark** my words" (given name as
verb), "The **Final** is on **Sunday** and my **Coach**" (capitalised common nouns),
"47 seconds" (performance figure, contrasted with jersey number 47 in the positive set),
"**Two days out**" (relative timing - contribution #3 must survive de-identification).
Without negatives, a de-identifier that blanks everything scores perfect recall.

12 tests enforce fixture integrity, including that none of it leaked into `data/raw/`.

**Also fixed:** allow-list and `docs/ethics.md` version headers said 1.0 while both had 1.1
changelog entries. Corrected; the machine-readable `version:` field bumped to 2 to mark
code enforcement.

### B7. BLOCKER - the work is not committed

`.git/index.lock` exists and the sandbox cannot delete it (`Operation not permitted`). This
is the same blocker as the Phase 6 session. All changes are on disk and verified.

**On the owner machine, in PowerShell:**

```powershell
cd C:\Users\x\sports-risk-nlp
# Close VS Code first if the lock persists; kill any stray git processes.
Remove-Item -LiteralPath ".git\index.lock" -Force

.\.venv\Scripts\Activate.ps1

# --- validate ---
pytest                                            # expect 130/130 on 3.11
ruff check src/ scripts/ tests/                   # expect: All checks passed!
ruff format --check src/ scripts/ tests/
python scripts\run_ingestion.py --demo-refusal    # expect: Phase 7 gate: PASSED
python scripts\run_benchmark_audit.py             # expect: Benchmark audit: PASSED
pre-commit run --all-files

# --- commit ---
git add -A
git commit -m "Phase 7: ingestion pipeline with allow-list enforcement, provenance and time-aware metadata

- src/ingestion/: fail-closed allow-list, structural provenance, RawStore, A2 generator
- src/evaluation/: template-disjoint splits, bootstrap CIs, baselines + memorisation probe
- OPEN-012 mitigated: vocab 444->638, distinct texts 81%->97%; leakage quantified at 0.53 macro-F1
- OPEN-013: 34-case de-identification fixture with 8 over-redaction negatives
- data/raw/synth_precomp_v1: 1200 A2 synthetic records, seed 42, provenance committed
- allow-list and ethics.md version headers corrected to 1.1"
```

On 3.11 all 130 tests should pass. In the 3.10 sandbox 129/130 pass; the single failure is
`test_python_version_is_311`, which is the test working correctly.

---

## PART C - Phase 8 Brief

**Objective (from `PROJECT_PLAN.md`):** Clean, segment, and strip PII.

**Owning agent:** Harvester Agent (cheap tier), contract already defined in
`src/agents/roster.py` as `HARVESTER` (phases 7–8). Reuse it; do not build a parallel layer.

**Tasks:**

1. Implement `src/preprocessing/` - normalisation, utterance segmentation, language filter.
   Output to `data/interim/`.
2. Implement `src/preprocessing/deidentify.py` to the specification already written in
   **`docs/ethics.md` §5.1**, which is a complete table of what is removed and what typed
   placeholder replaces it (`[ATHLETE]`, `[COACH]`, `[TEAM]`, `[LOCATION]`, `[EVENT]`,
   `[ID]`, and health detail removed entirely rather than placeholdered). Placeholders are
   **typed, not blanked** - a blank destroys the linguistic structure the model needs.
3. De-identification is **not reversible**. No mapping table back to identity is created or
   stored (`docs/ethics.md` §5.2).
4. Set `deidentified: true` on records and provenance **only after** the step actually runs.
   Phase 7 deliberately left it `False` everywhere.
5. **Read OPEN-013 first.** The synthetic corpus contains no personal names by design, so
   running the de-identifier against it will trivially pass while measuring nothing. Build a
   held-out fixture in `tests/fixtures/` seeded with names, handles, teams, venues, and
   events, with expected placeholder output, so recall is actually measured. Keep it out of
   `data/raw/` - it is a test artefact, not corpus.
6. Manual audit of a stratified sample; log failures (`docs/ethics.md` §5.2).

**Gate:** Spot-check sample shows no direct identifiers remain. Given OPEN-013, treat the
fixture-based recall measurement as the real gate and say so in the write-up.

**Inputs to read first:** `docs/ethics.md` §5 (the de-identification spec - it is already
written, do not redesign it); `docs/data_sources.md` §3 (what the corpus does and does not
contain); `docs/open_issues.md` OPEN-011/012/013; `src/ingestion/` (the record schema and
store you will read from); `docs/agents.md`.

**Constraints:**

- `data/gold/` is human-owned. Agents never write there. `RawStore` already enforces this;
  the preprocessing layer must too.
- Do not weaken the allow-list enforcement path. No bypass flag, ever.
- Phase 7's `RawRecord` schema is the input contract. Extend it if needed, but keep the
  nullable temporal/context fields intact - they are contribution #3 and cannot be
  backfilled.
- Offline and deterministic. `pytest` must never be able to spend money.

**Do not start Phase 9.**

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-011** | **No real athlete text in the corpus.** Contribution #1 needs some. Three routes, all owner-actionable, all currently declined. **Now the only unmitigated high-impact item.** | **Phase 11** |
| **OPEN-004** | **Expert-rater recruitment not started.** Week 1–2 per the risk register; it is now Week 3. Headline contribution, longest lead time, least control. Pairs naturally with the A3 route in OPEN-011. | **Phase 17** |
| OPEN-013 | ~~De-identification unvalidatable~~ - **fixture delivered**; Phase 8 must now use it and report precision/recall/exact-match per difficulty band. | **Phase 8** (next) |
| OPEN-012 | ~~Vocabulary too small~~ - **substantially mitigated**; vocab 638, leakage quantified, template-disjoint splits mandatory. Re-run the audit once the transformer exists. | Phase 14 (monitored) |
| OPEN-008 | No `OPENROUTER_API_KEY` in `.env`. | Phase 10 |
| OPEN-007 | CrewAI backend written but never executed. | Phase 10 if chosen |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-003 | No off-machine backup. Everything exists in one place on one machine. | Standing risk |
| OPEN-009 | Model/price drift. | Any large batch |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic, fires on every file write. | - |

**The two highest-value non-code actions available today are OPEN-011 and OPEN-004, and
they are the same conversation** - recruiting an SRMIST coach or sport-psychology
practitioner who could both donate/broker pre-competition text under A3 consent *and* serve
as the Phase 17 expert rater.
