"""Tests for the Phase 15 risk layer.

Offline, deterministic, no network, no spend, no torch, no sklearn. The risk
layer runs in the light Docker image and this suite must too.

The tests carrying the most weight are the ones guarding properties that a later
"optimisation" or "cleanup" would break silently, producing a number rather than
an error:

* `test_scores_do_not_depend_on_the_batch_they_were_scored_in` -- the moment a
  batch statistic enters the score, the same athlete's text gets a different risk
  index depending on who else was in the run.
* `test_an_unresolved_polarity_contributes_nothing_by_default` -- guessing a
  direction manufactures risk from missing information.
* `test_calibrating_the_risk_index_is_refused` -- the fused index has no outcome
  to calibrate against, and the obvious proxy is a restatement of its own inputs.
* `test_temperature_scaling_preserves_ranking` -- if calibration reordered
  anything, every F1 already reported upstream would need re-running.
* `test_passing_context_to_a_text_only_scorer_changes_nothing` -- the text-only
  path is the primary reported model and must not drift.
"""

from __future__ import annotations

import math

import pytest

from src.risk import (
    DEFAULT_MAGNITUDES,
    Direction,
    LinearRiskScorer,
    PolarityPolicy,
    RiskCalibrationUnavailable,
    apply_temperature,
    calibrate_risk_index,
    expected_calibration_error,
    fit_temperature,
    load_directions,
    reliability_table,
)

ANXIOUS = {"cognitive_anxiety": 0.9, "somatic_anxiety": 0.8, "perceived_stress": 0.7}
CONFIDENT = {"self_confidence": 0.9, "resilience": 0.8}


# ---------------------------------------------------------------------------
# Directions come from the taxonomy, not from this file
# ---------------------------------------------------------------------------


def test_directions_are_read_from_the_taxonomy():
    directions = load_directions()
    assert directions["cognitive_anxiety"] is Direction.RAISES
    assert directions["self_confidence"] is Direction.LOWERS
    assert directions["resilience"] is Direction.LOWERS


def test_the_four_polarity_bearing_constructs_are_recognised_as_polar():
    """The taxonomy states these as prose, so they must parse to POLAR rather
    than to a silently-assigned sign."""
    directions = load_directions()
    for construct in (
        "motivation_orientation",
        "attentional_focus",
        "coping_style",
        "appraisal_orientation",
    ):
        assert directions[construct] is Direction.POLAR, construct


def test_every_taxonomy_construct_has_a_default_magnitude():
    """A construct present in the taxonomy but absent from the weights would
    silently fall back to 1.0 and never be noticed."""
    assert set(load_directions()) == set(DEFAULT_MAGNITUDES)


# ---------------------------------------------------------------------------
# Fusion direction
# ---------------------------------------------------------------------------


def test_anxiety_raises_risk_and_confidence_lowers_it():
    scorer = LinearRiskScorer()
    assert scorer.score(ANXIOUS).index > 0.5
    assert scorer.score(CONFIDENT).index < 0.5


def test_resilience_is_protective_not_aggravating():
    """The taxonomy is explicit that resilience LOWERS risk. Treating any detected
    construct as risk-raising would invert it.
    """
    scorer = LinearRiskScorer()
    without = scorer.score({"cognitive_anxiety": 0.9})
    with_resilience = scorer.score({"cognitive_anxiety": 0.9, "resilience": 0.9})
    assert with_resilience.index < without.index


def test_threat_appraisal_raises_and_challenge_appraisal_lowers():
    scorer = LinearRiskScorer()
    threat = scorer.score(
        {"appraisal_orientation": 0.9}, polarities={"appraisal_orientation": "threat"}
    )
    challenge = scorer.score(
        {"appraisal_orientation": 0.9}, polarities={"appraisal_orientation": "challenge"}
    )
    assert threat.index > 0.5 > challenge.index


def test_debilitative_interpretation_raises_risk_at_equal_anxiety():
    """The Jones1992 point, and one of the things that makes this more than
    sentiment analysis: identical anxiety intensity, different risk.
    """
    scorer = LinearRiskScorer()
    same_anxiety = {"cognitive_anxiety": 0.8}
    debilitative = scorer.score(same_anxiety, interpretation="debilitative")
    unclear = scorer.score(same_anxiety, interpretation="unclear")
    facilitative = scorer.score(same_anxiety, interpretation="facilitative")
    assert debilitative.index > unclear.index > facilitative.index


def test_an_unresolved_polarity_contributes_nothing_by_default():
    """Guessing a direction manufactures risk from missing information."""
    scorer = LinearRiskScorer()
    result = scorer.score({"appraisal_orientation": 0.9})
    contribution = next(c for c in result.contributions if c.construct == "appraisal_orientation")
    assert contribution.contribution == 0.0
    assert contribution.polarity_unresolved is True
    assert result.index == pytest.approx(0.5)


def test_the_pessimistic_policy_exists_only_as_an_ablation():
    """It must actually differ from the default, or the sensitivity analysis
    comparing them is comparing a thing to itself."""
    row = {"appraisal_orientation": 0.9}
    neutral = LinearRiskScorer(polarity_policy=PolarityPolicy.NEUTRAL).score(row)
    pessimistic = LinearRiskScorer(polarity_policy=PolarityPolicy.PESSIMISTIC).score(row)
    optimistic = LinearRiskScorer(polarity_policy=PolarityPolicy.OPTIMISTIC).score(row)
    assert pessimistic.index > neutral.index > optimistic.index


def test_an_unrecognised_sub_label_does_not_silently_pick_a_sign():
    scorer = LinearRiskScorer()
    result = scorer.score(
        {"coping_style": 0.9}, polarities={"coping_style": "something_unexpected"}
    )
    contribution = next(c for c in result.contributions if c.construct == "coping_style")
    assert contribution.polarity_unresolved is True
    assert contribution.contribution == 0.0


# ---------------------------------------------------------------------------
# Score properties
# ---------------------------------------------------------------------------


def test_the_index_is_bounded():
    scorer = LinearRiskScorer()
    extreme_high = scorer.score(dict.fromkeys(DEFAULT_MAGNITUDES, 1.0))
    assert 0.0 <= extreme_high.index <= 1.0
    huge = scorer.score({"cognitive_anxiety": 1.0}, context=None)
    assert 0.0 <= huge.index <= 1.0


def test_no_constructs_detected_gives_a_neutral_score():
    assert LinearRiskScorer().score({}).index == pytest.approx(0.5)


def test_scores_do_not_depend_on_the_batch_they_were_scored_in():
    """Min-max normalisation over a batch would break this.

    If it broke, the same athlete's text would receive a different risk index
    depending on which other records happened to be scored alongside it -- which
    is indefensible for anything decision-adjacent, and would not raise an error.
    """
    scorer = LinearRiskScorer()
    alone = scorer.score(ANXIOUS).index
    in_a_calm_batch = scorer.score_many([ANXIOUS, CONFIDENT, CONFIDENT, CONFIDENT])[0].index
    in_a_tense_batch = scorer.score_many([ANXIOUS, ANXIOUS, ANXIOUS])[0].index
    assert alone == in_a_calm_batch == in_a_tense_batch


def test_the_score_is_never_marked_calibrated_by_default():
    """`is_calibrated` gates whether a consumer may read the index as a
    probability. It must default to False."""
    assert LinearRiskScorer().score(ANXIOUS).is_calibrated is False


def test_provenance_travels_with_the_number():
    """A bare float labelled 'risk 0.82' that escapes into a slide is a claim
    about a person with nothing attached saying where it came from."""
    result = LinearRiskScorer().score(ANXIOUS)
    assert "OPEN-025" in result.provenance
    assert "not a judgement about any real person" in result.provenance


# ---------------------------------------------------------------------------
# Decomposition readability -- Phase 15 gate condition 2
# ---------------------------------------------------------------------------


def test_contributions_sum_to_the_raw_score():
    """The decomposition must actually explain the number, not approximate it.

    An explanation whose parts do not sum to the whole is the kind of thing a
    reviewer checks first, and the interpretability contribution depends on it.
    """
    result = LinearRiskScorer().score({**ANXIOUS, **CONFIDENT})
    assert sum(c.contribution for c in result.contributions) == pytest.approx(result.raw_score)


def test_the_explanation_names_the_drivers_and_their_direction():
    text = LinearRiskScorer().score({**ANXIOUS, **CONFIDENT}).explain()
    assert "Risk index" in text
    assert "cognitive_anxiety" in text
    assert "raised" in text
    assert "lowered" in text


def test_the_explanation_flags_that_the_score_is_uncalibrated():
    assert "RANKING ONLY" in LinearRiskScorer().score(ANXIOUS).explain()


def test_the_explanation_reports_excluded_unresolved_constructs():
    """Silently dropping them would make the decomposition not add up from the
    reader's point of view, even though it adds up arithmetically."""
    text = LinearRiskScorer().score({"cognitive_anxiety": 0.8, "coping_style": 0.9}).explain()
    assert "unresolved" in text
    assert "coping_style" in text


def test_top_drivers_are_ordered_by_absolute_effect():
    result = LinearRiskScorer().score(
        {"cognitive_anxiety": 0.2, "perceived_stress": 0.9, "self_confidence": 0.5}
    )
    effects = [abs(c.contribution) for c in result.top_drivers]
    assert effects == sorted(effects, reverse=True)


# ---------------------------------------------------------------------------
# Context interface -- Phase 15 gate condition 3
# ---------------------------------------------------------------------------


def test_passing_context_to_a_text_only_scorer_changes_nothing():
    """The text-only path is the primary reported model. It must be bit-identical
    whether or not context is passed, or it would drift the moment someone
    started experimenting with context features.
    """
    scorer = LinearRiskScorer()
    without = scorer.score(ANXIOUS)
    with_ignored_context = scorer.score(ANXIOUS, context={"training_load": 0.9})
    assert without.index == with_ignored_context.index
    assert with_ignored_context.context_used == ()


def test_a_configured_context_weight_is_applied_and_recorded():
    scorer = LinearRiskScorer(context_weights={"training_load": 1.0})
    result = scorer.score(ANXIOUS, context={"training_load": 0.9})
    assert result.index > scorer.score(ANXIOUS).index
    assert result.context_used == ("training_load",)


def test_a_context_feature_with_no_weight_is_ignored():
    scorer = LinearRiskScorer(context_weights={"training_load": 1.0})
    result = scorer.score(ANXIOUS, context={"phase_of_moon": 0.9})
    assert result.context_used == ()


def test_the_manifest_records_whether_the_run_was_text_only():
    assert LinearRiskScorer().manifest()["text_only"] is True
    assert LinearRiskScorer(context_weights={"x": 1.0}).manifest()["text_only"] is False


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def test_a_perfectly_calibrated_predictor_has_near_zero_ece():
    probabilities = [0.05] * 100 + [0.5] * 100 + [0.95] * 100
    outcomes = [1] * 5 + [0] * 95 + [1] * 50 + [0] * 50 + [1] * 95 + [0] * 5
    assert expected_calibration_error(probabilities, outcomes) < 0.02


def test_a_confidently_wrong_predictor_has_high_ece():
    probabilities = [0.99] * 100
    outcomes = [0] * 100
    assert expected_calibration_error(probabilities, outcomes) > 0.9


def test_probability_one_lands_in_the_last_bin_rather_than_being_dropped():
    report = reliability_table([1.0] * 10, [1] * 10, n_bins=10)
    assert report.n == 10
    assert sum(b.count for b in report.bins) == 10


def test_ece_weights_bins_by_population():
    """A tiny badly-calibrated bin must not dominate a large well-calibrated one."""
    probabilities = [0.5] * 999 + [0.99]
    outcomes = [1] * 500 + [0] * 499 + [0]
    assert expected_calibration_error(probabilities, outcomes) < 0.01


def test_mismatched_lengths_are_refused():
    with pytest.raises(ValueError):
        reliability_table([0.5, 0.5], [1])


def test_temperature_scaling_preserves_ranking():
    """Temperature scaling is a monotone transform of the logit.

    This is why it is the right calibrator here: it cannot reorder anything, so
    it cannot change any F1 already reported upstream, and calibration becomes a
    strictly additive claim rather than a reason to re-run Phases 13 and 14.
    """
    probabilities = [0.1, 0.25, 0.4, 0.6, 0.75, 0.9]
    for temperature in (0.3, 0.8, 1.0, 2.5, 7.0):
        scaled = apply_temperature(probabilities, temperature)
        assert scaled == sorted(scaled), temperature


def test_temperature_one_is_a_no_op():
    probabilities = [0.1, 0.5, 0.9]
    for original, scaled in zip(probabilities, apply_temperature(probabilities, 1.0), strict=True):
        assert scaled == pytest.approx(original, abs=1e-9)


def test_fitting_temperature_softens_an_over_confident_predictor():
    """Over-confident means T > 1: the logits need shrinking toward 0.5."""
    probabilities = [0.99] * 50 + [0.01] * 50
    outcomes = [1] * 35 + [0] * 15 + [0] * 35 + [1] * 15
    assert fit_temperature(probabilities, outcomes) > 1.0


def test_fitting_temperature_reduces_ece_on_the_data_it_was_fitted_on():
    """The weakest possible calibration claim, asserted because if it fails the
    optimiser is broken. The runner evaluates on held-out data instead."""
    probabilities = [0.99] * 50 + [0.01] * 50
    outcomes = [1] * 35 + [0] * 15 + [0] * 35 + [1] * 15
    temperature = fit_temperature(probabilities, outcomes)
    before = expected_calibration_error(probabilities, outcomes)
    after = expected_calibration_error(apply_temperature(probabilities, temperature), outcomes)
    assert after < before


def test_fitting_temperature_on_nothing_is_a_no_op_not_a_crash():
    assert fit_temperature([], []) == 1.0


def test_extreme_probabilities_do_not_overflow():
    for temperature in (0.05, 1.0, 10.0):
        for probability in (0.0, 1.0):
            value = apply_temperature([probability], temperature)[0]
            assert 0.0 <= value <= 1.0
            assert not math.isnan(value)


def test_calibrating_the_risk_index_is_refused():
    """The single most load-bearing refusal in this module.

    The fused index has no observed outcome to calibrate against. The obvious
    proxy -- 'risk = 1 if any risk-raising construct was planted' -- is a
    restatement of the fusion's own inputs and would yield a respectable ECE that
    means nothing.
    """
    with pytest.raises(RiskCalibrationUnavailable) as excinfo:
        calibrate_risk_index()
    message = str(excinfo.value)
    assert "no risk outcome exists" in message.lower()
    assert "CSAI-2" in message
    assert "proxy" in message.lower()


# ---------------------------------------------------------------------------
# The Phase 15 gate script
# ---------------------------------------------------------------------------


def test_the_gate_refuses_gold_while_the_directory_is_empty():
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        "run_risk", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "run_risk.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Exit 2 is "config error". An empty gold set is not a failed experiment.
    assert module.main(["--gold"]) == 2
