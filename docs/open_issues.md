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

**Status: CLOSED 2026-08-09 (Phase 8).** The fixture was delivered at Phase 7 and the
measurement has now been made. All five obligations listed at the bottom of this entry were
met, and the numbers are in `docs/preprocessing.md` §3.

| Metric | Value |
|---|---|
| Precision | **100.0%** |
| Recall | **100.0%** |
| Exact match | **100.0%** (34/34) |
| Leak rate (the privacy number) | **0.0%** |
| Negatives preserved | **8/8** |

Reported per difficulty band (easy, medium, hard all 100% exact) and per category. A
**held-out 10-case generalisation probe**, never consulted while writing the rules, scores
10/10 exact — reported and deliberately **not** gated, because a probe that gates becomes a
second fixture the next person tunes against.

**One fixture case was corrected, and it should be recorded rather than glossed.** `name_01`
originally expected the bare role noun *"the coach"* to be replaced with `[COACH]`. That
contradicted `negative_04` in the same file — *"'my Coach' is a role, not an identity"* — and
contradicted `docs/ethics.md` §5.1, which lists person **names** for replacement, not role
nouns. The two cases could not both be satisfied, and `name_01` was the one that disagreed
with the policy. It was amended to expect `[ATHLETE] said the coach was happy with the
session.`; the implementation was **not** changed to chase it. The correction is recorded in
the case's own `notes` field so the file explains itself.

**A 100% score on 34 cases is not a strong claim, and the paper must not present it as one.**
Every case was written by this project; none of it is real athlete text (OPEN-011). The
number means the cascade handles the failure modes we thought to write down — not that it
handles the ones we did not. Re-measure when OPEN-011 resolves and report both numbers, with
the fixture score labelled as an **upper bound**. The seven stated limitations in
`docs/preprocessing.md` §5 are the honest counterweight to this number.

---

## OPEN-015 — Generator v1.1 lexical variation produced an ungrammatical substitution

**Status: CLOSED 2026-08-10 (Phase 9).** Option (a) was taken with the owner's approval. The
`("part", "portion", "corner", "piece")` group was deleted, generator bumped to **v1.2**, the
corpus regenerated at seed 42, and the Phase 7, Phase 8 and benchmark gates all re-run and
re-reported together. Occurrences of `corner of me`, `portion of me` and `piece of me` in the
regenerated corpus: **0, 0, 0**.

Regenerating moved the RNG stream, so every downstream count changed — 4,110 → **4,141**
utterances; memorisation probe 0.732/0.198 → **0.738/0.146**. Full before/after table in
`reports/eda.md` §0.

**One number in this entry was wrong and is corrected rather than deleted.** The
`src/ingestion/synthetic.py` comment written when the group was removed said `corner of me`
occurred in **11** records. The true v1.1 count is **9**, as this entry and
`phase8_handover.md` both said. Verified by reconstructing generator v1.1 from
`git show 6f9561a:src/ingestion/synthetic.py` and regenerating at seed 42; the other two
counts in that comment (10 and 14) are correct. The comment was fixed.

**The wider sweep was done, and it found that OPEN-015 was not an isolated defect. See
OPEN-016.**

**Original entry follows.**

**Owned by:** Phase 7 (synthetic generator), found at Phase 8
**Becomes blocking at:** never on its own — but it is a **corpus quality** defect, so it
belongs to **Phase 9** (EDA & quality profiling), which is the phase that exists to find
exactly this.

**How it was found:** by reading `reports/deid_audit_sample.md`, the manual audit sample Phase
8 generates. The very second entry read:

> *"To be fair, corner of me wants to attack it and part of me just wants to survive it."*

`corner of me` is not English. Generator v1.1's near-synonym substitution layer replaced
*part* with *corner* — a valid synonym in isolation ("a corner of the room"), invalid in the
idiom *part of me*.

**Prevalence: 9 of 1,200 records (0.8%).**

`phase8_handover.md` §B6b records that a first pass of the substitution layer produced
"fixating *about* the result", "I must *to* not mess this up", and "Sessions *has* been", and
that those groups were deleted with the reasoning recorded inline. This one survived the same
review, because the constraint applied was shared part-of-speech **and** argument structure —
and *part* → *corner* satisfies both. Idiom membership is a third constraint that was not
checked and cannot be checked from POS alone.

**Why it matters more than 0.8% suggests.** The corpus is the dataset contribution. A
reviewer who reads nine ungrammatical records will discount the whole generator, and the
paper claims the template grammar produces *plausible* pre-competition language. It also
pollutes the vocabulary statistics that OPEN-012 was mitigated against — some of the
444→638 vocabulary gain is noise of this kind, and nobody has measured how much.

**Resolution, owner's choice:**

- **(a)** Delete the `part`/`corner` group from the synonym bank, regenerate at seed 42, and
  re-run the Phase 7, Phase 8, and benchmark gates. Cheap; changes every downstream count
  (1,200 records / 4,110 utterances / the audit numbers) so all three must be re-reported
  together. *Recommended, and best done at the start of Phase 9 before EDA numbers are
  published.*
- **(b)** Leave it and disclose the rate in `docs/data_sources.md` as a known generator
  limitation.

**It was not fixed during Phase 8.** Regenerating the corpus mid-phase would have invalidated
the de-identification and pipeline numbers reported in the same session, and the corpus is a
Phase 7 artefact under owner decision, not a preprocessing detail.

**Wider action for Phase 9:** this was one substitution found by reading roughly twenty
records. A systematic sweep of the whole synonym bank against the corpus is EDA work, and
"junk" is already on the Phase 9 task list in `PROJECT_PLAN.md`.

---

## OPEN-016 — 15.8% of records still carry a broken or degraded synonym substitution

**Status: CLOSED 2026-08-10 (Phase 9).** Resolved by **option (c)**, the generation-time
guard, on the owner's instruction. Generator bumped to **v1.3**.

`_vary` now applies each candidate substitution, checks the result against the ruled-defective
signatures in the new `src/ingestion/substitution_verdicts.py`, and reverts it if it would
produce one. **Zero synonym groups were deleted.** Current corpus: **0 of 4,000 records
(0.0%)** carry a defect, down from 190 of 1,200 (15.8%).

**Both remedies were measured before choosing, at n=4,000 and seed 42:**

| | Synonym bank | Realised vocabulary | Defective records |
|---|---|---|---|
| v1.2, unguarded | 64 groups | 643 types | 630 (15.75%) |
| Option (a): delete the 34 implicated members | 57 groups | 594 types | 0 |
| **Option (c): guard — chosen** | **64, unchanged** | **625 types** | **0** |

Deleting costs 49 realised types; the guard costs 18. The guard is **not free** — a word whose
only frames in the bank were defective now never appears — but it keeps 31 more types than
deletion and removes nothing from the bank, so a future template using one of those words in a
good frame gets it back automatically. Deletion would not. This is why the vocabulary line in
`docs/data_sources.md` reads 636 → 625 rather than 636 → 594.

**The RNG stream deliberately does not depend on the verdict table.** A rejected substitution
consumes its random draw exactly as an accepted one does; there is no retry. Retrying until
something passed would make the corpus a function of the verdict table, and every future edit
to that table would silently reshuffle the whole corpus.

**The honest limit, which the paper must state.** The guard is only as good as its hand-ruled
table and cannot catch a defect class nobody has thought of. What it does is make the failure
mode **non-recurring**: the sweep is exhaustive over single substitutions, a test fails the
build on an unruled signature, and a second test asserts the corpus contains no ruled-defective
frame. A new defect class still needs a human to notice it once. It no longer needs a human to
notice it over and over.

**One structural detail worth recording**, because it was caught by a test rather than by
review. The three OPEN-015 signatures (`corner of me`, `piece of me`, `portion of me`) were
first added straight into `VERDICTS`, which broke `test_no_orphan_verdicts` — that test asserts
every verdict corresponds to a frame the audit can still produce, and the deleted group can
produce none of them. The invariant is correct. The two tables answer different questions, so
the guard entries moved to a separate `RETIRED_DEFECTS` tuple. The test was not weakened.

**Original entry follows.**

**Was:** OPEN — needs an owner decision; it is a trade-off, not a bug fix
**Owned by:** Phase 7 (synthetic generator), found at Phase 9
**Becomes blocking at:** **Phase 11.** An annotator asked to judge
*"my insides is in knots"* is being asked to judge text no athlete would produce, and the
kappa that results describes the generator's defects as much as the rubric's clarity.

**How it was found — and this part is the reusable finding.** OPEN-015 was found by a human
reading about twenty records. That is luck, and luck does not scale to 65 synonym groups.
`src/ingestion/synonym_audit.py` replaces it with an **exhaustive** enumeration of every
single-token substitution the generator can make — 221 filled template variants, **727
substitution events** — screened by six mechanical probes: idiom membership, indefinite
article agreement, number agreement, particle/argument structure, inflected form, and arity
(one word swapped for a phrase or the reverse). Every flagged signature carries a recorded
human verdict, and a test fails the build if any signature is unreviewed, so editing the
synonym bank or the template bank cannot silently introduce a new defect class.

**The finding.**

| Measure | Value |
|---|---|
| Substitution events enumerated (exhaustive over single substitutions) | 727 |
| Distinct signatures flagged | 127 |
| Ruled `broken` / `degraded` / `acceptable` | 53 / 6 / 68 |
| Distinct defective signatures **realised** in the v1.2 corpus | 55 |
| **Records containing ≥1 defect** | **190 / 1,200 (15.8%)** |
| Utterances containing ≥1 defect | 207 / 4,141 (5.0%) |

Removing the `part` group (OPEN-015) fixed 0.8% of records and left the other 15%. Examples,
all at seed 42 in the current v1.2 corpus:

> *"I can feel my heart pick up a bit when I **figure about** the first ball."*
> *"my **insides is** in knots and my fingers won't stop shaking"*
> *"we've got **a approach** for the first bell"*
> *"I'm **on edge I'll** let everyone down in this race"*
> *"I keep turning over what happens if I get the first half **badly**"*

**Why the original review could not have caught these.** The v1.1 bank was reviewed against
shared part-of-speech **and** shared argument structure. `think → figure` satisfies both and
still breaks, because *think about* is attested and *figure about* is not; that is a lexical
fact about English, not a property derivable from either constraint. Idiom membership is a
third constraint, arity a fourth, and article/number agreement a fifth and sixth. The general
lesson for the paper: **a generation-quality review that enumerates constraint classes will
always miss the class nobody thought of; enumerating the search space mechanically is a
guarantee.**

**Why it is not fixed in Phase 9.** The remedy is to delete or repair roughly fifteen more
synonym groups. That shrinks the vocabulary OPEN-012's mitigation rests on — the same 636
types that justify calling OPEN-012 "substantially mitigated" — and it regenerates the corpus
a second time, invalidating every number in `reports/eda.md`, `docs/preprocessing.md` and
`docs/data_sources.md`. **Corpus grammaticality versus lexical diversity is an owner
trade-off**, and it is the same reasoning under which Phase 8 declined to fix OPEN-015.

**Resolution, owner's choice:**

- **(a) Repair, don't delete.** Replace the offending groups with narrower ones that keep the
  type count — e.g. `("think", "reckon")` instead of `("think", "reckon", "figure",
  "suppose")` — and re-run the sweep until the defective-signature count is zero. Costs the
  most vocabulary at the margin but keeps the diversity claim honest. *Recommended.*
- **(b) Delete the offending groups outright.** Fastest; costs ~15 groups of vocabulary and
  weakens OPEN-012's mitigation.
- **(c) Make `_vary` context-aware** — refuse a substitution whose result matches a flagged
  signature. Reuses `synonym_audit.VERDICTS` as a live filter rather than an audit, so
  defects cannot be generated at all. Most robust, most work, and it makes the generator
  depend on a hand-curated verdict table.
- **(d) Disclose and leave.** Report 15.8% in the paper as a known generator limitation.
  Defensible only if the gold set is drawn to avoid defective records, which it currently is
  not.

**Do (a) or (c) together with OPEN-017's regeneration**, not separately. Both require a
regenerate-and-re-gate cycle, and doing them in one pass costs one re-report instead of two.

---

## OPEN-017 — The gold pool is too small for a per-construct kappa

**Status: CLOSED 2026-08-10 (Phase 9) against its stated criterion; the residual is now
OPEN-020.** Resolved by **option (a)**: `DEFAULT_COUNT` in `scripts/run_ingestion.py` raised
from 1,200 to **4,000**, corpus regenerated at seed 42, all four gates re-run.

| | Before (n=1,200) | **After (n=4,000)** |
|---|---|---|
| Utterances | 4,141 | **13,651** |
| Eligible gold pool | 235 | **559** |
| `gold_eval` drawn / target 400 | 235 | **400** |
| Constructs below the 40-positive floor | **7 / 10** | **0 / 10** |
| Thinnest construct (`resilience`) | 27 | **46** |

**But the correction this entry warned about did not go away, and it is now the binding
constraint.** The lexicon proxy still finds **153 of 400 (38.2%)** drawn items carrying no
construct cue, because that fraction is a property of *records* — a record is ~3.4 utterances
of which ~2 realise a construct — and multiplying records does not change the ratio. Corrected
at 0.62×, **7 of 10 constructs fall back below 40.**

Swept, correcting each draw by its own measured cue fraction:

| Records | Pool | Target | Drawn | Cue fraction | Corrected min | Below 40 |
|---|---|---|---|---|---|---|
| 1,200 | 235 | 400 | 235 | 0.59 | 10.0 | 10 / 10 |
| **4,000 (current)** | **559** | **400** | **400** | **0.62** | **28.4** | **7 / 10** |
| 4,000 | 559 | 559 | 559 | 0.61 | 32.3 | 3 / 10 |
| 6,000 | 694 | 500 | 500 | 0.61 | 34.2 | 4 / 10 |
| 8,000 | 838 | 400 | 400 | 0.59 | 28.2 | 7 / 10 |
| 8,000 | 838 | 600 | 600 | 0.59 | 37.8 | 2 / 10 |

Corrected coverage tracks **gold-set size**, not corpus size, and even 600 double-annotated
items (~10 hours per annotator) leaves two constructs short. **More records cannot fix this;
more templates can.** Continued as **OPEN-020**.

`TARGET_GOLD_EVAL` was left at 400 rather than raised to the full 559-item pool. That would
take the shortfall from 7 constructs to 3 at the cost of ~40% more annotation, which is the
owner's time budget, not a code decision. It is a one-constant change in
`src/evaluation/sampling.py` if wanted.

**Original entry follows.**

**Was:** OPEN — needs an owner decision on corpus size
**Owned by:** Phase 9, blocks Phase 11
**Becomes blocking at:** **Phase 11**, immediately and unavoidably.

**The measurement.** `src/evaluation/sampling.py` draws the gold set from a
construct-stratified held-out template partition (see `reports/eda.md` §7 for why the obvious
plan fails). At the current corpus size it yields:

| | Target | Drawn |
|---|---|---|
| `gold_eval` | 400 utterances | **235** |
| `gold_dev` | 100 utterances | 100 |
| Constructs meeting the 40-positive floor | 10 / 10 | **3 / 10** |

Short by: `appraisal_orientation`, `burnout_signal`, `coping_style`, `motivation_orientation`,
`perceived_stress`, `resilience`, `self_confidence`.

The binding constraint is **not** annotator time and **not** corpus size in utterances. Only
235 of 4,141 utterances survive the template partition and the deduplication: 3,649 are
excluded for straddling the partition or carrying no template, 251 as duplicates, 6 as junk.

**How much of an upper bound, estimated.** Running the Phase 7 lexicon baseline over the
drawn sample as a proxy detector, **97 of 235 `gold_eval` items (41.3%) contain no construct
cue of any kind** — the first drawn item is *"Kit arrived yesterday, so that's one thing
sorted."*, a logistics sentence selected because its *parent record* plants a construct. The
lexicon is crude and this is an estimate, not a measurement. But if it is even roughly right,
the per-construct counts should be read at about **0.6×** the table above, under which **no
construct meets the floor** — which strengthens this issue rather than changing its direction.
Those items are not waste (a gold set with no negatives cannot measure false positives), but
they are negatives and the coverage table counts them as positives.

**Those counts are an upper bound, not an estimate.** Phase 8 copies `generation_spec` from
the raw record onto every utterance cut from it, verbatim — verified, and asserted by a test.
A record averaging 3.45 utterances and planting 2 constructs therefore reports both constructs
on all 3.45 of them, including the neutral logistics sentence and the discourse suffix that
realise neither. The *true* count of gold utterances expressing each construct is lower than
the table above and will not be known until annotation. See OPEN-019.

**Measured remedy.** Corpus size was swept with the generator, seed, partition and draw held
fixed:

| Generated records | Utterances | Eligible gold pool | Drawn | Constructs below floor |
|---|---|---|---|---|
| 1,200 (current) | 4,141 | 235 | 235 | **7 of 10** |
| 2,400 | 8,214 | 408 | 400 | 1 of 10 |
| **4,000** | 13,651 | 599 | 400 | **0 of 10** |
| 8,000 | 27,367 | 933 | 400 | 0 of 10 |

**4,000 generated records is the minimum at which a 400-item gold set meets the floor for all
ten constructs**, and it is a lower bound for the reason above.

Note the sub-linear growth: 6.7× the corpus buys 4× the eligible pool, because deduplication
bites harder as the template grammar's ceiling of distinct utterances is approached. **More
records raise positives per template; only a larger template bank raises phrasing diversity,
and phrasing diversity is what a construct kappa generalises over.** With 7–12 templates per
construct, a 35% holdout leaves 2–4 phrasings per construct in the evaluation set. A kappa
computed on 3 phrasings is a kappa about those 3 phrasings.

**Resolution, owner's choice:**

- **(a) Regenerate at `--count 4000`.** One command, offline, deterministic, free. Changes
  every published number, so it must be bundled with a full re-gate and a re-report.
  *Recommended, and bundle it with OPEN-016.*
- **(b) Regenerate at 4,000 **and** expand the template bank to ~15 templates per construct.**
  The only option that raises phrasing diversity as well as count. Roughly a day of writing
  templates, and it is the one that most strengthens contribution #1.
- **(c) Accept the shortfall.** Report per-construct kappa with wide bootstrap intervals and
  say plainly that seven constructs are under-powered. Honest, and weak.
- **(d) Reduce the floor below 40.** Not recommended: the floor is already a working
  approximation, not a power calculation, and lowering it to fit the data is fitting the
  method to the result.

**Whichever is chosen, `reports/eda.md` and `tests/test_profile.py`'s three fixed-corpus
assertions become stale on regeneration — deliberately. Those tests exist to fail loudly so
the report cannot silently drift from the corpus.**

---

## OPEN-018 — 73.6% of utterances are exact duplicates of another utterance

**Status:** OPEN — **mitigated in the sampling plan**, root cause not fixed, and it **got
worse** at n=4,000 exactly as this entry predicted: **87.4%** (was 73.6%), 13,651 utterances
to 3,131 distinct texts. Record-level duplication is 7.2%. Multiplying records multiplies
repeats, because the template grammar has a ceiling of distinct utterances and the discourse
suffixes are not varied at all. Option (a) below is now the recommended one, bundled with
OPEN-020's template work.
**Owned by:** Phase 7 (generator) / Phase 8 (segmenter), found at Phase 9
**Becomes blocking at:** never on its own; it would have silently corrupted Phase 11's kappa
if the sampling plan had not been written to avoid it.

**The measurement.** At utterance level: 4,141 utterances, **1,528 distinct texts**, 3,046
utterances sharing text with another, exact duplicate rate **0.736 [0.723, 0.750]**. At
record level the same corpus is **5.0%** duplicated. So this is an artefact of segmentation,
not of generation, and it is invisible in every statistic Phase 7 published.

**Mechanism.** `DISCOURSE_SUFFIXES` and `NEUTRAL_SENTENCES` are appended as whole sentences
and are rendered **without** the near-synonym variation layer — `generate_records` applies
`_vary` to construct realisations only. Phase 8 then segments each into its own standalone
utterance. A bank of ~8 suffixes across 1,200 records produces the same string hundreds of
times: `"It is what it is."` 268 times, `"Anyway, that's the reality."` 266, `"That's the
honest version."` 265.

**Why it matters.** Two annotators agreeing on `"It is what it is."` 268 times is **one**
agreement counted 268 times. A gold set sampled without collapsing duplicates would report a
kappa inflated by repetition, and the inflation would be invisible in the kappa itself. It
also means the *effective* per-utterance corpus for any model is 1,528 strings, not 4,141 —
which changes what a training-set size of "4,141 utterances" means in the paper.

**Mitigation already in place.** `eligible_utterances` collapses exact and near-duplicates
(Jaccard ≥ 0.9) before drawing, and `test_the_gold_sample_contains_no_duplicate_text` asserts
the drawn sample is duplicate-free. That protects the kappa. It does not fix the corpus.

**Resolution, owner's choice:**

- **(a) Apply `_vary` to the discourse suffixes and neutral sentences too.** Cheap, and it
  raises real diversity. Interacts with OPEN-016 — more varied text is more substitution
  surface — so run the sweep afterwards.
- **(b) Attach discourse suffixes to the preceding sentence instead of letting the segmenter
  split them out.** Changes segmentation, which changes offsets, which contribution #2
  depends on. More invasive than it looks.
- **(c) Leave it and report both figures.** Quote "1,528 distinct utterances" alongside
  "4,141 utterances" everywhere. Requires no code change and no regeneration, and it is what
  `reports/eda.md` and `docs/data_sources.md` now do.

---

## OPEN-019 — `generation_spec` is replicated onto every utterance of a record

**Status:** OPEN — documentation and schema clarity, no data loss
**Owned by:** Phase 8, found at Phase 9
**Becomes blocking at:** never directly, but it is the most likely source of a wrong number
in the paper.

Phase 8 copies the parent record's `generation_spec` onto every utterance cut from it,
byte-identical (verified;
`tests/test_profile.py::test_generation_spec_is_identical_across_a_records_utterances`
asserts it). The consequence: a record averaging 3.45 utterances and planting 2 constructs
reports both constructs on all 3.45 utterances, including the neutral logistics sentence and
the discourse suffix that realise neither.

So **any per-utterance count derived from `generation_spec` is a per-record count multiplied
by ~3.45**, not a per-utterance quantity. It is not wrong to carry the field forward —
provenance requires it — but it is very easy to read as an utterance-level annotation,
because an interim record looks far more like training data than a raw one does.

`src/evaluation/profile.py::GeneratorMetadataProfile` documents this and every downstream
calculation uses `planted_construct_records`. OPEN-017's construct counts are an **upper
bound** for exactly this reason.

**Resolution:** no code change proposed. Two documentation actions:

1. State the replication in `docs/preprocessing.md` next to the schema, where a reader meets
   the field, not only in an evaluation module. *(Done at Phase 9.)*
2. If the generator is ever changed to record *which utterance* realises which construct, that
   is a genuine schema improvement — but it must be introduced as new metadata, not by
   narrowing `generation_spec`, or it starts looking exactly like the label it must never be.

---

## OPEN-013-SUPERSEDED — fixture delivery note (retained for the record)

**Status:** superseded by the closure above; retained because the design reasoning still
stands.

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
| 2026-08-09 | **Phase 8. OPEN-013 CLOSED** — de-identifier measured against the fixture: precision 100%, recall 100%, exact 100% (34/34), leak rate 0%, negatives 8/8, reported per difficulty band; held-out 10-case probe 10/10. Fixture case `name_01` corrected: it had required a bare role noun to be redacted, contradicting `negative_04` and `docs/ethics.md` §5.1; the implementation was not changed to chase it. Language-filter defect found and fixed by running the pipeline: unequal stopword profiles dropped 2 English records as Portuguese (`docs/preprocessing.md` §4.1). **OPEN-015 raised** — generator v1.1 substitution produced "corner of me" in 9/1,200 records; owned by Phase 9. |
| 2026-08-10 | **Phase 9 follow-up. OPEN-016 and OPEN-017 CLOSED.** OPEN-016 by generation-time guard (generator **v1.3**, `substitution_verdicts.py`): defective records **190/1,200 → 0/4,000**, zero synonym groups deleted, realised vocabulary 643 → 625 against 594 had the 34 implicated members been deleted instead. OPEN-017 by raising `DEFAULT_COUNT` 1,200 → **4,000**: gold_eval **235 → 400** items, constructs below the 40-positive floor **7/10 → 0/10**. All four gates re-run and PASSED; 251 tests. **OPEN-020 raised** — corrected for the 0.62 cue fraction, 7/10 constructs still fall short, and the sweep shows no corpus size fixes it; the remedy is ~15 templates per construct. **OPEN-018 worsened as predicted**: utterance duplication 73.6% → **87.4%**. |
| 2026-08-10 | **Phase 9. OPEN-015 CLOSED** — `("part","portion","corner","piece")` deleted, generator bumped to v1.2, corpus regenerated at seed 42, Phase 7 / Phase 8 / benchmark gates all re-run and PASSED. 4,110 → **4,141** utterances; memorisation probe 0.732/0.198 → 0.738/0.146. Four issues raised: **OPEN-016** (exhaustive synonym sweep — 727 substitution events, 127 flagged signatures, **15.8% of records still carry a broken/degraded substitution**; OPEN-015 was not isolated), **OPEN-017** (gold pool too small — 235 of a 400 target, 7/10 constructs below the 40-positive floor; 4,000 generated records measured as the minimum), **OPEN-018** (**73.6% utterance-level exact duplication**, a segmentation artefact invisible at record level; mitigated in the sampling plan), **OPEN-019** (`generation_spec` replicated onto every utterance). Three published numbers corrected: v1.1 vocabulary 638→**635**, distinct texts 1,163→**1,161**, `"corner of me"` 11→**9** in a code comment. Deliverables: `reports/eda.md`, 9 SVG figures, `notebooks/01_eda.ipynb`, `data/processed/gold_candidates/sampling_plan.json`. |

---

## OPEN-020 — The template bank is too small for a defensible per-construct kappa

**Status:** OPEN — the residual of OPEN-017, and the last corpus-side blocker on
contribution #1
**Owned by:** Phase 7 (generator), raised at Phase 9
**Becomes blocking at:** **Phase 11.**

**Two separate consequences of the same cause: 85 templates, 7–12 per construct.**

**1. Coverage.** A record realises ~2 constructs across ~3.4 utterances, so ~38% of any gold
sample carries no construct at all. Corrected for that, 7 of 10 constructs sit below the
40-positive floor even at 4,000 records — and the sweep in OPEN-017 shows no corpus size fixes
it, because the cue fraction is a per-record property. More construct realisations per record
raises it directly.

**2. Phrasing diversity, which matters more.** With 7–12 templates per construct, a 35%
holdout leaves **2–4 phrasings** in the evaluation set. A kappa computed on 3 phrasings is a
kappa about those 3 phrasings, not about the construct. Two annotators agreeing on *"I keep
turning over what happens if I get the first half wrong"* tells you they read the same
sentence the same way; it does not tell you the rubric distinguishes `cognitive_anxiety` from
`perceived_stress` in language they have not seen. **This is the weakest point in
contribution #1 and a reviewer will find it.**

**Target: ~15 templates per construct**, roughly doubling the bank. That takes the holdout to
5 phrasings per construct and raises the cue fraction, addressing both consequences at once.

**Cost:** roughly a day of writing realisations against `docs/annotation_guidelines.md` and
`config/taxonomy.yaml`. It is the single highest-value corpus action left, and unlike
OPEN-011 it is entirely within the owner's control.

**Do it together with OPEN-018's option (a)** — applying `_vary` to the discourse suffixes and
neutral sentences. Both are template-bank edits, both need one regenerate-and-re-gate cycle,
and both feed the same weakness.

**Sequencing note.** New templates create new substitution frames, so
`scripts/run_eda.py` will flag unruled signatures and the build will fail until each is ruled
in `substitution_verdicts.VERDICTS`. That is the ratchet working, not an obstacle — but budget
for it, and do not merge template work without re-running the sweep.
