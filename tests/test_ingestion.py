"""Phase 7 ingestion tests.

Offline, deterministic, no network -- the same contract as `test_agents.py`.
Every test writes into `tmp_path`, so the real `data/raw/` and the real
`logs/ingestion_refusals.log` are never touched by the suite.

The three tests the Phase 7 gate names explicitly are marked in their
docstrings: a disallowed source is rejected, a record cannot be written without
provenance, and nullable temporal fields round-trip.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from src.ingestion import (
    REQUIRED_DECLARATIONS,
    AllowlistError,
    IngestionRefused,
    Provenance,
    RawRecord,
    RawStore,
    SourceDescriptor,
    check_source,
    generate_records,
    generator_stamp,
    load_allowlist,
    metadata_coverage,
    synthetic_descriptor,
    validate_provenance,
)
from src.ingestion.allowlist import ALLOWLIST_PATH
from src.ingestion.store import GOLD_ROOT, RECORDS_FILENAME

CLEAN_DECLARATIONS = dict.fromkeys(REQUIRED_DECLARATIONS, True)


@pytest.fixture(scope="module")
def allowlist():
    return load_allowlist()


@pytest.fixture
def store(tmp_path: Path, allowlist) -> RawStore:
    """A store rooted in tmp_path, logging refusals to tmp_path."""
    return RawStore(
        root=tmp_path / "raw",
        allowlist=allowlist,
        refusal_log=tmp_path / "refusals.log",
    )


def _descriptor(**overrides) -> SourceDescriptor:
    base = {
        "source_id": "test_source",
        "source_name": "Test source",
        "allowlist_category": "A2_synthetic",
        "url_or_citation": "generated in tests",
        "licence_or_consent_basis": "project-generated synthetic text",
        "permitted_uses": "testing",
        "redistribution_permitted": True,
        "synthetic": True,
        "subject_is_adult": True,
        "language": "en",
        # `notes` is in the policy's provenance_required_fields, so it must be
        # non-empty. That is deliberate on the policy's part: every source in a
        # published corpus should carry a human sentence explaining it.
        "notes": "fixture source used by the ingestion test suite",
        "declares": dict(CLEAN_DECLARATIONS),
    }
    base.update(overrides)
    return SourceDescriptor(**base)


# ---------------------------------------------------------------------------
# The allow-list config itself
# ---------------------------------------------------------------------------


def test_real_allowlist_loads_and_is_fail_closed(allowlist):
    assert allowlist.default_action == "deny"
    assert "A2_synthetic" in allowlist.permitted_category_keys()
    assert allowlist.provenance_required_fields


def test_allowlist_refuses_a_permissive_default(tmp_path: Path):
    """A policy that admits unlisted sources by default must not load at all."""
    policy = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    policy["default_action"] = "allow"
    path = tmp_path / "permissive.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")

    with pytest.raises(AllowlistError, match="fail closed"):
        load_allowlist(path)


def test_every_prohibition_in_the_policy_has_a_guarding_declaration(allowlist):
    """No prohibition may exist in policy without a check that enforces it.

    Guards against the drift where someone adds P8 to the YAML and the code
    never learns about it -- the policy would then say more than the code does.
    """
    guarded = set(REQUIRED_DECLARATIONS.values())
    declared = {p.id for p in allowlist.prohibitions}
    assert declared <= guarded, f"prohibitions with no code guard: {declared - guarded}"


# ---------------------------------------------------------------------------
# GATE TEST 1 -- a source not on the allow-list is rejected by code
# ---------------------------------------------------------------------------


def test_unlisted_category_is_refused(store: RawStore):
    """GATE: a source outside the allow-list is refused, not warned about."""
    with pytest.raises(IngestionRefused) as excinfo:
        store.open_source(_descriptor(allowlist_category="A9_made_up", synthetic=False))
    assert excinfo.value.reason_code == "UNLISTED_SOURCE"


def test_refusal_is_logged(store: RawStore, tmp_path: Path):
    with pytest.raises(IngestionRefused):
        store.open_source(_descriptor(allowlist_category="A9_made_up", synthetic=False))
    log = (tmp_path / "refusals.log").read_text(encoding="utf-8")
    assert "UNLISTED_SOURCE" in log
    assert "test_source" in log


def test_refused_source_writes_no_directory(store: RawStore):
    """A refusal must leave nothing behind, or data/raw/ accretes empty shells."""
    with pytest.raises(IngestionRefused):
        store.open_source(_descriptor(allowlist_category="A9_made_up", synthetic=False))
    assert not (store.root / "test_source").exists()


@pytest.mark.parametrize("declaration", sorted(REQUIRED_DECLARATIONS))
def test_each_prohibition_declaration_must_be_true(store: RawStore, declaration: str):
    declares = dict(CLEAN_DECLARATIONS)
    declares[declaration] = False
    with pytest.raises(IngestionRefused) as excinfo:
        store.open_source(_descriptor(declares=declares))
    assert excinfo.value.reason_code == "PROHIBITED_MATCH"


@pytest.mark.parametrize("declaration", sorted(REQUIRED_DECLARATIONS))
def test_a_missing_declaration_is_refused_not_defaulted(store: RawStore, declaration: str):
    """Silence is not consent: an absent declaration must fail closed."""
    declares = dict(CLEAN_DECLARATIONS)
    del declares[declaration]
    with pytest.raises(IngestionRefused) as excinfo:
        store.open_source(_descriptor(declares=declares))
    assert excinfo.value.reason_code == "MISSING_DECLARATION"


def test_minor_subject_is_refused(store: RawStore):
    with pytest.raises(IngestionRefused) as excinfo:
        store.open_source(_descriptor(subject_is_adult=False))
    assert excinfo.value.reason_code == "PROHIBITED_MATCH"


def test_empty_licence_basis_is_refused(store: RawStore):
    with pytest.raises(IngestionRefused) as excinfo:
        store.open_source(_descriptor(licence_or_consent_basis="   "))
    assert excinfo.value.reason_code == "MISSING_LICENCE_BASIS"


def test_synthetic_text_cannot_be_filed_under_a_real_category(store: RawStore, allowlist):
    """Synthetic text outside A2 could be presented as real speech. Refuse it."""
    with pytest.raises(IngestionRefused) as excinfo:
        check_source(
            _descriptor(allowlist_category="A1_public_research_dataset", synthetic=True),
            allowlist,
            log_path=store.refusal_log,
        )
    assert excinfo.value.reason_code == "CATEGORY_MISMATCH"


def test_a2_requires_the_synthetic_flag(store: RawStore, allowlist):
    with pytest.raises(IngestionRefused) as excinfo:
        check_source(
            _descriptor(allowlist_category="A2_synthetic", synthetic=False),
            allowlist,
            log_path=store.refusal_log,
        )
    assert excinfo.value.reason_code == "CATEGORY_MISMATCH"


# ---------------------------------------------------------------------------
# GATE TEST 2 -- a record cannot exist without provenance
# ---------------------------------------------------------------------------


def test_provenance_is_written_before_any_record(store: RawStore):
    """GATE: opening a source writes provenance.json first."""
    writer = store.open_source(_descriptor())
    assert (writer.directory / "provenance.json").exists()
    assert not (writer.directory / RECORDS_FILENAME).exists()


def test_reading_a_source_without_provenance_is_refused(store: RawStore):
    """GATE: an orphaned records.jsonl is untraceable and must not load."""
    orphan = store.root / "orphan"
    orphan.mkdir(parents=True)
    (orphan / RECORDS_FILENAME).write_text(
        json.dumps({"record_id": "x", "source_id": "orphan", "text": "hello"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestionRefused) as excinfo:
        list(store.iter_all())
    assert excinfo.value.reason_code == "MISSING_PROVENANCE"


def test_every_policy_required_field_is_enforced(allowlist, tmp_path: Path):
    """Blanking any single required field must be refused, one field at a time."""
    descriptor = synthetic_descriptor("prov_test", seed=1)
    store = RawStore(root=tmp_path / "raw", allowlist=allowlist, refusal_log=tmp_path / "r.log")
    writer = store.open_source(descriptor)
    good = Provenance.read(writer.directory)

    for field_name in allowlist.provenance_required_fields:
        broken = Provenance.read(writer.directory)
        if isinstance(getattr(broken, field_name), bool):
            continue  # False is a meaningful answer, not an empty one
        setattr(broken, field_name, None)
        with pytest.raises(IngestionRefused) as excinfo:
            validate_provenance(broken, allowlist, log_path=tmp_path / "r.log")
        assert excinfo.value.reason_code == "MISSING_REQUIRED_PROVENANCE_FIELD"

    validate_provenance(good, allowlist, log_path=tmp_path / "r.log")  # unchanged: still valid


def test_deidentified_is_false_at_ingestion(store: RawStore):
    """Phase 7 must not claim de-identification. That is Phase 8's job."""
    writer = store.open_source(_descriptor())
    assert Provenance.read(writer.directory).deidentified is False


def test_record_count_is_stamped_on_clean_exit(store: RawStore):
    descriptor = _descriptor()
    with store.open_source(descriptor) as writer:
        writer.write_all(generate_records(5, seed=1, source_id=descriptor.source_id))
    assert Provenance.read(writer.directory).record_count == 5


def test_record_count_is_not_stamped_after_a_crash(store: RawStore):
    """A failed run must not leave provenance asserting a count it never wrote."""
    descriptor = _descriptor()
    with pytest.raises(RuntimeError, match="boom"):
        with store.open_source(descriptor) as writer:
            writer.write_all(generate_records(3, seed=1, source_id=descriptor.source_id))
            raise RuntimeError("boom")
    assert Provenance.read(writer.directory).record_count == 0


def test_duplicate_record_ids_are_refused(store: RawStore):
    descriptor = _descriptor()
    record = RawRecord(record_id="dup", source_id=descriptor.source_id, text="x", synthetic=True)
    with pytest.raises(IngestionRefused) as excinfo:
        with store.open_source(descriptor) as writer:
            writer.write(record)
            writer.write(record)
    assert excinfo.value.reason_code == "DUPLICATE_RECORD_ID"


def test_record_from_another_source_is_refused(store: RawStore):
    descriptor = _descriptor()
    stray = RawRecord(record_id="a", source_id="somewhere_else", text="x", synthetic=True)
    with pytest.raises(IngestionRefused) as excinfo:
        with store.open_source(descriptor) as writer:
            writer.write(stray)
    assert excinfo.value.reason_code == "SOURCE_ID_MISMATCH"


def test_non_synthetic_record_under_synthetic_source_is_refused(store: RawStore):
    descriptor = _descriptor()
    record = RawRecord(record_id="a", source_id=descriptor.source_id, text="x", synthetic=False)
    with pytest.raises(IngestionRefused) as excinfo:
        with store.open_source(descriptor) as writer:
            writer.write(record)
    assert excinfo.value.reason_code == "SYNTHETIC_FLAG_MISMATCH"


# ---------------------------------------------------------------------------
# GATE TEST 3 -- nullable temporal / context fields round-trip
# ---------------------------------------------------------------------------


def test_null_temporal_fields_round_trip_as_null(store: RawStore):
    """GATE: an unknown field survives as JSON null -- not missing, not "None"."""
    descriptor = _descriptor()
    record = RawRecord(
        record_id="null_case",
        source_id=descriptor.source_id,
        text="The team meeting is on Thursday.",
        time_to_competition_days=None,
        sport=None,
        competition_level=None,
        region=None,
        source_type=None,
        training_load_hint=None,
        synthetic=True,
    )
    with store.open_source(descriptor) as writer:
        writer.write(record)

    raw_line = (writer.directory / RECORDS_FILENAME).read_text(encoding="utf-8").strip()
    payload = json.loads(raw_line)
    for field_name in (
        "time_to_competition_days",
        "sport",
        "competition_level",
        "region",
        "source_type",
        "training_load_hint",
    ):
        assert field_name in payload, f"{field_name} was dropped rather than nulled"
        assert payload[field_name] is None
    assert '"None"' not in raw_line  # never the *string* "None"

    _, records = store.read_source(descriptor.source_id)
    assert records[0].time_to_competition_days is None
    assert records[0].sport is None


def test_populated_temporal_fields_round_trip_exactly(store: RawStore):
    descriptor = _descriptor()
    record = RawRecord(
        record_id="full_case",
        source_id=descriptor.source_id,
        text="Two days out and the nerves are building.",
        time_to_competition_days=0,  # zero must survive, not be read as falsy-missing
        sport="rowing",
        competition_level="national",
        region="south_asia",
        source_type="journal",
        training_load_hint="tapering",
        synthetic=True,
    )
    with store.open_source(descriptor) as writer:
        writer.write(record)

    _, records = store.read_source(descriptor.source_id)
    restored = records[0]
    assert restored.time_to_competition_days == 0
    assert restored.sport == "rowing"
    assert restored.competition_level == "national"
    assert restored.source_type == "journal"
    assert restored.training_load_hint == "tapering"


def test_negative_time_to_competition_is_rejected(store: RawStore):
    """This project is pre-competition; a negative offset would be post-match."""
    with pytest.raises(ValueError, match="pre-competition"):
        RawRecord(
            record_id="neg",
            source_id="s",
            text="after the final",
            time_to_competition_days=-3,
        )


def test_unknown_vocabulary_values_are_rejected(store: RawStore):
    with pytest.raises(ValueError, match="source_type"):
        RawRecord(record_id="a", source_id="s", text="x", source_type="podcast")
    with pytest.raises(ValueError, match="competition_level"):
        RawRecord(record_id="a", source_id="s", text="x", competition_level="galactic")


def test_metadata_coverage_counts_nulls_as_absent():
    records = [
        RawRecord(record_id="1", source_id="s", text="a", sport="tennis"),
        RawRecord(record_id="2", source_id="s", text="b", sport=None),
    ]
    assert metadata_coverage(records)["sport"] == 0.5
    assert metadata_coverage([])["sport"] == 0.0


# ---------------------------------------------------------------------------
# data/gold/ is human-owned
# ---------------------------------------------------------------------------


def test_store_refuses_to_root_itself_in_gold(allowlist):
    """CLAUDE.md sec.4: agents never write to data/gold/."""
    with pytest.raises(IngestionRefused) as excinfo:
        RawStore(root=GOLD_ROOT, allowlist=allowlist)
    assert excinfo.value.reason_code == "GOLD_IS_HUMAN_OWNED"


def test_store_refuses_a_subdirectory_of_gold(allowlist):
    with pytest.raises(IngestionRefused) as excinfo:
        RawStore(root=GOLD_ROOT / "sneaky", allowlist=allowlist)
    assert excinfo.value.reason_code == "GOLD_IS_HUMAN_OWNED"


# ---------------------------------------------------------------------------
# The synthetic generator
# ---------------------------------------------------------------------------


def test_generation_is_deterministic_under_a_seed():
    a = generate_records(60, seed=42, source_id="s")
    b = generate_records(60, seed=42, source_id="s")
    assert [r.to_dict() for r in a] == [r.to_dict() for r in b]


def test_different_seeds_give_different_text():
    a = [r.text for r in generate_records(60, seed=1, source_id="s")]
    b = [r.text for r in generate_records(60, seed=2, source_id="s")]
    assert a != b


def test_every_generated_record_is_marked_synthetic_and_not_deidentified():
    for record in generate_records(120, seed=3, source_id="s"):
        assert record.synthetic is True
        assert record.deidentified is False
        assert record.source_type == "synthetic"


def test_every_generated_record_carries_timing():
    """Contribution #3: timing is impossible to backfill, so it is never null here."""
    for record in generate_records(120, seed=4, source_id="s"):
        assert record.time_to_competition_days is not None
        assert record.time_to_competition_days >= 0
        assert record.sport is not None


def test_generated_constructs_are_all_in_the_locked_taxonomy():
    """The generator must not invent constructs -- CLAUDE.md sec.3."""
    from src.agents.config import construct_names

    valid = set(construct_names())
    for record in generate_records(200, seed=5, source_id="s"):
        for planted in record.generation_spec["planted_constructs"]:
            assert planted["construct"] in valid, planted["construct"]


def test_generated_intensities_are_within_the_taxonomy_scale():
    for record in generate_records(200, seed=6, source_id="s"):
        for planted in record.generation_spec["planted_constructs"]:
            if "intensity" in planted:
                assert planted["intensity"] in (1, 2, 3)


def test_interpretation_modifier_never_orphaned_or_contradictory():
    """The modifier needs a parent anxiety at intensity >= 2, and must agree
    with the appraisal it sits beside (Theory of Challenge and Threat States)."""
    for record in generate_records(400, seed=7, source_id="s"):
        spec = record.generation_spec
        modifier = spec["interpretation_modifier"]
        if modifier is None:
            continue
        planted = spec["planted_constructs"]
        assert any(
            p["construct"] in ("cognitive_anxiety", "somatic_anxiety")
            and p.get("intensity", 0) >= 2
            for p in planted
        ), f"{record.record_id}: modifier with no strong parent anxiety"
        appraisal = next(
            (p.get("label") for p in planted if p["construct"] == "appraisal_orientation"),
            None,
        )
        assert not (appraisal == "challenge" and modifier == "debilitative")
        assert not (appraisal == "threat" and modifier == "facilitative")


def test_some_records_carry_no_construct_at_all():
    """A corpus where every utterance expresses something teaches the model that
    everything is a signal. The taxonomy's negative examples are logistics talk."""
    records = generate_records(300, seed=8, source_id="s")
    empty = [r for r in records if not r.generation_spec["planted_constructs"]]
    assert len(empty) >= 5


def test_generation_spec_carries_its_own_circularity_warning():
    """The warning travels in the data, not only in the docs."""
    record = generate_records(1, seed=9, source_id="s")[0]
    assert "NOT a label" in record.generation_spec["NOTE"]


#: Capitalised tokens the template bank legitimately produces mid-sentence.
#: Weekdays are here because "we fly out on Thursday" is ordinary athlete
#: speech and a weekday is not an identifier -- `docs/ethics.md` sec.5.1 asks for
#: *exact dates* to be replaced by `time_to_competition`, which they are.
NON_NAME_CAPITALS = {
    "I",
    "I'm",
    "I've",
    "I'd",
    "I'll",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}


def test_generated_text_contains_no_personal_names():
    """Synthetic athlete voice uses roles, never names -- real or invented.

    Inventing names would risk colliding with a real athlete, and the corpus
    needs no identifiers at all. The check is a heuristic -- a mid-sentence
    capitalised token that is not a known non-name -- which is crude in general
    but decisive against this template bank.
    """
    records = generate_records(300, seed=10, source_id="s")
    for record in records:
        for sentence in record.text.replace("! ", ". ").split(". "):
            for word in sentence.split()[1:]:
                clean = re.sub(r"^\W+|\W+$", "", word, flags=re.UNICODE)
                if clean and clean[0].isupper() and clean not in NON_NAME_CAPITALS:
                    pytest.fail(f"possible name {clean!r} in {record.record_id}: {record.text}")


def test_generator_stamp_records_what_a2_requires():
    stamp = generator_stamp(42)
    assert stamp.seed == 42
    assert stamp.kind == "template-grammar"
    assert "synthetic.py" in stamp.prompts_location  # prompts are version-controlled
    assert stamp.generated_on


def test_synthetic_descriptor_declares_every_prohibition():
    descriptor = synthetic_descriptor(seed=42)
    assert set(descriptor.declares) == set(REQUIRED_DECLARATIONS)
    assert all(descriptor.declares.values())
    assert descriptor.allowlist_category == "A2_synthetic"
    assert descriptor.synthetic is True


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


def test_full_ingestion_round_trip(store: RawStore):
    descriptor = synthetic_descriptor("e2e", seed=11)
    stamp = generator_stamp(11)
    with store.open_source(descriptor, generator=stamp.to_dict()) as writer:
        writer.write_all(generate_records(50, seed=11, source_id="e2e"))

    provenance, records = store.read_source("e2e")
    assert provenance.record_count == len(records) == 50
    assert provenance.synthetic is True
    assert provenance.generator["seed"] == 11
    assert all(r.source_id == "e2e" for r in records)
    assert metadata_coverage(records)["time_to_competition_days"] == 1.0

    # Every source under the store is traceable -- the Phase 7 gate in one line.
    assert len(list(store.iter_all())) == 1
