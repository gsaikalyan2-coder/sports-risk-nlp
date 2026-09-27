# Phase 3 Handover Prompt - Literature Review & Novelty Positioning (completion pass)

> Copy everything below the line into a fresh Claude Cowork chat opened on the folder
> `C:\Users\x\sports-risk-nlp`.

---

You are continuing a multi-phase research-engineering project. Read `CLAUDE.md` (the standing
brief and single source of truth) and `PROJECT_PLAN.md` (the 25-phase blueprint) in the connected
folder **before doing any work**. Your job this session is **Phase 3 only**.

## Context - where the project stands

**Project:** *Pre-Competition Psychological Risk Profiling of Athletes.* Construct-grounded NLP that
detects validated sports-psychology constructs (cognitive/somatic anxiety, self-confidence,
motivation orientation, perceived stress, attentional focus, burnout, coping style, resilience,
appraisal orientation) in an athlete's pre-competition text and fuses them into an interpretable
0–1 risk index with span-level explanations. **Not** sentiment analysis; **not** clinical diagnosis.
Owner: Saikalyan, sophomore at SRMIST. Target: IEEE full paper (iTriply Explore), draft by the 1st
week of September 2026. Confirmed stack: Python 3.11, CrewAI, OpenRouter (cost-tier routing),
DeBERTa/RoBERTa via HuggingFace, scikit-learn baselines, SHAP, Streamlit, Docker, LaTeX.

**Phase 1 (repo reset & scaffold) - complete.** See `phase1_summary.md`. Folder structure matches
`CLAUDE.md` §7; `config/{taxonomy,model_routing,settings}.yaml` seeded; committed at `fb87925`.
One documented, owner-authorised deviation: the plan's `legacy-backup` branch was **not** created -
the previous codebase was permanently deleted at the owner's instruction. Only `main` exists, and
there is **no off-machine backup**.

**Phase 2 (dev environment & tooling) - complete, pending owner-machine verification.** See
`phase2_summary.md`, commit `07d77ab`. Delivered: `.pre-commit-config.yaml` (ruff + ruff-format +
detect-secrets + hygiene hooks), `.secrets.baseline` (real scan, 0 findings), hardened ruff config
in `pyproject.toml`, `scripts/hello.py` environment self-check, real `tests/test_smoke.py`,
`.dockerignore`, `scripts/verify_env.ps1`, and `docs/setup.md`. The venv / pip / pytest / Docker
steps must be run by the owner on Windows via `.\scripts\verify_env.ps1` - **ask whether that has
been run and passed before you rely on the environment.**

**Phase 3 is already SUBSTANTIALLY COMPLETE** from the owner's own 2026-08 evidence review. Do not
redo it. `docs/related_work.md` already contains: a one-paragraph gap statement, five thematic
sections, the three-part contribution, and 14 references. That review also drove taxonomy expansion
(resilience; appraisal orientation challenge/threat; an interpretation-direction modifier on anxiety)
and the "time-aware, fusion-ready" framing now recorded in `CLAUDE.md` and `PROJECT_PLAN.md`.

## Phase 3 - objective, remaining tasks, acceptance criteria

**Objective (from `PROJECT_PLAN.md`):** Prove the idea is novel and find the gap.

**Already done (verify, do not repeat):** 14 sources synthesised into `docs/related_work.md`; two
validated gaps identified - (a) no work bridges *validated psychological constructs* to athlete
*text* with span-level, construct-specific labels (text studies stop at sentiment or broad mental
health); (b) sports XAI explanations are almost never validated with coaches or practitioners.
Three-part contribution written.

**Remaining tasks for this session:**

1. **Resolve every Consensus link in the `## References` table of `docs/related_work.md` to its
   primary source** - publisher page or DOI. The 14 keys are: Zhao2024, Floyd2021,
   Domínguez-González2024, Li2025, Madigan2020, Daumiller2021, Tóth2025, Park2023, Kranzinger2025,
   Jiacheng2025, Raju2026, Biró2024, Feng2025, Qin2025. Use web search/fetch. For each, capture:
   full author list, exact title, venue/journal, year, volume/issue/pages, and DOI.
2. **Create and populate `paper/refs.bib`** - one correct BibTeX entry per resolved source, keyed
   with the existing keys above so nothing in `docs/related_work.md` breaks.
3. **Update the References table in `docs/related_work.md`** to carry the DOI alongside (or in place
   of) the Consensus link, and remove the "secondary citation records" caveat note once resolved.
4. **If a source cannot be resolved to a primary record**, do **not** invent a citation. Mark it
   `[UNRESOLVED]` in both files with what you tried, and report it in your summary. A fabricated
   citation is a paper-killing error; an honest gap is not.
5. **Optionally** add 3–5 method citations the current review lacks - multi-label text
   classification, transformer fine-tuning, and calibration (e.g. temperature scaling) - since the
   plan flags these as a known thin spot. Add them to both files with the same rigour. Ask the owner
   before expanding scope beyond ~5 additions.
6. **Do not modify** `config/taxonomy.yaml` (that is Phase 4) or any data directory.

**Acceptance gate - Phase 3 counts as done when:**
- A clear written gap statement exists in `docs/related_work.md` (already satisfied - confirm it).
- ≥14 references are present (already satisfied - confirm it).
- **`paper/refs.bib` exists and every entry resolves to a primary source with a DOI**, or is
  explicitly marked `[UNRESOLVED]` with evidence of the attempt. ← the open item.
- `docs/related_work.md` and `paper/refs.bib` use identical citation keys.

## How to work

- **Ask before assuming.** If anything is ambiguous - scope of the optional method citations, what
  to do with an unresolvable source, whether to touch anything outside these two files - **stop and
  ask the owner rather than guessing.**
- **Teach while doing.** The owner is a sophomore; explain *why* before *how*, define jargon once.
- **Be concise and direct in chat**; put depth in the files.
- **Small, verifiable steps**, and end with a verification step (e.g. confirm every `\cite{key}`-able
  key in `refs.bib` matches the table, and that the BibTeX parses).
- **Never commit secrets.** Pre-commit hooks are active; run `pre-commit run --all-files` before
  committing if the owner has installed them.
- **Ethics framing is mandatory and must survive into the paper:** research/decision-support only,
  de-identified data, no mental-health claims about real named individuals.
- Commit the work with a clear message and leave the working tree clean.

## Deliverable format

- `paper/refs.bib` - valid BibTeX, one entry per source, keys matching `docs/related_work.md`.
  Prefer `@article` / `@inproceedings` with complete fields; include `doi = {...}`.
- `docs/related_work.md` - updated References table (DOI column), caveat note removed or narrowed.
- A concise chat summary: what resolved, what did not, and any citations you added.
- **Then produce a Phase 4 handover file** (`phase4_handover.md`) covering Phase 4 - *Construct
  taxonomy design*: lock `config/taxonomy.yaml` (including resilience, appraisal orientation, and the
  facilitative/debilitative interpretation-direction modifier) and write
  `docs/annotation_guidelines.md`; gate = every construct has a definition, a citation anchor, and
  ≥2 examples. Structure it as: Part A project summary & status, Part B this-session summary
  (decisions, files changed, blockers), Part C the self-contained handoff prompt.
- **Do not start Phase 4 work** until the owner confirms receipt of that handover file.
