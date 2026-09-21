"""Abstention-aware evaluation: the gates' cost, and the routes they miss.

These tests pin the arithmetic and the honesty rules. They do **not** pin the
headline figures themselves -- `reports/abstention.md` is regenerated, and a
test asserting 71.0% would have to be edited every time the cue list moves,
which is how a number stops being a measurement and becomes a fixture.

What is pinned instead: that the decomposition is exhaustive, that each route is
reachable, that the counterfactual uses the evaluated cue list rather than the
widened dashboard one, and that the report states its limitations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.evaluation.abstention import (
    CAUSES,
    JUNK_CLASSES,
    MIDPOINT,
    build_report,
    counterfactual_index,
    evaluate,
    load_corpus,
    render_markdown,
    summarise,
)

CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "processed" / "gold_candidates"

#: Text that reads as an athlete but contains no frozen cue phrase. The
#: `no_detection` route, which is the one the gates do not close.
SILENT_BUT_REAL = "I woke early and lay there listening to the rain before the final."


def _corpus() -> tuple[str, ...]:
    texts = load_corpus(CORPUS_DIR)
    if not texts:  # pragma: no cover - thin checkout
        pytest.skip("gold_candidates corpus is not present.")
    return texts


# ---------------------------------------------------------------------------
# The arithmetic
# ---------------------------------------------------------------------------


def test_empty_text_reaches_the_midpoint() -> None:
    """The defect this module exists to measure, stated as a test.

    An empty string -- what a missing OCR engine yields -- scores exactly 50 out
    of 100. If this ever stops being true the report's whole argument changes
    and it should fail loudly rather than quietly reporting zeros.
    """
    assert counterfactual_index("") == pytest.approx(MIDPOINT)


def test_a_text_with_a_cue_moves_off_the_midpoint() -> None:
    """The control. Without this the midpoint result could just mean 'broken'."""
    moved = [text for text in _corpus() if counterfactual_index(text) != pytest.approx(MIDPOINT)]
    assert moved, "no corpus text moves the index; the detector is not running"


def test_every_outcome_has_exactly_one_cause() -> None:
    """The decomposition must be exhaustive, or the shares do not sum."""
    outcomes = [evaluate(text, "corpus") for text in _corpus()]
    assert all(o.cause in CAUSES for o in outcomes)
    result = summarise(outcomes, "corpus")
    assert sum(count for _, count in result.causes) == result.n


def test_refusal_outranks_the_other_causes() -> None:
    """A refused text never reaches the scorer, so its cause is `refused`.

    Empty text is both refused and at the midpoint with nothing detected. If the
    ordering in `Outcome.cause` ever flipped, refusals would be double-counted
    as live defects and the report would overstate its own finding.
    """
    assert evaluate("", "junk").cause == "refused"


def test_the_two_ungated_routes_are_both_reachable() -> None:
    """`no_detection` and `all_inert` are separate claims; both need evidence."""
    causes = {evaluate(text, "corpus").cause for text in _corpus()}
    assert "no_detection" in causes
    assert "all_inert" in causes, (
        "no corpus text detects a construct yet still scores the midpoint; "
        "the all_inert route in the report is unsupported"
    )


def test_ungated_midpoint_excludes_refusals() -> None:
    result = summarise([evaluate(t, "corpus") for t in _corpus()], "corpus")
    assert result.ungated_midpoint == result.cause("no_detection") + result.cause("all_inert")
    assert result.ungated_midpoint + result.refused + result.cause("moved") == result.n


# ---------------------------------------------------------------------------
# The gates
# ---------------------------------------------------------------------------


def test_non_language_junk_is_refused() -> None:
    for name, texts in JUNK_CLASSES.items():
        if name == "off_register":
            continue
        for text in texts:
            assert not evaluate(text, name).admitted, f"{name}: {text!r} was admitted"


def test_off_register_text_is_admitted_and_flagged_not_refused() -> None:
    """Sec.12.2: the register test decorates, it never gates.

    If this flips, the page starts refusing real English about the wrong
    subject, which is a product decision nobody made.
    """
    for text in JUNK_CLASSES["off_register"]:
        outcome = evaluate(text, "off_register")
        assert outcome.admitted, f"{text!r} was refused"
        assert not outcome.on_topic, f"{text!r} was not flagged off-register"


def test_the_gates_do_not_eat_the_corpus() -> None:
    """False refusals are pure cost. A floor, so an improvement passes."""
    result = summarise([evaluate(t, "corpus") for t in _corpus()], "corpus")
    assert result.refusal_rate <= 0.05, (
        f"the gates now refuse {result.refusal_rate:.1%} of legitimate corpus text"
    )


# ---------------------------------------------------------------------------
# Honesty rules
# ---------------------------------------------------------------------------


def test_counterfactual_uses_the_evaluated_cue_list_not_the_dashboard_one() -> None:
    """A measurement may not quietly use the widened demo detector.

    `DASHBOARD_EXTRA_CUES` exists so a visitor's own phrasing lights up a bar
    (`docs/dashboard.md`). It has no measured score, so a report built on it
    would be reporting an unevaluated system.
    """
    from src.dashboard.backend import DASHBOARD_EXTRA_CUES
    from src.evaluation.baselines import CONSTRUCT_CUES

    # "nervous" is in the widened list and in no frozen one. Several obvious
    # candidates are not: "trembling" and "butterflies" appear in both, and
    # "afraid" collides with self_confidence's "afraid of". The assertions below
    # check both halves so the fixture cannot silently stop isolating them.
    only_widened = "I am nervous about tomorrow and it has been on my mind"
    assert any(cue in only_widened.lower() for cue in DASHBOARD_EXTRA_CUES["cognitive_anxiety"]), (
        "fixture no longer exercises a widened-only cue"
    )
    assert not any(
        cue in only_widened.lower() for cues in CONSTRUCT_CUES.values() for cue in cues
    ), "fixture now hits a frozen cue too, so it no longer isolates the widening"
    assert counterfactual_index(only_widened) == pytest.approx(MIDPOINT), (
        "the counterfactual detected a cue only the dashboard list carries"
    )


def test_the_evaluated_cue_list_is_pinned() -> None:
    """`CONSTRUCT_CUES` is frozen, and changing it invalidates committed figures.

    macro-F1 **0.462** in `reports/results.md`, the floor the transformer's 0.588
    is measured against, and every derived number in `docs/model_card.md` were
    all computed with this exact list. The cheapest way to break the paper is to
    widen it -- the demo's list is right there in `src/dashboard/backend.py` and
    copying a few phrases across would raise the lexicon's score with nothing in
    the suite objecting.

    So the list is pinned by content. If this fails, the change may still be
    correct, but `scripts/run_baselines.py` and `scripts/run_evaluation.py` must
    be re-run and every affected figure re-stated before the pin is updated.
    """
    import hashlib

    from src.evaluation.baselines import CONSTRUCT_CUES

    payload = "|".join(
        f"{construct}:{','.join(CONSTRUCT_CUES[construct])}" for construct in sorted(CONSTRUCT_CUES)
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    # A content digest of a public cue list, not a credential. Same class of
    # false positive as OPEN-010, and the same class of value as the
    # `training_fingerprint` digests Phase 21 re-verdicted to is_secret: false.
    expected = "7b3f6df03f196a67c5039f4121f00ff35a147bef7d791e7eaef42f01d78f0028"  # pragma: allowlist secret
    assert digest == expected, (
        "the evaluated cue list changed. Every committed lexicon figure "
        "(macro-F1 0.462 and everything measured against it) is now stale. "
        f"Re-run the baselines, re-state the figures, then set the pin to {digest}."
    )


def test_silent_but_real_text_is_admitted_and_still_scores_the_midpoint() -> None:
    """The finding in one case: good text, no gate, no score, midpoint anyway."""
    outcome = evaluate(SILENT_BUT_REAL, "corpus")
    assert outcome.admitted
    assert outcome.cause == "no_detection"
    assert outcome.index == pytest.approx(MIDPOINT)


def test_report_states_its_limitations_and_claims_no_accuracy() -> None:
    report = build_report(_corpus(), "PROVISIONAL -- test")
    markdown = render_markdown(report, generated="2026-01-01")
    assert "No number in this file is an accuracy" in markdown
    assert "OPEN-011" in markdown
    assert "synthetic" in markdown.lower()
    assert "authored" in markdown.lower()


def test_report_reports_the_ungated_routes_rather_than_only_the_refusal_rate() -> None:
    """A report that printed only refusals would flatter the gates."""
    report = build_report(_corpus(), "PROVISIONAL -- test")
    markdown = render_markdown(report, generated="2026-01-01")
    assert "no_detection" in markdown
    assert "all_inert" in markdown
    assert str(report.corpus.ungated_midpoint) in markdown
