"""Calibration, and the honest measurement of how badly calibrated we are.

The distinction this module is built around
-------------------------------------------
A model that *ranks* well and a model that is *calibrated* are different things.
Ranking means: if A scores higher than B, A is more at risk than B. Calibration
means: among all cases scored 0.7, about 70% actually carry the property.

Phase 13 and 14 measure ranking (F1). Nothing so far measures calibration, and
the risk index is exactly where it starts to matter -- a coach shown "0.82 risk"
will read it as a probability whether or not anyone said it was one.
`config/settings.yaml` asks for ECE for this reason, and `PROJECT_PLAN.md` Phase
15 makes "calibration error reported" the gate.

Note the gate's wording: **reported**, not *low*. A high ECE that is measured and
stated is a result. A low ECE obtained by fitting the calibrator on the data it
is then evaluated on is a fabrication, and it is the easy mistake here because
the fitting code and the evaluation code want the same array. `fit_temperature`
and `expected_calibration_error` are therefore separate functions that must be
handed separate data, and `scripts/run_risk.py` passes a validation split to one
and a test split to the other.

What is being calibrated, and against what
------------------------------------------
Here is the part that must not be glossed. Calibrating the *risk index* requires
a binary risk outcome per record, and **no such outcome exists** -- no athlete in
this corpus has a measured pre-competition risk state (see `fusion.py`). So this
module does two different things, and keeping them apart is the whole point:

1. **Per-construct calibration** (`fit_temperature`, `reliability_table`) -- the
   classifier's construct probabilities *can* be calibrated, against the planted
   construct labels. This is real, runnable now, and inherits the standard
   caveat: the target is a template generator's intent, so it measures calibration
   against a corpus property, not against human judgement.

2. **Risk-index calibration** -- **not possible**, and `calibrate_risk_index`
   refuses rather than substituting a proxy. The tempting substitute is
   "risk = 1 if any risk-raising construct is planted", which would produce a
   respectable ECE and mean nothing: it calibrates the fusion against a
   restatement of its own inputs. `RiskCalibrationUnavailable` says so in the
   message.

Pure Python, deliberately
-------------------------
Same reasoning as `src/evaluation/metrics.py`: this must import in the light
Docker image, and a metric the project implements itself is one it can be held
to. Temperature is fitted by golden-section search over a one-dimensional convex
objective (NLL), which needs no optimiser and no gradient.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import log

#: Clamp for probabilities entering a logarithm. Without it a confident, wrong
#: prediction contributes an infinite NLL and the search returns whatever
#: temperature happens to avoid the infinity rather than the one that fits.
_EPS = 1e-12


class RiskCalibrationUnavailable(RuntimeError):
    """Raised when calibration of the *risk index* is requested.

    Distinct type, so a caller can catch exactly this and report "no risk target
    exists" rather than treating it as a numerical failure. See the module
    docstring.
    """


@dataclass(frozen=True)
class ReliabilityBin:
    """One bin of a reliability diagram."""

    lower: float
    upper: float
    count: int
    mean_confidence: float
    observed_frequency: float

    @property
    def gap(self) -> float:
        """Signed miscalibration. Positive means over-confident."""
        return self.mean_confidence - self.observed_frequency


@dataclass(frozen=True)
class CalibrationReport:
    """ECE, MCE and the bins they were computed from.

    The bins are kept, not just the summary. ECE is a weighted average and
    averages hide shape: a model that is well calibrated in the middle and wildly
    over-confident at the top can post a decent ECE, and the top is exactly where
    a risk instrument does damage.
    """

    ece: float
    mce: float
    n: int
    bins: tuple[ReliabilityBin, ...]
    label: str = ""

    def as_lines(self) -> list[str]:
        lines = [
            f"{self.label or 'calibration'}: n={self.n} ECE={self.ece:.4f} MCE={self.mce:.4f}",
            f"  {'bin':>12} {'n':>6} {'conf':>7} {'obs':>7} {'gap':>7}",
        ]
        for b in self.bins:
            if b.count == 0:
                continue
            lines.append(
                f"  [{b.lower:.2f},{b.upper:.2f}) {b.count:>6} "
                f"{b.mean_confidence:>7.3f} {b.observed_frequency:>7.3f} {b.gap:>+7.3f}"
            )
        return lines


def reliability_table(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
    label: str = "",
) -> CalibrationReport:
    """Bin predictions by confidence and compare to observed frequency.

    Equal-width bins rather than equal-count. Equal-width is the convention ECE
    is normally reported under, so the number is comparable to published ones;
    equal-count would give tighter estimates in sparse regions but a metric
    nobody else computes the same way.

    Empty bins contribute nothing and are dropped from the printed table, but the
    denominator remains the full sample -- ECE is weighted by bin population, so
    an empty bin correctly contributes zero rather than being averaged in as if
    it were perfect.
    """
    if len(probabilities) != len(outcomes):
        raise ValueError(
            f"length mismatch: {len(probabilities)} probabilities vs {len(outcomes)} outcomes"
        )
    n = len(probabilities)
    if n == 0:
        return CalibrationReport(ece=0.0, mce=0.0, n=0, bins=(), label=label)

    edges = [i / n_bins for i in range(n_bins + 1)]
    bins: list[ReliabilityBin] = []
    ece = 0.0
    mce = 0.0

    for i in range(n_bins):
        lower, upper = edges[i], edges[i + 1]
        # The last bin is closed on the right so p == 1.0 is not discarded.
        members = [
            (p, o)
            for p, o in zip(probabilities, outcomes, strict=True)
            if (lower <= p < upper) or (i == n_bins - 1 and p == 1.0)
        ]
        if not members:
            bins.append(ReliabilityBin(lower, upper, 0, 0.0, 0.0))
            continue
        confidence = sum(p for p, _ in members) / len(members)
        observed = sum(o for _, o in members) / len(members)
        gap = abs(confidence - observed)
        ece += (len(members) / n) * gap
        mce = max(mce, gap)
        bins.append(ReliabilityBin(lower, upper, len(members), confidence, observed))

    return CalibrationReport(ece=ece, mce=mce, n=n, bins=tuple(bins), label=label)


def expected_calibration_error(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    n_bins: int = 10,
) -> float:
    """ECE alone, for callers that want the scalar.

    A thin wrapper over `reliability_table` rather than a second implementation:
    two ways of computing ECE is two numbers that will eventually disagree in a
    paper. Prefer the full report where the shape matters -- see
    `CalibrationReport` on why the bins are worth keeping.
    """
    return reliability_table(probabilities, outcomes, n_bins=n_bins).ece


def _nll(probabilities: Sequence[float], outcomes: Sequence[int], temperature: float) -> float:
    """Negative log-likelihood of the outcomes under temperature-scaled probabilities."""
    total = 0.0
    for p, o in zip(probabilities, outcomes, strict=True):
        scaled = _apply_temperature(p, temperature)
        total -= log(max(scaled, _EPS)) if o else log(max(1.0 - scaled, _EPS))
    return total / max(1, len(outcomes))


def _apply_temperature(probability: float, temperature: float) -> float:
    """Temperature-scale a probability by rescaling its logit.

    Working in logit space rather than rescaling the probability directly is what
    makes this a monotone transform that fixes 0.5 and leaves the *ranking*
    untouched. That property is the reason temperature scaling is the right
    calibrator here: it cannot change which utterance is ranked riskier, so it
    cannot alter any F1 already reported, and calibration becomes a strictly
    additive claim rather than a re-run of everything upstream.
    """
    p = min(max(probability, _EPS), 1.0 - _EPS)
    logit = log(p / (1.0 - p))
    scaled = logit / temperature if temperature else logit
    if scaled >= 0:
        from math import exp

        return 1.0 / (1.0 + exp(-min(scaled, 700.0)))
    from math import exp

    e = exp(max(scaled, -700.0))
    return e / (1.0 + e)


def fit_temperature(
    probabilities: Sequence[float],
    outcomes: Sequence[int],
    *,
    low: float = 0.05,
    high: float = 10.0,
    tolerance: float = 1e-4,
) -> float:
    """Fit a single temperature by minimising NLL. **Validation data only.**

    Golden-section search: NLL as a function of temperature is unimodal on this
    interval, the problem is one-dimensional, and a search that needs no
    derivative keeps this module free of numpy.

    T > 1 softens over-confident probabilities; T < 1 sharpens under-confident
    ones; T = 1 is a no-op. A returned value pinned at `low` or `high` means the
    search hit its bound and the result should be read as "outside the searched
    range" rather than as a fit -- `scripts/run_risk.py` prints a warning in that
    case.

    Passing test data here silently destroys the meaning of every calibration
    number downstream. The function cannot detect that, which is why the runner
    keeps the two splits in separate variables and `tests/test_risk.py` asserts
    the temperature is fitted on the validation side.
    """
    if not probabilities:
        return 1.0

    phi = (5**0.5 - 1) / 2
    a, b = low, high
    c, d = b - phi * (b - a), a + phi * (b - a)
    fc, fd = _nll(probabilities, outcomes, c), _nll(probabilities, outcomes, d)

    while abs(b - a) > tolerance:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - phi * (b - a)
            fc = _nll(probabilities, outcomes, c)
        else:
            a, c, fc = c, d, fd
            d = a + phi * (b - a)
            fd = _nll(probabilities, outcomes, d)
    return (a + b) / 2


def apply_temperature(probabilities: Sequence[float], temperature: float) -> list[float]:
    """Temperature-scale a sequence of probabilities."""
    return [_apply_temperature(p, temperature) for p in probabilities]


def calibrate_risk_index(*_: object, **__: object) -> float:
    """Refuses. There is no risk target to calibrate the fused index against.

    Kept as a named function that raises, rather than omitted, because its
    absence would be an invitation: the next session needing a calibrated risk
    index would write it, reach for the nearest available binary, and calibrate
    the fusion against a restatement of its own inputs. A refusal with the
    reasoning attached is harder to walk past than a gap.
    """
    raise RiskCalibrationUnavailable(
        "The fused risk index cannot be calibrated: no risk outcome exists. No "
        "athlete in this corpus has a measured pre-competition risk state -- no "
        "administered CSAI-2, no clinician rating, no competition outcome linked "
        "to text. Calibration needs an observed binary per record and there is "
        "none.\n\n"
        "Do NOT substitute a proxy such as 'any risk-raising construct was "
        "planted'. That target is a restatement of the fusion's own inputs, so "
        "calibrating against it would produce a good ECE that means nothing.\n\n"
        "What IS calibratable today: the per-construct probabilities, against the "
        "planted construct labels -- use fit_temperature/reliability_table for "
        "those, and read the result as a corpus property (OPEN-025).\n\n"
        "What would make this function implementable: administered CSAI-2 scores "
        "alongside pre-competition text, or outcome-linked data. That is the "
        "'Outcome-linkage validation' expansion in CLAUDE.md sec.10, and it is "
        "the single acquisition that would turn the risk index from a ranking "
        "into a measurement."
    )
