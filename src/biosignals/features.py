"""Pure feature functions. No I/O, no state, no randomness, no ML stack.

Why these are functions and not methods on a source
---------------------------------------------------
Same argument as `src/dashboard/` (and `src/risk/`, and `src/evaluation/`): the
thing that computes and the thing that renders are separate programs. A feature
computed inside a source object can only be tested through that source, which
means the test is really testing the simulator, which means the day a real
device arrives the feature has no test at all. These take numbers and return
numbers, so the fixtures below are arithmetic a reader can check on paper.

There is no numpy here on purpose. The dashboard test suite runs in seconds with
no ML stack installed and `src/dashboard/__init__.py` explains why that matters;
`src/biosignals` joins that rule rather than starting a second one. A 256-point
window over four band edges is a few tens of thousands of float operations, which
is nothing, and the naive DFT below is legible enough that its correctness is
visible rather than delegated.

Nothing in this module is fitted. There is no outcome in this repository to fit
anything against (`data/gold/` is empty), so every constant here is either a
convention from the literature, stated as such, or an explicit choice with its
reasoning beside it. A weight that looks learned when it is not is the same
category of lie as a simulated trace that looks measured.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Sequence

#: Conventional EEG band edges, in Hz, lower inclusive and upper exclusive.
#: These are textbook boundaries, not a finding of this project.
DELTA_BAND = (0.5, 4.0)
THETA_BAND = (4.0, 8.0)
ALPHA_BAND = (8.0, 13.0)
BETA_BAND = (13.0, 30.0)

BANDS: dict[str, tuple[float, float]] = {
    "delta": DELTA_BAND,
    "theta": THETA_BAND,
    "alpha": ALPHA_BAND,
    "beta": BETA_BAND,
}


def _centered(samples: Sequence[float]) -> tuple[float, ...]:
    """Remove the mean. A DC offset otherwise lands in the lowest bins as power."""
    values = tuple(float(s) for s in samples)
    mean = sum(values) / len(values)
    return tuple(v - mean for v in values)


def band_power(
    samples: Sequence[float],
    sample_rate_hz: float,
    low_hz: float,
    high_hz: float,
) -> float:
    """Mean-square power of `samples` in [low_hz, high_hz), by naive DFT.

    Scaled so that a pure cosine of amplitude A sitting exactly on a bin centre
    returns A**2 / 2 -- its mean-square power. That is the property the test
    fixtures assert, and it is why the scaling is written out rather than lifted
    from a library: with

        X_k = sum_n x_n * exp(-2j*pi*k*n/N)

    a cosine of amplitude A at bin k has |X_k| = A*N/2, so (2/N**2)*|X_k|**2
    comes to A**2/2 exactly. Anything that changes this scaling breaks a
    hand-computed fixture rather than silently rescaling every panel.

    Only the bins inside the band are evaluated, so this is O(N * bins_in_band)
    rather than O(N**2).
    """
    if sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be positive.")
    if not (0.0 <= low_hz < high_hz):
        raise ValueError(f"band must satisfy 0 <= low < high, got ({low_hz}, {high_hz}).")
    values = _centered(samples)
    n = len(values)
    if n < 2:
        raise ValueError("band power needs at least two samples.")

    resolution = sample_rate_hz / n
    k_low = max(1, math.ceil(low_hz / resolution))  # bin 0 is DC, already removed
    k_high = min(n // 2, math.ceil(high_hz / resolution) - 1)

    total = 0.0
    for k in range(k_low, k_high + 1):
        acc = 0j
        step = -2j * math.pi * k / n
        for index, value in enumerate(values):
            acc += value * cmath.exp(step * index)
        total += (2.0 / (n * n)) * (acc.real * acc.real + acc.imag * acc.imag)
    return total


def relative_band_power(
    samples: Sequence[float],
    sample_rate_hz: float,
    low_hz: float,
    high_hz: float,
    *,
    reference: tuple[float, float] = (DELTA_BAND[0], BETA_BAND[1]),
) -> float:
    """Band power as a fraction of power in `reference`. Unitless, in [0, 1].

    Useful because absolute band power depends on electrode impedance, gain and
    a dozen other things a simulator does not have, so an absolute number is not
    comparable across sources even in principle.
    """
    whole = band_power(samples, sample_rate_hz, *reference)
    if whole <= 0.0:
        raise ValueError("reference band carries no power; a ratio would be meaningless.")
    return band_power(samples, sample_rate_hz, low_hz, high_hz) / whole


def alpha_theta_ratio(alpha_power: float, theta_power: float) -> float:
    """Alpha power divided by theta power.

    Raises on zero or negative theta rather than flooring it with an epsilon.
    An epsilon here would be an invented constant that silently sets the ceiling
    of the V5 ring -- a number nothing in this project supports, doing real work
    in a picture. A window with literally no theta power cannot come from any
    source in this package (there is always noise in the band), so the raise is
    a genuine "this input is not what you think it is" rather than a case the
    caller has to handle.
    """
    if alpha_power < 0.0:
        raise ValueError("alpha power cannot be negative.")
    if theta_power <= 0.0:
        raise ValueError(
            "theta power is zero, so the alpha/theta ratio is undefined. Flooring it "
            "with an epsilon would invent the ceiling of the neurofeedback ring; see "
            "this function's docstring."
        )
    return alpha_power / theta_power


# ---------------------------------------------------------------------------
# V3: cognitive load from heart-rate variability and webcam oculometrics
# ---------------------------------------------------------------------------

#: The high-frequency HRV band, in Hz. Respiratory-linked, conventionally read as
#: a parasympathetic index. A textbook boundary, not a finding of this project.
HF_BAND = (0.15, 0.40)


def _detrended(values: Sequence[float]) -> tuple[float, ...]:
    """Remove a least-squares straight line, not just the mean.

    Removing only the mean is enough for a stationary window and wrong for this
    one. When simulated arousal steps up, mean RR shifts part-way through the
    trailing window; that step is a broadband transient and it lands in the HF
    band as power. Observed directly: HF-HRV ROSE every time arousal rose, which
    is backwards, and the load index dipped exactly where it should have climbed.

    Linear detrending is the standard first step in HRV spectral analysis for
    precisely this reason, and it is applied here rather than inside
    `band_power` because band_power is generic and its hand-computed fixtures
    depend on it doing nothing clever.
    """
    series = [float(v) for v in values]
    n = len(series)
    mean_x = (n - 1) / 2.0
    mean_y = sum(series) / n
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    slope = (
        sum((i - mean_x) * (y - mean_y) for i, y in enumerate(series)) / denominator
        if denominator
        else 0.0
    )
    return tuple(y - (mean_y + slope * (i - mean_x)) for i, y in enumerate(series))


def hf_hrv(rr_ms: Sequence[float]) -> float:
    """High-frequency power of an RR-interval series, in ms**2.

    The tachogram is treated as a series sampled at the mean beat rate rather
    than interpolated onto a fixed grid. That is the cruder of the two standard
    choices and it is taken deliberately: interpolation adds a resampling kernel
    whose effect on the number nobody here could account for, and this figure is
    a ranking aid rather than a clinical measurement. The docstring says so
    because the panel's caption cannot say it twice.

    The series is linearly detrended first; see `_detrended` for the defect that
    forced it.

    A constant RR series returns 0 -- there is no variability to have power --
    and scaling the variation by k scales the result by k**2, both asserted in
    `tests/test_biosignals.py` against hand-computed fixtures.
    """
    values = [float(r) for r in rr_ms]
    if len(values) < 2:
        raise ValueError("HF-HRV needs at least two RR intervals.")
    if any(v <= 0 for v in values):
        raise ValueError("an RR interval must be positive.")
    detrended = _detrended(values)
    mean_rr_s = (sum(values) / len(values)) / 1000.0
    sample_rate_hz = 1.0 / mean_rr_s
    if sample_rate_hz / 2.0 <= HF_BAND[1]:
        raise ValueError(
            "the mean heart rate is too low for the HF band to sit under Nyquist; "
            "this window cannot answer the question being asked of it."
        )
    return band_power(detrended, sample_rate_hz, *HF_BAND)


def pupil_effort(pupil_z: Sequence[float]) -> float:
    """Mean pupil diameter over the window, in standard deviations from baseline.

    Not clipped at zero. Clipping would make the function non-monotone below
    baseline -- two windows, one calmer than the other, would return the same
    number -- and a meter that cannot tell "relaxed" from "very relaxed" invites
    the reading that everything below baseline is the same state.

    The baseline is the simulator's own, so this is a number about the
    simulation. With a real webcam it would be the participant's own baseline,
    which is a different privacy class and a different document; see
    `src/biosignals/sources.py`.
    """
    values = [float(z) for z in pupil_z]
    if not values:
        raise ValueError("pupil effort needs at least one sample.")
    return sum(values) / len(values)


def blink_rate(blinks: Sequence[float], duration_s: float) -> float:
    """Blinks per minute.

    `blinks` is a per-sample 0/1 flag series; anything above 0.5 counts as a
    blink onset. Returned per minute rather than per second because that is the
    unit the oculometrics literature quotes and a reader can sanity-check
    against their own experience -- roughly 15 to 20 at rest.
    """
    if duration_s <= 0:
        raise ValueError("duration must be positive.")
    count = sum(1 for b in blinks if float(b) > 0.5)
    return 60.0 * count / float(duration_s)


#: Display scales for the load index. NOT norms, NOT calibrated, NOT fitted.
#:
#: Each input arrives in its own unit (ms**2, standard deviations, per minute)
#: and a weighted sum of raw units would be dominated by whichever one happens
#: to be biggest. These divide each input by a round number in its own unit so
#: the weights below mean what they say. They were chosen by hand to put the
#: simulator's range across the middle of the meter, and nothing in this
#: repository could justify a different value -- which is exactly why the
#: caption on the panel says "ranking only, not calibrated".
HF_HRV_REFERENCE_MS2 = 400.0
BLINK_REFERENCE_PER_MIN = 20.0

#: The load index weights. Written here, in the open, because there is no
#: outcome anywhere in this project to fit them against (`data/gold/` is empty).
#: A fitted weight would look like a finding; these are a stated opinion.
#:
#:   hf_hrv       negative -- higher parasympathetic activation reads as calmer
#:   pupil_effort positive -- dilation above baseline is the standard effort proxy
#:   blink_rate   positive -- a CHOICE, and the shakiest term here. The
#:                oculometrics literature is not one-directional on blink rate
#:                under load; this project picks one sign, states that it picked,
#:                and gives the term the smallest weight so the choice moves the
#:                meter least.
LOAD_WEIGHTS: dict[str, float] = {
    "hf_hrv": -0.45,
    "pupil_effort": 0.35,
    "blink_rate": 0.20,
}


def load_index(
    hf_hrv_ms2: float,
    pupil_effort_z: float,
    blink_rate_per_min: float,
) -> float:
    """One 0-to-1 number from the three channels. An explicit weighted sum.

    Squashed with the same logistic `LinearRiskScorer` uses, so the two meters
    on this dashboard are on the same footing: both order windows, neither
    estimates a rate, and neither carries a band or a threshold.

    Monotone in each input with the others held fixed -- asserted -- because a
    meter that can move the wrong way for a single channel cannot be explained
    to anybody, and the explanation is the whole product here.
    """
    z = (
        LOAD_WEIGHTS["hf_hrv"] * (float(hf_hrv_ms2) / HF_HRV_REFERENCE_MS2)
        + LOAD_WEIGHTS["pupil_effort"] * float(pupil_effort_z)
        + LOAD_WEIGHTS["blink_rate"] * (float(blink_rate_per_min) / BLINK_REFERENCE_PER_MIN)
    )
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------------------
# Driving the simulator from what is being said
# ---------------------------------------------------------------------------
#
# READ THIS BEFORE CHANGING ANYTHING BELOW.
#
# This is NOT text<->physiology concordance. Concordance is the question "does
# what the athlete says agree with what their body shows", it is answered by
# correlating two MEASURED channels, and it is deliberately deferred to a second
# paper (.claude.md section 11, "explicitly out of scope"). Nothing here measures
# anything and nothing here answers that question.
#
# What this does is the reverse, and the reverse is trivial: it takes the
# construct probabilities the text model already produced and uses them to drive
# a simulator. The coupling is IMPOSED BY THIS CODE. It is the demo equivalent of
# animating a cartoon heart to a soundtrack -- the heart follows the words
# because it was told to, and the panel says so in those words.
#
# The reason it is worth having at all is that a physiology trace which ignores
# the text is a trace a viewer has to take on trust, while one that visibly
# responds to a phrase they just heard is a trace whose mechanism they can check.
# The risk is that it looks like evidence. The mitigation is that it is labelled,
# every time, as imposed.

#: How the simulated arousal responds to a phrase, in seconds. A rise, then an
#: exponential settle. Both are display constants chosen so the response is
#: visible at a glance next to an eight-second clip; neither is a physiological
#: finding and neither was fitted to anything.
AROUSAL_RISE_S = 1.1
AROUSAL_DECAY_S = 4.5

#: Where arousal sits when nothing has been said yet.
AROUSAL_FLOOR = 0.18


def _arousal_kernel(dt: float) -> float:
    """Response to one phrase, dt seconds after it was spoken. Causal: 0 before."""
    if dt < 0.0:
        return 0.0
    if dt < AROUSAL_RISE_S:
        return dt / AROUSAL_RISE_S
    return math.exp(-(dt - AROUSAL_RISE_S) / AROUSAL_DECAY_S)


def arousal_curve(
    events: Sequence[tuple[float, float]],
    duration_s: float,
    *,
    samples: int,
    baseline: float = AROUSAL_FLOOR,
) -> tuple[float, ...]:
    """A 0-to-1 arousal track over `duration_s`, driven by timed phrases.

    `events` is (time_s, weight), one per evidence span, where the weight is the
    construct's detection strength signed by the direction it pushes the risk
    index. A phrase that raises risk raises simulated arousal; one that lowers it
    lowers it; an inert construct contributes zero and is simply absent from the
    list.

    `baseline` is where the curve sits when no phrase is acting. It is a
    parameter rather than a constant because of what the caller needs to express:
    a construct that moved the risk index while the model could point at NO words
    has no moment in the audio to attach to, and this project refuses to invent
    one for it. Those constructs lift the baseline instead. The result is a trace
    in which an evidenced phrase makes a bump and an unevidenced driver makes a
    flat lift -- a visible difference, rather than the two being blended into one
    shape that hides which is which.

    Superposed and then clamped to [0, 1]. Clamping rather than normalising, so
    that adding a second worried phrase to a text cannot make the first one
    render smaller -- a curve whose past changes when the future does is a curve
    nobody can reason about while listening to it.
    """
    if duration_s <= 0:
        raise ValueError("duration must be positive.")
    if samples < 2:
        raise ValueError("an arousal curve needs at least two samples.")
    step = duration_s / (samples - 1)
    out = []
    for i in range(samples):
        t = i * step
        level = baseline + sum(w * _arousal_kernel(t - at) for at, w in events)
        out.append(max(0.0, min(1.0, level)))
    return tuple(out)


def heart_rate_bpm(rr_ms: Sequence[float]) -> float:
    """Mean heart rate over an RR series, in beats per minute. 60000 / mean(RR)."""
    values = [float(r) for r in rr_ms]
    if not values:
        raise ValueError("heart rate needs at least one RR interval.")
    mean_rr = sum(values) / len(values)
    if mean_rr <= 0:
        raise ValueError("an RR interval must be positive.")
    return 60000.0 / mean_rr


#: Weights for the short-window load index. Two channels, not three.
#:
#: HRV IS DELIBERATELY ABSENT. Every HRV statistic -- HF power, RMSSD, SDNN --
#: is contaminated when the window it covers contains a large change in heart
#: rate, because the change itself is variability. Over a seven-second clip in
#: which simulated arousal steps up, that contamination is the whole signal:
#: measured directly, HF-HRV ROSE by 3x and RMSSD by 1.6x exactly where both
#: should have fallen, under plain periodogram, linear detrending and a Hann
#: window alike. Twelve beats cannot support a spectral estimate and no window
#: function repairs that.
#:
#: So the short-window index reports what a short window can support and says in
#: the panel that HRV needs a longer one. The alternative was a number that moved
#: confidently in the wrong direction, which is the worst artefact this project
#: could ship on a page whose entire subject is physiological inference.
#:
#: `load_index` above keeps HRV because it runs on sixty-second windows from
#: `SimulatedCardioOculoSource.window()`, where the estimate is defensible. Two
#: indices, two window lengths, two honest answers -- not one index quietly
#: reused outside the range it works in.
SHORT_LOAD_WEIGHTS: dict[str, float] = {
    "pupil_effort": 0.62,
    "blink_rate": 0.28,
}


def rmssd(rr_ms: Sequence[float]) -> float:
    """Root mean square of successive RR differences, in ms.

    Provided because it is the statistic a reader will reach for on a short
    window, and because `tests/test_biosignals.py` uses it to pin the finding
    above: on a window spanning a rate change it moves the WRONG WAY. It is not
    used by any index. Kept, with that test, so the next person does not
    rediscover the problem by shipping it.
    """
    values = [float(r) for r in rr_ms]
    if len(values) < 2:
        raise ValueError("RMSSD needs at least two RR intervals.")
    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    return math.sqrt(sum(d * d for d in diffs) / len(diffs))


def short_window_load_index(pupil_effort_z: float, blink_rate_per_min: float) -> float:
    """Load index for a window too short to carry an HRV estimate.

    Same logistic and the same footing as `load_index` and as the risk index:
    it orders windows, it does not estimate a rate, and it carries no band and
    no threshold. Monotone in both inputs, asserted.
    """
    z = (
        SHORT_LOAD_WEIGHTS["pupil_effort"] * float(pupil_effort_z)
        + SHORT_LOAD_WEIGHTS["blink_rate"]
        * (float(blink_rate_per_min) - BLINK_REFERENCE_PER_MIN)
        / BLINK_REFERENCE_PER_MIN
    )
    return 1.0 / (1.0 + math.exp(-z))
