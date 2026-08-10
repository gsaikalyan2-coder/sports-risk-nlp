"""Tests for the lexical-variation audit (Phase 9, OPEN-015 / OPEN-016).

The important test in this file is `test_every_flagged_signature_has_a_verdict`.
It is the ratchet: adding a synonym group or a template that creates a new
flagged frame fails the build until a human rules on it. OPEN-015 existed
because no such control existed, and a control that only runs when somebody
remembers to run it is not a control.
"""

from __future__ import annotations

import pytest

from src.ingestion import synthetic
from src.ingestion.synonym_audit import (
    BROKEN,
    DEGRADED,
    VERDICTS,
    audit,
    contains,
    corpus_prevalence,
    defect_rate,
    defective,
    sentences,
    substitution_events,
    tokenise,
    unreviewed,
    varied_templates,
)

# --- the ratchet ----------------------------------------------------------


def test_every_flagged_signature_has_a_verdict():
    missing = unreviewed(audit())
    assert not missing, (
        "the audit flagged frames nobody has ruled on: "
        f"{missing}. Add each to VERDICTS in src/ingestion/synonym_audit.py "
        "after reading the rendered frame. Do NOT delete the probe."
    )


def test_no_orphan_verdicts():
    """A verdict for a frame the bank can no longer produce is stale."""
    produced = {f.signature for f in audit()}
    orphans = sorted(set(VERDICTS) - produced)
    assert not orphans, f"VERDICTS entries no longer produced by any probe: {orphans}"


def test_verdict_values_are_from_the_closed_set():
    assert set(VERDICTS.values()) <= {"broken", "degraded", "acceptable"}


# --- OPEN-015 regression --------------------------------------------------


def test_part_of_me_group_is_gone():
    for group in synthetic.SYNONYM_GROUPS:
        assert "part" not in group, (
            "the ('part', 'portion', 'corner', 'piece') group was removed at "
            "generator v1.2 because every occurrence of 'part' in the template "
            "bank sits inside the idiom 'part of me' (OPEN-015). Do not reinstate."
        )


@pytest.mark.parametrize("phrase", ["corner of me", "portion of me", "piece of me"])
def test_regenerated_corpus_contains_no_broken_part_idiom(phrase: str):
    records = synthetic.generate_records(300, seed=42, source_id="test_open015")
    assert not [r for r in records if phrase in r.text.lower()]


def test_part_of_me_stays_in_the_fixed_expression_inventory():
    """The group is gone; the guard against re-adding it must not be."""
    from src.ingestion.synonym_audit import FIXED_EXPRESSIONS

    assert "part of me" in FIXED_EXPRESSIONS


# --- probe machinery ------------------------------------------------------


def test_substitution_space_is_deterministic_and_non_trivial():
    first, second = substitution_events(), substitution_events()
    assert first == second
    assert len(first) > 100


def test_slot_fillers_are_substitutable_so_every_sport_must_be_enumerated():
    """The assumption that broke the first version of the sweep.

    Slot fillers are ordinary words and some of them are in the synonym bank
    (`race`, `start`). Enumerating one sport therefore misses frames -- it hid
    "at the outset line" until this test was written. The test pins both halves:
    that fillers really are substitutable, and that every sport is covered.
    """
    substitutable = {
        token
        for event, start in synthetic.SPORT_TERMS.values()
        for token in tokenise(f"{event} {start}")
        if token in synthetic._SYNONYM_INDEX
    }
    assert substitutable, "if this is ever empty, simplify varied_templates()"

    texts = {text for _, text in varied_templates()}
    for sport in synthetic.SPORTS:
        event, _ = synthetic.SPORT_TERMS[sport]
        assert any(event in text for text in texts), f"{sport} not enumerated"


def test_interpretation_bank_is_not_enumerated():
    """`generate_records` does not call `_vary` on interpretation sentences."""
    ids = {tid for tid, _ in varied_templates()}
    assert not [i for i in ids if i.startswith("interp")]


def test_sentences_split_on_terminal_punctuation():
    assert sentences("I'm just drained. I don't even care.") == [
        "I'm just drained.",
        "I don't even care.",
    ]


def test_signature_does_not_match_across_a_sentence_boundary():
    """The "hollowed out i" regression: punctuation must bound a frame."""
    text = "I'm just hollowed out. I don't even care how this one goes."
    assert corpus_prevalence(
        [f for f in audit() if f.signature == "just hollowed out"], [text]
    ) == {"just hollowed out": 1}
    pieces = [tokenise(s) for s in sentences(text)]
    assert not any(contains(t, tokenise("hollowed out i")) for t in pieces)


def test_contains_matches_contiguous_runs_only():
    assert contains(["a", "b", "c"], ["b", "c"])
    assert not contains(["a", "b", "c"], ["a", "c"])
    assert not contains(["a"], ["a", "b"])


def test_corpus_prevalence_counts_texts_not_occurrences():
    findings = [f for f in audit() if f.signature == "figure about"]
    assert findings, "expected the 'think -> figure' frame to be flagged"
    counts = corpus_prevalence(findings, ["I figure about it. I figure about it again."])
    assert counts["figure about"] == 1


def test_defect_rate_is_record_level():
    hits, total = defect_rate(audit(), ["we've got a approach for the start. an chance."])
    assert (hits, total) == (1, 1)


def test_known_defect_classes_are_all_represented():
    """Each probe must actually be earning its place."""
    probes = {f.probe for f in defective(audit())}
    assert probes == {"idiom", "article", "number", "particle", "form", "arity"}


def test_defective_is_broken_or_degraded_only():
    assert {f.verdict for f in defective(audit())} <= {BROKEN, DEGRADED}
