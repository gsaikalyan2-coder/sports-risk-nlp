"""Page 7 -- evidence coverage. A renderer, and nothing else.

Same contract as every other file under `dashboard/`: `src.dashboard` is the
only reachable part of the project, no view is constructed here, and
`tests/test_dashboard_pages.py` enforces both structurally by walking this
directory. This file computes nothing.

Two things are specific to this page.

**It is not behind a feature flag, and that is deliberate.** Pages 3 to 5 sit
behind `SRN_COGNITIVE_LAYER` because they introduce *simulated signals* a reader
could mistake for measurements, and because a real physiological source behind
that seam is a different privacy class (`CLAUDE.md` sec.11.2). This page
introduces no source, no signal, no sensor, no dependency and no new number --
it is a projection of a `DashboardView` the dashboard has already built. There
is nothing for a flag to protect. The consequence was accepted when the decision
was taken on 2026-09-22: every visitor sees a low count from first load, and a
flag must not be added later to hide it on a demo day.

**The caveats render above the table and outside the expander.** The three in
`plain.COVERAGE_CAVEATS` guard three specific misreadings -- subscales read as
items, silent read as absent, coverage read as correctness -- and a caveat below
the number does not travel with a screenshot of the number. Same rule the widget
grid already follows, for the same reason.
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
    build_view,
    coverage_for,
    coverage_height,
    coverage_panel,
    coverage_widget,
    known_examples,
    plain,
    scorer_for,
    theme,
)

st.set_page_config(page_title="Evidence coverage", layout="wide")

mode = theme.mode_control(st)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)


# NOT cached with @st.cache_resource, deliberately. Streamlit's watcher
# re-imports src.dashboard.* on a file change, creating NEW class objects, so an
# object held in cache_resource fails the isinstance check inside build_view
# against a type it plainly is. See the same note on pages 1 and 3.
def _replay():
    return known_examples()


replay = _replay()

st.markdown('<p class="mono-label">Phase 32 · coverage</p>', unsafe_allow_html=True)
st.title(plain.COVERAGE_TITLE)

# The same record the rest of the dashboard is showing. Read from session state
# rather than offered fresh, so two pages cannot disagree about which text is on
# screen; the selector is the fallback for a reader who opened this page first.
example_id = st.session_state.get("example_id") or replay.example_ids[0]
policy = st.session_state.get("policy_label", DEFAULT_POLICY_LABEL)
if policy not in POLICY_LABELS:
    policy = DEFAULT_POLICY_LABEL

choice = st.selectbox(
    "Committed known example",
    replay.example_ids,
    index=replay.example_ids.index(example_id) if example_id in replay.example_ids else 0,
    key="example_id",
)

view = build_view(example_id=choice, backend=replay, scorer=scorer_for(policy))
ledger = coverage_for(view)

# Above the fold, outside anything collapsible. The correctness caveat goes in
# the error style specifically: it is the one a reader is most likely to skip,
# because the panel looks like a completeness report and reads as one.
st.caption(ledger.stamp)
st.error(plain.COVERAGE_CORRECTNESS_CAVEAT)

tile = coverage_widget(view)
summary, _spacer = st.columns([1, 2])
with summary:
    st.markdown(
        f'<div class="widget"><span class="wl">{tile.title}</span>'
        f'<span class="wv">{tile.value}</span>'
        f'<span class="wu">{tile.value_caption}</span>'
        f'<hr class="wrule">'
        f'<span class="wv" style="font-size:24px">{tile.secondary}</span>'
        f'<span class="wu">{tile.secondary_caption}</span>'
        "</div>",
        unsafe_allow_html=True,
    )

components.html(
    coverage_panel(ledger, mode=mode),
    height=coverage_height(ledger),
    scrolling=False,
)

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.COVERAGE_PLAIN}")
    st.markdown(f"- {plain.COVERAGE_WHAT_IT_IS_NOT}")
    for caveat in plain.COVERAGE_CAVEATS:
        st.markdown(f"- {caveat}")
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"**{view.risk.stamp}**")
