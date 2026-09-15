"""The dashboard's only door onto `src/biosignals`. Import seam, nothing else.

Why this module exists
----------------------
`tests/test_dashboard_pages.py` forbids any file under `dashboard/` from
importing anything under `src.` except `src.dashboard`, and the reason is
written into that test: a page that can reach the rest of the project is a page
where business logic migrates into the file the Streamlit runtime executes, and
a property enforced inside a Streamlit callback is a property no test can
assert. Pages 4 and 5 need a biosignal source, so the seam comes to them.

It re-exports rather than wraps. There is no adaptation here, no defaulting and
no convenience construction, because every one of those would be logic sitting
between the guard and the thing it guards -- and `require_simulated` is the
guard that must not have anything sitting in front of it.

The import is at module scope and that is deliberate: this module is only ever
imported by a page that has already passed its `SRN_COGNITIVE_LAYER` check and
called `st.stop()` otherwise, so with the flag unset nothing here loads and
`src/biosignals` is never touched. `tests/test_dashboard_pages.py` asserts that
ordering on the page sources rather than trusting it.
"""

from __future__ import annotations

from src.biosignals import (
    LOAD_WEIGHTS,
    BiosignalWindow,
    EthicsGateError,
    NeurofeedbackSession,
    SessionState,
    SimulatedCardioOculoSource,
    SimulatedEEGSource,
    SimulatedSource,
    require_simulated,
)

__all__ = [
    "LOAD_WEIGHTS",
    "BiosignalWindow",
    "EthicsGateError",
    "NeurofeedbackSession",
    "SessionState",
    "SimulatedCardioOculoSource",
    "SimulatedEEGSource",
    "SimulatedSource",
    "require_simulated",
]
