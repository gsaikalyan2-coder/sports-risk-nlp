You are continuing an ongoing IEEE conference paper project as a Claude Cowork session. The repository is at `C:\Users\saika\sports-risk-nlp` and is connected to this session as a folder. Read `CLAUDE.md` first - it overrides defaults - then `handover_phase_21.txt`, `docs/security.md`, `docs/findings.md`, `docs/ethics.md`, and `PROJECT_PLAN.md`. Everything below is a summary so you know what you're walking into; the files are the source of truth.

## The project

Pre-Competition Psychological Risk Profiling of Athletes. NLP × sports psychology: detect 10 validated constructs (CSAI-2 / SDT / ABQ tradition) in athlete text and fuse them into an interpretable risk index with two-level explanations (span→construct, construct→risk). Owner: Saikalyan, sophomore at SRMIST. Paper draft due first week of September 2026, Python 3.11.

Phases 1–15 and 17–21 are complete. Phase 16 (DataRobot AutoML) was skipped by decision. Your job is **Phase 22 - reproducibility packaging**. Last commit: `aee3711`.

## The constraint that governs everything - carry it forward verbatim

`data/gold/` is empty. **No number in this repository is an accuracy.** Every result is a corpus property of a synthetic template grammar (`synth_precomp_v1`, 4,000 generated records, labels planted by the generator). Never report a figure as accuracy. Never write to `data/gold/`. Never weaken the `--gold` refusal in `src/models/dataset.py`. An attribution is a claim about the model, not about athlete psychology.

Five corollaries accumulated from earlier phases, all binding:

- **Phase 18:** a gate that only checks a result *exists* is worse than no gate, because it launders the claim.
- **Phase 19:** the claim ledger is upstream of the prose. Any headline sentence not traceable to a row in `src/evaluation/ablations.py::CLAIMS` requires a new `Claim`, added and passing the gate, *before* it is written anywhere.
- **Phase 20:** a property the unit tests can see is not the whole property. Two defects passed every test and were caught only by rendering the page and looking at it.
- **Phase 21:** a detector that fires on everything is exactly as uninformative as one that fires on nothing. Both make the difference between 0 findings and N findings meaningless. A gate needs both a proven floor and a legible ceiling.
- **Running through all five:** the check and the thing it protects keep turning out to be related by *assumption* rather than by *construction*. That is the defect shape this project has found five times. Assume it is present in your phase too.

## Where the numbers stand (real checkpoint, 2026-08-16)

Transformer macro-F1 **0.588** [0.546, 0.622] template-disjoint vs a lexicon floor of **0.462** [0.431, 0.492], delta +0.126 at p=0.000 paired bootstrap. The headline result is the memorisation gap: TF-IDF+LogReg scores 0.999 random-split and 0.222 template-disjoint (+0.777); the transformer's own gap is +0.234; the lexicon control moves only +0.100. Explanations beat a random-span control by +0.328 comprehensiveness with all ten constructs beating control individually - but 104 of 120 driver rows (86.7%) have no supporting span, published rather than hidden. Three negative results are reported as results: silver supervision bought nothing (+0.033, p=0.107), the risk index cannot be calibrated because no observed outcome exists, and four of ten constructs are inert in the fusion layer.

**These are the numbers your gate must reproduce.** They live in `reports/results.json` and are pinned as rows in `src/evaluation/ablations.py::CLAIMS`.

## What Phase 21 just delivered (do not rebuild it)

`src/security/` - four pure-Python modules with no ML imports: `audit.py` (report primitives: `Severity`, `shape()`, `Finding`, `ScannerResult`, `AuditReport.gate()`, `render_markdown`), `sweep.py` (detectors, canary, `run_sweep`), `baseline.py` (interrogates `.secrets.baseline`), `deps.py` (pinned-vs-floor classification). Plus `scripts/run_security_audit.py` (the only place that shells out to git, touches the network or writes to disk), `tests/test_security.py` (49 tests, ~1.2s, no ML stack), `docs/security.md` (the deliverable), and `reports/security_audit.md` (the generated run, committed as evidence).

The audit gate **passes** (exit 0). Ten findings; three are yours.

## Two things are outstanding before Phase 22 work, and they are your step 0

**1. The Phase 20 Docker check, still unrun across two sessions.** In PowerShell:

```powershell
cd C:\Users\saika\sports-risk-nlp
docker compose build app
docker compose up dashboard   # http://localhost:8501, click BOTH tabs, then Ctrl-C
```

Expected: the "Known examples" tab shows `synth_precomp_v1-003481` at risk index 0.87 with `burnout_signal` at +1.335, and the four inert constructs carry a hatched dashed marker **on both tabs**. If the hatch is missing on one tab, the duplicate-SVG-id defect has regressed. Report the result before starting.

**2. SEC-03 - regenerate the secrets baseline inside the container.** Phase 21 corrected the baseline's recorded *verdicts* and its path separators, but deliberately did **not** refresh `generated_at`, because moving it would assert a re-scan that never happened. Closing it is one command and it belongs at the head of a reproducibility phase:

```powershell
docker compose run --rm app detect-secrets scan > .secrets.baseline
docker compose run --rm app detect-secrets audit .secrets.baseline
python -m pytest tests/test_security.py -q      # EXPECT: still 49 passed
```

If the audit step offers anything that is **not** a `training_fingerprint` hash, stop and read it. That is a new finding, not a formality.

## Phase 22 - what you are building

**Objective:** a reviewer can rerun it.
**Tasks:** pin versions; fix all seeds; finalize Docker; write run scripts; complete the model card; prepare an anonymized artifact for release.
**Deliverable:** one-command reproduction path + artifact.
**Gate as originally written:** fresh clone reproduces headline numbers within tolerance.

### Three Phase 21 findings are already Phase 22 tasks - start from these, not from a search

- **SEC-07 (the big one).** Neither shipped image installs `requirements.lock.txt`. `Dockerfile` installs `requirements-base.txt` (12 floors); `Dockerfile.train` installs `requirements-ml.txt` (7 floors). **A floor is not a version** - `torch>=2.2` resolves to a different answer every build. The only auditable file, the 180-pin lock, is the one no image uses. Consequence: the artifact's security statement *and* its reproducibility statement currently both describe the owner's Windows host venv rather than either container. Fix by having the images install the lock, or by generating per-layer locks.
- **SEC-04.** A personal Gmail address is committed in six documents as the participant contact route: `docs/consent_form.md` (×2), `docs/ethics.md` (×2), `docs/open_issues.md`, `docs/recruitment.md`. `docs/ethics.md` §7.1 already names the remedy - an SRMIST institutional address plus a named supervisor.
- **SEC-05.** `C:\Users\<name>\sports-risk-nlp` appears in 25 tracked files, naming the author: `docs/setup.md`, `docs/docker.md`, `requirements.lock.txt` line 4, and most `phase*_handover.md`. `tests/test_transformer.py` already uses `C:\Users\x\...` - copy that.

`python scripts/run_security_audit.py --online` re-runs the sweep, so **SEC-04 and SEC-05 reaching zero is a checkable end state**, not a judgement call. Use it that way.

## Strengthen the gate before you start

"Fresh clone reproduces headline numbers within tolerance" is answerable by a person sitting in a directory that already contains everything. Phase 21 predicted your defect in advance:

> **The reproduction will be verified by a person who already has the artefacts that make it reproduce.** It will be checked in a working tree holding `models/`, `data/`, `reports/` and a warm pip cache from four months of work, and the step that silently reads one of those will pass - and will fail for the first reviewer who has none of them.

Same relationship-by-assumption as every previous instance: the check ("it reproduced") and the property ("a stranger can reproduce it") are related by an environment nobody enumerated. Add these to the gate and write the answers down:

- **Verify in a container built `--no-cache`, from a `git clone` into a NEW directory** - never in the working tree. `data/` and `models/` are gitignored, so a genuine fresh clone **has neither**. If the path still reproduces, ask what it read, because the corpus has to come from somewhere. (`scripts/run_ingestion.py` at seed 42 is the intended answer - verify that it *is* the answer rather than assuming it.)
- **The lock file pins `torch==2.13.0+cpu`**, a local version that does not exist on the default PyPI index. `pip install -r requirements.lock.txt` fails without `--extra-index-url https://download.pytorch.org/whl/cpu`. A reproduction command that only works with an undocumented flag is not a one-command path. Confirm the flag is inside the path, not in a reader's memory.
- **"Within tolerance" needs a NUMBER, chosen and written down BEFORE the re-run.** Phase 19's corollary applies without exception: a tolerance is a claim, so it belongs in `ablations.py::CLAIMS` and must pass the claim gate first. **A tolerance picked after seeing the delta is not a gate.**
- **Print what the reproduction does NOT reproduce.** Gold-derived figures cannot be reproduced because `data/gold/` is empty (OPEN-025), and the transformer arm needs roughly 10 CPU-hours. A one-command path that quietly skips them is claiming more than it delivers. Every previous phase's coverage statement exists for this reason; `src/security/audit.py::ScannerResult` makes the pattern mandatory by construction and is worth copying.
- **Distinguish byte-identical from within-tolerance, per artefact.** Some outputs are seeded and should match exactly (the corpus at seed 42, the classical baselines - Phase 13 asserts reproducibility at full float precision, not `approx`); others cannot. Say which is which, per artefact, rather than applying one word to all of them.

## Hard constraints - non-negotiable

Display or commit no verbatim corpus text anywhere outside the synthetic A2 source: not in the artifact, not in the model card, not in logs, not in a reproduction transcript. `docs/ethics.md` binds this and `src/explainability/cards.py::assert_publication_safe` is the existing mechanism - use it rather than reimplementing it. `src/security/audit.py::shape()` is how Phase 21 complied when it needed to report matched text; reuse it if you need the same thing.

Label no number "accuracy", "confidence in the athlete", or anything implying a measurement of a person. Every score surface carries `src/evaluation/harness.py::PROVISIONAL_STAMP`.

**Any phrase claiming the explanations were validated by experts, practitioners or coaches is forbidden everywhere** - paper, abstract, figures, dashboard, slides, model card, artifact README and any new document. The three exact banned strings are in `src/dashboard/view.py::FORBIDDEN_SUBSTRINGS`; read them there. OPEN-004 was closed by *decision*, not by recruitment: the study shipped as a blinded pilot self-audit with sports-familiar student raters, with practitioner validation named as a limitation. If any document references the study, use the mandatory wording fixed verbatim in `docs/findings.md` §2.4. `assert_no_forbidden_language` implements the screen - reuse it. One deliberate exception: the literal denial "not accuracy" is permitted, because `PROVISIONAL_STAMP` itself contains it.

**Phase 21 raised SEC-10 and you should know why.** That screen existed since Phase 20 and had never been run over the project's own planning documents - the forbidden claim was still asserted in `CLAUDE.md`, `.claude.md`, `PROJECT_PLAN.md` and `docs/related_work.md`, which are the exact sentences Phase 23 will draft the contribution paragraph from. Fixed. **Standing caveat: the screen is a case-insensitive substring test and cannot tell a claim from a statement of the prohibition**, so its output over the whole repo is a triage queue, not a findings list. Run it blanket over reader-facing surfaces, where every hit is real; triage the rest by hand.

Do not retrain, do not re-tune thresholds, do not regenerate the corpus *except* as the reproduction path itself does it. Do not weaken any existing guard to make a reproduction pass - if a guard fires, that is the finding.

Do not describe the risk decomposition as ten-construct without qualification. Four constructs - `appraisal_orientation`, `attentional_focus`, `coping_style`, `motivation_orientation` - are inert under the conservative `PolarityPolicy.NEUTRAL` default.

## Architecture - follow the project's established shape

Anything that needs to be checked repeatedly goes in tested pure Python under `src/`, and the runner in `scripts/` is a thin shell over it. This is the project's default and it has paid for itself six phases running (`src/risk/` at 15, `src/explainability/` at 17, `src/evaluation/` at 18, `src/dashboard/` at 20, `src/security/` at 21). The test suite must run with **no ML stack installed** - every phase since 15 has held this line and it is why tests run in seconds.

If Phase 22 produces a re-runnable reproduction check - and it should - it belongs in `src/` with `scripts/` as the runner. Phase 21's split is the template: `src/security/` is offline, filesystem-light and dependency-injected, while `scripts/run_security_audit.py` owns the three things a test must never do (shell out to git, touch the network, write to disk). Copy that separation.

## What already exists - rebuild none of it

`src/security/` (Phase 21), `src/dashboard/` (Phase 20), `src/explainability/cards.py` (`build_card`, `highlight`, `render_markdown`, `assert_publication_safe`, `CardSet`), `src/risk/fusion.py` (`LinearRiskScorer`, `PolarityPolicy`), `src/models/` (`TransformerBaseline.load` / `predict_proba`, and the `--gold` refusal in `dataset.py`), `src/evaluation/harness.py` (`PROVISIONAL_STAMP`, `assert_not_accuracy`), `src/evaluation/ablations.py` (`CLAIMS` - the ledger, upstream of all prose), `src/preprocessing/deidentify.py` (read its limitations before trusting it), `src/ingestion/allowlist.py` (the fail-closed data-source allow-list), `reports/results.json`, `reports/explain/cards.md`, `reports/figures/`, `reports/dashboard/`, `docs/findings.md`, `docs/security.md`, `docs/dashboard.md`, `docs/model_card.md` (exists, needs completing - do not start it over), `Dockerfile`, `Dockerfile.train`, `docker-compose.yml`, `.pre-commit-config.yaml`, `.secrets.baseline`.

## Skills to use

Read the relevant `SKILL.md` files before building, not while building. At minimum consult **`engineering:deploy-checklist`** for the packaging and release path, **`engineering:testing-strategy`** when designing the strengthened gate checks above, **`engineering:documentation`** for the model card and the artifact README, and **`engineering:code-review`** before you declare the phase done.

## Working rules

Teach while doing - the owner is a sophomore. Be concise in chat and put the depth in files. Work in small verifiable steps and end non-trivial work with a verification step; Phase 20 is the argument for that rule (three defects found by rendering output and looking at it, none by the tests) and Phase 21 is the second argument (its canary check caught a broken detector on the first run, before it could report a clean scan). `pytest` excludes `-m slow` by default. Install ML dependencies with `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu`.

**Git in this repo must be run by the owner in PowerShell.** When a Cowork session reaches the repo through the desktop folder bridge, git cannot unlink its own lock files, so `git add` succeeds and `git commit` fails with "Operation not permitted". Give the owner exact commands rather than running them yourself, including `if (Test-Path .git\index.lock) { Remove-Item .git\index.lock }` first. After any commit, verify it landed with `git log --oneline -1` **as its own command** - Phases 17 and 18 were both discovered uncommitted because a stale `index.lock` aborted a commit and the failure was read as success.

**Two environment traps Phase 21 hit, both worth knowing before you lose an hour to them.** First: through the folder bridge, `git status` prints a warning and returns **no output** because it cannot write `index.lock` - an empty `git status` here reads exactly like "clean working tree" and is evidence of nothing. Run git queries against a copied index instead (`cp .git/index /tmp/gidx; export GIT_INDEX_FILE=/tmp/gidx`). Second: the pre-commit hooks will run on the owner's commit and *will* block it if you have not checked them. Verify before handing over commands - `ruff check` and `ruff format --check` on every `.py` you touched, and remember that `detect-private-key` honours no inline waiver, so a literal PEM header anywhere in a staged file blocks the commit outright.

Produce a handover file at the end of the phase - `handover_phase_22.txt`, structured as Part A project summary, Part B session summary, Part C handoff for Phase 23 (IEEE draft assembly) - self-contained enough that a fresh session can continue from it alone. Include a named prediction of the defect shape to expect in Phase 23, as every handover since 18 has done. Do not start Phase 23 until the owner confirms receipt.

## Open items, in priority order

- **OPEN-011** - no real athlete text. The project's highest live risk and its only unmitigated high-impact item. Contribution #1 must be stated as a *synthetic* construct-grounded corpus throughout, including in the artifact README and the model card.
- **OPEN-025** - no second annotator, so no gold and no kappa. Blocks every accuracy claim in the paper, and bounds what the reproduction can possibly reproduce.
- **OPEN-021** - the lexicon baseline is not independent of the corpus; the caveat travels with the 0.462 floor wherever it is quoted.
- **OPEN-028** - silver is PRNG output; measured (+0.033, p=0.107) rather than asserted.
- **SEC-03** - the secrets baseline is internally correct and still stale; step 0 above closes it.
- **SEC-04 / SEC-05 / SEC-07** - Phase 22 tasks, detailed above.
- **SEC-06** - `chromadb==1.1.1` carries an open advisory with no fixed release; transitive via `crewai`, never imported by this project, severity not retrievable. Re-check at Phase 25; do not remove `crewai` for it.
- **OPEN-030/031/032, OPEN-005/006** - pre-submission items for Phases 23–25.

Begin by running the two step-0 items above and reporting their results, then read the files named at the top and tell me your plan for Phase 22 - including how you intend to structure the re-runnable reproduction check so it stays testable without torch, what number you propose for "within tolerance" and which `Claim` row it will become, and which artefacts you expect to be byte-identical versus merely within tolerance. Ask me anything genuinely ambiguous before you write code.

Think before answering (maximum reasoning)
