"""Tests against Potato 2.7.1's **recorded, real** output.

This file exists because OPEN-027 turned out not to be a formality. The Phase 11
ingest path had been written against an assumed Potato interface and, when it
finally met the real one, did not work at all -- and the worst of the three
mismatches failed *silently*, dropping every span rather than raising.

So every fixture here was produced by Potato's own serialiser, not by hand (see
`tests/fixtures/potato/README.md`). A fixture written by the author of the
parser cannot detect the author's wrong assumption; a recorded artifact can.

The tests are grouped by the property they defend:

1. **Discovery** -- the passes are where Potato actually puts them.
2. **Span recovery** -- offset-only spans become evidence, or are refused.
3. **Equivalence** -- the raw state file and the export agree.
4. **End to end** -- two real passes become a kappa with a bootstrap interval.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.config import load_taxonomy
from src.annotation import (
    Annotator,
    GoldStore,
    PotatoOutputError,
    PotatoPass,
    compute_agreement,
    discover_passes,
    ingest_passes,
    read_pass,
    resolve_span_surface,
)

FIXTURES = Path(__file__).parent / "fixtures" / "potato"
OUTPUT_DIR = FIXTURES / "annotation_output"


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return load_taxonomy()


@pytest.fixture(scope="module")
def item_texts() -> dict[str, str]:
    rows = [
        json.loads(line)
        for line in (FIXTURES / "items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {row["id"]: row["text"] for row in rows}


def roster() -> dict[str, Annotator]:
    # A2 is deliberately absent from the shipped config/annotators.yaml because
    # no such person has been recruited. Here they are a fixture, so the
    # agreement arithmetic can be exercised without inventing a real annotator.
    return {
        "A1": Annotator("A1", "owner", True),
        "A2": Annotator("A2", "peer", False),
    }


# ---------------------------------------------------------------------------
# 1. Discovery
# ---------------------------------------------------------------------------


def test_passes_are_found_where_potato_actually_writes_them():
    """Potato writes `<output_dir>/<user_id>/user_state.json`.

    The original implementation globbed for `**/*.jsonl` and therefore found
    nothing at all -- `--ingest` exited with 'has the annotator finished a
    pass?' while a completed pass sat on disk.
    """
    passes = discover_passes(OUTPUT_DIR)
    assert [p.annotator_id for p in passes] == ["A1", "A2"]
    assert all(p.kind == "user_state" for p in passes)
    assert all(p.path.name == "user_state.json" for p in passes)


def test_discovery_of_an_empty_directory_is_empty_not_an_error(tmp_path):
    """'Nobody has annotated yet' is a normal state and needs different advice
    from 'the output is malformed', so it must not raise."""
    assert discover_passes(tmp_path) == []
    assert discover_passes(tmp_path / "does-not-exist") == []


def test_the_export_is_only_read_when_no_raw_state_exists(tmp_path):
    """Otherwise the same pass would be ingested twice and every item would be
    silently double-counted in the agreement denominator."""
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "annotations.jsonl").write_text(
        (FIXTURES / "export" / "annotations.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )
    passes = discover_passes(tmp_path)
    assert [p.annotator_id for p in passes] == ["A1", "A2"]
    assert all(p.kind == "export" for p in passes)


# ---------------------------------------------------------------------------
# 2. Span recovery -- the silent failure
# ---------------------------------------------------------------------------


def test_spans_are_recovered_from_offsets(item_texts):
    """Potato spans carry `start`/`end` and no surface text whatsoever."""
    payloads, problems = read_pass(
        PotatoPass("A1", OUTPUT_DIR / "A1" / "user_state.json", "user_state"),
        item_texts=item_texts,
    )
    assert problems == []
    spans = [s for p in payloads for s in p["span_annotations"]]
    assert spans, "the recorded pass contains spans; recovering none is the OPEN-027 defect"
    for span in spans:
        assert span["span"], "a recovered span must carry its surface text"


def test_every_recovered_span_is_a_literal_substring(item_texts):
    """The invariant `SilverLabel` enforces procedurally, gold gets structurally:
    the surface is a slice of the utterance, so a paraphrase is unrepresentable."""
    for pass_id in ("A1", "A2"):
        payloads, _ = read_pass(
            PotatoPass(pass_id, OUTPUT_DIR / pass_id / "user_state.json", "user_state"),
            item_texts=item_texts,
        )
        for payload in payloads:
            text = item_texts[payload["id"]]
            for span in payload["span_annotations"]:
                assert span["span"] in text


def test_offsets_outside_the_utterance_are_refused_not_clipped():
    """A clipped span is not the span the annotator marked. Refusing surfaces a
    real divergence between the batch and what was annotated."""
    with pytest.raises(PotatoOutputError) as exc:
        resolve_span_surface({"start": 5, "end": 900}, "short text")
    assert "do not lie inside" in str(exc.value)


def test_a_span_with_no_offsets_is_refused():
    with pytest.raises(PotatoOutputError):
        resolve_span_surface({"name": "cognitive_anxiety"}, "some text")


def test_a_whitespace_only_span_is_refused():
    with pytest.raises(PotatoOutputError):
        resolve_span_surface({"start": 4, "end": 5}, "abcd efgh")


def test_an_annotation_of_an_unknown_item_is_reported(item_texts):
    """An annotation of an item nobody was handed cannot enter the gold set."""
    payloads, problems = read_pass(
        PotatoPass("A1", OUTPUT_DIR / "A1" / "user_state.json", "user_state"),
        item_texts={"not-the-batch": "irrelevant"},
    )
    assert payloads == []
    assert problems and all("not in the batch" in message for _, message in problems)


# ---------------------------------------------------------------------------
# 3. The two artifacts agree
# ---------------------------------------------------------------------------


def test_raw_state_and_export_produce_identical_payloads(item_texts):
    """An annotator who hands over an export must not get a different answer
    from one who hands over the project directory."""
    for annotator in ("A1", "A2"):
        from_state, _ = read_pass(
            PotatoPass(annotator, OUTPUT_DIR / annotator / "user_state.json", "user_state"),
            item_texts=item_texts,
        )
        from_export, _ = read_pass(
            PotatoPass(annotator, FIXTURES / "export" / "annotations.jsonl", "export"),
            item_texts=item_texts,
        )
        key = lambda payloads: sorted(json.dumps(p, sort_keys=True) for p in payloads)  # noqa: E731
        assert key(from_state) == key(from_export)


# ---------------------------------------------------------------------------
# 4. End to end: real output -> gold labels -> kappa
# ---------------------------------------------------------------------------


def test_real_potato_output_ingests_into_gold_labels(taxonomy, item_texts):
    report = ingest_passes(
        [PotatoPass("A1", OUTPUT_DIR / "A1" / "user_state.json", "user_state")],
        item_texts=item_texts,
        annotator_id="A1",
        batch="gold_dev",
        valid_constructs=taxonomy["constructs"],
    )
    assert report.ok, [str(e) for e in report.errors]
    assert report.labels

    by_id = {label.record_id: label for label in report.labels}
    stressed = by_id["synth_precomp_v1-000008#u0"]
    assert stressed.intensity_for("perceived_stress") == 2
    assert stressed.spans_for("perceived_stress") == ("a lot on right now",)

    # A categorical pole recorded as a span label decodes to the construct value.
    motivated = by_id["synth_precomp_v1-000011#u1"]
    assert motivated.value_for("motivation_orientation") == "approach"


def test_two_real_passes_yield_a_kappa_with_an_interval(taxonomy, item_texts, tmp_path):
    """The whole Phase 11 arc on real output: two passes in, agreement out.

    Deliberately written against a tmp_path store and a fixture roster. Nothing
    here may write into the repository's `data/gold/`, which belongs to whoever
    actually did the annotating.
    """
    store = GoldStore(root=tmp_path, roster=roster())
    for annotator in ("A1", "A2"):
        report = ingest_passes(
            [PotatoPass(annotator, OUTPUT_DIR / annotator / "user_state.json", "user_state")],
            item_texts=item_texts,
            annotator_id=annotator,
            batch="gold_dev",
            valid_constructs=taxonomy["constructs"],
        )
        assert report.ok, [str(e) for e in report.errors]
        store.write_pass(report.labels, annotator=roster()[annotator], batch="gold_dev")

    passes = store.read_batch("gold_dev")
    assert sorted(passes) == ["A1", "A2"]

    agreement = compute_agreement(
        passes, list(taxonomy["constructs"]), batch="gold_dev", bootstrap=50
    )
    assert agreement.n_paired > 0

    # The two rehearsal passes were built to differ on intensity while agreeing
    # on presence, so perceived_stress must show up as a graded disagreement
    # rather than a presence one.
    stress = next(c for c in agreement.constructs if c.construct == "perceived_stress")
    assert stress.only_a == 0 and stress.only_b == 0
    assert stress.weighted_kappa <= stress.kappa

    assert "inter-annotator agreement" in agreement.to_markdown().lower()


def test_the_bootstrap_interval_is_suppressed_on_a_tiny_batch(taxonomy, item_texts, tmp_path):
    """Five items cannot support a percentile bootstrap, and a CI printed from
    five items would be quoted as though it meant something."""
    store = GoldStore(root=tmp_path, roster=roster())
    for annotator in ("A1", "A2"):
        report = ingest_passes(
            [PotatoPass(annotator, OUTPUT_DIR / annotator / "user_state.json", "user_state")],
            item_texts=item_texts,
            annotator_id=annotator,
            batch="gold_dev",
            valid_constructs=taxonomy["constructs"],
        )
        store.write_pass(report.labels, annotator=roster()[annotator], batch="gold_dev")

    agreement = compute_agreement(
        store.read_batch("gold_dev"), list(taxonomy["constructs"]), batch="gold_dev", bootstrap=50
    )
    assert all(c.kappa_ci is None for c in agreement.constructs)
