"""Page 7 -- one passage as a contour. A renderer, and nothing else.

Same contract as every other page: `src.dashboard` is the only reachable part of
the project, no view and no scorer is constructed here, and the stamp is rendered
above the fold and outside anything collapsible.
`tests/test_dashboard_pages.py` enforces all of that structurally by walking every
file under `dashboard/`.

Two things are specific to this page.

**A refusal is an outcome, not an error.** `build_ribbon` raises `RibbonRefused`
for text that is not language, for one sentence, and for a wall of forty. Each
carries wording written for the reader, and this page prints it and stops. What it
must never do is fall back to scoring something else -- the Phase 27 rule: an
input that cannot be read produces no number.

**There is no `example_id` route in.** The ribbon needs a backend that can score
new text and `ReplayBackend.predict` refuses by design, so every column on this
page comes from the word-list floor. That is stated on the page rather than
implied, because a reader who assumes these are the paper's model's numbers has
been misled by the page, not by the figure.

Run:  streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path before the first `src.` import -- `streamlit run` puts the
# entry point's directory on sys.path, not the repository root. Idempotent, and a
# no-op where PYTHONPATH already covers it (as the images do).
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Sentence ribbon", layout="wide")

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    RibbonRefused,
    build_ribbon,
    plain,
    scorer_for,
    sentence_ribbon,
    theme,
)

mode = theme.mode_control(st)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

policy = st.session_state.get("policy_label", DEFAULT_POLICY_LABEL)
if policy not in POLICY_LABELS:
    policy = DEFAULT_POLICY_LABEL

st.markdown('<p class="mono-label">Passage shape</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.RIBBON_TITLE}")
st.markdown(theme.lede(plain.RIBBON_PLAIN), unsafe_allow_html=True)

text = st.text_area(
    plain.RIBBON_PROMPT,
    value=plain.RIBBON_SAMPLE,
    height=150,
    key="ribbon_text",
)
st.caption(plain.RIBBON_SAMPLE_NOTE)

try:
    ribbon = build_ribbon(text, scorer=scorer_for(policy))
except RibbonRefused as refusal:
    # No figure, no number, no partial render. The reason is the whole output.
    st.error(str(refusal))
    st.stop()

# Above the fold, outside anything collapsible.
st.caption(ribbon.stamp)
st.caption(ribbon.scale_label)

peak = ribbon.peak
left, middle, right = st.columns(3)
with left:
    st.markdown(
        f'<div class="widget"><span class="wl">Whole passage</span>'
        f'<span class="wv">{ribbon.whole.display}</span>'
        f'<span class="wu">{ribbon.whole.detail}</span></div>',
        unsafe_allow_html=True,
    )
with middle:
    highest = peak.surface.display if peak else "-"
    where = f"sentence {peak.index + 1} of {len(ribbon.bands)}" if peak else "no sentence scored"
    st.markdown(
        f'<div class="widget"><span class="wl">Highest sentence</span>'
        f'<span class="wv">{highest}</span>'
        f'<span class="wu">{where}</span></div>',
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        f'<div class="widget"><span class="wl">Sentences with no column</span>'
        f'<span class="wv">{ribbon.n_silent} of {len(ribbon.bands)}</span>'
        '<span class="wu">nothing was detected in these, so they carry no number</span>'
        "</div>",
        unsafe_allow_html=True,
    )

st.markdown(sentence_ribbon(ribbon), unsafe_allow_html=True)

st.markdown("## How to read it")
for heading, body in plain.RIBBON_HOW_TO_READ:
    st.markdown(f"**{heading}.** {body}")

st.info(plain.RIBBON_NOT_AVERAGE)

st.markdown("## Sentence by sentence")
for band in ribbon.bands:
    reading = band.surface.display if band.surface else "no number"
    st.markdown(f"**{band.index + 1}. {reading}** - {band.state}")
    st.markdown(f"> {band.text}")

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.RIBBON_FLOOR_NOTE}")
    st.markdown(f"- {plain.RIBBON_WHAT_IT_IS_NOT}")
    st.markdown(f"- {ribbon.caveat}")
    st.markdown(f"- Scored by: {ribbon.source}")
    st.markdown(f"**{ribbon.stamp}**")
