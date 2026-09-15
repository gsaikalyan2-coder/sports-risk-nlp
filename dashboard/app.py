"""Page 1 of the dashboard -- the widget grid. A renderer, and nothing else.

Every number, every label and every guard in this file comes from
`src.dashboard`, which is pure Python, imports no ML stack, and is covered by
`tests/test_dashboard.py` and `tests/test_dashboard_pages.py`. Business logic
does not live in the file the Streamlit runtime executes, because a property
enforced inside a Streamlit callback is a property no test can assert -- and
this project has found the same "the check and the thing it protects were
related by assumption" defect in six consecutive phases.

The tests enforce that structurally: this module, and every module under
`dashboard/pages/`, may import from `src.dashboard` and from nowhere else under
`src.`, and may not construct a `DashboardView`, `ExplanationCard` or `CardSet`.

The grid shows values with no explanation, which is the riskiest screen this
project has produced: a number with its provenance stripped is exactly what
`ScoreSurface` exists to prevent. Two things keep it honest -- the PROVISIONAL
stamp is rendered above the grid, before anything collapsible, and every tile
links to its own explanation rather than to a generic help page.

Run:  streamlit run dashboard/app.py
      docker compose up dashboard      (light image, no torch -- see backend.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path before the first `src.` import. `streamlit run
# dashboard/app.py` puts THIS file's directory on sys.path, not the repository
# root, so without these two lines the import below raises ModuleNotFoundError
# in any environment that has not been told the root some other way. Idempotent,
# and a no-op when PYTHONPATH already covers it (as the images now do).
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    POLICY_TILE_NOTE,
    build_view,
    known_examples,
    motion_panel,
    panel_height,
    plain,
    scorer_for,
    theme,
    widgets_for,
)

st.set_page_config(
    page_title="Pre-competition construct profiling",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Light or dark, chosen by the reader and held in session state so the detail
# page opens in the same mode the tile was clicked in. Every colour on both
# surfaces comes from `theme.palette(mode)`, which defines the full token set
# for each mode -- a partial palette is how a dark page ends up with dark text.
# Streamlit garbage-collects a widget's state when that widget is not rendered
# on the current page, so a radio key alone does NOT survive navigation -- the
# reader picked dark, opened Page 2, and got a light page. Found by clicking
# through the running app; the unit tests cannot see session lifetime at all.
# So the choice is copied into a plain (non-widget) key, which does persist, and
# every page reads that.
_choice = st.sidebar.radio(
    "Appearance",
    ("light", "dark"),
    index=("light", "dark").index(st.session_state.get("mode", theme.DEFAULT_MODE)),
    format_func=str.capitalize,
    horizontal=True,
    key="appearance_choice",
)
st.session_state["mode"] = _choice
mode = _choice
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

# Say why the Phase 26 pages are not in the menu, rather than leaving a reader to
# conclude the feature was never built. The layer hides its own nav entries when
# the flag is unset, which is correct and was also, on first contact with a real
# container, indistinguishable from a bug: the pages were on disk, the tests were
# green, and the menu showed two entries. A silent guard gets removed by the next
# person who meets it. Costs one line of sidebar text and only in the off state.
if not theme.cognitive_layer_enabled():
    st.sidebar.caption(
        f"Cognitive layer off: set {theme.COGNITIVE_FLAG}=1 to show the brain atlas, "
        "cognitive load and neurofeedback pages. Everything behind it runs on "
        "generated signals; nobody is recorded in either state."
    )

# The policy the reader chose, held in a plain (non-widget) session key.
#
# Streamlit garbage-collects a widget's state when that widget is not rendered on
# the current page, so a selectbox key alone does NOT survive navigation: the
# reader set "Pessimistic" on the dashboard, opened Score my own text, and was
# silently scored under the conservative default. That is the same defect the
# light/dark control already had, and it is worse here, because the two pages
# then disagreed about which assumption produced their numbers. Same fix: the
# choice is copied into a plain key, and every page reads and writes that.
POLICY_STATE_KEY = "policy_label_shared"

DETAIL_PAGE = "pages/1_Signal_detail.py"


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
# Nothing is lost here: reading the fixture is a 19 KB JSON parse.
def _replay():
    return known_examples()


def _announcement() -> None:
    """The black strip, with the close control DESIGNcohere.md specifies for it.

    The component was always documented as dismissible -- "centred microcopy with
    an underlined link and a close control at the far right" -- and shipped
    without the control, so it sat permanently across the top of every screen.
    Closing it is per-session and does not persist, so the next visitor sees it
    once. The same wording is in the provenance expander at the foot of the page
    and in `docs/ethics.md`; this strip is the reminder, not the record.
    """
    if st.session_state.get("announcement_closed"):
        return
    bar, close = st.columns([20, 1])
    with bar:
        st.markdown(f'<div class="announcement">{plain.ANNOUNCEMENT}</div>', unsafe_allow_html=True)
    with close:
        st.button("✕", key="close_announcement", help="Dismiss for this session")
    if st.session_state.get("close_announcement"):
        st.session_state["announcement_closed"] = True
        st.rerun()


def _open_detail(construct: str) -> None:
    """Route to the detail page for one construct.

    The construct key is written to session state rather than passed as free
    text, so a tile cannot open the explanation of a different signal.
    """
    st.session_state["detail_construct"] = construct


_announcement()

st.markdown('<p class="mono-label">Pre-competition construct profiling</p>', unsafe_allow_html=True)
st.markdown(f"# {plain.PAGE1_TITLE}")
st.markdown(theme.lede(plain.PAGE1_LEDE), unsafe_allow_html=True)

replay = _replay()
controls_left, controls_right = st.columns([1, 1])
with controls_left:
    choice = st.selectbox(
        "Committed known example",
        replay.example_ids,
        key="example_id",
    )
with controls_right:
    policy = st.selectbox(
        "How should the four two-sided signals be counted?",
        list(POLICY_LABELS),
        index=list(POLICY_LABELS).index(
            st.session_state.get(POLICY_STATE_KEY, DEFAULT_POLICY_LABEL)
        ),
        key="policy_label",
        help=(
            "Four of the ten signals can be good news or bad news depending on which way "
            "they point. The default refuses to guess and counts them as zero."
        ),
    )

st.session_state[POLICY_STATE_KEY] = policy

view = build_view(example_id=choice, backend=replay, scorer=scorer_for(policy))
st.markdown(f"> {replay.get(choice).text}")

# Above the fold and outside anything collapsible. A stamp inside a collapsed
# expander is present in the DOM and absent from the screen -- and from every
# screenshot that becomes a paper figure.
# The PROVISIONAL stamp is NOT rendered here.
#
# Removed from above the fold on the owner's explicit instruction, 2026-09-14,
# after the consequence was put to him in writing. It still renders in the
# "Provenance and limitations" expander at the foot of this page, it is still
# required by `ScoreSurface.__post_init__` (a number in this project cannot be
# constructed without it), and it is still rendered above the fold on every
# other page.
#
# What is lost is specific and worth naming: Phase 26 gate #3 -- "no simulated
# surface renders without its provenance stamp" -- no longer holds for page 1,
# and a screenshot of the risk index taken from this page now travels without
# the sentence that says the number is agreement with planted labels and is
# not accuracy. `tests/test_dashboard_pages.py` records the same thing beside the
# exemption it had to add.

# The policy note is a WARNING when the reader has changed the policy away from
# the conservative default, and an explanation when they have not. Only the
# warning earns a line above the fold; the explanation moved into the provenance
# expander, which is where page 2 already put it. Three stacked grey captions
# above the first number was pushing the content itself below the fold.
if not view.is_default_policy:
    st.error(view.policy_note)

# The hero band carries a *different* number from the panel beside it. Showing
# the risk index in both places was the Phase 20 defect -- the same number twice
# on one screen reads as two findings.
contributing = next(s for s in view.surfaces if s is not view.risk)

hero, meter = st.columns([1, 2])
with hero:
    st.markdown(
        f'<div class="hero-figure"><span class="hl">{contributing.label}</span>'
        f'<span class="hv">{contributing.display}</span>'
        f'<span class="hl">{contributing.detail}</span></div>',
        unsafe_allow_html=True,
    )
with meter:
    components.html(motion_panel(view, mode=mode), height=panel_height(view), scrolling=False)

st.markdown(f"## {plain.PAGE1_GRID_LABEL}")
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
    + " The four two-sided tiles below are the ones it moves."
)

tiles = widgets_for(view)
for row_start in range(0, len(tiles), 3):
    for column, widget in zip(st.columns(3), tiles[row_start : row_start + 3], strict=False):
        with column:
            st.markdown(
                f'<div class="widget{" is-inert" if widget.inert else ""}">'
                f'<span class="wl">{widget.title}</span>'
                f'<span class="wv">{widget.value}</span>'
                f'<span class="wu">{widget.value_caption}</span>'
                f'<hr class="wrule">'
                f'<span class="wv" style="font-size:24px">{widget.secondary}</span>'
                f'<span class="wu">{widget.secondary_caption}</span>'
                "</div>",
                unsafe_allow_html=True,
            )
            st.button(
                plain.PAGE1_OPEN_CTA,
                key=f"open_{widget.construct}",
                on_click=_open_detail,
                args=(widget.construct,),
            )

if st.session_state.get("detail_construct"):
    st.switch_page(DETAIL_PAGE)

with st.expander("Provenance and limitations: read before quoting any number"):
    st.markdown(f"- {plain.ANNOUNCEMENT}")
    st.markdown(f"- {view.policy_note}")
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"- {view.card.provenance}")
    st.markdown(f"- {view.card.risk.provenance}")
    st.markdown(f"**{view.risk.stamp}**")
