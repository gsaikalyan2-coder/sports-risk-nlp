# Security, dependency and PII audit — Phase 21

**Audit date:** 2026-08-23 · **Commit audited:** `fa4c22c` (Phase 20) · **Tracked files:** 257
**Re-run it:** `python scripts/run_security_audit.py --online --out reports/security_audit.md`
**Tests:** `pytest tests/test_security.py` — 49 tests, ~1.2 s, no ML stack required.

**Gate: PASS** (exit code 0) — zero HIGH findings, and every scanner proved its detectors fire
on this run. Both HIGH findings raised by the first execution (SEC-01, SEC-02) were **fixed**
during the phase, not suppressed; the fixes and their residual limits are recorded below.

**What a PASS here does and does not mean.** It means: no credential shape survives on the
released surface or anywhere in 34 commits of history, no released file carries a third party's
identifier, every detector demonstrated on this run that it can fire, and nothing is being
suppressed by a verdict nobody checked. It does **not** mean the repository has nothing left to
fix — seven findings remain open at MEDIUM and LOW, four of them handed to Phase 22, and §3 lists
what each tool cannot see. The gate is a floor, and the coverage statements are the reason the
floor is worth standing on.

---

## 1. The rule this phase was built around

`handover_phase_20.txt` §C4 predicted Phase 21's defect before the phase began, and the
prediction was correct enough that it shaped every design decision in `src/security/`:

> A scanner reporting "0 findings" will be accepted as "there is nothing to find", without
> anyone checking what the scanner actually looked at.

Four phases running, this project has found the same shape: **the check and the thing it
protects were related by assumption rather than by construction.** A security phase is made
almost entirely of gates, so the exposure here is larger than usual. Three mechanisms answer it,
and they are mechanisms rather than conventions on purpose:

| # | Mechanism | Where it lives | What becomes impossible |
|---|---|---|---|
| 1 | `ScannerResult` **requires** a non-empty `does_not_cover` sentence, validated at construction | `src/security/audit.py` | A findings table with no coverage statement. The reader cannot over-read a clean result, because the limits are printed beside it. |
| 2 | The sweep's file set is **`git ls-files`**, never a directory walk | `src/security/sweep.py` | "The sweep was scoped to `data/` and missed the file at the repo root." A file's position in the tree cannot put it out of scope. |
| 3 | `run_sweep` **refuses to report** unless every detector has just fired on a canary planting its own target | `src/security/sweep.py` | A zero produced by a broken pattern. A clean result now means "these detectors, demonstrably working, found nothing" — a weaker and truer claim. |

Mechanism 3 justified itself on its first execution: see §6.

**Every finding below carries the coverage statement of the tool that produced it.** That
sentence is the deliverable as much as the finding is.

---

## 2. Findings

Severity is assigned by a human reading the evidence, not by a tool — see §3 for why the
dependency scanner cannot assign one.

| ID | Sev | Area | Finding | Status |
|---|---|---|---|---|
| **SEC-01** | HIGH | secrets baseline | 4 of 4 entries in `.secrets.baseline` were recorded `is_secret: true` | **FIXED this phase** |
| **SEC-02** | HIGH | secrets baseline | Baseline filenames used Windows separators; its exclude patterns use POSIX ones. It was platform-locked in both directions | **FIXED this phase** |
| **SEC-03** | MEDIUM | secrets baseline | Baseline generated 2026-08-12; 57 tracked paths have been added or changed since and have never been scanned against it as a tree | **open — see below** |
| **SEC-04** | MEDIUM | PII / release | A personal email address is committed in 6 documents as the participant contact route | **open — Phase 22** |
| **SEC-05** | LOW | PII / release | `C:\Users\<name>` appears in 25 tracked files, naming the author | **open — Phase 22** |
| **SEC-06** | MEDIUM | dependencies | `chromadb==1.1.1` carries GHSA-f4j7-r4q5-qw2c / CVE-2026-45829; no fixed release published | **open — mitigated, see below** |
| **SEC-07** | MEDIUM | dependencies | Neither shipped image installs the lock file; both install floor-only requirement files, which cannot be audited at all | **open — Phase 22** |
| **SEC-08** | LOW | data governance | `donations_inbox.jsonl` sits inside the repository although its own note says it must live outside it | **open — owner action** |
| **SEC-09** | INFO | method | `git status` returns empty output in the Cowork folder-bridge environment because it cannot write `index.lock`. A "clean" status read here is not evidence of anything | **recorded; see §7** |
| **SEC-10** | MEDIUM | claim safety | The contribution claim forbidden by OPEN-004 survived in the four documents the paper will be drafted *from* | **FIXED this phase** |

### SEC-01 — the baseline suppresses four *confirmed* findings

`detect-secrets` records `is_secret: false` for "a human reviewed this and it is a false
positive" and `is_secret: true` for "a human reviewed this and it **is** a secret". A baseline
is the first kind. All four entries in this repository's baseline are the second kind:

| file (as recorded) | line | detector |
|---|---|---|
| `reports\baselines.json` | 393 | Hex High Entropy String |
| `reports\baselines.json` | 937 | Hex High Entropy String |
| `reports\transformer.json` | 127 | Hex High Entropy String |
| `reports\transformer.json` | 360 | Hex High Entropy String |

**What they actually are:** all four are `training_fingerprint` values — SHA-256 digests that
back the reproducibility claim in `CLAUDE.md` §9. They are derived from public inputs, they are
meant to be published, and they are not credentials. So the *values* are harmless and the
*verdict recorded against them is wrong*, which is the finding: every clean pre-commit run since
2026-08-12 has inherited a suppression whose own metadata says "yes, this is a secret". A
reviewer opening this file sees four confirmed secrets and no explanation. This is OPEN-034 in a
new costume — a gate certifying a claim its own evidence contradicts.

**FIXED 2026-08-23.** The verdict was corrected to `is_secret: false` on all four entries — the
value `detect-secrets` records for "reviewed, false positive", which is what these are. The
review that justifies it is written above and was verified mechanically before the flags moved:
each of the four is 64 lowercase hex characters under the key `training_fingerprint`, and
`src/models/classical.py::training_fingerprint` computes it as a SHA-256 over the synthetic
training pairs, reused by `src/models/transformer.py`. Nothing about it is secret; publishing it
is the point.

`test_an_entry_marked_is_secret_true_is_a_high_finding` fails the gate if a `true` reappears, so
this cannot regress into a green run.

### SEC-02 — the baseline works on neither platform, for opposite reasons

`detect-secrets` matches a baseline entry to a new finding **by filename string**.

* The results keys are `reports\baselines.json`. Inside the container and in CI the scanner
  reports `reports/baselines.json`. The strings differ, so **on Linux the four entries suppress
  nothing** and the hook fails on findings it was supposed to have absolved.
* The baseline's own exclusion filter is `^data/|^paper/|^\.git/|^models/|…` — forward slashes.
  On Windows the scanner supplies `data\...`, which the pattern does not match, so **on Windows
  the directories the baseline claims to exclude are scanned after all.**

Neither direction is visible from a green hook run, which is the entire problem. Note also that
`.pre-commit-config.yaml` carries a *second, different* exclude list
(`data/.*|paper/.*`, no `models/`); the two disagree about `models/`.

**FIXED 2026-08-23.** Both halves:

* Every `results` key and every entry's `filename` field was converted to forward slashes, so the
  four suppressions now match the filenames the scanner actually reports inside the container and
  in CI. Nothing else in the file moved — 27 plugins, 13 filters and 4 entries all preserved,
  verified by count after the rewrite.
* `.pre-commit-config.yaml`'s `exclude:` was reconciled with the baseline's own
  `should_exclude_file` pattern (it was missing `models/`), with a comment naming the baseline as
  authoritative if they ever diverge again. Two exclusion lists for one scanner is one list
  nobody can audit.

`test_windows_separators_in_a_baseline_are_a_high_finding` fails the gate if a backslash
reappears.

**The limit of this fix, and it is the reason SEC-03 stays open.** This corrected two recorded
*verdicts*; it was **not a re-scan**. `generated_at` was deliberately left at
`2026-08-12T13:35:43Z` rather than being refreshed, because moving it would assert a scan that
never happened — the same laundering this phase exists to refuse, applied to its own remediation.
The baseline is now internally correct and still stale.

**What makes the staleness tolerable rather than alarming, stated so nobody has to take it on
trust:** the release-surface sweep in §3.1 independently covered all 251 tracked text files with
proven detectors and found no credential shape, and the history scan in §4.1 covered every blob
in all 34 commits. Those two together are stronger evidence about the current tree than a fresh
baseline would be. Regenerating inside the container is still the right closing move for SEC-03,
and it is the first item in §8.

### SEC-04 / SEC-05 — the artifact names its author

Not a leak of anyone else's data; a de-anonymisation of the submission.

* **SEC-04** — a personal Gmail address appears in `docs/consent_form.md` (×2),
  `docs/ethics.md` (×2), `docs/open_issues.md` and `docs/recruitment.md` as the participant
  contact and withdrawal route. `docs/ethics.md` §7.1 already records the intended remedy
  ("replace with an SRMIST institutional address + named supervisor"), so this is a known,
  deliberate placeholder rather than an accident — but it is a personal identifier in a document
  set that goes to review, and a participant-facing withdrawal route that stops working the day
  the address does.
* **SEC-05** — `C:\Users\<name>\sports-risk-nlp` appears in 25 tracked files (`docs/setup.md`,
  `docs/docker.md`, `requirements.lock.txt` line 4, and most `phase*_handover.md`), naming the
  author's account. `tests/test_transformer.py` already uses `C:\Users\x\...` and is the pattern
  to copy.

Both are **Phase 22 (reproducibility packaging)** work, where "prepare an anonymized artifact for
release" is already a task. Listing them here so that task starts with the file list rather than
a search.

### SEC-06 — one advisory, on a package this project never imports

`chromadb==1.1.1` (`requirements.lock.txt` line 46) carries **GHSA-f4j7-r4q5-qw2c** /
**PYSEC-2026-311** / **CVE-2026-45829**. It is a *transitive* dependency, pulled by `crewai`; it
appears in no direct requirement file.

* **No fixed release exists.** The advisory is still open against chromadb 1.5.9, the current
  release at audit date, so upgrading is not a remedy.
* **Severity could not be retrieved.** PyPI's advisory endpoint returns ids and aliases but no
  CVSS score, and the GitHub advisory endpoint is not reachable from this environment. The
  severity above is a placeholder pending the owner reading the advisory. **Do not report it as
  assessed.**
* **Mitigation, and it is a strong one:** `grep -rn chromadb src/ scripts/ config/ tests/`
  returns exactly one line, in `requirements.lock.txt`. Nothing in this project imports chromadb,
  instantiates a vector store, or opens a network port for one. `CLAUDE.md` §6 lists a vector
  store as "only if RAG added", and RAG was never added. The vulnerable code is present in the
  image and unreachable from any entry point this project ships.

**Recommendation:** record it in the artifact statement as a known advisory in an unused
transitive dependency, and re-check for a fix at Phase 25. Removing it means removing `crewai`,
which is a confirmed Phase 6 decision and not worth reopening for an unreachable code path.

### SEC-07 — the auditable file is the one nothing installs

This is sharper than the instruction that prompted it, and it is a reproducibility finding as
much as a security one.

| file | kind | lines | auditable? | installed by |
|---|---|---|---|---|
| `requirements-base.txt` | floors and ceilings | 12 | **no** | `Dockerfile` (light image, and the base layer of the training image) |
| `requirements-ml.txt` | floors and ceilings | 7 | **no** | `Dockerfile.train` |
| `requirements.lock.txt` | 180 exact pins | 180 | **yes** | **no image — host installs only** |

There is no such thing as auditing `torch>=2.2`: what gets installed is whatever pip resolves on
the day of the build, and that is a different answer every day. So the single file that can be
audited is the single file neither image uses, and **the security statement made in §3 below
describes the owner's host venv, not either shipped container.** Phase 22 should have the images
install the lock file (or generate per-layer locks) so that the audited versions and the shipped
versions are the same versions.

### SEC-08 — the donation inbox is inside the repository it says it must stay outside of

`donations_inbox.jsonl` (522 bytes, repo root) contains one template record whose `_note` reads:
*"Donor name/contact may be kept in this inbox file for withdrawal handling. This file must live
OUTSIDE the repository."* It is currently inside it.

**Mitigating facts, both verified:** it is gitignored (`.gitignore:116`, pattern
`donations_inbox*.jsonl`), it has never been tracked (`git ls-files` returns nothing for it), and
its current content is the placeholder shipped by `scripts/run_donation.py` — no donor name,
contact or donated text. **Under OPEN-011 no donation has been received, so there is nothing in
it to leak.** The finding is that the safeguard is one `git add -f` away from failing, on a file
whose own documentation says it should not be there.

**Fix (owner):** move it to a directory outside the repository and point
`scripts/run_donation.py` at the new location via an environment variable, before the first real
donation arrives.

### SEC-10 — the banned claim was still upstream of the prose

Found by running `src/dashboard/view.py::assert_no_forbidden_language` over documents it had
never been pointed at. `docs/findings.md` §2.4 and the Phase 17 decision forbid the
"validated-by-an-expert" family of phrases, because OPEN-004 was closed by *decision* — a blinded
pilot self-audit with sports-familiar student raters — not by recruitment. The screen exists,
`src/dashboard/view.py` implements it, and Phase 20 applied it to every rendered dashboard
surface. **Nobody had ever run it over the project's own planning documents.**

Five occurrences survived, and their location is what makes this MEDIUM rather than cosmetic:

| file | line | context |
|---|---|---|
| `CLAUDE.md` | 61 | §1, contribution #2 — the headline differentiator |
| `.claude.md` | 61 | same paragraph, the agent-facing copy |
| `PROJECT_PLAN.md` | 11 | the novelty statement at the head of the plan |
| `docs/related_work.md` | 17, 65 | the gap statement and the contribution list |

Phase 19's corollary is that the claim ledger is upstream of the prose. These four files are
upstream of *everything*: Phase 23 drafts the paper's contribution paragraph from them. The
forbidden claim was sitting in the exact sentences a drafting session copies. All five were
replaced this phase with the qualified wording already fixed in `docs/findings.md`
("two-level interpretability with a measured faithfulness margin"), and the screen now passes on
all four files.

**The use/mention limit, which is now the standing caveat.** `assert_no_forbidden_language` is a
case-insensitive substring test and cannot tell a *claim* from a *statement of the prohibition*.
`docs/findings.md`, `docs/dashboard.md`, the `phase*_handover` files and `view.py` itself all
contain the banned strings while doing the opposite of claiming them, and
`docs/related_work.md:93` contains one inside a cited paper's title — the Kranzinger2025 finding
that sports XAI is rarely validated by practitioners, which is the gap this project exists to
address. **So the screen cannot be run blanket-fashion over the repository and its output is not
a findings list; it is a triage queue.** Run it over reader-facing surfaces — paper, abstract,
figures, dashboard, slides — where every hit is a genuine defect, and triage the rest by hand.

---

## 3. What each tool covers, and what it does not

The right-hand column is the point of this table. A findings table without it is the Phase 18
defect.

### 3.1 Release-surface identifier sweep — `src/security/sweep.py`

**Covers.** Every file `git ls-files` reports as tracked — exactly what a reviewer receives on
clone — 251 of them readable as UTF-8 text, matched against seven identifier and credential
patterns (private key, credential assignment, email, Windows user path, POSIX home path, social
handle, telephone number), each of which was **proven to fire on a planted canary in the same
run** before any result was reported.

**Does NOT cover.** Untracked and gitignored files — which is all of `data/`, `models/`, `.venv/`,
`.env` and `donations_inbox.jsonl`; those are audited separately in §4 precisely because this
scanner cannot see them. Binary files. **Git history**, which holds earlier versions of tracked
files — audited separately in §4.2. And any identifier shape nobody thought to write a pattern
for: this is the same upper-bound caveat `src/preprocessing/deidentify.py` carries, and it is the
real limit. A clean result here is a statement about seven patterns over the tracked tree, not a
statement about the repository.

**Suppressions, listed rather than totalled in silence.** One hit was waived by an inline
`# pragma: allowlist secret` at `docs/setup.md:125` — the deliberately fake key in the
"prove the secret hook works" walkthrough, whose whole purpose is to look like a credential. The
sweep honours `detect-secrets`' own pragma so the repository does not need two vocabularies for
the same idea, and it **prints every waiver it applied**, because a suppression nobody can total
up is `.secrets.baseline`'s problem rewritten as a comment.

**Two detectors were re-tuned mid-audit, and the reason generalises.** The first run returned
~600 telephone hits (every one a float such as `0.5462…` in `reports/*.json`, or an ISO date) and
314 handle hits (every one a `@dataclass` decorator or a BibTeX `@article{`). **A detector that
fires on everything is exactly as uninformative as one that fires on nothing** — both make the
difference between 0 findings and N findings meaningless, which is the same failure this phase
was built to prevent, approached from the other side. Fixes: telephone matches must carry 9–15
digits (E.164's ceiling) and contain no decimal point or bracket; handle matches must not begin
their line, which separates prose handles from decorators and BibTeX entries **by position**
rather than by a name list that needs editing every time a new library is imported. Residual:
10 telephone hits, all DOI/ISSN digit runs in `docs/related_work.md` and `paper/refs.bib`, and
8 handle hits, all in de-identification fixtures and prose *about* handles.

### 3.2 Baseline interrogation — `src/security/baseline.py`

**Covers.** The contents of `.secrets.baseline`: how many findings it suppresses (4, across 2
files), each entry's recorded audit verdict, whether its filenames and exclude patterns use the
separators of the platform the gate runs on, how many detector plugins are configured (27), and
when it was generated (2026-08-12T13:35:43Z).

**Does NOT cover.** Whether the suppressed values are in fact harmless — that judgement is human
and is written out in SEC-01 above, not computed. It does not run `detect-secrets`, does not scan
the tree, and says nothing about files the baseline's own exclude pattern removes from scope
before scanning begins: `^data/|^paper/|^\.git/|^models/|\.secrets\.baseline|\.env\.example`.
**`data/`, `paper/` and `models/` are outside every detect-secrets run this repository has ever
made.**

### 3.3 Dependency advisory audit — `src/security/deps.py`

**Covers.** 180 exactly-pinned requirements from `requirements.lock.txt`, each queried against
the PyPI advisory service by name and upstream version (`+cpu` and other local segments
normalised away, since advisories index the upstream version). 180/180 lookups succeeded; a
failed lookup would have marked the scanner unproven and failed the gate rather than being
counted as "no advisories".

**Does NOT cover.** The 19 floor-or-range requirements in `requirements-base.txt` and
`requirements-ml.txt` — a range has no version to look up, so **nothing in this report describes
what `docker compose build` will install today** (SEC-07). Also: system packages from the images'
`apt-get` layer (`git`, `build-essential`), the `python:3.11-slim` base image itself,
wheel-bundled native code, advisories published after 2026-08-23, **severity scores** (PyPI does
not return them and the GitHub advisory endpoint is unreachable from here), and whether a flagged
code path is reachable from this project — that last one is answered by hand for SEC-06 and for
nothing else.

---

## 4. The gate items, answered by evidence rather than by absence

### 4.1 "No secrets in git history"

Four separate checks, because the obvious one is the weakest.

| check | command | result |
|---|---|---|
| `.env` never committed — **history, not index** | `git log --all --full-history -- .env` | **empty.** `git ls-files .env` is also empty, but that is the weaker claim and is not what was relied on. |
| `.env` is ignored | `git check-ignore -v .env` | `.gitignore:2` |
| Nothing was ever added and later deleted | `git log --all --diff-filter=A --name-only` \| `sort -u` \| `wc -l` | **257 paths ever added; 257 paths tracked now.** The sets coincide, so history holds no file that is not also in the working tree. |
| No credential-shaped string in **any** historical blob | every blob through `git cat-file --batch`, matched against `sk-or-v1-…`, `sk-…`, `gh[pousr]_…`, `AKIA…`, PEM headers | **2 hits, both the documented fake** `sk-or-v1-0123…` in two revisions of `docs/setup.md`. No real credential shape in 34 commits. |

**What this does not cover:** the repository has one remote and 34 commits, all local-authored;
this says nothing about credentials that never took one of these five shapes, and nothing about
values pasted into a service outside git. `.env` currently holds one live OpenRouter key on the
owner's disk — **unused so far (OPEN-008), and it should still be rotated if it has ever been
pasted anywhere.**

### 4.2 "No high-severity dependency issues"

One advisory found (SEC-06), on an unused transitive package, with no fix available and **no
severity retrievable** — see §3.3. The gate as originally written asks for "no high-severity
issues", and this cannot be answered as a yes or a no, because the severity could not be
obtained. It is recorded as MEDIUM by human judgement — one open advisory, no fixed release, code
path unreachable from any entry point this project ships — and it therefore does not fail the
gate. **That is a judgement, not a measurement**, and it is the one place in this report where a
PASS rests on an assessment rather than on evidence. Re-check at Phase 25, when the advisory may
carry a score.

### 4.3 "Released data PII-clean"

**"Released" was redefined as "tracked", and that is the substantive change.** A sweep scoped to
`data/` would have been clean and meaningless: `data/` is gitignored in its entirety and is not
released at all. The corpus reaches a reviewer through no path this audit could find.

| location | tracked? | contains corpus text? | verdict |
|---|---|---|---|
| `data/**` | no — `.gitignore` | yes, all 4,000 records | not released |
| `annotation/gold_dev/data/`, `annotation/gold_eval/data/` | **no** — `.gitignore:93` (`annotation/*/data/`) | yes, 218 KB of utterances plus `context_html` | not released. **This is the one that would have been missed:** it is a second copy of corpus text, outside `data/`, and it is covered only because someone wrote that ignore rule at Phase 11. |
| `annotation/*/config.yaml`, `annotation/*/README.md` | no | no | not released |
| `donations_inbox.jsonl` (repo root) | no — `.gitignore:116` | placeholder only; no donation exists | not released — SEC-08 |
| `onboarding/README.md` | **yes** | no | swept, clean |
| `tests/fixtures/*.jsonl` | **yes** | de-identification fixtures with **invented** identifiers at reserved domains (`example-club.test`, `example.org`) | swept; hits are the planted test data and are correct practice |
| `models/` | only `.gitkeep` | — | no checkpoint has ever been committed; `.gitattributes` is a line-ending policy only, **no Git LFS is configured or in use** |
| `.venv/` | no — `.gitignore:8` | — | never committed |

Residual identifier findings on the released surface are SEC-04 and SEC-05 — the author's own
contact details, not any third party's. **No athlete text, real or synthetic, and no
participant's data, appears in any tracked file.**

**What this does not cover:** the sweep reads seven patterns. `src/preprocessing/deidentify.py`'s
own limitation applies here verbatim and is worth restating because it is the weakest link in
the whole audit — *it measures the failure modes someone thought to write down, on a corpus that
plants no identifiers.* When OPEN-011 resolves and real athlete text enters the pipeline, both
that module and this sweep must be re-measured against it. Neither has ever seen real text.

### 4.4 The `.claude` configuration review

There is no `.claude/` directory in this repository. The agent configuration is `CLAUDE.md` and
`.claude.md` (both tracked, both swept — no credential findings), plus `config/*.yaml` and
`.vscode/` (tracked, swept, clean). `config/model_routing.yaml` and `src/agents/llm.py` read the
OpenRouter key from the environment; **no key literal appears in any tracked configuration file**,
and `.env.example` carries the placeholder `your_openrouter_key_here`.

---

## 5. No verbatim matched text reaches this document

`docs/ethics.md` §3.3 permits verbatim quotation of the A2 synthetic source and nothing else, and
a scanner's proudest output is the line it matched. So no scanner in `src/security/` puts a
matched string into a committed document. `audit.shape()` converts a match to its character-class
silhouette (`k.mensah_07` → `a.aaaaaa_99`) and truncates at 40 characters, because a full-length
silhouette of a high-entropy string is itself close to an identifier.
`test_no_finding_carries_the_text_it_matched` scans the canary and asserts that every planted
value is absent from the serialised findings.

Two existing project guards are reused rather than reimplemented, per the standing rule:

* `src/dashboard/view.py::assert_no_forbidden_language` is called inside `Finding.__post_init__`,
  `ScannerResult.__post_init__` **and** over the fully rendered report — so a finding or a
  coverage sentence using forbidden wording cannot be constructed, let alone published. The
  `PROVISIONAL_STAMP`'s own literal denial remains quotable and is pinned by a test.
* `src/explainability/cards.py::assert_publication_safe` remains the mechanism for card
  rendering. Nothing here duplicates it; this module never handles cards.

---

## 6. The mechanism justified itself on its first run

`run_sweep`'s refusal-to-report fired on the very first execution, before it had scanned
anything: `credential_assignment` did not match the canary. The pattern opened with
`\b(api[_-]?key|…)`, and the field name in this repository is `OPENROUTER_API_KEY` — `\bAPI_KEY`
never matches it, because the preceding underscore is a word character.

Had the canary check not existed, that sweep would have returned **zero credential findings over
251 files and been reported as a clean result.** It would have been correct about six patterns
and blind to the one that matters most in a repository whose only real secret is an OpenRouter
key. The leading `\b` is gone and a comment above the pattern says why.

This is the same shape as Phase 9b (the obvious fix that did nothing), Phase 17 (a guard
bypassable through a different field), Phase 18 (a gate certifying a claim its evidence
contradicted) and Phase 20 (two charts sharing an SVG id). What is new is only *where* it hid:
in the detector itself, which is the last place a security review looks, because the detector is
what everything else is trusted through.

---

## 7. A note on how this audit was run

Reached through the Cowork desktop folder bridge, git cannot unlink its own lock files, so
`git status` **prints a warning and returns no output**. Read casually, an empty `git status` is
"the working tree is clean" — which would have been a false clean result inside an audit about
false clean results. Every git query in §4 was re-run against a copied index
(`GIT_INDEX_FILE=/tmp/gidx`), which needs no lock. This is recorded as SEC-09 so the next session
does not read an empty `git status` here as evidence.

---

## 8. Owner actions, in order

SEC-01 and SEC-02 are already fixed and the gate passes without these steps. They remain worth
running: the first closes SEC-03, which the fix above deliberately did not.

```powershell
cd C:\Users\saika\sports-risk-nlp
if (Test-Path .git\index.lock) { Remove-Item .git\index.lock }

# 0. Confirm the gate for yourself before trusting this document.
python -m pytest tests/test_security.py -q                  # EXPECT: 49 passed
python scripts/run_security_audit.py --online --out reports/security_audit.md
echo $LASTEXITCODE                                          # EXPECT: 0

# 1. SEC-03: regenerate the baseline inside the container, where the gate runs.
#    This is a re-SCAN, which the Phase 21 fix deliberately was not.
docker compose run --rm app detect-secrets scan > .secrets.baseline
docker compose run --rm app detect-secrets audit .secrets.baseline   # any hit: NOT a secret
python -m pytest tests/test_security.py -q                  # EXPECT: still 49 passed
#    If the audit step offers anything that is NOT a training_fingerprint hash,
#    STOP and read it. That is a new finding, not a formality.

# 2. SEC-08: move the donation inbox out of the repository.
Move-Item donations_inbox.jsonl ..\sports-risk-nlp-private\donations_inbox.jsonl

# 3. Commit.
git add src/security/ scripts/run_security_audit.py tests/test_security.py `
        docs/security.md reports/security_audit.md .secrets.baseline `
        .pre-commit-config.yaml CLAUDE.md .claude.md docs/related_work.md `
        handover_phase_21.txt PROJECT_PLAN.md
git commit -m "feat(phase21): security, dependency and PII audit with proven-detector gate"
git log --oneline -1     # VERIFY IT LANDED. Do not trust that the command was issued.
git push
```

SEC-04, SEC-05 and SEC-07 are handed to **Phase 22**, where anonymised-artifact preparation and
version pinning are already tasks. SEC-06 is re-checked at **Phase 25**.
