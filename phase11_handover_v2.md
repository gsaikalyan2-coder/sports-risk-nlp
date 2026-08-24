# Handover — Phase 11 (continued): Human Gold Annotation

Self-contained. A new AI session can start from this file plus the repo; no chat history
needed. **Supersedes `phase11_handover.md`**, which remains accurate for everything up to
2026-08-10 and is still worth reading for the Part D tooling design.

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
LaTeX. Annotation UI: **Potato 2.7.1**, installed separately, not vendored.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, expert-validated
interpretability; (3) a time-aware, fusion-ready design.

**Governing documents:** `CLAUDE.md` (single source of truth) and `PROJECT_PLAN.md`
(25-phase blueprint). `docs/open_issues.md` is the single source of truth for open items.

### Phase status

| Phase | Status |
|---|---|
| 1–10 | Complete (Phase 10 complete **offline only** — no live OpenRouter call has ever been made) |
| **11 — Human gold annotation** | **Tooling complete and now verified against the real annotation tool. The gate cannot pass: it needs a second human.** |
| 12 | Not started. **Do not start.** |

**The Phase 11 gate reports `UNMEASURABLE` and that is correct.** Kappa is a property of two
people. `scripts/run_annotation.py --agreement` refuses to emit a number from one pass rather
than returning a placeholder, and that refusal is the design.

### Carried-forward caveats

- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11. `datetime.UTC`
  (3.11+) is used in `src/agents/ledger.py`, `src/ingestion/allowlist.py` and
  `src/labeling/{schema,runner}.py`. Tests were run in the sandbox with an **uncommitted**
  `sitecustomize.py` shim backfilling that alias. **Re-run `pytest` on the 3.11 machine —
  expect 386/386.**
- **OPEN-002** (broken pixeltable plugin hook) fired on every file write again. Cosmetic.
- **Phase 3:** the BibTeX key `Toth2025` is historical. László Tóth was the handling editor,
  not an author. Correct authors: Nogueira, Morais, Mansell & Gomes.
- Re-running the gates rewrites `reports/eda.md`, `reports/deid_audit_sample.md`,
  `reports/labeling_run.json` and the silver `provenance.json` byte-identically or with a
  trailing-newline change. `git checkout --` those; it is noise, not a change.

---

## PART B — Current Session Summary

### B1. What this session was asked to do

Read the project, locate Phase 11, implement it, verify it. Phase 11's *tooling* was already
built and committed (`e626395`, `b992fa1`). What remained were the three items
`phase11_handover.md` Part D listed: recruit the second annotator (OPEN-025), time the
`gold_dev` pass (OPEN-026), and **exercise the ingest path against real Potato output
(OPEN-027)**. The first two need a human. The third was the implementable work, and it is
what this session did.

### B2. The headline finding: OPEN-027 was not a formality — the path was broken

`phase11_handover.md` framed OPEN-027 as *"five minutes converts an unexercised path into a
tested one."* Those five minutes were spent. **The ingest path did not work at all.**

Potato 2.7.1 was installed and its **own serialiser** (`potato.user_state_management.
UserState.save`, `potato.item_state_management.Label` / `SpanAnnotation`) used to write two
annotator passes over real `annotation/gold_dev/data/gold_dev.jsonl` items. Running the
existing gate against them:

```
$ python scripts/run_annotation.py --ingest --batch gold_dev --annotator A1
ERROR: no annotation output under .../annotation_output. Has A1 finished a pass in Potato?
```

— over a directory containing two completed passes. Three mismatches, each read out of the
installed package rather than inferred:

| `src/annotation/ingest.py` assumed | Potato 2.7.1 actually writes |
|---|---|
| `annotation_output/**/*.jsonl` | `annotation_output/<user_id>/user_state.json` |
| item key `id` | `instance_id`, and in the state file the instance id is a **dict key** |
| span carries surface text under `span` / `text` | span carries `start`/`end` **offsets only** |

**The third was the dangerous one.** `_collect_spans` *skipped* any span whose surface string
was empty. Against real output that meant **every span would have been silently dropped**, and
an item annotated with spans but no intensity would then have been counted as "not yet
annotated" rather than refused. A parser that loses evidence quietly is worse than one that
crashes, and this one lost all of it — without an error, on the artifact the entire corpus
contribution rests on.

This is the second time in this project that "written carefully against the documented
interface, just never run" turned out to mean "does not work" — the first was the Phase 6 cost
ledger (OPEN-024, quadratic, correct at n=5 and unusable at n=10,000). **OPEN-007 (CrewAI
backend) and OPEN-008 (the live labelling path) are the two remaining unexecuted paths and
should now be assumed broken until executed, not merely untested.**

### B3. The fix, and why it leaves the project better than the assumption did

**`src/annotation/potato_output.py`** (new). Reads both artifacts Potato 2.7.1 actually
writes — the authoritative per-user `user_state.json`, and the `annotations.jsonl` the
exporter produces — and normalises them to one payload shape, so `parse_annotation` has a
single input and the rubric's coupling rules are checked in exactly one place.

Span surface text is recovered by **slicing the utterance with Potato's own offsets**. That is
not a workaround; it is stronger than what was there. `SilverLabel` requires every evidence
span to be a literal substring of the utterance and enforces it with a check, because an LLM
asked to quote will paraphrase. Gold now has that property **by construction** — a slice of
the utterance cannot be anything but a substring of it. Offsets that do not land inside the
utterance are **refused, never clipped**: a clipped span is not the span the annotator marked,
and the divergence it signals (the batch and the annotated text disagreeing) is exactly what
someone needs to be told about.

`_collect_spans` now raises `SPAN_WITHOUT_SURFACE` instead of skipping. `scripts/
run_annotation.py --ingest` discovers passes via `discover_passes()` and reports the specific
case where output exists under a *different* annotator id — the likely real-world mistake,
since Potato names the directory after whatever id the person logged in with.

### B4. Verification, and the one thing it deliberately would not do

`tests/test_potato_output.py` — **13 tests, all against recorded real output** committed under
`tests/fixtures/potato/`. The fixtures were written by Potato's own serialiser and its own
exporter; nothing in them was typed by hand. That is the point: *a fixture written by the
author of the parser cannot detect the author's wrong assumption.* The previous 48 tests were
thorough and all passed against a shape the tool does not produce.

Covered: discovery at the real path; span recovery from offsets; every recovered span is a
literal substring; out-of-range, missing and whitespace-only offsets refused; unknown item ids
reported; **raw state file and JSONL export produce identical payloads**; end-to-end from two
real passes to a kappa; and the bootstrap CI correctly suppressed on a 5-item batch.

**What was deliberately not done:** the end-to-end run stops at the roster lock. `--ingest
--annotator A2` is refused because A2 is not a real person, and **that refusal was left
intact.** The agreement arithmetic is exercised in tests against a `tmp_path` store and a
fixture roster. No annotator was invented in `config/annotators.yaml`; nothing was written into
`data/gold/`, which still contains only `.gitkeep`. A verification that requires violating the
invariant it verifies is not a verification.

The rehearsal write that *did* land in `data/gold/gold_dev/` during testing was deleted, and
the working tree confirmed clean.

### B5. Gate results, all re-run at the end of the session

| Gate | Result |
|---|---|
| `scripts/run_ingestion.py --verify-only` | **Phase 7: PASSED** — 4,000 records |
| `scripts/run_preprocessing.py` | **Phase 8: PASSED** — 0 residual-risk flags |
| `scripts/run_benchmark_audit.py` | **PASSED** |
| `scripts/run_eda.py` | **Phase 9: PASSED** |
| `scripts/run_labeling.py` | **Phase 10: PASSED** — 9,302 labels verified |
| `scripts/run_annotation.py --build --batch gold_dev` | **PASSED**, with the one-annotator warning |
| `scripts/run_annotation.py --agreement` | **UNMEASURABLE** — correct; the human blocker |
| `ruff check` / `ruff format --check` | clean, 77 files |
| `pytest` | **385/386** in the sandbox; the one failure is `test_python_version_is_311` under 3.10, i.e. the test working correctly. **Expect 386/386 on the 3.11 machine.** |

Test count by file: agents 26 · annotation 48 · evaluation 34 · ingestion 53 · labeling 72 ·
**potato_output 13 (new)** · preprocessing 42 · profile 63 · smoke 17 · synonym_audit 18.

### B6. Files changed

| File | Change |
|---|---|
| `src/annotation/potato_output.py` | **new** — reads Potato 2.7.1's real artifacts |
| `tests/test_potato_output.py` | **new** — 13 tests against recorded real output |
| `tests/fixtures/potato/` | **new** — artifacts written by Potato's own serialiser, plus a README stating they are a rehearsal and not data |
| `src/annotation/ingest.py` | `ingest_passes()` added as the production path; `_collect_spans` now refuses instead of silently dropping |
| `src/annotation/__init__.py` | new exports |
| `scripts/run_annotation.py` | `--ingest` discovers real passes; better error when the id does not match |
| `docs/annotation_tooling.md` | §8b added (what running against the real tool found); limitations 5 and 6 rewritten |
| `docs/open_issues.md` | OPEN-027 resolved, with the finding recorded and the lesson generalised to OPEN-007/008 |

### B7. Commit commands

```powershell
cd C:\Users\x\sports-risk-nlp
Remove-Item -LiteralPath ".git\index.lock" -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\Activate.ps1

# verify before committing -- expect 386/386 on 3.11
pytest
ruff check src/ scripts/ tests/
ruff format --check src/ scripts/ tests/
python scripts\run_ingestion.py --verify-only
python scripts\run_preprocessing.py
python scripts\run_benchmark_audit.py
python scripts\run_eda.py
python scripts\run_labeling.py
python scripts\run_annotation.py --status

# the gate re-runs rewrite these byte-identically or add a trailing newline; that is noise
git checkout -- reports/eda.md reports/deid_audit_sample.md `
                reports/labeling_run.json data/processed/silver/

# 1 -- the fix
git add src/annotation/potato_output.py src/annotation/ingest.py `
        src/annotation/__init__.py scripts/run_annotation.py
git commit -m "fix(annotation): the Potato ingest path did not work against real Potato

- OPEN-027 was raised as 'the parser has never met real Potato output; five
  minutes converts an unexercised path into a tested one'. Those five minutes
  were spent and the path was broken in three places
- Potato 2.7.1 writes annotation_output/<user_id>/user_state.json, keys items
  by instance_id, and records spans as start/end OFFSETS with no surface text.
  ingest.py expected a per-annotator .jsonl, an 'id' key, and a 'span' string
- --ingest therefore reported 'no annotation output' over two completed passes
- worse: _collect_spans SKIPPED any span with no surface text, so every span
  would have been silently dropped and the item then miscounted as
  unannotated. Evidence lost with no error, on the artifact contribution #1
  rests on. It now raises SPAN_WITHOUT_SURFACE
- potato_output.py recovers spans by slicing the utterance with Potato's own
  offsets, which makes 'evidence spans are literal substrings' structural on
  the gold side rather than procedural -- a slice cannot be a paraphrase.
  Out-of-range offsets are refused, never clipped
- the roster lock was NOT relaxed to make an end-to-end run possible"

# 2 -- the tests, and the recorded artifacts that make them meaningful
git add tests/test_potato_output.py tests/fixtures/potato/
git commit -m "test(annotation): 13 tests against output Potato itself wrote

- fixtures produced by potato 2.7.1's own UserState.save() and its own JSONL
  exporter, not by hand. A fixture written by the parser's author cannot
  detect the author's wrong assumption; the previous 48 tests were thorough
  and all passed against a shape the tool does not produce
- asserts the raw state file and the export yield identical payloads, that
  every recovered span is a literal substring, and that two real passes reach
  a kappa end-to-end
- runs against a tmp_path store and a fixture roster. No annotator was
  invented in config/annotators.yaml and nothing was written to data/gold/"

# 3 -- the record
git add docs/open_issues.md docs/annotation_tooling.md
git commit -m "docs: OPEN-027 resolved; generalise the lesson to OPEN-007/008

- second time in this project that 'written carefully, never run' meant
  'broken' -- the first was the Phase 6 ledger (OPEN-024), correct at n=5 and
  unusable at n=10,000. The CrewAI backend and the live labelling path are the
  two remaining unexecuted paths and should be assumed broken until executed
- annotation_tooling.md gains 8b, and limitation 5 is rewritten: Potato output
  being version-coupled is now a demonstrated risk, not a theoretical one.
  tests/fixtures/potato/ must be regenerated if POTATO_VERSION is raised"

# 4 -- the handover
git add phase11_handover_v2.md
git commit -m "docs: Phase 11 handover v2 -- tooling verified, blocker unchanged"

git push
```

---

## PART C — What Phase 11 needs next

**No code can close the top item, and it has now been deferred across six phases.**

### 1. Recruit the second annotator (OPEN-025). This is the phase.

`onboarding/README.md` is the brief, ready to hand over. `config/annotators.yaml` has the A2
entry commented out with the reasoning. Uncomment it only when a real person has said yes.

**Make it the same conversation as OPEN-011 and OPEN-004.** One SRMIST coach or
sport-psychology practitioner could broker pre-competition athlete text under an A3 consent
basis (OPEN-011), serve as the second annotator (OPEN-025), *and* be the Phase 17 expert rater
(OPEN-004). Three open items, one solution, and the two oldest of them are the project's
highest-impact risks. A test asserts the roster has exactly one annotator — **if it starts
failing, someone has been recruited; update this handover, do not "fix" the test.**

### 2. Time the `gold_dev` calibration pass (OPEN-026).

Ten intensity questions plus a span pass, per item, per annotator, over 400 `gold_eval` items,
has never been costed. `CLAUDE.md` sec.3 freezes the construct set at Phase 12 *after checking
annotation burden*. Do not guess it — the generator supports a `constructs` filter and
`--graded-only` so the taxonomy can be trimmed on evidence rather than by feel.

### 3. Then the annotation itself, in this order, which is load-bearing.

`gold_dev` (100 items) → compare → argue about the rubric → amend
`docs/annotation_guidelines.md` → **only then** `gold_eval` (400). `gold_dev` is drawn from
training-side templates precisely so that burning it on rubric arguments costs zero evaluation
power. An item read during an argument about the rubric is no longer an independent
measurement.

### 4. Separately and in parallel: decide the live labelling run (OPEN-023).

The Phase 10 projection is **$17.46 against a $20 enforced cap** — 87% of the cap for one pass,
because `config/model_routing.yaml`'s "$1.12 per pass" assumed a ~400-token prompt and the real
rubric is 3,946. Recommended: `refresh_pricing.py --check`, then `run_labeling.py --live
--pricing-checked --limit 50` (costs pennies) to measure the cache-read rate, the real
escalation rate and the real output length, then re-project. If it is still uncomfortable,
shorten the rubric or reduce the escalation fraction — **do not raise `monthly_cap_usd`.**

### The rules that make the kappa meaningful — unchanged and non-negotiable

- **100% double-annotated.** Both annotators do all 400 `gold_eval` items; that is what makes a
  per-construct Cohen's kappa computable.
- **Independently.** Guidelines sec.7: never discuss specific records before both passes are
  complete. Discussing them inflates agreement, makes the statistic worthless, and cannot be
  undone.
- **`generation_spec` is stripped from every candidate** by the Phase 9 sampler. Do not
  reintroduce it. An annotator who can see what was planted is not an annotator.
- **Never compute a kappa between silver and a human.** Silver labels for these same utterances
  exist because the whole corpus was labelled. Silver-vs-human measures *the labeller* and is
  reported as such at Phase 14. Agreement is between two people.
- **Adjudicate after both passes**, against the document. If adjudication reveals a rule the
  document does not cover, amend the document and re-run the affected batch — do not settle it
  verbally.
- Per-construct kappa is reported **with a bootstrap interval, never a bare point estimate**
  (`PROJECT_PLAN.md` Phase 11 gate). Already implemented; the CI is suppressed below 20 items
  by design.

### Inherited constraints

- `data/gold/` is human-owned. `src/annotation/store.py` is the only sanctioned writer and its
  four locks are documented in `docs/annotation_tooling.md` §6. The other three stores refuse
  the root outright.
- `pytest` must never be able to spend money; `mode: offline` stays the default.
- Offline and deterministic from a fresh clone; fixed seeds.
- The allow-list enforcement path is never weakened and never gains a bypass flag.
- Every agent writes a run log to `logs/`; every call writes cost to `logs/cost_ledger.csv`.
- Never commit secrets. Keys live only in `.env` (gitignored).

**Do not start Phase 12.**

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-025** | **No second annotator.** Kappa is undefined with one person, so contribution #1 does not exist. | **Phase 11 (now)** |
| **OPEN-011** | **No real athlete text.** The corpus is 100% synthetic while contribution #1 claims an athlete-text corpus. | **Phase 11 (now)** |
| **OPEN-004** | **No expert raters recruited.** Headline contribution, longest lead time, least control. | Phase 17 |
| **OPEN-023** | Phase 10's cost estimate is low by ~10×; a full live pass projects at 87% of the monthly cap. Owner decision. | now |
| **OPEN-026** | Annotation burden unmeasured; the Phase 12 taxonomy freeze depends on it. | Phase 12 |
| **OPEN-008** | Partially resolved. The key exists; **no live call has ever been made.** Assume broken until executed. | Phase 10's live pilot |
| **OPEN-007** | CrewAI backend written but never executed. **Assume broken until executed.** | — |
| OPEN-027 | ~~Ingest never run against real Potato output~~ — **CLOSED this session, and it was broken.** | closed |
| OPEN-022 | Template era not recorded, so the sharpest shared-ancestry probe cannot be run. | Phase 18 |
| OPEN-021 | The lexicon baseline is not independent of the corpus. A paper obligation. | Phase 18 |
| OPEN-024 | ~~Ledger was O(n²)~~ — **CLOSED at Phase 10.** | closed |
| OPEN-019 | `generation_spec` replicated per utterance (×~2.3). | monitored |
| OPEN-009 | Model/price drift. Unverified — the sandbox has no route to openrouter.ai. | any large batch |
| OPEN-012 | Vocabulary bounded by the template bank; 860 types. | Phase 14 (monitored) |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic, fires on every file write. | — |

**OPEN-025, OPEN-011 and OPEN-004 are one conversation.** Phase 11 is where OPEN-011 stops
being a risk and becomes a limitation printed in the paper: annotating 400 synthetic
utterances produces a real inter-annotator agreement figure over text no athlete ever said.
The paper must frame it that way, and the sooner a practitioner is in the room, the smaller
that limitation gets.
