# Handover — Phase 3 → Phase 4

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Handover written:** 2026-08-08
**Next phase:** Phase 4 — Construct Taxonomy Design
**Do not start Phase 4 until Saikalyan confirms receipt of this file.**

---

## Part A — Project summary & status

### What the project is

Construct-grounded NLP that detects **validated sports-psychology constructs** in an athlete's
pre-competition text (interviews, press conferences, social posts, journals) and fuses them into
an interpretable **0–1 risk index** with span-level explanations.

It is explicitly **not** sentiment analysis and **not** clinical diagnosis. Constructs currently
in scope: cognitive anxiety, somatic anxiety, self-confidence, motivation orientation, perceived
stress, attentional focus, burnout signal, coping style, resilience, appraisal orientation, plus
a facilitative/debilitative **interpretation-direction modifier** on the two anxiety constructs.

**Three-part contribution:** (1) a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement; (2) two-level, **expert-validated**
interpretability (span→construct, construct→risk) — the headline differentiator; (3) a
time-aware, fusion-ready design, with full temporal/multimodal modelling as Future Work.

- **Owner:** Saikalyan, sophomore, SRMIST. **Venue:** IEEE full paper (iTriply Explore).
- **Deadline:** code frozen ~Week 7; paper draft by the 1st week of September 2026.
- **Stack (locked):** Python 3.11, CrewAI, OpenRouter (cost-tier routing), HuggingFace
  transformers with DeBERTa/RoBERTa, scikit-learn baselines, SHAP, Streamlit, Docker, LaTeX.
- **Single source of truth:** `CLAUDE.md`. 25-phase blueprint: `PROJECT_PLAN.md`.

### Phase status

| Phase | Status |
|---|---|
| 1 — Repo reset & scaffold | ✅ Complete (`fb87925`). See `phase1_summary.md`. |
| 2 — Dev environment & tooling | ✅ Complete (`07d77ab`), **pending owner-machine verification**. See `phase2_summary.md`. |
| 3 — Related work & novelty | ✅ **Complete.** See `phase3_summary.md`. |
| 4 — Construct taxonomy design | ⬜ Next. |

### Two standing caveats carried forward

1. **No off-machine backup.** Phase 1 deliberately skipped the `legacy-backup` branch at the
   owner's instruction; the previous codebase was permanently deleted. Only `main` exists.
2. **Phase 2 environment is unverified on the owner's machine.** The venv / pip / pytest /
   Docker checks must be run on Windows via `.\scripts\verify_env.ps1`. **Ask whether this
   has been run and passed before relying on the environment.**

---

## Part B — What happened in the Phase 3 session

### Starting point

Phase 3 was already substantially complete from the owner's own 2026-08 evidence review.
`docs/related_work.md` already had a gap statement, five thematic sections, the three-part
contribution, and 14 references — but every reference pointed at a **Consensus secondary
record**, not a primary publisher entry, and `paper/refs.bib` did not exist.

### Work completed

1. Resolved **all 14** Consensus links to primary publisher records (web search + Crossref /
   publisher-page verification). Captured full author lists, exact titles, venues,
   volume/issue/pages, and DOIs.
2. Created **`paper/refs.bib`** — 19 BibTeX entries.
3. Rewrote the References section of **`docs/related_work.md`** as a four-column table
   (key / note / primary source / DOI); removed the "secondary citation records" caveat.
4. Added **5 method citations** the plan flagged as a thin spot.

### Key decisions made

- **Three citation keys ASCII-ised.** `Domínguez-González2024` → `Dominguez-Gonzalez2024`,
  `Biró2024` → `Biro2024`, `Tóth2025` → `Toth2025`. BibTeX keys must be ASCII or `\cite{}`
  breaks in LaTeX. All in-text mentions in `related_work.md` were updated to match.
- **Conference papers without DOIs are treated as resolved, not unresolved.** ICLR, ICML, and
  NeurIPS do not mint DOIs. He2021, Guo2017, and Lundberg2017 cite their arXiv / PMLR /
  NeurIPS proceedings pages via `url` + `note`. This is standard practice.
- **Method citations chosen:** Devlin2019 (BERT / transformer fine-tuning), He2021 (DeBERTa
  backbone), Guo2017 (temperature scaling — the calibration method for the risk index),
  Lundberg2017 (SHAP), Cohen1960 (kappa for inter-annotator agreement). Five additions, at
  the agreed ceiling.

### ⚠ One material correction

**`Toth2025` was mis-attributed by the secondary record.** Consensus credited "Tóth / Nuetzel";
those are the *handling editor* and a *reviewer* of the Frontiers article. The actual authors
are **Nogueira, Morais, Mansell & Gomes** (Front. Sports Act. Living 7:1636826, 2025,
doi:10.3389/fspor.2025.1636826). The key is retained for continuity, but the paper must cite
the real authors. Both files carry the correction and a visible flag.

This is the class of error that gets a paper desk-rejected, and it is the concrete justification
for having done the primary-source resolution rather than trusting the aggregator.

### Files created / modified

| File | Change |
|---|---|
| `paper/refs.bib` | **New.** 19 entries, keys identical to `related_work.md`. |
| `docs/related_work.md` | References section rewritten; keys ASCII-ised; caveat removed; method-reference table and a "still thin" list added. |
| `phase3_summary.md` | **New.** |
| `phase4_handover.md` | **New** (this file). |

### Verification performed

- `bibtexparser` parses `paper/refs.bib` cleanly → 19 entries, 0 duplicate keys.
- Key-set diff between `refs.bib` and `docs/related_work.md` is **empty in both directions**.
- Only the 3 conference papers lack a `doi` field, as expected and documented.
- **Unresolved citations: 0.**

### Blockers / open items

- ⚠ **`config/taxonomy.yaml` line 88 still says `(Tóth2025)`.** It was deliberately not
  touched — taxonomy is Phase 4's file. **Phase 4 must update it to `Toth2025` and, better,
  to the correct authors.** Same check applies to any other citation string in that file.
- Phase 2's `verify_env.ps1` has not been confirmed as run on the owner's machine.
- `docs/annotation_guidelines.md` exists but its current contents were not reviewed this
  session — Phase 4 must read it before rewriting.

---

## Part C — Handoff prompt for Phase 4

> Copy everything below into a fresh session.

---

You are continuing a multi-phase research-engineering project. Read `CLAUDE.md` (the standing
brief and single source of truth) and `PROJECT_PLAN.md` (the 25-phase blueprint) in the
connected folder `C:\Users\saika\sports-risk-nlp` before doing any work. Also read
`phase3_summary.md` and `docs/related_work.md`.

**Your job this session is Phase 4 only. Do not start Phase 5.**

### Context — where the project stands

**Project:** *Pre-Competition Psychological Risk Profiling of Athletes.* Construct-grounded NLP
that detects validated sports-psychology constructs in an athlete's pre-competition text and
fuses them into an interpretable 0–1 risk index with span-level explanations. NOT sentiment
analysis; NOT clinical diagnosis. Owner: Saikalyan, sophomore at SRMIST. Target: IEEE full
paper (iTriply Explore), draft by the 1st week of September 2026.

Confirmed stack: Python 3.11, CrewAI, OpenRouter (cost-tier routing), DeBERTa/RoBERTa via
HuggingFace, scikit-learn baselines, SHAP, Streamlit, Docker, LaTeX.

**Phase 1 (repo reset & scaffold) — complete** (`fb87925`). One documented, owner-authorised
deviation: no `legacy-backup` branch; the previous codebase was permanently deleted at the
owner's instruction. Only `main` exists and there is no off-machine backup.

**Phase 2 (dev environment & tooling) — complete, pending owner-machine verification**
(`07d77ab`). Delivered `.pre-commit-config.yaml` (ruff + ruff-format + detect-secrets),
`.secrets.baseline`, hardened ruff config, `scripts/hello.py`, `tests/test_smoke.py`,
`.dockerignore`, `scripts/verify_env.ps1`, `docs/setup.md`. **Ask whether
`.\scripts\verify_env.ps1` has been run and passed before relying on the environment.**

**Phase 3 (related work & novelty) — complete.** `docs/related_work.md` holds the gap
statement, five thematic sections, the three-part contribution, and a References table where
all 14 domain sources are resolved to primary publisher records with DOIs, plus 5 method
references. `paper/refs.bib` exists with 19 entries whose keys match the doc exactly. Zero
unresolved citations. Three keys were ASCII-ised: `Dominguez-Gonzalez2024`, `Biro2024`,
`Toth2025`. **`Toth2025` was mis-attributed by the original secondary source — the real
authors are Nogueira, Morais, Mansell & Gomes, not Tóth/Nuetzel.**

### Phase 4 — objective, tasks, acceptance gate

**Objective (from `PROJECT_PLAN.md`):** Lock the construct taxonomy — the academic backbone of
the whole project. Every downstream phase (labelling, modelling, risk fusion, explainability,
the paper's dataset section) depends on this being defensible.

**Tasks:**

1. **Review and lock `config/taxonomy.yaml`.** It already contains 10 constructs plus an
   `interpretation_modifier`. Confirm each has: a clear definition, a real
   **instrument citation anchor**, ≥2 positive examples, ≥2 negative examples, an edge-case
   note, a label type (presence + intensity, or a categorical label set), and — where
   applicable — a `risk_direction`. Several constructs are currently thin: `perceived_stress`,
   `attentional_focus`, `burnout_signal`, `motivation_orientation`, and `coping_style` have no
   examples at all.
2. **Fix the stale citation string.** Line ~88 of `config/taxonomy.yaml` reads `(Tóth2025)`.
   Update it to the ASCII key `Toth2025` and correct the attribution.
3. **Ground every `instrument_anchor` in a real, citable instrument.** Right now several are
   descriptive placeholders (e.g. "Perceived Stress framing (sport context)", "Attentional
   control in sport"). Each anchor must point to a specific published instrument or an
   established theoretical source. **CSAI-2 and the ABQ are not yet in `paper/refs.bib` — add
   them**, resolved to primary records with DOIs, using the same rigour as Phase 3. Candidates
   to resolve: Martens et al. (CSAI-2), Raedeke & Smith (ABQ), Cohen et al. (Perceived Stress
   Scale), Elliot & McGregor or Deci & Ryan (achievement goals / SDT), Nicholls (coping in
   sport), and a challenge/threat appraisal source. **Do not invent a citation.** If one cannot
   be resolved to a primary record, mark it `[UNRESOLVED]` with evidence of the attempt.
4. **Write `docs/annotation_guidelines.md`.** Read the existing file first. It must give a human
   annotator everything needed to label consistently: the construct list with definitions and
   citation anchors, the intensity rubric (0–3) with concrete anchors per level, span-selection
   rules (what counts as a span, overlapping spans, multi-label spans), the
   facilitative/debilitative interpretation modifier, decision rules for ambiguous cases, worked
   examples, and an explicit "when in doubt, label 0" default. This document is what makes the
   inter-annotator agreement number defensible in the paper.
5. **Do not touch** any `data/` directory, or `src/`, this phase.

**Acceptance gate — Phase 4 counts as done when:**

- Every construct in `config/taxonomy.yaml` has a definition, a citation anchor, and **≥2
  examples**.
- Every `instrument_anchor` resolves to a real citable source, present in `paper/refs.bib` with
  a DOI (or explicitly marked `[UNRESOLVED]`).
- `docs/annotation_guidelines.md` is complete enough that a second annotator could label a
  batch without asking questions.
- `config/taxonomy.yaml` is valid YAML (verify by loading it).
- Citation keys remain consistent across `taxonomy.yaml`, `related_work.md`, and `refs.bib`.

### How to work

- **Ask before assuming.** If anything is ambiguous — whether to add or drop a construct,
  whether an instrument anchor is good enough, how granular the intensity rubric should be —
  stop and ask the owner rather than guessing. **Adding or removing a construct is an
  owner decision, not yours.** Note that the construct set is formally frozen at Phase 12, so
  Phase 4 should aim to *complete and ground* the current set, not expand it.
- **Teach while doing.** The owner is a sophomore; explain why before how, define jargon once.
- **Be concise and direct in chat**; put depth in the files.
- Small, verifiable steps, and end with a verification step (load the YAML, confirm each
  construct meets the gate, confirm citation keys are consistent across all three files).
- **Ethics framing is mandatory and must survive into the paper:** research/decision-support
  only, de-identified data, no mental-health claims about real named individuals. The
  annotation guidelines must state that annotators are labelling *language*, not diagnosing
  people.
- **Never commit secrets.** Pre-commit hooks are active; run `pre-commit run --all-files`
  before committing if the owner has installed them.
- Commit the work with a clear message and leave the working tree clean.

### Deliverable format

- `config/taxonomy.yaml` — completed and locked; valid YAML.
- `docs/annotation_guidelines.md` — complete annotator-facing rubric.
- `paper/refs.bib` — extended with the instrument citations, DOIs included.
- A concise chat summary: what was locked, what changed, what remains open.
- Then produce a Phase 5 handover file (`phase5_handover.md`) covering **Phase 5 — Data
  acquisition & ingestion** per `PROJECT_PLAN.md`. Structure it as: Part A project summary &
  status, Part B this-session summary (decisions, files changed, blockers), Part C the
  self-contained handoff prompt.
- **Do NOT start Phase 5 work until the owner confirms receipt of that handover file.**
