"""Phase 18 -- the evaluation harness that produces the paper's numbers.

Scoring is separated from *predicting*, and that separation is the whole design.

A prediction is expensive and needs the ML stack: loading a fine-tuned
distilroberta and running it over a held-out split costs minutes and a torch
install. A score is arithmetic over label sets and costs milliseconds. Phase 18
recomputes scores constantly -- every ablation, every re-slice of the error
analysis, every figure regenerated after a wording change -- and if each of those
had to re-run the model, three things would follow, all bad: ablations would take
hours instead of seconds, the test suite would need torch, and two runs of the
"same" number could differ because the model was reloaded in between.

So the model runs **once**, into a `PredictionSet` on disk (`--cache-predictions`
in `scripts/run_evaluation.py`), and everything downstream in this module is pure
Python over that cache. This mirrors how `src/risk/` (Phase 15) and everything in
`src/explainability/` except `attribution.py` (Phase 17) were built, for the same
reason: the invariants below are *tested*, not merely asserted, because the tests
run in an environment with no ML stack at all.

WHAT THESE NUMBERS ARE
----------------------
`data/gold/` is empty (OPEN-025). **Nothing this module computes is an accuracy.**
Every score is agreement with `generation_spec.planted_constructs` -- labels this
project's own generator planted -- so it measures how learnable the template
grammar `synth_precomp_v1` is, and nothing about athlete psychology. The
`PredictionSet.label_source` field carries that provenance into every artifact,
and `assert_not_accuracy` refuses to let a report be written without it.

NO VERBATIM CORPUS TEXT
-----------------------
`docs/ethics.md` binds the project to publish no verbatim corpus text in the
paper, dashboard or figures. Error analysis is therefore keyed on `record_id`
and on *structural* features (how many constructs a record carries, which length
band it falls in) rather than on example sentences. That is a real cost -- a
qualitative error table is more persuasive than a structural one -- and it is
paid deliberately. `ErrorProfile` carries no text field for the same reason
`ExplanationCard` cannot be built without provenance: an invariant enforced by
the shape of the data structure survives a future session that has forgotten why.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.evaluation.metrics import (
    PRF,
    Interval,
    bootstrap_ci,
    macro_f1,
    micro_f1,
    paired_bootstrap_p_value,
    per_label_prf,
    subset_accuracy,
)
from src.models.dataset import CONSTRUCTS

LabelSet = frozenset[str]

#: Stamped onto every artifact. See the module docstring.
PROVISIONAL_STAMP = (
    "PROVISIONAL -- planted-label corpus-property measurement, NOT accuracy. "
    "data/gold/ is empty (OPEN-025); no real athlete text exists (OPEN-011)."
)

#: Label sources that could, in principle, support an accuracy claim. Exactly one
#: entry, and the corpus does not have it yet. The list exists so that the day
#: `data/gold/` is populated, the change needed here is one line and it is
#: obvious where it goes.
ACCURACY_CAPABLE_SOURCES: frozenset[str] = frozenset({"gold"})


class MisalignedPredictions(ValueError):
    """Two prediction sets that cannot be compared were compared anyway.

    A distinct type because the failure it guards is silent otherwise: paired
    tests on misaligned records produce a plausible p-value computed against
    the wrong pairing, and nothing in the output looks wrong.
    """


# ---------------------------------------------------------------------------
# The cache
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PredictionSet:
    """One system's predictions on one split, plus the evidence to read them.

    `record_ids`, `y_true` and `y_pred` are positionally aligned and the same
    length; checked on construction rather than trusted, exactly as
    `models.dataset.Dataset` does, and for the same reason -- a silent
    misalignment yields a plausible macro-F1 scored against shuffled truth.

    `y_prob` is optional because not every system has probabilities. The lexicon
    baseline emits label sets and nothing else; the transformer emits both. Code
    that needs probabilities (risk fusion, calibration) must check rather than
    assume, so the field is `None` rather than a fabricated 0/1 matrix -- a
    fabricated probability is indistinguishable from a confident one downstream.
    """

    system: str
    split: str
    label_source: str
    constructs: tuple[str, ...]
    record_ids: tuple[str, ...]
    y_true: tuple[LabelSet, ...]
    y_pred: tuple[LabelSet, ...]
    y_prob: tuple[tuple[float, ...], ...] | None = None
    thresholds: dict[str, float] = field(default_factory=dict)
    provenance: str = PROVISIONAL_STAMP

    def __post_init__(self) -> None:
        n = len(self.record_ids)
        if not (len(self.y_true) == len(self.y_pred) == n):
            raise ValueError(
                f"{self.system}/{self.split}: {n} record_ids, {len(self.y_true)} truths, "
                f"{len(self.y_pred)} predictions; these must be positionally aligned"
            )
        if self.y_prob is not None:
            if len(self.y_prob) != n:
                raise ValueError(
                    f"{self.system}/{self.split}: {len(self.y_prob)} probability rows for "
                    f"{n} records"
                )
            width = len(self.constructs)
            bad = [i for i, row in enumerate(self.y_prob) if len(row) != width]
            if bad:
                raise ValueError(
                    f"{self.system}/{self.split}: probability rows {bad[:3]} have the wrong "
                    f"width; expected {width} to match `constructs`"
                )
        if len(set(self.record_ids)) != n:
            raise ValueError(
                f"{self.system}/{self.split}: duplicate record_ids. A record appearing twice "
                "is weighted twice in every metric below."
            )

    def __len__(self) -> int:
        return len(self.record_ids)

    @property
    def is_accuracy_capable(self) -> bool:
        return self.label_source in ACCURACY_CAPABLE_SOURCES

    def probabilities_for(self, index: int) -> dict[str, float]:
        """Row `index` as a construct -> probability mapping.

        The shape `LinearRiskScorer.score` wants. Raises rather than returning an
        empty mapping when there are no probabilities: an empty mapping scores as
        risk 0.0, which is a number, which would be reported.
        """
        if self.y_prob is None:
            raise ValueError(
                f"system {self.system!r} has no probabilities; it emits label sets only"
            )
        return dict(zip(self.constructs, self.y_prob[index], strict=True))

    # -- persistence --------------------------------------------------------

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "split": self.split,
            "label_source": self.label_source,
            "constructs": list(self.constructs),
            "record_ids": list(self.record_ids),
            "y_true": [sorted(s) for s in self.y_true],
            "y_pred": [sorted(s) for s in self.y_pred],
            "y_prob": [list(row) for row in self.y_prob] if self.y_prob is not None else None,
            "thresholds": dict(self.thresholds),
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PredictionSet:
        prob = payload.get("y_prob")
        return cls(
            system=payload["system"],
            split=payload["split"],
            label_source=payload["label_source"],
            constructs=tuple(payload["constructs"]),
            record_ids=tuple(payload["record_ids"]),
            y_true=tuple(frozenset(s) for s in payload["y_true"]),
            y_pred=tuple(frozenset(s) for s in payload["y_pred"]),
            y_prob=tuple(tuple(float(v) for v in row) for row in prob) if prob else None,
            thresholds=dict(payload.get("thresholds") or {}),
            provenance=payload.get("provenance", PROVISIONAL_STAMP),
        )

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.split}__{self.system}.json"
        path.write_text(json.dumps(self.as_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path) -> PredictionSet:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_cache(directory: Path) -> dict[tuple[str, str], PredictionSet]:
    """Every cached prediction set under `directory`, keyed `(split, system)`."""
    out: dict[tuple[str, str], PredictionSet] = {}
    for path in sorted(directory.glob("*.json")):
        ps = PredictionSet.load(path)
        out[(ps.split, ps.system)] = ps
    return out


def assert_not_accuracy(sets: Sequence[PredictionSet]) -> None:
    """Refuse to proceed if a caller is about to report a planted-label score as accuracy.

    Today this can only pass one way: every label source in the repository is
    `planted`, so the function's job is to make sure the *stamp* is present. It
    stops being a formality on the day `data/gold/` is populated, which is
    precisely the day someone will copy a report template forward without
    revisiting its banner.
    """
    for ps in sets:
        if ps.is_accuracy_capable:
            continue
        if PROVISIONAL_STAMP.split(" -- ")[0] not in ps.provenance:
            raise ValueError(
                f"{ps.system}/{ps.split}: label_source is {ps.label_source!r}, which cannot "
                "support an accuracy claim, but the provenance stamp is missing. "
                "See src/evaluation/harness.py's module docstring."
            )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SystemScore:
    """Everything the results table needs for one system on one split."""

    system: str
    split: str
    n: int
    macro_f1: Interval
    micro_f1: Interval
    subset_accuracy: float
    per_construct: dict[str, PRF]
    label_source: str

    @property
    def constructs_at_zero(self) -> tuple[str, ...]:
        """Constructs this system never gets right.

        Reported separately from macro-F1 because they are the difference
        between "the model is mediocre everywhere" and "the model is good at
        seven constructs and blind to three", which are different papers.
        """
        return tuple(name for name, prf in sorted(self.per_construct.items()) if prf.f1 == 0.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "split": self.split,
            "n": self.n,
            "label_source": self.label_source,
            "macro_f1": {
                "point": self.macro_f1.point,
                "low": self.macro_f1.low,
                "high": self.macro_f1.high,
            },
            "micro_f1": {
                "point": self.micro_f1.point,
                "low": self.micro_f1.low,
                "high": self.micro_f1.high,
            },
            "subset_accuracy": self.subset_accuracy,
            "constructs_at_zero": list(self.constructs_at_zero),
            "per_construct": {
                name: {
                    "precision": prf.precision,
                    "recall": prf.recall,
                    "f1": prf.f1,
                    "support": prf.support,
                }
                for name, prf in sorted(self.per_construct.items())
            },
            "is_accuracy": False,
        }


def score_predictions(
    ps: PredictionSet,
    *,
    n_resamples: int = 1000,
    seed: int = 42,
    labels: Sequence[str] = CONSTRUCTS,
) -> SystemScore:
    """Score one cached prediction set. Pure arithmetic; no model is loaded."""
    return SystemScore(
        system=ps.system,
        split=ps.split,
        n=len(ps),
        macro_f1=bootstrap_ci(
            ps.y_true,
            ps.y_pred,
            lambda t, p: macro_f1(t, p, labels),
            n_resamples=n_resamples,
            seed=seed,
        ),
        micro_f1=bootstrap_ci(
            ps.y_true,
            ps.y_pred,
            lambda t, p: micro_f1(t, p, labels),
            n_resamples=n_resamples,
            seed=seed,
        ),
        subset_accuracy=subset_accuracy(ps.y_true, ps.y_pred),
        per_construct=per_label_prf(ps.y_true, ps.y_pred, labels),
        label_source=ps.label_source,
    )


@dataclass(frozen=True)
class Comparison:
    """ "Does A beat B?", answered with a paired test rather than by eye."""

    system_a: str
    system_b: str
    split: str
    metric: str
    score_a: float
    score_b: float
    delta: float
    p_value: float
    alpha: float = 0.05

    @property
    def significant(self) -> bool:
        return self.p_value < self.alpha

    @property
    def verdict(self) -> str:
        if self.delta > 0 and self.significant:
            return "A beats B"
        if self.delta < 0 and self.significant:
            return "B beats A"
        return "no separation"

    def as_dict(self) -> dict[str, Any]:
        return {
            "system_a": self.system_a,
            "system_b": self.system_b,
            "split": self.split,
            "metric": self.metric,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "delta": self.delta,
            "p_value": self.p_value,
            "alpha": self.alpha,
            "significant": self.significant,
            "verdict": self.verdict,
        }


def compare_systems(
    a: PredictionSet,
    b: PredictionSet,
    *,
    metric_name: str = "macro_f1",
    n_resamples: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
    labels: Sequence[str] = CONSTRUCTS,
) -> Comparison:
    """Paired bootstrap comparison of two systems on the same split.

    Alignment is verified, not assumed. Two prediction sets can share a split
    name, a length and a record ordering that differ -- for instance if one was
    cached before a re-run changed the split seed -- and the paired test would
    silently pair record 17's truth with record 17's prediction from a different
    partition. That produces a p-value, and the p-value would be reported.
    """
    if a.split != b.split:
        raise MisalignedPredictions(
            f"cannot pair {a.system} on {a.split!r} with {b.system} on {b.split!r}"
        )
    if a.record_ids != b.record_ids:
        raise MisalignedPredictions(
            f"{a.system} and {b.system} are both on {a.split!r} but their record orderings "
            "differ; re-cache both from the same split before comparing"
        )

    metric = (
        (lambda t, p: macro_f1(t, p, labels))
        if metric_name == "macro_f1"
        else (lambda t, p: micro_f1(t, p, labels))
    )
    score_a, score_b = metric(a.y_true, a.y_pred), metric(b.y_true, b.y_pred)
    return Comparison(
        system_a=a.system,
        system_b=b.system,
        split=a.split,
        metric=metric_name,
        score_a=score_a,
        score_b=score_b,
        delta=score_a - score_b,
        p_value=paired_bootstrap_p_value(
            a.y_true, a.y_pred, b.y_pred, metric, n_resamples=n_resamples, seed=seed
        ),
        alpha=alpha,
    )


# ---------------------------------------------------------------------------
# Error analysis -- structural, never verbatim
# ---------------------------------------------------------------------------

#: Boundaries for the "how many constructs does this record carry" bands. Records
#: carrying nothing are their own band because they are ~38% of the corpus and a
#: model that over-predicts on them fails in a different way than one that
#: under-predicts on multi-construct records.
LOAD_BANDS: tuple[tuple[str, int, int], ...] = (
    ("0 constructs", 0, 0),
    ("1 construct", 1, 1),
    ("2 constructs", 2, 2),
    ("3+ constructs", 3, 99),
)


@dataclass(frozen=True)
class ErrorProfile:
    """Where a system's errors live. Carries record ids and counts; no text.

    See the module docstring on why there is no example-sentence field.
    """

    system: str
    split: str
    false_positives: dict[str, int]
    false_negatives: dict[str, int]
    #: (true construct, construct predicted instead) -> count, over records where
    #: the system swapped one construct for another. The confusable pairs are the
    #: taxonomy's problem, not the model's, and Phase 12 wants to know about them.
    confusions: dict[tuple[str, str], int]
    #: Band label -> (n records, n records with at least one error).
    by_load_band: dict[str, tuple[int, int]]
    worst_record_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "split": self.split,
            "false_positives": dict(sorted(self.false_positives.items())),
            "false_negatives": dict(sorted(self.false_negatives.items())),
            "confusions": {
                f"{t}->{p}": n
                for (t, p), n in sorted(self.confusions.items(), key=lambda kv: -kv[1])
            },
            "by_load_band": {
                k: {"n": v[0], "n_with_error": v[1]} for k, v in self.by_load_band.items()
            },
            "worst_record_ids": list(self.worst_record_ids),
            "note": "Structural only. No verbatim corpus text, per docs/ethics.md.",
        }


def _band_for(n: int) -> str:
    for label, low, high in LOAD_BANDS:
        if low <= n <= high:
            return label
    return LOAD_BANDS[-1][0]


def error_profile(ps: PredictionSet, *, top_k: int = 10) -> ErrorProfile:
    """Break a system's errors down by construct, by confusion pair, and by load."""
    fp: dict[str, int] = {}
    fn: dict[str, int] = {}
    confusions: dict[tuple[str, str], int] = {}
    bands: dict[str, list[int]] = {label: [0, 0] for label, _, _ in LOAD_BANDS}
    ranked: list[tuple[int, str]] = []

    for record_id, truth, pred in zip(ps.record_ids, ps.y_true, ps.y_pred, strict=True):
        missed, spurious = truth - pred, pred - truth
        for label in spurious:
            fp[label] = fp.get(label, 0) + 1
        for label in missed:
            fn[label] = fn.get(label, 0) + 1
        # A swap only counts as a confusion when something was both missed and
        # invented on the same record. Counting every (missed, spurious) pair
        # across the corpus would manufacture confusions between constructs that
        # never co-occurred on a single record.
        for true_label in sorted(missed):
            for pred_label in sorted(spurious):
                key = (true_label, pred_label)
                confusions[key] = confusions.get(key, 0) + 1

        band = _band_for(len(truth))
        bands[band][0] += 1
        n_errors = len(missed) + len(spurious)
        if n_errors:
            bands[band][1] += 1
        ranked.append((n_errors, record_id))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ErrorProfile(
        system=ps.system,
        split=ps.split,
        false_positives=fp,
        false_negatives=fn,
        confusions=confusions,
        by_load_band={k: (v[0], v[1]) for k, v in bands.items()},
        worst_record_ids=tuple(rid for n, rid in ranked[:top_k] if n > 0),
    )
