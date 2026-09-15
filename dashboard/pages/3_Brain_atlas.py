"""Page 3, the construct → brain network atlas. A renderer, and nothing else.

Same contract as `dashboard/app.py` and the other pages: every number, label and
guard comes from `src.dashboard`, which is pure Python with no ML stack, and
`tests/test_dashboard_pages.py` enforces that structurally by walking every file
under `dashboard/`. This file computes nothing.

Two things are specific to this page.

**The flag check runs before the first `src.` import.** `.claude.md` §11.3 says
the Phase 26 pages "are not registered" when `SRN_COGNITIVE_LAYER` is unset, but
Streamlit registers every file under `pages/` unconditionally and has no API for
a conditional page. So the rule is split: `theme._cognitive_nav_css()` removes
the menu entry, and the block below stops the page before it imports anything,
which is what actually delivers "`src/biosignals` is never imported". The check
has to precede the imports rather than sit after them, or the import happens and
the guard is decoration.

**The caveat is above the fold and outside anything collapsible.** A brain
graphic is the most over-read object in sports technology. The panel carries
"hypothesised association, not imaging" as its first element and again under the
figure, and this shell puts the provenance stamp above the panel, the same rule
`tests/test_dashboard_pages.py` already applies to the widget grid, for the same
reason: a caveat inside a collapsed expander is in the DOM, absent from the
screen, and absent from every screenshot that becomes a slide.

Run:  SRN_COGNITIVE_LAYER=1 streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo root on sys.path before the first `src.` import -- `streamlit run` puts
# the entry point's directory on sys.path, not the repository root. Idempotent,
# and a no-op where PYTHONPATH already covers it (as the images do).
_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

st.set_page_config(page_title="Brain atlas", layout="wide")

from src.dashboard import theme  # noqa: E402

# The flag gate. `theme` is the single source of truth for what the flag means --
# the page parsed the environment variable itself once, which is two copies of
# one rule and therefore two rules, the shape this repository has found seven
# times. `theme` imports no ML stack and, crucially, does not reach
# `src/biosignals`; that import is below the stop, which is what actually
# delivers "the layer is never loaded when it is off".
#
# The layer is ON unless explicitly disabled. See theme.cognitive_layer_enabled.
if not theme.cognitive_layer_enabled():
    st.title("Cognitive layer: off")
    st.info(
        f"This page is part of the Phase 26 cognitive layer, which is switched off "
        f"because {theme.COGNITIVE_FLAG} is set to a disabling value. Unset it to show "
        "the page. Nothing here measures anybody in either state."
    )
    st.stop()

from src.dashboard import (  # noqa: E402
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    build_view,
    known_examples,
    plain,
    scorer_for,
)
from src.dashboard.neurovis import atlas_height, atlas_panel  # noqa: E402
from src.dashboard.widgets import atlas_widget  # noqa: E402

mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)


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


replay = _replay()

st.markdown('<p class="mono-label">Cognitive layer · V1</p>', unsafe_allow_html=True)

# The same record the dashboard is showing. Read from session state rather than
# offered again here, so the two pages cannot disagree about which text is on
# screen; the selector is a fallback for a reader who opened this page first.
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

# Above the fold, outside anything collapsible.
st.caption(view.risk.stamp)
st.caption(plain.ATLAS_CAVEAT)

tile = atlas_widget(view)
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

# Every committed example, so the panel's Play control has somewhere to go.
# Each frame is a real view over a real fixture record -- the simulation moves
# between states the fixture already contains and invents nothing in between.
frames = tuple(
    build_view(example_id=eid, backend=replay, scorer=scorer_for(policy))
    for eid in replay.example_ids
)

components.html(
    atlas_panel(view, mode=mode, frames=frames),
    height=atlas_height(view),
    scrolling=False,
)

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.ATLAS_WHAT_IT_IS_NOT}")
    st.markdown(f"- {plain.ATLAS_ANCHOR_NOTE}")
    for notice in view.notices:
        st.markdown(f"- {notice}")
    st.markdown(f"**{view.risk.stamp}**")
