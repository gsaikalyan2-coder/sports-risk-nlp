"""Honesty and arithmetic tests for `src/biosignals`.

Four properties, and the reason each one is a test rather than a convention:

    (a) a window cannot exist without its stamp   -> the renderer is the step
                                                     most likely to be
                                                     reimplemented, so the check
                                                     cannot live there
    (b) the ethics gate checks a CLASS, not a flag -> a runtime-checkable
                                                     Protocol's isinstance only
                                                     checks attribute presence,
                                                     so an object with
                                                     `simulated = True` glued on
                                                     passes it. That is the
                                                     "related by assumption"
                                                     defect this repository has
                                                     found seven times
    (c) the features are arithmetic, checked       -> every fixture below is a
        against numbers computed on paper             closed form a reader can
                                                     verify without running the
                                                     code
    (d) the simulator is reproducible              -> a screenshot in the paper
                                                     has to be regenerable, and
                                                     a source holding an
                                                     advancing RNG would make
                                                     `window(3)` depend on what
                                                     was called before it
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from src.biosignals.features import (
    ALPHA_BAND,
    BETA_BAND,
    DELTA_BAND,
    LOAD_WEIGHTS,
    THETA_BAND,
    alpha_theta_ratio,
    band_power,
    blink_rate,
    hf_hrv,
    load_index,
    pupil_effort,
    relative_band_power,
)
from src.biosignals.sources import (
    SIMULATED_STAMP,
    BiosignalSource,
    BiosignalWindow,
    EthicsGateError,
    SimulatedCardioOculoSource,
    SimulatedEEGSource,
    SimulatedSource,
    require_simulated,
)

# A window whose bin spacing is exactly 0.5 Hz, so 6 Hz and 10 Hz land on bin
# centres (12 and 20) and the closed forms below are exact rather than leaky.
FS = 128.0
N = 256


def cosine(
    freq_hz: float,
    amplitude: float = 1.0,
    *,
    n: int = N,
    fs: float = FS,
    phase: float = 0.0,
):
    return tuple(amplitude * math.cos(2.0 * math.pi * freq_hz * (i / fs) + phase) for i in range(n))


def a_window(**overrides) -> BiosignalWindow:
    kwargs = {
        "source": "fixture",
        "stamp": SIMULATED_STAMP,
        "index": 0,
        "t0_s": 0.0,
        "sample_rate_hz": FS,
        "channels": {"eeg": cosine(10.0)},
        "features": {"alpha_power": 0.5},
    }
    kwargs.update(overrides)
    return BiosignalWindow(**kwargs)


# ---------------------------------------------------------------------------
# (a) a window cannot exist without its stamp
# ---------------------------------------------------------------------------


def test_a_window_without_a_stamp_cannot_be_constructed():
    with pytest.raises(ValueError, match="SIMULATED"):
        a_window(stamp="")
    with pytest.raises(ValueError, match="SIMULATED"):
        a_window(stamp="   ")
    with pytest.raises(ValueError, match="SIMULATED"):
        a_window(stamp="recorded from a participant on 2026-09-13")


def test_the_stamp_check_is_on_the_word_not_on_the_default_sentence():
    """A source may extend the sentence; it may not drop the word that matters."""
    extended = SIMULATED_STAMP + " Seed 7, 256 samples at 128 Hz."
    assert a_window(stamp=extended).stamp == extended
    # Case is not a way around it.
    assert a_window(stamp="simulated — generated, not recorded").stamp


def test_a_window_refuses_a_malformed_channel_or_feature():
    with pytest.raises(ValueError, match="empty"):
        a_window(channels={"eeg": ()})
    with pytest.raises(ValueError, match="non-finite"):
        a_window(channels={"eeg": (1.0, float("nan"))})
    with pytest.raises(ValueError, match="not finite"):
        a_window(features={"alpha_power": float("inf")})
    with pytest.raises(ValueError, match="positive"):
        a_window(sample_rate_hz=0.0)


def test_a_windows_numbers_cannot_be_rewritten_after_its_guards_have_passed():
    """A frozen dataclass holding a plain dict is frozen in name only.

    The caller keeps a live reference to the mapping it passed in, so without the
    copy in `__post_init__` every guard above could pass and the numbers could
    then be replaced -- including replacing them with numbers from somewhere
    else entirely.
    """
    channels = {"eeg": list(cosine(10.0))}
    window = a_window(channels=channels)
    channels["eeg"][0] = 999.0
    assert window.channels["eeg"][0] != 999.0
    with pytest.raises(TypeError):
        window.channels["eeg"] = (0.0,)  # type: ignore[index]
    with pytest.raises(TypeError):
        window.features["alpha_power"] = 0.0  # type: ignore[index]


def test_duration_is_derived_from_the_channels_and_not_stored():
    assert a_window().duration_s == pytest.approx(N / FS)


# ---------------------------------------------------------------------------
# (b) the ethics gate
# ---------------------------------------------------------------------------


def test_the_gate_lets_a_real_simulated_source_through():
    source = SimulatedEEGSource(seed=1)
    assert require_simulated(source) is source


def test_the_gate_refuses_an_object_that_merely_claims_to_be_simulated():
    """The defect this repository keeps finding, in its Phase 26 costume.

    `BiosignalSource` is a runtime-checkable Protocol, so `isinstance` against it
    checks only that the attribute names exist. The impostor below satisfies the
    Protocol completely. If the gate had been written against the Protocol, or
    against `source.simulated`, a hardware source would pass it by setting one
    attribute -- and the failure would be silent, in a phase whose entire point
    is that nothing touches a human being.
    """

    class Impostor:
        name = "polar-h10"
        stamp = SIMULATED_STAMP
        simulated = True

        def window(self, index: int) -> BiosignalWindow:
            return a_window(index=index)

    impostor = Impostor()
    assert isinstance(impostor, BiosignalSource), "the Protocol is satisfied, as expected"
    assert impostor.simulated is True
    with pytest.raises(EthicsGateError, match="ethics"):
        require_simulated(impostor)


def test_the_gate_refuses_none_and_a_bare_window():
    with pytest.raises(EthicsGateError):
        require_simulated(None)
    with pytest.raises(EthicsGateError):
        require_simulated(a_window())


def test_the_gate_names_the_documents_that_must_be_updated_first():
    """The message is the handover. A future session meets this exception before
    it meets `.claude.md` §11.2, so the exception has to carry the gate itself."""
    with pytest.raises(EthicsGateError) as excinfo:
        require_simulated(object())
    message = str(excinfo.value)
    assert "docs/ethics.md" in message
    assert "docs/model_card.md" in message
    assert "clinician" in message


def test_a_simulated_source_cannot_be_built_without_a_stamp():
    with pytest.raises(ValueError, match="SIMULATED"):
        SimulatedEEGSource(stamp="live capture")


def test_simulated_is_a_property_with_no_setter():
    """So a subclass cannot quietly assign its way out of being simulated."""
    source = SimulatedEEGSource(seed=1)
    with pytest.raises(AttributeError):
        source.simulated = False  # type: ignore[misc]
    assert isinstance(SimulatedSource.simulated, property)
    assert SimulatedSource.simulated.fset is None


def test_the_abstract_base_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        SimulatedSource(name="x", seed=1)  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# (c) the features are arithmetic, and the arithmetic is checked on paper
# ---------------------------------------------------------------------------


def test_band_power_of_a_pure_cosine_is_half_its_amplitude_squared():
    """A cosine of amplitude A on a bin centre has mean-square power A**2 / 2.

    10 Hz at 128 Hz over 256 samples is bin 20 exactly, so this is an identity,
    not an approximation. Any change to the DFT scaling breaks this line.
    """
    for amplitude, expected in ((1.0, 0.5), (2.0, 2.0), (0.5, 0.125)):
        series = cosine(10.0, amplitude)
        assert band_power(series, FS, *ALPHA_BAND) == pytest.approx(expected, rel=1e-9)


def test_band_power_is_zero_outside_the_band_that_holds_the_signal():
    series = cosine(10.0, 2.0)
    assert band_power(series, FS, *THETA_BAND) == pytest.approx(0.0, abs=1e-9)
    assert band_power(series, FS, *DELTA_BAND) == pytest.approx(0.0, abs=1e-9)
    assert band_power(series, FS, *BETA_BAND) == pytest.approx(0.0, abs=1e-9)


def test_band_power_of_a_constant_series_is_zero_in_every_band():
    """The mean is removed first, so a DC offset is not power in the lowest bins."""
    flat = tuple(3.7 for _ in range(N))
    for band in (DELTA_BAND, THETA_BAND, ALPHA_BAND, BETA_BAND):
        assert band_power(flat, FS, *band) == pytest.approx(0.0, abs=1e-12)


def test_band_power_adds_over_two_tones_in_different_bands():
    """Parseval, in the only form this module needs it: two cosines on distinct
    bin centres contribute their own power and nothing to each other."""
    alpha = cosine(10.0, 2.0)
    theta = cosine(6.0, 1.0)
    mixed = tuple(a + t for a, t in zip(alpha, theta, strict=True))
    assert band_power(mixed, FS, *ALPHA_BAND) == pytest.approx(2.0, rel=1e-9)
    assert band_power(mixed, FS, *THETA_BAND) == pytest.approx(0.5, rel=1e-9)


def test_band_power_is_monotone_in_amplitude():
    previous = -1.0
    for amplitude in (0.25, 0.5, 1.0, 2.0, 4.0):
        power = band_power(cosine(10.0, amplitude), FS, *ALPHA_BAND)
        assert power > previous
        previous = power


def test_band_power_does_not_depend_on_phase():
    """A power spectrum discards phase; a version that did not would make the
    simulator's per-window random phase show up as a wandering feature value."""
    reference = band_power(cosine(10.0, 1.0, phase=0.0), FS, *ALPHA_BAND)
    for phase in (0.3, 1.1, 2.7, 5.9):
        assert band_power(cosine(10.0, 1.0, phase=phase), FS, *ALPHA_BAND) == pytest.approx(
            reference, rel=1e-9
        )


def test_band_power_refuses_inputs_it_cannot_answer_for():
    with pytest.raises(ValueError, match="positive"):
        band_power(cosine(10.0), 0.0, *ALPHA_BAND)
    with pytest.raises(ValueError, match="low < high"):
        band_power(cosine(10.0), FS, 13.0, 8.0)
    with pytest.raises(ValueError, match="two samples"):
        band_power((1.0,), FS, *ALPHA_BAND)


def test_relative_band_power_of_a_single_tone_is_one():
    series = cosine(10.0, 2.0)
    assert relative_band_power(series, FS, *ALPHA_BAND) == pytest.approx(1.0, rel=1e-9)
    assert relative_band_power(series, FS, *THETA_BAND) == pytest.approx(0.0, abs=1e-9)


def test_relative_band_power_of_two_equal_tones_splits_in_half():
    mixed = tuple(a + t for a, t in zip(cosine(10.0, 1.0), cosine(6.0, 1.0), strict=True))
    assert relative_band_power(mixed, FS, *ALPHA_BAND) == pytest.approx(0.5, rel=1e-9)
    assert relative_band_power(mixed, FS, *THETA_BAND) == pytest.approx(0.5, rel=1e-9)


def test_the_alpha_theta_ratio_is_a_division_and_refuses_to_invent_a_ceiling():
    assert alpha_theta_ratio(2.0, 0.5) == pytest.approx(4.0)
    assert alpha_theta_ratio(0.5, 2.0) == pytest.approx(0.25)
    with pytest.raises(ValueError, match="undefined"):
        alpha_theta_ratio(1.0, 0.0)
    with pytest.raises(ValueError, match="negative"):
        alpha_theta_ratio(-1.0, 1.0)


# ---------------------------------------------------------------------------
# (d) the simulator is reproducible
# ---------------------------------------------------------------------------


def test_the_same_seed_and_index_give_an_identical_window():
    a = SimulatedEEGSource(seed=42).window(3)
    b = SimulatedEEGSource(seed=42).window(3)
    assert a.channels["eeg"] == b.channels["eeg"]
    assert a.features == b.features


def test_a_window_does_not_depend_on_what_was_asked_for_before_it():
    """The property a paper figure depends on, and the one an RNG held on the
    instance would silently break: the simulator is a function of (seed, index),
    not a stream with a position in it."""
    fresh = SimulatedEEGSource(seed=42).window(3)
    source = SimulatedEEGSource(seed=42)
    for index in (0, 1, 2, 7, 11):
        source.window(index)
    assert source.window(3).channels["eeg"] == fresh.channels["eeg"]


def test_different_seeds_give_different_windows():
    a = SimulatedEEGSource(seed=1).window(0)
    b = SimulatedEEGSource(seed=2).window(0)
    assert a.channels["eeg"] != b.channels["eeg"]


def test_every_window_the_source_emits_carries_the_stamp():
    source = SimulatedEEGSource(seed=5)
    for window in source.stream(6):
        assert "SIMULATED" in window.stamp.upper()
        assert window.source == "simulated-eeg"


def test_the_stream_is_consecutive_and_pure():
    source = SimulatedEEGSource(seed=5)
    first = source.stream(4)
    assert [w.index for w in first] == [0, 1, 2, 3]
    assert [w.channels["eeg"] for w in source.stream(4)] == [w.channels["eeg"] for w in first]


def test_the_alpha_theta_ratio_rises_and_falls_over_the_drift_cycle():
    """The behaviour V5's ring exists to show. Asserted on the amplitude schedule
    (a closed form) and then on the realised feature, so a change to the noise
    level cannot quietly flatten the thing the panel is animating."""
    source = SimulatedEEGSource(seed=9)
    quarter = source.DRIFT_PERIOD // 4
    assert source.alpha_amplitude(quarter) > source.alpha_amplitude(0)
    assert source.alpha_amplitude(3 * quarter) < source.alpha_amplitude(0)

    ratios = [source.window(i).features["alpha_theta_ratio"] for i in range(source.DRIFT_PERIOD)]
    assert max(ratios) > min(ratios) * 1.5, "the drift is too small for a ring to show it"
    assert ratios.index(max(ratios)) != 0, "the peak should not sit at the start of the cycle"


def test_the_windows_features_are_the_ones_the_panels_will_read():
    window = SimulatedEEGSource(seed=3).window(0)
    assert set(window.features) == {"alpha_power", "theta_power", "alpha_theta_ratio"}
    assert window.features["alpha_theta_ratio"] == pytest.approx(
        window.features["alpha_power"] / window.features["theta_power"], rel=1e-12
    )


# ---------------------------------------------------------------------------
# (e) the risk index does not move -- Phase 26 gate #2, in its cheapest form
# ---------------------------------------------------------------------------


def test_a_windows_context_mapping_cannot_collide_with_a_construct_name():
    """Every key is prefixed, so a biosignal feature can never be mistaken for a
    construct probability if the two mappings are ever merged by a future page."""
    window = SimulatedEEGSource(seed=3).window(0)
    context = window.context()
    assert context
    assert all(key.startswith("biosignal_") for key in context)
    assert set(context) == {f"biosignal_{name}" for name in window.features}


def test_the_risk_index_is_bit_identical_with_and_without_the_context_mapping():
    """Phase 26 gate #2. The seam has been in `src/risk/fusion.py` since Phase 15
    and `score()` only touches `total` inside `if self.context_weights and context`.
    Asserted here with a real window rather than a hand-written dict, so the test
    goes on protecting the index if what a source emits ever changes shape.

    Lives in this file rather than in a page because
    `tests/test_dashboard_pages.py` forbids a page importing `src.risk` at all.
    """
    from src.dashboard.view import DEFAULT_POLICY_LABEL, scorer_for

    scorer = scorer_for(DEFAULT_POLICY_LABEL)
    assert scorer.context_weights == {}, "Phase 26 configures no context weights"

    probabilities = {
        "cognitive_anxiety": 0.81,
        "somatic_anxiety": 0.44,
        "self_confidence": 0.22,
        "burnout_signal": 0.17,
    }
    window = SimulatedEEGSource(seed=3).window(0)

    without = scorer.score(probabilities)
    with_context = scorer.score(probabilities, context=window.context())

    assert with_context.index == without.index
    assert with_context.raw_score == without.raw_score
    assert with_context.contributions == without.contributions
    assert with_context.context_used == ()


# ---------------------------------------------------------------------------
# (f) V3 — the cognitive-load feature functions
# ---------------------------------------------------------------------------


def test_hf_hrv_of_a_constant_rr_series_is_zero():
    """No variability, no variability power. The identity the channel rests on."""
    assert hf_hrv([850.0] * 64) == pytest.approx(0.0, abs=1e-9)


def test_hf_hrv_scales_with_the_square_of_the_variation():
    """A cosine of amplitude A has mean-square power A**2/2, so doubling the
    swing quadruples HF power. Checked against the closed form, not against a
    previous run, so a change to the scaling breaks this line."""
    import math as _m

    base = [850.0 + 30.0 * _m.cos(2 * _m.pi * n / 4.0) for n in range(64)]
    doubled = [850.0 + 60.0 * _m.cos(2 * _m.pi * n / 4.0) for n in range(64)]
    assert hf_hrv(doubled) == pytest.approx(4.0 * hf_hrv(base), rel=1e-6)


def test_hf_hrv_refuses_inputs_it_cannot_answer_for():
    with pytest.raises(ValueError, match="two RR"):
        hf_hrv([850.0])
    with pytest.raises(ValueError, match="positive"):
        hf_hrv([850.0, -1.0, 850.0])
    with pytest.raises(ValueError, match="Nyquist"):
        # 30 bpm: the HF band sits above Nyquist, so the question is unanswerable
        # rather than answerable-with-a-caveat. Returning a number here would be
        # the worst option available.
        hf_hrv([2000.0 + (n % 2) * 40 for n in range(32)])


def test_pupil_effort_is_the_mean_and_is_not_clipped():
    assert pupil_effort([1.0, 2.0, 3.0]) == pytest.approx(2.0)
    assert pupil_effort([-1.0, -3.0]) == pytest.approx(-2.0)
    with pytest.raises(ValueError):
        pupil_effort([])


def test_blink_rate_counts_flags_per_minute():
    assert blink_rate([0, 1, 0, 1], 60.0) == pytest.approx(2.0)
    assert blink_rate([1] * 10, 30.0) == pytest.approx(20.0)
    assert blink_rate([0] * 10, 60.0) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        blink_rate([1], 0.0)


def test_the_load_index_is_monotone_in_every_channel():
    """A meter that can move the wrong way for one channel cannot be explained,
    and the explanation is the whole product here."""
    base = load_index(400.0, 0.0, 20.0)
    assert load_index(800.0, 0.0, 20.0) < base, "more HRV must read as calmer"
    assert load_index(100.0, 0.0, 20.0) > base
    assert load_index(400.0, 1.0, 20.0) > base, "more pupil effort must read as busier"
    assert load_index(400.0, -1.0, 20.0) < base
    assert load_index(400.0, 0.0, 40.0) > base
    assert load_index(400.0, 0.0, 5.0) < base


def test_the_load_index_is_bounded_and_its_weights_are_stated_not_fitted():
    for hf in (0.0, 50.0, 5000.0):
        for pupil in (-4.0, 0.0, 4.0):
            for blink in (0.0, 60.0):
                assert 0.0 <= load_index(hf, pupil, blink) <= 1.0
    assert set(LOAD_WEIGHTS) == {"hf_hrv", "pupil_effort", "blink_rate"}
    assert LOAD_WEIGHTS["hf_hrv"] < 0 < LOAD_WEIGHTS["pupil_effort"]
    # The shakiest term carries the smallest weight, deliberately -- see the
    # comment on LOAD_WEIGHTS about blink-rate direction being a choice.
    assert abs(LOAD_WEIGHTS["blink_rate"]) == min(abs(w) for w in LOAD_WEIGHTS.values())


def test_the_cardio_source_is_seeded_and_stamped():
    a = SimulatedCardioOculoSource(seed=3).window(5)
    b = SimulatedCardioOculoSource(seed=3).window(5)
    assert a.channels["rr_ms"] == b.channels["rr_ms"]
    assert a.features == b.features
    assert "SIMULATED" in a.stamp.upper()
    assert SimulatedCardioOculoSource(seed=4).window(5).channels["rr_ms"] != a.channels["rr_ms"]


def test_the_cardio_source_moves_hrv_and_pupil_in_opposite_directions():
    """The correlation the V3 panel exists to show, imposed by construction in
    the simulator and asserted here so a change to the drift cannot flatten it."""
    source = SimulatedCardioOculoSource(seed=9)
    calm = source.window(source.DRIFT_PERIOD * 3 // 4)  # arousal at its minimum
    strained = source.window(source.DRIFT_PERIOD // 4)  # arousal at its maximum
    assert source.arousal(source.DRIFT_PERIOD // 4) > source.arousal(source.DRIFT_PERIOD * 3 // 4)
    assert strained.features["hf_hrv"] < calm.features["hf_hrv"]
    assert strained.features["pupil_effort"] > calm.features["pupil_effort"]
    assert strained.features["load_index"] > calm.features["load_index"]


def test_the_cardio_window_context_is_still_ignored_by_the_scorer():
    """Gate #2 again, for V3's channels rather than V1's."""
    from src.dashboard.view import DEFAULT_POLICY_LABEL, scorer_for

    scorer = scorer_for(DEFAULT_POLICY_LABEL)
    probabilities = {"cognitive_anxiety": 0.6, "somatic_anxiety": 0.3}
    window = SimulatedCardioOculoSource(seed=3).window(0)
    without = scorer.score(probabilities)
    with_context = scorer.score(probabilities, context=window.context())
    assert with_context.index == without.index
    assert with_context.context_used == ()


# ---------------------------------------------------------------------------
# (g) V5 — the session state machine, checked on paper
# ---------------------------------------------------------------------------


def test_the_session_counters_match_arithmetic_done_by_hand():
    from src.biosignals.session import NeurofeedbackSession

    session = NeurofeedbackSession(target=1.0, tick_s=1.0)
    #        below, below, ON,  ON,  below, ON,  ON,  ON,  below
    ratios = [0.4, 0.9, 1.2, 1.5, 0.8, 1.1, 1.4, 1.0, 0.2]
    state = session.run(ratios)
    assert state.ticks == 9
    assert state.elapsed_s == pytest.approx(9.0)
    assert state.in_target_s == pytest.approx(5.0)  # two + three
    assert state.longest_hold_s == pytest.approx(3.0)
    assert state.current_hold_s == pytest.approx(0.0)
    assert state.in_target_fraction == pytest.approx(5.0 / 9.0)


def test_the_target_boundary_is_inclusive():
    """A ratio sitting exactly on the target is the value a participant would be
    trying hardest to hold; a strict comparison refuses to credit it."""
    from src.biosignals.session import NeurofeedbackSession

    session = NeurofeedbackSession(target=1.0)
    assert session.run([1.0]).in_target_s == pytest.approx(1.0)
    assert session.run([0.999]).in_target_s == pytest.approx(0.0)


def test_a_reset_clears_both_counters():
    from src.biosignals.session import NeurofeedbackSession

    session = NeurofeedbackSession(target=1.0)
    assert session.run([2.0, 2.0, 2.0]).longest_hold_s == pytest.approx(3.0)
    fresh = session.reset()
    assert fresh.in_target_s == 0.0 and fresh.longest_hold_s == 0.0 and fresh.ticks == 0
    assert fresh.in_target_fraction == 0.0


def test_the_session_state_is_frozen_so_history_stays_answerable():
    from src.biosignals.session import NeurofeedbackSession

    session = NeurofeedbackSession(target=1.0)
    states = session.trace([2.0, 0.5, 2.0])
    assert [s.in_target_s for s in states] == [1.0, 1.0, 2.0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        states[0].in_target_s = 99.0  # type: ignore[misc]


def test_a_session_refuses_a_target_that_every_ratio_meets():
    from src.biosignals.session import NeurofeedbackSession

    with pytest.raises(ValueError, match="target"):
        NeurofeedbackSession(target=0.0)
    with pytest.raises(ValueError, match="target"):
        NeurofeedbackSession(target=-1.0)
    with pytest.raises(ValueError, match="tick_s"):
        NeurofeedbackSession(target=1.0, tick_s=0.0)


def test_the_tick_length_scales_the_counters_and_nothing_else():
    from src.biosignals.session import NeurofeedbackSession

    ratios = [2.0, 2.0, 0.1]
    one = NeurofeedbackSession(target=1.0, tick_s=1.0).run(ratios)
    half = NeurofeedbackSession(target=1.0, tick_s=0.5).run(ratios)
    assert half.in_target_s == pytest.approx(one.in_target_s / 2)
    assert half.ticks == one.ticks
    assert half.in_target_fraction == pytest.approx(one.in_target_fraction)
