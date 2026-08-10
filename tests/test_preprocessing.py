"""Phase 8 preprocessing tests.

Offline, deterministic, no network -- the same contract as `test_ingestion.py`.
Every test writes into `tmp_path`, so the real `data/interim/` is never touched
by the suite.

The tests the Phase 8 gate names explicitly are marked in their docstrings:
the de-identifier is measured against the fixture rather than the corpus, a
record cannot reach `data/interim/` without being de-identified, negatives
survive un-redacted, and utterance offsets are exact.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingestion import (
    IngestionRefused,
    RawRecord,
    RawStore,
    generate_records,
    generator_stamp,
    synthetic_descriptor,
)
from src.preprocessing import (
    PLACEHOLDER_RE,
    InterimRecord,
    InterimStore,
    deidentify,
    deidentify_with_report,
    detect_language,
    normalize,
    normalize_with_report,
    preprocess_record,
    preprocess_source,
    score_fixture,
    segment,
    verify_offsets,
)
from src.preprocessing.audit import DEFAULT_FIXTURE, load_cases
from src.preprocessing.language import should_exclude
from src.preprocessing.store import GOLD_ROOT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fixture_score():
    return score_fixture()


@pytest.fixture
def raw_source(tmp_path: Path) -> tuple[RawStore, str]:
    """A small real ingested source, built through the Phase 7 path."""
    store = RawStore(root=tmp_path / "raw", refusal_log=tmp_path / "refusals.log")
    descriptor = synthetic_descriptor("test_precomp", seed=7)
    with store.open_source(descriptor, generator=generator_stamp(7).to_dict()) as writer:
        writer.write_all(generate_records(25, seed=7, source_id=descriptor.source_id))
    return store, descriptor.source_id


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def test_normalize_is_idempotent():
    """normalize(normalize(t)) == normalize(t) for awkward input."""
    messy = "  He said “I’m ready”…  really​ ready  "
    once = normalize(messy)
    assert normalize(once) == once


def test_normalize_folds_typography_but_not_case():
    text = "“I’M READY” – he said"
    result = normalize(text)
    assert '"' in result and "'" in result
    assert "I'M READY" in result, "casing is intensity evidence and must survive"


def test_normalize_removes_zero_width_and_controls():
    text = "ready​ for\x07 this"
    result, report = normalize_with_report(text)
    assert "​" not in result
    assert "\x07" not in result
    assert report.zero_width_removed == 1
    assert report.control_chars_removed == 1


def test_normalize_folds_fullwidth_at_sign_so_handles_stay_detectable():
    """The reason normalisation runs before de-identification."""
    assert deidentify(normalize("tagged ＠quietstorm in it")) == "tagged [HANDLE] in it"


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


def test_segment_offsets_are_exact():
    """Span attribution depends on this; a two-character drift is invisible."""
    text = normalize("I am nervous. My legs feel heavy! Will it matter? Probably not.")
    utterances = segment(text)
    assert len(utterances) == 4
    assert verify_offsets(text, utterances) == []
    for utterance in utterances:
        assert text[utterance.start : utterance.end] == utterance.text


def test_segment_does_not_split_on_honorifics_or_decimals():
    text = "Dr. Vance cleared me. I ran 3.5 km after that."
    assert len(segment(text)) == 2


def test_segment_returns_nothing_for_empty_input():
    """An empty utterance would reach the labeller and cost a paid API call."""
    assert segment("") == []
    assert segment("   \n  ") == []


# ---------------------------------------------------------------------------
# Language filter
# ---------------------------------------------------------------------------


def test_short_english_sentence_is_not_excluded():
    """Regression: this exact sentence was dropped as Portuguese.

    The English stopword profile was smaller than the Portuguese one, so an
    eight-token English sentence lost on the single shared token "a".
    """
    text = "Slept a little lighter than usual last night."
    drop, reason = should_exclude(text)
    assert not drop, f"dropped English text as {reason}"


def test_obvious_non_english_is_excluded():
    spanish = "No puedo dormir y el partido es manana por la tarde en el estadio"
    drop, _ = should_exclude(spanish)
    assert drop


def test_exclusion_requires_more_than_one_shared_token():
    """Burden of proof sits on exclusion: dropping a record is irreversible."""
    drop, _ = should_exclude("The session was a good one and I feel settled")
    assert not drop


def test_short_text_is_never_excluded():
    drop, reason = should_exclude("Two days out")
    assert not drop
    assert reason == "too_short_to_judge"


def test_detect_language_reports_uncertainty_rather_than_guessing():
    verdict = detect_language("xxx yyy")
    assert verdict.uncertain
    assert verdict.language == "und"


# ---------------------------------------------------------------------------
# De-identification -- the fixture is the gate (OPEN-013)
# ---------------------------------------------------------------------------


def test_fixture_exists_and_is_not_empty():
    """A missing fixture must fail loudly, never be silently skipped."""
    cases = load_cases(DEFAULT_FIXTURE)
    assert len(cases) >= 30
    assert {c["category"] for c in cases} >= {"person_name", "health", "negative"}


def test_fixture_recall_meets_the_floor(fixture_score):
    assert fixture_score.recall >= 0.90, "de-identification recall regressed"


def test_fixture_precision_meets_the_floor(fixture_score):
    """A de-identifier that blanks everything scores perfect recall."""
    assert fixture_score.precision >= 0.90


def test_every_negative_case_survives_unchanged(fixture_score):
    """Over-redaction destroys the linguistic structure the model needs."""
    damaged = [c.case_id for c in fixture_score.negatives if c.produced != c.expected]
    assert damaged == [], f"over-redacted: {damaged}"


def test_leak_rate_stays_within_ceiling(fixture_score):
    """The privacy number: a removed string surviving into the output."""
    assert fixture_score.leak_rate <= 0.05


def test_hard_band_is_reported_separately(fixture_score):
    """Aggregates hide that easy cases pass and hard ones do not."""
    bands = fixture_score.by("difficulty")
    assert {"easy", "medium", "hard"} <= set(bands)
    assert all(len(band.cases) > 0 for band in bands.values())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Coach Renner set the plan.", "[COACH] set the plan."),
        ("I am up against Kowalczyk tomorrow.", "I am up against [OPPONENT] tomorrow."),
        ("Reach me at h.varga@example-club.test", "Reach me at [CONTACT]"),
        ("The draw is at https://example.test/draw", "The draw is at [URL]"),
        ("Mark my words, I will not slip.", "Mark my words, I will not slip."),
        ("I ran it in 47 seconds.", "I ran it in 47 seconds."),
    ],
)
def test_deidentify_cases_outside_the_fixture(text, expected):
    """Held-out cases. The fixture is the gate; a gate you tune against is not evidence."""
    assert deidentify(text) == expected


def test_health_detail_is_removed_not_placeholdered():
    """docs/ethics.md sec.5.1, final row."""
    text = "The nerves are bad. My ACL reconstruction still aches."
    result, report = deidentify_with_report(text)
    assert "ACL" not in result
    assert not PLACEHOLDER_RE.search(result), "health detail must not leave a placeholder"
    assert report.health_clauses_removed == 1
    assert "The nerves are bad." in result


def test_body_parts_are_not_treated_as_health_data():
    """Somatic anxiety is one of the ten locked constructs; it lives in body language."""
    text = "My stomach is in knots and my hands will not stop shaking."
    assert deidentify(text) == text


def test_placeholders_are_typed_not_blanked():
    result = deidentify("Coach Renner and Nadia and I trained at the Verrick Street Arena.")
    found = set(PLACEHOLDER_RE.findall(result))
    assert len(found) > 1, "distinct entity types must map to distinct placeholders"
    assert "[REDACTED]" not in result


def test_deidentification_produces_no_reversible_mapping():
    """docs/ethics.md sec.5.2: no mapping table back to identity exists.

    Enforced by the shape of the API: what comes back is text and counts. If a
    future change adds an inverse, this test is where it announces itself.
    """
    _, report = deidentify_with_report("Coach Renner said it was fine.")
    payload = json.dumps(report.to_dict())
    assert "Renner" not in payload
    assert not hasattr(report, "mapping")
    assert set(report.to_dict()) == {
        "replacements",
        "total_replacements",
        "health_clauses_removed",
        "residual_flags",
    }


def test_residual_flags_surface_what_the_rules_could_not_resolve():
    _, report = deidentify_with_report("I trained with Bjornsson Tewolde Achterberg today.")
    assert report.replacements or report.residual_flags


# ---------------------------------------------------------------------------
# Interim records and the store
# ---------------------------------------------------------------------------


def _interim(**overrides) -> InterimRecord:
    base = {
        "record_id": "r1#u0",
        "source_id": "s1",
        "parent_record_id": "r1",
        "utterance_index": 0,
        "text": "I feel ready.",
        "char_start": 0,
        "char_end": 13,
    }
    base.update(overrides)
    return InterimRecord(**base)


def test_interim_record_cannot_be_created_undeidentified():
    """Phase 8 gate: the flag is earned by running the step, not by setting it."""
    with pytest.raises(ValueError, match="deidentified=False"):
        _interim(deidentified=False)


def test_interim_record_requires_a_parent():
    with pytest.raises(ValueError, match="parent_record_id"):
        _interim(parent_record_id="")


def test_interim_record_round_trips_nullable_metadata():
    record = _interim(sport=None, time_to_competition_days=None, training_load_hint=None)
    restored = InterimRecord.from_json_line(record.to_json_line())
    payload = json.loads(record.to_json_line())
    assert payload["sport"] is None
    assert "time_to_competition_days" in payload, "absent must be explicit null, never omitted"
    assert restored.to_dict() == record.to_dict()


def test_store_refuses_the_gold_root():
    """data/gold/ is human-owned; the guard is restated at every write layer."""
    with pytest.raises(IngestionRefused, match="GOLD_IS_HUMAN_OWNED"):
        InterimStore(root=GOLD_ROOT)


def test_store_refuses_a_subdirectory_of_gold():
    with pytest.raises(IngestionRefused, match="GOLD_IS_HUMAN_OWNED"):
        InterimStore(root=GOLD_ROOT / "nested")


def test_interim_provenance_flips_deidentified_and_raw_stays_false(raw_source, tmp_path):
    """Phase 7 wrote False everywhere; only running the step may change it."""
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    preprocess_source(source_id, raw_store=raw_store, interim_store=interim)

    raw_provenance, _ = raw_store.read_source(source_id)
    interim_provenance_read, _ = interim.read_source(source_id)
    assert raw_provenance.deidentified is False, (
        "raw text is not de-identified and must not claim to be"
    )
    assert interim_provenance_read.deidentified is True


def test_pipeline_writes_a_manifest_with_drop_reasons(raw_source, tmp_path):
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    result = preprocess_source(source_id, raw_store=raw_store, interim_store=interim)

    manifest = interim.read_manifest(source_id)
    assert manifest["utterance_count"] == result.utterances_written
    assert manifest["deidentified"] is True
    assert "dropped" in manifest and isinstance(manifest["dropped"], dict)
    assert manifest["steps"] == ["normalize", "segment", "language_filter", "deidentify"]


def test_pipeline_is_deterministic(raw_source, tmp_path):
    raw_store, source_id = raw_source
    first = InterimStore(root=tmp_path / "a")
    second = InterimStore(root=tmp_path / "b")
    preprocess_source(source_id, raw_store=raw_store, interim_store=first)
    preprocess_source(source_id, raw_store=raw_store, interim_store=second)

    _, records_a = first.read_source(source_id)
    _, records_b = second.read_source(source_id)
    assert [r.to_dict() for r in records_a] == [r.to_dict() for r in records_b]


def test_pipeline_carries_temporal_metadata_to_every_utterance(raw_source, tmp_path):
    """Contribution #3. `docs/data_sources.md`: impossible to backfill later."""
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    preprocess_source(source_id, raw_store=raw_store, interim_store=interim)

    _, records = interim.read_source(source_id)
    assert records
    assert all(r.time_to_competition_days is not None for r in records)
    assert all(r.sport is not None for r in records)


def test_pipeline_offsets_point_into_the_normalised_parent(raw_source, tmp_path):
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    preprocess_source(source_id, raw_store=raw_store, interim_store=interim)

    _, raw_records = raw_store.read_source(source_id)
    parents = {r.record_id: normalize(r.text) for r in raw_records}
    _, records = interim.read_source(source_id)
    for record in records:
        parent = parents[record.parent_record_id]
        assert 0 <= record.char_start < record.char_end <= len(parent)


def test_every_written_utterance_is_flagged_deidentified(raw_source, tmp_path):
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    preprocess_source(source_id, raw_store=raw_store, interim_store=interim)
    _, records = interim.read_source(source_id)
    assert records and all(r.deidentified for r in records)


def test_a_record_that_is_all_health_detail_yields_no_utterances():
    record = RawRecord(
        record_id="r-health",
        source_id="s1",
        text="My ACL reconstruction is still healing.",
        synthetic=True,
    )
    outcome = preprocess_record(record)
    assert outcome.utterances == []
    assert outcome.drops["no_utterances"] + outcome.drops["empty_after_deidentification"] >= 1


def test_generation_spec_is_carried_with_its_warning_intact(raw_source, tmp_path):
    """It is generator metadata, not a label, and looks more like one here."""
    raw_store, source_id = raw_source
    interim = InterimStore(root=tmp_path / "interim")
    preprocess_source(source_id, raw_store=raw_store, interim_store=interim)
    _, records = interim.read_source(source_id)
    spec = records[0].generation_spec
    assert spec is not None
    assert "NOTE" in spec and "ground truth" in spec["NOTE"]
