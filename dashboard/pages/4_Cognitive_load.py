"""Page 4, cognitive load from a simulated body. A renderer, and nothing else.

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

**Nothing here is a recording.** Every trace comes from `SimulatedCardioOculoSource`,
which cannot emit a window without a provenance stamp, and the page routes the
source through `require_simulated()` before it draws anything. That guard is the
ethics gate: the moment a real strap or a real webcam is wired in, `docs/ethics.md`
and `docs/model_card.md` have to be updated first. Do not weaken it.

The load meter carries "ranking only, not calibrated" and has no bands, for the
same reason `charts.py::risk_meter` refuses to band the risk index: a threshold
nothing in this project could set reads as a verdict about whoever the trace
belonged to.

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

st.set_page_config(page_title="Cognitive load", layout="wide")

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

from src.dashboard import narration, plain  # noqa: E402
from src.dashboard.biosources import (  # noqa: E402
    SimulatedCardioOculoSource,
    require_simulated,
)
from src.dashboard.neurovis import (  # noqa: E402
    load_height,
    load_panel,
    narrated_height,
    narrated_panel,
)
from src.dashboard.view import build_view, known_examples  # noqa: E402
from src.dashboard.widgets import load_widget  # noqa: E402

mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

WINDOWS = 12


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
def _source():
    """One seeded source for the session, so the page redraws identically.

    Routed through the ethics gate here rather than at render time: a guard that
    runs after the data is on screen has already failed.
    """
    return require_simulated(SimulatedCardioOculoSource(seed=20260913))


source = _source()
windows = source.stream(WINDOWS)
window = windows[0]

st.markdown('<p class="mono-label">Cognitive layer · V3</p>', unsafe_allow_html=True)

# Above the fold, outside anything collapsible.
st.caption(window.stamp)
st.caption(plain.LOAD_NOT_CALIBRATED)

tile = load_widget(window)
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

# ---------------------------------------------------------------------------
# The narrated clip: a voice, and a simulated body that follows what it says.
#
# The coupling runs TEXT -> BODY and this code draws it. That is not the
# text<->physiology concordance item, which asks the opposite question about two
# measured channels and is deferred to a second paper; see
# src/dashboard/narration.py. The panel states the direction on its own surface.
# ---------------------------------------------------------------------------


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


try:
    clips = narration.load_manifest()
except narration.NarrationMissing:
    clips = ()
    st.warning(plain.NARRATED_MISSING)

if clips:
    replay = _replay()
    spoken = st.selectbox(
        "Clip",
        [c.record_id for c in clips],
        format_func=lambda rid: narration.clip_for(rid).text,
        key="narration_clip",
    )
    spoken_view = build_view(example_id=spoken, backend=replay)
    clip = narration.clip_for(spoken)
    session = narration.narrated_windows(spoken_view, clip, source)
    components.html(
        narrated_panel(session, clip, mode=mode),
        height=narrated_height(session),
        scrolling=False,
    )

st.markdown("---")

components.html(
    load_panel(window, mode=mode, frames=windows),
    height=load_height(window),
    scrolling=False,
)

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.LOAD_WHAT_IT_IS_NOT}")
    st.markdown(f"- {plain.LOAD_WEIGHTS_NOTE}")
    st.markdown(f"**{window.stamp}**")
