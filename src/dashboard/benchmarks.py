"""The two committed benchmark numbers, read once from `reports/results.json`.

Why a module and not a constant
-------------------------------
The figures on this page (0.462 lexicon floor, 0.588 transformer, 0.822 on the
random split) are pinned rows in `src/evaluation/ablations.py::CLAIMS`. Typing
them into a caption would create a fourth copy that nothing keeps in step: the
ledger, `reports/results.json`, the paper, and the dashboard would drift, and
the dashboard would be the one nobody re-checks. So they are read from the same
artefact the claim gate reads.

Nothing here computes a score. It loads two numbers and their intervals, and
refuses to load anything if the artefact says it is missing -- a chart drawn
from a default value would be a number with no provenance, which is the one
thing `ScoreSurface` exists to prevent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.dashboard.view import REPO_ROOT, assert_no_forbidden_language

RESULTS_PATH = REPO_ROOT / "reports" / "results.json"

SPLIT_PLAIN = (
    "Template-disjoint means the sentence patterns in the test set were never seen in "
    "training. It is the honest split: the random split lets a model recognise a pattern "
    "it has already memorised."
)

GAP_PLAIN = (
    "The distance between the two transformer bars is the memorisation gap. It is a "
    "result of this project, not a defect being hidden: a model that scores far better "
    "on seen patterns than on unseen ones is partly recognising the generator, and the "
    "gap measures how much."
)


@dataclass(frozen=True)
class Benchmark:
    """One system's macro-F1 on one split, with its interval."""

    label: str
    split: str
    point: float
    low: float
    high: float
    note: str = ""


@dataclass(frozen=True)
class BenchmarkSet:
    rows: tuple[Benchmark, ...]
    delta: float
    caption: str


def _row(scores: dict, key: str, label: str, split: str, note: str) -> Benchmark:
    entry = scores[key]["macro_f1"]
    return Benchmark(
        label=label,
        split=split,
        point=float(entry["point"]),
        low=float(entry["low"]),
        high=float(entry["high"]),
        note=note,
    )


def load_benchmarks(path: Path | None = None) -> BenchmarkSet:
    """The three bars the benchmark chart draws, straight from the artefact."""
    data = json.loads((path or RESULTS_PATH).read_text(encoding="utf-8"))
    scores = data["scores"]
    rows = (
        _row(
            scores,
            "template_disjoint::lexicon",
            "Word-list floor",
            "unseen patterns",
            "the deliberate floor, and what the live tab runs",
        ),
        _row(
            scores,
            "template_disjoint::transformer",
            "Trained model",
            "unseen patterns",
            "the number the paper reports",
        ),
        _row(
            scores,
            "random::transformer",
            "Trained model",
            "seen patterns",
            "inflated by memorisation -- shown so the gap is visible",
        ),
    )
    delta = rows[1].point - rows[0].point
    caption = (
        "Agreement with generator-planted labels, averaged evenly over all ten "
        "constructs. Higher is better; 0 to 1."
    )
    for text in (caption, SPLIT_PLAIN, GAP_PLAIN, *(r.note for r in rows)):
        assert_no_forbidden_language(text)
    return BenchmarkSet(rows=rows, delta=delta, caption=caption)


@dataclass(frozen=True)
class ConstructScore:
    """One construct's detection quality, model against the word-list floor."""

    construct: str
    f1: float
    precision: float
    recall: float
    support: int
    floor_f1: float

    @property
    def beats_floor(self) -> bool:
        return self.f1 > self.floor_f1


PER_CONSTRUCT_CAPTION = (
    "Per-construct agreement on unseen sentence patterns. The averaged figure above "
    "hides this spread: the taxonomy is not detected evenly, and the weakest constructs "
    "are the ones a reader should trust least on the page above."
)


def load_per_construct(path: Path | None = None) -> tuple[ConstructScore, ...]:
    """Ten rows, worst first, from the same artefact the claim gate reads.

    Worst first on purpose. Sorting best-first would put the chart's most
    flattering row where the eye lands, and this chart exists precisely to show
    that a macro average of 0.588 contains constructs well below it.
    """
    data = json.loads((path or RESULTS_PATH).read_text(encoding="utf-8"))
    model = data["scores"]["template_disjoint::transformer"]["per_construct"]
    floor = data["scores"]["template_disjoint::lexicon"]["per_construct"]
    rows = [
        ConstructScore(
            construct=name,
            f1=float(entry["f1"]),
            precision=float(entry["precision"]),
            recall=float(entry["recall"]),
            support=int(entry["support"]),
            floor_f1=float(floor.get(name, {}).get("f1", 0.0)),
        )
        for name, entry in model.items()
    ]
    rows.sort(key=lambda r: r.f1)
    assert_no_forbidden_language(PER_CONSTRUCT_CAPTION)
    return tuple(rows)
