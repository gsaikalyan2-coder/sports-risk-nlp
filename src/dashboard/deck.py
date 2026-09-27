"""The taxonomy deck: ten cards, rendered into the host page rather than an iframe.

Why not an iframe, when every other rich surface here is one
------------------------------------------------------------
`motion.py` and `neurovis.py` mount their own documents because they animate, and
Streamlit offers no hook for a motion system. This deck does not animate. An
iframe would buy nothing and cost the two things that matter for a wall of text:
an iframe has a fixed pixel height, so a card whose definition wraps to one more
line is silently clipped, and it inherits nothing, so the deck would need its own
copy of the type scale. The cards are therefore a host-page fragment, and their
stylesheet lives in `theme.app_css` with the rest of the shell -- one source, as
that module's docstring requires.

Two rules this renderer follows
-------------------------------
* **No number, anywhere.** Not a probability, not a count, not an intensity. The
  taxonomy carries none and this surface invents none, which is why it is the one
  page in the application with no provenance stamp to render: there is no reading
  here to misread.
* **The four polar constructs are marked three times over**, exactly as
  `charts.py` marks an inert bar: a dashed card border, a muted chip, and the
  literal words "counted as zero". A reader who takes all ten cards as equally
  load-bearing has been misled by the deck, because under the conservative default
  only six of them can move the index.

Emitted with no leading indentation on any line, deliberately: `st.markdown`
treats a four-space-indented line as a code fence and would render the deck as
visible source text. Found once already in `theme.app_css` -- same failure, same
fix.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from src.dashboard.taxonomy_cards import TaxonomyCard
from src.dashboard.view import assert_no_forbidden_language


def _chip(text: str, *, muted: bool = False) -> str:
    cls = "tchip is-muted" if muted else "tchip"
    return f'<span class="{cls}">{escape(text)}</span>'


def _examples(title: str, examples: Sequence[str], *, kind: str) -> str:
    """One example block. `kind` picks the rule colour; the words carry the meaning."""
    items = "".join(f"<li>{escape(example)}</li>" for example in examples)
    return (
        f'<div class="tex is-{kind}"><span class="texl">{escape(title)}</span>'
        f"<ul>{items}</ul></div>"
    )


def taxonomy_card(card: TaxonomyCard) -> str:
    """One construct as a card: plain register first, reviewer register beneath."""
    classes = "tcard is-polar" if card.is_polar else "tcard"
    chips = [_chip(card.label_type)]
    if card.labels:
        chips.append(_chip(" / ".join(card.labels), muted=True))
    chips.append(_chip(card.direction_plain, muted=card.is_polar))
    if card.is_polar:
        # The word, not only the dash and the muting. Three channels.
        chips.append(_chip("counted as zero", muted=True))

    anchors = "".join(f'<code class="tanchor">{escape(key)}</code>' for key in card.anchor_keys)
    return (
        f'<article class="{classes}">'
        f'<span class="tkey">{escape(card.construct.replace("_", " "))}</span>'
        f'<h3 class="tname">{escape(card.plain_name)}</h3>'
        f'<p class="tplain">{escape(card.plain_meaning)}</p>'
        f'<div class="tchips">{"".join(chips)}</div>'
        f'<p class="tdef">{escape(card.definition)}</p>'
        + _examples("Counts as this", card.positive_examples, kind="yes")
        + _examples("Does not count", card.negative_examples, kind="no")
        + (
            f'<p class="tedge"><b>Edge cases.</b> {escape(card.edge_cases)}</p>'
            if card.edge_cases
            else ""
        )
        + f'<div class="tfoot"><span class="tinst">{escape(card.instrument_anchor)}</span>'
        f"{anchors}</div>"
        "</article>"
    )


def card_deck(cards: Sequence[TaxonomyCard]) -> str:
    """The whole deck as one host-page fragment, screened before it is returned.

    Screened here rather than trusted, because the text originates in
    `config/taxonomy.yaml`: `copy.py` screens itself at import and `view.py`
    screens what it builds, and neither has ever seen a definition from that file.
    `taxonomy_cards.load_cards` screens the fields it loads; this screens the
    assembled surface, which is the pairing `view.render_text` already uses -- the
    first catches what the loader reads, the second catches what a renderer adds.
    """
    body = "".join(taxonomy_card(card) for card in cards)
    html = f'<div class="deck">{body}</div>'
    assert_no_forbidden_language(html)
    return html
