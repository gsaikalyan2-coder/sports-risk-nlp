"""Phase 28 -- the facial-cue channel, and the properties that hold it down.

These tests are written so that the whole file passes on a machine with no
vision stack installed, which is the state of a clean checkout and of the test
runner in CI. The three tests that need a real model are skipped, explicitly and
with a reason, rather than being written to pass vacuously: a suite that reports
green because it quietly did nothing is the failure this project spends ten
modules refusing to ship.

What is asserted without the stack:

* consent is a gate that fires, not a flag that is read;
* a reading that was not measured carries no weight, so a missing library can
  never silently become a number that moves a psychological score;
* every face reading carries the stamp and the limitation;
* the declared weights are the stated prior, and they are small.
"""

from __future__ import annotations

import pytest

from src.dashboard import plain
from src.dashboard.mediaio import read_upload
from src.media.facecues import (
    EXPRESSIONS,
    FACE_STAMP,
    FACE_WEIGHTS,
    FaceCueReader,
    FaceCueUnavailable,
    _features_from_scores,
    face_context_weights,
    face_cue_reader,
    face_stack_status,
)
from src.media.nonverbal import (
    FACE_EXPRESSION_FEATURES,
    FACE_FEATURES,
    NonVerbalEthicsGate,
    NonVerbalReading,
)

STACK = face_stack_status()
needs_stack = pytest.mark.skipif(
    not STACK, reason="hsemotion-onnx / opencv-python-headless not installed here"
)


def png(width: int = 800, height: int = 600) -> bytes:
    """A minimal valid PNG header block, enough for the admission gate."""
    import struct
    import zlib

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x7f" * (width * 3) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


# ---------------------------------------------------------------------------
# 1. Consent
# ---------------------------------------------------------------------------


def test_reader_refuses_to_exist_without_consent() -> None:
    """The gate is construction, so there is no object to call read() on."""
    with pytest.raises(NonVerbalEthicsGate, match="consent"):
        FaceCueReader(consent=False)


def test_the_gate_names_the_document_that_governs_it() -> None:
    with pytest.raises(NonVerbalEthicsGate, match="ethics"):
        FaceCueReader(consent=False)


def test_factory_returns_nothing_without_consent() -> None:
    reader, detail = face_cue_reader(consent=False)
    assert reader is None
    assert detail == ""


def test_upload_without_consent_never_reads_a_face() -> None:
    result = read_upload("journal.png", png())
    assert result.face_measured is False
    assert result.context_weights == {}
    assert "NOT A MEASUREMENT" in result.nonverbal_stamp.upper()


# ---------------------------------------------------------------------------
# 2. An unmeasured reading may not move a number
# ---------------------------------------------------------------------------


def test_weights_are_empty_unless_a_face_was_actually_read() -> None:
    """The safety property of Phase 28, expressed as one function."""
    assert face_context_weights(measured=False) == {}
    assert face_context_weights(measured=True) == FACE_WEIGHTS


def test_simulated_feature_names_are_not_weight_keys() -> None:
    """A fallback reading is displayed and arithmetically ignored.

    `fusion.score` adds a term only for a name present in BOTH the weights and
    the context mapping, so this disjointness is what makes a missing library
    unable to become a number.
    """
    assert set(FACE_WEIGHTS) == set(FACE_FEATURES)
    assert not set(FACE_WEIGHTS) & {"expressivity", "vocal_strain", "steadiness"}


def test_declared_weights_are_small_and_signed_as_stated() -> None:
    assert FACE_WEIGHTS["negative_valence"] > 0
    assert FACE_WEIGHTS["arousal"] > 0
    assert sum(abs(w) for w in FACE_WEIGHTS.values()) <= 0.5


# ---------------------------------------------------------------------------
# 3. What a reading says about itself
# ---------------------------------------------------------------------------


def test_face_stamp_refuses_to_lose_the_words_that_matter() -> None:
    assert "NOT A MEASUREMENT" in FACE_STAMP.upper()
    reading = NonVerbalReading(
        source="face-cues", stamp=FACE_STAMP, features={"negative_valence": 0.4}
    )
    assert reading.features["negative_valence"] == 0.4


def test_the_limitation_is_in_the_copy_the_page_renders() -> None:
    """Required by docs/ethics.md sec.14.3 wherever a face number is shown."""
    low = plain.FACE_CUES_LIMITATION.lower()
    assert "expression is not a feeling" in low
    assert "by hand" in low


def test_consent_label_states_a_fact_rather_than_offering_a_feature() -> None:
    assert "mine" in plain.CONSENT_LABEL.lower()
    assert "agreed" in plain.CONSENT_LABEL.lower()


# ---------------------------------------------------------------------------
# 4. Turning the engine's row into two bounded features
# ---------------------------------------------------------------------------


def test_valence_is_inverted_so_that_more_negative_means_a_bigger_number() -> None:
    row = [0.0] * len(EXPRESSIONS) + [-1.0, 0.0]
    assert _features_from_scores(row)["negative_valence"] == pytest.approx(1.0)
    row = [0.0] * len(EXPRESSIONS) + [1.0, 0.0]
    assert _features_from_scores(row)["negative_valence"] == pytest.approx(0.0)


def test_arousal_is_rescaled_into_the_unit_interval() -> None:
    row = [0.0] * len(EXPRESSIONS) + [0.0, 1.0]
    assert _features_from_scores(row)["arousal"] == pytest.approx(1.0)
    row = [0.0] * len(EXPRESSIONS) + [0.0, -1.0]
    assert _features_from_scores(row)["arousal"] == pytest.approx(0.0)


def test_every_feature_is_bounded_whatever_the_engine_returns() -> None:
    row = [0.0] * len(EXPRESSIONS) + [-9.0, 9.0]
    features = _features_from_scores(row)
    assert all(0.0 <= value <= 1.0 for value in features.values())


def test_a_build_without_the_valence_head_degrades_rather_than_lies() -> None:
    """Eight scores only: a coarser reading, and arousal at the midpoint."""
    row = [0.0] * len(EXPRESSIONS)
    row[EXPRESSIONS.index("Sadness")] = 1.0
    features = _features_from_scores(row)
    assert features["negative_valence"] == pytest.approx(1.0)
    assert features["arousal"] == pytest.approx(0.5)


def test_an_unreadable_engine_row_produces_no_number() -> None:
    with pytest.raises(FaceCueUnavailable):
        _features_from_scores([0.1, 0.2])


# ---------------------------------------------------------------------------
# 4b. The eight-way expression breakdown -- supporting detail, never weighted
# ---------------------------------------------------------------------------


def test_a_full_row_carries_all_eight_expression_scores() -> None:
    row = [0.03, 0.06, 0.03, 0.25, 0.08, 0.23, 0.05, 0.26, 0.32, 0.14]
    features = _features_from_scores(row)
    assert set(FACE_EXPRESSION_FEATURES) <= set(features)
    assert all(0.0 <= features[name] <= 1.0 for name in FACE_EXPRESSION_FEATURES)


def test_a_degraded_eight_only_row_still_carries_the_breakdown() -> None:
    """The one case where the eight scores are the only signal present."""
    row = [0.0] * len(EXPRESSIONS)
    row[EXPRESSIONS.index("Sadness")] = 1.0
    features = _features_from_scores(row)
    assert set(FACE_EXPRESSION_FEATURES) <= set(features)
    assert features["expr_sadness"] == pytest.approx(1.0)


def test_the_expression_keys_never_drift_from_the_declared_name_set() -> None:
    row = [0.03, 0.06, 0.03, 0.25, 0.08, 0.23, 0.05, 0.26, 0.32, 0.14]
    features = _features_from_scores(row)
    expression_keys = set(features) - {"negative_valence", "arousal"}
    assert expression_keys == set(FACE_EXPRESSION_FEATURES)


def test_expression_scores_are_never_a_face_weights_key() -> None:
    """FACE_EXPRESSION_FEATURES must stay disjoint from FACE_WEIGHTS.

    This is the property the whole plan depends on: the eight scores can be
    shown without ever being able to move the index, because `fusion.score`
    only adds a context term for a name present in both a reading's features
    and the scorer's weights.
    """
    assert set(FACE_EXPRESSION_FEATURES).isdisjoint(FACE_WEIGHTS)


# ---------------------------------------------------------------------------
# 5. With the stack present
# ---------------------------------------------------------------------------


@needs_stack
def test_status_names_the_engine_when_it_is_available() -> None:
    assert "hsemotion" in STACK.engine


@needs_stack
def test_an_image_with_no_face_reads_nothing_and_says_so() -> None:
    """A flat grey rectangle. No face, so no cues, and the score stays text-only."""
    result = read_upload("plain.png", png(), consent=True)
    assert result.face_measured is False
    assert result.context_weights == {}
    assert result.face_detail


@needs_stack
def test_a_reader_built_with_consent_carries_the_engine_string() -> None:
    reader = FaceCueReader(consent=True)
    assert reader.simulated is False
    assert reader.engine


# ---------------------------------------------------------------------------
# 6. Phase 28b -- a photograph with no words in it
# ---------------------------------------------------------------------------


def test_face_only_index_is_zero_when_the_cues_are_zero() -> None:
    """No logistic squash, so an empty reading cannot land on 0.50 with a band.

    This is the Phase 27 failure restated for the picture door: an input that
    carries nothing produces nothing, never a midpoint that looks like a verdict.
    """
    from src.media.facecues import face_only_index

    assert face_only_index({"negative_valence": 0.0, "arousal": 0.0}) == 0.0
    assert face_only_index({}) == 0.0


def test_face_only_index_is_bounded_and_monotone() -> None:
    from src.media.facecues import face_only_index

    low = face_only_index({"negative_valence": 0.2, "arousal": 0.2})
    high = face_only_index({"negative_valence": 0.9, "arousal": 0.9})
    assert 0.0 <= low < high <= 1.0
    assert face_only_index({"negative_valence": 1.0, "arousal": 1.0}) == pytest.approx(1.0)


def test_the_face_only_stamp_denies_being_the_risk_index() -> None:
    """The figure and the index must not be confusable in a screenshot."""
    from src.media.facecues import FACE_ONLY_STAMP

    assert "NOT THE RISK INDEX" in FACE_ONLY_STAMP.upper()
    assert "NOT A MEASUREMENT" in FACE_ONLY_STAMP.upper()


def test_a_wordless_photo_without_consent_still_produces_nothing() -> None:
    """The face-only path is reachable only through a measured reading."""
    result = read_upload("crowd.png", png())
    assert result.face_only is False
    assert result.face_index == 0.0
