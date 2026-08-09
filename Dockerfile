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
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal. git is needed by some pip installs from VCS refs;
# build-essential is needed to compile the few sdists in the agent tree.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependency layer first, so editing source code does not invalidate the pip
# cache layer. This is the single biggest build-time saving on rebuilds.
COPY requirements-base.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements-base.txt

# Run as a non-root user. The container bind-mounts the repo in development, so
# the UID is chosen to be a common Linux default; on Docker Desktop for Windows
# file ownership is virtualised and this is not a concern.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --chown=appuser:appuser . .

# Default: prove the image works. Overridden per service in docker-compose.yml.
CMD ["python", "scripts/hello.py"]
