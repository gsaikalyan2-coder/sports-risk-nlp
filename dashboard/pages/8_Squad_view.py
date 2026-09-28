"""Page 8 -- a squad as a queue. A renderer, and nothing else.

Same contract as every other page: `src.dashboard` is the only reachable part of
the project, no view and no scorer is constructed here, and the stamp renders
above the fold and outside anything collapsible.
`tests/test_dashboard_pages.py` enforces all of that structurally.

Three things are specific to this page.

**The order is the output, and there is no squad score.** The argument is in
`src/dashboard/squad.py`'s docstring and stated on the page itself: a mean over
uncalibrated readings looks more solid than its inputs, and it is the number most
likely to be screenshotted beside a team name. The middle row is reported
instead, and it is one athlete's own reading, selected.

**Unreadable athletes render below the ranking, never inside it.** Placing them
last would be a position, and a position is a claim. They appear under their own
count with no number -- the Phase 27 rule, an input that cannot be read produces
no number, applied to a table rather than to a paste box.

**There is no `example_id` route in.** A freshly generated squad needs a backend
that can score new text and `ReplayBackend.predict` refuses by design, so every
row comes from the word-list floor and the page says so rather than letting a
reader assume the paper's model produced it.

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

st.set_page_config(page_title="Squad view", layout="wide")

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    MAX_SQUAD,
    MIN_SQUAD,
    POLICY_LABELS,
    SCENARIO_SPORTS,
    SCENARIO_STAMP,
    SquadRefused,
    build_squad,
    plain,
    scorer_for,
    squad_strip,
    theme,
)

mode = theme.mode_control(st)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

policy = st.session_state.get("policy_label", DEFAULT_POLICY_LABEL)
if policy not in POLICY_LABELS:
    policy = DEFAULT_POLICY_LABEL

st.markdown('<p class="mono-label">Squad view</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.SQUAD_TITLE}")
st.markdown(theme.lede(plain.SQUAD_PLAIN), unsafe_allow_html=True)

left_control, mid_control, right_control = st.columns(3)
with left_control:
    sport = st.selectbox("Sport", SCENARIO_SPORTS, key="squad_sport")
with mid_control:
    size = st.slider(
        plain.SQUAD_PROMPT,
        min_value=MIN_SQUAD,
        max_value=MAX_SQUAD,
        value=10,
        key="squad_size",
    )
with right_control:
    seed = st.number_input("Seed", min_value=0, max_value=99_999, value=11, key="squad_seed")
st.caption(plain.SQUAD_SEED_NOTE)

try:
    squad = build_squad(
        sport=sport, size=int(size), seed=int(seed), policy_scorer=scorer_for(policy)
    )
except SquadRefused as refusal:
    # No figure, no number, no partial render. The reason is the whole output.
    st.error(str(refusal))
    st.stop()

# Above the fold, outside anything collapsible.
st.caption(squad.stamp)
st.caption(SCENARIO_STAMP)
st.caption(squad.scale_label)

top = squad.ordered[0] if squad.ordered else None
left, middle, right = st.columns(3)
with left:
    st.markdown(
        f'<div class="widget"><span class="wl">First in the queue</span>'
        f'<span class="wv">{top.surface.display if top else "-"}</span>'
        f'<span class="wu">{top.plain_context if top else "no athlete could be read"}</span>'
        "</div>",
        unsafe_allow_html=True,
    )
with middle:
    st.markdown(
        f'<div class="widget"><span class="wl">Middle of the queue</span>'
        f'<span class="wv">{squad.median.display if squad.median else "-"}</span>'
        '<span class="wu">one athlete\'s own reading, selected - not an average</span>'
        "</div>",
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        f'<div class="widget"><span class="wl">Could not be read</span>'
        f'<span class="wv">{squad.n_silent} of {len(squad.members)}</span>'
        '<span class="wu">no number, and kept out of the order entirely</span>'
        "</div>",
        unsafe_allow_html=True,
    )

st.markdown(squad_strip(squad), unsafe_allow_html=True)

st.warning(plain.SQUAD_NO_TEAM_SCORE)

st.markdown("## How to read it")
for heading, body in plain.SQUAD_HOW_TO_READ:
    st.markdown(f"**{heading}.** {body}")

st.info(plain.SQUAD_SILENT_NOTE)

st.markdown("## The queue, in words")
for position, member in enumerate(squad.ordered, start=1):
    st.markdown(
        f"**{position}. {member.surface.display}** - {member.plain_context} - {member.state}"
    )
    st.markdown(f"> {member.text}")
for member in squad.silent:
    st.markdown(f"**no number** - {member.plain_context} - {member.state}")
    st.markdown(f"> {member.text}")

st.markdown("## What was found, and in how many")
st.caption(plain.SQUAD_PREVALENCE_NOTE)
for _construct, plain_name, count in squad.prevalence:
    st.markdown(f"- **{plain_name}** - found in {count} of {len(squad.members)}")

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.SQUAD_FLOOR_NOTE}")
    st.markdown(f"- {plain.SQUAD_WHAT_IT_IS_NOT}")
    st.markdown(f"- {squad.caveat}")
    st.markdown(f"- Scored by: {squad.source}")
    st.markdown(f"- {SCENARIO_STAMP}")
    st.markdown(f"**{squad.stamp}**")
