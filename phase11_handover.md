# Handover — Phase 11: Human Gold Annotation

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

| Phase | Status |
|---|---|
| 1–8 | Complete (see `phase10_handover.md` Part A for commits) |
| 9 — EDA & quality profiling | Complete |
| 9b — Corpus hardening | Complete |
| **10 — Weak / LLM labelling** | **Complete offline. The live path has never been run.** |
| **11 — Human gold annotation** | **NEXT** |

**Carried-forward caveats:**

- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11.
  `datetime.UTC` (3.11+) is used in `src/agents/ledger.py`, `src/ingestion/allowlist.py`
  and now `src/labeling/{schema,runner}.py`. Tests were run in the sandbox with an
  uncommitted `sitecustomize` shim backfilling that alias. **Re-run `pytest` on the 3.11
  machine to confirm natively — expect 325/325.**
- **OPEN-002** (broken pixeltable plugin hook) fired on every file write again. Cosmetic.
- **`.git/index.lock`** appeared again — Phase 6, 7, 8, 9 and now 10. Environment quirk.
- **Phase 3:** the BibTeX key `Toth2025` is historical. László Tóth was the handling editor,
  not an author. Correct authors: Nogueira, Morais, Mansell & Gomes.

---

## PART B — Current Session Summary (Phase 10)

### B1. What Phase 10 was asked to do

*Objective — produce silver labels cheaply. Tasks — the Labeling Agent labels utterances
against the taxonomy with rationale and confidence, using cheap-tier models, prompt caching
and batching; escalate low-confidence to mid tier. Deliverable — `data/processed/silver/`
plus per-shard cost logs. Gate — full corpus silver-labelled under budget, confidence
recorded per label, every call carrying a routing decision and a `logs/cost_ledger.csv`
entry, plus the Annotation-QA review queue.*

All delivered **offline**. The one thing not delivered is a live run — see B7.

### B2. What was built

`src/labeling/`, eight modules, ~1,900 lines, no new dependencies:

| Module | Responsibility |
|---|---|
| `prompt.py` | the cached rubric system prompt, built from `taxonomy.yaml` + the guidelines |
| `dedup.py` | group utterances by prompt payload; pay once per distinct prompt |
| `runner.py` | route → call → parse → escalate once → fan out; cost projection |
| `parser.py` | strict validation; refuses malformed output rather than coercing it |
| `schema.py` | `SilverLabel` / `ConstructLabel` with the invariants enforced in `__post_init__` |
| `store.py` | the only write path into `data/processed/silver/` |
| `qa.py` | the Annotation-QA pass → `logs/review_queue.jsonl` |
| `ancestry.py` | the OPEN-021 shared-ancestry probe, one level up |

Plus `scripts/run_labeling.py` (the gate), `tests/test_labeling.py` (72 tests), and
`docs/labeling.md`.

**The invariants that are structural rather than procedural**, mirroring how
`InterimRecord` refuses `deidentified=False`:

- a `SilverLabel` cannot exist without a confidence in [0,1] and a non-empty rationale;
- **every evidence span must be a literal substring of the utterance.** An LLM asked to
  quote will paraphrase given the chance, and a paraphrased span silently breaks span-level
  explanation at Phase 16;
- the interpretation modifier cannot attach to an absent anxiety construct;
- abstention is representable and is not an error;
- `SilverWriter` refuses any row containing `generation_spec`, and `SilverStore` refuses a
  root inside `data/gold/` with the same `GOLD_IS_HUMAN_OWNED` code the other two stores use.

### B3. Four measured findings, three of which contradict a document

**1. The 31% deduplication saving does not survive the requirement to pass parent context.**
Recomputed on the actual corpus:

| Dedup key | Distinct prompts | Saving |
|---|---|---|
| utterance text alone | 6,444 | 30.7% |
| (utterance, parent record) | 9,185 | 1.3% |
| **(utterance, parent record, days-to-competition) — used** | **9,260** | **0.5%** |

636 utterance texts appear in more than one distinct parent record, and they are the
frequent ones. Nearly all of the 31% was exactly the strings whose context differs. The key
is a hash of the bytes sent to the model, so "same key implies same answer" holds by
construction. The saving was given up deliberately; `--no-context` keeps the abandoned
option measurable as an ablation.

**2. `config/model_routing.yaml`'s cost estimate is low by an order of magnitude.**
It says "about $1.12 for a full labeling pass", assuming "~400 input tokens (rubric is
cached)". The assembled rubric is **3,946 estimated tokens**. Measured projection for the
full corpus: **$17.46 against a $20 enforced cap** — $4.99 cheap-tier plus $12.47 of
assumed escalation, with prompt caching given zero credit. Raised as **OPEN-023**.
**This is an owner decision and is the first thing Part C asks for.**

**3. The cost ledger was O(n²) and had never been run at scale.** `record()` called
`_ensure_header()` (mkdir + exists + stat) and `spend_this_month()` (a full CSV re-read) on
every append. cProfile: `_ensure_header` was **11.2 of 11.9 seconds** on a 600-prompt run.
The first full run did not finish. Fixed — month total cached and maintained incrementally
under the append lock, header checked once per instance — and a test asserts the cached
total equals a fresh read. Logged as **OPEN-024 (resolved)**.

**4. The Phase 9b era comparison cannot be reproduced for the labeller.** The sharpest
OPEN-021 instrument was "Phase 7 templates vs Phase 9b templates". `template_id` is
`construct:label:index` with index 0–4 across all 150 templates, because Phase 9b
restructured the bank rather than appending to it. Nothing records when a template was
written. `ancestry.py` falls back to lexical overlap with `positive_examples`, which is a
coarser proxy. Raised as **OPEN-022**.

### B4. Two tests caught me, and neither was weakened

1. **I broke four existing tests in `tests/test_agents.py`** by widening
   `OfflineLLM._synthesise(kind, rng)` to take the user prompt. Those tests subclass
   `OfflineLLM` and override that method with the two-argument signature, and they were
   right: `_synthesise(kind, rng)` is the established contract for "make an answer of this
   shape out of thin air", and a shape that needs the prompt is a different job. **The
   fix went into `llm.py`, not the tests** — the new "silver" shape is dispatched to a
   separate `_synthesise_silver(user, rng)` and the old signature is untouched.
2. **My own test fixtures were wrong twice** — `Provenance` field names and
   `IngestionRefused.reason_code`. Both fixed in the tests, because there the tests were
   the thing that was wrong.
3. **ruff caught a late-binding closure** (B023) in `ancestry.py`. The behaviour happened
   to be correct because the closure was called inside its own loop iteration; it was
   lifted to a module-level function anyway, because a function that depends on when it is
   called is a bug waiting for someone to store it in a list.

### B5. Gate results, all re-run at the end of the session

| Gate | Result |
|---|---|
| `scripts/run_ingestion.py --verify-only` | **Phase 7: PASSED** — 4,000 records |
| `scripts/run_preprocessing.py` | **Phase 8: PASSED** — 9,302 utterances, 0 dropped, fixture 34/34 exact, leak 0% |
| `scripts/run_benchmark_audit.py` | **PASSED** — probe drop +0.520, lexicon +0.108 |
| `scripts/run_eda.py` | **Phase 9: PASSED** — gold_eval 400, 0/10 below floor |
| `scripts/run_labeling.py` | **Phase 10: PASSED** — see below |
| `ruff check` / `ruff format --check` | clean, 65 files |
| `pytest` | **324/325** — the one failure is `test_python_version_is_311` under the sandbox's 3.10, i.e. the test working correctly |
| Determinism | two consecutive runs → identical `review_queue.jsonl`; `silver.jsonl` identical once `run_id` and `labeled_on` are stripped (both are per-run by design) |

**Phase 10 gate, offline, generator v1.4 corpus:**

| | |
|---|---|
| Utterances labelled | **9,302 / 9,302** |
| Distinct prompts | 9,260 (42 copied, 0.5%) |
| Calls made | 12,893 (9,260 cheap + 3,633 mid escalations) |
| Failures (unparseable after escalation) | **0** |
| Abstention rate | 0.333 |
| **Actual cost** | **$0.000000** — offline; nothing was spent |
| Projected live cost | $17.46 (upper bound, no cache credit) |
| Review queue | 4,944 rows over 4,427 distinct utterances |

**The abstention and escalation rates are artefacts of the stub's random number generator,
not findings.** Do not quote them.

Review queue by reason: `ESCALATED_AND_UNCERTAIN` 3,652 · `BURNOUT_ASSERTED` 1,087 ·
`SPAN_IS_WHOLE_UTTERANCE` 205. Every burnout assertion is queued, not a sample of them —
it is the most clinically loaded construct in the taxonomy.

### B6. API key handling

The owner added `OPENROUTER_API_KEY` to `.env` themselves. **It was verified only as set
and non-empty; the value was never read, printed, logged, or written anywhere.**
`git check-ignore -v .env` matches `.gitignore:2`. No key appears in any file, commit,
report, log, or message produced this session.

### B7. What did NOT happen, and it is the most important line in this handover

**Not one live OpenRouter call has been made.** Two blockers, both environmental:

1. **The agent sandbox has no route to `openrouter.ai`** — `scripts/refresh_pricing.py
   --check` returns `Tunnel connection failed: 403 Forbidden`. So the Step 1 catalogue
   check could not be performed here, and OPEN-009 remains unverified for this run.
2. Consequently `--live` was never attempted. `scripts/run_labeling.py` refuses `--live`
   without `--pricing-checked` precisely so this cannot be skipped by accident.

**OPEN-008 is therefore only partially closed.** `phase8_handover.md` records OPEN-007 as
exactly the mistake of shipping an unexecuted path; an unexecuted live labelling path is
that same mistake with a different module name.

### B8. Files changed

| File | Change |
|---|---|
| `src/labeling/{__init__,schema,prompt,parser,dedup,runner,store,qa,ancestry}.py` | **new** |
| `scripts/run_labeling.py` | **new** — the Phase 10 gate |
| `tests/test_labeling.py` | **new** — 72 tests |
| `docs/labeling.md` | **new** — prompt design, routing, schema, honest limitations |
| `src/agents/llm.py` | `_synthesise_silver` added; `_synthesise` signature preserved |
| `src/agents/ledger.py` | O(n²) fix: cached month total, header checked once |
| `docs/open_issues.md` | OPEN-008 partially resolved; OPEN-022/023/024 raised |
| `.gitignore` | silver JSONL and review queue ignored; manifest + provenance kept |
| `data/processed/silver/synth_precomp_v1/` | **new** — 9,302 labels, manifest, provenance |
| `reports/labeling_run.json` | **new** |

### B9. Commit commands

```powershell
cd C:\Users\x\sports-risk-nlp
Remove-Item -LiteralPath ".git\index.lock" -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\Activate.ps1

# verify before committing -- expect 325/325 on 3.11
pytest
ruff check src/ scripts/ tests/
ruff format --check src/ scripts/ tests/
python scripts\run_ingestion.py --verify-only
python scripts\run_preprocessing.py
python scripts\run_benchmark_audit.py
python scripts\run_eda.py
python scripts\run_labeling.py

# the gate re-runs append a trailing newline to these two; that is noise, not a change
git checkout -- reports/eda.md reports/deid_audit_sample.md

# 1 -- the Phase 6 defects Phase 10's volume exposed
git add src/agents/ledger.py src/agents/llm.py
git commit -m "fix(agents): ledger was O(n^2); offline stub learns the silver shape

- CostLedger.record() re-read and re-parsed the whole CSV, and re-ran mkdir +
  exists + stat, on EVERY append. Invisible at the Phase 6 smoke crew's handful
  of calls; 43M row parses and 39k syscalls at Phase 10's 12,893. cProfile put
  _ensure_header at 11.2 of 11.9 seconds on a 600-prompt run -- 95% of wall
  time re-asking whether a file it had just written to still existed
- month total now cached and maintained incrementally under the append lock;
  refresh() drops it. Header checked once per instance. A test asserts the
  cached total equals a fresh read, so the fix cannot change the numbers
- OfflineLLM gains _synthesise_silver, which reads the target utterance from
  its <<<...>>> delimiter so the stub cites spans that really are substrings
- _synthesise(kind, rng) signature deliberately NOT widened: doing so broke
  four tests in test_agents.py that subclass OfflineLLM. Those tests were
  right, so the code changed and the tests did not"

# 2 -- the Phase 10 deliverable
git add src/labeling/ scripts/run_labeling.py tests/test_labeling.py `
        docs/labeling.md .gitignore data/processed/silver/ reports/labeling_run.json
git commit -m "Phase 10: cost-aware weak labelling pipeline

- src/labeling/, eight modules, no new dependencies. Silver labels carry a
  confidence, a rationale, and spans that MUST be literal substrings of the
  utterance -- a paraphrased span breaks span-level explanation silently
- routing: cheap -> mid, escalate once on low confidence or a parse refusal,
  never to premium. Unparseable after escalation = unlabelled + queued, never
  guessed. Low-confidence = kept + flagged, because discarding uncertain
  labels biases silver toward easy utterances
- parser refuses malformed output rather than coercing it. A parser that
  clamps intensity and invents confidences fills the dataset with its own
  opinions, indistinguishable from the model's
- the store refuses generation_spec on the way out and refuses a root inside
  data/gold/. Circularity is closed structurally, not by a warning
- gate offline: 9,302/9,302 labelled, 0 failures, \$0.00, deterministic modulo
  run_id and labeled_on. NOT ONE LIVE CALL HAS BEEN MADE (OPEN-008)
- 72 tests; no test can reach a provider, and one asserts the config default
  that keeps it that way"

# 3 -- three findings that contradict committed documents
git add docs/open_issues.md
git commit -m "Phase 10: OPEN-008 partially resolved; OPEN-022/023/024 raised

- OPEN-023: config/model_routing.yaml's '\$1.12 per full pass' assumed ~400
  input tokens. The real rubric prompt is 3,946. Measured projection is
  \$17.46 against a \$20 enforced cap -- 87% of the cap for one pass, which is
  an owner decision and not an implementation detail
- OPEN-024: the cost ledger was quadratic and had never been run at scale.
  Fixed the same session. Correct at n=5, unusable at n=10,000, and every
  test written at n=5 passed
- OPEN-022: template era is not recorded, so the Phase 9b comparison that
  exposed the lexicon's shared ancestry cannot be run for the labeller.
  Lexical overlap is a coarser substitute
- the ~31% dedup saving does not survive passing parent context: 9,260
  distinct prompts, not 6,444, because 636 texts recur across different
  records. Third number carried forward from a superseded corpus version to
  fail on recomputation"

# 4 -- the handover
git add phase11_handover.md
git commit -m "docs: Phase 11 handover -- human gold annotation"

git push
```

---

## PART C — Phase 11 Brief

**Objective:** human gold annotation. Saikalyan plus **at least one peer** independently
annotate `data/processed/gold_candidates/gold_eval.jsonl` (400 items) against
`docs/annotation_guidelines.md`, then adjudicate and report inter-annotator agreement.

**This is the phase that produces contribution #1.** It is also the phase with the least
code in it and the most human coordination, which is why the two open items below have to
be settled first.

### Do these three things before annotating anything

**1. Decide the live labelling run (OPEN-023).** The projection is $17.46 against a $20
cap. Options, in order of preference:

   a. `python scripts/refresh_pricing.py --check`, then
      `python scripts/run_labeling.py --live --pricing-checked --limit 50`. Costs pennies,
      and measures the three unknowns inside the projection: the cache-read rate, the real
      escalation rate, the real output length. Re-project afterwards.
   b. If the re-projection is comfortable, run the full pass.
   c. If it is not, shorten the rubric or reduce the escalation fraction — **do not raise
      `monthly_cap_usd`.**

**2. Calibrate on `gold_dev` first.** 100 items drawn from *training-side* templates, so
arguing over the rubric on them costs zero evaluation power. Both annotators label
`gold_dev`, compare, and amend `docs/annotation_guidelines.md` where it did not decide the
case. Only then start `gold_eval`.

**3. Recruit the peer annotator — and make it the same conversation as OPEN-004.**

### The rules that make the kappa meaningful

- **100% double-annotated.** `gold_eval` is 400 items and both annotators do all 400, which
  is what makes a per-construct Cohen's kappa computable.
- **Independently.** `docs/annotation_guidelines.md` sec.7: never discuss specific records
  before both passes are complete. Discussing them inflates agreement and makes the
  statistic worthless.
- **`generation_spec` is stripped from every candidate** by the Phase 9 sampler. Do not
  reintroduce it. An annotator who can see what was planted is not an annotator.
- **Never compute a kappa between silver and a human.** Silver labels for these same
  utterances exist in `data/processed/silver/` because the whole corpus was labelled.
  Silver-vs-human is a *measurement of the labeller* and is reported as such at Phase 14.
  Agreement is between two humans.
- **Adjudication happens after both passes**, with the owner, against the document. If
  adjudication reveals a rule the document does not cover, amend the document and re-run
  the affected batch — do not settle it verbally.

### What Phase 10 hands you

- `data/processed/silver/synth_precomp_v1/silver.jsonl` — 9,302 silver labels (gitignored;
  regenerate with `python scripts/run_labeling.py`).
- `logs/review_queue.jsonl` — 4,427 utterances the Annotation-QA pass flagged. **Not an
  annotation queue.** It is evidence about the labeller.
- `docs/labeling.md` — including sec.9, the honest limitations, which the paper needs.

### Constraints, all inherited and non-negotiable

- `data/gold/` is human-owned; no agent writes there, and three stores refuse a root inside it.
- `pytest` must never be able to spend money; `mode: offline` stays the default.
- Offline and deterministic from a fresh clone; fixed seeds.
- The allow-list enforcement path is never weakened and never gains a bypass flag.
- Every agent writes a run log to `logs/`; every call writes cost to `logs/cost_ledger.csv`.
- Never commit secrets. Keys live only in `.env`.

**Do not start Phase 12.**

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-011** | **No real athlete text.** The corpus is 100% synthetic while contribution #1 claims an athlete-text corpus. Still the only unmitigated high-impact item. | **Phase 11 (now)** |
| **OPEN-004** | **No expert raters recruited.** Headline contribution, longest lead time, least control. Five phases overdue. | **Phase 17** |
| **OPEN-023** | **New.** The config's Phase 10 cost estimate is low by ~10x; a full live pass projects at 87% of the monthly cap. Owner decision. | **now** |
| **OPEN-008** | **Partially resolved.** The key exists; no live call has ever been made. | **Phase 10's live pilot** |
| **OPEN-022** | **New.** Template era is not recorded, so the sharpest shared-ancestry probe cannot be run. | Phase 18 |
| **OPEN-021** | The lexicon baseline is not independent of the corpus. A paper obligation; the same check now exists for silver in `ancestry.py`. | Phase 18 |
| OPEN-024 | ~~Ledger was O(n²)~~ — **CLOSED at Phase 10**, same session it was found. | closed |
| OPEN-019 | `generation_spec` replicated per utterance (×~2.3). | monitored |
| OPEN-009 | Model/price drift. **Unverified this session** — the sandbox has no route to openrouter.ai. | any large batch |
| OPEN-007 | CrewAI backend written but never executed. Phase 10 used the direct routing layer, so this is unchanged. | — |
| OPEN-012 | Vocabulary bounded by the template bank; 860 types. | Phase 14 (monitored) |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic, fires on every file write. | — |

**OPEN-011 and OPEN-004 are still the same conversation, and it is now blocking.** One
SRMIST coach or sport-psychology practitioner could both broker pre-competition text under
A3 consent *and* serve as the Phase 17 expert rater. It has been deferred across five
phases. Phase 11 is where OPEN-011 stops being a risk and becomes a limitation printed in
the paper: annotating 400 synthetic utterances produces a real inter-annotator agreement
figure over text no athlete ever said.

---

## PART D — Phase 11 tooling, built 2026-08-10 (update to Part C)

Part C above was written before any Phase 11 code existed. Two of the three
"do these first" items are now done. **The third is unchanged and is the blocker.**

### What was built

| Path | What |
|---|---|
| `src/annotation/context.py` | attaches the parent record to every item — **the defect fix** |
| `src/annotation/potato_project.py` | emits a Potato project from `config/taxonomy.yaml` |
| `src/annotation/schema.py` | `GoldLabel` / `GoldConstruct`; no machine author exists |
| `src/annotation/store.py` | the only write path into `data/gold/`, four locks |
| `src/annotation/ingest.py` | Potato output → `GoldLabel`; refuses, never coerces |
| `src/annotation/agreement.py` | Cohen's kappa, weighted kappa, span F1, adjudication list |
| `scripts/run_annotation.py` | `--build` / `--ingest` / `--agreement` / `--status` |
| `config/annotators.yaml` | the roster; **A2 is commented out because they do not exist** |
| `tests/test_annotation.py` | 48 tests |
| `docs/annotation_tooling.md` | design, verification, honest limitations |
| `onboarding/README.md` | ready to hand to a candidate annotator |

### The defect from Part C is fixed and the fix is measured

| Batch | Items | Gained multi-utterance context | Mean parent tokens | Mean target tokens |
|---|---|---|---|---|
| `gold_dev` | 100 | 84 (84.0%) | 43.2 | 18.5 |
| `gold_eval` | 400 | 301 (75.3%) | 35.1 | 17.7 |

The annotator now sees **the same context the Phase 10 labeller saw**, so the Phase 14
comparison is not measuring a context asymmetry. Spans are still marked on the utterance
alone, so offsets stay aligned with `InterimRecord` and `SilverLabel`.

### Tool decision

**Potato 2.7.1 adopted** (generated, not vendored — `pip install potato-annotation==2.7.1`).
**`sciknoworg/ALD-E-ImageMiner` rejected:** it is an image/figure annotation dataset project
for atomic-layer-deposition papers, not a text annotation tool. Its pilot→full task phasing
and `onboarding/` convention were borrowed; no code was.

### Verification

- Both projects pass **Potato's own** `python -m potato.validate_cli <config> --strict`:
  *"OK — no issues found."* That caught a real defect — an `html_layout` key carried over
  from an older Potato API — which was deleted rather than justified.
- `pytest` **372/373** (the failure is the 3.11 check under the sandbox's 3.10).
- Phase 7, 8, 9, 10 and benchmark gates all re-run: **PASSED**.
- `ruff check` / `format --check`: clean, 74 files.
- A test asserts the roster has exactly one annotator. **If it starts failing, someone has
  been recruited — update this handover, do not "fix" the test.**

### What remains, in order

1. **Recruit the second annotator (OPEN-025).** No code can close this. `onboarding/README.md`
   is the brief.
2. **Time the `gold_dev` pass (OPEN-026).** Phase 12's taxonomy freeze needs a measured
   burden, and 400 items × 10 constructs × 2 people has never been costed.
3. **Annotate ~5 items and run `--ingest` (OPEN-027).** The parser has never met real Potato
   output. Five minutes converts an unexercised path into a tested one.
4. Then: `gold_dev` in full → compare → amend the guidelines → `gold_eval`.

### Interpretation recorded for review

`CLAUDE.md` sec.4 says agents never write `data/gold/`. `src/annotation/store.py` writes
there, on the reading that the rule protects **the origin of the content** (a person's
judgement) rather than forbidding all file writes — under the literal reading gold could never
come into existence. Four locks enforce the purpose, and they are listed in
`docs/annotation_tooling.md` §6. **If the owner disagrees with that interpretation, this is
the module to change.**
