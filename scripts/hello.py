"""Phase 2 hello-world / environment self-check.

Purpose: prove the same command runs identically on the host venv and inside
the Docker container. Run with:

    python scripts/hello.py            # host (inside .venv)
    docker compose run --rm app python scripts/hello.py

It prints the Python version, whether the repo's config files parse, and
whether the heavy ML libraries import. It exits non-zero if a *required*
check fails, so it can be used as a gate in CI later.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES = ["taxonomy.yaml", "model_routing.yaml", "settings.yaml"]
# Optional heavy deps: absent in a minimal/CPU-only install is a warning, not a failure.
OPTIONAL_IMPORTS = ["torch", "transformers", "crewai", "sklearn", "streamlit"]

failures: list[str] = []
warnings: list[str] = []


def check_python() -> None:
    major, minor = sys.version_info[:2]
    print(f"Python      : {platform.python_version()} ({platform.system()})")
    if (major, minor) != (3, 11):
        warnings.append(f"expected Python 3.11, found {major}.{minor}")


def check_configs() -> None:
    try:
        import yaml
    except ImportError:
        failures.append("pyyaml not installed (run: pip install -r requirements.txt)")
        return
    for name in CONFIG_FILES:
        path = REPO_ROOT / "config" / name
        if not path.exists():
            failures.append(f"missing config/{name}")
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            failures.append(f"config/{name} is not valid YAML: {exc}")
            continue
        keys = len(data) if isinstance(data, dict) else 0
        print(f"config/{name:<20}: OK ({keys} top-level keys)")


def check_imports() -> None:
    import importlib

    for module in OPTIONAL_IMPORTS:
        try:
            importlib.import_module(module)
            print(f"import {module:<14}: OK")
        except ImportError:
            warnings.append(f"optional import failed: {module}")


def main() -> int:
    print("=== sports-risk-nlp environment check ===")
    check_python()
    check_configs()
    check_imports()

    for warning in warnings:
        print(f"WARN  {warning}")
    for failure in failures:
        print(f"FAIL  {failure}")

    if failures:
        print("\nenvironment check FAILED")
        return 1
    print(
        "\nsports-risk-nlp container ready" if not warnings else "\nenvironment OK (with warnings)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
