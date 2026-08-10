"""Evaluation harness -- honest metrics, honest splits, honest baselines.

Built at Phase 7 rather than Phase 18 because OPEN-012 is a *corpus* property,
and the corpus was built at Phase 7. Waiting until the evaluation phase to
discover that held-out F1 is inflated would mean discovering it after the
modelling decisions had already been made on the strength of that number.

Three pieces:

* `metrics`   -- multi-label P/R/F1, bootstrap CIs, paired significance tests.
* `splits`    -- template-disjoint splitting and leakage measurement.
* `baselines` -- majority, stratified-random, and lexicon floors.
* `profile`   -- Phase 9 corpus profiling over `data/interim/`.
* `sampling`  -- Phase 9 gold-set sampling plan for Phase 11.
* `figures`   -- hand-written SVG charts (no matplotlib; see the module docstring).

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
from .figures import bar_chart, grouped_bar_chart, histogram_chart
from .metrics import (
    PRF,
    Interval,
    bootstrap_ci,
    bootstrap_statistic,
    macro_f1,
    micro_f1,
    paired_bootstrap_p_value,
    per_label_prf,
    proportion_ci,
    subset_accuracy,
)
from .profile import (
    CorpusProfile,
    Distribution,
    DuplicateProfile,
    GeneratorMetadataProfile,
    JunkProfile,
    VocabularyStats,
    duplicate_profile,
    junk_flags,
    load_interim,
    mattr,
    profile_corpus,
    time_band,
    vocabulary,
)
from .sampling import (
    GoldSample,
    GoldSamplingPlan,
    TemplatePartition,
    build_plan,
    construct_stratified_template_partition,
    draw_gold_sample,
    eligible_utterances,
    write_candidates,
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
    "Baseline",
    "CONSTRUCT_CUES",
    "CorpusProfile",
    "Distribution",
    "DuplicateProfile",
    "GeneratorMetadataProfile",
    "GoldSample",
    "GoldSamplingPlan",
    "Interval",
    "JunkProfile",
    "LeakageReport",
    "LexiconBaseline",
    "MajorityBaseline",
    "MemorisationProbe",
    "PRF",
    "Split",
    "StratifiedRandomBaseline",
    "TemplatePartition",
    "VocabularyStats",
    "bar_chart",
    "bootstrap_ci",
    "bootstrap_statistic",
    "build_plan",
    "construct_stratified_template_partition",
    "draw_gold_sample",
    "duplicate_profile",
    "eligible_utterances",
    "grouped_bar_chart",
    "histogram_chart",
    "junk_flags",
    "leakage_report",
    "load_interim",
    "macro_f1",
    "mattr",
    "micro_f1",
    "paired_bootstrap_p_value",
    "per_label_prf",
    "profile_corpus",
    "proportion_ci",
    "random_split",
    "subset_accuracy",
    "template_disjoint_split",
    "templates_of",
    "time_band",
    "vocabulary",
    "write_candidates",
]
