# Development Environment Setup (Phase 2)

Reproducible setup for **sports-risk-nlp** on Windows 11 + VS Code, and in Docker.
Target: Python **3.11**. Everything below assumes the repo root
`C:\Users\saika\sports-risk-nlp` and PowerShell.

> **Why two environments?** The local `.venv` is for fast day-to-day work in VS Code.
> The Docker image is the *reproducibility contract* — it is what a reviewer or a future
> you rebuilds to get identical results. Both must run the same hello-world.

---

## 0. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11.x | `python --version` |
| Git | any recent | `git --version` |
| Docker Desktop | running | `docker --version` |
| VS Code extensions | Python, Pylance, Ruff, Docker | Extensions pane |

If `python --version` is not 3.11.x, install Python 3.11 from python.org and use
`py -3.11` in place of `python` in step 1.

---

## 1. Virtual environment

A *virtual environment* is a private copy of Python for this project, so this project's
package versions can never clash with another project's.

```powershell
cd C:\Users\saika\sports-risk-nlp
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1      # prompt should now start with (.venv)
python -m pip install --upgrade pip
```

If PowerShell blocks the activate script:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` then retry.

`.venv/` is already in `.gitignore` — never commit it.

---

## 2. Install dependencies

```powershell
pip install -r requirements.txt
pip check
```

**CPU-only torch fallback.** `torch` is a ~2 GB download and the default wheel pulls CUDA.
This project does not need a local GPU (fine-tuning in Phase 14 runs on Google Colab), so
prefer the smaller CPU wheel:

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

If a dependency conflict appears (most likely `crewai` vs `openai`), record the exact
error before changing versions — do not silently loosen a pin.

---

## 3. Verify: tests + hello-world

```powershell
pytest                       # expect: all tests pass
python scripts\hello.py      # expect: Python 3.11, three configs OK, imports OK
```

`scripts/hello.py` is the environment self-check: it prints the Python version, parses the
three `config/*.yaml` files, and tries the heavy imports. Missing optional imports are
warnings; a bad Python version or unparseable config is a failure (non-zero exit).

---

## 4. Docker

```powershell
copy .env.example .env       # only if .env does not already exist
docker compose build
docker compose run --rm app python scripts/hello.py
```

Expected final line: `sports-risk-nlp container ready`.

Services in `docker-compose.yml`:

| Service | Purpose | Command |
|---|---|---|
| `app` | pipeline / scripts | `docker compose run --rm app <cmd>` |
| `dashboard` | Streamlit UI (Phase 21) | `docker compose up dashboard` → http://localhost:8501 |

`.dockerignore` keeps `.git/`, `.venv/`, `.env`, `data/`, and `models/` out of the image —
that keeps builds fast and guarantees no secret or raw athlete text is baked into a layer.

---

## 5. Pre-commit hooks (formatting + secret scanning)

Hooks run automatically on `git commit` and are the last line of defence against
committing an API key.

```powershell
pip install pre-commit detect-secrets
pre-commit install
pre-commit run --all-files      # first run downloads the hook environments
```

Configured in `.pre-commit-config.yaml`:

- **ruff** + **ruff-format** — lint and format Python (config in `pyproject.toml`).
- **detect-secrets** — scans the diff for high-entropy strings and known key formats,
  compared against the reviewed allow-list in `.secrets.baseline`.
- basic hygiene — trailing whitespace, end-of-file newline, YAML validity,
  merge-conflict markers, private keys, and a 5 MB file-size ceiling
  (datasets and model weights must never enter git history).

**Prove the secret hook works** (do this once — it is a Phase 2 gate):

```powershell
"OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef0123456789abcdef" | Out-File fake_secret.py
git add fake_secret.py
git commit -m "test: should be blocked"     # EXPECT: detect-secrets FAILS the commit
git reset HEAD fake_secret.py
del fake_secret.py
```

If a finding is a genuine false positive, re-baseline and audit it:

```powershell
detect-secrets scan --baseline .secrets.baseline
detect-secrets audit .secrets.baseline
```

---

## 6. Secret hygiene checklist

```powershell
git ls-files | Select-String "\.env$"     # MUST return nothing
```

- Real keys live only in `.env` (gitignored). `.env.example` holds placeholders only.
- If a key was ever pasted into a tracked file or a chat, **rotate it** — deleting the line
  does not remove it from git history.
- Never print an API key into a log, a notebook output, or `logs/cost_ledger.csv`.

---

## 7. Version pinning (reproducibility)

Two files, two jobs:

| File | Role | Edited by |
|---|---|---|
| `requirements.txt` | human-readable manifest, minimum versions | you |
| `requirements.lock.txt` | exact resolved versions of *everything* | generated |

After a successful install, freeze the lock file and commit it:

```powershell
pip freeze > requirements.lock.txt
git add requirements.lock.txt
git commit -m "chore: pin resolved dependency versions (Phase 2)"
```

To rebuild that exact environment later: `pip install -r requirements.lock.txt`.
Regenerate the lock file any time `requirements.txt` changes, and re-run
`docker compose build` to confirm the container still builds.

> The lock file is platform-specific (Windows/py3.11). If the container ever resolves
> different versions, note it in `docs/setup.md` rather than forcing one to match.

---

## 8. VS Code

`Ctrl+Shift+P` → *Python: Select Interpreter* → `.\.venv\Scripts\python.exe`.
Recommended extensions: Python, Pylance, Ruff (`charliermarsh.ruff`), Docker.
The Ruff extension reads `pyproject.toml`, so editor formatting matches the pre-commit hook.

---

## 9. Known environment quirks (harmless — do not treat as failures)

- A `validate_antipatterns.py` plugin hook with an unresolved `${CLAUDE_PLUGIN_ROOT}` prints a
  red error after file writes. Files still save. Fix in Settings → Capabilities.
- Git may warn `unable to unlink … Operation not permitted` on this folder. Commits succeed.
- Deleting host-origin files from an agent session needs an explicit file-delete grant.

---

## 10. Daily workflow

```powershell
cd C:\Users\saika\sports-risk-nlp
.\.venv\Scripts\Activate.ps1
pytest
# ...work...
git add -A && git commit -m "..."     # hooks run here
```
