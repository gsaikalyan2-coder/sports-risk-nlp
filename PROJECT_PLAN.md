# PROJECT_PLAN.md — 25-Phase Blueprint

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Owner:** Saikalyan (SRMIST, sophomore) · **Window:** 8 weeks · **Paper due:** 1st week Sept 2026

**Confirmed stack (2026-07-23):** CrewAI (agents) · OpenRouter (cost-tier LLM routing) ·
public/licensed datasets first (hybrid synthetic fallback) · DeBERTa/RoBERTa · Docker · Streamlit · LaTeX.

**Evidence-backed novelty (updated 2026-08 from the Phase 3 review — see `docs/related_work.md`):**
Three-part contribution — (1) construct-grounded athlete-text corpus bridging validated constructs to
text; (2) **two-level, expert-validated interpretability** (span→construct + construct→risk), the
headline differentiator that fills the Interpretability-Validation gap; (3) time-aware, fusion-ready
design. Taxonomy expanded with **resilience** and **appraisal orientation (challenge/threat)** plus an
**interpretation-direction** modifier on anxiety.

**Expansions status (revised):** *Temporal* is now partly in-scope as **lightweight time-aware
sampling** (Phase 7) with full temporal modeling still Future Work; *Multimodal* is **architecture-ready**
(risk layer accepts optional light context, Phase 15) but not built; *Outcome linkage* is the one full
stretch attempted in-window if data allows; *Team aggregation* stays Future Work.

**How to read this:** phases are sequential *by dependency*, but many run **in parallel**
(shown in the "Parallel agents" column). Each phase has an objective, tasks, the agents
involved, a concrete deliverable, and a **gate** (the acceptance check that must pass before
the phase counts as done). Do not skip gates — they are what keep the paper defensible.

**Legend for agents:** Lit = Literature · Psy = Taxonomy/Psych · Har = Harvester ·
Lab = Labeling · QA = Annotation-QA · Mod = Modeling · Eval = Evaluation · Exp = Explainability ·
Sec = Security/Ethics · Pap = Paper.

---

## WEEK 1 — Foundation & Framing

### Phase 1 — Backup, wipe, and re-scaffold the repo
- **Objective:** Clean slate without losing history.
- **Tasks:** Create a `legacy-backup` git branch of the current repo; on `main`, delete old files;
  create the folder structure from `.claude.md` §7; add `.gitignore`, `README.md`, `.env.example`.
- **Parallel agents:** — (human + Claude)
- **Deliverable:** Empty, well-structured repo committed.
- **Gate:** `git log` shows backup branch exists; `tree` matches the target structure.

### Phase 2 — Dev environment & tooling
- **Objective:** Reproducible local setup in VS Code.
- **Tasks:** Python 3.11 `venv`; `requirements.txt`/`pyproject.toml`; VS Code extensions (Python,
  Pylance, Ruff, Docker); pre-commit hooks (formatter + secret check); `Dockerfile` + `docker-compose.yml` stub.
- **Parallel agents:** —
- **Deliverable:** `pip install -r requirements.txt` works; `docker compose build` succeeds.
- **Gate:** A hello-world script runs both locally and in the container.

### Phase 3 — Literature review & novelty positioning *(SUBSTANTIALLY COMPLETE — owner-led, 2026-08)*
- **Objective:** Prove the idea is novel and find the gap. ✅ Done via owner's evidence review.
- **Done:** 14 sources synthesized into `docs/related_work.md`; two validated gaps identified
  (construct↔text bridge; unvalidated sports-XAI explanations); three-part contribution written.
- **Remaining:** resolve each Consensus link to a primary DOI and populate `paper/refs.bib`
  (do in Phase 23/24); optionally add a few more transformer/multi-label NLP method citations.
- **Deliverable:** `docs/related_work.md` (drafted) → `paper/refs.bib` (pending).
- **Gate:** ✅ Clear written gap + ≥14 references. Remaining gate item: `refs.bib` with primary sources.

### Phase 4 — Construct taxonomy design
- **Objective:** Lock the label schema grounded in psychometrics.
- **Tasks:** Psy Agent maintains `config/taxonomy.yaml` — now includes **resilience**,
  **appraisal orientation (challenge/threat)**, and an **interpretation-direction** modifier
  (facilitative/debilitative) added from the Phase 3 evidence — and writes
  `docs/annotation_guidelines.md` (examples, edge cases) for every construct including the new ones.
- **Parallel agents:** Psy (uses Phase 3 output).
- **Deliverable:** Taxonomy + annotation rubric.
- **Gate:** Every construct has a definition, a citation anchor, and ≥2 examples. Final set frozen at Phase 12.

### Phase 5 — Ethics, data governance & risk plan
- **Objective:** Set the guardrails before touching data.
- **Tasks:** Sec Agent drafts `docs/ethics.md` (consent/licensing rules, de-identification policy,
  non-diagnosis framing, misuse & bias risks); define what data sources are allowed.
- **Parallel agents:** Sec.
- **Deliverable:** `docs/ethics.md` + a data-source allow-list.
- **Gate:** Written de-identification + non-diagnosis policy that the paper can cite.

---

## WEEK 2 — Data Foundation

### Phase 6 — Confirm decisions & wire the agent framework
- **Objective:** Resolve open questions (Q1–Q3, DataRobot) and stand up orchestration.
- **Tasks:** Lock framework (CrewAI/AutoGen), LLM provider/cost approach, and data strategy;
  implement `src/agents/` crew definitions + `config/model_routing.yaml`.
- **Parallel agents:** —
- **Deliverable:** A runnable "smoke-test crew" that passes a trivial task end to end.
- **Gate:** One orchestrated multi-agent run completes and logs cost to `logs/cost_ledger.csv`.

### Phase 7 — Data ingestion pipeline *(now time-aware)*
- **Objective:** Get raw text in with provenance **and lightweight temporal/context metadata**.
- **Tasks:** Har Agent implements `src/ingestion/`; each source writes `provenance.json`
  (source, date, license). Respect the Phase 5 allow-list. **New (from evidence review):** where
  available, capture **timing relative to the competition** (e.g., days-before) and any **light
  context** (sport, level, training-load/physiological hints) as optional metadata fields — even if
  sparse. This makes the corpus temporal- and fusion-ready without committing to those models now.
- **Parallel agents:** Har (can fan out per source).
- **Deliverable:** `data/raw/` populated with provenance + optional `time_to_competition` / context fields.
- **Gate:** Every raw record traceable to a licensed/consented/synthetic source; temporal/context
  fields present where the source allows (nullable otherwise).

### Phase 8 — Preprocessing & de-identification
- **Objective:** Clean, segment, and strip PII.
- **Tasks:** `src/preprocessing/` — normalization, utterance segmentation, language filter,
  `deidentify.py` (remove names/handles/locations). Output `data/interim/`.
- **Parallel agents:** Har.
- **Deliverable:** Clean, de-identified utterance corpus.
- **Gate:** Spot-check sample shows no direct identifiers remain.

### Phase 9 — Exploratory data analysis & quality profiling
- **Objective:** Understand the corpus before labeling.
- **Tasks:** Notebook EDA — length distributions, vocabulary, class-of-interest prevalence,
  duplicates, junk. Decide sampling strategy for gold set.
- **Parallel agents:** Eval (profiling).
- **Deliverable:** `reports/eda.md` + figures.
- **Gate:** Documented data-quality issues and a stratified sampling plan.

---

## WEEK 3 — Labeling & Gold Standard

### Phase 10 — Cost-aware LLM weak labeling *(parallelized)*
- **Objective:** Produce silver labels cheaply.
- **Tasks:** Lab Agent labels utterances against the taxonomy with rationale + confidence,
  using cheap-tier models, prompt caching, and batching; escalate low-confidence to mid tier.
- **Parallel agents:** Lab ×N shards.
- **Deliverable:** `data/processed/silver/` + per-shard cost logs.
- **Gate:** Full corpus silver-labeled under budget; confidence recorded per label.

### Phase 11 — Gold standard human verification
- **Objective:** A trustworthy evaluation set.
- **Tasks:** Draw a stratified sample; Saikalyan + ≥1 peer annotate independently using the
  rubric; QA Agent surfaces conflicts; adjudicate; compute inter-annotator agreement (kappa).
- **Parallel agents:** QA (assist only — humans own gold).
- **Deliverable:** `data/gold/` + `reports/iaa.md`.
- **Gate:** Kappa reported; a target subset (e.g. a few hundred utterances) gold-labeled.

### Phase 12 — Label validation & taxonomy refinement
- **Objective:** Fix schema problems the data exposed.
- **Tasks:** Analyze disagreement patterns; refine `taxonomy.yaml`/guidelines; re-label affected silver.
- **Parallel agents:** Psy, Lab.
- **Deliverable:** v2 taxonomy + changelog.
- **Gate:** Post-refinement agreement improves or is justified; dataset frozen for modeling.

---

## WEEK 4 — Modeling

### Phase 13 — Baselines *(parallelized)*
- **Objective:** Establish the bar the transformer must beat.
- **Tasks:** Mod Agent trains a lexicon baseline and TF-IDF + LogReg/SVM multi-label baselines
  with fixed seeds and a held-out split.
- **Parallel agents:** Mod ×2 (lexicon + classical, in parallel).
- **Deliverable:** Baseline metrics in `reports/`.
- **Gate:** Reproducible baseline macro-F1 recorded.

### Phase 14 — Transformer fine-tuning
- **Objective:** The main model.
- **Tasks:** Fine-tune DeBERTa/RoBERTa multi-label classifier on gold+silver; hyperparameter
  sweep; experiment tracking; save `models/` + model card.
- **Parallel agents:** Mod.
- **Deliverable:** Trained classifier + run logs + `docs/model_card.md`.
- **Gate:** Transformer > best baseline on macro-F1 on the held-out set.

### Phase 15 — Risk scoring layer *(fusion-ready)*
- **Objective:** Turn constructs into an interpretable risk index.
- **Tasks:** `src/risk/` — fuse construct probabilities into 0–1 risk with per-construct
  contributions; calibrate (temperature/Platt); document the scoring rationale. Reflect the expanded
  taxonomy: resilience & challenge-appraisal **lower** risk, threat-appraisal & debilitative
  interpretation **raise** it. **Design the interface to optionally accept light non-text context
  features** (timing, training-load) so multimodal fusion is a drop-in later — but keep **text-only
  as the primary, reported model**.
- **Parallel agents:** Mod, Psy (weights sanity-check).
- **Deliverable:** Calibrated risk scorer (text-only) + `reports/calibration.md`.
- **Gate:** Calibration error (ECE) reported; risk decomposition is human-readable; interface accepts
  optional context features without breaking the text-only path.

### Phase 16 — (Optional) DataRobot / AutoML benchmark
- **Objective:** External sanity check on the tabular construct→risk step.
- **Tasks:** If a DataRobot account is available, benchmark AutoML on the construct-feature table;
  otherwise use scikit-learn AutoML-style search. Compare, don't replace.
- **Parallel agents:** Mod.
- **Deliverable:** `reports/automl_comparison.md`.
- **Gate:** Comparison table produced (skippable without penalty).

---

## WEEK 5 — Explainability & Evaluation

### Phase 17 — Explainability module **+ expert validation (headline contribution)**
- **Objective:** Attribute risk to text AND show the explanations are meaningful to practitioners —
  the gap the evidence review flagged as most open (sports XAI is rarely practitioner-validated).
- **Tasks:**
  1. Exp Agent implements SHAP and/or attention rollout; generate "profile cards"
     (text → highlighted spans → constructs → risk).
  2. **Expert-validation study (small but real):** recruit 1–3 raters (a coach and/or sport-psychology
     student/practitioner); give them ~15–20 profile cards; collect a simple rating of whether each
     span→construct explanation is sensible/agree-disagree + free-text notes. Report agreement (e.g.
     % agreement or a simple kappa) in `reports/explain/expert_validation.md`.
- **Prep/decide (start EARLY — recruiting takes time):** identify the rater(s) now; prepare a 1-page
  rating form; keep it de-identified and low-burden.
- **Parallel agents:** Exp (cards) + human (runs the rating study).
- **Deliverable:** `reports/explain/` worked examples **+ `expert_validation.md`** with rater results.
- **Gate:** ≥5 sensible qualitative examples **and** ≥1 external rater's agreement scores reported.
  (If no rater can be found in time, downgrade to a documented self-audit + name it a limitation —
  but try hard to get at least one expert.)

### Phase 18 — Evaluation harness & ablations *(parallelized)*
- **Objective:** The numbers that go in the paper.
- **Tasks:** Eval Agent runs per-construct P/R/F1, macro/micro F1, calibration, human-agreement,
  and ablations (baseline vs transformer; ±silver data; ±risk fusion). Error analysis.
- **Parallel agents:** Eval ×N (one ablation per worker).
- **Deliverable:** `reports/results.md` + all paper figures/tables.
- **Gate:** Every claim the paper will make is backed by a logged experiment.

### Phase 19 — Results aggregation & narrative
- **Objective:** Decide the story the data tells.
- **Tasks:** Consolidate metrics; identify the 2–3 headline findings; note negative results honestly.
- **Parallel agents:** Eval, Pap.
- **Deliverable:** `docs/findings.md`.
- **Gate:** A clear, evidence-backed contribution statement.

---

## WEEK 6 — System, Security & Reproducibility

### Phase 20 — Dashboard / visualization
- **Objective:** A demo that communicates the system.
- **Tasks:** Streamlit app: paste text → construct bars + risk gauge + highlighted spans;
  Dockerized. This becomes a paper figure and a demo.
- **Parallel agents:** —
- **Deliverable:** `dashboard/` app + screenshots.
- **Gate:** App runs in Docker and reproduces a known example.

### Phase 21 — Security scan, dependency & PII audit
- **Objective:** Ship something safe and clean.
- **Tasks:** Sec Agent runs the security-scan workflow on the repo/`.claude` config; scans for
  committed secrets; dependency vulnerability check; final PII sweep of released data.
- **Parallel agents:** Sec.
- **Deliverable:** `docs/security.md` (findings + fixes).
- **Gate:** No secrets in git history; no high-severity dep issues; released data PII-clean.

### Phase 22 — Reproducibility packaging
- **Objective:** A reviewer can rerun it.
- **Tasks:** Pin versions; fix all seeds; finalize Docker; write run scripts; complete model card;
  prepare an anonymized artifact for release.
- **Parallel agents:** Mod, Sec.
- **Deliverable:** One-command reproduction path + artifact.
- **Gate:** Fresh clone reproduces headline numbers within tolerance.

---

## WEEK 7 — Paper

### Phase 23 — IEEE draft assembly *(parallelized by section)*
- **Objective:** Full first draft.
- **Tasks:** Pap Agent drafts sections from artifacts — abstract, intro, related work, method,
  dataset, experiments, results, ablation, ethics & limitations, conclusion. Different sections
  drafted in parallel, human-edited.
- **Parallel agents:** Pap ×N (one section per worker), Lit (citations).
- **Deliverable:** `paper/main.tex` compiling in the IEEE template.
- **Gate:** Compiles two-column; every section present; every figure/table referenced.

### Phase 24 — Figures, tables & polish
- **Objective:** Camera-quality presentation.
- **Tasks:** Finalize figures (pipeline diagram, results, calibration, explainability card);
  clean tables; check citation formatting; page-limit fit.
- **Parallel agents:** Eval, Pap.
- **Deliverable:** Polished, page-limit-compliant draft.
- **Gate:** Within page limit; figures legible in grayscale.

### Phase 25 — Internal review, red-team & submission prep
- **Objective:** Reviewer-proof it before submitting.
- **Tasks:** Devil's-advocate review (a critique agent + a human) against likely reviewer
  objections; fix novelty/rigor/ethics gaps; proofread; prepare submission package for
  iTriply Explore / IEEE by the 1st week of September.
- **Parallel agents:** Lit, Sec, Pap.
- **Deliverable:** Submission-ready paper + artifact link.
- **Gate:** Addresses the top predictable reviewer objections; passes a plagiarism/formatting check.

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

## Risk Register (top 5)

1. **Data scarcity/licensing** (highest risk) — mitigate via synthetic augmentation + a small
   high-quality gold set; decided in Q3 / Phase 6–7.
2. **Weak labels too noisy** — mitigate with confidence thresholds, human gold anchor, Phase 12 refinement.
3. **Scope creep** — mitigate by parking stretch goals (see expansion list) until core is done.
4. **Expert-rater access** (new — Phase 17) — the expert-validation contribution needs ≥1 coach or
   sport-psych practitioner. **Start recruiting in Week 1–2**, not Week 5. Fallback: documented
   self-audit named as a limitation.
5. **Annotation burden from expanded taxonomy** — resilience + appraisal + interpretation modifier
   raise labeling load; mitigate by freezing the final set at Phase 12 after an agreement check, and
   dropping any construct with poor inter-annotator agreement.
```
