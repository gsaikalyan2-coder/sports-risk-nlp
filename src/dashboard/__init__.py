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
* `charts`   -- SVG marks. Grayscale- and CVD-safe by construction, because these
  become paper figures and `PROJECT_PLAN.md` Phase 24 gates on grayscale
  legibility.

What this package must never do
--------------------------------
Persist anything a user pasted. Label a number "accuracy". Draw ten equal bars.
Re-derive the Phase 17 highlighting. See `handover_phase_19.txt` C2.
"""

from .backend import BackendResult, LexiconBackend, PredictionBackend, ReplayBackend
from .charts import construct_contribution_chart, construct_probability_chart, risk_meter
from .view import (
    FORBIDDEN_SUBSTRINGS,
    ConstructBar,
    DashboardView,
    ScoreSurface,
    assert_no_forbidden_language,
    build_view,
    known_examples,
)

__all__ = [
    "BackendResult",
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
    "known_examples",
    "risk_meter",
]
