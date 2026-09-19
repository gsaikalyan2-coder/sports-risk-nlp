"""Page 6 -- a photograph and a press conference, one profile.

Everything this file does is render. `src.dashboard.matchday.build_profile`
fetches, de-identifies, gates, scores and decides; the page branches on what
comes back. That division is what lets the honesty properties be tested at all,
and it is the rule `tests/test_dashboard_pages.py` enforces on every page here.

The order on screen is deliberate and is the same order the other scoring page
uses: what was read, then the stamp, then the limitation, then the number. A
caveat below a figure is a caveat a screenshot loses.
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
    FACE_ONLY_STAMP,
    POLICY_LABELS,
    LexiconBackend,
    build_profile,
    evidence_height,
    face_stack_status,
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
photo = st.file_uploader(
    plain.MATCHDAY_PHOTO_LABEL,
    type=["png", "jpg", "jpeg", "webp"],
    key="matchday_photo",
    help=plain.MEDIA_PLAIN,
)
consent = st.checkbox(plain.CONSENT_LABEL, value=False, key="matchday_consent")
st.caption(plain.CONSENT_PLAIN)

policy = st.selectbox(
    "How should the four two-sided signals be counted?",
    list(POLICY_LABELS),
    index=list(POLICY_LABELS).index(
        st.session_state.get("policy_label_shared", DEFAULT_POLICY_LABEL)
    ),
    key="policy_label_matchday",
)
st.session_state["policy_label_shared"] = policy

# What can run here, said before the reader presses anything, because the two
# optional stacks fail by being absent and an absent stack looks like a bug.
_faces = face_stack_status()
_words = transcript_stack_status()
if not _faces:
    st.warning(_faces.detail)
if not _words:
    st.warning(_words.detail)

if not st.button(plain.MATCHDAY_SUBMIT):
    st.caption(plain.MATCHDAY_EMPTY)
    st.stop()

with st.spinner(plain.MATCHDAY_WORKING):
    profile = build_profile(
        policy=policy,
        backend=_lexicon(),
        url=url,
        photo=photo.getvalue() if photo is not None else None,
        consent=consent,
    )

# --- neither channel produced anything ------------------------------------
if not profile and not profile.face_measured:
    st.error(f"**{plain.MATCHDAY_NOTHING}** {profile.transcript_detail}")
    if profile.face_detail:
        st.caption(profile.face_detail)
    st.caption(plain.PAGE2_REJECTED_WHY)
    st.stop()

# --- a face, but no words --------------------------------------------------
if not profile:
    st.info(profile.transcript_detail)
    st.caption(profile.face_stamp)
    st.error(f"**{plain.FACE_CUES_HEADLINE}.** {plain.FACE_CUES_LIMITATION}")
    st.markdown(f"## {plain.FACE_ONLY_HEADLINE}")
    st.markdown(theme.lede(plain.FACE_ONLY_PLAIN), unsafe_allow_html=True)
    figure, cues = st.columns([1, 2])
    with figure:
        st.markdown(
            f'<div class="hero-figure"><span class="hl">Face-only figure</span>'
            f'<span class="hv">{profile.face_only_100}</span>'
            f'<span class="hl">out of 100, ranking only</span></div>',
            unsafe_allow_html=True,
        )
    with cues:
        for column, (name, value) in zip(
            st.columns(max(len(profile.face_features), 1)),
            sorted(profile.face_features.items()),
            strict=False,
        ):
            with column:
                st.markdown(
                    f'<div class="widget"><span class="wl">{name.replace("_", " ")}</span>'
                    f'<span class="wv" style="font-size:32px">{value:.2f}</span>'
                    f'<span class="wu">weight '
                    f"{profile.face_weights.get(name, 0.0):+.2f}</span></div>",
                    unsafe_allow_html=True,
                )
    st.error(FACE_ONLY_STAMP)
    st.stop()

# --- both channels, or words alone ----------------------------------------
view = profile.view
score = score_from_view(view)

st.success(
    f"Read {plain.MATCHDAY_READ_BY.format(route=profile.transcript.route)} "
    f"({profile.transcript.segments} segments). "
    f"{profile.replacements} name-like item(s) replaced before scoring."
)
st.caption(profile.transcript.stamp)
if profile.face_measured:
    st.caption(profile.face_stamp)
    st.error(f"**{plain.FACE_CUES_HEADLINE}.** {plain.FACE_CUES_LIMITATION}")
else:
    st.info(profile.face_detail or plain.MATCHDAY_NO_FACE)

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
    if profile.face_measured:
        st.caption(
            f"{plain.FACE_COMBINED_LABEL}: {profile.score_100}. "
            f"{plain.FACE_TEXT_ONLY_LABEL}: {profile.text_only_100}. "
            "The difference is what the face contributed."
        )
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

if profile.face_measured:
    st.markdown("## What the face contributed")
    for column, (name, value) in zip(
        st.columns(max(len(profile.face_features), 1)),
        sorted(profile.face_features.items()),
        strict=False,
    ):
        with column:
            weight = profile.face_weights.get(name, 0.0)
            st.markdown(
                f'<div class="widget{"" if weight else " is-inert"}">'
                f'<span class="wl">{name.replace("_", " ")}</span>'
                f'<span class="wv" style="font-size:32px">{value:.2f}</span>'
                f'<span class="wu">'
                f"{f'weight {weight:+.2f}' if weight else 'shown, weighted as zero'}"
                f"</span></div>",
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
    if profile.face_measured:
        st.markdown(f"- {profile.face_stamp}")
        st.markdown(f"- {plain.FACE_CUES_LIMITATION}")
        st.markdown(
            "- Facial cue weights, declared and not learned: "
            + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(profile.face_weights.items()))
        )
    st.markdown(f"- {plain.RELEVANCE_MEASURED}")
    st.markdown(f"- {score.band.describe()}")
    st.markdown(f"**{view.risk.stamp}**")
