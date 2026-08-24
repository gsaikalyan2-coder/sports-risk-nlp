You are continuing an ongoing IEEE conference paper project as a Claude Cowork session. The repository is at `C:\Users\x\sports-risk-nlp` and is connected to this session as a folder. Read `CLAUDE.md` first — it overrides defaults — then `handover_phase_20.txt`, `docs/findings.md`, `docs/ethics.md`, and `PROJECT_PLAN.md`. Everything below is a summary so you know what you're walking into; the files are the source of truth.

## The project

Pre-Competition Psychological Risk Profiling of Athletes. NLP × sports psychology: detect 10 validated constructs (CSAI-2 / SDT / ABQ tradition) in athlete text and fuse them into an interpretable risk index with two-level explanations (span→construct, construct→risk). Owner: Saikalyan, sophomore at SRMIST. Week 4 of 8, paper draft due first week of September 2026, Python 3.11.

Phases 1–15 and 17–20 are complete. Phase 16 (DataRobot AutoML) was skipped by decision. Your job is **Phase 21 — security scan, dependency and PII audit**.

## The constraint that governs everything — carry it forward verbatim

`data/gold/` is empty. **No number in this repository is an accuracy.** Every result is a corpus property of a synthetic template grammar (`synth_precomp_v1`, 4,000 generated records, labels planted by the generator). Never report a figure as accuracy. Never write to `data/gold/`. Never weaken the `--gold` refusal in `src/models/dataset.py`. An attribution is a claim about the model, not about athlete psychology.

Three corollaries accumulated from earlier phases, all binding:

- **Phase 18:** a gate that only checks a result *exists* is worse than no gate, because it launders the claim.
- **Phase 19:** the claim ledger is upstream of the prose. Any headline sentence not traceable to a row in `src/evaluation/ablations.py::CLAIMS` requires a new `Claim`, added and passing the gate, *before* it is written anywhere.
- **Phase 20:** a property the unit tests can see is not the whole property. Two defects last phase passed every test and were caught only by rendering the page and looking at it.

## Where the numbers stand (real checkpoint, 2026-08-16)

Transformer macro-F1 **0.588** [0.546, 0.622] template-disjoint vs a lexicon floor of **0.462** [0.431, 0.492], delta +0.126 at p=0.000 paired bootstrap. The headline result is the memorisation gap: TF-IDF+LogReg scores 0.999 random-split and 0.222 template-disjoint (+0.777); the transformer's own gap is +0.234; the lexicon control moves only +0.100. Explanations beat a random-span control by +0.328 comprehensiveness with all ten constructs beating control individually — but 104 of 120 driver rows (86.7%) have no supporting span, published rather than hidden. Three negative results are reported as results: silver supervision bought nothing (+0.033, p=0.107), the risk index cannot be calibrated because no observed outcome exists, and four of ten constructs are inert in the fusion layer.

## What Phase 20 just delivered (do not rebuild it)

`src/dashboard/` (backend / view / charts — pure Python, no torch), `dashboard/app.py` (a ~115-line Streamlit shell with zero business logic), `tests/test_dashboard.py` (23 tests), `tests/fixtures/dashboard_known_examples.json`, `scripts/build_dashboard_{fixture,figure}.py`, `docs/dashboard.md`, `reports/dashboard/` (3 screenshots including a grayscale proof), `reports/figures/phase20_explanation_card.{svg,png}`. The suite runs in ~1.5s with no ML stack installed.

**One Phase 20 gate item is outstanding and it is your step 0.** In PowerShell:

```powershell
cd C:\Users\x\sports-risk-nlp
docker compose build app
docker compose up dashboard   # http://localhost:8501, click BOTH tabs, then Ctrl-C
```

Expected: the "Known examples" tab shows `synth_precomp_v1-003481` at risk index 0.87 with `burnout_signal` at +1.335, and the four inert constructs carry a hatched dashed marker **on both tabs**. If the hatch is missing on one tab, the duplicate-SVG-id defect has regressed. Report the result before starting Phase 21 work.

## Phase 21 — what you are building

**Objective:** ship something safe and clean.
**Tasks:** run the security-scan workflow on the repo and `.claude` config; scan for committed secrets; dependency vulnerability check; final PII sweep of released data.
**Deliverable:** `docs/security.md` (findings + fixes).
**Gate as originally written:** no secrets in git history; no high-severity dependency issues; released data PII-clean.

**Strengthen that gate before you start.** This project has now found the same defect shape four phases running — Phase 9b (the obvious duplication fix did nothing because bank size was never the lever), Phase 17 (an ethics guard passed its own test while bypassable through a different field), Phase 18 (the claim gate certified a claim its own evidence contradicted), Phase 20 (two charts shared an SVG element id, so one chart's required marking rendered blank while every unit test stayed green). Each time, the check and the thing it protects were related by assumption rather than by construction.

**Phase 21's instance is easy to name, because a security phase is made almost entirely of gates:**

> A scanner reporting "0 findings" will be accepted as "there is nothing to find", without anyone checking what the scanner actually looked at.

Add these to the gate, and write down the answers in `docs/security.md` next to each finding:

- **Read `.secrets.baseline` (4,035 bytes, exists) before trusting any clean `detect-secrets` run.** A baseline is a list of findings someone already decided to ignore. A clean scan against a stale baseline is a laundered claim — this is literally OPEN-034 in a new costume. Report how many entries the baseline suppresses and whether each is still justified.
- **`.env` exists in the working tree (92 bytes).** Prove it was never committed by checking *history*, not the index: `git log --all --full-history -- .env` must return nothing. `git ls-files .env` returning nothing is a weaker claim and is not sufficient.
- **`donations_inbox.jsonl` (522 bytes) sits at the repo ROOT, not under `data/`.** A PII sweep scoped to `data/` misses it entirely. Check whether it is tracked, what it contains, and whether it should be gitignored. Also sweep the root-level `annotation/` and `onboarding/` directories, which are likewise outside `data/`.
- **The dependency scan must cover `requirements-base.txt`, `requirements-ml.txt` AND `requirements.lock.txt`.** Scanning only the first reports on the light Docker image and says nothing about the training image. `Dockerfile.train` builds `FROM sports-risk-nlp-base:latest`, so both are in scope.
- **Check what `models/` and `.venv/` do in git.** `.gitattributes` exists (1,890 bytes) — determine whether LFS is in play and whether any model checkpoint or virtualenv content was ever committed.
- **For every tool you run, write one sentence in `docs/security.md` saying what it does NOT cover.** That sentence is the thing that stops the next reader from over-reading a clean result. A findings table with no coverage statement is the Phase 18 defect.

## Hard constraints — non-negotiable

Display or commit no verbatim corpus text anywhere outside the synthetic A2 source: not in `docs/security.md`, not in scan output pasted into a report, not in logs. `docs/ethics.md` binds this and `src/explainability/cards.py::assert_publication_safe` is the existing mechanism — use it rather than reimplementing it. If a scanner's output quotes a matched line from a data file, redact it before it reaches a committed document.

Label no number "accuracy", "confidence in the athlete", or anything implying a measurement of a person. Every score surface carries `src/evaluation/harness.py::PROVISIONAL_STAMP`.

The strings **"expert-validated", "practitioner-validated" and "coach-validated" are forbidden** everywhere — paper, abstract, figures, dashboard, slides, and any new document. OPEN-004 was closed by *decision*, not by recruitment: the expert study shipped as a blinded pilot self-audit with sports-familiar student raters, with practitioner validation named as a limitation. If any document references the study, use the mandatory wording fixed verbatim in `docs/findings.md` §2.4. `src/dashboard/view.py::FORBIDDEN_SUBSTRINGS` and `assert_no_forbidden_language` already implement this screen — reuse them if a new surface needs screening. Note the one deliberate exception: the literal denial "not accuracy" is permitted, because `PROVISIONAL_STAMP` itself contains it.

Do not retrain, do not re-tune thresholds, do not regenerate the corpus. Do not weaken any existing guard to make a scan pass — if a guard fires, that is the finding.

Do not describe the risk decomposition as ten-construct without qualification. Four constructs — `appraisal_orientation`, `attentional_focus`, `coping_style`, `motivation_orientation` — are inert under the conservative `PolarityPolicy.NEUTRAL` default.

## Architecture — follow the project's established shape

Anything that needs to be checked repeatedly goes in tested pure Python under `src/`, and the runner in `scripts/` is a thin shell over it. This is the project's default and it has paid for itself five phases running (`src/risk/` at 15, `src/explainability/` at 17, `src/evaluation/` at 18, `src/dashboard/` at 20). The test suite must run with **no ML stack installed** — every phase since 15 has held this line and it is why tests run in seconds. If Phase 21 produces a re-runnable audit (a PII sweep is a good candidate), it belongs in `src/`, with `scripts/run_security_audit.py` as the runner, not as a one-off notebook or a pasted terminal transcript.

## What already exists — rebuild none of it

`src/preprocessing/deidentify.py` (the Phase 8 de-identification pass, measured 34/34 exact on its fixture, leak rate 0% — read its limitations before trusting it as a PII checker: it measures the failure modes someone thought to write down, on a corpus that plants no identifiers), `src/preprocessing/audit.py`, `src/explainability/cards.py::assert_publication_safe`, `src/evaluation/harness.py::{PROVISIONAL_STAMP, assert_not_accuracy}`, `src/dashboard/view.py::assert_no_forbidden_language`, `src/ingestion/allowlist.py` (the fail-closed data-source allow-list), `.pre-commit-config.yaml`, `.secrets.baseline`, `docs/ethics.md`, `docs/findings.md`, `docs/dashboard.md`.

## Skills to use

Read the relevant `SKILL.md` files before building, not while building. At minimum consult the **`security-scan`** skill for the audit workflow itself, **`engineering:testing-strategy`** when designing the strengthened gate checks above, **`engineering:documentation`** for `docs/security.md`, and **`engineering:code-review`** before you declare the phase done.

## Working rules

Teach while doing — the owner is a sophomore. Be concise in chat and put the depth in files. Work in small verifiable steps and end non-trivial work with a verification step; Phase 20 is the argument for that rule, since three of its defects were found by rendering output and looking at it and none by the tests. `pytest` excludes `-m slow` by default. Install ML dependencies with `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu`.

**Git in this repo must be run by the owner in PowerShell.** When a Cowork session reaches the repo through the desktop folder bridge, git cannot unlink its own lock files, so `git add` succeeds and `git commit` fails with "Operation not permitted". Give the owner exact commands rather than running them yourself, including `if (Test-Path .git\index.lock) { Remove-Item .git\index.lock }` first. After any commit, verify it landed with `git log --oneline -1` rather than trusting that the command was issued — Phases 17 and 18 were both discovered uncommitted because a stale `index.lock` aborted a commit and the failure was read as success.

Produce a handover file at the end of the phase — `handover_phase_21.txt`, structured as Part A project summary, Part B session summary, Part C handoff for Phase 22 (reproducibility packaging) — self-contained enough that a fresh session can continue from it alone. Include a named prediction of the defect shape to expect in Phase 22, as every handover since 18 has done. Do not start Phase 22 until the owner confirms receipt.

## Open items, in priority order

- **OPEN-011** — no real athlete text. The project's highest live risk and its only unmitigated high-impact item. Contribution #1 must be stated as a *synthetic* construct-grounded corpus throughout.
- **OPEN-025** — no second annotator, so no gold and no kappa. Blocks every accuracy claim in the paper.
- **OPEN-021** — the lexicon baseline is not independent of the corpus; the caveat travels with the 0.462 floor wherever it is quoted.
- **OPEN-028** — silver is PRNG output; now measured (+0.033, p=0.107) rather than asserted.
- **OPEN-030/031/032, OPEN-005/006** — pre-submission items for Phases 22–25.

Begin by running the step-0 Docker check above and reporting its result, then read the files named at the top and tell me your plan for Phase 21 — including how you intend to structure any re-runnable audit code so it stays testable without torch, and what each scanner you plan to run does *not* cover. Ask me anything genuinely ambiguous before you write code.

Think before answering (maximum reasoning)
