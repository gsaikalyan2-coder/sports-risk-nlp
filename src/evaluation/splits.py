"""Train/test splitting, and the leakage measurement that justifies it.

The problem this module exists to solve
---------------------------------------
`data/raw/synth_precomp_v1` is generated from a template bank
(`src/ingestion/synthetic.py`). Under a **random** split, the same template
appears in both train and test — differing only in slot fillers and near-synonym
substitutions. A model can then score highly on held-out data by recognising
"I cannot stop thinking about all the ways this could fall apart" as a string it
has already seen labelled, without having learned anything about
`cognitive_anxiety`.

That is OPEN-012. The resulting F1 is not merely optimistic; it measures a
different quantity from the one the paper claims to report.

The fix
-------
**Template-disjoint splitting.** Partition the *templates* first, then assign
records. A record goes to test only if every template it uses is a test
template. A model evaluated this way has never seen the phrasings it is tested
on, so its score reflects generalisation across realisations of a construct —
which is the quantity of interest.

Records whose templates straddle the partition are **discarded**, not quietly
assigned. Assigning them to train would leak test templates into training;
assigning them to test would put trained-on templates into the test set. The
discard count is reported, because a split that throws away 60% of the corpus is
a fact the reader needs.

Reporting both is itself a result
----------------------------------
`compare_splits` scores the same system under both regimes. The gap between
random-split F1 and template-disjoint F1 quantifies exactly how much of the
headline number was memorisation. Publishing that gap is stronger than
publishing the honest number alone: it demonstrates the failure mode was
measured rather than assumed away, and it is a reusable finding for anyone else
building a template-seeded corpus.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.ingestion.records import RawRecord


def templates_of(record: RawRecord) -> frozenset[str]:
    """Template IDs used to build a record.

    Empty for records with no construct planted (pure logistics talk). Those are
    template-free by construction and so cannot leak; they are distributed
    randomly.
    """
    spec = record.generation_spec or {}
    return frozenset(
        planted["template_id"]
        for planted in spec.get("planted_constructs", ())
        if "template_id" in planted
    )


@dataclass(frozen=True)
class Split:
    """One train/test partition, with the evidence needed to trust it."""

    name: str
    train: tuple[RawRecord, ...]
    test: tuple[RawRecord, ...]
    discarded: tuple[RawRecord, ...] = ()
    train_templates: frozenset[str] = frozenset()
    test_templates: frozenset[str] = frozenset()

    @property
    def shared_templates(self) -> frozenset[str]:
        """Templates appearing on both sides. Must be empty for a clean split."""
        return self.train_templates & self.test_templates

    @property
    def is_template_disjoint(self) -> bool:
        return not self.shared_templates

    def summary(self) -> str:
        total = len(self.train) + len(self.test) + len(self.discarded)
        return (
            f"{self.name}: train={len(self.train)} test={len(self.test)} "
            f"discarded={len(self.discarded)} ({len(self.discarded) / total:.1%} of {total}) "
            f"shared_templates={len(self.shared_templates)} "
            f"disjoint={self.is_template_disjoint}"
        )


def random_split(
    records: Sequence[RawRecord],
    *,
    test_size: float = 0.2,
    seed: int = 42,
) -> Split:
    """The naive split. Provided **as a foil**, not as a recommendation.

    Use it only to quantify how much a leaky split inflates the score. Do not
    report a number produced by this split as a generalisation result.
    """
    items = list(records)
    rng = random.Random(seed)
    rng.shuffle(items)
    cut = int(len(items) * (1.0 - test_size))
    train, test = items[:cut], items[cut:]
    return Split(
        name="random",
        train=tuple(train),
        test=tuple(test),
        train_templates=frozenset().union(*(templates_of(r) for r in train))
        if train
        else frozenset(),
        test_templates=frozenset().union(*(templates_of(r) for r in test)) if test else frozenset(),
    )


def template_disjoint_split(
    records: Sequence[RawRecord],
    *,
    test_size: float = 0.2,
    seed: int = 42,
) -> Split:
    """Partition templates first, then records. No template crosses the line.

    `test_size` targets the fraction of *templates* held out, which is only
    approximately the fraction of records held out — records using several
    templates are likelier to be discarded, so the realised test fraction is
    smaller. `Split.summary()` reports what actually happened rather than what
    was requested.
    """
    items = list(records)
    all_templates = sorted(frozenset().union(*(templates_of(r) for r in items)) if items else set())
    rng = random.Random(seed)
    shuffled = list(all_templates)
    rng.shuffle(shuffled)

    n_test = int(len(shuffled) * test_size)
    test_templates = frozenset(shuffled[:n_test])
    train_templates = frozenset(shuffled[n_test:])

    train: list[RawRecord] = []
    test: list[RawRecord] = []
    discarded: list[RawRecord] = []

    for record in items:
        used = templates_of(record)
        if not used:
            # Construct-free records carry no template, so they cannot leak.
            # Split them randomly to keep the negative class in both halves --
            # a test set with no negatives cannot measure false positives.
            (test if rng.random() < test_size else train).append(record)
        elif used <= test_templates:
            test.append(record)
        elif used <= train_templates:
            train.append(record)
        else:
            discarded.append(record)

    # Exact-duplicate sweep. Template-free records (pure logistics talk) are
    # drawn from a small neutral bank, so the same sentence can legitimately
    # land on both sides without any template being shared. That still means the
    # model is tested on a string it was trained on, which is leakage by any
    # reasonable definition -- the first version of this function left it in and
    # reported 4.9% exact overlap on a split it called clean. Test-side
    # duplicates are moved to `discarded`.
    train_texts = {r.text for r in train}
    deduped_test = [r for r in test if r.text not in train_texts]
    discarded.extend(r for r in test if r.text in train_texts)
    test = deduped_test

    return Split(
        name="template_disjoint",
        train=tuple(train),
        test=tuple(test),
        discarded=tuple(discarded),
        train_templates=frozenset().union(*(templates_of(r) for r in train))
        if train
        else frozenset(),
        test_templates=frozenset().union(*(templates_of(r) for r in test)) if test else frozenset(),
    )


# ---------------------------------------------------------------------------
# Leakage measurement
# ---------------------------------------------------------------------------


def _ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    tokens = text.lower().split()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@dataclass(frozen=True)
class LeakageReport:
    """How much of the test set the model has effectively already seen."""

    split_name: str
    n_train: int
    n_test: int
    shared_template_count: int
    exact_text_overlap: float
    ngram_overlap: dict[int, float] = field(default_factory=dict)

    def as_lines(self) -> list[str]:
        lines = [
            f"split                  : {self.split_name}",
            f"train / test records   : {self.n_train} / {self.n_test}",
            f"templates on both sides: {self.shared_template_count}",
            f"exact test texts seen  : {self.exact_text_overlap:.1%}",
        ]
        lines.extend(
            f"{n}-gram overlap        : {frac:.1%}"
            for n, frac in sorted(self.ngram_overlap.items())
        )
        return lines


def leakage_report(split: Split, *, ngram_sizes: Sequence[int] = (4, 6, 8)) -> LeakageReport:
    """Quantify overlap between train and test.

    Three signals, weakest to strongest evidence of a problem:

    * **n-gram overlap** — some is unavoidable and healthy; English shares
      phrases. Very high 8-gram overlap means near-duplicate sentences.
    * **exact text overlap** — a test record whose text appears verbatim in
      train. Should be 0. Anything above 0 invalidates the split.
    * **shared templates** — the decisive one for this corpus. Non-zero means
      the model saw the phrasing pattern it is being tested on.
    """
    train_texts = {r.text for r in split.train}
    exact = (
        sum(1 for r in split.test if r.text in train_texts) / len(split.test) if split.test else 0.0
    )

    overlaps: dict[int, float] = {}
    for n in ngram_sizes:
        train_ngrams: set[tuple[str, ...]] = set()
        for record in split.train:
            train_ngrams |= _ngrams(record.text, n)
        seen = total = 0
        for record in split.test:
            grams = _ngrams(record.text, n)
            total += len(grams)
            seen += len(grams & train_ngrams)
        overlaps[n] = seen / total if total else 0.0

    return LeakageReport(
        split_name=split.name,
        n_train=len(split.train),
        n_test=len(split.test),
        shared_template_count=len(split.shared_templates),
        exact_text_overlap=exact,
        ngram_overlap=overlaps,
    )
