"""Phase 13 modelling -- classical baselines and the datasets they train on.

Two modules, and the split between them is the load-bearing part:

* `dataset` -- assembles `(text, label-set)` pairs and, more importantly, owns
  the question of **which labels** and **what a score against them means**. The
  gold source refuses while `data/gold/` is empty rather than falling back to
  silver; the silver source requires an explicit acknowledgement that it
  contains no signal (OPEN-028).
* `classical` -- TF-IDF + one-vs-rest linear classifiers, persisted with the
  seed, library version, feature config and training fingerprint needed to
  reproduce a run.

* `transformer` -- Phase 14's fine-tuned multi-label encoder, behind the same
  `Baseline` interface as the classical models so the gate scores both through
  one harness. Trained against the same planted labels, so it inherits the same
  corpus-property framing: it measures how much of the template grammar a
  pretrained encoder recovers, not how well it detects constructs in athlete
  text.

Unlike `src/evaluation/`, this package **does** depend on scikit-learn
(`requirements-base.txt`). It deliberately does not depend on torch or
transformers at import time -- those arrive with Phase 14 and live in
`requirements-ml.txt`, so the classical baselines stay runnable in the light
Docker image. `transformer.py` imports them lazily inside the functions that
need them, and `TRANSFORMER_IMPORT_ERROR` records why the import failed when it
did, so a caller can distinguish "the ML stack is missing" from "the module is
broken".
"""

from .classical import (
    CLASSICAL_BASELINES,
    DEFAULT_FEATURES,
    LinearSVCBaseline,
    LogisticRegressionBaseline,
    TfidfLinearBaseline,
    training_fingerprint,
)
from .dataset import (
    CONSTRUCTS,
    Dataset,
    NoEvaluableLabels,
    deduplicate,
    load_gold,
    load_planted,
    load_silver,
    planted_labels,
)
from .transformer import (
    DEFAULT_SWEEP,
    HParams,
    MLDependencyMissing,
    TransformerBaseline,
    WeightsUnavailable,
    carve_validation,
    decode_predictions,
    encode_labels,
    positive_weights,
    tune_thresholds,
)

__all__ = [
    "CLASSICAL_BASELINES",
    "CONSTRUCTS",
    "DEFAULT_FEATURES",
    "DEFAULT_SWEEP",
    "Dataset",
    "HParams",
    "LinearSVCBaseline",
    "LogisticRegressionBaseline",
    "MLDependencyMissing",
    "NoEvaluableLabels",
    "TfidfLinearBaseline",
    "TransformerBaseline",
    "WeightsUnavailable",
    "carve_validation",
    "decode_predictions",
    "deduplicate",
    "encode_labels",
    "positive_weights",
    "tune_thresholds",
    "load_gold",
    "load_planted",
    "load_silver",
    "planted_labels",
    "training_fingerprint",
]
