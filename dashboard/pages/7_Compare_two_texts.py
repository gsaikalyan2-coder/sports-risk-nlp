"""Page 7 -- two pieces of writing, read the same way, diffed.

A renderer and nothing else, on the same contract as every other file under
`dashboard/`: it reaches the project only through `src.dashboard`, constructs no
view or scorer of its own, and computes no number. `tests/test_dashboard_pages.py`
walks this file with the rest.

Three things are specific to this page, and all three are about the one sentence
it invites -- "this one is twelve points worse than that one".

**Both texts pass the admission gate before either is scored.** `LexiconBackend`
returns a reading for anything; keyboard mash matches nothing, every probability
comes back 0.0, the weighted sum is 0.0 and the logistic squash turns that into
an index of exactly 0.50. On a comparison page that failure is worse than on
page 2, because two rejected strings produce two identical confident figures and
a diff of zero, which reads as a finding. So both strings are admitted first, and
a refusal stops the page before a `DashboardView` exists for either.

**One policy, both texts.** Scoring the two under different policies would put
the difference between the two assumptions inside the gap, where no reader could
separate it from a difference between the texts.

**No bands.** Two band labels side by side is a verdict comparison between two
people, which is the exact shape `docs/ethics.md` forbids, and this page is
where it would look most natural. The 0-100 figures are shown; the thirds of the
scale are not.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Compare two texts", layout="wide")

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    LexiconBackend,
    admit,
    build_view,
    construct_delta_chart,
    plain,
    score_from_view,
    scorer_for,
    theme,
)

mode = theme.mode_control(st)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)


# Plain data, so caching it is safe -- see the note in 3_Brain_atlas.py for why
# anything that later meets an `isinstance` check may not be cached here.
@st.cache_resource
def _lexicon():
    return LexiconBackend()


st.markdown('<p class="mono-label">Live scoring · side by side</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.COMPARE_TITLE}")
st.markdown(theme.lede(plain.COMPARE_LEDE), unsafe_allow_html=True)

left_col, right_col = st.columns(2)
with left_col:
    text_a = st.text_area("First piece of writing", height=160, key="compare_text_a")
with right_col:
    text_b = st.text_area("Second piece of writing", height=160, key="compare_text_b")

# The same shared key the dashboard and page 2 write, so a setting chosen
# anywhere is the setting in force here, and one chosen here carries back.
POLICY_STATE_KEY = "policy_label_shared"
policy = st.selectbox(
    "How should the four two-sided signals be counted?",
    list(POLICY_LABELS),
    index=list(POLICY_LABELS).index(st.session_state.get(POLICY_STATE_KEY, DEFAULT_POLICY_LABEL)),
    key="policy_label_compare",
)
st.session_state[POLICY_STATE_KEY] = policy
st.caption(plain.COMPARE_ONE_SETTING)

submitted = st.button("Compare")

if not (submitted or (text_a.strip() and text_b.strip())):
    st.caption(plain.COMPARE_EMPTY)
    st.stop()

if not (text_a.strip() and text_b.strip()):
    st.caption(plain.COMPARE_EMPTY)
    st.stop()

# Both gates run before either backend call. A page that admitted the first text,
# scored it, then refused the second would leave one number on screen with
# nothing to compare it against -- and that lone number is the thing that gets
# screenshotted.
for label, candidate in (("first", text_a), ("second", text_b)):
    admission = admit(candidate)
    if not admission:
        st.error(f"**{plain.COMPARE_REJECTED}** The {label} one: {admission.detail}")
        st.caption(plain.COMPARE_NO_NUMBER_WHY)
        st.stop()

scorer = scorer_for(policy)
view_a = build_view(text=text_a, backend=_lexicon(), scorer=scorer)
view_b = build_view(text=text_b, backend=_lexicon(), scorer=scorer)
score_a = score_from_view(view_a)
score_b = score_from_view(view_b)

# Above the fold, outside anything collapsible, before the first number.
st.caption(view_a.risk.stamp)
st.warning(view_a.caveat)
st.error(plain.COMPARE_CAVEAT)
if not view_a.is_default_policy:
    st.error(view_a.policy_note)

# A text can pass the admission gate -- it is language -- and still match none of
# the ten signals, at which point the weighted sum is 0.0 and the index is
# exactly the midpoint. On a single-text page that shows up as ten tiles reading
# 0.00. Here the midpoint would quietly become the baseline the other text is
# measured against, so it is named before the gap is shown rather than after.
for _name, _view in (("first", view_a), ("second", view_b)):
    if _view.detected_nothing:
        st.error(f"**The {_name} text** {plain.COMPARE_NOTHING_DETECTED}")

a_col, delta_col, b_col = st.columns([1, 1, 1])
with a_col:
    st.markdown(
        f'<div class="widget"><span class="wl">First text</span>'
        f'<span class="wv">{score_a.score_100}</span>'
        f'<span class="wu">out of 100, ranking only</span></div>',
        unsafe_allow_html=True,
    )
with b_col:
    st.markdown(
        f'<div class="widget"><span class="wl">Second text</span>'
        f'<span class="wv">{score_b.score_100}</span>'
        f'<span class="wu">out of 100, ranking only</span></div>',
        unsafe_allow_html=True,
    )
with delta_col:
    st.markdown(
        f'<div class="hero-figure"><span class="hl">Gap</span>'
        f'<span class="hv">{score_b.score_100 - score_a.score_100:+d}</span>'
        f'<span class="hl">points of an uncalibrated scale</span></div>',
        unsafe_allow_html=True,
    )

st.caption(plain.SCALE_NOTE_TEXT)

st.markdown("## Which of the ten signals separate them")
st.markdown(theme.lede(plain.COMPARE_HOW_TO_READ), unsafe_allow_html=True)
# Paired by name, exactly as the chart pairs them. A positional zip here and a
# name pairing in the chart would be two answers to one question.
_first = {bar.construct: bar.probability for bar in view_a.bars}
if all(abs(bar.probability - _first[bar.construct]) < 0.0005 for bar in view_b.bars):
    st.info(plain.COMPARE_IDENTICAL)
st.markdown(
    construct_delta_chart(
        view_a.bars,
        view_b.bars,
        left_label="first text",
        right_label="second text",
    ),
    unsafe_allow_html=True,
)

unevidenced = view_a.unevidenced_driver_count + view_b.unevidenced_driver_count
if unevidenced:
    st.error(
        f"{unevidenced} signal(s) across the two texts moved a score with no supporting "
        "words behind them. The gap above is partly built on assertions neither text "
        "can be pointed at for."
    )

with st.expander("Provenance and limitations: read before quoting any number here"):
    st.markdown(f"- {plain.COMPARE_CAVEAT}")
    st.markdown(f"- {plain.COMPARE_ONE_SETTING}")
    st.markdown(f"- {plain.SCALE_NOTE_TEXT}")
    for notice in view_a.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"**{view_a.risk.stamp}**")
