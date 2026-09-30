"""Phase 22 -- trajectory features over `synth_precomp_v2`, and the control that judges them.

What this computes, and what it is for
---------------------------------------
Post-processing on the L2 risk vector -- the per-record output of
`src/dashboard/view.py::build_view`: ten construct probabilities and one risk
index. Nothing here re-scores anything, fits a weight, or introduces a model.
Every value entering this module was produced by the ordinary scoring path for
a real record, which keeps Phase 34's "no new arithmetic" rule true one level
up: the arithmetic here is over `build_view`'s outputs, never inside them.

**These numbers are a sanity check on instrumentation.** The drift they
recover was planted on purpose by `src/ingestion/temporal.py` under an owner
decision of 2026-09-29, citing CSAI-2 multidimensional anxiety theory
[Martens1990; Cox2003]. Recovering a drift this project planted tells us the
trajectory code works. It is not a finding about athletes, not a clinical
result, and not evidence for the psychological claim itself -- no real athlete,
no observed outcome and no human label is involved anywhere in this corpus.
`TRAJECTORY_FRAMING` carries that sentence and every artefact leads with it.

The time axis, stated once and loudly
--------------------------------------
`time_to_competition_days` counts DOWN to the event: 30 is a month out, 0 is
the day itself. Fitting a slope against it directly would give a NEGATIVE
coefficient for a quantity that rises as the competition approaches, which is
the sign error this kind of analysis is famous for. So the regressor is

    t = -time_to_competition_days

t increases towards the event, and a POSITIVE slope therefore means "rises as
the competition approaches" in plain reading. `SLOPE_SIGN_NOTE` says so on
every surface that prints a slope.

The two rules this module is shaped around
-------------------------------------------
**A slope needs enough points to be a shape.** Over three points an OLS slope
is dominated by whichever point sits furthest from the other two; over two it
is a line through both and says nothing about shape at all. Slopes over fewer
than `MIN_TIMEPOINTS_FOR_SLOPE` timepoints are therefore SUPPRESSED -- returned
as `None`, never as a number -- and the suppression rate is reported as a
headline figure rather than the rows being quietly dropped.

**A timepoint the detector could not read carries no value.** `.claude.md`
sec.12.3, by a sixth door: `LexiconBackend` scores anything, and a record it
found nothing in squashes to exactly 0.50. Dropped into a trajectory, a run of
those would draw a confident flat line at the midpoint. So an unreadable
timepoint is excluded from the series entirely -- not imputed, not carried
forward, not entered as 0.5 -- and `AthleteSeries` refuses to hold a value it
did not earn.

The control, and why the whole phase is gated on it
-----------------------------------------------------
A slope fitted to a short, noisy series will be non-zero essentially always.
The question is never "is the slope non-zero" but "is it more than the same
series in a scrambled order would give". `shuffled_control` permutes the
day-to-value pairing WITHIN each athlete and recomputes every feature, R times,
building a null distribution of the aggregate. If the observed aggregate sits
inside that null, the feature carries no temporal signal, **and that is the
finding that gets published** -- it is not a failure to be tuned away.

For `somatic_anxiety` the control should destroy the signal. For
`cognitive_anxiety` and `self_confidence` -- flat by design in the generator
(`temporal.FLAT_BY_DESIGN`) -- there is nothing to destroy, and they should sit
inside the null both before and after. They are the layer's built-in negative
controls. Eight of the ten constructs have no drift planted at all and the same
holds for them: a reader meeting nine quiet channels and one live one is
looking at the design working, not at nine failures.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np

from src.ingestion.temporal import MIN_TIMEPOINTS_FOR_SLOPE, AthletePanel

__all__ = [
    "CLUSTER_FEATURES",
    "N_SHAPE_CLUSTERS",
    "SHUFFLE_REPEATS",
    "SLOPE_SIGN_NOTE",
    "TRAJECTORY_FRAMING",
    "AthleteSeries",
    "ChannelResult",
    "ControlResult",
    "TrajectoryFeatures",
    "TrajectoryReport",
    "analyse",
    "cluster_shapes",
    "features_for",
    "shuffled_control",
]

TRAJECTORY_FRAMING = (
    "Sanity check, not a finding. Every trajectory number below is computed over "
    "synth_precomp_v2, a synthetic corpus in which the temporal drift was PLANTED by "
    "src/ingestion/temporal.py under an owner decision of 2026-09-29. Recovering that "
    "drift shows the trajectory code works; it is not evidence about athletes, not a "
    "clinical statement, and not support for the psychological claim that motivated it. "
    "No real athlete, no observed outcome and no human label exists anywhere in this corpus."
)

SLOPE_SIGN_NOTE = (
    "Slope is fitted against t = -time_to_competition_days, so t increases towards the "
    "competition and a POSITIVE slope means the quantity rises as the event approaches."
)

#: Permutations per channel. 2,000 puts the resolution of a two-sided
#: permutation p-value at 0.0005, which is finer than any claim made from it.
SHUFFLE_REPEATS = 2_000

#: The feature vector clustered into trajectory shapes.
CLUSTER_FEATURES: tuple[str, ...] = ("slope", "volatility", "last_day_delta")

#: Family-wise error rate for the channel family. Every channel is tested at
#: once, so an uncorrected 0.05 threshold is simply the wrong test: across 11
#: channels it produces a false positive roughly half the time, and this
#: analysis duly found one (`coping_style`, p=0.025, no drift planted in it, no
#: cue overlap with the drifting construct and a flat day profile). Holm's
#: step-down controls the family-wise rate without Bonferroni's power loss, and
#: it is applied to the whole channel family in `analyse`.
FAMILY_ALPHA = 0.05

#: Three shapes: the smallest k that can separate "rising", "falling" and
#: "flat/noisy", which is the distinction the drift claim is about. A larger k
#: would split the noise, and a silhouette-chosen k would be a number fitted on
#: data with no outcome to fit against.
N_SHAPE_CLUSTERS = 3


@dataclass(frozen=True)
class AthleteSeries:
    """One athlete, one channel: the readable timepoints and nothing else.

    `days` counts down to the event and is strictly decreasing. `values` are
    whatever `build_view` produced at those timepoints. The two must be the
    same length -- an `AthleteSeries` cannot hold a value it did not earn, the
    same construction-time rule `SquadMember`, `SentenceBand` and `CloudLane`
    already enforce one level down.
    """

    athlete_id: str
    channel: str
    days: tuple[int, ...]
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.days) != len(self.values):
            raise ValueError(
                f"series {self.athlete_id}/{self.channel} has {len(self.days)} days and "
                f"{len(self.values)} values. A timepoint the detector could not read is "
                "excluded, never imputed and never entered as 0.5 -- see .claude.md sec.12.3."
            )
        if len(set(self.days)) != len(self.days):
            raise ValueError(f"series {self.athlete_id}/{self.channel} repeats a day")
        if list(self.days) != sorted(self.days, reverse=True):
            raise ValueError(f"series {self.athlete_id}/{self.channel} is not ordered far-to-near")
        if any(not math.isfinite(v) for v in self.values):
            raise ValueError(f"series {self.athlete_id}/{self.channel} holds a non-finite value")

    @property
    def n(self) -> int:
        return len(self.values)

    @property
    def t(self) -> tuple[float, ...]:
        """The regressor: negated days, so t increases towards the competition."""
        return tuple(float(-d) for d in self.days)


@dataclass(frozen=True)
class TrajectoryFeatures:
    """The four features, with `slope` absent rather than unreliable.

    `slope is None` is a suppression, not a failure and not a zero. It means the
    series had fewer than `MIN_TIMEPOINTS_FOR_SLOPE` readable timepoints and a
    slope over it would have been a number without a shape behind it.
    """

    athlete_id: str
    channel: str
    n_timepoints: int
    slope: float | None
    volatility: float | None
    last_day_delta: float | None
    suppressed: bool

    def __post_init__(self) -> None:
        if self.suppressed != (self.slope is None):
            raise ValueError(
                f"{self.athlete_id}/{self.channel}: suppressed={self.suppressed} disagrees "
                "with whether a slope is present. The suppression rate is a reported "
                "figure; it cannot be reported if the flag and the value can drift apart."
            )
        if self.slope is not None and self.n_timepoints < MIN_TIMEPOINTS_FOR_SLOPE:
            raise ValueError(
                f"{self.athlete_id}/{self.channel}: slope over {self.n_timepoints} points "
                f"below the floor of {MIN_TIMEPOINTS_FOR_SLOPE}"
            )


def _ols_slope(t: Sequence[float], y: Sequence[float]) -> float:
    """Plain least-squares slope of y on t. No intercept shortcuts, no library."""
    t_arr = np.asarray(t, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    t_centred = t_arr - t_arr.mean()
    denom = float((t_centred**2).sum())
    if denom == 0.0:  # pragma: no cover - AthleteSeries forbids repeated days
        raise ValueError("cannot fit a slope against a constant time axis")
    return float((t_centred * (y_arr - y_arr.mean())).sum() / denom)


def features_for(series: AthleteSeries) -> TrajectoryFeatures:
    """The four trajectory features for one series, suppressing a thin slope."""
    n = series.n
    suppressed = n < MIN_TIMEPOINTS_FOR_SLOPE
    slope = None if suppressed else _ols_slope(series.t, series.values)
    # Sample standard deviation: an athlete's spread around their own level.
    # ddof=1 because a single reading has no spread to estimate, and reporting
    # 0.0 there would claim a steady athlete rather than an unmeasurable one.
    volatility = float(np.std(series.values, ddof=1)) if n >= 2 else None
    # values are ordered far-to-near, so the last pair is the approach to the event.
    last_day_delta = float(series.values[-1] - series.values[-2]) if n >= 2 else None
    return TrajectoryFeatures(
        athlete_id=series.athlete_id,
        channel=series.channel,
        n_timepoints=n,
        slope=slope,
        volatility=volatility,
        last_day_delta=last_day_delta,
        suppressed=suppressed,
    )


@dataclass(frozen=True)
class ControlResult:
    """Observed aggregate slope against the within-athlete shuffled null."""

    channel: str
    n_series: int
    n_suppressed: int
    observed_mean_slope: float | None
    null_mean: float | None
    null_sd: float | None
    null_lo: float | None
    null_hi: float | None
    p_value: float | None
    repeats: int

    @property
    def suppression_rate(self) -> float:
        total = self.n_series + self.n_suppressed
        return self.n_suppressed / total if total else 0.0

    @property
    def survives_control(self) -> bool:
        """True when the observed slope sits outside the shuffled null.

        Deliberately phrased as surviving a control rather than as significance:
        the null here is a re-ordering of this corpus, not a population model,
        and the p-value is a permutation rank rather than a test statistic with
        a distributional claim behind it.
        """
        if self.p_value is None or self.null_lo is None or self.null_hi is None:
            return False
        if self.observed_mean_slope is None:
            return False
        outside = not (self.null_lo <= self.observed_mean_slope <= self.null_hi)
        return outside and self.p_value < 0.05

    @property
    def verdict(self) -> str:
        """One line, in the words the report prints. Never a colour or a symbol."""
        if self.observed_mean_slope is None:
            return "no unsuppressed series - nothing to test"
        if self.survives_control:
            return "slope survives the shuffled-time control"
        return "slope carries no signal beyond the shuffle"


def shuffled_control(
    series: Sequence[AthleteSeries],
    *,
    channel: str,
    repeats: int = SHUFFLE_REPEATS,
    seed: int = 22,
) -> ControlResult:
    """Recompute the aggregate slope on within-athlete shuffled day order.

    The permutation is of the day-to-value PAIRING inside one athlete: the same
    readings, re-dated. It destroys temporal order while preserving every
    athlete's own level, spread and series length, so the null answers exactly
    "what slope would this athlete's own readings give in a scrambled order"
    rather than "what would a different athlete give".

    Series too thin for a slope are excluded from both the observed statistic
    and the null -- suppression applies identically on both sides, or the
    comparison is between two different populations -- and counted, so the
    suppression rate stays reportable.
    """
    usable = [s for s in series if s.n >= MIN_TIMEPOINTS_FOR_SLOPE]
    n_suppressed = len(series) - len(usable)
    if not usable:
        return ControlResult(
            channel=channel,
            n_series=0,
            n_suppressed=n_suppressed,
            observed_mean_slope=None,
            null_mean=None,
            null_sd=None,
            null_lo=None,
            null_hi=None,
            p_value=None,
            repeats=repeats,
        )

    observed = float(np.mean([_ols_slope(s.t, s.values) for s in usable]))

    # Vectorised, because the scalar form is 11 channels x `repeats` x ~300
    # series of OLS fits and takes minutes. The arithmetic is identical: with
    # t centred, `sum(t_c * mean(y))` is zero, so the slope reduces to
    # `dot(t_c, y) / sum(t_c**2)` and a whole block of permutations is one
    # matrix product. Seeded per channel so a rerun reproduces the null.
    # zlib.crc32, not hash(): Python randomises string hashing per process
    # unless PYTHONHASHSEED is set, so hash() here would make the null
    # irreproducible across runs while looking seeded.
    stream = (seed * 1_000_003 + zlib.crc32(channel.encode("utf-8"))) % (2**32)
    rng = np.random.default_rng(stream)
    null_sum = np.zeros(repeats, dtype=float)
    for s in usable:
        t_arr = np.asarray(s.t, dtype=float)
        t_centred = t_arr - t_arr.mean()
        denom = float((t_centred**2).sum())
        y = np.asarray(s.values, dtype=float)
        # argsort of uniform noise gives `repeats` independent permutations.
        order = np.argsort(rng.random((repeats, s.n)), axis=1)
        null_sum += (y[order] @ t_centred) / denom
    null = null_sum / len(usable)

    # Two-sided permutation rank. The +1s are the standard correction that
    # keeps p strictly positive: an observed value more extreme than every
    # permutation gives 1/(R+1), never 0, because R permutations cannot
    # establish that nothing is more extreme.
    p_value = float((np.sum(np.abs(null) >= abs(observed)) + 1) / (repeats + 1))
    return ControlResult(
        channel=channel,
        n_series=len(usable),
        n_suppressed=n_suppressed,
        observed_mean_slope=observed,
        null_mean=float(null.mean()),
        null_sd=float(null.std(ddof=1)),
        null_lo=float(np.percentile(null, 2.5)),
        null_hi=float(np.percentile(null, 97.5)),
        p_value=p_value,
        repeats=repeats,
    )


@dataclass(frozen=True)
class ChannelResult:
    """Everything computed for one channel: features, control and clusters."""

    channel: str
    plain_name: str
    features: tuple[TrajectoryFeatures, ...]
    control: ControlResult
    flat_by_design: bool
    drifting_by_design: bool
    #: True for a channel with no drift planted IN it that must nonetheless move,
    #: because it is computed from one that does. `risk_index` is the only such
    #: channel: `somatic_anxiety` carries a weight of +1.0 in
    #: `LinearRiskScorer`, so a planted rise in the construct propagates into the
    #: index arithmetically. Kept distinct from `drifting_by_design` because a
    #: reader is entitled to know which channel was designed and which merely
    #: inherits -- collapsing the two would let a derived result be read as an
    #: independent confirmation of the same planted effect.
    inherits_drift: bool = False
    clusters: Mapping[str, int] = field(default_factory=dict)
    cluster_sizes: Mapping[int, int] = field(default_factory=dict)
    #: Holm-corrected decision across the whole channel family. This, not
    #: `control.survives_control`, is what the report and `matches_expectation`
    #: read: the uncorrected flag answers "is this channel's slope outside its
    #: own null", which is the right question only if this were the one channel
    #: anyone looked at.
    holm_reject: bool = False
    holm_threshold: float | None = None

    @property
    def n_suppressed(self) -> int:
        return sum(1 for f in self.features if f.suppressed)

    @property
    def suppression_rate(self) -> float:
        return self.n_suppressed / len(self.features) if self.features else 0.0

    @property
    def expectation(self) -> str:
        """What the generator's design says this channel SHOULD do.

        Printed beside the result so a reader can see the prediction was made
        before the measurement, not fitted to it afterwards.
        """
        if self.drifting_by_design:
            return "drift planted - should survive the control"
        if self.inherits_drift:
            return "drift inherited, not planted - should survive the control"
        if self.flat_by_design:
            return "flat by design - should NOT survive the control"
        return "no drift planted - should NOT survive the control"

    @property
    def should_survive(self) -> bool:
        return self.drifting_by_design or self.inherits_drift

    @property
    def signal(self) -> bool:
        """Family-corrected verdict: the one the report prints."""
        return self.holm_reject

    @property
    def verdict(self) -> str:
        if self.control.observed_mean_slope is None:
            return "no unsuppressed series - nothing to test"
        if self.holm_reject:
            return "slope survives the shuffled-time control"
        if self.control.survives_control:
            return "not separable from the shuffle once the channel family is corrected"
        return "slope carries no signal beyond the shuffle"

    @property
    def matches_expectation(self) -> bool:
        return self.signal == self.should_survive


def cluster_shapes(
    features: Sequence[TrajectoryFeatures], *, k: int = N_SHAPE_CLUSTERS, seed: int = 22
) -> tuple[dict[str, int], dict[int, int]]:
    """Group athletes by trajectory shape, in feature space.

    Clustering raw series is not available here and pretending otherwise would
    be the error: the panels are RAGGED by design, so two athletes' readings
    sit on different day sets and cannot be compared point-by-point without
    interpolating readings nobody took. So the clustering runs over the
    z-scored `CLUSTER_FEATURES` vector, which is defined identically for every
    unsuppressed athlete regardless of which days they spoke on.

    Returned as `athlete_id -> cluster` plus the sizes. Cluster INDICES carry no
    meaning and no ordering -- they are not a ranking, not a severity and not a
    label -- which is why nothing downstream prints one without its centroid.
    """
    usable = [
        f
        for f in features
        if not f.suppressed and f.volatility is not None and f.last_day_delta is not None
    ]
    if len(usable) < k:
        return {}, {}

    from sklearn.cluster import KMeans

    matrix = np.array([[f.slope, f.volatility, f.last_day_delta] for f in usable], dtype=float)
    sd = matrix.std(axis=0, ddof=0)
    # A feature with no spread carries no information and would divide by zero.
    sd[sd == 0.0] = 1.0
    z = (matrix - matrix.mean(axis=0)) / sd

    model = KMeans(n_clusters=k, n_init=10, random_state=seed)
    labels = model.fit_predict(z)

    # strict=True: KMeans must return exactly one label per row it was given.
    # A silent truncation here would drop athletes from the clustering without
    # changing any reported count.
    assignment = {f.athlete_id: int(label) for f, label in zip(usable, labels, strict=True)}
    sizes: dict[int, int] = {}
    for label in labels:
        sizes[int(label)] = sizes.get(int(label), 0) + 1
    return assignment, sizes


@dataclass(frozen=True)
class TrajectoryReport:
    """The whole analysis: one `ChannelResult` per channel, plus corpus counts."""

    channels: tuple[ChannelResult, ...]
    n_athletes: int
    n_records: int
    n_readable_records: int
    n_unreadable_records: int
    framing: str = TRAJECTORY_FRAMING
    sign_note: str = SLOPE_SIGN_NOTE

    @property
    def unreadable_rate(self) -> float:
        return self.n_unreadable_records / self.n_records if self.n_records else 0.0

    def channel(self, name: str) -> ChannelResult:
        for result in self.channels:
            if result.channel == name:
                return result
        raise KeyError(name)

    @property
    def design_holds(self) -> bool:
        """Every channel did what the generator's design predicted it would."""
        return all(c.matches_expectation for c in self.channels)


def _series_from_panels(
    panels: Sequence[AthletePanel],
    readings: Mapping[str, Mapping[str, float]],
    channel: str,
) -> list[AthleteSeries]:
    """Assemble one channel's series, skipping timepoints with no reading."""
    out: list[AthleteSeries] = []
    for panel in panels:
        days: list[int] = []
        values: list[float] = []
        for record in panel.records:
            reading = readings.get(record.record_id)
            if reading is None or channel not in reading:
                continue
            days.append(int(record.time_to_competition_days))
            values.append(float(reading[channel]))
        if values:
            out.append(
                AthleteSeries(
                    athlete_id=panel.athlete_id,
                    channel=channel,
                    days=tuple(days),
                    values=tuple(values),
                )
            )
    return out


def analyse(
    panels: Sequence[AthletePanel],
    readings: Mapping[str, Mapping[str, float]],
    *,
    channels: Sequence[str],
    plain_names: Mapping[str, str] | None = None,
    drifting: Sequence[str] = (),
    flat: Sequence[str] = (),
    inherits: Sequence[str] = (),
    repeats: int = SHUFFLE_REPEATS,
    seed: int = 22,
) -> TrajectoryReport:
    """Run every channel through features, control and clustering.

    `readings` maps `record_id -> {channel: value}`, exactly what a caller gets
    by running `build_view` over the corpus. A record the detector could not
    read is simply absent from the mapping, which is how an unreadable
    timepoint stays out of every series without this module needing to know
    what made it unreadable.
    """
    plain_names = plain_names or {}
    n_records = sum(p.n_timepoints for p in panels)
    n_readable = sum(1 for p in panels for r in p.records if readings.get(r.record_id) is not None)

    results: list[ChannelResult] = []
    for channel in channels:
        series = _series_from_panels(panels, readings, channel)
        feats = tuple(features_for(s) for s in series)
        control = shuffled_control(series, channel=channel, repeats=repeats, seed=seed)
        assignment, sizes = cluster_shapes(feats, seed=seed)
        results.append(
            ChannelResult(
                channel=channel,
                plain_name=plain_names.get(channel, channel),
                features=feats,
                control=control,
                flat_by_design=channel in flat,
                drifting_by_design=channel in drifting,
                inherits_drift=channel in inherits,
                clusters=assignment,
                cluster_sizes=sizes,
            )
        )

    # --- Holm step-down across the channel family ---
    import dataclasses

    testable = [r for r in results if r.control.p_value is not None]
    ordered = sorted(testable, key=lambda r: r.control.p_value)
    m = len(ordered)
    rejected: set[str] = set()
    thresholds: dict[str, float] = {}
    for i, result in enumerate(ordered):
        threshold = FAMILY_ALPHA / (m - i)
        thresholds[result.channel] = threshold
        if result.control.p_value < threshold and (i == 0 or ordered[i - 1].channel in rejected):
            rejected.add(result.channel)
    results = [
        dataclasses.replace(
            r,
            holm_reject=r.channel in rejected,
            holm_threshold=thresholds.get(r.channel),
        )
        for r in results
    ]

    return TrajectoryReport(
        channels=tuple(results),
        n_athletes=len(panels),
        n_records=n_records,
        n_readable_records=n_readable,
        n_unreadable_records=n_records - n_readable,
    )
