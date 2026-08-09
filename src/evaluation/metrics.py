"""Multi-label metrics and bootstrap confidence intervals.

Pure Python, no numpy or scikit-learn. Two reasons: this module must import in
the light Docker image (`requirements-base.txt`, which has no ML stack), and a
metric the project implements itself is a metric the project can be held to.
Roughly 60 lines of arithmetic is a cheaper dependency than sklearn here.

**A point number without an interval is not a result.** With a held-out set of a
few hundred records, the difference between macro-F1 0.71 and 0.74 is usually
noise, and reporting the point estimate alone invites a claim the data does not
support. `bootstrap_ci` is therefore not optional decoration -- Phase 18 should
report an interval next to every headline number.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

#: One prediction: the set of construct labels assigned to a record.
LabelSet = frozenset[str]


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float
    support: int

    def as_row(self) -> str:
        return f"P={self.precision:.3f} R={self.recall:.3f} F1={self.f1:.3f} n={self.support}"


def _prf(tp: int, fp: int, fn: int, support: int) -> PRF:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return PRF(precision, recall, f1, support)


def per_label_prf(
    y_true: Sequence[LabelSet],
    y_pred: Sequence[LabelSet],
    labels: Sequence[str],
) -> dict[str, PRF]:
    """Precision, recall, and F1 for each label independently."""
    if len(y_true) != len(y_pred):
        raise ValueError(f"length mismatch: {len(y_true)} true vs {len(y_pred)} predicted")
    out: dict[str, PRF] = {}
    for label in labels:
        tp = fp = fn = support = 0
        for truth, pred in zip(y_true, y_pred, strict=True):
            in_true, in_pred = label in truth, label in pred
            support += in_true
            if in_true and in_pred:
                tp += 1
            elif in_pred:
                fp += 1
            elif in_true:
                fn += 1
        out[label] = _prf(tp, fp, fn, support)
    return out


def macro_f1(
    y_true: Sequence[LabelSet],
    y_pred: Sequence[LabelSet],
    labels: Sequence[str],
) -> float:
    """Unweighted mean of per-label F1.

    Macro rather than micro is the primary metric (`config/settings.yaml`)
    because the rare constructs matter as much as the common ones -- a model
    that never predicts `burnout_signal` should be penalised for it, and micro
    averaging would let the frequent labels hide that.
    """
    scores = per_label_prf(y_true, y_pred, labels)
    if not scores:
        return 0.0
    return sum(s.f1 for s in scores.values()) / len(scores)


def micro_f1(
    y_true: Sequence[LabelSet],
    y_pred: Sequence[LabelSet],
    labels: Sequence[str],
) -> float:
    label_set = set(labels)
    tp = fp = fn = 0
    for truth, pred in zip(y_true, y_pred, strict=True):
        t, p = truth & label_set, pred & label_set
        tp += len(t & p)
        fp += len(p - t)
        fn += len(t - p)
    return _prf(tp, fp, fn, tp + fn).f1


def subset_accuracy(y_true: Sequence[LabelSet], y_pred: Sequence[LabelSet]) -> float:
    """Fraction of records whose label set is predicted exactly right."""
    if not y_true:
        return 0.0
    return sum(t == p for t, p in zip(y_true, y_pred, strict=True)) / len(y_true)


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    level: float = 0.95

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.low:.3f}, {self.high:.3f}]"

    @property
    def width(self) -> float:
        return self.high - self.low


def bootstrap_ci(
    y_true: Sequence[LabelSet],
    y_pred: Sequence[LabelSet],
    metric: Callable[[Sequence[LabelSet], Sequence[LabelSet]], float],
    *,
    n_resamples: int = 1000,
    level: float = 0.95,
    seed: int = 42,
) -> Interval:
    """Percentile bootstrap CI for any of the metrics above.

    Resamples records with replacement `n_resamples` times and takes the
    empirical percentiles. Seeded, so the interval is reproducible.

    Caveat worth stating in the paper rather than hiding: the bootstrap
    quantifies **sampling variability of the test set**, and nothing else. It
    does not capture template leakage, annotation error, or domain shift from
    synthetic to real text. A tight interval on a leaky split is a precise
    measurement of the wrong quantity.
    """
    if not y_true:
        return Interval(0.0, 0.0, 0.0, level)
    rng = random.Random(seed)
    n = len(y_true)
    point = metric(y_true, y_pred)

    scores: list[float] = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        scores.append(metric([y_true[i] for i in idx], [y_pred[i] for i in idx]))
    scores.sort()

    tail = (1.0 - level) / 2.0
    low = scores[max(0, int(tail * n_resamples))]
    high = scores[min(n_resamples - 1, int((1.0 - tail) * n_resamples))]
    return Interval(point, low, high, level)


def paired_bootstrap_p_value(
    y_true: Sequence[LabelSet],
    y_pred_a: Sequence[LabelSet],
    y_pred_b: Sequence[LabelSet],
    metric: Callable[[Sequence[LabelSet], Sequence[LabelSet]], float],
    *,
    n_resamples: int = 1000,
    seed: int = 42,
) -> float:
    """Two-sided paired bootstrap p-value for "does A beat B?".

    The right test for "the transformer beats the baseline" (Phase 14's gate)
    and for every Phase 18 ablation. Paired, because both systems are scored on
    the *same* resampled records -- an unpaired test throws away the pairing and
    is needlessly conservative.

    A gate that reads "transformer > baseline on macro-F1" is not actually met
    by 0.74 vs 0.73 unless this says the gap survives resampling.
    """
    rng = random.Random(seed)
    n = len(y_true)
    if n == 0:
        return 1.0
    observed = metric(y_true, y_pred_a) - metric(y_true, y_pred_b)

    at_least_as_extreme = 0
    for _ in range(n_resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        t = [y_true[i] for i in idx]
        delta = metric(t, [y_pred_a[i] for i in idx]) - metric(t, [y_pred_b[i] for i in idx])
        # Centre on the observed difference: the null is "no difference".
        if abs(delta - observed) >= abs(observed):
            at_least_as_extreme += 1
    return at_least_as_extreme / n_resamples
