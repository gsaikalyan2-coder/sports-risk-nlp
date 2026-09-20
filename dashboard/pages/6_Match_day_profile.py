"""Page 6 -- a press conference, scored.

Everything this file does is render. `src.dashboard.matchday.build_profile`
fetches, de-identifies, gates, scores and decides; the page branches on what
comes back. That division is what lets the honesty properties be tested at all,
and it is the rule `tests/test_dashboard_pages.py` enforces on every page here.

No photo upload here, by request (2026-09-19). Page 2 ("Score my own text")
is the one place in this dashboard a photograph can be attached, under its own
consent checkbox, and that stays true here: this page never passes `photo` or
`consent` to `build_profile`, so `src.dashboard.matchday._read_face` always
takes its early `if not data: return {}, False, "", ""` branch and no face is
ever read on this page. The face-reading capability in `matchday.py` itself is
untouched -- `tests/test_pressroom.py` still exercises it directly -- this page
simply never reaches for it. One consequence worth being explicit about: with
no face channel, every score this page produces is the words-only score, so the
combined-vs-text-only comparison Page 2 shows never appears here.

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
    build_profile,
    build_scenario_profile,
    evidence_height,
    motion_panel,
    panel_height,
    plain,
    score_from_view,
    spans_panel,
    theme,
    transcript_stack_status,
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
st.markdown(f"# {plain.MATCHDAY_TITLE}")
st.markdown(theme.lede(plain.MATCHDAY_LEDE), unsafe_allow_html=True)

url = st.text_input(
    plain.MATCHDAY_LINK_LABEL, key="press_url", placeholder="https://www.youtube.com/watch?v=..."
)

policy = st.selectbox(
    "How should the four two-sided signals be counted?",
    list(POLICY_LABELS),
    index=list(POLICY_LABELS).index(
        st.session_state.get("policy_label_shared", DEFAULT_POLICY_LABEL)
    ),
    key="policy_label_matchday",
)
st.session_state["policy_label_shared"] = policy

# Said before the reader presses anything, because an absent optional stack
# fails by being absent, and an absent stack looks like a bug otherwise.
_words = transcript_stack_status()
if not _words:
    st.warning(_words.detail)

# ---------------------------------------------------------------------------
# Synthetic scenario: an alternative to a real link, always available (the
# real-athlete path below stays gated behind SRN_MATCHDAY_REAL_ATHLETES,
# declined by owner decision -- docs/phase29_decision_draft.md, 2026-09-20).
# Placed BEFORE the real-link button's `st.stop()` so it renders regardless
# of whether the gated real fetch ever succeeds.
# ---------------------------------------------------------------------------

st.markdown(f"## {plain.SCENARIO_TITLE}")
st.markdown(theme.lede(plain.SCENARIO_LEDE), unsafe_allow_html=True)

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

if st.button(plain.SCENARIO_SUBMIT, key="scenario_generate"):
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

    scenario_headline, scenario_panel = st.columns([1, 2])
    with scenario_headline:
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
    with scenario_panel:
        components.html(
            motion_panel(scenario_view, mode=mode),
            height=panel_height(scenario_view),
            scrolling=False,
        )

    scenario_tiles = widgets_for(scenario_view)
    for row_start in range(0, len(scenario_tiles), 5):
        for column, widget in zip(
            st.columns(5), scenario_tiles[row_start : row_start + 5], strict=False
        ):
            with column:
                st.markdown(
                    f'<div class="widget{" is-inert" if widget.inert else ""}">'
                    f'<span class="wl">{widget.title}</span>'
                    f'<span class="wv" style="font-size:32px">{widget.value}</span>'
                    f'<span class="wu">{widget.secondary_caption}</span></div>',
                    unsafe_allow_html=True,
                )

    with st.expander("Provenance: what generated this scenario"):
        for notice in scenario_view.notices:
            st.markdown(f"- {notice}")
        st.markdown(f"- {SCENARIO_STAMP}")
        st.markdown(
            f"- Constructs planted: {scenario_record.generation_spec['planted_constructs']}"
        )
        st.markdown(f"**{scenario_view.risk.stamp}**")

st.divider()
st.markdown("## Or: from a real press conference")

if not st.button(plain.MATCHDAY_SUBMIT):
    st.caption(plain.MATCHDAY_EMPTY)
    st.stop()

with st.spinner(plain.MATCHDAY_WORKING):
    profile = build_profile(policy=policy, backend=_lexicon(), url=url)

# --- nothing was read -------------------------------------------------------
if not profile:
    st.info(profile.transcript_detail)
    st.caption(plain.PAGE2_REJECTED_WHY)
    st.stop()

# --- a transcript was read and scored ---------------------------------------
view = profile.view
score = score_from_view(view)

st.success(
    f"Read {plain.MATCHDAY_READ_BY.format(route=profile.transcript.route)} "
    f"({profile.transcript.segments} segments). "
    f"{profile.replacements} name-like item(s) replaced before scoring."
)
st.caption(profile.transcript.stamp)

if not profile.on_topic:
    st.error(f"**{plain.OFF_TOPIC_HEADLINE}** {profile.relevance_detail}")
    st.caption(plain.OFF_TOPIC_PLAIN)

st.caption(view.risk.stamp)
st.warning(view.caveat)
if not view.is_default_policy:
    st.error(view.policy_note)

headline, panel = st.columns([1, 2])
with headline:
    st.markdown(
        f'<div class="hero-figure"><span class="hl">Final score</span>'
        f'<span class="hv">{profile.score_100}</span>'
        f'<span class="hl">out of 100, ranking only</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="margin-top:16px"><span class="band">{score.band.label}</span></p>',
        unsafe_allow_html=True,
    )
    st.caption(score.band.describe())
with panel:
    components.html(motion_panel(view, mode=mode), height=panel_height(view), scrolling=False)

st.caption(plain.SCALE_NOTE_TEXT)

st.markdown("## The ten signals behind the score")
st.markdown(theme.lede(plain.DIMENSIONS_NOTE), unsafe_allow_html=True)
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
st.markdown(theme.lede(plain.SPANS_PLAIN), unsafe_allow_html=True)
components.html(spans_panel(view, mode=mode), height=evidence_height(view), scrolling=False)

if view.unevidenced_driver_count:
    st.error(
        f"{view.unevidenced_driver_count} signal(s) moved the score with no supporting "
        "words in the transcript. The system is asserting something it cannot point at."
    )

with st.expander("The transcript, as it was scored"):
    st.markdown(f"> {profile.transcript.text[:4000]}")

with st.expander("Provenance and limitations: read before quoting any number"):
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {profile.transcript.stamp}")
    st.markdown(f"- {plain.MATCHDAY_DEID_NOTE.format(count=profile.replacements)}")
    st.markdown(f"- {plain.RELEVANCE_MEASURED}")
    st.markdown(f"- {score.band.describe()}")
    st.markdown(f"**{view.risk.stamp}**")
