# Handover — Phase 5: Ethics, Data Governance & Risk Plan

Self-contained. A new AI session can start from this file plus the repo; no chat history needed.

---

## PART A — Project Summary

**Project:** Pre-Competition Psychological Risk Profiling of Athletes.
Construct-grounded NLP that detects validated sports-psychology constructs in an athlete's
pre-competition text (interviews, press conferences, social posts, journals) and fuses them
into an interpretable 0–1 risk index with span-level explanations.

**Explicitly NOT** sentiment analysis and **NOT** clinical diagnosis. Research and
decision-support only.

**Owner:** Saikalyan, sophomore, SRMIST.
**Target:** IEEE full paper (iTriply Explore); draft by the 1st week of September 2026.
**Timeline:** 8 weeks; code frozen ~Week 7.

**Confirmed stack:** Python 3.11 · CrewAI · OpenRouter (cost-tier routing) · HuggingFace
transformers with DeBERTa/RoBERTa · scikit-learn baselines · SHAP · Streamlit · Docker · LaTeX.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, expert-validated
interpretability; (3) a time-aware, fusion-ready design.

**Governing documents:** `CLAUDE.md` (single source of truth) and `PROJECT_PLAN.md`
(25-phase blueprint). Read both before working.

### Phase status

| Phase | Status | Commit |
|---|---|---|
| 1 — Repo reset & scaffold | Complete | `fb87925` |
| 2 — Dev environment & tooling | Complete, **pending owner-machine verification** | `07d77ab` |
| 3 — Related work & novelty | Complete | `b104b8d` |
| **4 — Construct taxonomy** | **Complete (this session)** | **`d238721`** |
| 5 — Ethics, data governance & risk plan | **NEXT** | — |

**Carried-forward caveats:**

- **Phase 1 deviation:** no `legacy-backup` branch was created — the previous codebase was
  permanently deleted at the owner's instruction. Only `main` exists; there is no off-machine
  backup.
- **Phase 2:** ask the owner whether `.\scripts\verify_env.ps1` has been run and passed on
  Windows before relying on the environment. Still unconfirmed.
- **Phase 3:** the key `Toth2025` is historical. László Tóth was the **handling editor**, not an
  author. Correct authors: Nogueira, Morais, Mansell & Gomes. The key is retained for stability;
  cite the correct authors in prose.

---

## PART B — Current Session Summary (Phase 4)

### Objective

Lock the construct taxonomy — the academic backbone every downstream phase depends on.

### What was accomplished

**1. `config/taxonomy.yaml` — rewritten and locked (v1 → v2).**

All 10 constructs now carry a complete, uniform record: `definition`, `label_type`,
`instrument_anchor`, `risk_direction`, ≥2 positive examples, ≥2 negative examples, and an
`edge_cases` note. Five constructs previously had **no examples at all**
(`perceived_stress`, `attentional_focus`, `burnout_signal`, `motivation_orientation`,
`coping_style`); all are now fully populated.

New structural additions:

- Explicit `label_type` on every construct: `graded` (presence + intensity 0–3) or
  `categorical` (one label from a set + intensity).
- `risk_direction` on every construct, including the ones that previously lacked it.
- Definitions sharpened at the confusable boundaries — `perceived_stress` vs.
  `cognitive_anxiety` (demand-vs-resource against outcome-worry), and `resilience` vs.
  `self_confidence` (recovery-if-wrong against expected-success).
- An ethics note at the top of the file: these constructs describe **language, not people**.
- `interpretation_modifier` given its own anchor, examples, edge cases, and a
  `default: unclear`.

**2. Stale citation strings fixed.**
`(Tóth2025)` on the old line ~88 → ASCII `Toth2025`, with attribution corrected. A file-wide
sweep confirms **zero** remaining non-ASCII citation strings in `taxonomy.yaml`.

**3. `paper/refs.bib` — extended from 19 to 30 entries (new Section E).**
Every `instrument_anchor` that was previously a descriptive placeholder is now grounded in a
real, citable instrument or theoretical source, each resolved to a primary publisher record:

| Key | Source | DOI | Anchors |
|---|---|---|---|
| `Martens1990` | CSAI-2 original (Human Kinetics book chapter) | **none — pre-DOI**; paired with `Cox2003` | cognitive/somatic anxiety, self-confidence |
| `Cox2003` | CSAI-2R revision, *JSEP* 25(4) | `10.1123/jsep.25.4.519` | same, + directional tradition |
| `Jones1992` | Intensity/direction dimensions, *Percept Mot Skills* | `10.2466/pms.1992.74.2.467` | interpretation_modifier |
| `Raedeke2001` | Athlete Burnout Questionnaire, *JSEP* 23(4) | `10.1123/jsep.23.4.281` | burnout_signal |
| `Cohen1983` | Perceived Stress Scale, *J Health Soc Behav* | `10.2307/2136404` | perceived_stress |
| `Elliot2001` | 2×2 achievement-goal framework, *JPSP* | `10.1037/0022-3514.80.3.501` | motivation_orientation |
| `Deci2000` | Self-Determination Theory, *Psych Inquiry* | `10.1207/S15327965PLI1104_01` | motivation_orientation |
| `Nicholls2007` | Coping in sport systematic review, *J Sports Sci* | `10.1080/02640410600630654` | coping_style |
| `JonesMeijen2009` | TCTSA challenge/threat, *IRSEP* | `10.1080/17509840902829331` | appraisal_orientation |
| `Nideffer1976` | TAIS attentional style, *JPSP* | `10.1037/0022-3514.34.3.394` | attentional_focus |
| `Connor2003` | CD-RISC resilience scale, *Depress Anxiety* | `10.1002/da.10113` | resilience |

**Zero `[UNRESOLVED]` markers. Zero fabricated citations.** The one entry without a DOI
(`Martens1990`) genuinely predates DOI assignment — it is a 1990 Human Kinetics book chapter —
and this is stated in a `note` field and paired with `Cox2003`, which does have a DOI and is the
version current practice recommends.

*Author-order correction made during verification:* the TCTSA paper is Jones, Meijen,
**McCarthy, Sheffield** — not Meijen, Sheffield, McCarthy as commonly miscited.

**4. `docs/annotation_guidelines.md` — written from a 5-line stub to a complete rubric.**

Sections: (0) ethics framing — you are labelling language, not diagnosing people; (1) unit of
annotation, span-selection rules table, overlapping and multi-label span rules; (2) the label
model — graded vs. categorical, the 0–3 intensity anchor table with calibration tips
(hedges pull down, intensifiers pull up, take the strongest not the average), the
interpretation modifier, and the `low_resilience_explicit` flag; (3) an 8-step decision
procedure; (4) five **discriminating questions** for the confusable construct pairs that cause
most annotator disagreement; (5) four fully worked examples with span-level label tables and
rationale; (6) the **when-in-doubt-label-0** rule with its asymmetric-risk justification;
(7) uncertainty, escalation, and adjudication protocol including the rule that annotators must
not discuss records before both passes complete; (8) a pre-submission checklist; (9) a
construct quick-reference table; (10) a change log.

**5. Constraint respected:** no file under `data/` or `src/` was touched.

### Verification performed

A script loaded the YAML and checked every gate condition mechanically:

- `config/taxonomy.yaml` parses as valid YAML — v2, 10 constructs.
- Every construct passes: definition ✓, instrument_anchor ✓, ≥2 examples ✓, edge_cases ✓,
  label_type ✓, risk_direction ✓, and `labels` present on all categorical constructs. **Gate: PASS.**
- Citation-key consistency, checked in both directions: 14 keys cited in `taxonomy.yaml`,
  14 in `annotation_guidelines.md`, all bracketed keys in `related_work.md` — **all resolve to
  entries in `refs.bib`; zero missing.** `refs.bib` now holds 30 entries.
- Zero remaining `Tóth2025` occurrences.

### Key decisions made this session

1. **CSAI-2 anchored as a pair** (`Martens1990` + `Cox2003`) rather than forcing a single
   citation, because the original has no DOI and the revision is what reviewers expect.
2. **`resilience` fragility handled with a boolean flag**, not a negative score. "One mistake
   and I'm done" is `resilience = 0` **plus** `low_resilience_explicit: true`. Explicit
   fragility and mere silence are different signals and Phase 15's risk model needs to
   distinguish them.
3. **`mixed` is not "undecided."** It requires an independent span for each pole. Undecided
   resolves to `none`. This directly protects the inter-annotator agreement statistic.
4. **Intensity anchors are linguistic, not inferential** — graded on hedges, intensifiers, and
   repetition rather than on the annotator's estimate of the athlete's true internal state.
   This is what makes the rubric reproducible by a second annotator.
5. **Two constructs given sharper boundaries** to reduce predictable annotator confusion
   (stress/anxiety and resilience/confidence), and the five confusable pairs written up
   explicitly in Section 4.

### Blockers and unresolved issues

> **`docs/open_issues.md` is the single source of truth for open items.** It is deliberately
> not duplicated here. As of 2026-08-08 it carries **OPEN-001** (Docker daemon down — deferred
> by owner, **hard gate on Phase 6**), **OPEN-002** (broken plugin hook), **OPEN-003** (no
> off-machine backup), **OPEN-004** (expert-rater recruitment not started), **OPEN-005**
> (ethics exemption not yet in writing — blocks submission), **OPEN-006** (contact route is a
> personal address — blocks release). Read it before planning any phase.

- **Stale git lock files — RESOLVED 2026-08-08.** `.git/HEAD.lock`, `.git/index.lock`, and
  `.git/objects/maintenance.lock` were deleted on the owner machine; commits work again.
- **`pre-commit` — RESOLVED.** Could not run in the sandbox, but `verify_env.ps1` check 9 ran
  the full hook set on Windows: trailing whitespace, end-of-files, check-yaml, merge-conflict,
  large-files, detect-private-key, ruff, ruff-format, detect-secrets — all **Passed**. Check 10
  confirms `.env` is untracked.
- **Phase 2 verification — 8/10 pass.** Only Docker checks 7 and 8 fail; see OPEN-001. The
  Python environment is verified and safe to rely on.
- **Open for Phase 12:** the construct set is locked but not frozen. `burnout_signal` and
  `attentional_focus` are the most likely candidates to show weak inter-annotator agreement.
- **Not started, but should be:** `PROJECT_PLAN.md` risk #4 says expert-rater recruitment for
  the Phase 17 validation study should begin in Week 1–2. It has not begun. This is the
  headline contribution of the paper and it is the item most at risk of running out of runway.

---

## PART C — Phase 5 Brief

> **Note:** the incoming request for this session referred to Phase 5 as "Government
> Validation." That does not match the blueprint. `PROJECT_PLAN.md` defines Phase 5 as
> **Ethics, data governance & risk plan**, which is what this handover covers. Confirm with the
> owner if a scope change was intended.

**Objective (from `PROJECT_PLAN.md`):** Set the guardrails before touching any data.

**Owning agent:** Security/Ethics Agent (mid tier).

**Tasks:**

1. Draft `docs/ethics.md` covering:
   - consent and licensing rules for source text;
   - the de-identification policy that `src/preprocessing/deidentify.py` will implement in
     Phase 8 (names, handles, locations, club/team identifiers, dates that enable re-identification);
   - the **non-diagnosis framing** — the paper must be able to cite this section directly;
   - misuse risks (selection decisions, contract decisions, media use), bias risks (sport,
     gender, language, and cultural variation in emotional expression), and stigmatisation risk
     from a "risk score" label attached to an individual;
   - what the system must never be used for.
2. Define a **data-source allow-list**: which categories of text are permitted
   (public/consented/synthetic/anonymised) and which are explicitly forbidden. Phase 7
   ingestion must respect this list.

**Deliverable:** `docs/ethics.md` + a data-source allow-list.

**Gate:** A written de-identification and non-diagnosis policy that the paper can cite.

**Inputs to read first:** `CLAUDE.md` §1 (ethics guardrails) and §8 rule 5;
`PROJECT_PLAN.md` Phase 5 and Phase 7–8; `docs/related_work.md` (the XAI-validation gap);
`docs/annotation_guidelines.md` §0 (the language-not-people framing, which `docs/ethics.md`
should extend rather than restate); `config/taxonomy.yaml` (the ethics note at the top).

**Constraints:**

- Do **not** touch `data/` or `src/` in Phase 5 either — this phase is policy, not code.
- Confirmed in Phase 3/§10 of `CLAUDE.md`: data strategy is **existing public/licensed datasets
  first**, with a hybrid synthetic-plus-small-real-gold-set fallback revisited at Phase 7. The
  allow-list must be consistent with that.
- Ask the owner before locking any policy that constrains later data acquisition — an
  over-tight allow-list written now becomes a Phase 7 blocker.

**Do not start Phase 6.**

---

## Files changed this session

| File | Change |
|---|---|
| `config/taxonomy.yaml` | Rewritten, v1 → v2, locked |
| `docs/annotation_guidelines.md` | Stub → complete rubric (v1.0) |
| `paper/refs.bib` | +11 entries (19 → 30), new Section E |
| `phase5_handover.md` | This file |

**Commit:** `d238721` — *Phase 4: lock construct taxonomy and annotation rubric*
**Working tree:** clean.
