"""Honesty tests for the taxonomy deck (Phase 34).

`tests/test_taxonomy.py` already validates `config/taxonomy.yaml` as configuration.
This file validates it as a **surface**, which is a different job and turns on two
properties the config tests have no reason to check:

    (a) the deck carries no reading. No probability, no index, no count, no stamp.
        It is the one page in the application with nothing to misread, and that is a
        property worth defending rather than a coincidence.
    (b) the YAML's own prose reaches a reader for the first time here. `copy.py`
        screens itself at import and `view.py` screens what it builds; a definition
        written at Phase 4 has passed through neither, so the loader screens every
        field and the renderer screens the assembled surface.

Plus the refusals: a card that could not cite itself, or that came from outside the
frozen taxonomy, must not render at all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from src.dashboard import theme
from src.dashboard.deck import card_deck, taxonomy_card
from src.dashboard.taxonomy_cards import (
    TAXONOMY_PATH,
    TaxonomyCard,
    TaxonomyCardError,
    load_cards,
)
from src.dashboard.view import ForbiddenLanguage, assert_no_forbidden_language
from src.evaluation.harness import PROVISIONAL_STAMP
from src.models.dataset import CONSTRUCTS

REPO_ROOT = Path(__file__).resolve().parents[1]
DECK_PAGE = REPO_ROOT / "dashboard" / "pages" / "9_Taxonomy_cards.py"

#: A reading, as this project writes one: two decimals between 0 and 1. Citation
#: years (Martens1990) and instrument names (CSAI-2) contain digits and are fine --
#: what may not appear is a *score*.
_READING_RE = re.compile(r"\b[01]\.\d\d\b")


@pytest.fixture(scope="module")
def cards() -> tuple[TaxonomyCard, ...]:
    return load_cards()


def _valid_entry(**overrides) -> dict:
    entry = {
        "label_type": "graded",
        "definition": "Worry about the upcoming competition.",
        "instrument_anchor": "CSAI-2 cognitive-anxiety subscale [Martens1990; Cox2003]",
        "risk_direction": "raises",
        "positive_examples": ["I keep thinking it will go wrong."],
        "negative_examples": ["I have prepared and I know the plan."],
        "edge_cases": "General life worry unrelated to competition does not count.",
    }
    entry.update(overrides)
    return entry


def _write(tmp_path, entry: dict, construct: str = "cognitive_anxiety") -> str:
    path = tmp_path / "taxonomy.yaml"
    path.write_text(yaml.safe_dump({"constructs": {construct: entry}}), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# (a) the deck carries no reading
# ---------------------------------------------------------------------------


def test_the_deck_contains_no_score_shaped_number(cards):
    """The property that makes this the safest page in the application."""
    found = _READING_RE.search(card_deck(cards))
    assert found is None, f"the deck renders a score-shaped value: {found.group()!r}"


def test_the_deck_carries_no_provenance_stamp(cards):
    """Nothing here was measured, so borrowing a measurement's stamp would be a lie."""
    html = card_deck(cards)
    assert PROVISIONAL_STAMP.split(" -- ")[0] not in html
    assert "PROVISIONAL" not in html


def test_the_deck_page_has_no_collapsible_provenance_section():
    """A rule, so a later edit does not add one and then invent a stamp to satisfy it."""
    assert "st.expander(" not in DECK_PAGE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# (b) every card is cited, and the set is complete
# ---------------------------------------------------------------------------


def test_there_is_one_card_per_construct_in_taxonomy_order(cards):
    assert len(cards) == len(CONSTRUCTS) == 10
    assert {card.construct for card in cards} == set(CONSTRUCTS)
    # File order, not alphabetical: the three CSAI-2 subscales lead, as the
    # annotation guidelines teach them.
    raw = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))
    assert [card.construct for card in cards] == list(raw["constructs"])


def test_every_card_cites_a_reference_that_resolves_in_the_bibliography(cards):
    from src.dashboard.taxonomy_cards import _bib_keys

    keys = _bib_keys()
    for card in cards:
        assert card.anchor_keys, card.construct
        for key in card.anchor_keys:
            assert key in keys


def test_every_card_carries_both_registers(cards):
    for card in cards:
        assert card.plain_name and card.plain_name != card.construct
        assert card.definition
        assert card.positive_examples and card.negative_examples


def test_exactly_four_cards_are_directionally_unresolved(cards):
    """The same four the decomposition counts as zero, derived rather than listed."""
    polar = [card for card in cards if card.is_polar]
    assert len(polar) == 4
    assert {card.construct for card in polar} == {
        "appraisal_orientation",
        "attentional_focus",
        "coping_style",
        "motivation_orientation",
    }


def test_a_polar_card_is_marked_three_times_over(cards):
    """Dashed border, muted chip and the literal words -- as `charts.py` marks inert."""
    polar = next(card for card in cards if card.is_polar)
    html = taxonomy_card(polar)
    assert 'class="tcard is-polar"' in html
    assert "counted as zero" in html
    assert "point either way" in html
    # The third channel is the border, which lives in the shell's stylesheet.
    for mode in ("light", "dark"):
        assert ".tcard.is-polar{border-style:dashed}" in theme.app_css(mode)


def test_a_graded_card_is_not_marked_as_unresolved(cards):
    graded = next(card for card in cards if not card.is_polar)
    html = taxonomy_card(graded)
    assert "is-polar" not in html
    assert "counted as zero" not in html


def test_every_card_says_which_way_it_pushes(cards):
    for card in cards:
        assert card.direction_plain
        assert card.direction_plain in taxonomy_card(card)


# ---------------------------------------------------------------------------
# the refusals
# ---------------------------------------------------------------------------


def test_a_construct_outside_the_frozen_taxonomy_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="frozen taxonomy"):
        load_cards(_write(tmp_path, _valid_entry(), construct="vibes"))


def test_a_missing_construct_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="no entry for"):
        load_cards(_write(tmp_path, _valid_entry()))


def test_a_card_with_no_definition_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="no definition"):
        load_cards(_write(tmp_path, _valid_entry(definition="")))


def test_a_card_whose_anchor_resolves_nowhere_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="no resolvable reference"):
        load_cards(_write(tmp_path, _valid_entry(instrument_anchor="some instrument [Nobody2099]")))


def test_a_card_with_no_counter_example_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="counter-example"):
        load_cards(_write(tmp_path, _valid_entry(negative_examples=[])))


def test_a_categorical_card_with_no_labels_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="whole label model"):
        load_cards(_write(tmp_path, _valid_entry(label_type="categorical")))


def test_a_card_carrying_forbidden_language_is_refused(tmp_path):
    with pytest.raises(ForbiddenLanguage):
        load_cards(
            _write(
                tmp_path,
                _valid_entry(definition="Worry, validated against coach-validated thresholds."),
            )
        )


def test_a_missing_taxonomy_file_is_refused(tmp_path):
    with pytest.raises(TaxonomyCardError, match="missing"):
        load_cards(str(tmp_path / "nope.yaml"))


# ---------------------------------------------------------------------------
# the rendered surface
# ---------------------------------------------------------------------------


def test_the_deck_uses_no_forbidden_language(cards):
    assert_no_forbidden_language(card_deck(cards))


def test_the_deck_escapes_the_text_it_renders():
    """Definitions are prose from a config file, not markup. An ampersand is data."""
    card = TaxonomyCard(
        construct="cognitive_anxiety",
        plain_name="Worry in the head",
        plain_meaning="",
        label_type="graded",
        definition="<script>alert(1)</script> & a note",
        instrument_anchor="CSAI-2 [Martens1990]",
        anchor_keys=("Martens1990",),
        risk_direction="raises",
        labels=(),
        positive_examples=("I keep thinking it will go wrong.",),
        negative_examples=("I know the plan.",),
        edge_cases="",
    )
    html = taxonomy_card(card)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&amp;" in html


def test_the_deck_renders_one_article_per_card(cards):
    html = card_deck(cards)
    assert html.count("<article") == len(cards)
    assert html.startswith('<div class="deck">')


def test_the_deck_is_deterministic(cards):
    assert card_deck(cards) == card_deck(cards)
