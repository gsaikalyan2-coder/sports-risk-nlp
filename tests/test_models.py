"""Tests for the Phase 13 dataset assembler and classical baselines.

Offline, deterministic, no network, no spend. Same contract as the other suites.

The two tests that carry real weight are `test_identical_seeds_give_bitwise_identical_metrics`
-- because "reproducible baseline macro-F1 recorded" is the literal wording of
the Phase 13 gate, and a gate phrased that way is only met by an equality check
at full float precision -- and the pair asserting that `load_gold` refuses while
`data/gold/` is empty. The second is the one that stops a future session from
quietly evaluating against silver and calling the result accuracy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.evaluation import macro_f1, micro_f1, template_disjoint_split
from src.ingestion import generate_records
from src.ingestion.records import RawRecord
from src.models.classical import (
    DEFAULT_FEATURES,
    LinearSVCBaseline,
    LogisticRegressionBaseline,
    training_fingerprint,
)
from src.models.dataset import (
    CONSTRUCTS,
    Dataset,
    NoEvaluableLabels,
    deduplicate,
    load_gold,
    load_silver,
    planted_labels,
)


@pytest.fixture(scope="module")
def records() -> list[RawRecord]:
    return generate_records(400, seed=42, source_id="models_test")


@pytest.fixture(scope="module")
def labels(records: list[RawRecord]) -> list[frozenset[str]]:
    return [planted_labels(r) for r in records]


# ---------------------------------------------------------------------------
# Dataset assembly
# ---------------------------------------------------------------------------


def test_planted_labels_read_the_generation_spec(records, labels):
    assert any(labels), "the generator plants constructs; none were read"
    for label_set in labels:
        assert label_set <= set(CONSTRUCTS)


def test_deduplicate_collapses_repeated_texts():
    a = RawRecord(record_id="r2", source_id="s", text="same text")
    b = RawRecord(record_id="r1", source_id="s", text="same text")
    c = RawRecord(record_id="r3", source_id="s", text="different")
    kept, kept_labels, collapsed, ambiguous = deduplicate(
        [a, b, c], [frozenset({"resilience"}), frozenset({"resilience"}), frozenset()]
    )
    assert len(kept) == 2
    assert collapsed == 1
    assert ambiguous == 0
    # Lowest record_id within the group wins, so the choice is not shuffle-dependent.
    assert {r.record_id for r in kept} == {"r1", "r3"}
    assert kept_labels[kept.index(next(r for r in kept if r.record_id == "r1"))] == frozenset(
        {"resilience"}
    )


def test_deduplicate_drops_texts_whose_copies_disagree():
    """A text mapping to two label sets is unlearnable; keeping one would be noise."""
    a = RawRecord(record_id="r1", source_id="s", text="ambiguous")
    b = RawRecord(record_id="r2", source_id="s", text="ambiguous")
    kept, _, _, ambiguous = deduplicate(
        [a, b], [frozenset({"resilience"}), frozenset({"coping_style"})]
    )
    assert kept == ()
    assert ambiguous == 1


def test_deduplicate_is_order_independent(records, labels):
    forward = deduplicate(records, labels)
    backward = deduplicate(list(reversed(records)), list(reversed(labels)))
    assert [r.record_id for r in forward[0]] == [r.record_id for r in backward[0]]
    assert forward[1] == backward[1]


def test_dataset_refuses_misaligned_records_and_labels():
    with pytest.raises(ValueError, match="positionally aligned"):
        Dataset(
            name="x",
            label_source="planted",
            records=(RawRecord(record_id="r1", source_id="s", text="t"),),
            labels=(),
        )


def test_dataset_reports_constructs_with_no_support():
    dataset = Dataset(
        name="x",
        label_source="planted",
        records=(RawRecord(record_id="r1", source_id="s", text="t"),),
        labels=(frozenset({"resilience"}),),
    )
    missing = dataset.constructs_without_support
    assert "resilience" not in missing
    assert len(missing) == len(CONSTRUCTS) - 1


# ---------------------------------------------------------------------------
# The refusals. These are the point of the module.
# ---------------------------------------------------------------------------


def test_load_gold_refuses_while_the_gold_directory_is_empty(tmp_path: Path):
    with pytest.raises(NoEvaluableLabels) as excinfo:
        load_gold("synth_precomp_v1", gold_root=tmp_path)
    message = str(excinfo.value)
    assert "OPEN-025" in message
    # The refusal must name the fallback it is declining, or a future reader
    # will "fix" the error by adding exactly that fallback.
    assert "silver" in message.lower()


def test_load_gold_does_not_silently_fall_back_to_silver(tmp_path: Path):
    """The whole harness is shaped to make this substitution impossible."""
    with pytest.raises(NoEvaluableLabels):
        load_gold("synth_precomp_v1", gold_root=tmp_path)


def test_load_silver_requires_an_explicit_acknowledgement():
    with pytest.raises(NoEvaluableLabels) as excinfo:
        load_silver("synth_precomp_v1")
    assert "PRNG" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Classical baselines
# ---------------------------------------------------------------------------


def test_classical_models_fit_and_predict_label_sets(records, labels):
    model = LogisticRegressionBaseline(seed=42).fit(records, labels)
    predictions = model.predict(records[:20])
    assert len(predictions) == 20
    for prediction in predictions:
        assert prediction <= set(CONSTRUCTS)


def test_a_construct_with_no_positives_gets_a_constant_zero_not_a_crash(records):
    """Four constructs are unattested in silver. That must not raise, and must not
    be papered over by dropping them from the label set."""
    stripped = [label_set - {"resilience"} for label_set in (planted_labels(r) for r in records)]
    model = LogisticRegressionBaseline(seed=42).fit(records, stripped)
    assert "resilience" in model._degenerate
    assert all("resilience" not in p for p in model.predict(records[:10]))
    # Still in the label space, so macro-F1 keeps its denominator of 10.
    assert "resilience" in model.constructs


def test_identical_seeds_give_bitwise_identical_metrics(records, labels):
    """The Phase 13 gate says "reproducible". This is what that word means.

    Full float equality, not `pytest.approx`. An approximate check would pass
    while a nondeterministic solver wandered in the sixth decimal, and the whole
    point of pinning the solver and the seed is that it does not.
    """
    split = template_disjoint_split(records, test_size=0.2, seed=42)
    index = {r.record_id: ls for r, ls in zip(records, labels, strict=True)}
    y_train = [index[r.record_id] for r in split.train]
    y_test = [index[r.record_id] for r in split.test]

    scores = []
    for _ in range(2):
        model = LogisticRegressionBaseline(seed=42).fit(split.train, y_train)
        predicted = model.predict(split.test)
        scores.append(
            (macro_f1(y_test, predicted, CONSTRUCTS), micro_f1(y_test, predicted, CONSTRUCTS))
        )
    assert scores[0] == scores[1]


def test_both_classifiers_are_reproducible(records, labels):
    for factory in (LogisticRegressionBaseline, LinearSVCBaseline):
        first = factory(seed=42).fit(records, labels).predict(records[:50])
        second = factory(seed=42).fit(records, labels).predict(records[:50])
        assert first == second, f"{factory.__name__} is not deterministic"


def test_the_training_fingerprint_changes_when_a_label_changes(records, labels):
    original = training_fingerprint(records, labels)
    mutated = list(labels)
    mutated[0] = mutated[0] ^ {"resilience"}
    assert training_fingerprint(records, mutated) != original


def test_the_training_fingerprint_ignores_row_order(records, labels):
    """A fingerprint that moved with the shuffle would flag every reordered run."""
    pairs = list(zip(records, labels, strict=True))
    shuffled = list(reversed(pairs))
    assert training_fingerprint(records, labels) == training_fingerprint(
        [r for r, _ in shuffled], [ls for _, ls in shuffled]
    )


def test_the_manifest_records_what_is_needed_to_reproduce_a_run(records, labels):
    model = LogisticRegressionBaseline(seed=7).fit(records, labels)
    manifest = model.manifest()
    assert manifest["seed"] == 7
    assert manifest["sklearn_version"]
    assert manifest["n_train"] == len(records)
    assert manifest["training_fingerprint"] == training_fingerprint(records, labels)
    assert manifest["features"]["word_ngram_range"] == list(DEFAULT_FEATURES["word_ngram_range"])
    assert manifest["constructs"] == list(CONSTRUCTS)


def test_a_saved_model_writes_its_manifest_beside_it(records, labels, tmp_path: Path):
    model = LogisticRegressionBaseline(seed=42).fit(records, labels)
    directory = model.save(tmp_path / "m")
    assert (directory / "model.joblib").exists()
    assert (directory / "manifest.json").exists()


def test_predict_before_fit_is_an_error(records):
    with pytest.raises(RuntimeError, match="fit\\(\\) before predict\\(\\)"):
        LogisticRegressionBaseline().predict(records[:5])


def test_the_classical_models_memorise_a_random_split_far_better_than_a_disjoint_one(
    records, labels
):
    """The headline Phase 13 finding, asserted so a refactor cannot erase it.

    A linear model over TF-IDF features scores near-perfectly when templates are
    shared between train and test, and collapses when they are not. If this test
    ever starts failing because the gap closed, that is not a fixed test -- it is
    a corpus whose leakage properties changed, and Phase 14 needs to know.
    """
    from src.evaluation import random_split

    index = {r.record_id: ls for r, ls in zip(records, labels, strict=True)}

    def score(split) -> float:
        y_train = [index[r.record_id] for r in split.train]
        y_test = [index[r.record_id] for r in split.test]
        model = LinearSVCBaseline(seed=42).fit(split.train, y_train)
        return macro_f1(y_test, model.predict(split.test), CONSTRUCTS)

    leaky = score(random_split(records, test_size=0.2, seed=42))
    honest = score(template_disjoint_split(records, test_size=0.2, seed=42))
    assert leaky > honest + 0.2, (
        f"expected a large memorisation gap; got random={leaky:.3f} "
        f"disjoint={honest:.3f}. The split may have stopped being disjoint."
    )
