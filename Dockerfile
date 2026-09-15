# Light runtime image: agents (CrewAI + OpenRouter), config/taxonomy layer,
# classical baselines, dashboard shell, dev toolchain.
#
# Deliberately does NOT contain torch/transformers. See Dockerfile.train for the
# training image and docs/docker.md for the reasoning and the build commands.
#
# Build:  docker compose build app
# Run:    docker compose run --rm app python scripts/hello.py

FROM python:3.11-slim

# Fail fast, no .pyc clutter, unbuffered logs so container output streams live.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# PYTHONPATH is load-bearing, not decoration (Phase 22, 2026-08-24).
# `streamlit run dashboard/app.py` puts /app/dashboard on sys.path -- NOT /app --
# so `from src.dashboard import ...` raised ModuleNotFoundError and the dashboard
# service had never once started in a container. The suite did not catch it
# because tests/__init__.py makes pytest insert the repo root itself, so the
# tests and the container disagreed about what "importable" means. Phase 20's
# gate read "app runs in Docker" and was met with host screenshots.

WORKDIR /app

# System deps kept minimal. git is needed by some pip installs from VCS refs;
# build-essential is needed to compile the few sdists in the agent tree.
# tesseract-ocr is load-bearing for the Phase 27 photo path, and its absence is
# a SILENT feature loss rather than a crash: src/media/extract.py checks whether
# the engine runs, finds it does not, and selects the honest floor -- so the
# container starts, the uploader appears, and every photo is refused with "this
# build cannot read photos". Correct behaviour, and indistinguishable from the
# feature being broken. The language pack is separate from the engine and is
# equally required; an engine with no eng.traineddata fails at the point of use.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        tesseract-ocr \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first, so editing source code does not invalidate the pip
# cache layer. This is the single biggest build-time saving on rebuilds.
#
# Installs the LOCK, not requirements-base.txt (SEC-07, fixed at Phase 22).
# requirements-base.txt carries twelve version FLOORS, and a floor is not a
# version: `crewai>=1.15,<2.0` resolves to a different answer on every build, so
# this image used to match no auditable file in the repository while the
# reproducibility statement claimed otherwise. The lock resolves with zero
# unpinned extras -- verified 2026-08-24 with `pip install --dry-run`, which is
# the property that makes "pinned" true rather than aspirational.
COPY requirements-base.lock.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements-base.lock.txt

# Run as a non-root user. The container bind-mounts the repo in development, so
# the UID is chosen to be a common Linux default; on Docker Desktop for Windows
# file ownership is virtualised and this is not a concern.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser . .

# Default: prove the image works. Overridden per service in docker-compose.yml.
CMD ["python", "scripts/hello.py"]
