"""Statistical and lexicon baselines -- the floor every real model must clear.

Why these exist before any model does
-------------------------------------
"Macro-F1 0.68" means nothing on its own. It means something once you know that
always-predict-the-majority scores 0.11 and a keyword lexicon scores 0.52. The
baselines convert an uninterpretable number into a comparison, and `CLAUDE.md`
sec.9 makes beating them part of publication-readiness.

They are also the cheapest possible defence against the OPEN-012 failure. If a
fine-tuned DeBERTa barely beats a 40-line keyword matcher on a template-disjoint
split, the transformer has learned the template bank and not the constructs.
That is a finding worth having in Week 4 rather than Week 7.

All three are free, deterministic, dependency-free, and run in under a second.
"""

from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from src.ingestion.records import RawRecord

LabelSet = frozenset[str]


class Baseline:
    """Common interface: fit on training records, predict label sets."""

    name = "baseline"

    def fit(self, records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> Baseline:
        raise NotImplementedError

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        raise NotImplementedError


@dataclass
class MajorityBaseline(Baseline):
    """Predict, for every record, exactly the labels that occur in >50% of training.

    Usually predicts the empty set, which is the point: it shows what "always
    say nothing" scores. On an imbalanced multi-label problem that is often a
    surprisingly respectable micro-F1, which is why macro-F1 is the primary
    metric.
    """

    name: str = "majority"
    _predicted: LabelSet = frozenset()

    def fit(self, records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> MajorityBaseline:
        counts: dict[str, int] = {}
        for label_set in labels:
            for label in label_set:
                counts[label] = counts.get(label, 0) + 1
        threshold = len(labels) / 2
        self._predicted = frozenset(k for k, v in counts.items() if v > threshold)
        return self

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        return [self._predicted] * len(records)


@dataclass
class StratifiedRandomBaseline(Baseline):
    """Sample each label independently at its training prevalence.

    The honest "chance" level for multi-label classification. A model that fails
    to beat this has learned nothing. Seeded, so it is reproducible -- an
    unseeded random baseline gives a different floor each run, which makes every
    comparison against it unfalsifiable.
    """

    seed: int = 42
    name: str = "stratified_random"
    _rates: dict[str, float] | None = None

    def fit(
        self, records: Sequence[RawRecord], labels: Sequence[LabelSet]
    ) -> StratifiedRandomBaseline:
        counts: dict[str, int] = {}
        for label_set in labels:
            for label in label_set:
                counts[label] = counts.get(label, 0) + 1
        n = max(1, len(labels))
        self._rates = {k: v / n for k, v in counts.items()}
        return self

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        if self._rates is None:
            raise RuntimeError("fit() before predict()")
        rng = random.Random(self.seed)
        return [
            frozenset(label for label, rate in sorted(self._rates.items()) if rng.random() < rate)
            for _ in records
        ]


#: Keyword cues per construct, drawn from the `positive_examples` and
#: `definition` fields of `config/taxonomy.yaml`. Hand-written on purpose: a
#: lexicon induced from the training labels would inherit the template bank and
#: stop being an independent baseline.
#:
#: **That precaution was not sufficient, and Phase 9b measured how insufficient
#: (OPEN-021).** Avoiding induction from labels prevents *direct* inheritance. It
#: does not prevent **shared ancestry**: `src/ingestion/synthetic.py`'s template
#: bank was also written from `taxonomy.yaml`'s `positive_examples`, and several
#: Phase 7 templates reproduce them close to verbatim. So the cues and the
#: corpus descend from one source, and the lexicon scores well partly because it
#: is matching its own cousin.
#:
#: The number: this cue list fires on **73%** of the pre-Phase-9b templates and
#: **22%** of the Phase 9b templates, which were written to the same construct
#: definitions but deliberately not to the same example phrasings. Nothing about
#: the constructs changed between those two sets. What changed is how much
#: wording they share with this file.
#:
#: Consequences, both of which the paper has to carry:
#:
#: 1. The lexicon's macro-F1 fell 0.780 -> 0.461 on the template-disjoint split
#:    between v1.3 and v1.4. That is not the corpus getting harder in any
#:    meaningful sense; it is this baseline losing an advantage it should never
#:    have been credited with. **0.461 is the more honest floor.**
#: 2. Do not use `LexiconBaseline` as a detector of whether a span expresses a
#:    construct. Phase 9 used it exactly that way, to estimate what fraction of
#:    gold candidates carry construct language, and the estimate was really a
#:    measure of overlap with this list.
CONSTRUCT_CUES: dict[str, tuple[str, ...]] = {
    "cognitive_anxiety": (
        "worried",
        "anxious",
        "uneasy",
        "apprehensive",
        "doubt",
        "wonder",
        "what if",
        "go wrong",
        "fall apart",
        "let everyone down",
        "come up short",
        "replaying",
        "can't stop",
        "cannot stop",
    ),
    "somatic_anxiety": (
        "stomach",
        "gut",
        "knots",
        "shaking",
        "trembling",
        "butterflies",
        "heart",
        "pulse",
        "chest",
        "couldn't sleep",
        "barely slept",
        "sick",
        "hands",
        "tight",
        "heavy",
    ),
    "self_confidence": (
        "i know i",
        "back myself",
        "belong",
        "no doubt",
        "capable",
        "i've beaten",
        "earned this",
        "afraid of",
        "confident",
        "certain",
    ),
    "perceived_stress": (
        "too much",
        "a lot on",
        "can't keep up",
        "cannot keep up",
        "out of my hands",
        "pulled in every direction",
        "pressure",
        "strain",
        "everyone wants",
        "busy",
        "hectic",
        "manage",
    ),
    "burnout_signal": (
        "drained",
        "don't even care",
        "do not even care",
        "used to love",
        "want to finish",
        "no difference",
        "flat",
        "point of the session",
        "hard to care",
        "exhaust",
    ),
    "resilience": (
        "reset",
        "come back",
        "bounce",
        "been behind",
        "worse than this",
        "steady myself",
        "keep going",
        "whatever happens",
    ),
    "motivation_orientation": (
        "want to",
        "take it on",
        "see what i",
        "how good i",
        "don't want to",
        "do not want to",
        "can't afford",
        "cannot afford",
        "embarrass",
        "mess this",
        "not to",
    ),
    "attentional_focus": (
        "all i'm thinking",
        "focus",
        "locked in",
        "dialled in",
        "controllables",
        "control",
        "keep checking",
        "distract",
        "phone",
        "crowd",
        "noise",
        "glancing",
        "pulling me out",
    ),
    "coping_style": (
        "routine",
        "breathing",
        "checklist",
        "talked it through",
        "my coach",
        "write down",
        "avoid",
        "not to think about",
        "rather not talk",
        "switch off",
        "plan for",
    ),
    "appraisal_orientation": (
        "opportunity",
        "test myself",
        "waiting for",
        "that's why i train",
        "way above me",
        "get exposed",
        "step up",
        "not sure i'm ready",
        "not enough for",
        "huge",
    ),
}


@dataclass
class LexiconBaseline(Baseline):
    """Keyword matching against taxonomy-derived cues. No training at all.

    The most informative of the three. It encodes what a careful human could do
    with a word list and no machine learning, so the transformer's margin over
    it is the honest measure of what the modelling actually bought.

    Deliberately unsupervised: `fit` ignores the labels entirely, so this
    baseline is immune to the *label* leakage that inflates the others.

    **It is not independent of the corpus, and Phase 9b proved it (OPEN-021).**
    Ignoring labels prevents direct inheritance; it does not prevent shared
    ancestry. Both this cue list and the template bank were written from
    `taxonomy.yaml`'s `positive_examples`, so they are cousins, and the score
    reflects that relationship as well as any real detection ability. See the
    note on `CONSTRUCT_CUES` for the measurement.

    Treat its score as a floor with a known upward bias, and never as a
    construct detector for corpus-profiling purposes.
    """

    name: str = "lexicon"

    def fit(self, records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> LexiconBaseline:
        return self  # nothing to learn; cues come from the taxonomy

    @staticmethod
    def _matches(text: str, cues: Sequence[str]) -> bool:
        low = text.lower()
        for cue in cues:
            if " " in cue:
                if cue in low:
                    return True
            elif re.search(rf"\b{re.escape(cue)}", low):
                return True
        return False

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        return [
            frozenset(
                construct
                for construct, cues in CONSTRUCT_CUES.items()
                if self._matches(record.text, cues)
            )
            for record in records
        ]


@dataclass
class MemorisationProbe(Baseline):
    """1-nearest-neighbour over training texts by Jaccard token overlap.

    NOT a baseline to beat -- an instrument. It is the cheapest possible
    memoriser: it stores the training set and copies the labels of the most
    lexically similar training example.

    Its purpose is diagnostic. Run it under a random split and under a
    template-disjoint split; the drop between the two is a direct measurement of
    how much of the corpus can be solved by recall alone. `LexiconBaseline`
    cannot serve this role because it never looks at the training labels, so it
    is leakage-immune by construction and reports no gap -- which is exactly what
    the first version of `scripts/run_benchmark_audit.py` did, and why this class
    exists.

    A transformer sits between this probe and the lexicon in capacity. If the
    probe scores near the transformer on a random split, the transformer's
    number is memorisation.
    """

    name: str = "memorisation_probe"
    _train: list[tuple[frozenset[str], LabelSet]] | None = None

    def fit(self, records: Sequence[RawRecord], labels: Sequence[LabelSet]) -> MemorisationProbe:
        self._train = [
            (frozenset(r.text.lower().split()), label)
            for r, label in zip(records, labels, strict=True)
        ]
        return self

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        if self._train is None:
            raise RuntimeError("fit() before predict()")
        out: list[LabelSet] = []
        for record in records:
            tokens = frozenset(record.text.lower().split())
            best_score, best_labels = -1.0, frozenset()
            for train_tokens, train_labels in self._train:
                union = len(tokens | train_tokens)
                score = len(tokens & train_tokens) / union if union else 0.0
                if score > best_score:
                    best_score, best_labels = score, train_labels
            out.append(best_labels)
        return out


ALL_BASELINES: tuple[type[Baseline], ...] = (
    MajorityBaseline,
    StratifiedRandomBaseline,
    LexiconBaseline,
    MemorisationProbe,
)
