"""Evaluation harness -- honest metrics, honest splits, honest baselines.

Built at Phase 7 rather than Phase 18 because OPEN-012 is a *corpus* property,
and the corpus was built at Phase 7. Waiting until the evaluation phase to
discover that held-out F1 is inflated would mean discovering it after the
modelling decisions had already been made on the strength of that number.

Three pieces:

* `metrics`   -- multi-label P/R/F1, bootstrap CIs, paired significance tests.
* `splits`    -- template-disjoint splitting and leakage measurement.
* `baselines` -- majority, stratified-random, and lexicon floors.

All pure Python. No numpy, no scikit-learn, no network, no cost.
"""

from .baselines import (
    ALL_BASELINES,
    CONSTRUCT_CUES,
    Baseline,
    LexiconBaseline,
    MajorityBaseline,
    MemorisationProbe,
    StratifiedRandomBaseline,
)
from .metrics import (
    PRF,
    Interval,
    bootstrap_ci,
    macro_f1,
    micro_f1,
    paired_bootstrap_p_value,
    per_label_prf,
    subset_accuracy,
)
from .splits import (
    LeakageReport,
    Split,
    leakage_report,
    random_split,
    template_disjoint_split,
    templates_of,
)

__all__ = [
    "ALL_BASELINES",
    "CONSTRUCT_CUES",
    "PRF",
    "Baseline",
    "Interval",
    "LeakageReport",
    "LexiconBaseline",
    "MajorityBaseline",
    "MemorisationProbe",
    "Split",
    "StratifiedRandomBaseline",
    "bootstrap_ci",
    "leakage_report",
    "macro_f1",
    "micro_f1",
    "paired_bootstrap_p_value",
    "per_label_prf",
    "random_split",
    "subset_accuracy",
    "template_disjoint_split",
    "templates_of",
]
