"""Page 6 -- a synthetic match-day scenario, scored.

Everything this file does is render. `src.dashboard.matchday.build_scenario_profile`
generates and scores; the page just draws what comes back.

Real-press-conference input was removed from this page on 2026-09-20 by owner
request: `SRN_MATCHDAY_REAL_ATHLETES` stays permanently unset
(`docs/phase29_decision_draft.md`, `CLAUDE.md` sec.14.6, Declined), so the
real-link path had nothing to show but a permanent refusal message. The
underlying capability (`src.dashboard.matchday.build_profile`,
`src.media.pressroom`) is untouched and still directly tested by
`tests/test_pressroom.py` -- only this page's UI for it was removed.

The order on screen is deliberate and is the same order the other scoring page
uses: what was read, then the stamp, then the number. A caveat below a figure
is a caveat a screenshot loses.
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
    LIFE_CONTEXT_LABELS,
    LIFE_CONTEXTS,
    POLICY_LABELS,
    SCENARIO_SPORTS,
    SCENARIO_STAMP,
    TIMING_LABELS,
    TIMINGS,
    LexiconBackend,
    build_scenario_profile,
    motion_panel,
    panel_height,
    plain,
    score_from_view,
    theme,
    widgets_for,
)

st.set_page_config(page_title="Match-day profile", layout="wide")

mode = st.sidebar.radio(
    "Appearance",
    ("light", "dark"),
    index=("light", "dark").index(st.session_state.get("mode", theme.DEFAULT_MODE)),
    format_func=str.capitalize,
    horizontal=True,
    key="appearance_choice_matchday",
)
st.session_state["mode"] = mode
# The dashboard (Cohere) language, not the Claude one. `tests/test_dashboard_pages.py`
# holds that the Claude language belongs to Page 2 alone, and the rule exists so
# the two design specifications stay separable; a second page borrowing it is how
# a design system becomes one undocumented blend.
st.markdown(theme.app_css(mode), unsafe_allow_html=True)


@st.cache_resource
def _lexicon():
    return LexiconBackend()


st.markdown(f'<div class="announcement">{plain.ANNOUNCEMENT}</div>', unsafe_allow_html=True)
st.markdown('<p class="mono-label">Match-day profile</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.SCENARIO_TITLE}")
st.markdown(theme.lede(plain.SCENARIO_LEDE), unsafe_allow_html=True)

policy = st.selectbox(
    "How should the four two-sided signals be counted?",
    list(POLICY_LABELS),
    index=list(POLICY_LABELS).index(
        st.session_state.get("policy_label_shared", DEFAULT_POLICY_LABEL)
    ),
    key="policy_label_matchday",
)
st.session_state["policy_label_shared"] = policy

scenario_col1, scenario_col2, scenario_col3 = st.columns(3)
with scenario_col1:
    scenario_sport = st.selectbox("Sport", SCENARIO_SPORTS, key="scenario_sport")
with scenario_col2:
    scenario_timing = st.selectbox(
        "When, before the competition",
        TIMINGS,
        format_func=lambda key: TIMING_LABELS[key],
        key="scenario_timing",
    )
with scenario_col3:
    scenario_life_context = st.selectbox(
        "Life context",
        LIFE_CONTEXTS,
        format_func=lambda key: LIFE_CONTEXT_LABELS[key],
        key="scenario_life_context",
    )

scenario_seed = st.number_input(
    plain.SCENARIO_SEED_LABEL, min_value=0, max_value=999_999, value=42, step=1, key="scenario_seed"
)

if not st.button(plain.SCENARIO_SUBMIT, key="scenario_generate"):
    st.caption(plain.SCENARIO_EMPTY)
    st.stop()

scenario_record, scenario_view = build_scenario_profile(
    policy=policy,
    backend=_lexicon(),
    sport=scenario_sport,
    timing=scenario_timing,
    life_context=scenario_life_context,
    seed=int(scenario_seed),
)
scenario_score = score_from_view(scenario_view)
scenario_score_100 = round(scenario_view.risk.value * 100)

st.caption(SCENARIO_STAMP)
st.caption(scenario_view.risk.stamp)
st.markdown(f"> {scenario_record.text}")
st.warning(scenario_view.caveat)

headline, panel = st.columns([1, 2])
with headline:
    st.markdown(
        f'<div class="hero-figure"><span class="hl">Score</span>'
        f'<span class="hv">{scenario_score_100}</span>'
        f'<span class="hl">out of 100, ranking only</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="margin-top:16px"><span class="band">{scenario_score.band.label}</span></p>',
        unsafe_allow_html=True,
    )
    st.caption(scenario_score.band.describe())
with panel:
    components.html(
        motion_panel(scenario_view, mode=mode), height=panel_height(scenario_view), scrolling=False
    )

st.caption(plain.SCALE_NOTE_TEXT)

st.markdown("## The ten signals behind the score")
st.markdown(theme.lede(plain.DIMENSIONS_NOTE), unsafe_allow_html=True)
tiles = widgets_for(scenario_view)
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

with st.expander("Provenance and limitations: read before quoting any number"):
    for notice in scenario_view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {SCENARIO_STAMP}")
    st.markdown(f"- Constructs planted: {scenario_record.generation_spec['planted_constructs']}")
    st.markdown(f"- {scenario_score.band.describe()}")
    st.markdown(f"**{scenario_view.risk.stamp}**")
