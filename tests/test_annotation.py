"""Tests for the Phase 11 annotation pipeline.

Three things are defended here, in order of how badly they break the paper:

1. **`data/gold/` stays human-owned.** Not by convention -- by a schema with no
   machine author, a roster of real people, and a store that refuses anything
   else.
2. **The annotator sees the whole record.** The defect this phase opened with.

NOTE (2026-09-28): this file used to also test the agreement arithmetic
(Cohen's kappa, weighted kappa, span F1, the adjudication worklist). That
suite was deleted along with `src/annotation/agreement.py` -- see
`config/annotators.yaml`'s header and `CLAUDE.md` sec.20-21 for why this
project no longer reports inter-annotator agreement. A backup of the deleted
module (and its tests, if needed later) is under
`annotation/gold_dev/_backup_2026-09-28/removed_20260928/`.

Everything is offline and free; nothing here touches a network or a model.
"""

from __future__ import annotations

import json

import pytest

from src.agents.config import load_taxonomy
from src.annotation import (
    AnnotationItem,
    Annotator,
    ContextError,
    GoldConstruct,
    GoldLabel,
    GoldSchemaError,
    GoldStore,
    GoldWriteRefused,
    build_config,
    build_items,
    context_coverage,
    ingest_potato,
    parse_annotation,
    span_labels,
    write_project,
)
from src.annotation.potato_project import REQUIRED_CONFIG_KEYS
from src.annotation.schema import load_annotators

TEXT = "I keep thinking about the ways this could go wrong before the final."
PARENT = f"The taper went fine. {TEXT} Kit arrived on Tuesday."


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return load_taxonomy()


def make_item(record_id: str = "s-p0#u1", text: str = TEXT, siblings: int = 3) -> AnnotationItem:
    return AnnotationItem(
        record_id=record_id,
        parent_record_id="p0",
        text=text,
        parent_text=PARENT,
        utterance_index=1,
        siblings=siblings,
        time_to_competition_days=2,
    )


def gold(
    annotator: str = "A1",
    *,
    record_id: str = "s-p0#u1",
    constructs: tuple[GoldConstruct, ...] = (),
    **kw,
) -> GoldLabel:
    defaults = dict(
        record_id=record_id,
        parent_record_id="p0",
        text=TEXT,
        annotator_id=annotator,
        batch="gold_dev",
        constructs=constructs,
    )
    defaults.update(kw)
    return GoldLabel(**defaults)  # type: ignore[arg-type]


def anxiety(intensity: int = 2, span: str = "I keep thinking") -> GoldConstruct:
    return GoldConstruct("cognitive_anxiety", "present", intensity, (span,))


# ---------------------------------------------------------------------------
# Context: the defect this phase opened with
# ---------------------------------------------------------------------------


def test_the_target_is_marked_inside_its_record():
    html = make_item().context_html()
    assert "<mark>" in html
    assert "The taper went fine." in html


def test_context_html_escapes_before_marking():
    """The corpus is synthetic today. An A3 donation is arbitrary text, and it
    must not be able to inject markup into the annotator's browser."""
    item = AnnotationItem(
        record_id="x",
        parent_record_id="p",
        text="<script>alert(1)</script>",
        parent_text="before <script>alert(1)</script> after",
        utterance_index=0,
        siblings=2,
    )
    html = item.context_html()
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_potato_row_is_a_whitelist_not_a_dump():
    """Only four keys reach the tool. Anything else on a candidate -- including
    annotation_batch, which says whether this is the evaluation set -- stays off
    the annotator's screen."""
    assert set(make_item().to_potato_row()) == {"id", "text", "context_html", "meta"}


def test_build_items_refuses_generation_spec():
    with pytest.raises(ContextError, match="generation_spec"):
        build_items(
            [{"record_id": "r", "parent_record_id": "p", "text": TEXT, "generation_spec": {}}],
            contexts={"p": PARENT},
            siblings={"p": 2},
        )


def test_build_items_refuses_to_guess_missing_context():
    """A silent fallback to the bare utterance would reintroduce the defect on a
    subset, invisibly, and a kappa over a mixture is not interpretable."""
    with pytest.raises(ContextError, match="not in data/interim"):
        build_items(
            [{"record_id": "r", "parent_record_id": "missing", "text": TEXT}],
            contexts={"p": PARENT},
            siblings={"p": 2},
        )


def test_annotation_batch_is_allowed_to_exist():
    """It is written by the Phase 9 sampler on purpose. An earlier draft refused
    it and the build died on valid data -- presence and display are different
    questions."""
    items = build_items(
        [
            {
                "record_id": "r",
                "parent_record_id": "p",
                "text": TEXT,
                "annotation_batch": "gold_eval",
            }
        ],
        contexts={"p": PARENT},
        siblings={"p": 2},
    )
    assert items[0].record_id == "r"


def test_context_coverage_reports_what_was_gained():
    stats = context_coverage([make_item(), make_item("s-p1#u0", siblings=1)])
    assert stats["items"] == 2
    assert stats["with_multi_utterance_context"] == 1


# ---------------------------------------------------------------------------
# Potato project generation
# ---------------------------------------------------------------------------


def test_every_construct_reaches_the_screen(taxonomy):
    """The taxonomy is the single source of truth. A construct that never
    renders is a construct nobody can annotate, and its kappa is undefined for a
    reason no one would find."""
    labels = {entry["name"].split(":")[0] for entry in span_labels(taxonomy)}
    assert labels == set(taxonomy["constructs"])


def test_categorical_constructs_get_one_span_label_per_pole(taxonomy):
    names = {entry["name"] for entry in span_labels(taxonomy)}
    assert "motivation_orientation:approach" in names
    assert "motivation_orientation:avoidance" in names
    # mixed is derived from marking both poles; a `mixed` span would let an
    # annotator assert co-presence without evidencing either side.
    assert not any(n.endswith(":mixed") or n.endswith(":none") for n in names)


def test_config_carries_potatos_required_keys(taxonomy):
    config = build_config(
        task_name="t",
        data_file="data/x.jsonl",
        output_dir="out/",
        task_dir="/tmp/t",
        taxonomy=taxonomy,
    )
    for key in REQUIRED_CONFIG_KEYS:
        assert key in config


def test_context_is_a_display_scheme_and_the_utterance_is_the_annotated_text(taxonomy):
    """Span offsets must land on the utterance, or they stop lining up with
    InterimRecord offsets and with SilverLabel spans."""
    config = build_config(
        task_name="t", data_file="d", output_dir="o", task_dir="/tmp", taxonomy=taxonomy
    )
    by_name = {s["name"]: s for s in config["annotation_schemes"]}
    assert by_name["context"]["annotation_type"] == "pure_display"
    assert by_name["evidence"]["annotation_type"] == "span"
    assert config["item_properties"]["text_key"] == "text"


def test_sign_up_is_closed(taxonomy):
    """An unexpected third login would silently add a third annotator with a
    partial pass, and Cohen's kappa is defined for a pair."""
    config = build_config(
        task_name="t",
        data_file="d",
        output_dir="o",
        task_dir="/tmp",
        taxonomy=taxonomy,
        annotators=["A1", "A2"],
    )
    assert config["user_config"]["allow_all_users"] is False
    assert config["user_config"]["users"] == ["A1", "A2"]


def test_both_annotators_get_the_same_items(taxonomy, tmp_path):
    """100% double annotation is what makes a per-construct kappa computable.
    Splitting the data per annotator would produce two disjoint passes."""
    items = [make_item(f"s-p{i}#u0") for i in range(5)]
    paths = write_project(items, batch="gold_dev", taxonomy=taxonomy, root=tmp_path)
    rows = [
        json.loads(line)
        for line in paths["data"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 5
    assert paths["config"].exists()


# ---------------------------------------------------------------------------
# Gold schema: human-owned, structurally
# ---------------------------------------------------------------------------


def test_a_gold_label_cannot_be_machine_authored():
    with pytest.raises(GoldSchemaError, match="human-owned"):
        gold(author_kind="model")


def test_a_gold_label_needs_an_annotator():
    with pytest.raises(GoldSchemaError, match="annotator_id"):
        gold(annotator="")


def test_a_present_construct_needs_a_span():
    with pytest.raises(GoldSchemaError, match="needs at least one span"):
        GoldConstruct("cognitive_anxiety", "present", 2, ())


def test_a_span_must_be_a_literal_substring():
    """For a human this catches the mis-copied offset, which is the common
    failure and the reason this project uses a tool rather than a spreadsheet."""
    bad = GoldConstruct("cognitive_anxiety", "present", 2, ("worrying about it",))
    with pytest.raises(GoldSchemaError, match="not a literal substring"):
        gold(constructs=(bad,))


def test_escalated_items_carry_no_labels():
    with pytest.raises(GoldSchemaError, match="escalated but asserts"):
        gold(constructs=(anxiety(),), escalate=True, escalate_reason="unreadable")


def test_escalation_needs_a_reason():
    """One of the reasons is an ethics incident and the others are not; the
    register has to be able to tell them apart."""
    with pytest.raises(GoldSchemaError, match="no reason"):
        gold(escalate=True)


def test_modifier_requires_an_anxiety_construct():
    with pytest.raises(GoldSchemaError, match="interpretation_modifier"):
        gold(interpretation_modifier="facilitative")


def test_unmarked_construct_is_an_assertion_of_absence():
    """Treating it as missing data would restrict every kappa to the items both
    annotators marked -- the subset they already agree on."""
    label = gold(constructs=(anxiety(),))
    assert label.value_for("burnout_signal") == "none"
    assert label.intensity_for("burnout_signal") == 0


def test_gold_round_trips_through_json():
    original = gold(constructs=(anxiety(),), interpretation_modifier="unclear")
    restored = GoldLabel.from_json_line(original.to_json_line())
    assert restored.constructs == original.constructs
    assert restored.interpretation_modifier == "unclear"


# ---------------------------------------------------------------------------
# The store: four locks on data/gold/
# ---------------------------------------------------------------------------


def roster() -> dict[str, Annotator]:
    return {
        "A1": Annotator("A1", "owner", True),
        "A2": Annotator("A2", "peer", False),
    }


def test_the_shipped_roster_holds_exactly_the_one_annotator():
    """**Single-annotator by decision, 2026-09-28.** A2 had been recruited
    (OPEN-025 resolved 2026-08-12) but never annotated anything, and the owner
    decided to proceed on A1's single pass rather than wait -- see
    `config/annotators.yaml`'s header and `CLAUDE.md` sec.20-21. This test
    previously asserted `== ["A1", "A2"]`; it is back to `== ["A1"]`, and that
    is not a regression, it is the roster reflecting the decision.

    The assertion stays *exact* rather than relaxing to `>= 1`. The roster is a
    lock, not a list: `src/annotation/store.py` refuses any gold label whose
    `annotator_id` is not here, and a test that tolerates extra entries would
    let a second annotator appear -- by typo or by a well-meaning future
    session inventing one to make a pipeline run -- without anything failing.
    """
    assert sorted(load_annotators()) == ["A1"]


def test_exactly_one_roster_entry_is_the_owner():
    """Agreement is a property of a pair of *distinct* people. Two owner flags
    would mean the roster had been edited by duplicating A1's entry, which is
    the cheapest way to fake a second annotator and produce a kappa of 1.0."""
    owners = [a for a in load_annotators().values() if a.is_owner]
    assert len(owners) == 1, f"expected exactly one owner, found {[a.annotator_id for a in owners]}"


def test_store_refuses_an_annotator_not_on_the_roster(tmp_path):
    store = GoldStore(root=tmp_path, roster=roster())
    with pytest.raises(GoldWriteRefused) as exc:
        store.resolve_annotator("someone_else")
    assert exc.value.reason_code == "UNKNOWN_ANNOTATOR"


def test_store_refuses_a_label_attributed_to_a_different_person(tmp_path):
    store = GoldStore(root=tmp_path, roster=roster())
    with pytest.raises(GoldWriteRefused) as exc:
        store.write_pass([gold("A2")], annotator=roster()["A1"], batch="gold_dev")
    assert exc.value.reason_code == "ANNOTATOR_MISMATCH"


def test_store_refuses_to_mix_the_calibration_and_evaluation_batches(tmp_path):
    store = GoldStore(root=tmp_path, roster=roster())
    with pytest.raises(GoldWriteRefused) as exc:
        store.write_pass(
            [gold("A1", batch="gold_dev")], annotator=roster()["A1"], batch="gold_eval"
        )
    assert exc.value.reason_code == "BATCH_MISMATCH"


def test_store_will_not_silently_replace_a_completed_pass(tmp_path):
    """A pass is hours of human work. Re-running a script must not destroy it."""
    store = GoldStore(root=tmp_path, roster=roster())
    store.write_pass([gold("A1")], annotator=roster()["A1"], batch="gold_dev")
    with pytest.raises(GoldWriteRefused) as exc:
        store.write_pass([gold("A1")], annotator=roster()["A1"], batch="gold_dev")
    assert exc.value.reason_code == "PASS_ALREADY_EXISTS"


def test_store_round_trips_and_records_whether_it_is_double_annotated(tmp_path):
    store = GoldStore(root=tmp_path, roster=roster())
    store.write_pass([gold("A1")], annotator=roster()["A1"], batch="gold_dev")
    assert store.read_manifest("gold_dev")["double_annotated"] is False
    store.write_pass([gold("A2")], annotator=roster()["A2"], batch="gold_dev")
    assert store.read_manifest("gold_dev")["double_annotated"] is True
    assert sorted(store.read_batch("gold_dev")) == ["A1", "A2"]


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------


def potato_payload(**kw) -> dict:
    payload = {
        "id": "s-p0#u1",
        "span_annotations": [
            {"annotation": "cognitive_anxiety", "span": "I keep thinking"},
        ],
        "annotations": {"intensity_cognitive_anxiety": "2 moderate"},
    }
    payload.update(kw)
    return payload


def test_ingest_reads_a_clean_annotation(taxonomy):
    label = parse_annotation(
        potato_payload(),
        item_text=TEXT,
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert label.intensity_for("cognitive_anxiety") == 2
    assert label.spans_for("cognitive_anxiety") == ("I keep thinking",)


def test_ingest_derives_mixed_from_two_poles(taxonomy):
    """Guidelines sec.2b defines mixed as both poles present, each with a span.
    Deriving it is more faithful than a `mixed` button nobody has to evidence."""
    payload = potato_payload(
        span_annotations=[
            {"annotation": "motivation_orientation:approach", "span": "I keep"},
            {"annotation": "motivation_orientation:avoidance", "span": "go wrong"},
        ],
        annotations={"intensity_motivation_orientation": "2 moderate"},
    )
    label = parse_annotation(
        payload,
        item_text=TEXT,
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert label.value_for("motivation_orientation") == "mixed"


def test_ingest_refuses_intensity_without_a_span(taxonomy):
    payload = potato_payload(span_annotations=[])
    with pytest.raises(Exception) as exc:
        parse_annotation(
            payload,
            item_text=TEXT,
            annotator_id="A1",
            batch="gold_dev",
            valid_constructs=taxonomy["constructs"],
        )
    assert "INTENSITY_WITHOUT_SPAN" in str(exc.value)


def test_ingest_refuses_a_span_with_intensity_zero(taxonomy):
    payload = potato_payload(annotations={"intensity_cognitive_anxiety": "0 none"})
    with pytest.raises(Exception) as exc:
        parse_annotation(
            payload,
            item_text=TEXT,
            annotator_id="A1",
            batch="gold_dev",
            valid_constructs=taxonomy["constructs"],
        )
    assert "SPAN_WITHOUT_INTENSITY" in str(exc.value)


def test_ingest_records_escalation_without_labels(taxonomy):
    payload = potato_payload(
        annotations={"evidence:::bad_text": True, "note": "identifying info survived"},
        span_annotations=[],
    )
    label = parse_annotation(
        payload,
        item_text=TEXT,
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert label.escalate and not label.constructs


def test_ingest_refuses_an_item_nobody_was_asked_to_label(taxonomy, tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text(json.dumps(potato_payload(id="not-in-batch")) + "\n", encoding="utf-8")
    report = ingest_potato(
        [path],
        item_texts={"s-p0#u1": TEXT},
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert not report.ok
    assert report.errors[0].reason == "UNKNOWN_ITEM"


def test_ingest_skips_items_not_yet_annotated(taxonomy, tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text(json.dumps({"id": "s-p0#u1", "annotations": {}}) + "\n", encoding="utf-8")
    report = ingest_potato(
        [path],
        item_texts={"s-p0#u1": TEXT},
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert report.ok and report.skipped_unannotated == 1
