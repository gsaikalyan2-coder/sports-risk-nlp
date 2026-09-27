"""Page 2 -- score a piece of text and read the result.

The score is the project's risk index multiplied by 100, and the band is a third
of that scale. Both come from `src.dashboard.bands`, whose docstring records why
a band is allowed here at all and why it can never reach a paper figure: the
band is constructed with a mandatory caveat and is only ever rendered through
`Band.describe()`, which emits the caveat with it.

Pasted text is the reader's own. It is scored, shown back, and dropped: no
store, no log, no cache, and the view it produces is marked non-exportable by
the publication guard, so it cannot become a figure.

Owner instruction, 2026-09-27: **typed words are the only input.** The photo /
video uploader and the facial-cue consent tick that Phases 27 and 28 put on this
page are gone from it. `src/media/` and `src/dashboard/mediaio.py` still exist
and are still tested, so none of their honesty machinery was weakened, but no
page calls them any more and therefore no picture reaches a score. The text-only
path this page now takes is the one every number in the paper uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    POLICY_TILE_NOTE,
    LexiconBackend,
    admit,
    build_view,
    evidence_height,
    motion_panel,
    panel_height,
    plain,
    score_from_view,
    scorer_for,
    spans_panel,
    theme,
    widgets_for,
)

st.set_page_config(page_title="Score my own text", layout="wide")
# This page, and only this page, runs the Claude design language
# (DESIGNclaude.md): serif display, coral CTA, warm surfaces. It follows the
# reader's light/dark choice from the dashboard, expressed in *its* tokens:
# the cream canvas becomes surface-dark #181715, the cream cards become
# surface-dark-elevated #252320, the text roles invert to on-dark. The coral CTA
# does not move: it is the brand voltage on both surfaces.
# The control is repeated here rather than only on the dashboard, because a
# reader can land on this page first. It reads and writes the same plain session
# key, so the two pages stay in step in both directions.
mode = theme.mode_control(st)
CLAUDE_MODE = "claude-dark" if mode == "dark" else "claude"
st.markdown(theme.claude_css(mode), unsafe_allow_html=True)


@st.cache_resource
def _lexicon():
    return LexiconBackend()


st.markdown('<p class="mono-label">Live scoring</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.PAGE2_TITLE}")
st.markdown(theme.claude_lede(plain.PAGE2_LEDE), unsafe_allow_html=True)

pasted = st.text_area(
    "Text",
    height=160,
    key="pasted_text",
    placeholder="Type or paste a few sentences an athlete wrote before a competition...",
)

# Reads and writes the same plain key the dashboard writes, so the setting a
# reader chose over there is the setting their own text is scored under here,
# and a change made here carries back. Two selectboxes, one fact.
POLICY_STATE_KEY = "policy_label_shared"
policy = st.selectbox(
    "How should the four two-sided signals be counted?",
    list(POLICY_LABELS),
    index=list(POLICY_LABELS).index(st.session_state.get(POLICY_STATE_KEY, DEFAULT_POLICY_LABEL)),
    key="policy_label_live",
)
st.session_state[POLICY_STATE_KEY] = policy
submitted = st.button(plain.PAGE2_SUBMIT)

source_text = pasted

if not (submitted or source_text.strip()):
    st.caption(plain.PAGE2_EMPTY)
    st.stop()

if not source_text.strip():
    st.caption(plain.PAGE2_EMPTY)
    st.stop()

# The admission gate, and it runs BEFORE the backend rather than after it.
#
# `LexiconBackend` will happily score keyboard mash: nothing matches, every
# probability is 0.0, the weighted sum is 0.0, and the logistic squash turns that
# into an index of exactly 0.50 -- a psychological score of 50 out of 100, with a
# band, a stamp and ten tiles under it, for a string that contained no words. The
# arithmetic is right and the screen is a lie. So the refusal happens here, where
# no `DashboardView` has been constructed yet and there is therefore no number in
# existence to screenshot. See src/dashboard/gibberish.py.
admission = admit(source_text)
if not admission:
    st.error(f"**{plain.PAGE2_REJECTED}** {admission.detail}")
    st.caption(plain.PAGE2_REJECTED_WHY)
    st.stop()

view = build_view(text=source_text, backend=_lexicon(), scorer=scorer_for(policy))
score = score_from_view(view)

st.markdown(f"> {source_text}")

st.caption(view.risk.stamp)
st.warning(view.caveat)
if not view.is_default_policy:
    st.error(view.policy_note)

headline, panel = st.columns([1, 2])
with headline:
    st.markdown(
        f'<div class="hero-figure"><span class="hl">Psychological score</span>'
        f'<span class="hv">{score.score_100}</span>'
        f'<span class="hl">out of 100, ranking only</span></div>',
        unsafe_allow_html=True,
    )
    # Rendered through describe(), never band.label: a band with its caveat
    # detached is a verdict about a person. See src/dashboard/bands.py.
    st.markdown(
        f'<p style="margin-top:16px"><span class="band">{score.band.label}</span></p>',
        unsafe_allow_html=True,
    )
    st.caption(score.band.describe())
with panel:
    components.html(
        motion_panel(view, mode=CLAUDE_MODE), height=panel_height(view), scrolling=False
    )

st.caption(plain.SCALE_NOTE_TEXT)

st.markdown("## The ten dimensions behind the score")
st.caption(
    POLICY_TILE_NOTE[view.policy_key].capitalize()
    + ". "
    + (
        f"This text triggered {view.two_sided_detected} of them, so the setting "
        "changes those tiles and the index with them."
        if view.two_sided_detected
        else "This text triggered none of them, so the setting states a different "
        "assumption and every number stays where it is."
    )
    + " Four of the ten tiles below move with it; the other six do not."
)
st.markdown(theme.claude_lede(plain.DIMENSIONS_NOTE), unsafe_allow_html=True)
tiles = widgets_for(view)
for row_start in range(0, len(tiles), 5):
    for column, widget in zip(st.columns(5), tiles[row_start : row_start + 5], strict=False):
        with column:
            st.markdown(
                f'<div class="widget{" is-inert" if widget.inert else ""}">'
                f'<span class="wl">{widget.title}</span>'
                f'<span class="wv" style="font-size:32px">{widget.value}</span>'
                f'<span class="wu">{widget.secondary_caption}</span></div>',
                unsafe_allow_html=True,
            )

st.markdown("## The words that produced it")
st.markdown(theme.claude_lede(plain.SPANS_PLAIN), unsafe_allow_html=True)
components.html(spans_panel(view, mode=CLAUDE_MODE), height=evidence_height(view), scrolling=False)

if view.unevidenced_driver_count:
    st.error(
        f"{view.unevidenced_driver_count} signal(s) moved the score with no supporting "
        "words in the text. The system is asserting something it cannot point at."
    )

with st.expander("Provenance and limitations: read before quoting any number"):
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {plain.SCALE_NOTE_TEXT}")
    st.markdown(f"- {score.band.describe()}")
    st.markdown(f"**{view.risk.stamp}**")
