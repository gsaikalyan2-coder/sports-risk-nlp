"""Loads, validates and freezes `config/taxonomy.yaml` as ten readable cards.

Why this surface exists
-----------------------
The taxonomy is the project's academic backbone (`.claude.md` section 3) and until
now it was the one part a reader could not see. `atlas_map.py` reads the same file
and takes only the construct *names* from it; the definitions, the instrument
anchors, the worked examples and the edge cases -- the content that makes the
labels reproducible and reviewer-defensible -- lived in a YAML file and in
`docs/annotation_guidelines.md`, neither of which is on screen.

This is also the safest surface in the application, and that is worth stating
plainly: **it carries no numbers at all**. Nothing here is detected, scored,
ranked or squashed, so there is no stamp to attach, no calibration to disclaim and
no 0.50 to invent. A card is a definition and two citations.

What this refuses, and why
--------------------------
* **A construct in the file that is not in the frozen taxonomy, or a construct in
  the taxonomy with no entry.** Both halves, for the reason `atlas_map` gives: a
  card for something the model does not predict teaches a reader a construct that
  does not exist, and a missing card silently shows nine of ten.
* **An `instrument_anchor` with no citation key that resolves in
  `paper/refs.bib`.** The anchor is the entire claim to defensibility. An anchor
  that resolves nowhere is a card that reads as cited.
* **A construct with no definition, or without both a positive and a negative
  example.** The rubric's own shape: a definition with no counter-example is not a
  labelling rule, and `docs/annotation_guidelines.md` is built on the pairing.
* **A `categorical` construct with no labels.** Its whole label model is the
  choice between them.
* **Any string carrying forbidden vocabulary.** The YAML has never been screened
  before: `copy.py` screens itself at import and `view.py` screens what it builds,
  but a definition written at Phase 4 and rendered for the first time now has
  passed through neither.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from src.dashboard.copy import CONSTRUCTS as PLAIN_CONSTRUCTS
from src.dashboard.view import assert_no_forbidden_language
from src.models.dataset import CONSTRUCTS

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"
REFS_PATH = REPO_ROOT / "paper" / "refs.bib"

#: A citation key as `refs.bib` writes them and `taxonomy.yaml` cites them: a name
#: followed by a four-digit year, optionally disambiguated. Matched rather than
#: hand-listed, because a hardcoded list is correct only on the day it is written
#: -- the argument `atlas_map._bib_keys` already makes for reading the bib file.
_ANCHOR_KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*\d{4}[a-z]?")


class TaxonomyCardError(ValueError):
    """Raised when `taxonomy.yaml` cannot be shown to a reader as it stands."""


@dataclass(frozen=True)
class TaxonomyCard:
    """One construct, in both registers: the reader's words and the paper's.

    `plain_name` and `plain_meaning` come from `copy.py`, which is written for a
    coach with no machine-learning background; `definition` and `instrument_anchor`
    come from the taxonomy, which is written for a reviewer. Both are shown,
    because a card carrying only one of them would be either unreadable or
    unciteable.
    """

    construct: str
    plain_name: str
    plain_meaning: str
    label_type: str
    definition: str
    instrument_anchor: str
    anchor_keys: tuple[str, ...]
    risk_direction: str
    labels: tuple[str, ...]
    positive_examples: tuple[str, ...]
    negative_examples: tuple[str, ...]
    edge_cases: str

    def __post_init__(self) -> None:
        if self.construct not in CONSTRUCTS:
            raise TaxonomyCardError(
                f"{self.construct!r} is not in the frozen taxonomy; a card for it would "
                "teach a reader a construct the model does not predict."
            )
        if not self.definition.strip():
            raise TaxonomyCardError(f"{self.construct!r} has no definition.")
        if not self.anchor_keys:
            raise TaxonomyCardError(
                f"{self.construct!r} cites no resolvable reference in its "
                f"instrument_anchor ({self.instrument_anchor!r}). The anchor is the "
                "entire claim to defensibility; a card without one reads as cited."
            )
        if not self.positive_examples or not self.negative_examples:
            raise TaxonomyCardError(
                f"{self.construct!r} is missing a positive or a negative example. A "
                "definition with no counter-example is not a labelling rule."
            )
        if self.label_type == "categorical" and not self.labels:
            raise TaxonomyCardError(
                f"{self.construct!r} is categorical and names no labels, which is its "
                "whole label model."
            )
        for chunk in (
            self.plain_name,
            self.plain_meaning,
            self.definition,
            self.instrument_anchor,
            self.risk_direction,
            self.edge_cases,
            *self.labels,
            *self.positive_examples,
            *self.negative_examples,
        ):
            assert_no_forbidden_language(chunk)

    @property
    def is_polar(self) -> bool:
        """Whether this is one of the four whose direction the default leaves open.

        Read off the label model and the direction wording rather than a name list,
        the same argument `view._bars_for` makes: a list would be correct today and
        wrong the first time anyone re-labelled a construct.
        """
        return self.label_type == "categorical" and ";" in self.risk_direction

    @property
    def direction_plain(self) -> str:
        """The direction in a phrase a card can print without a legend."""
        if self.is_polar:
            return "can point either way, so the default counts it as zero"
        if self.risk_direction == "raises":
            return "pushes the risk index up"
        if self.risk_direction == "lowers":
            return "pulls the risk index down"
        return self.risk_direction


@lru_cache(maxsize=1)
def _bib_keys() -> frozenset[str]:
    """Every citation key in `paper/refs.bib`. Read, never hardcoded."""
    if not REFS_PATH.exists():
        raise TaxonomyCardError(f"{REFS_PATH} is missing; card anchors cannot be checked.")
    return frozenset(re.findall(r"^@\w+\{([^,]+),", REFS_PATH.read_text(encoding="utf-8"), re.M))


def _clean(value: object) -> str:
    """YAML block scalars arrive with their wrapping newlines. Collapse them."""
    return " ".join(str(value or "").split())


@lru_cache(maxsize=2)
def load_cards(path: str | None = None) -> tuple[TaxonomyCard, ...]:
    """Load, validate and freeze the ten cards, in taxonomy file order.

    File order rather than alphabetical: `taxonomy.yaml` groups the three CSAI-2
    subscales together and then walks outward, which is the order the annotation
    guidelines teach them in. Sorting would break a deliberate sequence for no
    gain.
    """
    source = Path(path) if path else TAXONOMY_PATH
    if not source.exists():
        raise TaxonomyCardError(f"{source} is missing; the taxonomy cards cannot render.")
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    keys = _bib_keys()

    cards: list[TaxonomyCard] = []
    for construct, entry in (data.get("constructs") or {}).items():
        anchor = _clean(entry.get("instrument_anchor"))
        plain = PLAIN_CONSTRUCTS.get(construct)
        cards.append(
            TaxonomyCard(
                construct=construct,
                plain_name=plain[0] if plain else construct.replace("_", " "),
                plain_meaning=plain[1] if plain else "",
                label_type=_clean(entry.get("label_type")),
                definition=_clean(entry.get("definition")),
                instrument_anchor=anchor,
                anchor_keys=tuple(key for key in _ANCHOR_KEY_RE.findall(anchor) if key in keys),
                risk_direction=_clean(entry.get("risk_direction")),
                labels=tuple(str(label) for label in entry.get("labels") or ()),
                positive_examples=tuple(
                    _clean(example) for example in entry.get("positive_examples") or ()
                ),
                negative_examples=tuple(
                    _clean(example) for example in entry.get("negative_examples") or ()
                ),
                edge_cases=_clean(entry.get("edge_cases")),
            )
        )

    named = {card.construct for card in cards}
    if missing := set(CONSTRUCTS) - named:
        raise TaxonomyCardError(
            f"taxonomy.yaml has no entry for {sorted(missing)}. Every construct gets a "
            "card, or the deck shows nine of ten and nobody counts cards."
        )
    return tuple(cards)
