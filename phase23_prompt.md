You are continuing an ongoing IEEE conference paper project as a Claude Cowork session. The repository is at `C:\Users\saika\sports-risk-nlp` and is connected to this session as a folder. Read `CLAUDE.md` first - it overrides defaults - then `handover_phase_22.txt` **including its addendum**, `docs/findings.md`, `docs/reproducibility.md`, `docs/security.md`, `docs/ethics.md`, `docs/model_card.md` and `PROJECT_PLAN.md`. Everything below is a summary so you know what you're walking into; the files are the source of truth.

## The project

Pre-Competition Psychological Risk Profiling of Athletes. NLP × sports psychology: detect 10 validated constructs (CSAI-2 / SDT / ABQ tradition) in athlete text and fuse them into an interpretable risk index with two-level explanations (span→construct, construct→risk). Owner: Saikalyan, sophomore at SRMIST. Paper draft due first week of September 2026, Python 3.11.

Phases 1–15 and 17–22 are complete. Phase 16 (DataRobot AutoML) was skipped by decision. Your job is **Phase 23 - IEEE draft assembly**.

## The constraint that governs everything - carry it forward verbatim

`data/gold/` is empty. **No number in this repository is an accuracy.** Every result is a corpus property of a synthetic template grammar (`synth_precomp_v1`, 4,000 generated records, labels planted by the generator). Never report a figure as accuracy. Never write to `data/gold/`. Never weaken the `--gold` refusal in `src/models/dataset.py`. An attribution is a claim about the model, not about athlete psychology.

**Phase 23 is the phase where this constraint is most likely to break**, because prose is where a hedge quietly becomes a claim. "The model achieves 0.588" is already wrong: it achieves 0.588 agreement with generator-planted labels on a template-disjoint split of a synthetic corpus. Write the long form. Every time.

Six corollaries accumulated from earlier phases, all binding:

- **Phase 18:** a gate that only checks a result *exists* is worse than no gate, because it launders the claim.
- **Phase 19:** the claim ledger is upstream of the prose. Any headline sentence not traceable to a row in `src/evaluation/ablations.py::CLAIMS` requires a new `Claim`, added and passing the gate, *before* it is written anywhere. **This corollary is the whole of Phase 23's discipline.**
- **Phase 20:** a property the unit tests can see is not the whole property. Two defects passed every test and were caught only by rendering the page and looking at it.
- **Phase 21:** a detector that fires on everything is exactly as uninformative as one that fires on nothing. A gate needs both a proven floor and a legible ceiling.
- **Phase 22:** a test that builds its own fixture proves the parser and proves nothing about the artefact that ships. Three defects were found by running the artefact; zero by the suite.
- **Running through all six:** the check and the thing it protects keep turning out to be related by *assumption* rather than by *construction*. That is the defect shape this project has now found six times. Assume it is present in your phase too.

## Where the numbers stand (real checkpoint, 2026-08-16)

Transformer macro-F1 **0.588** [0.546, 0.622] template-disjoint vs a lexicon floor of **0.462** [0.431, 0.492], delta +0.126 at p=0.000 paired bootstrap. The headline result is the memorisation gap: TF-IDF+LogReg scores 0.999 random-split and 0.222 template-disjoint (+0.777); the transformer's own gap is +0.234; the lexicon control moves only +0.100. Explanations beat a random-span control by +0.328 comprehensiveness with all ten constructs beating control individually - but 104 of 120 driver rows (86.7%) have no supporting span, published rather than hidden. Three negative results are reported as results: silver supervision bought nothing (+0.033, p=0.107), the risk index cannot be calibrated because no observed outcome exists, and four of ten constructs are inert in the fusion layer.

These live in `reports/results.json` and are pinned as rows in `src/evaluation/ablations.py::CLAIMS` (now **8** rows - Phase 22 added the reproduction tolerance).

## What Phase 22 delivered (do not rebuild it)

`src/reproducibility/` - four pure-Python modules with no ML imports: `environment.py`, `manifest.py`, `plan.py`, `verify.py`. Plus `scripts/run_reproduction.py` (the runner that owns shelling out, the network and disk), `docs/reproducibility.md`, `ARTIFACT.md`, per-layer locks (`requirements-base.lock.txt`, `requirements-ml.lock.txt`), and a completed `docs/model_card.md`.

The reproduction path is **tiered and the tiers are declared**, because a one-command path that quietly skips the expensive arm claims more than it delivers:

- **Tier A** - byte-identical, seeded: the corpus at seed 42, the classical baselines (Phase 13 asserts full float precision, not `approx`).
- **Tier B** - within a declared numeric tolerance: the evaluation harness outputs.
- **Tier C** - NOT reproduced, and the artefact says so: gold-derived figures (impossible, `data/gold/` is empty, OPEN-025) and the transformer arm (~10 CPU-hours).

Four things Phase 22 fixed that you should not undo:

- **SEC-07** - both images now install the lock, not a floor file. `ENV PYTHONPATH=/app` is in the Dockerfile and is load-bearing.
- **SEC-04 / OPEN-006 CLOSED** - the participant contact route is `sk8069@srmist.edu.in` (SRMIST) with **Dr. Shankar Ram** named as supervisor. It appears on all five reader-facing surfaces, enforced by tests. No personal webmail remains anywhere, including historical notes.
- **SEC-05** - the `C:\Users\<name>\...` path scrub.
- **DASH-01** - the dashboard had never once started in a container (`streamlit run` never puts the repo root on `sys.path`; `tests/__init__.py` made pytest insert it, so pytest and the runtime disagreed and 23 green tests could not see it). Fixed with a `sys.path` bootstrap plus `PYTHONPATH`, pinned by a test that reproduces the runtime's `sys.path` in a subprocess.

## Phase 23 - what you are building

**Objective:** a full first draft.
**Tasks:** draft abstract, intro, related work, method, dataset, experiments, results, ablation, ethics & limitations, conclusion from the artifacts. Resolve every Consensus link in `docs/related_work.md` to a primary DOI and populate `paper/refs.bib` (deferred from Phase 3).
**Deliverable:** `paper/main.tex` compiling in the IEEE two-column template.
**Gate as originally written:** compiles two-column; every section present; every figure/table referenced.

### Strengthen the gate before you start - that gate is the weakest in the plan

"Compiles, every section present, every figure referenced" is satisfied by a document full of true-looking sentences backed by nothing. It checks *structure* and the project's entire risk is in *content*. Same relationship-by-assumption as all six previous instances: the check ("it compiles and has ten sections") and the property ("every sentence is defensible") share no mechanism at all.

Predicted defect, named in advance so you can look for it specifically:

> **A sentence will enter the draft that no `CLAIMS` row backs, and it will survive because it is true-adjacent and reads well.** The most likely offenders are comparative and causal connectives that no experiment tested - "because the transformer captures context", "which suggests the constructs are separable", "outperforms", "demonstrates that" - and the quiet drift from "agreement with planted labels" to "detects constructs". LaTeX has no opinion about any of them, and neither does a compiler check.

Add these to the gate and write the answers down:

- **A traceability screen over the compiled prose, not over the source tree.** Extract the sentences from `main.tex` and require every sentence carrying a number to name the `CLAIMS` row or the `reports/` artefact it comes from. A number with no provenance is the finding. Build it as tested pure Python under `src/` with a thin runner in `scripts/` - `src/security/audit.py::ScannerResult` (a findings table is unconstructable without a non-empty `does_not_cover` sentence) and `src/security/sweep.py` (a scanner that has not just fired on a canary **refuses to report**) are the two templates; copy both, and make your screen prove itself on a planted bad sentence before it is allowed to report a clean draft.
- **Run `assert_no_forbidden_language` over the rendered PDF text, not the `.tex`.** A forbidden phrase produced by a macro, a bibliography entry or a figure caption does not appear in the source you screened. Phase 20's lesson is exactly this and it cost two defects.
- **Every number in the paper must round-trip to `reports/results.json`.** Not "was copied from" - re-read the JSON at gate time and compare. A hand-typed 0.588 that became 0.688 is invisible to a compiler and to a reader.
- **Count what the draft does NOT cover**, in the paper itself: no gold, no kappa, no real athlete text, no practitioner validation, four inert constructs, the transformer arm unreproduced in Tier C.

## Hard constraints - non-negotiable

Display or commit no verbatim corpus text anywhere outside the synthetic A2 source: not in the paper, not in a figure, not in an appendix, not in a caption. `docs/ethics.md` binds this; `src/explainability/cards.py::assert_publication_safe` is the existing mechanism - use it rather than reimplementing it, and `src/security/audit.py::shape()` is how Phase 21 reported matched text without quoting it.

Label no number "accuracy", "confidence in the athlete", or anything implying a measurement of a person. The exact banned strings are in `src/dashboard/view.py::FORBIDDEN_SUBSTRINGS`; read them there. The literal denial "not accuracy" is the one permitted exception, because `PROVISIONAL_STAMP` contains it.

**Any phrase claiming the explanations were validated by experts, practitioners or coaches is forbidden everywhere** - paper, abstract, figures, captions, slides, artifact README. OPEN-004 was closed by *decision*, not by recruitment: the study shipped as a blinded pilot self-audit with sports-familiar student raters, practitioner validation named as a limitation. Where the paper references the study, use `src/dashboard/view.py::PILOT_STUDY_WORDING` verbatim.

Do not describe the risk decomposition as ten-construct without qualification - use `SIX_OF_TEN_WORDING` verbatim. Four constructs (`appraisal_orientation`, `attentional_focus`, `coping_style`, `motivation_orientation`) are inert under the conservative `PolarityPolicy.NEUTRAL` default.

The contribution statement is **locked** in `docs/findings.md` §0 and every clause maps to a `CLAIMS` row. The abstract is that paragraph compressed, not re-argued. If the paper needs a claim the statement does not make, add the `Claim`, pass the gate, then write the sentence - in that order, never the reverse.

Do not retrain, do not re-tune thresholds, do not regenerate the corpus. Do not weaken any guard to make the draft pass - if a guard fires, that is the finding.

## Architecture - follow the project's established shape

Anything checked repeatedly goes in tested pure Python under `src/`, with the runner in `scripts/` as a thin shell. This has paid for itself seven phases running (`src/risk/` 15, `src/explainability/` 17, `src/evaluation/` 18, `src/dashboard/` 20, `src/security/` 21, `src/reproducibility/` 22). The test suite must run with **no ML stack installed** - every phase since 15 has held this line.

The Phase 21/22 split is the template: `src/` is offline, filesystem-light and dependency-injected; the `scripts/` runner owns the three things a test must never do (shell out, touch the network, write to disk).

## What already exists - rebuild none of it

`src/reproducibility/` (22), `src/security/` (21), `src/dashboard/` (20), `src/explainability/cards.py`, `src/risk/fusion.py`, `src/models/`, `src/evaluation/harness.py` (`PROVISIONAL_STAMP`, `assert_not_accuracy`), `src/evaluation/ablations.py` (`CLAIMS`, 8 rows), `src/preprocessing/deidentify.py`, `src/ingestion/allowlist.py`, `reports/results.json`, `reports/explain/cards.md`, `reports/figures/`, `reports/dashboard/`, `docs/findings.md`, `docs/reproducibility.md`, `docs/security.md`, `docs/dashboard.md`, `docs/model_card.md` (**complete** - do not restart it), `docs/related_work.md` (14 refs, needs DOI resolution into `paper/refs.bib`), `ARTIFACT.md`, both Dockerfiles, both lock files, `.pre-commit-config.yaml`, `.secrets.baseline`.

## Two environment traps, both worth knowing before you lose an hour

**PowerShell's `>` writes UTF-16LE with a BOM.** Phase 22 lost time to exactly this: `docker compose run --rm app detect-secrets scan > .secrets.baseline` corrupts the file it regenerates, and `detect-secrets` dies on byte 0xff. Put the redirect **inside** the container: `docker compose run --rm app sh -c 'detect-secrets scan > .secrets.baseline'`. The same trap applies to any `>` you write in a documented command - and to LaTeX log capture.

**Through the folder bridge, `git status` prints a warning and returns no output** because it cannot write `index.lock`; an empty `git status` reads exactly like "clean tree" and is evidence of nothing. Run git queries against a copied index: `cp .git/index /tmp/gidx; export GIT_INDEX_FILE=/tmp/gidx`.

**Git must be run by the owner in PowerShell.** Give exact commands rather than running them, prefixed with `if (Test-Path .git\index.lock) { Remove-Item .git\index.lock }`. After any commit verify with `git log --oneline -1` **as its own command** - Phases 17 and 18 were both discovered uncommitted because a stale lock aborted a commit and the failure read as success. Check `ruff check` and `ruff format --check` on every `.py` you touch before handing over commands; `detect-private-key` honours no inline waiver.

## Skills to use

Read the relevant `SKILL.md` before building, not while building. At minimum consult **`engineering:documentation`** for the drafting itself, **`engineering:testing-strategy`** when designing the traceability screen above, **`fact-checker`** for the citation resolution pass, and **`engineering:code-review`** before you declare the phase done.

## Working rules

Teach while doing - the owner is a sophomore. Be concise in chat and put the depth in files. Work in small verifiable steps and end non-trivial work with a verification step; the argument for that rule is now three phases long - Phase 20 found three defects by rendering output and looking, Phase 21's canary caught a broken detector before it could report a clean scan, and Phase 22 found three more the same way and none by its tests. `pytest` excludes `-m slow` by default. Install ML dependencies with `pip install -r requirements-ml.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu`.

Produce a handover file at the end of the phase - `handover_phase_23.txt`, structured as Part A project summary, Part B session summary, Part C handoff for Phase 24 (figures, tables & polish) - self-contained enough that a fresh session can continue from it alone. Include a named prediction of the defect shape to expect in Phase 24, as every handover since 18 has done. Do not start Phase 24 until the owner confirms receipt.

## Open items, in priority order

- **OPEN-011** - no real athlete text. The project's highest live risk and its only unmitigated high-impact item. Contribution #1 must be stated as a *synthetic* construct-grounded corpus in the abstract, the intro and the dataset section, not only in limitations.
- **OPEN-025** - no second annotator, so no gold and no kappa. Blocks every accuracy claim and bounds what Tier C can ever reproduce.
- **OPEN-021** - the lexicon baseline is not independent of the corpus; the caveat travels with the 0.462 floor wherever it is quoted, including in the paper's baseline table.
- **OPEN-028** - silver is PRNG output; measured (+0.033, p=0.107) rather than asserted.
- **OPEN-005** - the ethics exemption determination is still not in writing. Needed before submission; it is a Phase 23/25 owner action, not a code task.
- **SEC-06** - `chromadb==1.1.1` carries an open advisory with no fixed release; transitive via `crewai`, never imported. Re-check at Phase 25; do not remove `crewai` for it.
- **Author identification** - `docs/open_issues.md` still contains the GitHub username `gsaikalyan2-coder` in two OPEN-003 changelog lines. SEC-05-class; scrub before any anonymised submission.
- **OPEN-030/031/032** - pre-submission items for Phases 24–25.

Begin by reading the files named at the top and telling me your plan for Phase 23 - including how you intend to structure the traceability screen so it stays testable without a LaTeX toolchain, which sections you will draft first and why, how you will resolve the 14 Consensus links to primary DOIs without fabricating a citation, and which sentences in the locked contribution statement you expect to need a new `Claim` row. Ask me anything genuinely ambiguous before you write code.

Think before answering (maximum reasoning)
