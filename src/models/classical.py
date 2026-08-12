"""TF-IDF + linear classifiers -- the bar Phase 14's transformer must clear.

Why classical baselines are worth building properly
---------------------------------------------------
`CLAUDE.md` sec.9 makes "transformer beats classical + lexicon baselines on
macro-F1" part of publication-readiness. That criterion is only meaningful if
the classical baseline was given a fair run. A deliberately weak baseline makes
the transformer look good and makes the paper worse, because the first reviewer
to run `TfidfVectorizer` themselves will find the margin was manufactured.

So these are tuned to be respectable: word and character n-grams, sublinear term
frequency, and both a probabilistic (logistic regression) and a max-margin
(linear SVC) classifier. If a fine-tuned DeBERTa cannot beat this on a
template-disjoint split, that is a finding about the corpus and it should be
reported as one rather than engineered away.

One-vs-rest, written out rather than imported
---------------------------------------------
`sklearn.multiclass.OneVsRestClassifier` would do most of this in one line. It
is not used, for one specific reason: it raises on a label column with a single
class, and a label column with zero positives is a situation this project
actually has. The silver source attests only 6 of 10 constructs
(`src/models/dataset.py`), so four columns are all-negative there. The choices
are to crash, to silently drop those constructs from the label set, or to fit a
constant-zero predictor and let the resulting F1 of 0.0 appear in the table.

The third is the only honest one. Dropping unattested constructs would raise
macro-F1 by shrinking the denominator -- averaging over the 6 constructs that
exist instead of the 10 the taxonomy defines -- which is a real way papers
overstate results, and it would happen silently. `_ConstantZero` makes the
degenerate case explicit, keeps the denominator at 10, and records the affected
labels in the fitted metadata.

Reproducibility is a stored fact, not a hope
--------------------------------------------
Every fitted model persists a sidecar manifest carrying the seed, the scikit-learn
version, the full feature configuration, and a SHA-256 fingerprint of the
training data. The fingerprint covers record IDs, texts and label sets, so a
model reloaded against a mutated corpus can be detected rather than trusted.
`CLAUDE.md` sec.7 asks for a model card per model; this is its machine-readable
half.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sklearn
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion
from sklearn.svm import LinearSVC

from src.evaluation.baselines import Baseline
from src.ingestion.records import RawRecord
from src.models.dataset import CONSTRUCTS, LabelSet

#: Default TF-IDF configuration, named so it can be recorded in the manifest and
#: compared across runs. Word unigrams+bigrams catch construct phrases ("fall
#: apart", "back myself"); character 3-5 grams give some robustness to the
#: morphological variation the Phase 9b synonym substitution introduced.
DEFAULT_FEATURES: dict[str, Any] = {
    "word_ngram_range": (1, 2),
    "word_min_df": 2,
    "char_ngram_range": (3, 5),
    "char_min_df": 3,
    "sublinear_tf": True,
    "lowercase": True,
    "max_features": 200_000,
}


def training_fingerprint(records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> str:
    """SHA-256 over the exact training pairs, in a canonical order.

    Sorted by record ID so the fingerprint is a property of the *set* and not of
    the shuffle. Covers labels as well as texts: the same texts with different
    labels is a different training set, and a fingerprint that missed that would
    certify a model as reproducible while its target had changed underneath it.
    """
    digest = hashlib.sha256()
    for record_id, text, label_set in sorted(
        (r.record_id, r.text, tuple(sorted(ls))) for r, ls in zip(records, labels, strict=True)
    ):
        digest.update(record_id.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
        digest.update("|".join(label_set).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


class _ConstantZero:
    """Predictor for a label column with no positive examples.

    Exists so an unattested construct scores 0.0 in the table instead of
    vanishing from the denominator. See the module docstring.
    """

    def predict(self, features: Any) -> list[int]:
        return [0] * features.shape[0]


def _build_vectorizer(features: dict[str, Any]) -> FeatureUnion:
    """Word + character TF-IDF, unioned.

    A `FeatureUnion` rather than two fitted vectorizers stitched by hand,
    because the union handles the sparse hstack and, more importantly, refits
    both halves identically on reload.
    """
    return FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=tuple(features["word_ngram_range"]),
                    min_df=features["word_min_df"],
                    sublinear_tf=features["sublinear_tf"],
                    lowercase=features["lowercase"],
                    max_features=features["max_features"],
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=tuple(features["char_ngram_range"]),
                    min_df=features["char_min_df"],
                    sublinear_tf=features["sublinear_tf"],
                    lowercase=features["lowercase"],
                    max_features=features["max_features"],
                ),
            ),
        ]
    )


@dataclass
class TfidfLinearBaseline(Baseline):
    """TF-IDF features, one binary linear classifier per construct.

    Subclasses pick the classifier. Everything else -- features, the
    one-vs-rest loop, the degenerate-column handling, persistence -- is shared,
    so a difference between the logistic and SVC rows of the results table is a
    difference in the classifier and nothing else.
    """

    seed: int = 42
    name: str = "tfidf_linear"
    constructs: tuple[str, ...] = CONSTRUCTS
    features: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_FEATURES))

    _vectorizer: Any = None
    _classifiers: dict[str, Any] = field(default_factory=dict)
    _degenerate: tuple[str, ...] = ()
    _fingerprint: str = ""
    _n_train: int = 0

    def _make_classifier(self) -> Any:
        raise NotImplementedError

    def fit(self, records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> TfidfLinearBaseline:
        texts = [r.text for r in records]
        self._vectorizer = _build_vectorizer(self.features)
        matrix = self._vectorizer.fit_transform(texts)

        self._classifiers = {}
        degenerate: list[str] = []
        for construct in self.constructs:
            targets = [1 if construct in label_set else 0 for label_set in labels]
            if len(set(targets)) < 2:
                # Zero positives (or, impossibly here, zero negatives). A linear
                # model has nothing to separate; say so rather than crash.
                self._classifiers[construct] = _ConstantZero()
                degenerate.append(construct)
                continue
            classifier = self._make_classifier()
            classifier.fit(matrix, targets)
            self._classifiers[construct] = classifier

        self._degenerate = tuple(degenerate)
        self._fingerprint = training_fingerprint(records, labels)
        self._n_train = len(records)
        return self

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        if self._vectorizer is None:
            raise RuntimeError(f"{self.name}: fit() before predict()")
        matrix = self._vectorizer.transform([r.text for r in records])
        # Predict per construct, then transpose into per-record label sets.
        columns = {
            construct: list(classifier.predict(matrix))
            for construct, classifier in self._classifiers.items()
        }
        return [
            frozenset(construct for construct in self.constructs if columns[construct][i] == 1)
            for i in range(len(records))
        ]

    def predict_proba(self, records: Sequence[RawRecord]) -> list[dict[str, float]]:
        """Per-construct P(present) for each record. Added for Phase 15.

        The risk layer fuses *probabilities*, not label sets, so it needs a
        source of them. Phase 14's transformer is the intended source; this
        method exists so `src/risk/` is runnable and testable **before** the
        transformer has been trained, which decouples Phase 15 from Phase 14's
        blocked state.

        Three cases, and the middle one is why this is not a one-liner:

        * `LogisticRegression` exposes a genuine `predict_proba`.
        * `LinearSVC` does not, and has no probabilistic interpretation at all.
          Its `decision_function` is a signed margin, not a log-odds, and passing
          it through a sigmoid produces a number that *looks* like a probability
          while being an arbitrary monotone transform of a distance. That is
          returned here -- because a ranked score is still useful to the fusion --
          but it is exactly the situation `src/risk/calibration.py` exists for,
          and an SVC-sourced risk index must not be reported without calibration.
        * `_ConstantZero` columns (a construct with no positive training
          examples) return 0.0, matching the constant-zero prediction rather than
          an undefined value.
        """
        if self._vectorizer is None:
            raise RuntimeError(f"{self.name}: fit() before predict_proba()")
        matrix = self._vectorizer.transform([r.text for r in records])

        columns: dict[str, list[float]] = {}
        for construct, classifier in self._classifiers.items():
            if hasattr(classifier, "predict_proba"):
                # Column 1 is P(positive); sklearn orders classes ascending.
                columns[construct] = [float(row[1]) for row in classifier.predict_proba(matrix)]
            elif hasattr(classifier, "decision_function"):
                from math import exp

                margins = classifier.decision_function(matrix)
                columns[construct] = [
                    1.0 / (1.0 + exp(-max(min(float(m), 700.0), -700.0))) for m in margins
                ]
            else:
                columns[construct] = [0.0] * len(records)

        return [
            {construct: columns[construct][i] for construct in self.constructs}
            for i in range(len(records))
        ]

    # -- persistence --------------------------------------------------------

    def manifest(self) -> dict[str, Any]:
        """Everything needed to judge whether a stored model is the one you want."""
        return {
            "name": self.name,
            "seed": self.seed,
            "sklearn_version": sklearn.__version__,
            "features": {
                k: list(v) if isinstance(v, tuple) else v for k, v in self.features.items()
            },
            "constructs": list(self.constructs),
            "degenerate_constructs": list(self._degenerate),
            "n_train": self._n_train,
            "training_fingerprint": self._fingerprint,
        }

    def save(self, directory: Path) -> Path:
        """Persist the fitted model plus its manifest. Returns the directory."""
        import joblib

        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"vectorizer": self._vectorizer, "classifiers": self._classifiers},
            directory / "model.joblib",
        )
        (directory / "manifest.json").write_text(
            json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return directory


@dataclass
class LogisticRegressionBaseline(TfidfLinearBaseline):
    """L2 logistic regression per construct.

    `class_weight="balanced"` because the constructs are imbalanced (support
    runs 446-885 out of 3,888 records) and an unweighted logistic model on a
    12%-positive column learns to predict zero, which scores well on accuracy
    and 0.0 on F1. Balancing is the standard correction and it is applied to
    both classical models so the comparison stays clean.
    """

    name: str = "tfidf_logreg"
    max_iter: int = 2000

    def _make_classifier(self) -> Any:
        return LogisticRegression(
            max_iter=self.max_iter,
            class_weight="balanced",
            random_state=self.seed,
            # liblinear: deterministic on this problem size and does not depend
            # on BLAS threading, which lbfgs does -- and a score that moves with
            # the thread count is not reproducible in the gate's sense.
            solver="liblinear",
        )


@dataclass
class LinearSVCBaseline(TfidfLinearBaseline):
    """Linear support vector classifier per construct.

    Usually the stronger of the two on short-text TF-IDF, and it produces no
    calibrated probability -- which is fine here, because Phase 13 scores label
    sets. Calibration becomes a requirement at Phase 15 (risk fusion), not now.
    """

    name: str = "tfidf_linearsvc"
    max_iter: int = 5000

    def _make_classifier(self) -> Any:
        return LinearSVC(
            max_iter=self.max_iter,
            class_weight="balanced",
            random_state=self.seed,
            dual=True,
        )


#: Registered in the order they should appear in the results table: trivial
#: floors first, then the lexicon, then the learned classical models.
CLASSICAL_BASELINES: tuple[type[TfidfLinearBaseline], ...] = (
    LogisticRegressionBaseline,
    LinearSVCBaseline,
)
