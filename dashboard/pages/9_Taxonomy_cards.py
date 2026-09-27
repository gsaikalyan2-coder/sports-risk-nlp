"""Page 9 -- the ten construct definitions as a card deck. The only page with no number.

Same contract as every other page: only `src.dashboard` is reachable and nothing is
constructed here.

**This page has no `st.expander`, on purpose.** Every other page hides its
provenance behind one and is required to put the stamp above it, because every
other page shows a reading. This one shows definitions and citations: nothing has
been detected, scored, ranked or squashed, so there is no stamp to attach and
nothing for a caveat to caveat. Adding an expander here would mean either faking a
provenance line for text that has none, or tripping the shell rule that says a page
with collapsible sections must stamp itself. The notes are therefore inline, where
they are read.

**A card that could not cite itself would not render.** `load_cards` refuses a
construct whose `instrument_anchor` resolves to no key in `paper/refs.bib`, so a
card on this page is cited by construction rather than by proofreading.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Taxonomy cards", layout="wide")

from src.dashboard import card_deck, load_cards, plain, theme  # noqa: E402

mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

cards = load_cards()

st.markdown('<p class="mono-label">Taxonomy</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.DECK_TITLE}")
st.markdown(theme.lede(plain.DECK_PLAIN), unsafe_allow_html=True)

st.caption(plain.DECK_NO_NUMBERS)
st.caption(plain.DECK_SOURCE_NOTE)

st.info(plain.DECK_POLAR_NOTE)
st.markdown(card_deck(cards), unsafe_allow_html=True)
st.caption(plain.DECK_GUIDELINES_NOTE)
