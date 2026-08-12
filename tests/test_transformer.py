"""Tests for the Phase 14 transformer module.

Offline, deterministic, no network, no spend, **no torch**. Same contract as the
other suites, with one extra constraint that shapes the whole file: torch and
transformers live in `requirements-ml.txt` and are not installed in the light
image or in CI, so this suite must exercise everything it can without them.

That turns out to cover most of what can actually go wrong. The parts of Phase
14 that are easy to get subtly and invisibly wrong are not the training loop --
a broken training loop produces an obviously broken number -- but the pure
functions around it:

* **label encoding**, where a column permutation between fit and predict yields a
  model that confidently reports the wrong construct while every shape check
  passes;
* **threshold tuning**, where fitting on the wrong slice is an optimistic bias
  that never announces itself;
* **the validation carve**, where sharing templates with the reduced training set
  silently calibrates thresholds for a leaky regime;
* **the refusals**, where a fallback to random weights or to silver labels would
  produce a plausible number that means nothing.

All of those are tested here. The training loop itself is covered by the
`--dry-run` plan check and by the integration run on the owner's machine, where
torch exists.

The two tests carrying the most weight are
`test_weights_unavailable_is_raised_rather_than_falling_back_to_random_init` and
`test_thresholds_are_never_tuned_on_the_examples_they_are_scored_on`. Both guard
against a failure that produces a number rather than an error.
"""

from __future__ import annotations

import dataclasses
import importlib.util

import pytest

from src.evaluation.splits import template_disjoint_split
from src.ingestion import generate_records
from src.ingestion.records import RawRecord
from src.models.dataset import CONSTRUCTS, planted_labels
from src.models.transformer import (
    DEFAULT_SWEEP,
    HParams,
    MLDependencyMissing,
    TransformerBaseline,
    WeightsUnavailable,
    carve_validation,
    decode_predictions,
    encode_labels,
    positive_weights,
    require_ml_stack,
    resolve_base_model,
    tune_thresholds,
)

TORCH_INSTALLED = importlib.util.find_spec("torch") is not None
needs_torch = pytest.mark.skipif(not TORCH_INSTALLED, reason="requirements-ml.txt not installed")


@pytest.fixture(scope="module")
def records() -> list[RawRecord]:
    return generate_records(200, seed=42, source_id="transformer_test")


@pytest.fixture(scope="module")
def labels(records: list[RawRecord]) -> list[frozenset[str]]:
    return [planted_labels(r) for r in records]


# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------


def test_hparams_are_frozen_so_a_logged_config_is_the_config_that_ran():
    """A configuration that can be mutated after the run is a configuration the
    run log cannot be trusted to describe.
    """
    config = HParams()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.learning_rate = 5e-5  # type: ignore[misc]


def test_slugs_distinguish_configurations_that_differ_only_in_a_minor_field():
    """Two configs differing only in weight_decay must not share a checkpoint dir.

    The readable prefix of the slug omits weight_decay, so without the
    configuration hash these two would collide and the second run would silently
    overwrite the first one's weights and manifest.
    """
    a = HParams(weight_decay=0.01)
    b = HParams(weight_decay=0.1)
    assert a.slug() != b.slug()
    assert a.slug().rsplit("_", 1)[0] == b.slug().rsplit("_", 1)[0]


def test_slug_is_stable_across_calls():
    config = HParams()
    assert config.slug() == config.slug()


def test_the_sweep_contains_no_duplicate_configurations():
    slugs = [config.slug() for config in DEFAULT_SWEEP]
    assert len(slugs) == len(set(slugs))


def test_an_epochs_override_collapses_two_sweep_points_and_must_be_deduplicated():
    """`--epochs 2` maps the 4-epoch and 6-epoch lr2e-5 configs onto one another.

    Results are keyed by slug, so without explicit deduplication the second run
    would silently overwrite the first: an hour of compute spent recomputing a
    number already held, and a report claiming six configurations over five rows.
    This pins the collision so the runner's dedup cannot be removed unnoticed.
    """
    overridden = [HParams(**{**c.as_dict(), "epochs": 2}) for c in DEFAULT_SWEEP]
    assert len(set(overridden)) < len(overridden), "expected a collision to deduplicate"
    # HParams is frozen and hashable, so dict.fromkeys preserves order and drops
    # the later duplicate -- the runner relies on both properties.
    deduped = list(dict.fromkeys(overridden))
    assert len(deduped) == len(set(overridden))
    assert deduped[0] == overridden[0]


# ---------------------------------------------------------------------------
# Label encoding
# ---------------------------------------------------------------------------


def test_encoding_uses_the_construct_order_it_was_given_not_set_iteration():
    """A column permutation is the bug this test exists to make impossible."""
    order = ("resilience", "cognitive_anxiety", "burnout_signal")
    encoded = encode_labels([frozenset({"cognitive_anxiety"})], order)
    assert encoded == [[0.0, 1.0, 0.0]]


def test_encoding_ignores_labels_outside_the_taxonomy():
    encoded = encode_labels([frozenset({"not_a_construct"})], CONSTRUCTS)
    assert sum(encoded[0]) == 0.0


def test_encode_then_decode_round_trips_at_a_half_threshold():
    original = [frozenset({"resilience", "coping_style"}), frozenset()]
    encoded = encode_labels(original, CONSTRUCTS)
    recovered = decode_predictions(encoded, [0.5] * len(CONSTRUCTS), CONSTRUCTS)
    assert list(recovered) == original


def test_the_empty_set_is_a_legitimate_prediction():
    """Records with no planted construct are common (pure logistics talk).

    An argmax-style "always predict at least one label" rule would manufacture a
    false positive on every one of them.
    """
    predictions = decode_predictions([[0.1] * len(CONSTRUCTS)], [0.5] * len(CONSTRUCTS), CONSTRUCTS)
    assert predictions == [frozenset()]


# ---------------------------------------------------------------------------
# Class weighting
# ---------------------------------------------------------------------------


@needs_torch
def test_trimming_a_batch_removes_padding_without_changing_the_real_tokens():
    """Dynamic padding must be a pure cost reduction, never a content change."""
    import torch

    from src.models.transformer import _trim_batch

    input_ids = torch.tensor([[5, 6, 0, 0, 0], [7, 8, 9, 0, 0]])
    attention_mask = torch.tensor([[1, 1, 0, 0, 0], [1, 1, 1, 0, 0]])
    trimmed_ids, trimmed_mask = _trim_batch(input_ids, attention_mask)

    assert trimmed_ids.shape[1] == 3, "should trim to the longest real sequence"
    assert torch.equal(trimmed_ids, torch.tensor([[5, 6, 0], [7, 8, 9]]))
    assert torch.equal(trimmed_mask, torch.tensor([[1, 1, 0], [1, 1, 1]]))
    # Every token the mask marks real must survive untouched.
    assert torch.equal(input_ids[attention_mask.bool()], trimmed_ids[trimmed_mask.bool()])


@needs_torch
def test_trimming_an_all_padding_batch_does_not_produce_a_zero_width_tensor():
    import torch

    from src.models.transformer import _trim_batch

    input_ids = torch.zeros((2, 4), dtype=torch.long)
    attention_mask = torch.zeros((2, 4), dtype=torch.long)
    trimmed_ids, _ = _trim_batch(input_ids, attention_mask)
    assert trimmed_ids.shape[1] == 4


def test_the_default_max_length_covers_the_longest_record_in_the_corpus():
    """128 was chosen from a measurement, and the measurement should be pinned.

    The longest record in `synth_precomp_v1` is ~93 whitespace tokens, ~125
    subword. If a future corpus revision produces longer records, silently
    truncating them would drop the end of every long utterance -- so this fails
    loudly instead.
    """
    from src.ingestion.store import RawStore

    _, corpus = RawStore().read_source("synth_precomp_v1")
    longest_words = max(len(r.text.split()) for r in corpus)
    # 1.35 is a conservative subword-per-word factor for English BPE.
    assert longest_words * 1.35 < HParams().max_length


def test_positive_weight_is_the_negative_to_positive_ratio():
    encoded = [[1.0], [0.0], [0.0], [0.0]]  # 1 positive, 3 negative
    assert positive_weights(encoded, cap=100.0) == [3.0]


def test_positive_weight_is_capped():
    encoded = [[1.0]] + [[0.0]] * 999
    assert positive_weights(encoded, cap=10.0) == [10.0]


def test_a_construct_with_no_positives_gets_weight_one_not_a_zero_division():
    assert positive_weights([[0.0], [0.0]], cap=10.0) == [1.0]


# ---------------------------------------------------------------------------
# Threshold tuning -- the optimistic-bias guard
# ---------------------------------------------------------------------------


def test_tuning_finds_a_threshold_that_separates_a_clean_column():
    order = ("resilience",)
    probabilities = [[0.9], [0.8], [0.2], [0.1]]
    truth = [[1.0], [1.0], [0.0], [0.0]]
    threshold = tune_thresholds(probabilities, truth, order)[0]
    assert 0.2 < threshold <= 0.8


def test_a_construct_with_no_validation_positives_keeps_the_default_threshold():
    """There is no F1 to maximise, so a tuned threshold would be fitting noise."""
    order = ("resilience",)
    assert tune_thresholds([[0.9], [0.1]], [[0.0], [0.0]], order) == [0.5]


def test_ties_resolve_toward_one_half_so_tuning_is_not_iteration_order_dependent():
    """Thresholds are persisted in the manifest as a reproducibility claim.

    A tie broken by grid order would make that claim depend on an implementation
    detail of the loop.
    """
    order = ("resilience",)
    probabilities = [[0.95], [0.05]]
    truth = [[1.0], [0.0]]
    assert tune_thresholds(probabilities, truth, order) == [0.5]


def test_tuning_is_per_construct_not_global():
    """Construct prevalence varies ~2x across the taxonomy; one global threshold
    systematically under-predicts the rare ones, which macro-F1 punishes hardest.
    """
    order = ("a", "b")
    probabilities = [[0.9, 0.3], [0.8, 0.25], [0.2, 0.1], [0.1, 0.05]]
    truth = [[1.0, 1.0], [1.0, 1.0], [0.0, 0.0], [0.0, 0.0]]
    thresholds = tune_thresholds(probabilities, truth, order)
    assert thresholds[0] != thresholds[1]


def test_thresholds_are_never_tuned_on_the_examples_they_are_scored_on():
    """The invariant, asserted at the level it can be asserted without torch.

    `TransformerBaseline.fit` carves its validation slice out of the records it
    was handed and `predict` is a separate call, so test records are structurally
    unreachable from the tuning code. This test pins the carve: the two index
    sets must be disjoint, must index only real records, and must invent nothing.

    They do **not** have to cover the input. `carve_validation` delegates to
    `template_disjoint_split`, which discards records whose templates straddle
    the partition -- so some training records are dropped rather than assigned.
    That is the intended cost of a clean validation slice; see the function's
    docstring.
    """
    items = generate_records(120, seed=7, source_id="carve_test")
    label_sets = [planted_labels(r) for r in items]
    train_idx, val_idx = carve_validation(items, label_sets, fraction=0.2, seed=42)
    assert set(train_idx) & set(val_idx) == set()
    assert set(train_idx) | set(val_idx) <= set(range(len(items)))
    assert val_idx, "a validation slice was requested and must be non-empty"
    assert train_idx, "the training side must survive the carve"


def test_the_validation_carve_does_not_share_templates_with_its_training_side():
    """Otherwise thresholds are calibrated on memorised phrasings, then applied to
    a template-disjoint test set -- a mismatch visible only as unexplained
    underperformance.
    """
    from src.evaluation.splits import templates_of

    items = generate_records(300, seed=11, source_id="carve_templates")
    label_sets = [planted_labels(r) for r in items]
    train_idx, val_idx = carve_validation(items, label_sets, fraction=0.2, seed=42)

    train_templates: set[str] = set()
    for i in train_idx:
        train_templates |= templates_of(items[i])
    val_templates: set[str] = set()
    for i in val_idx:
        val_templates |= templates_of(items[i])
    assert not (train_templates & val_templates)


def test_the_carve_is_deterministic_for_a_fixed_seed():
    items = generate_records(120, seed=7, source_id="carve_seed")
    label_sets = [planted_labels(r) for r in items]
    first = carve_validation(items, label_sets, fraction=0.2, seed=42)
    second = carve_validation(items, label_sets, fraction=0.2, seed=42)
    assert first == second


def test_the_carve_drops_straddling_records_rather_than_assigning_them():
    """The cost of a clean slice, asserted so it is visible rather than surprising.

    A record whose templates fall on both sides of the partition cannot go to
    either side without leaking. `template_disjoint_split` discards it, so the
    two index sets are a strict subset of the input on a corpus where records
    use several templates.
    """
    items = generate_records(300, seed=11, source_id="carve_straddle")
    label_sets = [planted_labels(r) for r in items]
    train_idx, val_idx = carve_validation(items, label_sets, fraction=0.2, seed=42)
    assert len(train_idx) + len(val_idx) < len(items)


def test_requesting_no_validation_slice_returns_every_index_for_training():
    items = generate_records(20, seed=3, source_id="carve_zero")
    label_sets = [planted_labels(r) for r in items]
    train_idx, val_idx = carve_validation(items, label_sets, fraction=0.0, seed=42)
    assert val_idx == []
    assert train_idx == list(range(len(items)))


# ---------------------------------------------------------------------------
# Refusals -- the tests that stop a plausible-but-meaningless number
# ---------------------------------------------------------------------------


@pytest.mark.skipif(TORCH_INSTALLED, reason="only meaningful without the ML stack")
def test_a_missing_ml_stack_raises_a_typed_error_naming_the_install_command():
    with pytest.raises(MLDependencyMissing) as excinfo:
        require_ml_stack()
    message = str(excinfo.value)
    assert "requirements-ml.txt" in message
    assert "download.pytorch.org/whl/cpu" in message


@pytest.mark.skipif(TORCH_INSTALLED, reason="only meaningful without the ML stack")
def test_fit_without_the_ml_stack_fails_before_touching_data():
    with pytest.raises(MLDependencyMissing):
        TransformerBaseline().fit([], [])


@needs_torch
def test_weights_unavailable_is_raised_rather_than_falling_back_to_random_init(tmp_path):
    """The most expensive failure mode available in Phase 14.

    A randomly-initialised "DeBERTa" trains without complaint and scores low,
    which in the report is indistinguishable from the honest finding that the
    corpus has no generalisable signal. Refusing is the only safe behaviour, and
    the error must name the ways out.
    """
    empty = tmp_path / "not_a_checkpoint"
    empty.mkdir()
    with pytest.raises(WeightsUnavailable) as excinfo:
        resolve_base_model(str(empty))
    assert "config.json" in str(excinfo.value)


@needs_torch
def test_an_unreachable_hub_identifier_refuses_offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    with pytest.raises(WeightsUnavailable) as excinfo:
        resolve_base_model("this-org/definitely-not-a-real-model-xyz", local_only=True)
    message = str(excinfo.value)
    assert "Randomly-initialised" in message or "randomly-initialised" in message
    assert "--base-model" in message


def test_a_missing_sentencepiece_is_translated_into_an_actionable_error(monkeypatch):
    """Regression test for the first real Phase 14 run (2026-08-11, OPEN-029).

    Without `sentencepiece`, transformers 5.x does not report a missing
    dependency. It falls back to a TikToken extractor which parses DeBERTa-v3's
    SentencePiece protobuf as text and dies with
    `ValueError: Error parsing line b'\\x0e' in ...spm.model` -- an error that
    names neither the cause nor the fix.
    """
    import src.models.transformer as module

    class _FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(name):
            cause = ImportError("SentencePieceExtractor requires the SentencePiece library")
            raise ValueError(
                r"Error parsing line b'\x0e' in "
                r"C:\Users\x\.cache\huggingface\hub\models--microsoft--deberta-v3-base\spm.model"
            ) from cause

    monkeypatch.setattr(
        module,
        "require_ml_stack",
        lambda: (None, type("T", (), {"AutoTokenizer": _FakeAutoTokenizer})),
    )
    with pytest.raises(MLDependencyMissing) as excinfo:
        module.load_tokenizer("microsoft/deberta-v3-base")
    message = str(excinfo.value)
    assert "pip install sentencepiece" in message
    assert "roberta-base" in message


def test_an_unrelated_tokenizer_failure_is_not_relabelled_as_a_sentencepiece_problem(monkeypatch):
    """The translation must stay narrow.

    Attaching a confident, wrong explanation to an unrelated failure is worse
    than attaching none -- it sends the reader to fix something that is not
    broken.
    """
    import src.models.transformer as module

    class _FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(name):
            raise OSError("Connection reset by peer")

    monkeypatch.setattr(
        module,
        "require_ml_stack",
        lambda: (None, type("T", (), {"AutoTokenizer": _FakeAutoTokenizer})),
    )
    with pytest.raises(OSError, match="Connection reset"):
        module.load_tokenizer("microsoft/deberta-v3-base")


def test_predict_before_fit_is_an_error():
    with pytest.raises((RuntimeError, MLDependencyMissing)):
        TransformerBaseline().predict([RawRecord(record_id="r", source_id="s", text="t")])


# ---------------------------------------------------------------------------
# Interface compatibility with the Phase 13 harness
# ---------------------------------------------------------------------------


def test_the_transformer_presents_the_same_interface_as_the_classical_baselines():
    """The gate scores both through one harness. If the interfaces diverge, a
    difference between the two rows of the results table stops being a
    difference in the model.
    """
    from src.evaluation.baselines import Baseline

    assert issubclass(TransformerBaseline, Baseline)
    for method in ("fit", "predict"):
        assert callable(getattr(TransformerBaseline, method))


def test_the_gate_runner_imports_without_the_ml_stack():
    """`--dry-run` and `--gold` must work on a machine with no torch, otherwise
    the refusal path cannot be exercised where it matters most.
    """
    spec = importlib.util.spec_from_file_location(
        "run_transformer",
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_transformer.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.GATE_REFERENCE == "lexicon"
    assert module.GATE_ALPHA == 0.05


def test_the_gate_refuses_gold_while_the_directory_is_empty():
    spec = importlib.util.spec_from_file_location(
        "run_transformer_gold",
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_transformer.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Exit code 2 is "config error", not 1 ("gate failed"). An empty gold set is
    # not a failed experiment and must not be recorded as one.
    assert module.main(["--gold"]) == 2


def test_the_interpretation_sentence_always_disclaims_accuracy():
    """Whatever the gate result, the sentence that travels with it must refuse the
    accuracy reading. This is the guard against a caveat being dropped in a
    future edit to only one of the three branches.
    """
    spec = importlib.util.spec_from_file_location(
        "run_transformer_interp",
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "scripts"
        / "run_transformer.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for passed, significant in ((True, True), (False, True), (False, False)):
        sentence = module.gate_interpretation(passed, significant, "lexicon")
        lowered = sentence.lower()
        assert any(
            marker in lowered
            for marker in ("not evidence", "corpus", "noise", "no measurable difference")
        ), sentence


# ---------------------------------------------------------------------------
# Integration -- only where the ML stack exists
# ---------------------------------------------------------------------------


#: Tiny checkpoint for the integration smoke test. Maintained by Hugging Face
#: for precisely this purpose, and current (updated 2025).
#:
#: NOT `prajjwal1/bert-tiny`, which was the first choice and fails: that
#: checkpoint dates from 2020 and its `config.json` carries no `model_type` key,
#: which transformers 5.x refuses with "Unrecognized model". The refusal is
#: correct -- `resolve_base_model` turned it into a `WeightsUnavailable` exactly
#: as designed -- but a smoke test should exercise the happy path, not a
#: checkpoint's metadata rot.
TINY_CHECKPOINT = "hf-internal-testing/tiny-random-RobertaForSequenceClassification"


@needs_torch
@pytest.mark.slow
def test_a_short_fine_tune_produces_valid_label_sets(records, labels):
    """Smoke test, not a quality test.

    One epoch on a tiny slice with a tiny checkpoint. It asserts the plumbing
    (tokenisation, loss, thresholds, decode, manifest) produces well-formed
    output; it asserts nothing about the score, because a one-epoch run on 200
    synthetic records has no score worth asserting.

    **Marked `slow` and excluded from the default run** (`pyproject.toml`
    `addopts`), because it is the only test here that needs the network. Run it
    deliberately with `pytest -m slow`.

    Skips rather than fails when the hub is unreachable. A network outage, a
    rate limit, or an upstream checkpoint change is not a defect in this
    repository, and a red test report that means "someone else's server is down"
    trains people to ignore red test reports.
    """
    split = template_disjoint_split(records, test_size=0.3, seed=42)
    if not split.test:
        pytest.skip("no test side for this tiny fixture")
    index = {r.record_id: ls for r, ls in zip(records, labels, strict=True)}
    y_train = [index[r.record_id] for r in split.train]

    model = TransformerBaseline(
        hparams=HParams(base_model=TINY_CHECKPOINT, epochs=1, max_length=64, batch_size=8),
        progress=False,
    )
    try:
        model.fit(split.train, y_train)
    except WeightsUnavailable as exc:
        pytest.skip(f"hub unreachable, not a code defect: {exc}")
    predictions = model.predict(split.test)

    assert len(predictions) == len(split.test)
    for prediction in predictions:
        assert prediction <= set(CONSTRUCTS)

    manifest = model.manifest()
    assert manifest["is_accuracy"] is not True
    assert "NOT accuracy" in manifest["label_semantics"]
    assert manifest["training_fingerprint"]


@needs_torch
@pytest.mark.slow
def test_a_saved_model_reloads_as_the_same_classifier(records, labels, tmp_path):
    """Phase 17 depends on this round trip.

    Explainability needs the trained model back. Reloading it with *default*
    thresholds would make it a different classifier from the one that was
    evaluated, and every explanation would describe predictions the reported
    numbers never covered. So the assertion is not merely "it loads" but
    "it predicts identically".
    """
    split = template_disjoint_split(records, test_size=0.3, seed=42)
    if not split.test:
        pytest.skip("no test side for this tiny fixture")
    index = {r.record_id: ls for r, ls in zip(records, labels, strict=True)}

    model = TransformerBaseline(
        hparams=HParams(base_model=TINY_CHECKPOINT, epochs=1, max_length=64, batch_size=8),
        progress=False,
    )
    try:
        model.fit(split.train, [index[r.record_id] for r in split.train])
    except WeightsUnavailable as exc:
        pytest.skip(f"hub unreachable, not a code defect: {exc}")

    target = model.save(tmp_path / "ckpt")
    reloaded = TransformerBaseline.load(target)

    assert reloaded._thresholds == model._thresholds, "tuned thresholds must survive"
    assert reloaded._fingerprint == model._fingerprint
    assert reloaded.predict(split.test) == model.predict(split.test)


@needs_torch
def test_loading_a_checkpoint_without_its_manifest_is_refused(tmp_path):
    """A checkpoint with no manifest has no thresholds, no seed and no
    fingerprint, so it cannot be reloaded as the model that was evaluated."""
    empty = tmp_path / "no_manifest"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="manifest"):
        TransformerBaseline.load(empty)


@needs_torch
def test_loading_refuses_a_checkpoint_fitted_on_a_different_construct_order(tmp_path):
    """The highest-consequence load-time failure, and a silent one without this.

    Label columns are positional. A taxonomy edit between save and load would
    map every probability to the wrong construct while every shape check passed.
    """
    import json as _json

    target = tmp_path / "reordered"
    target.mkdir()
    (target / "manifest.json").write_text(
        _json.dumps(
            {
                "hparams": HParams().as_dict(),
                "constructs": list(reversed(CONSTRUCTS)),
                "thresholds": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="different construct order"):
        TransformerBaseline.load(target)
