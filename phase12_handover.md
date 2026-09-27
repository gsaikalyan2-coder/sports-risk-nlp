# Handover - Phase 12: Label Validation & Taxonomy Refinement

Self-contained. A new AI session can start from this file plus the repo; no chat history
needed. Supersedes nothing - read alongside `phase11_handover_v2.md`, which remains the
authority on the annotation tooling.

---

## PART A - Project Summary

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
LaTeX. Annotation UI: Potato 2.7.1, installed separately, not vendored.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, expert-validated
interpretability; (3) a time-aware, fusion-ready design.

**Governing documents:** `CLAUDE.md` (single source of truth) and `PROJECT_PLAN.md`
(25-phase blueprint). `docs/open_issues.md` is the single source of truth for open items.

### Phase status

| Phase | Status |
|---|---|
| 1–10 | Complete (Phase 10 complete **offline only** - no live OpenRouter call has ever been made) |
| 11 - Human gold annotation | Tooling complete and verified against real Potato output. **Gate UNMEASURABLE**: kappa needs a second human |
| **12 - Label validation & taxonomy refinement** | **Tooling complete, tested and gated. `--burden` and `--propose` run today and produce real Phase 12 inputs. `--refine` reports BLOCKED, because it consumes gold that does not exist** |
| 13 | Not started |

**Phases 11 and 12 are now blocked on the same missing person.** That is the single most
important fact in this file. `OPEN-025` has been deferred across seven phases and is now the
critical path: every remaining phase that consumes gold inherits the block, and no amount of
code shortens it.

### Carried-forward caveats

- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11. Tests were run
  with an **uncommitted** `sitecustomize.py` shim backfilling `datetime.UTC`. **That file is
  still in the working tree and must be deleted before committing** - the sandbox could not
  remove it (`Operation not permitted`). `git status` will show it as untracked.
- A stale `.git/index.lock` has appeared again; `Remove-Item -LiteralPath ".git\index.lock"`
  before the first git command.
- **The Phase 11 work is still uncommitted.** `src/annotation/potato_output.py`,
  `tests/test_potato_output.py`, `tests/fixtures/potato/` and the `ingest.py` fix all show as
  new/modified. Commit those first, with the messages in `phase11_handover_v2.md` §B7, before
  the Phase 12 commits below.
- **OPEN-002** (broken pixeltable plugin hook) fired on every file write again. Cosmetic.
- Re-running the earlier gates rewrites `reports/eda.md`, `reports/deid_audit_sample.md`,
  `reports/labeling_run.json` and the silver `provenance.json` byte-identically or with a
  trailing-newline change. `git checkout --` those; it is noise, not a change.

---

## PART B - Current Session Summary

### B1. What this session was asked to do

Read the project, locate Phase 12, implement it, verify it. `PROJECT_PLAN.md` defines Phase 12
as: *analyse disagreement patterns; refine `taxonomy.yaml`/guidelines; re-label affected
silver; deliver a v2 taxonomy + changelog; gate on "post-refinement agreement improves or is
justified; dataset frozen for modeling."*

`phase11_handover_v2.md` ends with **"Do not start Phase 12."** That instruction was correct
and it was also incomplete, which is the finding this session turned on.

### B2. The finding: Phase 12 is two halves, and only one of them is blocked

`config/taxonomy.yaml` freezes the construct set at Phase 12 *"after checking **annotation
burden** and **inter-annotator agreement**."* Two inputs. The project had been treating the
phase as one blocked thing because agreement is blocked.

**Burden is not blocked.** It depends on the taxonomy and the sample size, both of which exist.
And it is not optional: `OPEN-026` says the freeze *"must be made against a measured burden,
not a feeling"*, and nothing in the project estimated it. So the phase decomposes cleanly:

| Half | Needs | Status |
|---|---|---|
| agreement analysis (`--refine`) | `data/gold/`, i.e. a second annotator | **BLOCKED - exits 1** |
| burden analysis (`--burden`) | the taxonomy | **runs today** |
| change costing (`--propose`) | a candidate taxonomy + silver | **runs today** |

Building only the blocked half and stopping would have left the freeze criterion half-built
for a reason that applies to the other half and not to this one.

### B3. What was built

**`src/taxonomy/`** - previously an empty package, now the Phase 12 home.

**`burden.py` - the arithmetic half of OPEN-026.** Counts the decisions
`potato_project.py` actually puts in front of an annotator, derived from the *same*
`taxonomy.yaml` that generates the Potato schemes so the estimate cannot drift from the
instrument. Under the current 10 constructs:

> **1.82 min/item → 12.11 h per annotator → 24.22 person-hours for `gold_eval`, across
> 7 sittings** at a 2-hour fatigue threshold.

Three design choices carry weight here:

1. **The estimate declares itself an estimate, everywhere.** `TimingModel.measured` is `False`
   and `basis` reads `UNMEASURED ASSUMPTION (OPEN-026)`; the Markdown opens with
   `**ESTIMATE, NOT A MEASUREMENT.**` and the JSON carries `estimate_is_measured`. An
   undisclosed assumption becomes a citation, and this one would end up in a paper describing
   how a corpus was built.
2. **`from_measurement()` refuses an unattributed number.** Passing
   `--measured-minutes-per-item` without `--measured-source` exits 2. A number with no
   provenance is not an improvement on a declared assumption.
3. **Marginal cost excludes the shared span pass.** Dropping a construct does not remove the
   reading of the utterance, so each construct is charged only its own intensity judgement
   (≈1.33 h over `gold_eval`, 5.5%). Charging a share of the shared cost would overstate what
   a drop saves, and overstating that is how a taxonomy gets trimmed for no gain.

The fatigue threshold is not a comfort metric. `OPEN-026` names the failure exactly: a rushed
second half produces a worse dataset than a careful smaller one, **and the damage is invisible
in the kappa** - two tired annotators drift toward the same defaults and *agree more*. Burden
is the only guard against a kappa that looks good because both people gave up.

**`refinement.py` - disagreement → repair.** A kappa of 0.31 is compatible with at least four
different fixes and they are not interchangeable, so the module **decomposes before it
recommends**: presence disagreements vs intensity-only vs span-only, plus cross-construct
confusion pairs. Verdicts are `KEEP` / `REVISE_RUBRIC` / `REVISE_INTENSITY_ANCHORS` /
`REVISE_SPAN_RULE` / `MERGE_CANDIDATE` / `DROP_CANDIDATE` / `UNDER_SAMPLED`.

Two guards are the point of the module:

- **`UNDER_SAMPLED` exists so a sampling defect cannot be recorded as a taxonomy defect.** A
  construct nobody marked has an undefined kappa; it is tested *first*, before any rule that
  would read that undefined number as unreliability.
- **A rare construct with a low kappa returns `KEEP`, not `DROP`.** The obvious Phase 12 move
  is to drop whatever scores badly. That optimises the headline kappa and damages the paper,
  because the worst-scoring constructs are the rare, clinically loaded ones - `burnout_signal`
  above all - which are exactly what a reviewer cares about. The kappa paradox is reported, not
  acted on.

`confusion_pairs()` finds the merge signal that **no single construct's kappa can show**:
`perceived_stress` and `cognitive_anxiety` can each score moderately while the same items swap
between them.

**`versioning.py` - the changelog and what a change costs.** Diffs two taxonomies and
classifies every difference by whether it invalidates silver. The load-bearing entry:

> **An added construct invalidates the entire corpus.** The instinct is that adding is safe. It
> is not - a v2 label is *silent* about a new construct, and treating silence as "not present"
> fabricates a negative on every utterance, worst precisely where the class is rare.

Verified against real silver: a definition edit to `cognitive_anxiety` invalidates 1,036 of
6,200 labels (16.7%) across **873 distinct texts**; adding one construct invalidates 100% across
6,444 distinct texts. The distinct-text count is reported beside the record count because Phase
9 measured 87.4% duplication and quoting records alone would overstate the bill several-fold -
which could talk the owner out of a change that is actually cheap.

`Changelog` refuses a version that does not advance, and refuses a change with no stated
reason: the gate is *"agreement improves **or is justified**"*, and an unjustified change
satisfies neither half. Reworded examples are flagged `COSMETIC` and surfaced for owner
confirmation rather than auto-approved - whether a rewording changed the *question* is a
judgement about meaning, and no diff can make it.

**`scripts/run_taxonomy_refinement.py`** - the Phase 12 gate: `--burden`, `--refine`,
`--propose`, `--status`. Offline, free, deterministic.

**Nothing in Phase 12 writes `config/taxonomy.yaml`.** Every output is a recommendation to the
owner (`CLAUDE.md` sec.10), and a test asserts the file is byte-identical after the gate runs.
A construct set a script can quietly shrink is not frozen, and "frozen at Phase 12" is a claim
the paper makes.

### B4. Verification

`tests/test_taxonomy.py` - **30 tests, all passing.** The ones that matter assert refusals:

- the default timing model declares itself unmeasured, and the report says so in its own text
- a measurement with no source is refused
- marginal cost excludes the shared span pass
- a degenerate construct is `UNDER_SAMPLED`, never `DROP_CANDIDATE`
- a rare low-kappa construct is `KEEP` with "kappa paradox" in the rationale
- an added construct invalidates the whole corpus; a whitespace reflow invalidates nothing
- `relabel_scope` counts distinct texts, not just records
- a version bump with no reason is refused
- **`--refine` exits 1 with `BLOCKED` and `OPEN-025` when no gold exists**
- **`config/taxonomy.yaml` is byte-identical after `--status` and `--burden`**
- gold labels still refuse a machine author - Phase 12 reads gold and must not become a way to
  write it

**What was deliberately not done:** no annotator was invented, nothing was written to
`data/gold/`, and `--refine` was not exercised end-to-end against fabricated gold. The
refinement path's *arithmetic* is exercised in tests against synthetic `ConstructAgreement`
objects, which is a different claim from "it has been run on real annotations" - and this
project has now twice found that a carefully-written, never-executed path was broken
(OPEN-024, OPEN-027). **Treat `--refine` as unexecuted until it runs on real gold.**

### B5. Gate results, all re-run at the end of the session

| Gate | Result |
|---|---|
| `scripts/run_ingestion.py --verify-only` | **Phase 7: PASSED** |
| `scripts/run_preprocessing.py` | **Phase 8: PASSED** |
| `scripts/run_eda.py` | **Phase 9: PASSED** |
| `scripts/run_labeling.py` | **Phase 10: PASSED** - 9,302 labels |
| `scripts/run_annotation.py --status` | unchanged; both batches NOT computable |
| `scripts/run_taxonomy_refinement.py --status` | v2, 10 constructs; burden computed, agreement blocked |
| `scripts/run_taxonomy_refinement.py --burden` | **0** - writes `reports/annotation_burden.{md,json}` |
| `scripts/run_taxonomy_refinement.py --propose` | **0** with a reason, **2** without |
| `scripts/run_taxonomy_refinement.py --refine` | **1 - BLOCKED**, correct |
| `ruff check` / `ruff format --check` | clean, 82 files |
| `pytest` | **415/416**; the one failure is `test_python_version_is_311` under sandbox 3.10, i.e. the test working. **Expect 416/416 on the 3.11 machine.** |

Test count by file: agents 26 · annotation 48 · evaluation 34 · ingestion 53 · labeling 72 ·
potato_output 13 · preprocessing 42 · profile 63 · smoke 17 · synonym_audit 18 ·
**taxonomy 30 (new)**.

### B6. Files changed

| File | Change |
|---|---|
| `src/taxonomy/burden.py` | **new** - annotation burden, marginal cost, fatigue threshold |
| `src/taxonomy/refinement.py` | **new** - disagreement decomposition, confusion pairs, verdicts |
| `src/taxonomy/versioning.py` | **new** - taxonomy diff, changelog, silver re-label scope |
| `src/taxonomy/__init__.py` | was empty - now the package surface |
| `scripts/run_taxonomy_refinement.py` | **new** - the Phase 12 gate |
| `tests/test_taxonomy.py` | **new** - 30 tests |
| `reports/annotation_burden.{md,json}` | **new** - generated |
| `docs/open_issues.md` | OPEN-026 half-closed, with what closes the other half |
| `PROJECT_PLAN.md` | status board brought current through Phase 12 |

### B7. Commit commands

```powershell
cd C:\Users\x\sports-risk-nlp
Remove-Item -LiteralPath ".git\index.lock" -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "sitecustomize.py" -Force -ErrorAction SilentlyContinue  # sandbox shim
.\.venv\Scripts\Activate.ps1

# COMMIT THE PHASE 11 WORK FIRST -- see phase11_handover_v2.md B7. It is still uncommitted.

# verify -- expect 416/416 on 3.11
pytest
ruff check src/ scripts/ tests/
ruff format --check src/ scripts/ tests/
python scripts\run_taxonomy_refinement.py --status
python scripts\run_taxonomy_refinement.py --burden
python scripts\run_taxonomy_refinement.py --refine   # expect exit 1, BLOCKED

git checkout -- reports/eda.md reports/deid_audit_sample.md `
                reports/labeling_run.json data/processed/silver/

# 1 -- the modules
git add src/taxonomy/
git commit -m "feat(taxonomy): Phase 12 -- burden, disagreement analysis, versioning

- taxonomy.yaml freezes the construct set at Phase 12 'after checking annotation
  burden AND inter-annotator agreement'. Agreement is blocked on OPEN-025;
  burden is not blocked by anything and had never been computed
- burden.py: 1.82 min/item -> 12.1 h per annotator -> 24.2 person-hours for
  gold_eval, 7 sittings. The estimate declares itself unmeasured in its own
  text and from_measurement() refuses a number with no source -- an
  undisclosed assumption becomes a citation, and this one describes how the
  corpus was built. Marginal cost charges only the per-construct intensity
  judgement, never the shared span pass: overstating what a drop saves is how
  a taxonomy gets trimmed for no gain
- refinement.py: decomposes disagreement (presence / intensity / span /
  cross-construct confusion) before recommending, because one kappa is
  compatible with four different repairs. UNDER_SAMPLED exists so a sampling
  gap cannot be recorded as a taxonomy problem, and a rare low-kappa construct
  returns KEEP -- dropping the clinically loaded constructs optimises the
  headline number and weakens the paper
- versioning.py: an ADDED construct invalidates the whole corpus. A v2 label is
  silent about it and silence is not a negative; treating it as one fabricates
  a negative on every utterance, worst where the class is rare. Re-label scope
  is reported in distinct texts as well as records -- Phase 9 measured 87.4%
  duplication and the record count overstates the bill several-fold
- nothing here writes config/taxonomy.yaml; the construct set is an owner
  decision (CLAUDE.md sec.10)"

# 2 -- the gate
git add scripts/run_taxonomy_refinement.py reports/annotation_burden.md `
        reports/annotation_burden.json
git commit -m "feat(phase12): the taxonomy refinement gate

- --burden and --propose run today; --refine reports BLOCKED and exits 1
- routing around the block would be worse than waiting: analysing silver asks
  whether the LLM agrees with itself, analysing one human pass asks whether a
  person agrees with themselves, and both would be recorded as if either were
  a reason to change a construct definition"

# 3 -- the tests
git add tests/test_taxonomy.py
git commit -m "test(taxonomy): 30 tests, most of them asserting a refusal

- the estimate says it is an estimate; an unattributed measurement is refused;
  a degenerate construct is UNDER_SAMPLED not DROP_CANDIDATE; a rare low-kappa
  construct is KEEP; an added construct invalidates everything; a version bump
  with no reason is refused; --refine exits BLOCKED without gold; and
  config/taxonomy.yaml is byte-identical after the gate runs"

# 4 -- the record
git add docs/open_issues.md PROJECT_PLAN.md phase12_handover.md
git commit -m "docs: OPEN-026 half-closed; status board current through Phase 12

- the arithmetic exists, the stopwatch does not. Closing it needs
  --measured-minutes-per-item from a timed gold_dev pass
- Phases 11 and 12 are now blocked on the same missing person (OPEN-025),
  which makes recruiting the critical path"

git push
```

---

## PART C - What Phase 12 needs next

### 1. Recruit the second annotator (OPEN-025). Still the phase. Still one conversation.

Two phases are now blocked on it instead of one, and it has been deferred across seven.
`onboarding/README.md` is the brief, ready to hand over. `config/annotators.yaml` has the A2
entry commented out.

**One SRMIST coach or sport-psychology practitioner closes three items:** OPEN-011 (broker
pre-competition athlete text under an A3 consent basis), OPEN-025 (second annotator), OPEN-004
(Phase 17 expert rater). A test asserts the roster has exactly one annotator - **if it starts
failing, someone has been recruited; update this handover, do not "fix" the test.**

### 2. Time the `gold_dev` pass and close OPEN-026 properly.

The projection is now concrete enough to act on: **12.1 h per annotator for `gold_eval`, over
7 sittings.** If that is unreasonable, the lever is `potato_project.py`'s `constructs` filter,
and the marginal table says each construct returns ≈1.33 h. **Do not trim on the estimate.**
Run the pass, time it, then:

```
python scripts/run_taxonomy_refinement.py --burden `
  --measured-minutes-per-item <n> --measured-source "gold_dev, A1, 2026-08-xx, stopwatch"
```

### 3. Then, and only then, the refinement itself.

`gold_dev` (100) → both annotators → `--agreement` → **`--refine`** → argue about the rubric
against the verdict table → amend `docs/annotation_guidelines.md` → `--propose` a v3 taxonomy
to cost the change → owner decides → `--propose --write` for the changelog → **only then**
`gold_eval` (400).

`--refine` has never been run on real gold. Treat it as unexecuted, not merely untested: this
project has twice found that a carefully-written, never-run path was broken.

### 4. Separately: decide the live labelling run (OPEN-023).

Unchanged. $17.46 projected against a $20 cap. Recommended: `refresh_pricing.py --check`, then
`run_labeling.py --live --pricing-checked --limit 50` to measure the real cache-read and
escalation rates, then re-project. **Do not raise `monthly_cap_usd`.**

### The rules that make the Phase 12 decision meaningful

- **The taxonomy is an owner decision.** Nothing in `src/taxonomy/` edits it, and the test
  asserting that must not be relaxed to make an automated freeze possible.
- **Never drop a construct because it is rare.** `is_rare` and `is_degenerate` distinguish the
  kappa paradox and a sampling gap from genuine unreliability; both are `KEEP`/`UNDER_SAMPLED`
  by design. The rare constructs are the clinically loaded ones a reviewer cares about.
- **Every change gets a written reason**, or the gate's "or is justified" clause is unmet.
- **Price the re-labelling before adopting a change**, in distinct texts, and deduplicate
  before the API call as Phase 10 does.
- **An added construct means a full-corpus re-label.** No exceptions, and never infer a
  negative from an old label's silence.
- `data/gold/` is human-owned. `pytest` must never be able to spend money. Offline and
  deterministic from a fresh clone. Never commit secrets.

**Do not start Phase 13** until the dataset is frozen - a baseline trained on a taxonomy that
is still moving has to be retrained, and the number it produced in the meantime will be quoted
by someone.

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-025** | **No second annotator.** Now blocks Phases 11 **and** 12. Contribution #1 does not exist without it. | **now** |
| **OPEN-011** | **No real athlete text.** The corpus is 100% synthetic while contribution #1 claims an athlete-text corpus. | **now** |
| **OPEN-004** | **No expert raters recruited.** Headline contribution, longest lead time. | Phase 17 |
| **OPEN-023** | A full live labelling pass projects at 87% of the monthly cap. Owner decision. | now |
| **OPEN-026** | **Half closed.** Arithmetic done (12.1 h/annotator); the stopwatch is not. | Phase 12 freeze |
| OPEN-008 | Key exists; **no live call has ever been made.** Assume broken until executed. | Phase 10 live pilot |
| OPEN-007 | CrewAI backend written but never executed. **Assume broken until executed.** | - |
| OPEN-022 | Template era not recorded. | Phase 18 |
| OPEN-021 | The lexicon baseline is not independent of the corpus. A paper obligation. | Phase 18 |
| OPEN-019 | `generation_spec` replicated per utterance. | monitored |
| OPEN-009 | Model/price drift. Unverified - the sandbox has no route to openrouter.ai. | any large batch |
| OPEN-012 | Vocabulary bounded by the template bank; 860 types. | Phase 14 (monitored) |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic. | - |
| OPEN-024, OPEN-027, OPEN-003 | closed | - |

**The paper consequence, stated plainly.** Phase 12 can now show a reviewer that the construct
set was frozen against a *measured* burden and a *measured* agreement, with every candidate
change costed and every decision written down. None of that is worth anything until two people
have annotated the same 400 items. The tooling is no longer the bottleneck and has not been
for two phases.
