"""Honesty tests for the sentence ribbon (Phase 30 V7).

The ribbon is the riskiest of the three Phase 30 surfaces, for one reason: it puts
a column per sentence on a 0-to-1 axis, and `LexiconBackend` will happily return an
all-zero decomposition that squashes to exactly 0.50. Drawn naively, a passage of
sentences the detector had nothing to say about becomes a flat mid-height fence
that reads as "uniformly middling" -- the `.claude.md` section 12.3 defect, at
figure scale.

So the properties asserted here are, in order of how much they matter:

    (a) a sentence with nothing detected carries NO number     -> structural, at
                                                                  construction
    (b) the three states are each marked in words              -> not by colour,
                                                                  not by height
    (c) offsets hold: band N is exactly those characters       -> the invariant
                                                                  segment.py exists
                                                                  for
    (d) refusals refuse, and say why in the reader's words     -> no partial render
    (e) the figure invents no number the ribbon does not carry
"""

from __future__ import annotations

import pytest

from src.dashboard.bands import BANDS
from src.dashboard.charts import sentence_ribbon
from src.dashboard.copy import RIBBON_SAMPLE
from src.dashboard.ribbon import (
    MAX_SENTENCES,
    MIN_SENTENCES,
    Ribbon,
    RibbonRefused,
    SentenceBand,
    build_ribbon,
)
from src.dashboard.view import ScoreSurface, assert_no_forbidden_language

#: Two sentences with cues and one with none, so every marking is exercised by the
#: smallest possible input.
MIXED = (
    "My hands will not stop shaking before the heat. "
    "Prep has been at the usual times this block. "
    "I know I can win this if I stick to my game."
)


@pytest.fixture(scope="module")
def ribbon() -> Ribbon:
    return build_ribbon(RIBBON_SAMPLE)


@pytest.fixture(scope="module")
def mixed() -> Ribbon:
    return build_ribbon(MIXED)


# ---------------------------------------------------------------------------
# (a) no detection, no number
# ---------------------------------------------------------------------------


def test_a_band_that_detected_nothing_cannot_carry_a_number():
    """The section 12.3 rule, enforced where it cannot be forgotten.

    An all-zero decomposition squashes to exactly 0.50. A band allowed to hold that
    value would draw at half height and read as a middling sentence, so the
    disagreement is refused at construction rather than checked at render time.
    """
    surface = ScoreSurface(label="Risk index", value=0.5, display="0.50")
    with pytest.raises(ValueError, match="0.50"):
        SentenceBand(
            index=0,
            text="Prep has been at the usual times.",
            start=0,
            end=33,
            detected=False,
            moved=False,
            surface=surface,
            constructs=(),
        )
    with pytest.raises(ValueError, match="0.50"):
        SentenceBand(
            index=0,
            text="Prep has been at the usual times.",
            start=0,
            end=33,
            detected=True,
            moved=False,
            surface=None,
            constructs=("resilience",),
        )


def test_a_band_cannot_move_the_index_without_being_detected():
    with pytest.raises(ValueError, match="without being detected"):
        SentenceBand(
            index=0,
            text="Prep has been at the usual times.",
            start=0,
            end=33,
            detected=False,
            moved=True,
            surface=None,
            constructs=(),
        )


def test_silent_sentences_are_absent_rather_than_drawn_at_the_midpoint(mixed):
    silent = [band for band in mixed.bands if not band.detected]
    assert silent, "the fixture no longer contains a sentence with nothing detected"
    for band in silent:
        assert band.value is None
        assert band.surface is None
    # And the count is reported rather than left for a reader to notice.
    assert mixed.n_silent == len(silent)


def test_no_band_value_is_a_fabricated_midpoint(ribbon):
    """Every value present came from a real decomposition, so any 0.50 is earned.

    A band at exactly 0.50 is legitimate -- it means the detected constructs were
    all directionally unresolved -- but it must then be marked as such, never left
    to look like a middling reading.
    """
    for band in ribbon.bands:
        if band.value == pytest.approx(0.5):
            assert not band.moved
            assert band.state == "counted as zero"


# ---------------------------------------------------------------------------
# (b) three states, each named in words
# ---------------------------------------------------------------------------


def test_every_state_is_a_word_and_not_only_a_height(mixed):
    states = {band.state for band in mixed.bands}
    assert states <= {"nothing detected", "counted as zero", "moves the index"}
    assert "nothing detected" in states


def test_the_figure_prints_the_state_of_every_band(mixed):
    figure = sentence_ribbon(mixed)
    for band in mixed.bands:
        assert band.state in figure


def test_the_figure_carries_no_band_label(mixed):
    """The ribbon is on the same unbanded footing as `charts.risk_meter`."""
    figure = sentence_ribbon(mixed)
    for band in BANDS:
        assert band.label not in figure
    for word in ("low risk", "high risk", "moderate risk", "severe", "critical"):
        assert word not in figure.lower()


def test_the_figure_says_the_whole_is_not_the_average(mixed):
    figure = sentence_ribbon(mixed)
    assert "not the average" in figure
    assert "whole passage" in figure
    assert "nothing was detected" in figure


def test_the_figure_uses_no_forbidden_language(ribbon):
    assert_no_forbidden_language(sentence_ribbon(ribbon))


# ---------------------------------------------------------------------------
# (c) the offsets hold
# ---------------------------------------------------------------------------


def test_every_band_slices_its_own_words_out_of_the_passage(ribbon):
    for band in ribbon.bands:
        assert ribbon.text[band.start : band.end] == band.text


def test_a_band_whose_offsets_do_not_slice_its_text_is_refused():
    """The one failure a span-level explanation cannot survive, made unbuildable."""
    surface = ScoreSurface(label="Risk index", value=0.8, display="0.80")
    good = SentenceBand(
        index=0,
        text="My hands are shaking.",
        start=0,
        end=21,
        detected=True,
        moved=True,
        surface=surface,
        constructs=("somatic_anxiety",),
    )
    wrong = SentenceBand(
        index=1,
        text="I know the plan.",
        start=40,  # nowhere near the real position
        end=56,
        detected=True,
        moved=True,
        surface=surface,
        constructs=("self_confidence",),
    )
    with pytest.raises(ValueError, match="do not slice"):
        Ribbon(
            text="My hands are shaking. I know the plan.",
            bands=(good, wrong),
            whole=surface,
            scale_label="",
            caveat="",
            source="test",
        )


# ---------------------------------------------------------------------------
# (d) refusals
# ---------------------------------------------------------------------------


def test_text_that_is_not_language_is_refused_with_a_readable_reason():
    with pytest.raises(RibbonRefused) as refusal:
        build_ribbon("asdkj kjsdhf lkjhsdf qwoieu zxcvmn")
    assert str(refusal.value).strip()
    # The reason a reader sees names the property that failed, not "invalid input".
    assert "invalid input" not in str(refusal.value).lower()


def test_one_sentence_is_refused_because_a_ribbon_is_a_comparison():
    with pytest.raises(RibbonRefused, match=str(MIN_SENTENCES)):
        build_ribbon("My hands will not stop shaking before the heat.")


#: Thirty distinct sentences. Deliberately not a repeated template: `gibberish.admit`
#: catches near-duplicate text first and by design -- its reasons run cheapest and
#: most concrete first -- so a wall built by repetition tests the repetition rule
#: rather than the length rule.
LONG_PASSAGE = " ".join(
    (
        "The taper has gone roughly to plan so far.",
        "My legs felt heavy in the pool this morning.",
        "I slept badly and woke before the alarm again.",
        "Breakfast sat wrong and I left most of it.",
        "The coach wants a controlled first fifty.",
        "I keep replaying the semifinal from last season.",
        "There is a swimmer in lane four I have never beaten.",
        "My shoulder has been grumbling since Tuesday.",
        "Physio says it is nothing structural.",
        "The pool feels colder than the warm-up one.",
        "I have not looked at the start lists yet.",
        "My parents flew in yesterday evening.",
        "Having them here helps more than I expected.",
        "The heats are early and the final is late.",
        "I do not know what to do with the gap between.",
        "Last time I filled it badly and paid for it.",
        "My kit bag is packed the way it always is.",
        "Superstition, maybe, but it costs nothing.",
        "The turnaround from trials was short.",
        "I trust the work even when the times wobble.",
        "Some mornings I wonder why I still do this.",
        "Most mornings I do not wonder at all.",
        "The team meeting is at seven tonight.",
        "I will keep my phone off until after the final.",
        "Tomorrow is only one race among many.",
        "That is easier to write down than to believe.",
        "I have come back from a worse block than this.",
        "The plan is the plan and I know it cold.",
        "Two hundred metres is a long way to overthink.",
        "Whatever happens I will have raced it properly.",
    )
)


def test_too_many_sentences_are_refused_rather_than_silently_trimmed():
    with pytest.raises(RibbonRefused, match=str(MAX_SENTENCES)):
        build_ribbon(LONG_PASSAGE)


def test_an_empty_passage_is_refused():
    with pytest.raises(RibbonRefused):
        build_ribbon("   ")


# ---------------------------------------------------------------------------
# (e) the figure adds nothing
# ---------------------------------------------------------------------------


def test_the_figure_shows_only_values_the_ribbon_carries(mixed):
    figure = sentence_ribbon(mixed)
    for band in mixed.bands:
        if band.value is None:
            continue
        assert f"{band.value:.2f}" in figure
    assert mixed.whole.display in figure


def test_the_ribbon_is_deterministic():
    """Two builds of one passage are byte-identical, so a figure can be diffed."""
    first, second = build_ribbon(MIXED), build_ribbon(MIXED)
    assert [band.value for band in first.bands] == [band.value for band in second.bands]
    assert sentence_ribbon(first) == sentence_ribbon(second)


def test_the_whole_passage_number_is_not_the_average_of_the_bands(ribbon):
    """Asserted, not just captioned: the claim on the figure has to be true."""
    values = [band.value for band in ribbon.scored]
    assert values
    assert ribbon.whole.value != pytest.approx(sum(values) / len(values))


def test_the_spread_reports_a_real_range(ribbon):
    values = [band.value for band in ribbon.scored]
    assert ribbon.spread == pytest.approx(max(values) - min(values))


def test_the_ribbon_stamp_is_the_risk_surface_stamp(ribbon):
    assert ribbon.stamp == ribbon.whole.stamp
    assert "PROVISIONAL" in ribbon.stamp
