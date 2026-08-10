# Handover — Phase 9: Exploratory Data Analysis & Quality Profiling

Self-contained. A new AI session can start from this file plus the repo; no chat history
needed.

---

## PART A — Project Summary

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
| 1 — Repo reset & scaffold | Complete | `fb87925` |
| 2 — Dev environment & tooling | Complete | `07d77ab` + `b28873f` |
| 3 — Related work & novelty | Complete | `b104b8d` |
| 4 — Construct taxonomy | Complete (v2, locked; frozen at Phase 12) | `d238721` |
| 5 — Ethics, data governance & risk plan | Complete | `a28b7ba` |
| 6 — Confirm decisions & wire agent framework | Complete | `b28873f` (+ `ccba023`) |
| 7 — Data ingestion pipeline | Complete | `6f9561a` |
| **8 — Preprocessing & de-identification** | **Complete & committed** | see Part B7 |
| 9 — EDA & quality profiling | **NEXT** | — |

**Carried-forward caveats:**

- **Phase 1 deviation:** no `legacy-backup` branch; the previous codebase was permanently
  deleted at the owner's instruction. Only `main` exists, no remote, no off-machine backup
  (**OPEN-003**).
- **Phase 3:** the BibTeX key `Toth2025` is historical. László Tóth was the **handling
  editor**, not an author. Correct authors: Nogueira, Morais, Mansell & Gomes.
- **Sandbox caveat:** the agent sandbox runs Python 3.10; the project pins 3.11.
  `datetime.UTC` (3.11+) is used in `src/agents/ledger.py` and `src/ingestion/allowlist.py`.
  Tests were run here with a shim backfilling that alias. **Re-run `pytest` on the 3.11
  machine to confirm natively.**

---

## PART B — Current Session Summary (Phase 8)

### B1. Prerequisite verification before any code was written

Every Phase 8 prerequisite named in `phase8_handover.md` Part C was checked against the
codebase first. All were already satisfied by Phase 7:

| Prerequisite | Evidence | Verdict |
|---|---|---|
| De-identification spec exists and is not to be redesigned | `docs/ethics.md` §5.1 removal table, §5.2 rules | **Complete** |
| Harvester Agent contract defined | `src/agents/roster.py::HARVESTER`, phases `(7, 8)` | **Complete** |
| `RawRecord` input contract | `src/ingestion/records.py` | **Complete** |
| `data/raw/` populated with provenance | 1,200 records + `provenance.json`, gate re-run PASSED | **Complete** |
| `deidentified` left `False` at ingestion | `provenance.py::provenance_from_descriptor`, hardcoded with comment | **Complete** |
| De-identification recall fixture (OPEN-013) | `tests/fixtures/deid_cases.jsonl`, 34 cases, 8 negatives | **Complete** |
| `data/gold/` write guard | `src/ingestion/store.py::RawStore._guard_root` | **Complete** |
| Offline/deterministic constraint | no network in `src/ingestion/` or `src/evaluation/` | **Complete** |

**Nothing from Phases 1–7 had to be back-filled.** `src/preprocessing/` was an empty package
(`__init__.py`, 0 bytes) and that was the only gap — which is exactly what Phase 8 was for.

### B2. What was built

`src/preprocessing/` — nine modules, ~1,900 lines:

| Module | Responsibility |
|---|---|
| `lexicons.py` | All word lists in one auditable place: safety list, role nouns, entity suffixes, health triggers, body parts, stopword profiles. |
| `normalize.py` | NFKC, typography folding, control/zero-width stripping. Idempotent. **Casing untouched** — it is intensity evidence and the de-identifier depends on it. |
| `segment.py` | Utterance splitting with exact `(char_start, char_end)` offsets; abbreviation and decimal guards; `verify_offsets`. |
| `language.py` | Coarse offline English filter. `should_exclude` puts the burden of proof on exclusion. |
| `deidentify.py` | The `docs/ethics.md` §5.1 implementation. Ordered five-pass cascade with locked replacements. |
| `records.py` | `InterimRecord`; refuses to exist with `deidentified=False`; parentage mandatory. |
| `store.py` | `InterimStore`/`InterimWriter` — the only write path into `data/interim/`. Gold-root guard restated. |
| `pipeline.py` | The four-step orchestration and the manifest. |
| `audit.py` | Fixture scoring (precision/recall/exact/leak, by band and category) and the stratified manual-audit sample. |

Plus `scripts/run_preprocessing.py` (the Phase 8 gate), `tests/test_preprocessing.py`
(42 tests), `docs/preprocessing.md`.

**Design decisions worth defending in the paper:**

1. **Pass order is load-bearing.** health → contacts → dates → entities → quasi-identifiers.
   Health first so nothing is spent placeholdering text about to be deleted and so a name
   inside a removed clause disappears with it; contacts before entities so
   `marcus@example-club.org` is one `[CONTACT]` and not a `[PERSON]` glued to a domain.
2. **Segment before de-identify.** Redaction changes length, so offsets computed after it
   point into a string that no longer matches the raw record. The consequence —
   `char_start`/`char_end` index the *normalised parent*, not the stored utterance text — is
   written on the schema, in the manifest, and in `docs/preprocessing.md`, not left to be
   discovered at Phase 16.
3. **`deidentified: true` is earned in exactly one function.** `store.interim_provenance`,
   called only after the de-identifier has run over every record.
   `InterimRecord.__post_init__` raises if the flag is `False`. `data/raw/` still says
   `false`, correctly — that text has not been de-identified and never will be.
4. **Health detail is removed clause-by-clause, not sentence-by-sentence.** Sentence-level
   removal would delete "and I felt flat all week" along with the medication clause, and that
   surviving half is exactly the affective language this project studies.
5. **Body parts are not health data.** Somatic anxiety surfaces almost entirely as body
   language — knotted stomach, shaking hands. Treating body parts as health triggers would
   delete the evidence for one of the ten locked constructs.
6. **No reversible mapping exists, structurally.** `deidentify_with_report` returns text and
   counts. A test asserts the report contains no original strings and exposes no inverse.

### B3. What Phase 8 measured

**The fixture gate (`tests/fixtures/deid_cases.jsonl`, 34 cases) — the real measurement:**

| Metric | Value |
|---|---|
| Precision | **100.0%** |
| Recall | **100.0%** |
| Exact match | **100.0%** (34/34) |
| **Leak rate** | **0.0%** |
| Negatives preserved | **8/8** |

| Band | n | Precision | Recall | Exact | Leak |
|---|---|---|---|---|---|
| easy | 10 | 100.0% | 100.0% | 100.0% | 0.0% |
| medium | 11 | 100.0% | 100.0% | 100.0% | 0.0% |
| hard | 13 | 100.0% | 100.0% | 100.0% | 0.0% |

**Read this number carefully.** 34 self-authored cases sweeping clean means the cascade
handles the failure modes this project thought to write down. It is an **upper bound** on
real-text performance, not a measurement of it, and the paper must say so.

**Held-out generalisation probe: 10/10 exact.** 10 cases with different names, sports, and
sentence shapes, never consulted while writing the rules. Reported, deliberately **not**
gated — a probe that gates becomes a second fixture the next person tunes against.

**The corpus run (`synth_precomp_v1`):** 1,200 raw records → **4,110 utterances**, 0 dropped,
0 placeholders written, 0 residual-risk flags.

**Zero placeholders is the expected result and it measures nothing** — the A2 generator plants
no personal names. That is OPEN-013, and it is why the fixture is the gate.

### B4. Bugs found by running the code

1. **The language filter deleted two perfectly good English records.** "Slept a little lighter
   than usual last night" scored as Portuguese: the English stopword profile had 20 entries,
   Portuguese 21, and the sentence matched exactly one token — `a`, a Portuguese article.
   Fixed twice over: profiles equalised to ~45 entries each, and `should_exclude` now requires
   a non-English profile to clear an absolute score **and** beat English by a margin.
   Regression test uses the exact sentence. **The dropped text was short, terse, and
   sleep-related — `somatic_anxiety` and `burnout_signal` evidence. A filter biased against
   short sparse text is biased against exactly what this project detects.**
2. **`k.mensah_07` was redacted twice**, producing `[HANDLE].[HANDLE]`. The handle-cue
   lookahead broke on the internal dot. Fixed to stop only at a sentence-final period.
3. **"Nadia and I have trained together" survived un-redacted.** The sentence-initial guard
   (which correctly protects "Mark my words") was firing before classification, so the
   "X and I" frame never got a chance. `_classify_run` now reports whether a *cue* fired, and
   the guard applies only to uncued single tokens.
4. **A Phase 7 generator artifact, found by reading the audit sample this phase generates.**
   The second entry in `reports/deid_audit_sample.md` reads *"corner of me wants to attack
   it"* — v1.1's synonym layer substituting *part* → *corner* inside the idiom *part of me*.
   **9 of 1,200 records (0.8%).** Logged as **OPEN-015**, deliberately **not fixed here**:
   regenerating the corpus mid-phase would invalidate the numbers reported in the same
   session, and the corpus is a Phase 7 artefact under owner decision. It belongs to Phase 9,
   which exists to find exactly this. Worth noting the mechanism — the substitution passed a
   review that checked shared POS *and* argument structure, because idiom membership is a
   third constraint neither of those catches.

### B5. A fixture contradiction, raised before it was resolved — closed

`name_01` expected the bare role noun `the coach` → `[COACH]`. `negative_04` required
`my Coach` to survive **unchanged**, with its own note reading *"'my Coach' is a role, not an
identity."* `docs/ethics.md` §5.1 lists **person names** for replacement, not role nouns.

The two could not both be satisfied, and `name_01` was the one that disagreed with the policy.

**Resolved by amending `name_01`**, on the owner's decision, to expect
`[ATHLETE] said the coach was happy with the session.` The reasoning is recorded in the
case's own `notes` field so the fixture explains itself.

**The sequence matters more than the outcome.** The contradiction was found by running the
de-identifier, reported before any file was touched, checked against the policy, and only
then resolved by the owner. The implementation was never changed to chase the fixture — a
gate rewritten to fit its implementation stops being evidence, and this fixture is the only
real measurement the de-identifier has. If a future session finds itself editing this file to
make a test pass, that is the failure mode to stop and re-read this paragraph for.

### B6. Verification performed

| Check | Result |
|---|---|
| `ruff check src/ scripts/ tests/` | **All checks passed** |
| `ruff format --check` | 47 files already formatted |
| `pytest tests/test_preprocessing.py` | **42/42 pass** |
| Full suite | **171/172** — the one failure is `test_python_version_is_311` under the sandbox's 3.10, i.e. the test working correctly |
| Phase 8 gate `run_preprocessing.py` | **PASSED** |
| Phase 7 gate re-run (no regression) | **PASSED** |
| Benchmark audit re-run (no regression) | **PASSED** |
| Determinism | Same input → byte-identical `utterances.jsonl`, asserted in tests |
| Offset invariant | `parent[start:end] == utterance.text` for every utterance |
| `data/gold/` guard | Refuses the gold root and any subdirectory |
| Irreversibility | Report carries no original strings and no inverse |

### B6b. Files changed

| File | Change |
|---|---|
| `src/preprocessing/{lexicons,normalize,segment,language,deidentify,records,store,pipeline,audit}.py` | **new** |
| `src/preprocessing/__init__.py` | public API (was empty) |
| `scripts/run_preprocessing.py` | **new** — the Phase 8 gate |
| `tests/test_preprocessing.py` | **new** — 42 tests |
| `docs/preprocessing.md` | **new** |
| `docs/ethics.md` | §5 implementation-status note added; spec itself unchanged |
| `docs/open_issues.md` | OPEN-013 **closed**, OPEN-015 **raised**, change log updated |
| `tests/fixtures/deid_cases.jsonl` | `name_01` expected output corrected (role noun is not a name); reasoning in the case's `notes` |
| `.gitignore` | commit interim `provenance.json` + `preprocessing.json`, keep utterances out |
| `reports/deid_audit_sample.md` | **new** — generated, unreviewed |
| `data/interim/synth_precomp_v1/` | **new** — 4,110 utterances (gitignored), provenance + manifest committed |

### B7. Commit status

**Phase 8 is committed.** The owner committed the implementation, tests, docs, and interim
artefacts on 2026-08-09.

A follow-up commit is outstanding for the fixture correction described in B5 and the numbers
it changed:

```powershell
cd C:\Users\saika\sports-risk-nlp
Remove-Item -LiteralPath ".git\index.lock" -Force -ErrorAction SilentlyContinue
.\.venv\Scripts\Activate.ps1

pytest                                          # expect 172/172 on 3.11
ruff check src/ scripts/ tests/
python scripts\run_preprocessing.py             # expect: Phase 8 gate: PASSED, 34/34 exact

git add tests/fixtures/deid_cases.jsonl docs/ phase9_handover.md
git commit -m "Phase 8 follow-up: correct fixture case name_01; role nouns are not names

- name_01 required the bare role noun 'the coach' to be redacted, contradicting
  negative_04 in the same file and docs/ethics.md 5.1, which lists person NAMES
  for replacement. Amended to expect [ATHLETE] said the coach was happy...
- the implementation was NOT changed to chase the fixture; the contradiction was
  found by running the de-identifier and reported before any file was touched
- reasoning recorded in the case's own notes field so the fixture explains itself
- de-identification now 34/34 exact: precision 100%, recall 100%, leak rate 0%
- numbers updated in docs/preprocessing.md, docs/ethics.md, docs/open_issues.md"
```

Note the recurring blocker: `.git/index.lock` has appeared in the Phase 6, 7, and 8 sessions.
It is an environment quirk, not a repo problem, but it costs time every session.

---

## PART C — Phase 9 Brief

**Objective (from `PROJECT_PLAN.md`):** Understand the corpus before labelling.

**Owning agent:** Evaluation Agent (cheap tier), `src/agents/roster.py::EVALUATION`.

**Tasks:**

1. Notebook EDA in `notebooks/` — length distributions, vocabulary, duplicates, junk,
   prevalence of the constructs of interest.
2. Decide the **stratified sampling strategy for the gold set** (Phase 11). This is the real
   deliverable; the plots are supporting evidence.
3. `reports/eda.md` plus figures.

**Gate:** Documented data-quality issues and a stratified sampling plan.

**Read first:** `docs/preprocessing.md` (what the interim corpus is and what it is not),
`docs/data_sources.md` §2 (OPEN-012, vocabulary and leakage), `src/evaluation/splits.py`
(template-disjoint splitting is **mandatory** — `random_split` is a foil only),
`docs/open_issues.md`.

**Constraints and traps specific to Phase 9:**

- **Profile `data/interim/`, not `data/raw/`.** Raw text is not de-identified. Phase 9 is the
  first phase that could accidentally read the wrong one.
- **`generation_spec` is not a label.** It records what the generator planted. Using it for
  prevalence statistics produces a number about the template bank, not about athlete language.
  If you report it, label it as generator metadata every time.
- **The unit changed.** 1,200 records became 4,110 utterances. Any statistic quoted per-record
  from Phase 7 is not comparable to a per-utterance statistic now. Say which unit you mean.
- **Placeholders are tokens.** `[EVENT_WINDOW]` and friends will appear in vocabulary counts.
  Decide explicitly whether to include or exclude them and state which — and check the
  tokeniser does not split them into fragments when the model is wired at Phase 13.
- **The sampling plan must survive template-disjoint splitting.** A gold set drawn without
  regard to template identity will straddle the split and re-introduce the leakage Phase 7
  quantified at 0.53 macro-F1.
- Offline and deterministic. `pytest` must never be able to spend money.

**Do not start Phase 10.**

---

## Open items, by urgency

> `docs/open_issues.md` is the single source of truth. This is a pointer, not a copy.

| ID | Item | Blocking at |
|---|---|---|
| **OPEN-011** | **No real athlete text in the corpus.** Contribution #1 needs some. Three routes, all owner-actionable, all currently declined. **Still the only unmitigated high-impact item.** | **Phase 11** |
| **OPEN-004** | **Expert-rater recruitment not started.** Week 1–2 per the risk register; it is now Week 3. Headline contribution, longest lead time, least control. | **Phase 17** |
| OPEN-015 | **New.** Generator v1.1 substitution produced "corner of me" in 9/1,200 records (0.8%). Corpus-quality defect; **Phase 9 owns it**, and option (a) — fix and regenerate — is best done *before* EDA numbers are published. | **Phase 9 (next)** |
| OPEN-013 | ~~De-identification unvalidatable~~ — **CLOSED at Phase 8.** Measured; re-measure against real text when OPEN-011 resolves. | closed |
| OPEN-012 | ~~Vocabulary too small~~ — substantially mitigated; re-run the audit once the transformer exists. | Phase 14 (monitored) |
| OPEN-008 | No `OPENROUTER_API_KEY` in `.env`. | Phase 10 |
| OPEN-007 | CrewAI backend written but never executed. | Phase 10 if chosen |
| OPEN-005 | Ethics exemption not in writing. | Submission |
| OPEN-006 | Withdrawal contact is a personal address. | Public release |
| OPEN-003 | No off-machine backup. Everything exists in one place on one machine. | Standing risk |
| OPEN-009 | Model/price drift. | Any large batch |
| OPEN-002 | Broken pixeltable plugin hook; cosmetic, fires on every file write. Confirmed still firing throughout Phase 8. | — |

**The two highest-value non-code actions available today remain OPEN-011 and OPEN-004, and
they are the same conversation** — recruiting an SRMIST coach or sport-psychology practitioner
who could both donate/broker pre-competition text under A3 consent *and* serve as the Phase 17
expert rater. It was Week 3 at the start of this session and it is still Week 3; that
conversation has not happened yet, and it has the longest lead time of anything left.
