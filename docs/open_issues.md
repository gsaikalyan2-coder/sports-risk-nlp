# Open Issues Register

Running list of known-open items that are deliberately deferred rather than resolved.
Every entry names the phase that owns it and the phase where it becomes blocking.
Nothing should be closed here without evidence.

---

## OPEN-001 — Docker daemon not running; Phase 2 gate unmet

**Status: RESOLVED 2026-08-09.** Docker Desktop was started on the owner machine and
`.\scripts\verify_env.ps1` reported **checks 1–9 passing**, including check 7 (container
build) and check 8 (container hello-world) — the two that defined this issue. The only
remaining failure in that run was check 10, an unrelated detect-secrets false positive
(see OPEN-010, closed the same day).

**This was the first successful build the `Dockerfile` has ever had.** Both the daemon
problem and the CUDA-torch problem documented below had to be fixed before it could pass;
neither alone was sufficient.

**Owned by:** Phase 2 (dev environment & tooling)
**Was blocking at:** Phase 6 — resolved before it bit.

### Update 2026-08-09 — a second, independent defect was found and fixed

The daemon being down was never the only problem. `docker compose build` would also
have failed or crawled, for a reason that had nothing to do with Docker Desktop:

The old `Dockerfile` ran `pip install -r requirements.txt`, and that manifest contained
`torch>=2.2`. On Linux the default PyPI wheel for torch is the **CUDA** build — roughly
2.5 GB plus a stack of `nvidia-*` CUDA runtime libraries, none of which a CPU-only
container ever loads. Estimated result: a ~6 GB image and a 30–60 minute build, with a
real chance of failing on disk or a network timeout.

So check 7 had never been exercised against a real defect, exactly as the original
diagnosis warned ("those files have never been successfully built, so they remain
unverified"). That warning turned out to be the important sentence.

**Fixed this session:**

| Change | Why |
|---|---|
| Split into `Dockerfile` (light) + `Dockerfile.train` (heavy) | Phase 6–12 never pays the ML-stack cost |
| `requirements-base.txt` / `requirements-ml.txt` split | mirrors the image split |
| torch installed from the PyTorch **CPU** wheel index | ~200 MB instead of ~2.5 GB |
| `train` service behind a Compose `profile` | plain `docker compose build` skips it |
| shared `image:` name across app/agents/dashboard | compose builds once, not three times |
| `env_file: required: false` | a fresh clone with no `.env` no longer aborts |
| dependency layer copied above source | code edits stop invalidating the pip cache |
| non-root `appuser` | secrets and layers hygiene |
| `numpy<2.1` bound removed | it would have **downgraded** the owner's working numpy 2.4.6 |

**Verified in the Linux sandbox** (no Docker available there, so this is a proxy not a
substitute): `requirements-base.txt` resolves cleanly with no dependency conflicts —
the failure mode a build would most likely have hit after the torch fix.

**Still required from the owner** — the actual gate:

1. Start Docker Desktop, wait for the tray icon to read "Docker Desktop is running".
2. `docker info --format '{{.ServerVersion}}'` returns a version.
3. `.\scripts\verify_docker.ps1` — probes the daemon, then runs checks 7, 8 and an
   in-container crew run.
4. `.\scripts\verify_env.ps1` — expect 10/10 (now 11 checks; see `docs/docker.md`).

Full runbook including WSL and virtualization troubleshooting: **`docs/docker.md`**.

### Why this is now lower-risk than it was

Phase 6's gate — one orchestrated multi-agent run that logs cost — **passes outside
Docker**, via `python scripts/run_crew.py --offline`. Docker is no longer on the
critical path for Phase 6 itself. It remains required for the Phase 21 dashboard and
the Phase 24 reproducible artifact, which `CLAUDE.md` §9 makes a publication
requirement. So it must still be closed, but it is no longer blocking forward progress.

---

## OPEN-001-HISTORICAL — original Phase 2 diagnosis (retained for the record)

**Status:** superseded by the update above; kept because the reasoning is still correct.

### What failed

`.\scripts\verify_env.ps1` on Windows, 2 of 10 checks:

- `FAIL: 7. Container build`
- `FAIL: 8. Container hello-world`

Both with the same underlying error:

```
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine;
check if the path is correct and if the daemon is running:
open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.
```

### Diagnosis

Docker Desktop is not running. The Docker CLI is finding no daemon at the end of the
Windows named pipe. This is a **single root cause producing both failures** — it is not
two independent problems, and it is not evidence that the `Dockerfile` or
`docker-compose.yml` are wrong. Those files have never been successfully built, so they
remain **unverified**, which is a distinct open question from the daemon being down.

### Why it is safe to defer right now

`PROJECT_PLAN.md` Phase 5 is *Ethics, data governance & risk plan* — policy only, no code
and no containers. Phase 5 can be completed and gated with Docker down.

### Why it must NOT be deferred past Phase 6

Phase 6 stands up the CrewAI agent services via `docker-compose` and its gate requires one
orchestrated multi-agent run to complete. That cannot be reached without a working daemon.
Phase 6 is Week 2 work on an 8-week timeline.

Two later phases also depend on it: the Dockerized Streamlit dashboard (~Phase 21) and the
reproducible artifact required by `CLAUDE.md` §9 for publication readiness (~Phase 24).
A reproducible Docker artifact is part of the definition of "publication-ready", so this
is ultimately a paper requirement, not merely a convenience.

### Resolution steps (when picked up)

1. Start Docker Desktop; wait for the tray icon to read "Docker Desktop is running".
2. Verify the daemon: `docker info --format '{{.ServerVersion}}'` returns a version.
3. If it will not start, check WSL (`wsl --status`, then `wsl --update`) and confirm
   virtualization is enabled in BIOS (Task Manager -> Performance -> CPU -> Virtualization).
4. Re-run `.\scripts\verify_env.ps1`; expect all 10 checks to pass.
5. **Separately confirm the container definitions actually build** — a passing check 7 is
   the first real test the `Dockerfile` has had.

### Related

Checks 1-6, 9, and 10 pass. Notably check 9 (pre-commit hooks over the whole repo) passes
all hooks including `detect-secrets`, and check 10 confirms `.env` is untracked. Secret
hygiene is verified; only containerization is outstanding.

---

## OPEN-007 — CrewAI execution backend is written but never executed

**Status:** OPEN — new 2026-08-09
**Owned by:** Phase 6
**Becomes blocking at:** whenever the project needs CrewAI specifically, realistically
**Phase 10** (bulk weak labeling) if the crewai engine is chosen for it.

`src/agents/crewai_engine.py` maps the agent roster onto real `crewai.Agent` /
`crewai.Task` / `crewai.Crew` objects. It is written against **crewai 1.15.x**, the
version installed in the owner's venv. It has **never been run**, because every
execution path available in this session was offline and CrewAI's engine makes real
paid API calls by design.

The verified, default path is `--engine simple`: the built-in sequential orchestrator
in `src/agents/crew.py`, which is fully covered by tests and runs offline for free.

**Why this is acceptable rather than sloppy.** `CLAUDE.md` §10 confirms CrewAI as the
framework, so the integration belongs in the repo. But the Phase 6 gate — one
orchestrated run that logs cost — is satisfied by the simple engine, and a reviewer
reproducing the artifact should not need an API key. Isolating CrewAI in its own module
that nothing else imports means a CrewAI breaking change cannot take down the pipeline.
CrewAI already went 0.x → 1.x during this project's lifetime, so that is not a
hypothetical risk.

**Resolution:** run `python scripts/run_crew.py --engine crewai --live` once an
`OPENROUTER_API_KEY` is in `.env`. Expect to fix small API-surface details on first
contact. Budget roughly $0.01. Record the outcome here.

**Known limitation to decide on before Phase 10.** CrewAI calls the provider itself, so
our ledger cannot see individual calls and records one coarse summary row instead of
per-call rows. If per-record cost attribution matters for the paper's cost analysis —
and it probably does — prefer `--engine simple` for bulk labeling.

---

## OPEN-008 — No OpenRouter API key present

**Status:** OPEN — new 2026-08-09
**Owned by:** Phase 6
**Becomes blocking at:** **Phase 10** (bulk weak labeling). Does not block Phase 6–9.

`.env` currently contains only `YOUTUBE_API_KEY`. There is no `OPENROUTER_API_KEY`, so
no live model call has ever been made by this project.

Everything through Phase 9 works offline. Phase 10 cannot: weak labeling is the point at
which real model calls start, and it is the phase the entire silver dataset depends on.

**Resolution:** create a key at <https://openrouter.ai/keys>, add it to `.env` as
`OPENROUTER_API_KEY=...`, and confirm with
`python scripts/run_crew.py --live` (costs well under a cent). The budget guard in
`config/model_routing.yaml` caps spend at $20/month and refuses calls that would breach
it. `.env` is gitignored and excluded from Docker images; `detect-secrets` runs in
pre-commit.

**Sizing, so the cost is not a surprise:** a full 10,000-utterance labeling pass on the
cheap tier is estimated at about **$1.12**. The arithmetic is in
`config/model_routing.yaml`.

---

## OPEN-009 — Model IDs and prices drift without notice

**Status:** OPEN — monitoring in place
**Owned by:** Phase 6
**Becomes blocking at:** any large batch run, and at write-up time.

`config/model_routing.yaml` pins three OpenRouter models with prices read from the live
catalogue on 2026-08-09 and verified programmatically:

| Tier | Model | $/1M in | $/1M out |
|---|---|---|---|
| cheap | `openai/gpt-5.6-luna` | 0.10 | 0.60 |
| mid | `openai/gpt-5.6-terra` | 1.00 | 6.00 |
| premium | `anthropic/claude-sonnet-5` | 2.00 | 10.00 |

Both failure modes are silent. A retired model ID returns 404 and kills a labeling run
partway through, leaving a half-written silver dataset. A price change invalidates every
cost estimate in the ledger, and therefore the cost-aware-pipeline claim in the paper.

**Mitigation:** `python scripts/refresh_pricing.py --check` compares the config against
the live catalogue and exits non-zero on drift; `--write` updates prices in place (it
drops YAML comments, so review the diff). Run it before any large batch and before
quoting cost numbers in the write-up.

*Note:* an earlier draft of this config used `openai/gpt-4o-mini`,
`anthropic/claude-3.5-haiku` and `anthropic/claude-sonnet-4`. None of those three exist
in the current catalogue. They were caught by checking rather than by assuming, which is
precisely the failure this issue exists to prevent recurring.

---

## OPEN-010 — detect-secrets false positive on `api_key_env`

**Status: RESOLVED 2026-08-09.** Same day it was raised.

`pre-commit` check 10 failed on `config/model_routing.yaml:27`:

```
Secret Type: Secret Keyword
Location:    config\model_routing.yaml:27
```

The flagged line was the `api_key_env` field, whose value is the string
`OPENROUTER_API_KEY`. That value is the **name of an environment variable**, not a
credential. detect-secrets' "Secret Keyword" rule fires on an `api_key`-like field name
followed by a quoted string, and cannot distinguish a variable name from a key.

**A second-order trap, hit 2026-08-09:** the original wording of this very paragraph
reproduced the flagged line verbatim, field and quoted value together on one line. That is
the exact pattern the rule matches, so documenting the false positive *recreated* it in
`docs/open_issues.md` and failed pre-commit a second time. Rewritten to describe the field
and its value separately. If you ever need to quote a triggering line literally in prose,
append `# pragma: allowlist secret` to that line rather than reformulating it.

**Resolution:** inline `# pragma: allowlist secret` with a comment stating why it is a
false positive — the same mechanism already used for the deliberately fake key in
`docs/setup.md`. Verified afterwards that the pragma is parsed as a YAML comment and the
loaded value is still exactly `OPENROUTER_API_KEY`.

**Why the pragma was the right call and not a shortcut.** Silencing a secret detector is
normally a smell. It is justified here because the finding is structurally impossible to
be a real secret: the file is committed, the value is a variable name, and the actual key
only ever lives in `.env`, which is gitignored, excluded from Docker images via
`.dockerignore`, and confirmed untracked by check 11 in the same run. The narrow inline
pragma also leaves the detector fully armed for every other line in the file — a baseline
regeneration would have been the blunter, riskier fix.

---

## OPEN-011 — The corpus contains no real athlete text

**Status:** OPEN — new 2026-08-09, Phase 7
**Owned by:** Phase 7 (data strategy), realised in Phases 8–11
**Becomes blocking at:** **Phase 11** (gold standard). Does not block Phases 8–10.

The Phase 7 survey established that **no public corpus of pre-competition athlete text
exists** — every athlete-speech corpus located is post-match, which is the wrong side of
the event for an anticipatory taxonomy. Full reasoning and the rejected-candidate table:
`docs/data_sources.md` §1 and §4.

The owner chose **synthetic-first** on 2026-08-09 and declined, for now, the three routes
to real text (Cornell author permission, iMiGUE licence agreement, A3 consented donation).
So `data/raw/` is 100% synthetic.

**Why this is the most consequential open item in the register.** Contribution #1 in
`CLAUDE.md` §1 is "a construct-grounded athlete-text corpus … bridging the survey↔text
gap". A corpus containing no athlete text does not bridge that gap. Phase 11's gold set and
the inter-annotator agreement built on it are what make the contribution real, and both
currently have nothing real to annotate.

A reviewer will ask this question first. The honest answers available are, in descending
strength:

1. A small real gold set exists, drawn from a licensed source, and IAA is reported on it.
2. No real text was obtainable within the window; the contribution is reframed as a
   *method and schema* contribution with a synthetic proof-of-concept, and the absence is
   named as the principal limitation.

Option 2 is publishable but materially weaker, and it is the default if nothing changes.

**Resolution — any one of these closes it, and all three are the owner's to action:**

- **Cornell** — email Liye Fu / Cristian Danescu-Niculescu-Mizil / Lillian Lee asking for
  written permission to use the transcript dataset for research. One line back converts an
  unlicensed download into a recordable A1 basis. Post-match, so useful as contrastive
  data rather than as the core corpus.
- **iMiGUE-Speech** — contact Haoyu Chen (University of Oulu) to sign the licence
  agreement. Cleanest licence position of any candidate; base iMiGUE is identity-free.
- **A3 consented donation** — the only route that yields genuinely *pre-competition* text.
  A handful of adult athletes at SRMIST donating pre-event journal entries under written
  consent. Highest scientific value, longest lead time, and it pairs naturally with the
  **OPEN-004** expert-rater recruitment that is already overdue.

The A3 route is unblocked: `docs/ethics.md` §3.4 records the exemption determination and
`config/data_sources_allowlist.yaml` marks A3 `permitted`. Nothing but the consent form and
the asking stands in the way.

---

## OPEN-012 — Synthetic corpus vocabulary is too small to train a generalising model

**Status: SUBSTANTIALLY MITIGATED 2026-08-09, same day it was raised.** Downgraded from
blocking to monitored. Two things were done, and the second matters more than the first.

**1. Vocabulary raised (generator v1.1).** A construct-preserving lexical-variation layer
now runs after template rendering: near-synonym substitution plus discourse framing.

| Metric | v1.0 | v1.1 |
|---|---|---|
| Vocabulary (types) | 444 | **638** |
| Distinct texts | 81.3% | **96.9%** |
| MATTR-50 | — | **0.819** |

Raw TTR barely moved (0.0146 → 0.0159) and that is a property of the metric, not the
corpus: TTR's denominator grows without bound while its numerator saturates. **MATTR-50 and
vocabulary size are the honest figures** and both improved materially. `docs/data_sources.md`
§2.1 states this rather than quoting the flattering number.

**2. The real fix: template-disjoint evaluation.** Raising vocabulary reduces memorisation;
it does not prove the absence of it. `src/evaluation/splits.py` now partitions *templates*
before records, so a model is never tested on a phrasing it trained on.
`scripts/run_benchmark_audit.py` measures the effect:

| System | Random split | Template-disjoint | Drop |
|---|---|---|---|
| Memorisation probe (1-NN) | 0.732 | **0.198** | **+0.534** |
| Lexicon (leakage-immune) | 0.729 | 0.757 | −0.028 |

Templates on both sides: 85 → **0**. Verbatim test texts seen in train: 3.8% → **0.0%**.
8-gram overlap: 60.3% → 11.8%.

A pure memoriser loses **0.53 macro-F1** when templates are held out; a system that cannot
memorise is unchanged. That gap *is* OPEN-012, now quantified rather than feared — and
because a transformer memorises far more readily than 1-NN, 0.53 is a **lower bound** on the
inflation Phase 14 would otherwise have reported.

**What remains open, and why this is not closed.** The mitigation makes the metric honest;
it does not make the corpus real. A 638-word synthetic vocabulary still will not produce a
model that transfers to actual athlete speech — that requires **OPEN-011**. Two standing
obligations:

- Re-run `scripts/run_benchmark_audit.py` **after** the transformer exists. The probe's 0.53
  is a floor, and the transformer's own drop is the number the paper should report.
- Never quote a `random_split` number as a result. The function's docstring says it is a
  foil; `docs/data_sources.md` §2.2 lists the five binding consequences for Phases 13/14/18.

**Optional further work, no longer urgent:** an LLM paraphrase pass once **OPEN-008** is
closed would widen lexis further. `GeneratorStamp` already distinguishes generators so the
two passes cannot be confused.

---

## OPEN-012-HISTORICAL — original statement (retained for the record)

**Status:** superseded by the mitigation above; the reasoning still holds.
**Owned by:** Phase 7 (generator), realised at Phase 10
**Owned by:** Phase 7 (generator), realised at Phase 10
**Becomes blocking at:** **Phase 14** (transformer fine-tuning), and at any point a
held-out number is quoted as evidence of generalisation.

`synth_precomp_v1` measures **444 word types across 30,367 tokens**, type–token ratio
**0.0146**, with 976 distinct texts out of 1,200. That is the expected consequence of a
template grammar and it was chosen deliberately for reproducibility (`docs/data_sources.md`
§2.1), but it has a specific downstream failure mode worth stating before it happens.

A DeBERTa/RoBERTa classifier fine-tuned on this corpus will reach a very high held-out
macro-F1 by memorising template surface forms. That number would be **meaningless** as
evidence about athlete language, and quoting it in the paper without qualification would be
the single most damaging thing this project could do to its own credibility.

**Resolution options, in preference order:**

1. **LLM paraphrase pass** over the existing records once **OPEN-008** is closed —
   preserves the construct/intensity structure while widening lexis. Cheap on the
   cheap tier; `GeneratorStamp` already distinguishes generators so the two passes never
   get confused. This is the recommended Phase 8/10 follow-on.
2. **Expand the template bank** in `src/ingestion/synthetic.py` — free and deterministic,
   but effort scales linearly and the ceiling is still low.
3. **Accept it and report it** — state the TTR, and report held-out numbers on the *real*
   gold set only, never on synthetic held-out data.

Option 3 is mandatory regardless of whether 1 or 2 is done.

---

## OPEN-013 — De-identification cannot be validated against a corpus with no identifiers

**Status: FIXTURE DELIVERED 2026-08-09.** The measurement instrument now exists; the
measurement itself is Phase 8's job.

`tests/fixtures/deid_cases.jsonl` — **34 cases** with expected placeholder output, covering
every category in the `docs/ethics.md` §5.1 removal table: person names (including
nicknames, lowercase, hyphenated, and honorific forms), handles, contacts, URLs, teams and
sponsors, locations, events, exact dates, quasi-identifier combinations, and health detail
(removed entirely, not placeholdered). Spans easy/medium/hard difficulty bands.

**Eight of the 34 are negatives** — text that must come back *unchanged*. This is the half
that is usually forgotten. A de-identifier that redacts everything scores perfect recall and
destroys the corpus, and `docs/ethics.md` §5.2 requires typed placeholders precisely because
blanking "destroys the linguistic structure the model needs". The negatives include "**Mark**
my words" (common given name used as a verb), "The **Final** is on **Sunday** and my
**Coach**" (capitalised common nouns with no proper name), "47 seconds" (a performance
figure, contrasted against jersey number 47 in the positive set), and "**Two days out**"
(relative timing, which is contribution #3 and must survive).

Every name in the fixture is invented. 12 tests enforce the fixture's own integrity —
unique IDs, required fields, positives that change, negatives that do not, health cases that
delete rather than placeholder, timing preserved, and that none of it has leaked into
`data/raw/`.

**Still Phase 8's obligation, and the gate should be written this way:**

1. Report **recall, precision, and exact-match**, not recall alone.
2. Report **per difficulty band**. An aggregate hides that easy passes and hard fails.
3. Treat the fixture measurement as the real gate. "Spot-check shows no identifiers remain"
   against the synthetic corpus is true and worthless — that corpus never had any.
4. Do not tune until it overfits 34 cases. It is a smoke test with teeth, not a benchmark,
   and `docs/ethics.md` §5.3 already names residual re-identification risk as a limitation.
5. Re-measure against real text when **OPEN-011** resolves, and report both numbers.

---

## OPEN-013-HISTORICAL — original statement (retained for the record)

**Status:** superseded by the fixture above.
**Owned by:** Phase 8 (preprocessing & de-identification)
**Owned by:** Phase 8 (preprocessing & de-identification)
**Becomes blocking at:** **Phase 8's own gate** ("spot-check sample shows no direct
identifiers remain").

`src/ingestion/synthetic.py` deliberately emits **no personal names**, real or invented —
inventing names risks colliding with real people, and the corpus needs no identifiers. A
test enforces this.

The consequence is that Phase 8's `deidentify.py` will be run against text containing
essentially nothing to remove, and will trivially pass its own gate while telling us
**nothing about its recall**. `docs/ethics.md` §5.3 already names automated
de-identification as imperfect and highest-risk for A4 press text — precisely the text this
corpus does not contain.

**Why it matters beyond tidiness.** "Spot-check shows no identifiers remain" is a claim the
paper will make. Made against a corpus that never had identifiers, it is true and
worthless.

**Resolution:**

- Build a small **held-out de-identification test fixture** in Phase 8: a few dozen
  synthetic utterances deliberately seeded with names, handles, teams, venues, and event
  names, with the expected placeholder output recorded. That gives `deidentify.py` a real
  recall measurement without needing real athlete data, and it is cheap.
- Keep it in `tests/fixtures/`, **not** in `data/raw/` — it is a test artefact, not corpus.
- When real text arrives (**OPEN-011**), re-measure against it and report both numbers.

---

## OPEN-002 — Misconfigured plugin hook fires on every file write

**Status:** OPEN — cosmetic
**Owned by:** local tooling, not the project

The `pixeltable` plugin registers a `PostToolUse` hook pointing at
`hooks/validate_antipatterns.py`, which does not exist on disk. It errors on every file
write. It has blocked nothing and has not corrupted any file, but it adds noise to every
session. Remove or repair the plugin's hook configuration.

---

## OPEN-003 — No off-machine backup of the repository

**Status:** OPEN — accepted risk
**Owned by:** Phase 1

Per the documented Phase 1 deviation, the previous codebase was permanently deleted at the
owner's instruction and no `legacy-backup` branch was created. Only `main` exists and there
is no remote. Every artifact produced so far — the Phase 3 citation sweep, the Phase 4
taxonomy and rubric — exists in exactly one place on one machine.

Pushing to a private remote would close this in a few minutes.

---

## OPEN-004 — Expert-rater recruitment not started

**Status:** OPEN — schedule risk
**Owned by:** Phase 17, but `PROJECT_PLAN.md` risk #4 says recruitment starts Week 1-2

The expert-validation study needs at least one coach or sport-psych practitioner. This is
the headline differentiator of the paper — the Phase 3 review found that sports XAI
explanations are almost never validated with practitioners, and filling that gap is
contribution #2. It is also the item with the longest lead time and the least control,
since it depends on someone else's calendar.

Documented fallback if no rater is secured: a self-audit, named explicitly as a limitation.
That fallback materially weakens the contribution, so it should be a last resort.

---

## OPEN-005 — Ethics-review exemption not yet in writing

**Status:** OPEN — favourable determination, documentary record missing
**Owned by:** Phase 5 (ethics & data governance)
**Becomes blocking at:** **paper submission** (1st week of September 2026). Does **not** block
Phase 7 ingestion.

The owner reports that SRMIST determined this project **exempt** from institutional ethics
review, as secondary analysis of public/licensed/consented/synthetic text with no primary
human-subjects collection. Recorded in `docs/ethics.md` §3.4 on 2026-08-08. On the strength of
that, A3 and A4 collection are unblocked.

What is missing is the *documentary* form of the determination — an email, a letter, or a
committee reference number naming the determining body and the date.

**Why this stays open even though the answer was favourable.** An exemption is a claim about
process, and reviewers and ethics editors ask for its provenance. "The author states the work was
exempt" is materially weaker than "exempt per SRMIST, determination dated X, reference Y". The gap
is only closable before submission, and it is cheapest to close now while the conversation is
fresh — one email — rather than in September against a deadline.

**Resolution:** obtain the written determination; save as `docs/ethics_review_exemption.*`, or if
it carries personal contact details, record only the reference number in `docs/ethics.md` §3.4 and
keep the document out of the repo. Cite it in the paper's Ethics section.

---

## OPEN-006 — Withdrawal/incident contact route is a personal address

**Status:** OPEN — interim route live, institutional route required
**Owned by:** Phase 5 (ethics & data governance)
**Becomes blocking at:** **any public release** — corpus, code, or paper (~Phase 24/25).
Does **not** block Phase 7 ingestion.

`docs/ethics.md` §7.1 nominates `gsaikalyan2@gmail.com` (prefix `[SPORTS-RISK-NLP]`, 7-day
acknowledgement) as the route for withdrawal, correction, and incident reports. That is adequate
for a project with nothing released yet.

It is not adequate on a published artefact, for two reasons. **Accountability:** the project's only
accountability mechanism should be traceable to the institution that determined it exempt, not to
one individual's private webmail. **Continuity:** an A3 donor may withdraw consent two years after
publication, and the route has to still work — past the owner's graduation.

**Resolution:** before release, update §7.1 to an **SRMIST institutional address** as primary plus
a **named supervisor or lab contact** as secondary, then propagate to `README.md`,
`docs/model_card.md`, and the A3 consent form.

*Note:* no institutional address or supervisor name has been invented as a placeholder. A
plausible-looking address that does not resolve would produce a withdrawal route that silently
fails, which is worse than an honest interim one.

---

## Change log

| Date | Change |
|---|---|
| 2026-08-08 | Register created at end of Phase 4. OPEN-001 through OPEN-004 logged. |
| 2026-08-08 | Phase 5 owner decisions resolved. OPEN-005 (exemption not in writing) and OPEN-006 (personal contact address) logged as the two residuals. Neither blocks Phase 7. |
| 2026-08-09 | Phase 6. OPEN-001 updated: a second defect (CUDA torch in the image) found and fixed; container definitions split and hardened. OPEN-007 (CrewAI backend unexecuted), OPEN-008 (no OpenRouter key), OPEN-009 (model/price drift) logged. |
| 2026-08-09 | **OPEN-001 RESOLVED** — Docker Desktop started; verify_env checks 1–9 pass including container build and container hello-world. First successful build of the `Dockerfile`. OPEN-010 (detect-secrets false positive) raised and resolved the same day. |
| 2026-08-09 | Phase 7 follow-up. OPEN-012 **substantially mitigated** (generator v1.1 lexical variation: vocab 444->638, distinct texts 81%->97%; plus template-disjoint splitting in `src/evaluation/`, memorisation probe drops 0.732->0.198). OPEN-013 **fixture delivered** (34 cases, 8 negatives). Allow-list and ethics.md version headers corrected to 1.1. |
| 2026-08-09 | Phase 7. Source survey found **no public pre-competition athlete corpus**; owner chose synthetic-first. OPEN-011 (no real athlete text), OPEN-012 (synthetic vocabulary too small), OPEN-013 (de-identification unvalidatable against an identifier-free corpus) logged. OPEN-011 supersedes risk #1 in `PROJECT_PLAN.md` as the project's live highest risk. |
