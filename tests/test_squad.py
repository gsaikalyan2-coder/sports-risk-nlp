"""Phase 36 -- the squad view's honesty rules, asserted rather than trusted.

The rules worth a test here are the ones that would fail silently. A squad that
renders is not evidence of anything: the failure this module exists to prevent is
a page that renders *perfectly* while a member the detector could not read sits
mid-table at exactly 0.50, looking like an average athlete.

Members are constructed directly in several tests rather than generated. The live
lexicon happens not to produce a silent member for the seeds tried, and a test
that only runs when the word list cooperates is a test that stops running the day
the word list changes.
"""

from __future__ import annotations

import pytest

from src.dashboard.charts import squad_strip
from src.dashboard.squad import (
    MAX_SQUAD,
    MIN_SQUAD,
    Squad,
    SquadMember,
    SquadRefused,
    build_squad,
)
from src.dashboard.view import ScoreSurface
from src.ingestion.scenarios import SPORTS


def _surface(value: float) -> ScoreSurface:
    return ScoreSurface(label="Risk index", value=value, display=f"{value:.2f}")


def _member(slot: int, value: float | None, *, moved: bool = True) -> SquadMember:
    return SquadMember(
        slot=slot,
        sport="athletics",
        life_context="none",
        plain_context="No particular context",
        seed=slot,
        text="I am ready for the race on Saturday.",
        detected=value is not None,
        moved=moved if value is not None else False,
        surface=_surface(value) if value is not None else None,
        constructs=("cognitive_anxiety",) if value is not None else (),
    )


def _squad(members: list[SquadMember], median: ScoreSurface | None) -> Squad:
    return Squad(
        sport="athletics",
        members=tuple(members),
        median=median,
        scale_label="0 to 1, ranking only",
        caveat="Synthetic corpus.",
        source="lexicon baseline",
        stamp=_surface(0.5).stamp,
    )


# ---------------------------------------------------------------------------
# (a) the section 12.3 rule: no detection, no number
# ---------------------------------------------------------------------------


def test_a_member_with_no_detection_cannot_hold_a_number():
    """The whole module exists for this. 0.50 mid-table reads as an average athlete."""
    with pytest.raises(ValueError, match="0.50"):
        SquadMember(
            slot=0,
            sport="athletics",
            life_context="none",
            plain_context="No particular context",
            seed=0,
            text="nothing here",
            detected=False,
            moved=False,
            surface=_surface(0.5),
            constructs=(),
        )


def test_a_detected_member_must_carry_its_number():
    with pytest.raises(ValueError, match="disagrees with"):
        SquadMember(
            slot=0,
            sport="athletics",
            life_context="none",
            plain_context="No particular context",
            seed=0,
            text="I am worried",
            detected=True,
            moved=True,
            surface=None,
            constructs=("cognitive_anxiety",),
        )


def test_a_member_cannot_move_the_index_without_being_detected():
    with pytest.raises(ValueError, match="without being detected"):
        SquadMember(
            slot=0,
            sport="athletics",
            life_context="none",
            plain_context="No particular context",
            seed=0,
            text="text",
            detected=False,
            moved=True,
            surface=None,
            constructs=(),
        )


def test_a_squad_with_no_readable_member_has_no_median():
    """One level up, and the same rule: no readings, no summary number."""
    with pytest.raises(ValueError, match="no readable member"):
        _squad([_member(0, None), _member(1, None), _member(2, None)], _surface(0.5))


def test_a_squad_with_readable_members_must_report_a_median():
    with pytest.raises(ValueError, match="must report one"):
        _squad([_member(0, 0.8), _member(1, 0.4), _member(2, 0.6)], None)


# ---------------------------------------------------------------------------
# (b) the median is selected, never computed
# ---------------------------------------------------------------------------


def test_the_median_is_one_members_own_reading_and_never_an_average():
    """An even count is the case that would tempt an average. It must not take one."""
    squad = build_squad(sport="athletics", size=4, seed=3)
    assert squad.median is not None
    readings = {m.surface.value for m in squad.scored}
    assert squad.median.value in readings, (
        "the median is an order statistic here: it selects one member's reading. A value "
        "absent from the readings means something averaged two of them, which would be "
        "the first number on a page that build_view did not produce."
    )


def test_the_median_takes_the_lower_of_two_middles():
    members = [_member(0, 0.20), _member(1, 0.40), _member(2, 0.60), _member(3, 0.80)]
    assert _squad(members, _surface(0.40)).median.value == 0.40
    # Pinned to the builder's own behaviour too, not only to the fixture above.
    live = build_squad(sport="athletics", size=4, seed=3)
    ranked = sorted(m.surface.value for m in live.scored)
    assert live.median.value == ranked[(len(ranked) - 1) // 2]


# ---------------------------------------------------------------------------
# (c) unreadable members are outside the order, not at the bottom of it
# ---------------------------------------------------------------------------


def test_unreadable_members_are_excluded_from_the_ranking():
    members = [_member(0, 0.9), _member(1, None), _member(2, 0.3)]
    squad = _squad(members, _surface(0.3))
    assert [m.slot for m in squad.ordered] == [0, 2]
    assert [m.slot for m in squad.silent] == [1]
    assert squad.n_silent == 1


def test_the_ranking_is_highest_first_and_stable_on_ties():
    members = [_member(0, 0.5), _member(1, 0.9), _member(2, 0.5)]
    squad = _squad(members, _surface(0.5))
    assert [m.slot for m in squad.ordered] == [1, 0, 2]


def test_spread_is_zero_below_two_readable_members():
    squad = _squad([_member(0, 0.7), _member(1, None), _member(2, None)], _surface(0.7))
    assert squad.spread == 0.0


# ---------------------------------------------------------------------------
# (d) the three states, and the figure that draws them
# ---------------------------------------------------------------------------


def test_the_three_states_are_distinct_words():
    assert _member(0, None).state == "nothing detected"
    assert _member(1, 0.5, moved=False).state == "counted as zero"
    assert _member(2, 0.8, moved=True).state == "moves the index"


def test_the_figure_marks_both_zero_states_in_words_not_only_in_colour():
    """Three channels, as charts.py requires everywhere: hatch, tone and the word."""
    members = [_member(0, 0.9), _member(1, 0.5, moved=False), _member(2, None)]
    svg = squad_strip(_squad(members, _surface(0.5)))
    assert "counted as zero" in svg
    assert "nothing detected" in svg


def test_the_figure_never_claims_a_squad_average():
    svg = squad_strip(_squad([_member(0, 0.9), _member(1, 0.4), _member(2, 0.6)], _surface(0.6)))
    assert "not calibrated" in svg
    assert "nothing here is an average of the squad" in svg


def test_the_figure_carries_no_band_label():
    """Band vocabulary on a figure is the thing tests/test_dashboard_pages.py bans."""
    svg = squad_strip(_squad([_member(0, 0.9), _member(1, 0.4), _member(2, 0.6)], _surface(0.6)))
    low = svg.lower()
    for word in ("elevated", "moderate", "severe", "high risk", "low risk"):
        assert word not in low, f"{word!r} is a band label and may not appear on a figure"


# ---------------------------------------------------------------------------
# (e) the builder: refusals, determinism, and no invented numbers
# ---------------------------------------------------------------------------


def test_a_squad_below_the_minimum_is_refused_with_a_reason():
    with pytest.raises(SquadRefused, match="not a squad"):
        build_squad(sport="athletics", size=MIN_SQUAD - 1, seed=1)


def test_a_squad_above_the_maximum_is_refused_rather_than_truncated():
    with pytest.raises(SquadRefused, match="readable at figure width"):
        build_squad(sport="athletics", size=MAX_SQUAD + 1, seed=1)


def test_an_unknown_sport_is_refused():
    with pytest.raises(SquadRefused, match="not one of the sports"):
        build_squad(sport="quidditch", size=5, seed=1)


def test_the_same_seed_rebuilds_the_same_squad():
    a = build_squad(sport="swimming", size=6, seed=42)
    b = build_squad(sport="swimming", size=6, seed=42)
    assert [m.text for m in a.members] == [m.text for m in b.members]
    assert [m.value for m in a.members] == [m.value for m in b.members]


def test_every_number_on_a_squad_is_one_build_view_produced():
    """No arithmetic is introduced here: every displayed value is a member's own."""
    squad = build_squad(sport="tennis", size=7, seed=5)
    readings = {m.surface.value for m in squad.scored}
    assert squad.median.value in readings
    assert all(m.surface.stamp for m in squad.scored)


def test_prevalence_counts_members_and_scores_nothing():
    squad = build_squad(sport="football", size=8, seed=9)
    for _construct, _plain, count in squad.prevalence:
        assert isinstance(count, int)
        assert 1 <= count <= len(squad.members)


def test_every_sport_the_page_offers_actually_builds():
    """The page's dropdown is SPORTS; a sport that raises would be a dead option."""
    for sport in SPORTS:
        squad = build_squad(sport=sport, size=MIN_SQUAD, seed=2)
        assert len(squad.members) == MIN_SQUAD
