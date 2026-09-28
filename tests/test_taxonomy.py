"""Phase 12 -- burden and taxonomy versioning.

The tests that matter here are the ones asserting a *refusal*: that an
unmeasured burden estimate says so, and that an added construct invalidates
the whole corpus.

Every one of those is a case where the convenient behaviour is the wrong one.

NOTE (2026-09-28): this file used to also test the disagreement-decomposition
and verdict machinery in `src/taxonomy/refinement.py` (profile_disagreements,
confusion_pairs, verdict_for, analyse) against `src/annotation/agreement.py`'s
`AgreementReport`/`ConstructAgreement`. Both modules were deleted by owner
decision -- this project no longer reports inter-annotator agreement, so
there is nothing left for that analysis to consume. See
`config/annotators.yaml`'s header and `CLAUDE.md` sec.20-21. A backup of both
deleted modules is under
`annotation/gold_dev/_backup_2026-09-28/removed_20260928/`.
"""

from __future__ import annotations

import pytest

from src.annotation.schema import GoldConstruct, GoldLabel
from src.taxonomy import (
    Changelog,
    TaxonomyVersionError,
    TimingModel,
    diff_taxonomy,
    estimate_burden,
    relabel_scope,
)
from src.taxonomy.burden import DEFAULT_TIMING, FATIGUE_HOURS_PER_ANNOTATOR
from src.taxonomy.versioning import CHANGE_ADDED, CHANGE_COSMETIC, CHANGE_REMOVED

CONSTRUCTS = ["cognitive_anxiety", "somatic_anxiety", "burnout_signal"]


# --- burden ---------------------------------------------------------------


def test_default_timing_declares_itself_unmeasured():
    """The whole point of OPEN-026: an estimate must not read as a measurement."""
    assert DEFAULT_TIMING.measured is False
    assert "UNMEASURED" in DEFAULT_TIMING.basis
    report = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS)
    assert report.to_dict()["estimate_is_measured"] is False
    assert "ESTIMATE, NOT A MEASUREMENT" in report.to_markdown()


def test_measured_model_reproduces_the_observation():
    model = TimingModel.from_measurement(
        observed_minutes_per_item=2.0, n_constructs=10, source="gold_dev, A1, stopwatch"
    )
    assert model.measured is True
    assert model.seconds_per_item(10) == pytest.approx(120.0)
    assert "MEASURED" in model.basis


def test_measurement_without_a_source_is_refused():
    with pytest.raises(ValueError, match="where the measurement came from"):
        TimingModel.from_measurement(observed_minutes_per_item=2.0, n_constructs=10, source="   ")


def test_burden_scales_with_construct_count():
    few = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS)
    many = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS + ["resilience"])
    assert many.seconds_per_item > few.seconds_per_item


def test_marginal_cost_excludes_the_shared_span_pass():
    """Dropping a construct does not remove the reading of the utterance.

    Charging each construct a share of the shared cost would overstate what a
    drop saves, which is how a taxonomy gets trimmed for no gain.
    """
    report = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS)
    row = report.per_construct[0]
    assert row.marginal_seconds_per_item == DEFAULT_TIMING.intensity_per_construct_s
    assert row.marginal_seconds_per_item < report.seconds_per_item


def test_double_annotation_is_the_default_person_hours():
    report = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS)
    assert report.n_annotators == 2
    assert report.total_hours == pytest.approx(report.hours_per_annotator * 2)


def test_fatigue_threshold_splits_a_long_batch():
    report = estimate_burden(batch="gold_eval", n_items=400, constructs=CONSTRUCTS * 4)
    assert report.exceeds_fatigue_threshold is True
    assert report.sittings >= 2
    assert report.hours_per_annotator / report.sittings <= FATIGUE_HOURS_PER_ANNOTATOR + 1e-9
    assert "tired annotators" in report.to_markdown()


# --- versioning -----------------------------------------------------------

V2 = {
    "version": 2,
    "constructs": {
        "cognitive_anxiety": {
            "label_type": "graded",
            "definition": "worry about performance",
            "edge_cases": "general life worry = 0",
            "positive_examples": ["a"],
        },
        "burnout_signal": {"label_type": "graded", "definition": "exhaustion"},
    },
}


def test_added_construct_invalidates_the_whole_corpus():
    """The counter-intuitive one: adding is not safe.

    A v2 label is silent about a new construct, and treating silence as a
    negative fabricates one on every utterance.
    """
    new = {**V2, "version": 3}
    new["constructs"] = {**V2["constructs"], "resilience": {"definition": "recovery"}}
    changes = diff_taxonomy(V2, new)
    added = [c for c in changes if c.kind == CHANGE_ADDED]
    assert [c.construct for c in added] == ["resilience"]
    assert added[0].invalidates_silver is True
    assert added[0].scope == "all"


def test_removed_and_redefined_constructs_invalidate_only_themselves():
    new = {
        "version": 3,
        "constructs": {
            "cognitive_anxiety": {
                **V2["constructs"]["cognitive_anxiety"],
                "definition": "worry about performance AND its consequences",
            }
        },
    }
    changes = diff_taxonomy(V2, new)
    kinds = {c.kind for c in changes}
    assert CHANGE_REMOVED in kinds
    assert all(c.scope != "all" for c in changes)


def test_reworded_examples_are_cosmetic_and_not_auto_approved():
    new = {"version": 3, "constructs": dict(V2["constructs"])}
    new["constructs"]["cognitive_anxiety"] = {
        **V2["constructs"]["cognitive_anxiety"],
        "positive_examples": ["a", "b"],
    }
    changes = diff_taxonomy(V2, new)
    cosmetic = [c for c in changes if c.kind == CHANGE_COSMETIC]
    assert cosmetic and cosmetic[0].invalidates_silver is False
    log = Changelog(old_version=2, new_version=3, reason="add an example", changes=changes)
    assert "Awaiting owner confirmation" in log.to_markdown()


def test_whitespace_reflow_is_not_a_change():
    new = {"version": 3, "constructs": dict(V2["constructs"])}
    new["constructs"]["burnout_signal"] = {"label_type": "graded", "definition": "  exhaustion \n"}
    assert diff_taxonomy(V2, new) == []


class _Item:
    def __init__(self, construct):
        self.construct = construct


class _Label:
    def __init__(self, record_id, text, constructs):
        self.record_id = record_id
        self.text = text
        self.labels = [_Item(c) for c in constructs]


def test_relabel_scope_counts_distinct_texts_not_just_records():
    """Phase 9 measured 87.4% duplication; the record count overstates the bill."""
    labels = [
        _Label("r1", "same text", ["cognitive_anxiety"]),
        _Label("r2", "same text", ["cognitive_anxiety"]),
        _Label("r3", "other", ["burnout_signal"]),
    ]
    changes = diff_taxonomy(
        V2,
        {
            "version": 3,
            "constructs": {
                **V2["constructs"],
                "cognitive_anxiety": {
                    **V2["constructs"]["cognitive_anxiety"],
                    "definition": "changed",
                },
            },
        },
    )
    scope = relabel_scope(changes, labels)
    assert scope.affected_records == 2
    assert scope.distinct_texts_affected == 1
    assert scope.whole_corpus is False
    assert scope.share == pytest.approx(2 / 3)


def test_version_must_advance():
    with pytest.raises(TaxonomyVersionError, match="does not advance"):
        Changelog(old_version=2, new_version=2, reason="x", changes=[])


def test_a_change_without_a_reason_is_refused():
    changes = diff_taxonomy(V2, {"version": 3, "constructs": {}})
    with pytest.raises(TaxonomyVersionError, match="needs a stated reason"):
        Changelog(old_version=2, new_version=3, reason="  ", changes=changes)


def test_no_change_is_a_legitimate_phase_12_outcome():
    log = Changelog(old_version=2, new_version=3, reason="", changes=[])
    assert "carried into the freeze unchanged" in log.to_markdown()


# --- the gate -------------------------------------------------------------


def test_gate_burden_runs_today(capsys):
    from scripts import run_taxonomy_refinement as gate

    assert gate.main(["--burden"]) == 0
    out = capsys.readouterr().out
    assert "OPEN-026: STILL OPEN" in out


def test_gate_refuses_an_unattributed_measurement(capsys):
    from scripts import run_taxonomy_refinement as gate

    assert gate.main(["--burden", "--measured-minutes-per-item", "2.0"]) == 2


def test_gate_does_not_write_the_taxonomy(tmp_path):
    """A construct set a script can edit is not frozen."""
    from scripts import run_taxonomy_refinement as gate

    path = gate.REPO_ROOT / "config" / "taxonomy.yaml"
    before = path.read_bytes()
    gate.main(["--status"])
    gate.main(["--burden"])
    assert path.read_bytes() == before


def test_gold_labels_still_refuse_a_machine_author():
    """Phase 12 reads gold; it must not become a way to write it."""
    from src.annotation.schema import GoldSchemaError

    with pytest.raises(GoldSchemaError, match="human-owned"):
        GoldLabel(
            record_id="r1",
            parent_record_id="p1",
            text="I am worried",
            annotator_id="A1",
            batch="gold_dev",
            constructs=(
                GoldConstruct(
                    construct="cognitive_anxiety",
                    value="present",
                    intensity=2,
                    evidence_spans=("worried",),
                ),
            ),
            author_kind="machine",
        )
