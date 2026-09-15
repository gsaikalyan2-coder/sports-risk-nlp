"""Page 1b -- the explanation behind one widget.

A tile on the grid shows two numbers and no words. This page is the other half
of that bargain: the same two numbers, plus what the signal is, the words that
triggered it, what it did to the index, and how well the detector handles this
particular signal on unseen sentence patterns.

Same structural rules as the entry point: `src.dashboard` is the only reachable
part of the project, and no view is constructed here. The construct is read from
session state, which the tile wrote -- there is no free-text route into this
page, so it cannot render an explanation of a signal the reader did not open.
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
    PER_CONSTRUCT_CAPTION,
    POLICY_LABELS,
    build_view,
    construct_contribution_chart,
    evidence_height,
    known_examples,
    load_per_construct,
    per_construct_chart,
    plain,
    risk_waterfall,
    scorer_for,
    spans_panel,
    theme,
    widget_for,
)

st.set_page_config(page_title="Signal detail", layout="wide")
# The mode the reader chose on the dashboard, not a second control: this page is
# opened by clicking a tile, so it must look like the page the tile was on.
mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

HOME = "app.py"


# NOT cached with @st.cache_resource, deliberately.
#
# Streamlit's watcher re-imports src.dashboard.* when a file changes, which
# creates NEW class objects. An object held in cache_resource was built from the
# OLD ones, so isinstance(x, SomeClass) against the reloaded class returns False
# and the page dies with a type error about a type it plainly is. That is
# exactly how build_view's isinstance(backend, ReplayBackend) check failed here.
#
# The cousin is worse, and is why this is a rule rather than a one-line fix:
# require_simulated() is also an isinstance check, so a cached source could trip
# the ETHICS GATE for no reason at all -- and a guard that cries wolf is a guard
# that gets switched off.
#
# The rule is narrow: an object that something later passes to isinstance may not
# be cached. Caching plain DATA (_per_construct, _lexicon) is unaffected, because
# nothing type-checks it.
#
# Nothing is lost here. Reading the fixture is a 19 KB JSON parse, and the
# simulated sources are stateless functions of (seed, index) -- rebuilding one
# returns byte-identical windows, the property Step 0 was built around.
def _replay():
    return known_examples()


@st.cache_resource
def _per_construct():
    return load_per_construct()


st.markdown(f'<div class="announcement">{plain.ANNOUNCEMENT}</div>', unsafe_allow_html=True)

construct = st.session_state.get("detail_construct")
if not construct:
    st.markdown("# Nothing selected")
    st.markdown(
        '<p class="lede">Open a signal from the dashboard to see its explanation.</p>',
        unsafe_allow_html=True,
    )
    st.button("Back to the dashboard", on_click=lambda: st.switch_page(HOME))
    st.stop()

replay = _replay()
example_id = st.session_state.get("example_id") or replay.example_ids[0]
policy = st.session_state.get("policy_label") or DEFAULT_POLICY_LABEL
if policy not in POLICY_LABELS:
    policy = DEFAULT_POLICY_LABEL

view = build_view(example_id=example_id, backend=replay, scorer=scorer_for(policy))
widget = widget_for(view, construct)
bar = next(b for b in view.bars if b.construct == construct)
name, meaning, direction = plain.CONSTRUCTS[construct]

if st.button("← Back to all signals"):
    st.session_state["detail_construct"] = ""
    st.switch_page(HOME)

st.markdown(f'<p class="mono-label">{construct.replace("_", " ")}</p>', unsafe_allow_html=True)
st.markdown(f"# {name}")
st.markdown(theme.lede(f"{meaning} {plain.DETAIL_INTRO}"), unsafe_allow_html=True)

st.caption(view.risk.stamp)
st.caption(view.policy_note)
st.markdown(f"> {replay.get(example_id).text}")

left, middle, right = st.columns(3)
with left:
    st.markdown(
        f'<div class="widget"><span class="wl">Detection strength</span>'
        f'<span class="wv">{widget.value}</span>'
        f'<span class="wu">{widget.value_caption}</span></div>',
        unsafe_allow_html=True,
    )
with middle:
    st.markdown(
        f'<div class="widget"><span class="wl">Push on the index</span>'
        f'<span class="wv">{widget.secondary}</span>'
        f'<span class="wu">{widget.secondary_caption}</span></div>',
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        f'<div class="widget"><span class="wl">Supporting words</span>'
        f'<span class="wv">{len(bar.spans)}</span>'
        f'<span class="wu">spans in the text the explanation points at</span></div>',
        unsafe_allow_html=True,
    )

st.markdown("## What this number means here")
if bar.inert:
    st.info(plain.CONTRIBUTING_PLAIN)
else:
    st.markdown(f'<p class="lede">{bar.note.capitalize()}.</p>', unsafe_allow_html=True)
st.markdown(theme.lede(plain.RISK_PLAIN), unsafe_allow_html=True)

st.markdown("## The words behind it")
st.markdown(theme.lede(plain.SPANS_PLAIN), unsafe_allow_html=True)
components.html(spans_panel(view, mode=mode), height=evidence_height(view), scrolling=False)

st.markdown("## Where it sits among the ten")
st.markdown(theme.lede(plain.CHART_LEFT_PLAIN), unsafe_allow_html=True)
st.markdown(construct_contribution_chart(view.bars), unsafe_allow_html=True)
st.markdown(theme.lede(plain.WATERFALL_PLAIN), unsafe_allow_html=True)
st.markdown(
    risk_waterfall(view.bars, raw_score=view.raw_score, index=view.risk.value),
    unsafe_allow_html=True,
)

st.markdown("## How well this signal is detected at all")
st.markdown(theme.lede(plain.PER_CONSTRUCT_PLAIN), unsafe_allow_html=True)
st.markdown(
    per_construct_chart(_per_construct(), caption=PER_CONSTRUCT_CAPTION),
    unsafe_allow_html=True,
)

with st.expander("Provenance and limitations: read before quoting any number"):
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {view.card.provenance}")
    st.markdown(f"**{view.risk.stamp}**")
