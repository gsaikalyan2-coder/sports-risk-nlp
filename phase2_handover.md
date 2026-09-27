# Phase 2 Handover Instructions - Dev Environment & Tooling

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Handover to:** a new Claude Cowork chat executing **Phase 2**
**Predecessor doc:** `phase1_summary.md` · **Governing docs:** `.claude.md`, `PROJECT_PLAN.md`
**Prepared:** 2026-08-03

---

## 1. Phase 2 Goals & Success Criteria

**Goal:** Turn the committed scaffold into a **reproducible, verified development environment** so all
later phases run identically on the owner's machine and in Docker.

**Success criteria (all must be true):**
- `pip install -r requirements.txt` completes cleanly in a fresh Python 3.11 virtual environment.
- `pytest` passes (`tests/test_smoke.py`).
- `docker compose build` succeeds and a hello-world runs **both** locally and inside the container.
- Pre-commit hooks (formatter + secret scan) are installed and block a test secret.
- `.env` is confirmed **not** tracked by git; `.env.example` documents required keys.
- A short `docs/setup.md` records the exact setup steps.

---

## 2. Prerequisites, Environment & Access

| Requirement | Needed for | Status |
|---|---|---|
| Python 3.11 installed | venv + installs | [CONFIRM ON OWNER MACHINE] |
| Docker Desktop running | container build | [CONFIRM] |
| VS Code + Python & Docker extensions | primary IDE | [CONFIRM] |
| PyPI network access | `pip install` | Assumed available |
| Owner's OS | path/shell syntax | Windows (`C:\Users\x\sports-risk-nlp`) |
| OpenRouter key | **NOT** needed in Phase 2 (Phase 6) | Defer |

**Relevant tools this phase:** VS Code (primary) + Claude Code (fix env/Docker issues).
Google Colab, Supabase, and Stitch are **not** used in Phase 2.

---

## 3. Step-by-Step Execution Plan

> Work in the project root `C:\Users\x\sports-risk-nlp`. Do small, verifiable steps.

| Step | Task | Expected outcome | Acceptance criteria |
|---|---|---|---|
| 1 | Verify toolchain: `python --version`, `docker --version`, `git status` | Versions print; repo clean | Python is 3.11.x; Docker responds; git on commit `fb87925` |
| 2 | Create & activate venv: `python -m venv .venv` → `.venv\Scripts\activate` | Isolated env active | Prompt shows `(.venv)`; `.venv/` is gitignored |
| 3 | Install deps: `pip install -r requirements.txt` | All packages install | No errors; `pip check` clean (note torch download size) |
| 4 | Run tests: `pytest -q` | Smoke test passes | 1 passed |
| 5 | Local hello-world: `python -c "import torch, transformers, crewai; print('ok')"` | Core libs import | Prints `ok` with no ImportError |
| 6 | Build container: `docker compose build` | Image builds | Build succeeds |
| 7 | Container hello-world: `docker compose run --rm app python -c "print('container ready')"` | Runs in container | Prints `container ready` |
| 8 | Add pre-commit config (formatter = ruff, + a secret-scan hook); `pre-commit install` | Hooks active | A staged fake secret is blocked on commit |
| 9 | Verify secret hygiene: `git ls-files | findstr .env` returns nothing | `.env` untracked | Only `.env.example` is tracked |
| 10 | Write `docs/setup.md` with the exact commands used | Setup documented | A fresh clone can reproduce the env from it |
| 11 | Pin versions in `requirements.txt` to the resolved versions; commit | Reproducible pins | New commit; `docker compose build` still passes |

**If GPU/torch install is heavy or fails locally:** document the CPU-only fallback and note that
model training (Phase 14) will run on **Google Colab** instead - do not block Phase 2 on local GPU.

---

## 4. File & Reference Index

| The receiving chat will need | Path |
|---|---|
| Standing brief / rules | `.claude.md` |
| Full phase plan (Phase 2 = "Dev environment & tooling") | `PROJECT_PLAN.md` |
| What Phase 1 delivered | `phase1_summary.md` |
| Dependencies | `requirements.txt`, `pyproject.toml` |
| Container | `Dockerfile`, `docker-compose.yml` |
| Secrets template | `.env.example` (real `.env` is gitignored) |
| Test | `tests/test_smoke.py` |
| Config (do not break) | `config/{taxonomy,model_routing,settings}.yaml` |
| Where to record setup | `docs/setup.md` (to be created) |

---

## 5. Roles & Responsibilities of the Receiving Claude Chat

- **Execute** the Phase 2 steps above; produce runnable, verified increments.
- **Teach while doing** - explain each command's purpose (owner is a sophomore).
- **Report** each step's result and stop at the first failure with a diagnosis, not a guess.
- **Update** `.claude.md` / this doc if any tool decision changes (with owner confirmation).
- **Do not** start Phase 3+ work (no data ingestion, no modeling) - Phase 2 is environment only.

---

## 6. Definition of Done for Phase 2

- [ ] Fresh `.venv` installs `requirements.txt` cleanly.
- [ ] `pytest` passes.
- [ ] `docker compose build` succeeds; hello-world runs locally **and** in the container.
- [ ] Pre-commit hooks installed and proven to block a secret.
- [ ] `.env` confirmed untracked; `.env.example` accurate.
- [ ] `requirements.txt` version-pinned; changes committed.
- [ ] `docs/setup.md` written and reproducible.
- [ ] A single commit (or few) captures Phase 2; working tree clean.

---

## 7. Escalation Path for Blockers

1. **Try to self-diagnose** (read the error, check versions/paths) and report the finding.
2. **Environment quirks are expected, not blockers:** the `validate_antipatterns.py` hook error and
   git "unable to unlink … Operation not permitted" warnings are **harmless** - files/commits still
   succeed. Do not treat them as failures.
3. **Missing prerequisite** (no Python 3.11 / Docker not installed): pause and ask the owner to install;
   provide the exact download step. Do not work around it silently.
4. **Dependency conflict / heavy torch install:** switch to the documented CPU-only fallback and note
   Colab for GPU work; flag to owner.
5. **Anything requiring a new tool/library not in `.claude.md`:** stop and ask the owner before adding.
6. **Unresolved after a reasonable attempt:** summarize the blocker, what was tried, and options; hand
   back to the owner (Saikalyan).

---

## 8. Guardrails, Constraints & Best Practices

- **Never commit secrets.** Keys live only in `.env` (gitignored); use `.env.example` for placeholders.
- **Ask before locking any new tool/library/model** - confirmed decisions only (`.claude.md` §8).
- **Reproducibility first:** pin versions, keep the fixed seed (`config/settings.yaml`, seed 42),
  Dockerize. No "works on my machine."
- **Small, verifiable steps** with a check after each; end with a verification step.
- **Do not touch `data/gold/`** in any phase - human-owned.
- **Stay in scope:** Phase 2 = environment only; no pipeline logic, no data, no models.
- **Be concise and direct** in chat; put depth in files/docs (owner preference).
- **Keep the ethics framing intact** - research/decision-support, de-identification, non-diagnosis.
- **Back up:** once a GitHub remote is authorized, push after Phase 2 so work is off-machine.

---

## 9. Known Placeholders to Resolve

- [CONFIRM Python 3.11 installed on owner's machine]
- [CONFIRM Docker Desktop installed and running]
- [VERIFY contents of the pre-existing `.env` file and rotate the key if needed]
- [CHOOSE the secret-scan pre-commit hook - e.g. `detect-secrets` or `gitleaks`]
