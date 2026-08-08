# Open Issues Register

Running list of known-open items that are deliberately deferred rather than resolved.
Every entry names the phase that owns it and the phase where it becomes blocking.
Nothing should be closed here without evidence.

---

## OPEN-001 — Docker daemon not running; Phase 2 gate unmet

**Status:** OPEN — deferred by owner decision, 2026-08-08
**Owned by:** Phase 2 (dev environment & tooling)
**Becomes blocking at:** **Phase 6** (docker-compose agent services)

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
