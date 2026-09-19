"""Phase 20 -- the demo layer, and nothing else.

Predicting and rendering are separate programs
----------------------------------------------
This package is the project's default shape applied once more (`src/risk/` at
Phase 15, `src/explainability/` at 17, `src/evaluation/` at 18): every number the
dashboard shows is arithmetic over cached or derived values, computed by pure
Python that imports no ML stack, and `dashboard/app.py` is a rendering shell over
it. That is why the test suite still runs in seconds with no torch installed, and
why the honesty properties in `tests/test_dashboard.py` are testable at all -- a
property enforced inside a Streamlit callback is a property nobody can assert.

Three modules:

* `backend`  -- construct probabilities from somewhere. `ReplayBackend` replays a
  committed fixture derived from `reports/explain/cards.md`; `LexiconBackend`
  scores pasted text with the Phase 13 lexicon baseline, in pure Python. Neither
  touches torch. A `TransformerBackend` would slot in behind the same Protocol
  and is deliberately not built here (C2.7: do not retrain, do not re-tune).
* `view`     -- the honesty layer. `DashboardView` cannot be constructed without
  passing the publication guard, cannot hold an unstamped number, and cannot
  carry forbidden vocabulary. See its module docstring.
* `copy`     -- every plain-English caption on the page, as data, screened by the
  same forbidden-vocabulary guard at import time. Written for a reader with no
  machine-learning background; the technical terms live in its `GLOSSARY`
  rather than in the captions.
* `motion`   -- the animated demo panel, one self-contained HTML document handed
  to `st.components.v1.html`. Renders no number the view does not already carry.
* `charts`   -- SVG marks. Grayscale- and CVD-safe by construction, because these
  become paper figures and `PROJECT_PLAN.md` Phase 24 gates on grayscale
  legibility.

What this package must never do
--------------------------------
Persist anything a user pasted. Label a number "accuracy". Draw ten equal bars.
Re-derive the Phase 17 highlighting. See `handover_phase_19.txt` C2.
"""

from . import copy as plain
from . import theme
from .backend import BackendResult, LexiconBackend, PredictionBackend, ReplayBackend
from .bands import BANDS, Band, PsychologicalScore, band_for, score_from_view
from .benchmarks import (
    PER_CONSTRUCT_CAPTION,
    BenchmarkSet,
    ConstructScore,
    load_benchmarks,
    load_per_construct,
)
from .charts import (
    benchmark_chart,
    construct_contribution_chart,
    construct_probability_chart,
    evidence_coverage_chart,
    per_construct_chart,
    risk_meter,
    risk_waterfall,
)
from .gibberish import TextAdmission, admit
from .matchday import (
    PRESS_STAMP,
    MatchDayProfile,
    build_profile,
    face_stack_status,
    transcript_stack_status,
)
from .mediaio import (
    FACE_ONLY_STAMP,
    FACE_STAMP,
    FACE_WEIGHTS,
    NONVERBAL_STAMP,
    MediaResult,
    media_context_weights,
    read_upload,
)
from .motion import evidence_height, motion_panel, panel_height, spans_panel
from .view import (
    DEFAULT_POLICY_LABEL,
    FORBIDDEN_SUBSTRINGS,
    POLICY_LABELS,
    POLICY_SHORT,
    POLICY_TILE_NOTE,
    ConstructBar,
    DashboardView,
    ScoreSurface,
    assert_no_forbidden_language,
    build_view,
    known_examples,
    scorer_for,
)
from .widgets import Widget, widget_for, widgets_for

__all__ = [
    "widgets_for",
    "admit",
    "read_upload",
    "MediaResult",
    "media_context_weights",
    "NONVERBAL_STAMP",
    "FACE_STAMP",
    "FACE_ONLY_STAMP",
    "FACE_WEIGHTS",
    "face_stack_status",
    "transcript_stack_status",
    "build_profile",
    "MatchDayProfile",
    "PRESS_STAMP",
    "TextAdmission",
    "widget_for",
    "theme",
    "score_from_view",
    "band_for",
    "Widget",
    "PsychologicalScore",
    "Band",
    "BANDS",
    "scorer_for",
    "per_construct_chart",
    "load_per_construct",
    "POLICY_LABELS",
    "POLICY_SHORT",
    "POLICY_TILE_NOTE",
    "PER_CONSTRUCT_CAPTION",
    "DEFAULT_POLICY_LABEL",
    "ConstructScore",
    "BackendResult",
    "BenchmarkSet",
    "benchmark_chart",
    "ConstructBar",
    "DashboardView",
    "FORBIDDEN_SUBSTRINGS",
    "LexiconBackend",
    "PredictionBackend",
    "ReplayBackend",
    "ScoreSurface",
    "assert_no_forbidden_language",
    "build_view",
    "construct_contribution_chart",
    "construct_probability_chart",
    "evidence_coverage_chart",
    "evidence_height",
    "known_examples",
    "load_benchmarks",
    "motion_panel",
    "panel_height",
    "plain",
    "spans_panel",
    "risk_meter",
    "risk_waterfall",
]
