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
from typing import TypeVar

#: Element type for the single-sample bootstrap. Phase 9 found this missing:
#: `bootstrap_statistic` was annotated `Sequence[T]` with no `T` in scope, which
#: `from __future__ import annotations` makes invisible at runtime -- the code
#: worked, and only ruff's F821 caught it. An annotation nobody can resolve is a
#: comment that looks like a type.
T = TypeVar("T")

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


def _percentile_interval(
    scores: list[float], point: float, level: float, n_resamples: int
) -> Interval:
    """Percentile bootstrap interval from an unsorted list of resample scores.

    Factored out so `bootstrap_ci` and `bootstrap_statistic` cannot drift apart
    in how they take percentiles -- two implementations of the same interval is
    two numbers that will one day disagree in a paper.
    """
    scores.sort()
    tail = (1.0 - level) / 2.0
    low = scores[max(0, int(tail * n_resamples))]
    high = scores[min(n_resamples - 1, int((1.0 - tail) * n_resamples))]
    return Interval(point, low, high, level)


def bootstrap_statistic(
    values: Sequence[T],
    statistic: Callable[[Sequence[T]], float],
    *,
    n_resamples: int = 1000,
    level: float = 0.95,
    seed: int = 42,
) -> Interval:
    """Percentile bootstrap CI for a statistic of a **single** sample.

    `bootstrap_ci` above resamples aligned (truth, prediction) pairs, which is
    the right shape for a model score and the wrong shape for a corpus
    statistic: "mean utterance length" and "duplicate rate" have no predictions
    to pair with. Rather than pass a sequence twice and ignore one copy -- which
    works, and which would quietly turn a typo into a silent wrong answer -- the
    single-sample case gets its own entry point sharing the same machinery, the
    same default seed, and the same percentile rule.

    Same caveat as `bootstrap_ci`, and it bites harder here: this quantifies
    sampling variability **within this corpus**. For `synth_precomp_v1` the
    corpus is a template grammar, so the interval describes variability across
    draws from that grammar. It says nothing whatever about athlete language.
    """
    n = len(values)
    if n == 0:
        return Interval(0.0, 0.0, 0.0, level)
    rng = random.Random(seed)
    point = statistic(values)
    scores = [statistic([values[rng.randrange(n)] for _ in range(n)]) for _ in range(n_resamples)]
    return _percentile_interval(scores, point, level, n_resamples)


def proportion_ci(
    flags: Sequence[bool],
    *,
    n_resamples: int = 1000,
    level: float = 0.95,
    seed: int = 42,
) -> Interval:
    """Bootstrap CI for a rate, given one boolean per item.

    A convenience over `bootstrap_statistic`, present because almost every
    headline number in the Phase 9 profile is a rate -- duplicate rate, defect
    rate, coverage -- and writing the lambda at each call site is where an
    off-by-one denominator gets introduced.
    """
    return bootstrap_statistic(
        [1.0 if f else 0.0 for f in flags],
        lambda xs: sum(xs) / len(xs),
        n_resamples=n_resamples,
        level=level,
        seed=seed,
    )


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
