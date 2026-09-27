# Docker runbook

Closes **OPEN-001** (Phase 2 verification checks 7 and 8). Written 2026-08-09.

This document does two things: it explains *why* the container layout is split in
two, and it gives you the exact commands to get checks 7 and 8 to pass on Windows.

---

## 1. Why two images

The original `Dockerfile` ran `pip install -r requirements.txt`, and that manifest
included `torch>=2.2`. That looks harmless. It is not.

On Linux, the default PyPI wheel for `torch` is the **CUDA** build. Installing it
pulls roughly 2.5 GB of torch itself plus a set of `nvidia-*` CUDA runtime
libraries - cuDNN, cuBLAS, NCCL and friends - that together push the image past
**6 GB**. A container with no GPU never loads a single one of them. The build
would have taken 30–60 minutes on a laptop and could plausibly have failed on
disk space or a network timeout.

So check 7 was never merely blocked by the daemon being down. It was also sitting
on a real defect that had never been exercised.

The fix is to layer:

| Image | Built from | Contains | Size (approx) | Needed from |
|---|---|---|---|---|
| `sports-risk-nlp-base` | `Dockerfile` | CrewAI, OpenRouter client, pandas, scikit-learn, Streamlit, dev tools | ~700 MB–1.2 GB | Phase 6 |
| `sports-risk-nlp-train` | `Dockerfile.train` | base **+** CPU-only torch, transformers, datasets, shap, wandb | ~2.5 GB | Phase 13 |

`Dockerfile.train` installs torch with
`--extra-index-url https://download.pytorch.org/whl/cpu`, which is what your
Windows venv already does correctly - it has `torch==2.13.0+cpu`.

The `train` service sits behind a Compose **profile**, so a plain
`docker compose build` does not touch the heavy stack. You will not pay the
multi-GB cost until you actually need to fine-tune a model.

**Jargon, once:** a *Compose profile* is a label on a service. Services with a
profile are skipped by default and only included when you pass
`--profile <name>`. It is how you keep an expensive optional service in the same
file without it running every time.

---

## 2. Getting the daemon up (Windows)

Run these in PowerShell, in order. Stop at the first one that misbehaves.

### 2.1 Start Docker Desktop

```powershell
# Launch it (adjust the path if you installed elsewhere)
Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

Then **wait**. Docker Desktop takes 30–90 seconds to bring up its Linux VM. The
whale icon in the system tray stops animating and the tooltip reads
"Docker Desktop is running". Do not run the next command until it does - a
half-started daemon produces the same "cannot find the file specified" error and
sends you chasing a problem you do not have.

### 2.2 Confirm the daemon is actually answering

```powershell
docker info --format '{{.ServerVersion}}'
```

Expected: a version string such as `27.3.1`. This is the real test - `docker
--version` only proves the *CLI* exists and will happily succeed with the daemon
dead, which is exactly why Phase 2 check 2 passed while checks 7 and 8 failed.

### 2.3 If it will not start

```powershell
wsl --status          # Docker Desktop's Linux backend runs on WSL 2
wsl --update          # fixes the most common failure by itself
wsl --shutdown        # then restart Docker Desktop
```

If WSL itself will not install, virtualization is probably off in firmware.
Check: Task Manager → Performance → CPU → the "Virtualization" line should read
**Enabled**. If it reads Disabled you need to turn on Intel VT-x / AMD-V in the
BIOS/UEFI. Nothing in software can work around that.

---

## 3. Build and verify

```powershell
cd C:\Users\x\sports-risk-nlp
.\.venv\Scripts\Activate.ps1
```

### 3.1 Check 7 - container build

```powershell
docker compose build app
```

First build takes 5–12 minutes, mostly `pip install`. Rebuilds after a code
change take seconds, because the `COPY requirements-base.txt` step sits *above*
the `COPY . .` step and Docker caches layers in order - editing `src/` no longer
invalidates the dependency layer.

### 3.2 Check 8 - container hello-world

```powershell
docker compose run --rm app python scripts/hello.py
```

Expected output ends with `environment OK (with warnings)`. **The warnings are
correct and expected** on the light image: `scripts/hello.py` treats `torch` and
`transformers` as *optional* imports, and they are deliberately absent here.
Absence of the heavy stack in the light image is the design, not a failure.

### 3.3 One-shot re-verification

```powershell
.\scripts\verify_docker.ps1
```

Runs both checks plus the daemon probe and an offline crew run, and prints a
single PASS/FAIL summary. Use this rather than re-running the whole
`verify_env.ps1` while you are iterating on Docker.

### 3.4 Full Phase 2 gate

```powershell
.\scripts\verify_env.ps1
```

Expect **10/10**. That closes OPEN-001.

---

## 4. Everyday commands

```powershell
# Interactive shell in the light image
docker compose run --rm app bash

# Phase 6 smoke crew, offline (no API key, no spend)
docker compose run --rm agents

# Phase 6 smoke crew, live against OpenRouter (requires OPENROUTER_API_KEY in .env)
docker compose run --rm agents python scripts/run_crew.py --live

# Dashboard at http://localhost:8501
docker compose up dashboard

# Heavy training image - build the base FIRST, it is the parent layer
docker compose build app
docker compose --profile train build train
docker compose --profile train run --rm train python scripts/hello.py

# Reclaim disk after experimenting
docker system df
docker system prune -f
```

---

## 5. Things that will bite you

**`.env` is optional, deliberately.** Both services declare
`env_file: [{path: .env, required: false}]`. Without `required: false`, Compose
aborts before creating the container if `.env` is missing - and `.env` is
gitignored, so a fresh clone has none. This is a common way for a repo to be
"reproducible" everywhere except on a reviewer's machine.

**`.env` never enters the image.** It is in `.dockerignore`, so `COPY . .` skips
it. Secrets reach the container at *runtime* through `env_file`, not baked into a
layer. This matters: image layers are readable by anyone who pulls the image, and
a secret committed into a layer survives even if a later layer deletes the file.

**Build the base before the train image.** `Dockerfile.train` begins
`FROM sports-risk-nlp-base:latest`. If that tag does not exist locally, Docker
will try to pull it from a registry and fail with a confusing "not found".

**The bind mount shadows `COPY . .`.** In development, `volumes: - .:/app`
mounts your working tree over `/app`, so the copied code is hidden and your live
edits take effect without rebuilding. The `COPY` still matters - it is what makes
the image standalone for the Phase 24 reproducible artifact, where there is no
bind mount.

**The container runs as non-root** (`appuser`, UID 1000). On Docker Desktop for
Windows, file ownership across the bind mount is virtualised, so this causes no
permission friction. On native Linux it can; if you hit it there, `chown` the
repo to UID 1000 or add `user: root` to the service.
