"""Phase 2 smoke tests.

Deliberately dependency-light: these must pass before the heavy ML stack is
installed, so a broken torch/CUDA install never hides a broken repo. Real
model/pipeline tests arrive from Phase 7 onward.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES = ["taxonomy.yaml", "model_routing.yaml", "settings.yaml"]
EXPECTED_DIRS = [
    "config",
    "data/raw",
    "data/interim",
    "data/processed/silver",
    "data/gold",
    "docs",
    "logs",
    "paper",
    "reports",
    "src",
    "tests",
]


def test_python_version_is_311():
    assert sys.version_info[:2] == (3, 11), (
        f"project targets Python 3.11, running {sys.version_info[:2]}"
    )


@pytest.mark.parametrize("name", CONFIG_FILES)
def test_config_yaml_parses(name: str):
    path = REPO_ROOT / "config" / name
    assert path.exists(), f"missing config/{name}"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data, f"config/{name} parsed empty"


@pytest.mark.parametrize("rel", EXPECTED_DIRS)
def test_scaffold_dir_exists(rel: str):
    assert (REPO_ROOT / rel).is_dir(), f"missing directory {rel}"


def test_src_packages_importable():
    sys.path.insert(0, str(REPO_ROOT))
    import importlib

    for pkg in [
        "src.ingestion",
        "src.preprocessing",
        "src.taxonomy",
        "src.labeling",
        "src.models",
        "src.risk",
        "src.explainability",
        "src.evaluation",
        "src.agents",
    ]:
        importlib.import_module(pkg)


def test_env_file_is_not_tracked():
    """Guardrail: .env must never be committed. .env.example must be."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert (REPO_ROOT / ".env.example").exists()
