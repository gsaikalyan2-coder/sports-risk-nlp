"""Page 5, closed-loop neurofeedback, DEMO MODE. A renderer, and nothing else.

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

**This is the one feature here that is an intervention, not an observation.**
A closed feedback loop changes the behaviour of the person inside it. In this
phase the loop closes against a generated signal and trains nobody, and the page
refuses to render for anything that is not a `SimulatedSource`, the guard is
`require_simulated()`, called before the source is used for anything.

# BLOCKED UNTIL ETHICS SIGN-OFF
Before this runs against any person it needs ethics approval and a clinician in
the loop, and `docs/ethics.md` and `docs/model_card.md` updated first. Do not
weaken, comment out or "temporarily" bypass the guard below.

The demo-mode banner is rendered before the first control, both on this shell
and inside the panel, the same ordering rule as the provenance stamp, for the
same reason: a warning below the fold is in the DOM and not on the screen.

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

st.set_page_config(page_title="Neurofeedback (demo)", layout="wide")

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

from src.dashboard import plain  # noqa: E402
from src.dashboard.biosources import (  # noqa: E402
    NeurofeedbackSession,
    SimulatedEEGSource,
    require_simulated,
)
from src.dashboard.neurovis import neurofeedback_height, neurofeedback_panel  # noqa: E402
from src.dashboard.widgets import neurofeedback_widget  # noqa: E402

mode = st.session_state.get("mode", theme.DEFAULT_MODE)
st.markdown(theme.app_css(mode), unsafe_allow_html=True)

TICKS = 48


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
    """The ethics gate, called before the source is used for anything."""
    return require_simulated(SimulatedEEGSource(seed=20260913))


source = _source()
ratios = [w.features["alpha_theta_ratio"] for w in source.stream(TICKS)]

# The target is the median of the generated ratios, and it is a DISPLAY choice,
# not a finding: it puts the ring either side of its reference often enough to
# show the mechanism. Nothing in this project could set a real one, and a real
# session would set it per participant with a clinician present.
target = sorted(ratios)[len(ratios) // 2]
session = NeurofeedbackSession(target=target, tick_s=1.0)

# Banner before any control on this shell too, not only inside the panel.
st.error(plain.NF_DEMO_ONLY)

st.markdown('<p class="mono-label">Cognitive layer · V5</p>', unsafe_allow_html=True)
st.caption(source.stamp)

tile = neurofeedback_widget(session, ratios, stamp=source.stamp)
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
    neurofeedback_panel(session, ratios, mode=mode, stamp=source.stamp),
    height=neurofeedback_height(session),
    scrolling=False,
)

with st.expander("Provenance and limitations: read before quoting anything here"):
    st.markdown(f"- {plain.NF_ETHICS_GATE}")
    st.markdown(f"**{source.stamp}**")
