"""Honesty tests for the paired diff (page 7).

The page-shell rules in `tests/test_dashboard_pages.py` already walk this page
with the others -- imports, the stamp above the fold, forbidden vocabulary. What
is left is the chart, and its failure modes are specific:

  (a) it must not invent a number      -> every delta equals the arithmetic
                                          difference the two views already carry
  (b) it must not pair by position     -> two decompositions in different orders
                                          would silently subtract one construct
                                          from another
  (c) it must not read as an effect    -> the "not a measured effect" sentence is
                                          drawn inside the figure, so it travels
                                          with a screenshot
  (d) it must survive grayscale        -> same three-channel rule as the other
                                          charts: hatch, dash, and the word
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import pytest

from src.dashboard import plain
from src.dashboard.backend import LexiconBackend, ReplayBackend
from src.dashboard.charts import (
    DELTA_CAPTION,
    INERT_HATCH_ID,
    construct_contribution_chart,
    construct_delta_chart,
)
from src.dashboard.view import assert_no_forbidden_language, build_view

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"
PAGE_PATH = REPO_ROOT / "dashboard" / "pages" / "7_Compare_two_texts.py"

CALM = "I have slept well, the plan is clear and I know exactly what I am doing first."
RATTLED = "My hands will not stop shaking and I keep replaying the start in my head."


@pytest.fixture(scope="module")
def pair():
    backend = LexiconBackend()
    return (
        build_view(text=CALM, backend=backend),
        build_view(text=RATTLED, backend=backend),
    )


@pytest.fixture(scope="module")
def replay_pair():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return tuple(build_view(example_id=eid, backend=backend) for eid in backend.example_ids[:2])


# ---------------------------------------------------------------------------
# (a) the chart introduces no number
# ---------------------------------------------------------------------------


def test_every_delta_is_the_difference_the_two_views_already_carry(pair):
    a, b = pair
    svg = construct_delta_chart(a.bars, b.bars)
    first = {bar.construct: bar.probability for bar in a.bars}
    for bar in b.bars:
        delta = bar.probability - first[bar.construct]
        assert f"{delta:+.2f}" in svg, f"{bar.construct}: {delta:+.2f} absent from the figure"


def test_all_ten_constructs_get_a_row(pair):
    a, b = pair
    svg = construct_delta_chart(a.bars, b.bars)
    assert len(a.bars) == len(b.bars) == 10
    for bar in a.bars:
        assert bar.construct.replace("_", " ") in svg


def test_two_identical_texts_produce_an_all_zero_diff(pair):
    a, _ = pair
    svg = construct_delta_chart(a.bars, a.bars)
    assert svg.count("+0.00") == len(a.bars)


# ---------------------------------------------------------------------------
# (b) pairing is by name, and a mismatch refuses
# ---------------------------------------------------------------------------


def test_rows_are_paired_by_name_and_not_by_position(pair):
    """Reversing one side must not change a single delta."""
    a, b = pair
    straight = construct_delta_chart(a.bars, b.bars)
    reversed_right = construct_delta_chart(a.bars, tuple(reversed(b.bars)))
    first = {bar.construct: bar.probability for bar in a.bars}
    for bar in b.bars:
        delta = f"{bar.probability - first[bar.construct]:+.2f}"
        assert delta in straight and delta in reversed_right


def test_a_diff_over_two_different_taxonomies_refuses(pair):
    a, b = pair
    renamed = tuple(replace(bar, construct="not_a_construct") for bar in b.bars[:1]) + b.bars[1:]
    with pytest.raises(ValueError, match="different constructs"):
        construct_delta_chart(a.bars, renamed)


# ---------------------------------------------------------------------------
# (c) the figure carries its own qualification
# ---------------------------------------------------------------------------


def test_the_not_an_effect_sentence_is_inside_the_figure(pair):
    a, b = pair
    assert DELTA_CAPTION in construct_delta_chart(a.bars, b.bars)
    assert "not a measured effect" in DELTA_CAPTION


def test_the_page_states_the_caveat_outside_any_expander():
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert source.index("plain.COMPARE_CAVEAT") < source.index("st.expander")


def test_the_page_renders_no_band():
    """Two band labels side by side is a verdict comparison between two people."""
    assert ".band" not in PAGE_PATH.read_text(encoding="utf-8")


def test_the_page_admits_both_texts_before_it_scores_either():
    """One admitted text scored beside one refused text leaves a lone number."""
    source = PAGE_PATH.read_text(encoding="utf-8")
    assert source.index("admit(") < source.index("build_view(")


def test_a_text_that_matches_nothing_is_named_as_a_blank_not_a_reading():
    """The 0.50 problem through a door the gates do not cover.

    `gibberish.admit` asks "is this language?". Ordinary English the lexicon has
    no entries for passes that and still yields ten zeros, a weighted sum of 0.0
    and an index of exactly 0.50. On this page that midpoint would become the
    baseline the other text is measured against, so the page has to say so.
    """
    blank = "I have slept well, the plan is clear and I know exactly what I am doing first."
    from src.dashboard.bands import score_from_view
    from src.dashboard.gibberish import admit

    view = build_view(text=blank, backend=LexiconBackend())
    assert admit(blank), "the premise is that this text is admitted, not refused"
    assert all(bar.probability == 0.0 for bar in view.bars)
    assert score_from_view(view).score_100 == 50
    assert view.detected_nothing

    source = PAGE_PATH.read_text(encoding="utf-8")
    assert "detected_nothing" in source, "the page does not check for a blank reading"
    assert source.index("COMPARE_NOTHING_DETECTED") < source.index("st.expander")


def test_a_text_that_matches_something_is_not_called_blank(pair):
    _, rattled = pair
    assert not rattled.detected_nothing


def test_no_forbidden_language_reaches_the_figure(pair):
    a, b = pair
    assert_no_forbidden_language(construct_delta_chart(a.bars, b.bars))
    assert_no_forbidden_language(plain.COMPARE_CAVEAT + plain.COMPARE_HOW_TO_READ)


# ---------------------------------------------------------------------------
# (d) grayscale, and no shared pattern id
# ---------------------------------------------------------------------------


def test_a_construct_inert_in_both_texts_is_marked_three_ways(replay_pair):
    a, b = replay_pair
    inert = {bar.construct for bar in a.bars if bar.inert} & {
        bar.construct for bar in b.bars if bar.inert
    }
    assert inert, "the fixture is expected to carry inert constructs under the default policy"
    svg = construct_delta_chart(a.bars, b.bars)
    hatch = re.search(rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"', svg)
    assert hatch, "no hatch pattern; the marking would be colour-only"
    assert f"url(#{hatch.group(1)})" in svg
    assert "stroke-dasharray" in svg
    for construct in inert:
        assert f"{construct.replace('_', ' ')} (inert)" in svg
    assert svg.count("inert") >= 2 * len(inert)


def test_the_delta_chart_does_not_share_a_pattern_id_with_the_others(replay_pair):
    """SVG ids share one namespace and Streamlit keeps every tab's DOM mounted."""
    a, b = replay_pair
    ids = [
        re.search(rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"', svg).group(1)
        for svg in (
            construct_delta_chart(a.bars, b.bars),
            construct_contribution_chart(a.bars),
            construct_contribution_chart(b.bars),
        )
    ]
    assert len(set(ids)) == 3, f"pattern ids collide on one page: {ids}"
    # Deterministic: same data, same id, or every screenshot churns.
    repeat = re.search(
        rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"', construct_delta_chart(a.bars, b.bars)
    ).group(1)
    assert repeat == ids[0]


def test_the_inert_note_cannot_collide_with_the_row_label(replay_pair):
    """The note was first drawn inside the label column, under the construct name.

    Pinned as geometry rather than as "the string is present", because the string
    was present the whole time it was unreadable.
    """
    a, b = replay_pair
    svg = construct_delta_chart(a.bars, b.bars)
    notes = re.findall(r'<text x="([\d.]+)"[^>]*text-anchor="end">inert in both', svg)
    assert notes, "no inert note rendered"
    labels = re.findall(r'<text x="8" y="[\d.]+"[^>]*>([^<]*\(inert\))</text>', svg)
    assert labels, "no inert row label rendered"
    # The note is right-anchored in the reserved gutter, well clear of the 200px
    # label column every row label starts in.
    assert all(float(x) > 400 for x in notes)
