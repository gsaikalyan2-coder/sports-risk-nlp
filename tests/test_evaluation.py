"""Tests for the evaluation harness (OPEN-012) and the de-id fixture (OPEN-013).

Offline, deterministic, no network. Same contract as the other suites.

The tests that matter most are the leakage ones. They assert that a
template-disjoint split is actually disjoint and that a memoriser collapses
under it -- which is the evidence that the split is doing its job rather than
merely claiming to.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation import (
    LexiconBaseline,
    MajorityBaseline,
    MemorisationProbe,
    StratifiedRandomBaseline,
    bootstrap_ci,
    leakage_report,
    macro_f1,
    micro_f1,
    paired_bootstrap_p_value,
    per_label_prf,
    random_split,
    subset_accuracy,
    template_disjoint_split,
    templates_of,
)
from src.ingestion import generate_records

FIXTURE_DIR = Path(__file__).parent / "fixtures"
DEID_CASES = FIXTURE_DIR / "deid_cases.jsonl"

CONSTRUCTS = (
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


@pytest.fixture(scope="module")
def corpus():
    return generate_records(600, seed=42, source_id="eval_test")


def planted(record) -> frozenset[str]:
    spec = record.generation_spec or {}
    return frozenset(p["construct"] for p in spec.get("planted_constructs", ()))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_perfect_prediction_scores_one():
    y = [frozenset({"a"}), frozenset({"a", "b"}), frozenset()]
    assert macro_f1(y, y, ("a", "b")) == 1.0
    assert subset_accuracy(y, y) == 1.0


def test_empty_prediction_scores_zero():
    y_true = [frozenset({"a"}), frozenset({"b"})]
    y_pred = [frozenset(), frozenset()]
    assert macro_f1(y_true, y_pred, ("a", "b")) == 0.0


def test_prf_arithmetic_is_correct():
    # label "a": tp=1 (r0), fp=1 (r1), fn=1 (r2)  -> P=.5 R=.5 F1=.5
    y_true = [frozenset({"a"}), frozenset(), frozenset({"a"})]
    y_pred = [frozenset({"a"}), frozenset({"a"}), frozenset()]
    prf = per_label_prf(y_true, y_pred, ("a",))["a"]
    assert prf.precision == 0.5
    assert prf.recall == 0.5
    assert prf.f1 == 0.5
    assert prf.support == 2


def test_macro_and_micro_differ_under_imbalance():
    """Macro must not let a frequent label mask a neglected rare one."""
    y_true = [frozenset({"common"})] * 20 + [frozenset({"rare"})]
    y_pred = [frozenset({"common"})] * 20 + [frozenset()]
    labels = ("common", "rare")
    assert micro_f1(y_true, y_pred, labels) > macro_f1(y_true, y_pred, labels)
    assert per_label_prf(y_true, y_pred, labels)["rare"].f1 == 0.0


def test_length_mismatch_is_an_error():
    with pytest.raises(ValueError, match="length mismatch"):
        per_label_prf([frozenset({"a"})], [], ("a",))


def test_bootstrap_ci_brackets_the_point_estimate():
    y_true = [frozenset({"a"}) if i % 3 else frozenset({"b"}) for i in range(120)]
    y_pred = [frozenset({"a"}) if i % 4 else frozenset({"b"}) for i in range(120)]
    ci = bootstrap_ci(
        y_true, y_pred, lambda t, p: macro_f1(t, p, ("a", "b")), n_resamples=200, seed=1
    )
    assert ci.low <= ci.point <= ci.high
    assert 0.0 < ci.width < 1.0


def test_bootstrap_ci_is_deterministic():
    y_true = [frozenset({"a"})] * 50
    y_pred = [frozenset({"a"}) if i % 2 else frozenset() for i in range(50)]
    metric = lambda t, p: macro_f1(t, p, ("a",))  # noqa: E731
    a = bootstrap_ci(y_true, y_pred, metric, n_resamples=100, seed=7)
    b = bootstrap_ci(y_true, y_pred, metric, n_resamples=100, seed=7)
    assert (a.point, a.low, a.high) == (b.point, b.low, b.high)


def test_identical_systems_are_not_significantly_different():
    y_true = [frozenset({"a"}) if i % 2 else frozenset({"b"}) for i in range(80)]
    y_pred = [frozenset({"a"})] * 80
    p = paired_bootstrap_p_value(
        y_true, y_pred, y_pred, lambda t, q: macro_f1(t, q, ("a", "b")), n_resamples=200
    )
    assert p == 1.0


def test_clearly_better_system_is_significant():
    y_true = [frozenset({"a"})] * 100
    good = [frozenset({"a"})] * 100
    bad = [frozenset()] * 100
    p = paired_bootstrap_p_value(
        y_true, good, bad, lambda t, q: macro_f1(t, q, ("a",)), n_resamples=200
    )
    assert p < 0.05


# ---------------------------------------------------------------------------
# Splits -- the core OPEN-012 guarantee
# ---------------------------------------------------------------------------


def test_generated_records_expose_template_ids(corpus):
    with_constructs = [r for r in corpus if planted(r)]
    assert with_constructs
    for record in with_constructs:
        assert templates_of(record), f"{record.record_id} has constructs but no template_id"


def test_random_split_leaks_templates(corpus):
    """The foil. If this ever stops leaking, the audit has lost its contrast."""
    split = random_split(corpus, seed=42)
    assert split.shared_templates
    assert not split.is_template_disjoint


def test_template_disjoint_split_shares_no_template(corpus):
    """GATE for OPEN-012: no template may appear on both sides."""
    split = template_disjoint_split(corpus, seed=42)
    assert split.shared_templates == frozenset()
    assert split.is_template_disjoint


def test_template_disjoint_split_has_no_exact_text_overlap(corpus):
    """Template-free records could still duplicate verbatim across the split."""
    split = template_disjoint_split(corpus, seed=42)
    assert leakage_report(split).exact_text_overlap == 0.0


def test_disjoint_split_reports_what_it_discarded(corpus):
    split = template_disjoint_split(corpus, seed=42)
    total = len(split.train) + len(split.test) + len(split.discarded)
    assert total == len(corpus), "records must not vanish silently"
    assert split.discarded, "straddling records exist and must be accounted for"


def test_disjoint_split_keeps_both_halves_non_empty(corpus):
    split = template_disjoint_split(corpus, seed=42)
    assert len(split.train) > 50
    assert len(split.test) > 20


def test_disjoint_split_has_lower_ngram_overlap_than_random(corpus):
    rnd = leakage_report(random_split(corpus, seed=42))
    dis = leakage_report(template_disjoint_split(corpus, seed=42))
    assert dis.ngram_overlap[8] < rnd.ngram_overlap[8]


def test_splits_are_deterministic(corpus):
    a = template_disjoint_split(corpus, seed=3)
    b = template_disjoint_split(corpus, seed=3)
    assert [r.record_id for r in a.test] == [r.record_id for r in b.test]


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_majority_baseline_predicts_one_constant_set(corpus):
    y = [planted(r) for r in corpus]
    preds = MajorityBaseline().fit(corpus, y).predict(corpus)
    assert len(set(preds)) == 1


def test_stratified_random_baseline_is_seeded(corpus):
    y = [planted(r) for r in corpus]
    a = StratifiedRandomBaseline(seed=5).fit(corpus, y).predict(corpus)
    b = StratifiedRandomBaseline(seed=5).fit(corpus, y).predict(corpus)
    assert a == b


def test_lexicon_baseline_beats_chance(corpus):
    y = [planted(r) for r in corpus]
    lex = LexiconBaseline().fit(corpus, y).predict(corpus)
    rnd = StratifiedRandomBaseline(seed=1).fit(corpus, y).predict(corpus)
    assert macro_f1(y, lex, CONSTRUCTS) > macro_f1(y, rnd, CONSTRUCTS)


def test_lexicon_baseline_ignores_training_labels(corpus):
    """It must be leakage-immune, which is why it is the control in the audit."""
    y = [planted(r) for r in corpus]
    scrambled = [frozenset({"burnout_signal"}) for _ in corpus]
    assert LexiconBaseline().fit(corpus, y).predict(corpus) == LexiconBaseline().fit(
        corpus, scrambled
    ).predict(corpus)


def test_memorisation_probe_collapses_on_a_disjoint_split(corpus):
    """The headline OPEN-012 evidence.

    A pure memoriser should do well when templates are shared and badly when
    they are not. If this assertion ever fails, either the split has stopped
    isolating templates or the corpus has stopped being template-generated --
    both of which invalidate every downstream number.
    """
    rnd = random_split(corpus, seed=42)
    dis = template_disjoint_split(corpus, seed=42)

    def score(split):
        y_tr = [planted(r) for r in split.train]
        y_te = [planted(r) for r in split.test]
        pred = MemorisationProbe().fit(split.train, y_tr).predict(split.test)
        return macro_f1(y_te, pred, CONSTRUCTS)

    assert score(rnd) - score(dis) > 0.15


def test_baselines_require_fit_before_predict(corpus):
    with pytest.raises(RuntimeError):
        StratifiedRandomBaseline().predict(corpus)
    with pytest.raises(RuntimeError):
        MemorisationProbe().predict(corpus)


# ---------------------------------------------------------------------------
# De-identification fixture (OPEN-013)
# ---------------------------------------------------------------------------


def _load_cases():
    return [
        json.loads(line)
        for line in DEID_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_deid_fixture_exists_and_parses():
    assert DEID_CASES.exists(), "OPEN-013 fixture is missing"
    assert len(_load_cases()) >= 30


def test_deid_fixture_case_ids_are_unique():
    ids = [c["case_id"] for c in _load_cases()]
    assert len(ids) == len(set(ids))


def test_deid_fixture_has_required_fields():
    required = {"case_id", "category", "difficulty", "text", "expected", "expected_placeholders"}
    for case in _load_cases():
        assert required <= set(case), f"{case.get('case_id')} is missing {required - set(case)}"


def test_deid_fixture_has_negatives_to_catch_over_redaction():
    """A de-identifier that blanks everything must be able to fail."""
    negatives = [c for c in _load_cases() if c["category"] == "negative"]
    assert len(negatives) >= 6
    for case in negatives:
        assert case["text"] == case["expected"], f"{case['case_id']}: negative must be unchanged"
        assert case["expected_placeholders"] == []


def test_deid_fixture_positives_actually_change():
    for case in _load_cases():
        if case["category"] == "negative":
            continue
        assert case["text"] != case["expected"], f"{case['case_id']}: positive case is unchanged"


def test_deid_fixture_placeholders_match_the_expected_text():
    for case in _load_cases():
        for placeholder in case["expected_placeholders"]:
            assert placeholder in case["expected"], (
                f"{case['case_id']}: {placeholder} not in expected"
            )


def test_deid_fixture_health_cases_remove_rather_than_placeholder():
    """docs/ethics.md 5.1: health detail is deleted, not typed-placeholdered."""
    health = [c for c in _load_cases() if c["category"] == "health"]
    assert health
    for case in health:
        assert case["expected_placeholders"] == []
        assert len(case["expected"]) < len(case["text"])


def test_deid_fixture_preserves_relative_timing():
    """Contribution #3 must survive de-identification."""
    for case in _load_cases():
        low = case["text"].lower()
        if "days out" in low or "three days" in low or "two days" in low:
            assert "days out" in case["expected"].lower(), case["case_id"]


def test_deid_fixture_covers_the_ethics_removal_table():
    categories = {c["category"] for c in _load_cases()}
    for required in ("person_name", "handle", "contact", "team_org", "location", "event", "health"):
        assert required in categories, f"no fixture case for {required}"


def test_deid_fixture_spans_difficulty_bands():
    bands = {c["difficulty"] for c in _load_cases()}
    assert {"easy", "medium", "hard"} <= bands


def test_deid_fixture_is_not_in_the_corpus():
    """It is a test artefact. It must never be ingested."""
    raw = Path(__file__).resolve().parents[1] / "data" / "raw"
    for records_file in raw.glob("*/records.jsonl"):
        body = records_file.read_text(encoding="utf-8")
        assert "Marcus Halloway" not in body
        assert "Northgate Harriers" not in body
