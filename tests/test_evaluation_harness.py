"""Phase 18 tests -- the harness, the ablations, and the claim ledger.

No torch anywhere in this file. That is the point of the Phase 18 architecture
(see `src/evaluation/harness.py`): if the invariants below could only be checked
with the ML stack installed, they would be checked rarely, which is the same as
not being checked. Every fixture here is hand-built, so the expected values are
computable by hand and the tests fail for one reason each.
"""

from __future__ import annotations

import json

import pytest

from src.evaluation.ablations import (
    CLAIMS,
    Ablation,
    AblationStatus,
    ClaimLedger,
    fusion_ablation,
    refuse_transformer_silver_ablation,
    risk_sensitivity,
)
from src.evaluation.harness import (
    PROVISIONAL_STAMP,
    MisalignedPredictions,
    PredictionSet,
    assert_not_accuracy,
    compare_systems,
    error_profile,
    load_cache,
    score_predictions,
)

CONSTRUCTS = ("a", "b", "c")


def make_set(
    system: str = "sys",
    *,
    split: str = "template_disjoint",
    y_true=None,
    y_pred=None,
    record_ids=None,
    y_prob=None,
    label_source: str = "planted",
    provenance: str = PROVISIONAL_STAMP,
) -> PredictionSet:
    y_true = y_true if y_true is not None else [frozenset({"a"}), frozenset({"b"})]
    y_pred = y_pred if y_pred is not None else [frozenset({"a"}), frozenset()]
    record_ids = record_ids or tuple(f"r{i}" for i in range(len(y_true)))
    return PredictionSet(
        system=system,
        split=split,
        label_source=label_source,
        constructs=CONSTRUCTS,
        record_ids=tuple(record_ids),
        y_true=tuple(y_true),
        y_pred=tuple(y_pred),
        y_prob=y_prob,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# PredictionSet invariants
# ---------------------------------------------------------------------------


def test_misaligned_lengths_are_rejected_at_construction():
    """The failure this guards is silent: a plausible score against shuffled truth."""
    with pytest.raises(ValueError, match="positionally aligned"):
        make_set(y_true=[frozenset({"a"})], y_pred=[frozenset(), frozenset()], record_ids=("r0",))


def test_duplicate_record_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicate record_ids"):
        make_set(record_ids=("r0", "r0"))


def test_probability_rows_must_match_construct_width():
    with pytest.raises(ValueError, match="wrong width"):
        make_set(y_prob=((0.1, 0.2), (0.3, 0.4)))


def test_probabilities_for_refuses_when_there_are_none():
    """Returning {} instead would score as risk 0.0 -- a number, which would be reported."""
    ps = make_set()
    with pytest.raises(ValueError, match="no probabilities"):
        ps.probabilities_for(0)


def test_probabilities_for_maps_onto_construct_names():
    ps = make_set(y_prob=((0.1, 0.2, 0.7), (0.4, 0.5, 0.6)))
    assert ps.probabilities_for(1) == {"a": 0.4, "b": 0.5, "c": 0.6}


def test_round_trip_through_disk_preserves_everything(tmp_path):
    ps = make_set(y_prob=((0.1, 0.2, 0.7), (0.4, 0.5, 0.6)))
    path = ps.save(tmp_path)
    assert PredictionSet.load(path) == ps


def test_load_cache_keys_on_split_and_system(tmp_path):
    make_set("alpha").save(tmp_path)
    make_set("beta", split="random").save(tmp_path)
    cache = load_cache(tmp_path)
    assert set(cache) == {("template_disjoint", "alpha"), ("random", "beta")}


# ---------------------------------------------------------------------------
# The no-accuracy invariant
# ---------------------------------------------------------------------------


def test_planted_labels_without_the_stamp_are_refused():
    """The guard is a no-op today and stops being one the day gold exists."""
    with pytest.raises(ValueError, match="provenance stamp is missing"):
        assert_not_accuracy([make_set(provenance="Results.")])


def test_gold_labelled_sets_are_exempt():
    """Nothing in the repo produces this yet; the exemption is what it will need."""
    assert_not_accuracy([make_set(label_source="gold", provenance="human-verified")])


def test_score_dict_always_declares_it_is_not_accuracy():
    assert score_predictions(make_set(), n_resamples=20).as_dict()["is_accuracy"] is False


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def test_perfect_predictions_score_one_on_attested_constructs():
    truth = [frozenset({"a"}), frozenset({"b"}), frozenset({"a", "b"})]
    score = score_predictions(
        make_set(y_true=truth, y_pred=truth), n_resamples=20, labels=("a", "b")
    )
    assert score.macro_f1.point == 1.0
    assert score.subset_accuracy == 1.0


def test_unattested_construct_drags_macro_f1_down_by_a_fixed_amount():
    """A macro-F1 over 3 constructs when only 2 are attested is capped at 2/3.

    This is a property of the label source, not of the model, and Phase 18's
    report says so -- so it is worth a test that pins the arithmetic.
    """
    truth = [frozenset({"a"}), frozenset({"b"})]
    score = score_predictions(
        make_set(y_true=truth, y_pred=truth), n_resamples=20, labels=CONSTRUCTS
    )
    assert score.macro_f1.point == pytest.approx(2 / 3)
    assert score.constructs_at_zero == ("c",)


def test_comparison_refuses_misaligned_record_orderings():
    """Same split name, same length, different partition -> a plausible wrong p-value."""
    a = make_set("a", record_ids=("r0", "r1"))
    b = make_set("b", record_ids=("r9", "r8"))
    with pytest.raises(MisalignedPredictions, match="record orderings"):
        compare_systems(a, b, n_resamples=20)


def test_comparison_refuses_across_splits():
    with pytest.raises(MisalignedPredictions, match="cannot pair"):
        compare_systems(make_set("a"), make_set("b", split="random"), n_resamples=20)


def test_comparison_reports_the_direction_of_the_gap():
    truth = [frozenset({"a"}), frozenset({"a"}), frozenset({"a"}), frozenset({"a"})]
    good = make_set("good", y_true=truth, y_pred=truth)
    bad = make_set("bad", y_true=truth, y_pred=[frozenset()] * 4)
    comparison = compare_systems(good, bad, n_resamples=50, labels=("a",))
    assert comparison.delta > 0
    assert comparison.verdict in {"A beats B", "no separation"}


# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------


def test_confusions_only_count_swaps_within_a_single_record():
    """Pairing every miss with every invention corpus-wide manufactures confusions
    between constructs that never co-occurred on one record."""
    ps = make_set(
        y_true=[frozenset({"a"}), frozenset({"b"})],
        y_pred=[frozenset({"c"}), frozenset({"b"})],
    )
    profile = error_profile(ps)
    assert profile.confusions == {("a", "c"): 1}
    assert profile.false_positives == {"c": 1}
    assert profile.false_negatives == {"a": 1}


def test_error_profile_carries_no_text():
    """docs/ethics.md: no verbatim corpus text in any published artifact."""
    payload = json.dumps(error_profile(make_set()).as_dict())
    assert "text" not in json.loads(payload)
    assert set(json.loads(payload)["worst_record_ids"]) <= {"r0", "r1"}


def test_load_bands_separate_the_no_construct_records():
    ps = make_set(
        y_true=[frozenset(), frozenset({"a"}), frozenset({"a", "b"})],
        y_pred=[frozenset({"a"}), frozenset({"a"}), frozenset({"a", "b"})],
        record_ids=("r0", "r1", "r2"),
    )
    bands = error_profile(ps).by_load_band
    assert bands["0 constructs"] == (1, 1)
    assert bands["1 construct"] == (1, 0)
    assert bands["2 constructs"] == (1, 0)


# ---------------------------------------------------------------------------
# Ablations
# ---------------------------------------------------------------------------


def test_measured_ablation_must_carry_a_measurement():
    """A green badge over an empty result is the OPEN-007 failure mode."""
    with pytest.raises(ValueError, match="neither a comparison nor"):
        Ablation(id="x", question="?", status=AblationStatus.MEASURED, rationale="looks fine")


def test_refused_ablation_must_explain_itself():
    with pytest.raises(ValueError, match="no rationale"):
        Ablation(id="x", question="?", status=AblationStatus.REFUSED, rationale="  ")


def test_the_silver_refusal_names_the_issue_it_is_blocked_on():
    refusal = refuse_transformer_silver_ablation()
    assert refusal.status is AblationStatus.REFUSED
    assert "OPEN-028" in refusal.rationale
    assert refusal.detail["blocked_by"] == ["OPEN-028", "OPEN-008"]


# ---------------------------------------------------------------------------
# Risk-layer sensitivity
# ---------------------------------------------------------------------------

FULL_CONSTRUCTS = (
    "appraisal_orientation",
    "attentional_focus",
    "burnout_signal",
    "cognitive_anxiety",
    "coping_style",
    "motivation_orientation",
    "perceived_stress",
    "resilience",
    "self_confidence",
    "somatic_anxiety",
)


def _rows(n: int = 12) -> list[dict[str, float]]:
    return [
        {name: ((i * 7 + j * 3) % 10) / 10.0 for j, name in enumerate(FULL_CONSTRUCTS)}
        for i in range(n)
    ]


def test_risk_sensitivity_shares_sum_to_one():
    sensitivity = risk_sensitivity(_rows())
    assert sum(sensitivity.contribution_share.values()) == pytest.approx(1.0)


def test_risk_sensitivity_is_deterministic_under_a_fixed_seed():
    a = risk_sensitivity(_rows(), seed=7)
    b = risk_sensitivity(_rows(), seed=7)
    assert a.perturbation_rho == b.perturbation_rho


def test_risk_sensitivity_refuses_an_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        risk_sensitivity([])


def test_fusion_ablation_flags_a_layer_that_only_reproduces_a_count():
    """If the index orders records the same way counting does, the paper must say so."""
    sensitivity = risk_sensitivity(_rows())
    ablation = fusion_ablation(sensitivity)
    assert ablation.status is AblationStatus.MEASURED
    assert "circular" in ablation.rationale
    assert ablation.detail["is_accuracy"] is False


# ---------------------------------------------------------------------------
# The claim ledger == the Phase 18 gate
# ---------------------------------------------------------------------------


def test_every_claim_has_a_distinct_id_and_a_nonempty_evidence_key():
    ids = [c.id for c in CLAIMS]
    assert len(ids) == len(set(ids))
    assert all(c.evidence_key.strip() for c in CLAIMS)


def test_an_empty_payload_leaves_every_claim_unbacked():
    assert len(ClaimLedger().unbacked({})) == len(CLAIMS)


def test_a_present_but_empty_evidence_key_does_not_count_as_backing():
    """`{}` is the shape a partially-written report has, and it must not pass."""
    payload = {"comparisons": {"transformer_vs_lexicon": {}}}
    assert "transformer_beats_lexicon" in {c.id for c in ClaimLedger().unbacked(payload)}


def test_evidence_that_contradicts_a_claim_does_not_back_it():
    """Regression, 2026-08-13, found by the first real run of the harness.

    The `silver_is_noise` claim then read "training on silver degrades a model".
    The ablation measured delta=+0.033 at p=0.110 -- no significant change in
    either direction -- and the gate went green, because the presence-only audit
    saw an evidence key and stopped looking. A gate that certifies a claim its
    own evidence contradicts is worse than no gate: it launders the claim.
    """
    payload = {
        "comparisons": {
            "transformer_vs_lexicon": {"delta": -0.2, "significant": True},
        }
    }
    assert "transformer_beats_lexicon" in {c.id for c in ClaimLedger().unbacked(payload)}


def test_a_nonsignificant_gap_does_not_back_a_beats_claim():
    payload = {"comparisons": {"transformer_vs_lexicon": {"delta": 0.4, "significant": False}}}
    assert "transformer_beats_lexicon" in {c.id for c in ClaimLedger().unbacked(payload)}


def test_a_significant_silver_improvement_would_break_the_no_signal_claim():
    """If PRNG labels ever significantly *helped*, that needs explaining, not certifying."""
    payload = {
        "ablations": {
            "silver_classical": {
                "status": "measured",
                "comparison": {"delta": 0.3, "significant": True},
            }
        }
    }
    assert "silver_is_noise" in {c.id for c in ClaimLedger().unbacked(payload)}


def test_zeroed_constructs_are_counted_not_hidden():
    """Polarity-bearing constructs are inert under the NEUTRAL default; say so."""
    sensitivity = risk_sensitivity(_rows())
    assert set(sensitivity.zeroed_constructs) <= set(FULL_CONSTRUCTS)
    assert all(sensitivity.contribution_share[c] == 0 for c in sensitivity.zeroed_constructs)


def test_a_fully_populated_payload_backs_every_claim():
    payload = {
        "provenance": PROVISIONAL_STAMP,
        "scores": {"template_disjoint::transformer": {"macro_f1": 0.5}},
        "comparisons": {
            "transformer_vs_lexicon": {"delta": 0.1, "significant": True},
            "split_gap": {"delta": 0.3},
        },
        "ablations": {
            "silver_classical": {
                "status": "measured",
                "comparison": {"delta": 0.03, "significant": False},
            },
            "risk_fusion": {"status": "measured"},
        },
        "explainability": {"faithfulness": {"comprehensiveness_margin": 0.3}},
        # Added at Phase 22 with the `reproduction_tolerance` claim. The two
        # hashes must agree: `declared_sha256` is frozen when the tolerances are
        # declared and `plan_sha256` is recomputed from
        # src/reproducibility/manifest.py, so a tolerance widened after a run
        # makes them diverge and the claim goes unbacked. See
        # tests/test_reproducibility.py for that case measured directly.
        "reproduction": {
            "declaration": {
                "retrain_tolerance_macro_f1": 0.010,
                "declared_sha256": "a" * 64,
                "plan_sha256": "a" * 64,
            }
        },
    }
    assert ClaimLedger().unbacked(payload) == ()


# ---------------------------------------------------------------------------
# Import-order regression (OPEN-036)
# ---------------------------------------------------------------------------


def test_explainability_imports_standalone_in_a_fresh_interpreter():
    """`import src.explainability` must work when nothing else is imported first.

    This is a subprocess test on purpose, and the subprocess IS the test. Phase
    18 added `from .ablations import ...` to `src/evaluation/__init__.py`, and
    `ablations` imported `src.explainability.faithfulness` at module level. That
    closed a cycle:

        src.evaluation/__init__ -> ablations -> explainability.faithfulness
        -> explainability.attribution -> models.dataset -> models/__init__
        -> classical -> evaluation.baselines -> src.evaluation/__init__

    The cycle only bites when `src.explainability` is imported before
    `src.evaluation`. A full-suite run imports them in the safe order, so
    `pytest -q` passed 100% while `pytest tests/test_explainability.py` raised
    ImportError. Any in-process assertion here would inherit the parent's
    already-populated sys.modules and pass for the wrong reason.

    The fix is a function-local import in `ablations.risk_sensitivity`. If
    someone hoists it back to module level to tidy the file up, this fails.
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import src.explainability.attribution"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr
    assert "partially initialized" not in combined and "circular import" not in combined, (
        "src.explainability cannot be imported first -- the Phase 18 import cycle is back:\n"
        + combined
    )
