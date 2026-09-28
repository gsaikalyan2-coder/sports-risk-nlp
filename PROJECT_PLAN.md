# PROJECT_PLAN.md - 25-Phase Blueprint

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Owner:** Saikalyan (SRMIST, sophomore) · **Window:** 8 weeks · **Paper due:** 1st week Sept 2026

**Confirmed stack (2026-07-23):** CrewAI (agents) · OpenRouter (cost-tier LLM routing) ·
public/licensed datasets first (hybrid synthetic fallback) · DeBERTa/RoBERTa · Docker · Streamlit · LaTeX.

**Evidence-backed novelty (updated 2026-08 from the Phase 3 review - see `docs/related_work.md`):**
Three-part contribution - (1) construct-grounded athlete-text corpus bridging validated constructs to
text; (2) **two-level interpretability with a measured faithfulness margin** (span→construct + construct→risk), the
headline differentiator that fills the Interpretability-Validation gap; (3) time-aware, fusion-ready
design. Taxonomy expanded with **resilience** and **appraisal orientation (challenge/threat)** plus an
**interpretation-direction** modifier on anxiety.

**Expansions status (revised):** *Temporal* is now partly in-scope as **lightweight time-aware
sampling** (Phase 7) with full temporal modeling still Future Work; *Multimodal* is **architecture-ready**
(risk layer accepts optional light context, Phase 15) but not built; *Outcome linkage* is the one full
stretch attempted in-window if data allows; *Team aggregation* stays Future Work.

---

## STATUS BOARD (updated 2026-08-23, end of Phase 21)

**Week 4 of 8.** Phases 1–15 and 17–19 complete; 16 skipped by decision (no DataRobot
account, and uploading athlete text to a third-party cloud breaks the "reviewer
reproduces with no account" property). Phase 18 **executed on the real checkpoint**
2026-08-16 - **OPEN-035 closed, all seven claims backed**. Phase 19 complete:
`docs/findings.md` written, contribution statement locked, **OPEN-004 closed by
decision** (pilot self-audit, practitioner validation named as a limitation).

**Phase 22 - reproducibility packaging: ✅ COMPLETE 2026-08-24, gate PASSED from a genuine fresh clone.**
**Next: Phase 23 - IEEE draft assembly.**

> ### ⚠️ Phase-order debt (recorded 2026-09-23)
>
> **Phase 23 has not started.** It was due the first week of September 2026, and Phases
> 26, 27, 28, 29, 30, 31 and 32 have all run ahead of it. The gate below on Phase 26 -
> "starts only after Phase 23 ships" - was **not honoured**, and risk item 3 (scope creep)
> is not a risk any more, it is the thing that happened. Each of those phases is
> individually defensible and none of them moved a number in the paper; the debt is that
> none of them is the paper. Two human acts still block both headline contributions and no
> amount of code performs either: **A2 annotating 100 `gold_dev` items** (~3h, agreed
> 2026-08-12) and **2 sports-familiar raters** (~45 min each, deadline 2026-09-28).
> This note exists so the gate below reads as breached rather than as holding.
Phase 21 complete 2026-08-23: `src/security/` + `scripts/run_security_audit.py`
+ 49 tests + `docs/security.md`. **Gate PASSES** (exit 0, zero HIGH findings,
every scanner proven). The two HIGH findings the first run raised were **fixed,
not suppressed**; SEC-03 stays open deliberately because that fix corrected
verdicts and was not a re-scan. The Phase 20 `docker compose up dashboard` check
is **still outstanding** (`handover_phase_20.txt` C1).

| Phase | Status | Evidence |
|---|---|---|
| 14 Transformer | ✅ gate PASSED | distilroberta lr2e-5 bs16 ep6 → macro-F1 **0.588** vs lexicon 0.462, paired bootstrap p=0.000 |
| 15 Risk scoring | ✅ | `src/risk/` · per-construct ECE reported; `calibrate_risk_index` **refuses** - no observed risk outcome exists |
| 16 AutoML | ⏭️ skipped | no account; decision recorded in `CLAUDE.md` §10 |
| 17 Explainability + expert study | ✅ structural halves PASS; expert half shipped as **pilot self-audit** | `reports/explain/` · comprehensiveness margin **+0.328** over random control, all 10 constructs beat control · IG-vs-SHAP top-5 Jaccard 0.384 · **86.7% of driver rows have no supporting span**, counted not hidden · **OPEN-004 closed by decision 2026-08-16** - student raters only, "expert-validated" is forbidden wording |
| 18 Evaluation harness & ablations | ✅ **gate PASSED on the real checkpoint** | `src/evaluation/{harness,ablations}.py`, `scripts/run_evaluation.py`, 37 tests · `reports/results.{md,json}` + 8 prediction caches + 4 figures · **7/7 claims backed** · **OPEN-034** raised and closed (the claim gate certified a claim its evidence contradicted); **OPEN-035 closed** |
| **19 Results aggregation & narrative** | **✅ gate PASSED** | `docs/findings.md` - contribution statement locked, 3 headline findings, 8 forbidden claims tabulated, every headline traceable to a `CLAIMS` row |
| **20 Dashboard / visualisation** | **✅ gate PASSED** (Docker check owner-run) | `src/dashboard/` + `dashboard/app.py` + 23 tests · `docs/dashboard.md` · `reports/dashboard/` 3 screenshots incl. a **grayscale proof** · `reports/figures/phase20_explanation_card.svg` · gate **strengthened before the app was written**: known example reproduces `reports/explain/cards.md` **byte-identically**; `assert_publication_safe` unavoidable by construction; PROVISIONAL stamp unconstructable-if-absent *and* rendered above the fold; 4 inert constructs derived from the scorer, never a name list; forbidden-vocabulary screen over the rendered surface. **Two defects found by looking, not by asserting** - duplicate SVG ids blanked one chart's inert hatch, and the stamp sat inside a collapsed expander |
| **21 Security, dependency & PII audit** | **✅ gate PASSED** | `src/security/` (audit/sweep/baseline/deps) + `scripts/run_security_audit.py` + **49 tests, ~1.2s, no ML stack** · `docs/security.md` · `reports/security_audit.md`. Gate **strengthened before any scanner ran**: `ScannerResult` requires a non-empty `does_not_cover` sentence, so a findings table with no coverage statement is unconstructable; sweep scope is `git ls-files`, so a file's position cannot put it out of scope; `run_sweep` **refuses to report** unless every detector has just fired on a canary planting its own target, and an unproven scanner fails the gate with zero findings. **The predicted defect happened on the first run and the mechanism caught it** - the credential pattern's leading `\b` never matched `OPENROUTER_API_KEY`, and without the canary that sweep returns zero credential findings over 251 files and reads as clean. **10 findings**: 2 HIGH - the `.secrets.baseline` entries were all marked `is_secret: true`, and the baseline was platform-locked in both directions - **both fixed in-phase, not suppressed** (verdicts corrected after verifying all four values are `training_fingerprint` SHA-256 digests; every path converted to POSIX; the disagreeing `.pre-commit-config.yaml` exclude list reconciled). `generated_at` was deliberately **not** refreshed, so SEC-03 stays open: the fix corrected verdicts, it was not a re-scan. Plus 5 MEDIUM, 2 LOW, 1 method note - including **SEC-10**, the forbidden contribution claim still asserted in `CLAUDE.md`, `PROJECT_PLAN.md` and `docs/related_work.md`, i.e. the exact sentences Phase 23 drafts from; fixed. **Clean with evidence**: `.env` never committed (checked in *history*, not the index), 257 paths ever added = 257 tracked now, every historical blob matched against 5 credential shapes across 34 commits, no LFS, no checkpoint ever committed |
| **22 Reproducibility packaging** | **✅ gate PASSED** | `src/reproducibility/` (plan/environment/verify/manifest) + `scripts/run_reproduction.py` + **52 tests, no ML stack** · `docs/reproducibility.md` · `ARTIFACT.md` · `reports/reproduction.{json,md}`. Gate **strengthened before anything ran**: an artefact cannot be declared without its reproduction *strength* (byte-identical / within a stated tolerance / not reproducible), each demanding a different field at construction; the ±0.010 retrain tolerance was declared **before any re-run**, hashed, and bound into every verification, so widening it afterwards fails the gate; `cannot_reproduce` is mandatory per step; a step installing a local-version lock without `--extra-index-url` is **unconstructable** (`MissingExtraIndex`); and a verification in a tree still holding `data/` or `models/` is **refused, exit 2** -- the defect `handover_phase_21.txt` predicted, refused mechanically. **Verified end to end from a real fresh clone on a different OS, no `data/`, no `models/`:** every headline number returned at **full float precision** (0.5877114720181955 · +0.1259828877582358 · +0.23423985163237282 · CI bounds), corpus and utterances matched by SHA-256, all 8 claims backed. **SEC-07 closed** -- both images now install per-layer locks partitioned by a computed closure; the base lock resolves with **zero unpinned extras**. **SEC-05 closed** (27 path occurrences → 0). **SEC-11 raised and fixed** -- the 180-pin lock was missing `uvloop` (Linux-only, a Windows freeze cannot see it) and `sentencepiece` (required, added to `requirements-ml.txt` two days *after* the lock was captured). **Three defects found by running and reading, none by the tests**: the gate passed having reproduced nothing when no tier was selected; a step that exited non-zero did not fail the gate because it produced no artefacts; and `utterances.jsonl` was **not byte-identical across platforms** -- CRLF vs LF, 9,302 bytes, two artefacts generated on two machines two days apart with nothing recording which. **SEC-04 remains OPEN** (personal contact address, 9 occurrences, 5 files) |

**Phase 19's three headline findings.**

| # | finding | number |
|---|---|---|
| 1 | **The memorisation gap** - a random split massively overstates generalisation on a synthetic corpus | TF-IDF 0.999 → 0.222 (**+0.777**); transformer 0.822 → 0.588 (**+0.234**); lexicon control only +0.100 |
| 2 | **Two-level interpretability with a measured faithfulness margin** | comprehensiveness **+0.328** over random control, sufficiency +0.170, all 10 constructs beat control - **pilot** expert review, never practitioner validation |
| 3 | **Negative results reported as results** | silver bought nothing (+0.033, p=0.107) · risk index uncalibratable by construction · **4 of 10 constructs inert** in fusion |

**Two things the real run settled that the handover flagged as open questions.**
`naive_rho` came back at **0.100**, not near 1.0 - the taxonomy weighting materially
reorders records rather than reproducing a construct count. And the per-construct table
resolved into **three regimes**, not a spread: three competent, four threshold-collapsed
(recall ~1.0 at precision 0.19–0.57), one threshold-frozen (`cognitive_anxiety`,
P 1.000 / R 0.227) - a finding about per-construct threshold search under macro-F1.

**Phase 18's three ablations, as actually delivered.** The plan named
baseline-vs-transformer, ±silver and ±risk-fusion. Only the first was runnable as written.

| ablation | delivered as | why |
|---|---|---|
| baseline vs transformer | **measured**, paired bootstrap | as planned |
| ± silver | **measured on the classical model; refused in writing on the transformer** | OPEN-028 - silver labels are `rng.randrange` output, so the transformer arm would spend ~10 CPU-hours measuring the effect of adding noise. The cheap arm demonstrates it instead |
| ± risk fusion | **structural sensitivity analysis** | no observed risk outcome exists; a proxy target from planted labels would measure whether the model recovers this project's own generator |

---

## STATUS BOARD (superseded - end of Phase 9)

**Week 3 of 8.** Phases 1–10 complete and gated (10 offline only). Phases 11 and 12 have their
tooling built and tested. **OPEN-025 update, 2026-09-28: closed by decision, not by recruiting.**
A2 had agreed (2026-08-12) but never annotated anything; the owner decided to proceed on A1's
single `gold_dev` pass (96/100 items) and drop the inter-annotator-agreement claim rather than
wait further. `src/annotation/agreement.py` and `src/taxonomy/refinement.py` were deleted as a
direct consequence (backup under `annotation/gold_dev/_backup_2026-09-28/removed_20260928/`),
and `scripts/run_taxonomy_refinement.py --refine` no longer exists. See `CLAUDE.md` sec.20-21.

| Phase | Status | Evidence |
|---|---|---|
| 1 Scaffold | ✅ | `fb87925` · deviation: no `legacy-backup` branch; **OPEN-003 closed 2026-08-10**, private GitHub remote |
| 2 Env & tooling | ✅ | `07d77ab`, `b28873f` · Docker builds, 11 env checks pass |
| 3 Related work | ✅ | `b104b8d` · `docs/related_work.md`, 14 refs resolved to primaries |
| 4 Taxonomy | ✅ | `d238721` · 10 constructs locked; **frozen at Phase 12** |
| 5 Ethics & governance | ✅ | `a28b7ba` · `docs/ethics.md`, allow-list v1.1 |
| 6 Agent framework | ✅ | `b28873f` · offline crew run + cost ledger |
| 7 Ingestion | ✅ | `6f9561a` · **4,000** records, generator **v1.4**, fail-closed allow-list |
| 8 Preprocessing & de-ID | ✅ | **9,302** utterances · fixture 34/34 exact, leak rate 0% |
| 9 EDA & quality profiling | ✅ | `reports/eda.md` · gold plan, 400 items, 0/10 below floor |
| **9b Corpus hardening** | ✅ | **15 templates/construct**, vocab 625→**860**, duplication 87.4%→**37.6%** |
| 10 Weak labelling | ✅ **offline only** | **9,302** silver labels verified; no live OpenRouter call has ever been made (OPEN-008/OPEN-023) |
| 11 Gold verification | **gate CLOSED by decision, no IAA** | Potato ingest verified against real Potato 2.7.1 output (OPEN-027 closed, and it was broken). A1 single-annotated `gold_dev` (96/100). Kappa dropped by owner decision, not measured - **OPEN-025 closed 2026-09-28** |
| **12 Label validation & taxonomy refinement** | **tooling ✅ (burden/propose only), refine REMOVED** | `src/taxonomy/` + `scripts/run_taxonomy_refinement.py`. `--burden` and `--propose` run today; `--refine` was deleted 2026-09-28 along with the agreement machinery it depended on (OPEN-025) |
| **13 Baselines** | ✅ **gate PASSED, numbers PROVISIONAL** | `src/models/` + `scripts/run_baselines.py` · `reports/baselines.{md,json}`. Six systems scored with bootstrap CIs. **Honest floor is the lexicon at 0.462 macro-F1** on the template-disjoint split; TF-IDF+LogReg 0.222, LinearSVC 0.181. All figures are planted-label *corpus-property* measurements, **not accuracy** - `data/gold/` is empty (OPEN-025). **OPEN-028 raised:** silver labels are PRNG output |

**Live risks, in order.** These supersede the generic risk list at the foot of this file.

| # | Risk | Status |
|---|---|---|
| 1 | **OPEN-011 - no real athlete text.** Contribution #1 claims an *athlete-text* corpus; the corpus is 100% synthetic. Only unmitigated high-impact item. | open, owner-actionable |
| 2 | ~~**OPEN-004 - no expert raters recruited.**~~ | **CLOSED by decision 2026-08-16** - pilot self-audit with student raters; practitioner validation is a named limitation, not a pending task |
| 3 | **OPEN-008 - no OpenRouter key.** First phase that genuinely needs one. | open, blocks Phase 10 |
| 4 | **OPEN-021 - the lexicon baseline is not independent of the corpus.** Shared ancestry with the template bank via `taxonomy.yaml` examples; macro-F1 0.780 → 0.461 once the bank stopped reusing those phrasings. A paper obligation, not a bug. | open, Phase 18 |
| 5 | **OPEN-028 - the entire silver set is PRNG output, not labels.** Consequence of OPEN-008, discovered at Phase 13. All 9,302 labels come from the offline stub's `rng.randrange`; single-label, 6/10 constructs, chance agreement. Phase 14's "train on gold+silver" is currently "train on gold + noise". | open, **blocks Phase 14 as written** |

**Closed since the last revision:** OPEN-003 (off-machine backup), OPEN-013, OPEN-015,
OPEN-016, OPEN-017, OPEN-018, OPEN-020. **Push at the end of every phase; a remote that stops
receiving pushes is not a backup.**

**Risks 1 and 2 are the same conversation** - one SRMIST coach or sport-psychology
practitioner could both broker pre-competition text under A3 consent *and* serve as the
Phase 17 rater. It has been deferred across Phases 7, 8 and 9.

---

**How to read this:** phases are sequential *by dependency*, but many run **in parallel**
(shown in the "Parallel agents" column). Each phase has an objective, tasks, the agents
involved, a concrete deliverable, and a **gate** (the acceptance check that must pass before
the phase counts as done). Do not skip gates - they are what keep the paper defensible.

**Legend for agents:** Lit = Literature · Psy = Taxonomy/Psych · Har = Harvester ·
Lab = Labeling · QA = Annotation-QA · Mod = Modeling · Eval = Evaluation · Exp = Explainability ·
Sec = Security/Ethics · Pap = Paper.

---

## WEEK 1 - Foundation & Framing

### Phase 1 - Backup, wipe, and re-scaffold the repo
- **Objective:** Clean slate without losing history.
- **Tasks:** Create a `legacy-backup` git branch of the current repo; on `main`, delete old files;
  create the folder structure from `.claude.md` §7; add `.gitignore`, `README.md`, `.env.example`.
- **Parallel agents:** - (human + Claude)
- **Deliverable:** Empty, well-structured repo committed.
- **Gate:** `git log` shows backup branch exists; `tree` matches the target structure.

### Phase 2 - Dev environment & tooling
- **Objective:** Reproducible local setup in VS Code.
- **Tasks:** Python 3.11 `venv`; `requirements.txt`/`pyproject.toml`; VS Code extensions (Python,
  Pylance, Ruff, Docker); pre-commit hooks (formatter + secret check); `Dockerfile` + `docker-compose.yml` stub.
- **Parallel agents:** -
- **Deliverable:** `pip install -r requirements.txt` works; `docker compose build` succeeds.
- **Gate:** A hello-world script runs both locally and in the container.

### Phase 3 - Literature review & novelty positioning *(SUBSTANTIALLY COMPLETE - owner-led, 2026-08)*
- **Objective:** Prove the idea is novel and find the gap. ✅ Done via owner's evidence review.
- **Done:** 14 sources synthesized into `docs/related_work.md`; two validated gaps identified
  (construct↔text bridge; unvalidated sports-XAI explanations); three-part contribution written.
- **Remaining:** resolve each Consensus link to a primary DOI and populate `paper/refs.bib`
  (do in Phase 23/24); optionally add a few more transformer/multi-label NLP method citations.
- **Deliverable:** `docs/related_work.md` (drafted) → `paper/refs.bib` (pending).
- **Gate:** ✅ Clear written gap + ≥14 references. Remaining gate item: `refs.bib` with primary sources.

### Phase 4 - Construct taxonomy design
- **Objective:** Lock the label schema grounded in psychometrics.
- **Tasks:** Psy Agent maintains `config/taxonomy.yaml` - now includes **resilience**,
  **appraisal orientation (challenge/threat)**, and an **interpretation-direction** modifier
  (facilitative/debilitative) added from the Phase 3 evidence - and writes
  `docs/annotation_guidelines.md` (examples, edge cases) for every construct including the new ones.
- **Parallel agents:** Psy (uses Phase 3 output).
- **Deliverable:** Taxonomy + annotation rubric.
- **Gate:** Every construct has a definition, a citation anchor, and ≥2 examples. Final set frozen at Phase 12.

### Phase 5 - Ethics, data governance & risk plan
- **Objective:** Set the guardrails before touching data.
- **Tasks:** Sec Agent drafts `docs/ethics.md` (consent/licensing rules, de-identification policy,
  non-diagnosis framing, misuse & bias risks); define what data sources are allowed.
- **Parallel agents:** Sec.
- **Deliverable:** `docs/ethics.md` + a data-source allow-list.
- **Gate:** Written de-identification + non-diagnosis policy that the paper can cite.

---

## WEEK 2 - Data Foundation

### Phase 6 - Confirm decisions & wire the agent framework
- **Objective:** Resolve open questions (Q1–Q3, DataRobot) and stand up orchestration.
- **Tasks:** Lock framework (CrewAI/AutoGen), LLM provider/cost approach, and data strategy;
  implement `src/agents/` crew definitions + `config/model_routing.yaml`.
- **Parallel agents:** -
- **Deliverable:** A runnable "smoke-test crew" that passes a trivial task end to end.
- **Gate:** One orchestrated multi-agent run completes and logs cost to `logs/cost_ledger.csv`.

### Phase 7 - Data ingestion pipeline *(now time-aware)* - ✅ COMPLETE
- **Outcome:** No public pre-competition athlete corpus exists (survey in `docs/data_sources.md`
  §4 - four candidates, all rejected). Owner chose **synthetic-first (A2)**. Generator is a seeded
  template grammar, now at **v1.3**, default **4,000 records** at seed 42, byte-reproducible with
  no API key. Fail-closed allow-list; structural provenance; time-aware metadata at 100% coverage
  on all five required fields. **Consequence: OPEN-011 is the project's highest live risk.**
- **Objective:** Get raw text in with provenance **and lightweight temporal/context metadata**.
- **Tasks:** Har Agent implements `src/ingestion/`; each source writes `provenance.json`
  (source, date, license). Respect the Phase 5 allow-list. **New (from evidence review):** where
  available, capture **timing relative to the competition** (e.g., days-before) and any **light
  context** (sport, level, training-load/physiological hints) as optional metadata fields - even if
  sparse. This makes the corpus temporal- and fusion-ready without committing to those models now.
- **Parallel agents:** Har (can fan out per source).
- **Deliverable:** `data/raw/` populated with provenance + optional `time_to_competition` / context fields.
- **Gate:** Every raw record traceable to a licensed/consented/synthetic source; temporal/context
  fields present where the source allows (nullable otherwise).

### Phase 8 - Preprocessing & de-identification - ✅ COMPLETE
- **Outcome:** 4,000 records → **13,651 utterances**, 0 dropped. De-identification measured against
  a 34-case fixture: precision 100%, recall 100%, exact 34/34, **leak rate 0%**, negatives 8/8,
  plus a held-out 10/10 probe reported but deliberately not gated. **Read that as an upper bound**
  - the A2 generator plants no identifiers, so the fixture measures the failure modes we thought to
  write down. Re-measure against real text when OPEN-011 resolves.
- **Objective:** Clean, segment, and strip PII.
- **Tasks:** `src/preprocessing/` - normalization, utterance segmentation, language filter,
  `deidentify.py` (remove names/handles/locations). Output `data/interim/`.
- **Parallel agents:** Har.
- **Deliverable:** Clean, de-identified utterance corpus.
- **Gate:** Spot-check sample shows no direct identifiers remain.

### Phase 9 - Exploratory data analysis & quality profiling - ✅ COMPLETE
- **Objective:** Understand the corpus before labeling.
- **Delivered:** `src/evaluation/{profile,sampling,figures}.py` (pure Python, no new deps),
  `scripts/run_eda.py` (the gate), `reports/eda.md` + 9 SVG figures, `notebooks/01_eda.ipynb` as a
  thin viewer over tested functions, and `data/processed/gold_candidates/sampling_plan.json`.
- **The gold-set sampling plan is the real deliverable.** The obvious plan - draw from the test
  side of `template_disjoint_split` - leaves `appraisal_orientation` with **zero** items, because
  that function shuffles all 85 templates as one pool. Templates are now partitioned **per
  construct** (35% holdout, floor of one), records assigned only if *every* template is held out,
  duplicates and sub-annotatable items filtered, then drawn construct-quota-first and
  context-balanced. 400 `gold_eval` + 100 `gold_dev`, 100% double-annotated, `generation_spec`
  stripped from every candidate.
- **Four defects found, three fixed in-phase:** OPEN-016 (15.8% of records carried an
  ungrammatical substitution → **0%** via a generation-time guard), OPEN-017 (gold pool too small
  → corpus raised to 4,000, **0/10** constructs below floor), OPEN-019 (`generation_spec` is
  replicated per utterance - documentation), and OPEN-018 (**87.4%** utterance duplication,
  mitigated in the sampling plan, root cause open).
- **Gate:** ✅ Documented data-quality issues and a stratified sampling plan.

### Phase 9b - Corpus hardening - ✅ COMPLETE *(inserted and executed 2026-08-10)*

- **Delivered:** template bank 7–12 → **15 realisations per construct** (150 templates);
  discourse suffixes converted from sentences to **clauses**; `_vary` extended to the discourse
  frame, the interpretation modifier and construct-free records; generator **v1.4**.
- **Measured:** realised vocabulary **625 → 860** (+38%) · distinct record texts 94.9% → 97.2%
  · utterance duplication **87.4% → 37.6%** · utterance count 13,651 → 9,302 on a corpus that
  did not shrink · **median utterance length 9 → 17 tokens**, which independently fixes the
  "too short to annotate" problem Phase 9 flagged · defective substitutions still **0/4,000**.
- **The obvious fix for OPEN-018 was implemented first and did nothing.** Expanding the suffix
  bank from 8 entries to 17 spread the repeats without reducing them, because each suffix was
  still its own sentence and Phase 8 still segmented it into its own utterance. **Bank size was
  never the lever; sentence-hood was.** Worth carrying into the paper: the diagnosis that feels
  obvious is the one to measure first.
- **The ratchet blocked the build 28 times** - new templates create new substitution frames,
  each needed a human verdict, 19 were `broken`. Not one was found by reading.
- **A Phase 7 claim was falsified:** OPEN-021, the lexicon baseline is not independent of the
  corpus. See the risk table above.
- **Gate:** ✅ ≥14 templates per construct · duplication materially below 87.4% · all four
  gates pass · sweep reports zero unruled signatures and zero realised defects.

---

### Phase 9b - original brief *(retained for the record)*
- **Why this exists.** Phase 9 measured two things that cannot be fixed downstream and that both
  attack contribution #1 at its weakest point. Doing them now costs ~1 day and one
  regenerate-and-re-gate cycle. Doing them after Phase 10 means paying for silver labels twice.
- **Objective:** Make the corpus able to support a kappa a reviewer will believe.
- **Tasks:**
  1. **OPEN-020 - expand the template bank to ~15 realisations per construct** (from 7–12). This
     is the one that matters. At the current size a 35% holdout leaves 2–4 phrasings per construct
     in the evaluation set, so the kappa describes those phrasings rather than the construct. It
     also raises the fraction of utterances that actually realise a construct (currently 0.62),
     which corpus size provably cannot: swept at 1.2k/4k/6k/8k records, the fraction stays at
     0.59–0.62 because it is a per-*record* property.
  2. **OPEN-018 option (a) - apply `_vary` to `DISCOURSE_SUFFIXES` and `NEUTRAL_SENTENCES`.**
     They are currently emitted verbatim, and Phase 8 segments each into its own utterance, so
     `"It is what it is."` appears hundreds of times. 87.4% of utterances are exact duplicates.
  3. Re-run the synonym sweep. **New templates create new substitution frames**, so the build will
     fail until each flagged signature is ruled in `substitution_verdicts.VERDICTS`. That is the
     ratchet working - budget for it.
  4. Regenerate at seed 42; re-run all four gates; update `reports/eda.md`, `docs/data_sources.md`
     and the fixed-corpus assertions in `tests/test_profile.py` **in the same change**.
- **Parallel agents:** Psy (writes realisations against the rubric), Eval (re-runs the profile).
- **Deliverable:** v1.4 corpus + refreshed EDA report.
- **Gate:** ≥14 templates per construct; utterance duplicate rate materially below 87.4%;
  cue-corrected construct coverage ≥40 for at least 8 of 10 constructs; all four gates pass;
  synonym sweep reports zero unruled signatures and zero realised defects.
- **Explicitly NOT in scope:** anything requiring an API key, and any change to the taxonomy
  (frozen until Phase 12).

---

## WEEK 3 - Labeling & Gold Standard

### Phase 10 - Cost-aware LLM weak labeling *(parallelized)*
- **Blocked on:** `OPENROUTER_API_KEY` (**OPEN-008**). Do not ship an unexecuted path - that is
  the OPEN-007 mistake. Either get the key, or gate the provider behind a mock with the real
  integration test hidden behind an env flag. **`pytest` must never be able to spend money.**
- **Do Phase 9b first.** Both of its remedies regenerate the corpus, and silver labels computed
  against a corpus about to be replaced are tokens spent twice.
- **Objective:** Produce silver labels cheaply.
- **Tasks:** Lab Agent labels utterances against the taxonomy with rationale + confidence,
  using cheap-tier models, prompt caching, and batching; escalate low-confidence to mid tier.
- **Four things Phase 9 measured that change how this is built:**
  1. **Deduplicate before the API call.** 87.4% of utterances are exact duplicates; there are
     3,131 distinct strings, not 13,651. Label the distinct set and fan results back out - that is
     roughly a **77% saving** on the phase's entire budget, and it costs one `dict`.
  2. **Abstention must be a first-class answer.** ~38% of utterances carry no construct at all. A
     labeller that never returns "none" is broken, not thorough.
  3. **Pass the parent record as context.** Median utterance is 9 tokens - too short to judge
     `appraisal_orientation` alone. `parent_record_id` is on every interim record for this.
  4. **Placeholders must survive the prompt intact** and the model must be told what `[ATHLETE]`
     and `[EVENT_WINDOW]` mean rather than left to guess.
- **The circularity trap.** This phase produces something that *is* a label, stored next to
  records carrying `generation_spec`, which is not one. Never evaluate silver against
  `generation_spec` - that measures whether an LLM can recover this project's own template
  choices. Silver is evaluated against the Phase 11 human gold set and nothing else.
- **Parallel agents:** Lab ×N shards.
- **Deliverable:** `data/processed/silver/` + per-shard cost logs.
- **Gate:** Full corpus silver-labeled under budget; confidence recorded per label; every call has
  a routing decision and a `logs/cost_ledger.csv` entry.

### Phase 11 - Gold standard human verification
- **Outcome (2026-09-28):** Ran with **one** annotator (A1), not the two planned below. A2 had
  agreed (2026-08-12) but never sat down to annotate, and time didn't allow further waiting.
  `gold_dev`: 100/100 items intensity-labelled, **96/100 with valid spans** (4 excluded honestly,
  not faked or zeroed - see `CLAUDE.md` sec.20). Kappa is undefined with one annotator, so the
  owner decided to drop the inter-annotator-agreement claim rather than leave it perpetually
  pending: `src/annotation/agreement.py` and `src/taxonomy/refinement.py` were deleted
  (backup under `annotation/gold_dev/_backup_2026-09-28/removed_20260928/`), and this phase's
  gate is now "single-annotator, span-anchored gold; no IAA reported" - a named limitation in
  the paper, not an omission. `gold_eval` (400 items) remains unannotated.
- **Objective:** A trustworthy evaluation set.
- **The sample is already drawn.** `data/processed/gold_candidates/` holds `gold_eval.jsonl`
  (400 items) and `gold_dev.jsonl` (100), with `sampling_plan.json` recording the template
  partition and every parameter. Regenerate with `python scripts/run_eda.py`. **Do not redraw by
  hand** - the plan is what makes the evaluation set leakage-safe, and it is asserted by tests.
- **Order of operations, and it is load-bearing:** annotators calibrate on `gold_dev` **first**,
  argue over the rubric, revise `docs/annotation_guidelines.md`, and only then start `gold_eval`.
  `gold_dev` is drawn from *training-side* templates precisely so that burning it on rubric
  arguments costs zero evaluation power. An item read during an argument about the rubric is no
  longer an independent measurement.
- **Tasks:** Saikalyan + ≥1 peer annotate **every** `gold_eval` item independently using the
  rubric (100% double annotation, so kappa is computable *per construct*); QA Agent surfaces
  conflicts; adjudicate; compute inter-annotator agreement.
- **Parallel agents:** QA (assist only - humans own gold).
- **Deliverable:** `data/gold/` + `reports/iaa.md`.
- **Gate:** Per-construct Cohen's kappa reported **with a bootstrap interval, never a bare point
  estimate** - at 40 items the interval is roughly ±0.20 wide, enough to separate "substantial"
  from "fair" and not enough to separate 0.70 from 0.75. 400 utterances gold-labelled.
- **`data/gold/` is human-owned.** No agent writes there; the store guards refuse the root.

### Phase 12 - Label validation & taxonomy refinement
- **Outcome (2026-09-28):** The disagreement-driven half of this phase (`--refine`, and
  `src/taxonomy/refinement.py` underneath it) was deleted along with Phase 11's agreement
  machinery - there is no measured disagreement left to analyse. The construct set freezes on
  burden + owner rubric review instead of burden + measured kappa. `--burden` and `--propose`
  are unaffected and still run. See `CLAUDE.md` sec.20-21.
- **Objective:** Fix schema problems the data exposed.
- **Tasks:** Analyze disagreement patterns; refine `taxonomy.yaml`/guidelines; re-label affected silver.
- **Parallel agents:** Psy, Lab.
- **Deliverable:** v2 taxonomy + changelog.
- **Gate:** Post-refinement agreement improves or is justified; dataset frozen for modeling.

---

## WEEK 4 - Modeling

### Phase 13 - Baselines *(parallelized)*
- **Objective:** Establish the bar the transformer must beat.
- **Tasks:** Mod Agent trains a lexicon baseline and TF-IDF + LogReg/SVM multi-label baselines
  with fixed seeds and a held-out split.
- **Parallel agents:** Mod ×2 (lexicon + classical, in parallel).
- **Deliverable:** Baseline metrics in `reports/`.
- **Gate:** Reproducible baseline macro-F1 recorded.
- **Outcome (2026-08-11): gate PASSED, every number PROVISIONAL.**
  `src/models/{dataset,classical}.py`, `scripts/run_baselines.py`, `tests/test_models.py` (19 tests).
  Reproducibility is asserted at full float precision, not `approx`.

  | system | template-disjoint macro-F1 [95% CI] | random | gap |
  |---|---|---|---|
  | majority | 0.000 | 0.000 | +0.000 |
  | stratified random | 0.104 [0.082, 0.126] | 0.175 | +0.071 |
  | memorisation probe | 0.197 [0.162, 0.228] | 0.720 | +0.523 |
  | **lexicon** | **0.462 [0.432, 0.494]** | 0.562 | +0.100 |
  | TF-IDF + LogReg | 0.222 [0.181, 0.259] | 0.999 | +0.777 |
  | TF-IDF + LinearSVC | 0.181 [0.150, 0.212] | **1.000** | **+0.819** |

  Three findings the paper should carry:
  1. **The bar for Phase 14 is the lexicon at 0.462**, not the learned models. Both classical
     models score *below* the lexicon on the honest split. The 0.462 also independently
     reproduces the OPEN-021 floor of 0.461.
  2. **A linear model over TF-IDF memorises this corpus perfectly** - 1.000 macro-F1 on a
     random split, 0.181 template-disjoint. The +0.819 gap is the strongest evidence yet for
     OPEN-012 and belongs in the paper as a result, not a diagnostic.
  3. These are **planted-label corpus-property measurements, not accuracy.** `data/gold/` is
     empty (OPEN-025). `--gold` refuses rather than falling back to silver.

### Phase 14 - Transformer fine-tuning
- **Objective:** The main model.
- **Tasks:** Fine-tune DeBERTa/RoBERTa multi-label classifier on gold+silver; hyperparameter
  sweep; experiment tracking; save `models/` + model card.
- **Parallel agents:** Mod.
- **Deliverable:** Trained classifier + run logs + `docs/model_card.md`.
- **Gate:** Transformer > best baseline on macro-F1 on the held-out set.

### Phase 15 - Risk scoring layer *(fusion-ready)*
- **Objective:** Turn constructs into an interpretable risk index.
- **Tasks:** `src/risk/` - fuse construct probabilities into 0–1 risk with per-construct
  contributions; calibrate (temperature/Platt); document the scoring rationale. Reflect the expanded
  taxonomy: resilience & challenge-appraisal **lower** risk, threat-appraisal & debilitative
  interpretation **raise** it. **Design the interface to optionally accept light non-text context
  features** (timing, training-load) so multimodal fusion is a drop-in later - but keep **text-only
  as the primary, reported model**.
- **Parallel agents:** Mod, Psy (weights sanity-check).
- **Deliverable:** Calibrated risk scorer (text-only) + `reports/calibration.md`.
- **Gate:** Calibration error (ECE) reported; risk decomposition is human-readable; interface accepts
  optional context features without breaking the text-only path.

### Phase 16 - (Optional) DataRobot / AutoML benchmark
- **Objective:** External sanity check on the tabular construct→risk step.
- **Tasks:** If a DataRobot account is available, benchmark AutoML on the construct-feature table;
  otherwise use scikit-learn AutoML-style search. Compare, don't replace.
- **Parallel agents:** Mod.
- **Deliverable:** `reports/automl_comparison.md`.
- **Gate:** Comparison table produced (skippable without penalty).

---

## WEEK 5 - Explainability & Evaluation

### Phase 17 - Explainability module **+ expert validation (headline contribution)**
- **Objective:** Attribute risk to text AND show the explanations are meaningful to practitioners -
  the gap the evidence review flagged as most open (sports XAI is rarely practitioner-validated).
- **Tasks:**
  1. Exp Agent implements SHAP and/or attention rollout; generate "profile cards"
     (text → highlighted spans → constructs → risk).
  2. **Expert-validation study (small but real):** recruit 1–3 raters (a coach and/or sport-psychology
     student/practitioner); give them ~15–20 profile cards; collect a simple rating of whether each
     span→construct explanation is sensible/agree-disagree + free-text notes. Report agreement (e.g.
     % agreement or a simple kappa) in `reports/explain/expert_validation.md`.
- **Prep/decide (start EARLY - recruiting takes time):** identify the rater(s) now; prepare a 1-page
  rating form; keep it de-identified and low-burden.
- **Parallel agents:** Exp (cards) + human (runs the rating study).
- **Deliverable:** `reports/explain/` worked examples **+ `expert_validation.md`** with rater results.
- **Gate:** ≥5 sensible qualitative examples **and** ≥1 external rater's agreement scores reported.
  (If no rater can be found in time, downgrade to a documented self-audit + name it a limitation -
  but try hard to get at least one expert.)

### Phase 18 - Evaluation harness & ablations *(parallelized)*
- **Objective:** The numbers that go in the paper.
- **Tasks:** Eval Agent runs per-construct P/R/F1, macro/micro F1, calibration, human-agreement,
  and ablations (baseline vs transformer; ±silver data; ±risk fusion). Error analysis.
- **Parallel agents:** Eval ×N (one ablation per worker).
- **Deliverable:** `reports/results.md` + all paper figures/tables.
- **Gate:** Every claim the paper will make is backed by a logged experiment.

### Phase 19 - Results aggregation & narrative
- **Objective:** Decide the story the data tells.
- **Tasks:** Consolidate metrics; identify the 2–3 headline findings; note negative results honestly.
- **Parallel agents:** Eval, Pap.
- **Deliverable:** `docs/findings.md`.
- **Gate:** A clear, evidence-backed contribution statement.

---

## WEEK 6 - System, Security & Reproducibility

### Phase 20 - Dashboard / visualization
- **Objective:** A demo that communicates the system.
- **Tasks:** Streamlit app: paste text → construct bars + risk gauge + highlighted spans;
  Dockerized. This becomes a paper figure and a demo.
- **Parallel agents:** -
- **Deliverable:** `dashboard/` app + screenshots.
- **Gate:** App runs in Docker and reproduces a known example.

### Phase 21 - Security scan, dependency & PII audit
- **Objective:** Ship something safe and clean.
- **Tasks:** Sec Agent runs the security-scan workflow on the repo/`.claude` config; scans for
  committed secrets; dependency vulnerability check; final PII sweep of released data.
- **Parallel agents:** Sec.
- **Deliverable:** `docs/security.md` (findings + fixes).
- **Gate:** No secrets in git history; no high-severity dep issues; released data PII-clean.

### Phase 22 - Reproducibility packaging
- **Objective:** A reviewer can rerun it.
- **Tasks:** Pin versions; fix all seeds; finalize Docker; write run scripts; complete model card;
  prepare an anonymized artifact for release.
- **Parallel agents:** Mod, Sec.
- **Deliverable:** One-command reproduction path + artifact.
- **Gate:** Fresh clone reproduces headline numbers within tolerance.

---

## WEEK 7 - Paper

### Phase 23 - IEEE draft assembly *(parallelized by section)*
- **Objective:** Full first draft.
- **Tasks:** Pap Agent drafts sections from artifacts - abstract, intro, related work, method,
  dataset, experiments, results, ablation, ethics & limitations, conclusion. Different sections
  drafted in parallel, human-edited.
- **Parallel agents:** Pap ×N (one section per worker), Lit (citations).
- **Deliverable:** `paper/main.tex` compiling in the IEEE template.
- **Gate:** Compiles two-column; every section present; every figure/table referenced.

### Phase 24 - Figures, tables & polish
- **Objective:** Camera-quality presentation.
- **Tasks:** Finalize figures (pipeline diagram, results, calibration, explainability card);
  clean tables; check citation formatting; page-limit fit.
- **Parallel agents:** Eval, Pap.
- **Deliverable:** Polished, page-limit-compliant draft.
- **Gate:** Within page limit; figures legible in grayscale.

### Phase 25 - Internal review, red-team & submission prep
- **Objective:** Reviewer-proof it before submitting.
- **Tasks:** Devil's-advocate review (a critique agent + a human) against likely reviewer
  objections; fix novelty/rigor/ethics gaps; proofread; prepare submission package for
  iTriply Explore / IEEE by the 1st week of September.
- **Parallel agents:** Lit, Sec, Pap.
- **Deliverable:** Submission-ready paper + artifact link.
- **Gate:** Addresses the top predictable reviewer objections; passes a plagiarism/formatting check.

---

## WEEK 8+ - Post-submission extension

### Phase 26 - Cognitive layer (V1 / V3 / V5) *(stretch; gated on "starts only after Phase 23 ships" - **gate breached 2026-09-13**, see the phase-order debt note in the status board)*
- **Objective:** Add a cognitive/physiological presentation layer over the existing text pipeline -
  a construct→brain-network atlas (V1), a cognitive-load panel from HRV + webcam oculometrics (V3),
  and a closed-loop neurofeedback demo (V5) - **without moving a single number in the paper**.
- **Scope decision (owner, 2026-09-13):** simulated signals only, behind a hardware-ready seam.
  No headset, no strap, no participant. V5 ships in **demo mode**: the loop closes against a
  simulated signal and trains nobody.
- **Why it is safe to bolt on:** `LinearRiskScorer` has carried an unused `context` /
  `context_weights` seam since Phase 15, with the text-only path as a separate tested code path.
  The layer fills that slot at weight zero.
- **Tasks:** new `src/biosignals/` package (Protocol + simulated sources + pure feature functions);
  `src/dashboard/neurovis.py` renderers; `config/brain_atlas.yaml` with one citation per construct;
  three new pages after Dashboard and Score; feature flag `SRN_COGNITIVE_LAYER`.
- **Parallel agents:** Vis, Test.
- **Deliverable:** Three widgets behind a flag; full spec in `.claude.md` §11.
- **Gate (all four required):**
  1. With the flag unset, the dashboard output is byte-identical to Phase 24.
  2. `LinearRiskScorer.score()` is bit-identical with and without the context mapping.
  3. No simulated surface renders without its provenance stamp - asserted, not reviewed.
  4. The atlas contains no activation vocabulary and states "hypothesised association, not imaging".
- **Blocking gate for any real signal:** `docs/ethics.md` and `docs/model_card.md` must be updated
  **before** any physiological data from any person - including the owner's own - reaches this code.
  V5 additionally requires ethics approval and a clinician in the loop before it runs against a
  person, because a closed feedback loop is an intervention, not an observation.
- **Explicitly out of scope for this phase:** real hardware, participant recruitment,
  text↔physiology concordance (the strongest scientific item - deferred to a second paper).

---

## Parallelization Map (what actually runs at once)

- **Week 1:** Phase 3 fans out to 3–4 Literature agents while Phase 2 setup proceeds.
- **Week 3:** Phase 10 labeling shards run in parallel; QA runs alongside.
- **Week 4:** Baselines (Phase 13) train in parallel with each other.
- **Week 5:** Phase 18 ablations run one-per-worker.
- **Week 7:** Phase 23 drafts multiple paper sections concurrently.

## Timeline at a Glance

| Week | Phases | Milestone |
|---|---|---|
| 1 | 1–5 | Repo reset, novelty locked, taxonomy + ethics defined |
| 2 | 6–9 | Agents wired, data ingested, cleaned, profiled |
| 3 | 10–12 | Silver + gold labels, IAA reported |
| 4 | 13–16 | Baselines + transformer + risk index |
| 5 | 17–19 | Explainability + full evaluation + findings |
| 6 | 20–22 | Dashboard, security, reproducible artifact |
| 7 | 23–25 | IEEE draft → reviewed → submission-ready |
| 8 | buffer | Slack for slippage + final proofing |
| 8+ | 26 | Cognitive layer V1/V3/V5 - stretch, flag-gated, simulated only |

## Risk Register (top 5)

1. **Data scarcity/licensing** (highest risk) - mitigate via synthetic augmentation + a small
   high-quality gold set; decided in Q3 / Phase 6–7.
2. **Weak labels too noisy** - mitigate with confidence thresholds, human gold anchor, Phase 12 refinement.
3. **Scope creep** - mitigate by parking stretch goals (see expansion list) until core is done.
   **Phase 26 was the live instance of this risk, and the risk landed.** It is visually
   compelling, it is not on the critical path to the paper, it started before Phase 23
   shipped, and Phases 27–32 followed it. Recorded as realised 2026-09-23 rather than left
   standing as a warning about a future that already happened.
4. **Expert-rater access** (new - Phase 17) - the expert-validation contribution needs ≥1 coach or
   sport-psych practitioner. **Start recruiting in Week 1–2**, not Week 5. Fallback: documented
   self-audit named as a limitation.
5. **Annotation burden from expanded taxonomy** - resilience + appraisal + interpretation modifier
   raise labeling load; mitigate by freezing the final set at Phase 12 after an agreement check, and
   dropping any construct with poor inter-annotator agreement.
```

---

## PHASE 27 - Media input, admission gates and the register test ✅ COMPLETE (2026-09-15)

**Goal.** Let the live-scoring page accept a photograph or a short video, recover
the words from it, and score them exactly as typed words are - while refusing
everything that cannot honestly be scored, and without letting a face move a
number in the paper.

**Why it was not in the original 25-phase plan.** It was not. It arrived as an
owner request during the Phase 26 deployment pass. It is recorded here as its own
phase rather than folded into 26 because it introduces a new input modality, a
new privacy class, and a blocking ethics gate - three things that deserve their
own row in a plan.

### Work items

| # | Item | State |
|---|---|---|
| 27.1 | Remove "Research prototype" from headers; fix dark-mode announcement colours | ✅ |
| 27.2 | Remove every em dash from user-facing copy | ✅ 0 remaining |
| 27.3 | Policy selector shared across pages; the four two-sided tiles react to it | ✅ two bugs fixed |
| 27.4 | Junk-text admission gate on the live-scoring page | ✅ `src/dashboard/gibberish.py` |
| 27.5 | Photo and video upload, parsed and scored | ✅ `src/media/` |
| 27.6 | Media admission gate - ignore unreadable and unwanted files | ✅ `src/media/admission.py` |
| 27.7 | Non-verbal channel, stamped, zero-weighted, ethics-gated | ✅ `src/media/nonverbal.py` |
| 27.8 | Register test, fitted on dev, reported on held-out | ✅ 0.85 held-out recall |
| 27.9 | OCR direct to the upstream Tesseract engine | ✅ two dependencies removed |
| 27.10 | `docs/ethics.md` §13 - the blocking gate, discharged | ✅ |
| 27.11 | `docs/model_card.md` §11 | ✅ |
| 27.12 | Deployment: `packages.txt` (Streamlit Community Cloud) and `Dockerfile` apt layer | ✅ |

### Merge gates (all met)

* Every existing test green; 93 new tests added across three files.
* Risk index **bit-identical** with and without an attached file at default weights.
* Register test reports a held-out figure, not a development figure.
* No new surface renders a number without its stamp.
* `docs/ethics.md` updated **before** the media path was allowed to remain.

### Two defects found and fixed during the phase

1. **The policy selector never crossed pages.** Streamlit garbage-collects a
   widget's state when that widget is not rendered on the current page, so the
   Score page always scored under the conservative default no matter what the
   dashboard was set to. Same defect the light/dark control had in Phase 22, same
   fix: a plain session key.
2. **OCR availability checked the wrong thing.** It asked whether `pytesseract`
   and `PIL` imported. Both are pip packages that install cleanly on a machine
   with no OCR engine - so the check returned True on exactly the machines where
   OCR does not work, and every upload showed a coach a Python exception type.

### Known limitation carried forward

The default known example (`synth_precomp_v1-003481`) triggers none of the four
two-sided constructs, so the policy selector correctly changes nothing on it.
Both pages now report how many two-sided signals the text triggered, so a no-op
switch explains itself rather than looking broken. **OPEN-027:** consider
ordering the example list so the default selection demonstrates the control.

---

## PHASE 28 - Facial cues, under consent, inside the index ✅ COMPLETE (2026-09-16)

**Goal.** Read `negative_valence` and `arousal` from the largest face in an
uploaded photograph, under an uploader consent attestation, and let those two
cues move the risk index at small, declared (not fitted) weights - closing the
seam Phase 27 built and then bolted shut (`GatedRealReader`).

### Work items

| # | Item | State |
|---|---|---|
| 28.1 | `src/media/facecues.py` - `hsemotion-onnx` + OpenCV Haar cascade reader | ✅ |
| 28.2 | Consent as a construction precondition (`FaceCueReader(consent=...)`) | ✅ |
| 28.3 | Only a measured reading carries weight; simulated reading stays at zero | ✅ |
| 28.4 | Mandatory limitation rendered above every face-derived score | ✅ `copy.FACE_CUES_LIMITATION` |
| 28.5 | `docs/ethics.md` §14 - the blocking gate, discharged for facial cues only | ✅ |
| 28.6 | `docs/model_card.md` §12 | ✅ |
| 28.7 | `tests/test_facecues.py` | ✅ |

### Merge gates (all met)

* Consent-refused construction asserted (`NonVerbalEthicsGate` fires).
* Simulated-reading feature names disjoint from `FACE_WEIGHTS` keys, so a
  missing library or absent consent can never move the index.
* Text-only score remains visible beside the combined score.
* `docs/ethics.md` updated **before** `facecues.py` was allowed to remain.

---

## PHASE 29 - Match-day profile: built, blocked by default (2026-09-19)

**Status: ⚠ CODE AND TESTS COMPLETE. FEATURE INERT.** Not a merge gate in the
usual sense - the gate this phase must clear is an owner ethics decision, not a
test suite, and that decision has not been made. See `CLAUDE.md` §14 and
`docs/ethics.md` §15 for the full record.

**Goal as requested.** Given a press-conference link and a photograph, produce
one final score for that specific athlete.

**What was found on review.** The feature as requested is the exact act
`docs/ethics.md` §2.3.3 and §13.4 already prohibit in writing: a claim about a
named, identifiable public figure's psychological state, from their own public
material. De-identifying the transcript text does not de-identify who the
reader is looking up. This was found and gated **before** the code was
committed, not after a report.

### Work items

| # | Item | State |
|---|---|---|
| 29.1 | `src/media/pressroom.py` - captions via `youtube-transcript-api`, speech via `yt-dlp` + `faster-whisper` (local only) | ✅ built |
| 29.2 | `src/dashboard/matchday.py` - de-identify, fuse text + face, one score | ✅ built |
| 29.3 | `dashboard/pages/6_Match_day_profile.py` | ✅ built |
| 29.4 | Ethics gate: `fetch_transcript` refuses unless `SRN_MATCHDAY_REAL_ATHLETES` is set | ✅ blocks by default |
| 29.5 | `docs/ethics.md` §15 - the blocking gate, NOT discharged | ✅ documents the block |
| 29.6 | `tests/test_pressroom.py` - gate-closed and gate-open behaviour both asserted | ✅ |
| 29.7 | Owner decision to ever unblock `SRN_MATCHDAY_REAL_ATHLETES` | ❌ not made; see `docs/ethics.md` §15.4 |

### Merge gates

* All existing tests remain green with the gate added.
* The gate fires before any network call - asserted, not just documented.
* No code path in the repository, the deploy repo, or `.env.example` sets the
  flag. The deployed Streamlit Community Cloud app ships the feature inert.
* `CLAUDE.md` and `docs/ethics.md` updated **before** this phase's code was
  committed, recording the block rather than a discharge.

---

## PHASE 30 - Scenario-driven match-day profile (synthetic) ✅ COMPLETE (2026-09-20)

**Goal.** Phase 29's real-athlete path stays inert (owner declined,
`docs/phase29_decision_draft.md`). Give the same page something honest to
score in the meantime: a scenario the reader picks from dropdowns -
sport, timing, life context - generated by the *same* seeded template
grammar that built `synth_precomp_v1-*` (`src/ingestion/synthetic.py`), so a
different life context plants a measurably different construct set and the
score moves for a real reason, not just a different label on generic text.

### Work items

| # | Item | State |
|---|---|---|
| 30.1 | `src/ingestion/scenarios.py` - `MatchDayScenario`, `SCENARIO_BIAS` table, `generate_scenario_record` | ✅ built, `synthetic.py` untouched |
| 30.2 | `src/dashboard/matchday.py` - `build_scenario_profile` bridge, `SCENARIO_STAMP` | ✅ built |
| 30.3 | `dashboard/pages/6_Match_day_profile.py` - dropdowns + "Generate & score", placed *before* the real-link gate so it always renders | ✅ built |
| 30.4 | `tests/test_scenarios.py` - determinism, validation, and a statistical check that life_context changes the construct set ≥90% of the time | ✅ 14 tests, all green |
| 30.5 | End-to-end check: same sport/timing, five life contexts, through the real `LexiconBackend` | ✅ scores 50 / 62 / 27 / 82 / 73 |

### Merge gates (all met)

* `src/ingestion/synthetic.py` has zero diff - the bias table lives in a new
  module that imports its realisation banks and framing helpers, never
  modifies its RNG-sensitive internals.
* Every construct cited in `SCENARIO_BIAS` reuses the same `config/taxonomy.yaml`
  instrument anchor the construct already carries - no invented grounding.
* "none" life context falls back to `synthetic._draw_constructs`'s ordinary
  unbiased draw rather than being a fifth, invented context.
* The scenario section renders regardless of whether the gated real-athlete
  fetch ever succeeds (it is placed before that path's `st.stop()`).
* `SCENARIO_STAMP` is distinct from `PRESS_STAMP` so a reader can never
  mistake a generated scenario for a real, fetched transcript.

---

## PHASE 31 - Abstention-aware evaluation + demo cue widening ✅ COMPLETE (2026-09-21)

**Goal.** Measure the three refusal gates for the first time, and compute the number
`CLAUDE.md` §12.3 only asserted: the index each refused input *would* have received had
the gate not been there.

### Work items

| # | Item | State |
|---|---|---|
| 31.1 | `src/evaluation/abstention.py` - gates, counterfactual index, four-cause decomposition | ✅ |
| 31.2 | `scripts/run_abstention_report.py` → `reports/abstention.{md,json}` | ✅ |
| 31.3 | `DASHBOARD_EXTRA_CUES` widening, demo path only | ✅ owner decision 2026-09-21 |
| 31.4 | `tests/test_abstention.py` - arithmetic, reachability, honesty rules | ✅ |

### The finding

An index of exactly 0.50 is reached three ways and the gates close only the narrowest:
`refused` 1/500 (0.2%), `no_detection` 293/500 (58.6%), `all_inert` 62/500 (12.4%).
**355 of 500 corpus texts are admitted, scored, and handed back the midpoint anyway.**
This contradicted the comfortable reading of §12.3 and is recorded as such.

### Merge gates (all met)

* The counterfactual uses the **frozen** `CONSTRUCT_CUES`; `LexiconBaseline` and macro-F1
  0.462 are untouched, and `tests/test_abstention.py` holds the two cue lists apart.
* Every widened phrase came from a `synthetic.py` realisation template that states its own
  construct - never from corpus text, which would be OPEN-021 by another route.
* `src/evaluation/abstention.py` is **not** re-exported from the package `__init__`; an
  eager re-export tripped the OPEN-036 import cycle and was removed, not worked around.

---

## PHASE 32 - Evidence coverage: what a text could not speak to ✅ COMPLETE (2026-09-23)

**Goal.** Project one already-scored `DashboardView` onto the eight validated instruments
behind the taxonomy and report, per subscale, whether the text gave any evidence at all.
The risk index is rendered today with no statement of how much evidence it rests on; this
supplies the denominator. Plan: `docs/phase32_implementation_plan.md`.

### Work items

| # | Item | State |
|---|---|---|
| 32.1 | `config/instruments.yaml` + `src/dashboard/instruments.py` - instrument → subscale → construct, one citation per row, every citation resolving in `paper/refs.bib` | ✅ |
| 32.2 | `src/dashboard/coverage.py` - the four-state ledger, pure, no I/O | ✅ |
| 32.3 | `src/dashboard/coverage_panel.py` + `dashboard/pages/7_Evidence_coverage.py` | ✅ |
| 32.4 | `widgets.coverage_widget`, `docs/dashboard.md`, `docs/model_card.md` | ✅ |
| 32.5 | `tests/test_coverage.py` | ✅ 38 tests |
| 32.7 | Suite, measured both sides 2026-09-23 | ✅ **1095 passed / 2 skipped** at `e1f9787`; **1136 passed / 2 skipped** at HEAD. Zero regressions |
| 32.6 | Post-review corrections (2026-09-23): cue-list attribution, measured coverage shape, `CLAUDE.md` §16, this section | ✅ |

### The finding, as corrected

The plan claimed a realistic passage speaks to "a quarter of the instrument set" from three
hand-picked passages. Measured over every text: `gold_dev` mean **0.62 of 8** (0: 40, 1: 58,
2: 2), `gold_eval` mean **0.56 of 8**. A typical text speaks to zero or one instrument;
40% of `gold_dev` speaks to none.

### Merge gates (all met)

* The risk index is bit-identical with and without the ledger - it is a read-only projection
  and introduces no number the view does not carry.
* `src/dashboard/` does **not** import `src.evaluation.abstention`; the two modules agree on
  the four states by construction, with an agreement test that imports both.
* No coverage figure appears anywhere without the cue list that produced it - **58.8%**
  frozen, **20.2%** widened, both measured in `reports/abstention.md` §4.
* The panel is a **superset** of `reports/evidence_coverage_mockup.html`: same table, summary,
  caveats and stamp, plus the state legend and the N4 prompts block the mockup predates.
* Ships unflagged, by decision: it introduces no source, no signal, no dependency, no number.
