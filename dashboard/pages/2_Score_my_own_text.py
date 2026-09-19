"""Page 2 -- score a piece of text and read the result.

The score is the project's risk index multiplied by 100, and the band is a third
of that scale. Both come from `src.dashboard.bands`, whose docstring records why
a band is allowed here at all and why it can never reach a paper figure: the
band is constructed with a mandatory caveat and is only ever rendered through
`Band.describe()`, which emits the caveat with it.

Pasted text is the reader's own. It is scored, shown back, and dropped: no
store, no log, no cache, and the view it produces is marked non-exportable by
the publication guard, so it cannot become a figure.
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
    POLICY_TILE_NOTE,
    LexiconBackend,
    admit,
    build_view,
    evidence_height,
    face_stack_status,
    motion_panel,
    panel_height,
    plain,
    read_upload,
    score_from_view,
    scorer_for,
    spans_panel,
    theme,
    widgets_for,
)

st.set_page_config(page_title="Score my own text", layout="wide")
# This page, and only this page, runs the Claude design language
# (DESIGNclaude.md): serif display, coral CTA, warm surfaces. It follows the
# reader's light/dark choice from the dashboard, expressed in *its* tokens --
# the cream canvas becomes surface-dark #181715, the cream cards become
# surface-dark-elevated #252320, the text roles invert to on-dark. The coral CTA
# does not move: it is the brand voltage on both surfaces.
# The control is repeated here rather than only on the dashboard, because a
# reader can land on this page first. It reads and writes the same plain session
# key, so the two pages stay in step in both directions.
mode = st.sidebar.radio(
    "Appearance",
    ("light", "dark"),
    index=("light", "dark").index(st.session_state.get("mode", theme.DEFAULT_MODE)),
    format_func=str.capitalize,
    horizontal=True,
    key="appearance_choice_score",
)
st.session_state["mode"] = mode
CLAUDE_MODE = "claude-dark" if mode == "dark" else "claude"
st.markdown(theme.claude_css(mode), unsafe_allow_html=True)


@st.cache_resource
def _lexicon():
    return LexiconBackend()


st.markdown(f'<div class="announcement">{plain.ANNOUNCEMENT}</div>', unsafe_allow_html=True)
st.markdown('<p class="mono-label">Live scoring</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.PAGE2_TITLE}")
st.markdown(theme.claude_lede(plain.PAGE2_LEDE), unsafe_allow_html=True)

pasted = st.text_area(
    "Text",
    height=160,
    key="pasted_text",
    placeholder="Type or paste a few sentences an athlete wrote before a competition…",
)
# Photo / video, as an alternative source of the same words.
#
# `read_upload` is the one door to `src.media`: this file may import from
# `src.dashboard` and from nowhere else under `src.`, which the page-shell tests
# enforce, and routing the media layer through `src/dashboard/mediaio.py` keeps
# that true rather than making an exception for one feature.
uploaded = st.file_uploader(
    plain.MEDIA_UPLOAD_LABEL,
    type=["png", "jpg", "jpeg", "gif", "webp", "mp4", "mov", "m4v", "webm"],
    key="uploaded_media",
    help=plain.MEDIA_PLAIN,
)

# Phase 28: consent, not a preference switch.
#
# Ticking this is what allows anything to look at a face, and it is phrased as a
# statement of fact about the file rather than as a feature toggle, because that
# is what it has to be: the uploader is asserting that the person shown agreed.
# Unticked, `read_upload` never constructs a `FaceCueReader` and the simulated
# reading is carried at zero weight exactly as in Phase 27.
consent = st.checkbox(
    plain.CONSENT_LABEL,
    value=False,
    key="face_consent",
    help=plain.CONSENT_PLAIN,
)
st.caption(plain.CONSENT_PLAIN)
_stack = face_stack_status()
if consent and not _stack:
    st.warning(_stack.detail)

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

# Where the words come from. A file wins when one is attached, because
# attaching a file is the more deliberate act; the text box is left alone rather
# than cleared, so switching back costs nothing.
media = (
    read_upload(uploaded.name, uploaded.getvalue(), consent=consent)
    if uploaded is not None
    else None
)
media_context: dict[str, float] = dict(media.context) if media is not None else {}
# The weights come from the RESULT, not from the page. A page that decided the
# weights itself could weight a reading that was never taken; this way an empty
# mapping is the direct consequence of no face having been read.
media_weights: dict[str, float] = dict(media.context_weights) if media is not None else {}

if media is not None and not media and media.face_only:
    # A photograph of an athlete carrying no writing. There is no risk index
    # here and there never can be -- the index is ten constructs found in words
    # -- so this branch renders a different object entirely: two cues, one
    # figure derived from them, its own stamp, and no tiles or spans beside it.
    st.info(media.detail)
    # The stamp goes above the figure, never only inside the expander below:
    # tests/test_dashboard_pages.py enforces the ordering, and the reason it
    # exists is that a stamp in a collapsed section is in the DOM and not on the
    # screen, so a screenshot loses it.
    st.caption(media.stamp)
    st.error(f"**{plain.FACE_CUES_HEADLINE}.** {plain.FACE_CUES_LIMITATION}")
    st.markdown(f"## {plain.FACE_ONLY_HEADLINE}")
    st.markdown(theme.claude_lede(plain.FACE_ONLY_PLAIN), unsafe_allow_html=True)
    figure, cues = st.columns([1, 2])
    with figure:
        st.markdown(
            f'<div class="hero-figure"><span class="hl">Face-only figure</span>'
            f'<span class="hv">{round(media.face_index * 100)}</span>'
            f'<span class="hl">out of 100, ranking only</span></div>',
            unsafe_allow_html=True,
        )
    with cues:
        for column, (name, value) in zip(
            st.columns(len(media_weights)),
            sorted((k, v) for k, v in media_context.items() if k in media_weights),
            strict=False,
        ):
            with column:
                st.markdown(
                    f'<div class="widget"><span class="wl">{name.replace("_", " ")}</span>'
                    f'<span class="wv" style="font-size:32px">{value:.2f}</span>'
                    f'<span class="wu">weight {media_weights[name]:+.2f}</span></div>',
                    unsafe_allow_html=True,
                )
    st.caption(media.nonverbal_stamp)
    st.error(FACE_ONLY_STAMP)
    with st.expander("Provenance and limitations: read before quoting this figure"):
        st.markdown(f"- {FACE_ONLY_STAMP}")
        st.markdown(f"- {plain.FACE_CUES_LIMITATION}")
        st.markdown(f"- Read from **{uploaded.name}** by {media.method or 'the face reader'}.")
        st.markdown(f"- {media.stamp}")
    st.stop()

if media is not None and not media:
    # Refused by one of the four gates in mediaio.read_upload. No view has been
    # constructed, so there is no number to show and none is shown.
    st.error(f"**{plain.MEDIA_REJECTED}** {media.detail}")
    st.caption(plain.PAGE2_REJECTED_WHY)
    if media.face_detail:
        st.caption(media.face_detail)
    st.stop()

source_text = media.text if media is not None else pasted

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

view = build_view(
    text=source_text,
    backend=_lexicon(),
    scorer=scorer_for(policy, context_weights=media_weights),
    context=media_context,
)
score = score_from_view(view)

# The text-only score, computed alongside whenever the face moved the index.
#
# Shown rather than described: "the face raised this by 4 points" is a claim the
# reader can check only if both numbers are on the page, and the difference is
# the single most important thing to be able to see on a page where a picture
# now changes a psychological number.
text_only_score = None
if media_weights:
    text_only_score = score_from_view(
        build_view(text=source_text, backend=_lexicon(), scorer=scorer_for(policy))
    )

if media is not None:
    st.info(f"Read from **{uploaded.name}** by {media.method}. {plain.MEDIA_MACHINE_READ}")
    st.caption(media.stamp)
st.markdown(f"> {source_text}")

# Register, shown loudly and beside the number rather than instead of it.
#
# The owner's decision (2026-09-15) was to score off-register text and flag it,
# not to refuse it -- and that is the harder thing to get right, because a
# warning has to survive being screenshotted next to the figure it qualifies.
# So it renders above the score, outside any expander, in the error style, in the
# same position the policy warning uses for the same reason.
if media is not None and not media.on_topic:
    st.error(f"**{plain.OFF_TOPIC_HEADLINE}** {media.relevance_detail}")
    st.caption(plain.OFF_TOPIC_PLAIN)
# The limitation docs/ethics.md sec.14 requires beside every face-derived number,
# in the error style, above the score, outside any expander: the same position
# and the same reason as the register flag.
if media is not None and media.face_measured:
    st.error(f"**{plain.FACE_CUES_HEADLINE}.** {plain.FACE_CUES_LIMITATION}")
elif media is not None and media.face_detail:
    st.warning(media.face_detail)

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
    if text_only_score is not None:
        st.caption(
            f"{plain.FACE_COMBINED_LABEL}: {score.score_100}. "
            f"{plain.FACE_TEXT_ONLY_LABEL}: {text_only_score.score_100}. "
            "The difference is what the face contributed."
        )
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

if media is not None and media_context:
    st.markdown("## The non-verbal reading")
    st.caption(plain.FACE_CUES_MEASURED if media.face_measured else plain.FACE_CUES_NOT_MEASURED)
    for column, (name, value) in zip(
        st.columns(len(media_context)), sorted(media_context.items()), strict=False
    ):
        with column:
            st.markdown(
                f'<div class="widget{"" if name in media_weights else " is-inert"}">'
                f'<span class="wl">{name.replace("_", " ")}</span>'
                f'<span class="wv" style="font-size:32px">{value:.2f}</span>'
                f'<span class="wu">'
                f"{'moved the score' if name in media_weights else 'shown, weighted as zero'}"
                f"</span></div>",
                unsafe_allow_html=True,
            )
    st.caption(media.nonverbal_stamp)

with st.expander("Provenance and limitations: read before quoting any number"):
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {plain.SCALE_NOTE_TEXT}")
    st.markdown(f"- {score.band.describe()}")
    if media is not None:
        st.markdown(f"- {media.stamp}")
        st.markdown(f"- {media.nonverbal_stamp}")
        if media.face_measured:
            st.markdown(f"- {plain.FACE_CUES_LIMITATION}")
            st.markdown(
                "- Facial cue weights, declared and not learned: "
                + ", ".join(f"{k} {v:+.2f}" for k, v in sorted(media_weights.items()))
            )
        st.markdown(f"- {plain.RELEVANCE_MEASURED}")
        st.markdown(
            f"- Register score for this text: {media.relevance:.2f} "
            f"({'reads as athlete self-report' if media.on_topic else 'does not'})."
        )
    st.markdown(f"**{view.risk.stamp}**")
