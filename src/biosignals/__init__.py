"""Phase 26: simulated biosignal sources and the pure features over them.

Nothing in this package measures anybody
----------------------------------------
Every window it emits was generated from a seed. Every window says so, in a
sentence it cannot be constructed without. See `sources.py` for the two guards
and for the blocking ethics gate that must be cleared before any real
physiological signal from any person -- including the repository owner's own --
reaches this code.

Shape borrowed wholesale from `src/dashboard/`, because it worked there: a
`Protocol` for the seam, frozen dataclasses with guards in `__post_init__`, and
pure functions that a test can check against arithmetic done on paper. No
Streamlit import, no ML stack, no I/O.

This package is imported only when `SRN_COGNITIVE_LAYER` is set. The three
cognitive pages check that environment variable and stop before their first
`src.` import, so with the flag unset nothing here is ever loaded and the
dashboard behaves exactly as it did in Phase 24.
"""

from src.biosignals.features import (
    HF_BAND,
    LOAD_WEIGHTS,
    band_power,
    blink_rate,
    hf_hrv,
    load_index,
    pupil_effort,
)
from src.biosignals.sources import (
    SIMULATED_STAMP,
    SIMULATED_TOKEN,
    BiosignalSource,
    BiosignalWindow,
    EthicsGateError,
    NarratedSession,
    SimulatedCardioOculoSource,
    SimulatedSource,
    require_simulated,
)

__all__ = [
    "SIMULATED_STAMP",
    "HF_BAND",
    "LOAD_WEIGHTS",
    "SIMULATED_TOKEN",
    "BiosignalSource",
    "BiosignalWindow",
    "EthicsGateError",
    "NarratedSession",
    "SimulatedCardioOculoSource",
    "SimulatedSource",
    "band_power",
    "blink_rate",
    "hf_hrv",
    "load_index",
    "pupil_effort",
    "require_simulated",
]
