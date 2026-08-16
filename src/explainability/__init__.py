"""Phase 17 -- explainability and expert validation.

Four modules, and the split is by what each one needs to run:

* `attribution` -- span-level, construct-specific token attribution
  (Integrated Gradients, SHAP Partition). The **only** module that touches
  torch, and it does so lazily.
* `faithfulness` -- comprehensiveness / sufficiency against a random control,
  plus IG-vs-SHAP agreement. Pure Python; the model enters through a
  `predict_fn` callable.
* `cards` -- joins span->construct attribution to `src/risk/fusion.py`'s
  construct->risk contributions. This is contribution #2's artefact.
* `study` -- the blinded expert-validation instrument and its statistics.

Only `attribution` requires the ML stack, so the other three import in the light
Docker image and are unit-tested without torch installed.

The distinction the whole package rests on: **faithfulness** asks whether the
explanation describes the model, **plausibility** asks whether a human finds it
sensible, and Phase 17 reports both because an explanation can pass either one
alone while being useless.
"""

from .attribution import (
    EXPLANATION_PROVENANCE,
    AttributionUnavailable,
    ConstructExplanation,
    IntegratedGradients,
    RecordExplanation,
    ShapPartition,
    SpanAttribution,
    TokenAttribution,
    merge_into_spans,
    word_spans,
)
from .cards import (
    CardSet,
    ConstructEvidence,
    ExplanationCard,
    PublicationUnsafe,
    assert_publication_safe,
    build_card,
    highlight,
    render_markdown,
)
from .faithfulness import (
    DEFAULT_FRACTIONS,
    FaithfulnessScore,
    MethodAgreement,
    align_to_words,
    compare_methods,
    score_record,
    spearman,
    summarise,
    top_k_jaccard,
)
from .study import (
    ITEM_TYPES,
    SCALE,
    RatingSheet,
    StudyItem,
    StudyResult,
    analyse,
    build_sheet,
    cohens_kappa,
)

__all__ = [
    "AttributionUnavailable",
    "CardSet",
    "ConstructEvidence",
    "ConstructExplanation",
    "DEFAULT_FRACTIONS",
    "EXPLANATION_PROVENANCE",
    "ExplanationCard",
    "FaithfulnessScore",
    "ITEM_TYPES",
    "IntegratedGradients",
    "MethodAgreement",
    "PublicationUnsafe",
    "RatingSheet",
    "RecordExplanation",
    "SCALE",
    "ShapPartition",
    "SpanAttribution",
    "StudyItem",
    "StudyResult",
    "TokenAttribution",
    "align_to_words",
    "analyse",
    "assert_publication_safe",
    "build_card",
    "build_sheet",
    "cohens_kappa",
    "compare_methods",
    "highlight",
    "merge_into_spans",
    "render_markdown",
    "score_record",
    "spearman",
    "summarise",
    "top_k_jaccard",
    "word_spans",
]
