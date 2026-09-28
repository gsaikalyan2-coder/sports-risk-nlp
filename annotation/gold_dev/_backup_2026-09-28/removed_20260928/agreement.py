"""Inter-annotator agreement -- the number contribution #1 rests on.

Four statistics, each answering a different question, because no single number
describes agreement on a multi-label span-anchored task:

| Statistic | Question it answers |
|---|---|
| Cohen's kappa, per construct | do the two annotators agree on *whether* the construct is expressed, above chance? |
| Quadratic-weighted kappa | do they agree on *how strongly*, treating 0-vs-3 as worse than 2-vs-3? |
| Percent agreement | the raw number, always reported beside kappa |
| Span F1 | do their *spans* overlap, given they agreed on the construct? |

## Why per-construct and never a single headline kappa

`config/taxonomy.yaml` freezes the construct set at Phase 12 *"after checking
annotation burden and inter-annotator agreement. Any construct with poor
agreement is a candidate to drop."* That check is impossible against an average.
A macro-averaged kappa of 0.6 hides `burnout_signal` at 0.2, and
`burnout_signal` is the most clinically loaded label in the taxonomy -- exactly
the one whose disagreement matters most.

## The prevalence problem, reported rather than hidden

Cohen's kappa is unstable when one category dominates. Several constructs here
are rare, so a pair of annotators can agree on 97% of items and score a kappa
near zero -- the *kappa paradox*. Suppressing that as "poor agreement" would be
wrong, and quoting the kappa alone would be misleading.

So `ConstructAgreement` carries the prevalence, the raw percent agreement and
the observed counts alongside kappa, and `interpretation` says plainly when a
low kappa is a prevalence artefact rather than a disagreement. That distinction
decides whether a construct gets dropped at Phase 12, so it cannot be left to
whoever reads the table.

## Bootstrap intervals

Every headline figure carries a percentile bootstrap CI, reusing
`src/evaluation/metrics.bootstrap_statistic` -- the same machinery and the same
argument Phase 9 made: `[0.41, 0.79]` is a different statement from `0.61`, and
on 400 items with rare constructs the interval is wide enough to change what
the paper can claim.

## What is deliberately NOT computed

**No agreement between a human and the silver labeller.** That is a measurement
of the model and belongs in Phase 14 under a name that says so. Calling it
agreement would put a model in a statistic whose entire meaning is that two
people independently reached the same judgement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.evaluation.metrics import bootstrap_statistic

from .schema import GoldLabel

#: Landis & Koch bands. Conventional, contested, and reported because reviewers
#: expect them -- not because a bright line at 0.6 means anything in itself.
KAPPA_BANDS = (
    (0.81, "almost perfect"),
    (0.61, "substantial"),
    (0.41, "moderate"),
    (0.21, "fair"),
    (0.01, "slight"),
    (-1.0, "poor"),
)

#: Below this prevalence a kappa is dominated by the marginal distribution and
#: should be read with the percent agreement, not instead of it.
RARE_PREVALENCE = 0.10


def band(kappa: float) -> str:
    for floor, name in KAPPA_BANDS:
        if kappa >= floor:
            return name
    return "poor"  # pragma: no cover - unreachable, the table ends at -1.0


@dataclass(frozen=True)
class ConstructAgreement:
    """Agreement between two annotators on one construct."""

    construct: str
    n_items: int
    percent_agreement: float
    kappa: float
    weighted_kappa: float
    prevalence_a: float
    prevalence_b: float
    both_present: int
    only_a: int
    only_b: int
    neither: int
    span_f1: float
    kappa_ci: tuple[float, float] | None = None

    @property
    def is_rare(self) -> bool:
        return max(self.prevalence_a, self.prevalence_b) < RARE_PREVALENCE

    @property
    def is_degenerate(self) -> bool:
        """True when neither annotator ever marked it: kappa is undefined."""
        return self.both_present + self.only_a + self.only_b == 0

    def interpretation(self) -> str:
        if self.is_degenerate:
            return (
                "UNDEFINED -- neither annotator marked this construct anywhere in the "
                "batch. Not a disagreement; there is nothing to agree about. Either the "
                "sample under-represents it or the construct is not realised in this "
                "corpus, and Phase 12 needs to know which"
            )
        if self.is_rare:
            return (
                f"{band(self.kappa)} kappa, but prevalence is only "
                f"{max(self.prevalence_a, self.prevalence_b):.1%} -- read this with the "
                f"{self.percent_agreement:.1%} raw agreement. A low kappa at this "
                "prevalence is the kappa paradox, not necessarily poor annotation"
            )
        return f"{band(self.kappa)} agreement"

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "n_items": self.n_items,
            "percent_agreement": round(self.percent_agreement, 4),
            "kappa": round(self.kappa, 4),
            "kappa_ci": (
                [round(self.kappa_ci[0], 4), round(self.kappa_ci[1], 4)] if self.kappa_ci else None
            ),
            "weighted_kappa_intensity": round(self.weighted_kappa, 4),
            "prevalence_a": round(self.prevalence_a, 4),
            "prevalence_b": round(self.prevalence_b, 4),
            "both_present": self.both_present,
            "only_a": self.only_a,
            "only_b": self.only_b,
            "neither": self.neither,
            "span_f1": round(self.span_f1, 4),
            "band": band(self.kappa),
            "rare": self.is_rare,
            "degenerate": self.is_degenerate,
            "interpretation": self.interpretation(),
        }


def cohens_kappa(pairs: Sequence[tuple[Any, Any]]) -> float:
    """Cohen's kappa over paired categorical judgements.

    Returns 1.0 for perfect agreement on a single category rather than `nan`.
    When both annotators always said the same thing, expected agreement is 1,
    the standard formula divides by zero, and the truthful answer is that they
    agreed completely -- a `nan` here would propagate into a macro-average and
    quietly delete the construct from the table.
    """
    if not pairs:
        return 0.0
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n

    categories = {a for a, _ in pairs} | {b for _, b in pairs}
    expected = 0.0
    for category in categories:
        pa = sum(1 for a, _ in pairs if a == category) / n
        pb = sum(1 for _, b in pairs if b == category) / n
        expected += pa * pb

    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def quadratic_weighted_kappa(pairs: Sequence[tuple[int, int]], *, max_rating: int = 3) -> float:
    """Weighted kappa for the ordinal 0-3 intensity scale.

    Quadratic weights because the scale is ordinal and the errors are not
    equivalent: an annotator pair splitting 2-vs-3 has essentially agreed, while
    0-vs-3 is a disagreement about whether the construct is there at all.
    Unweighted kappa treats those as the same error and understates agreement on
    a graded scale.
    """
    if not pairs:
        return 0.0
    size = max_rating + 1
    n = len(pairs)

    observed = [[0.0] * size for _ in range(size)]
    for a, b in pairs:
        observed[a][b] += 1

    hist_a = [sum(1 for a, _ in pairs if a == i) for i in range(size)]
    hist_b = [sum(1 for _, b in pairs if b == i) for i in range(size)]

    numerator = 0.0
    denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = ((i - j) ** 2) / ((size - 1) ** 2)
            expected = hist_a[i] * hist_b[j] / n
            numerator += weight * observed[i][j]
            denominator += weight * expected

    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return 1 - numerator / denominator


def _token_set(text: str) -> set[str]:
    return {t for t in text.lower().split() if t}


def span_overlap_f1(spans_a: Sequence[str], spans_b: Sequence[str]) -> float:
    """Token-level F1 between two annotators' spans for one construct.

    Token overlap rather than exact match, because exact span match is a
    standard both human annotators would fail against each other constantly --
    guidelines sec.1 asks for "the minimal span a reader could not remove", and
    two careful people routinely include or exclude a leading "I keep". Scoring
    that as total disagreement would say nothing useful about whether they found
    the same evidence.
    """
    tokens_a: set[str] = set()
    for span in spans_a:
        tokens_a |= _token_set(span)
    tokens_b: set[str] = set()
    for span in spans_b:
        tokens_b |= _token_set(span)

    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    if overlap == 0:
        return 0.0
    precision = overlap / len(tokens_b)
    recall = overlap / len(tokens_a)
    return 2 * precision * recall / (precision + recall)


def align(
    pass_a: Sequence[GoldLabel], pass_b: Sequence[GoldLabel]
) -> list[tuple[GoldLabel, GoldLabel]]:
    """Pair the two passes by `record_id`, keeping only items both annotated.

    Escalated items are dropped from the pair. Guidelines sec.7 says an
    escalated item is *not labelled*, so including it would compare a judgement
    against a refusal to judge. They are counted separately and reported.
    """
    by_id_b = {label.record_id: label for label in pass_b}
    pairs: list[tuple[GoldLabel, GoldLabel]] = []
    for label_a in pass_a:
        label_b = by_id_b.get(label_a.record_id)
        if label_b is None:
            continue
        if label_a.escalate or label_b.escalate:
            continue
        pairs.append((label_a, label_b))
    return pairs


def construct_agreement(
    pairs: Sequence[tuple[GoldLabel, GoldLabel]],
    construct: str,
    *,
    bootstrap: int = 1000,
    seed: int = 42,
) -> ConstructAgreement:
    """Full agreement picture for one construct."""
    presence = [
        (a.value_for(construct) != "none", b.value_for(construct) != "none") for a, b in pairs
    ]
    values = [(a.value_for(construct), b.value_for(construct)) for a, b in pairs]
    intensities = [(a.intensity_for(construct), b.intensity_for(construct)) for a, b in pairs]

    n = len(pairs)
    both = sum(1 for x, y in presence if x and y)
    only_a = sum(1 for x, y in presence if x and not y)
    only_b = sum(1 for x, y in presence if y and not x)
    neither = sum(1 for x, y in presence if not x and not y)

    kappa = cohens_kappa(values)
    weighted = quadratic_weighted_kappa(intensities)
    percent = (sum(1 for x, y in values if x == y) / n) if n else 0.0

    span_scores = [
        span_overlap_f1(a.spans_for(construct), b.spans_for(construct))
        for a, b in pairs
        if a.value_for(construct) != "none" and b.value_for(construct) != "none"
    ]
    span_f1 = sum(span_scores) / len(span_scores) if span_scores else 0.0

    kappa_ci = None
    if n >= 20 and bootstrap:
        # Reuses the Phase 9 bootstrap so the interval is computed the same way
        # everywhere in the project.
        interval = bootstrap_statistic(values, cohens_kappa, n_resamples=bootstrap, seed=seed)
        kappa_ci = (interval.low, interval.high)

    return ConstructAgreement(
        construct=construct,
        n_items=n,
        percent_agreement=percent,
        kappa=kappa,
        weighted_kappa=weighted,
        prevalence_a=(both + only_a) / n if n else 0.0,
        prevalence_b=(both + only_b) / n if n else 0.0,
        both_present=both,
        only_a=only_a,
        only_b=only_b,
        neither=neither,
        span_f1=span_f1,
        kappa_ci=kappa_ci,
    )


@dataclass
class AgreementReport:
    """The whole agreement analysis for one batch."""

    batch: str
    annotator_a: str
    annotator_b: str
    n_paired: int
    n_escalated: int
    n_unpaired: int
    constructs: list[ConstructAgreement]

    @property
    def measurable(self) -> list[ConstructAgreement]:
        return [c for c in self.constructs if not c.is_degenerate]

    @property
    def macro_kappa(self) -> float:
        """Mean kappa over measurable constructs. Reported, never alone."""
        rows = self.measurable
        return sum(c.kappa for c in rows) / len(rows) if rows else 0.0

    def below(self, threshold: float) -> list[str]:
        return [c.construct for c in self.measurable if c.kappa < threshold]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": 11,
            "batch": self.batch,
            "annotators": [self.annotator_a, self.annotator_b],
            "paired_items": self.n_paired,
            "escalated_items_excluded": self.n_escalated,
            "items_only_one_annotator_labelled": self.n_unpaired,
            "macro_kappa_over_measurable": round(self.macro_kappa, 4),
            "measurable_constructs": len(self.measurable),
            "degenerate_constructs": [c.construct for c in self.constructs if c.is_degenerate],
            "constructs": [c.to_dict() for c in self.constructs],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Inter-annotator agreement -- {self.batch}",
            "",
            f"Annotators **{self.annotator_a}** and **{self.annotator_b}**, "
            f"{self.n_paired} doubly-annotated items "
            f"({self.n_escalated} escalated and excluded, "
            f"{self.n_unpaired} labelled by only one annotator).",
            "",
            "| construct | n | % agree | kappa | 95% CI | weighted k (intensity) | span F1 | prevalence | reading |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for row in sorted(self.constructs, key=lambda c: c.kappa):
            ci = f"[{row.kappa_ci[0]:.2f}, {row.kappa_ci[1]:.2f}]" if row.kappa_ci else "--"
            lines.append(
                f"| {row.construct} | {row.n_items} | {row.percent_agreement:.1%} | "
                f"{row.kappa:.3f} | {ci} | {row.weighted_kappa:.3f} | {row.span_f1:.3f} | "
                f"{max(row.prevalence_a, row.prevalence_b):.1%} | {row.interpretation()} |"
            )
        lines += [
            "",
            f"Macro kappa over the {len(self.measurable)} measurable construct(s): "
            f"**{self.macro_kappa:.3f}**. Never quote this without the per-construct "
            "table -- an average hides exactly the construct Phase 12 should drop.",
        ]
        return "\n".join(lines)


class AgreementUnmeasurable(RuntimeError):
    """Raised when agreement is asked for and cannot exist."""


def compute_agreement(
    passes: dict[str, list[GoldLabel]],
    constructs: Sequence[str],
    *,
    batch: str,
    bootstrap: int = 1000,
    seed: int = 42,
) -> AgreementReport:
    """Agreement between exactly two annotators.

    Refuses a single-annotator batch rather than returning a placeholder. One
    person labelling 400 items produces a labelled set, not a gold standard, and
    a function that returned 0.0 or `nan` here would let that distinction slide
    into a results table.
    """
    ids = sorted(passes)
    if len(ids) < 2:
        raise AgreementUnmeasurable(
            f"batch {batch!r} has {len(ids)} annotator pass(es): {ids}. Inter-annotator "
            "agreement requires two independent passes over the same items. Add the "
            "second annotator to config/annotators.yaml and have them complete the "
            "batch -- this is the Phase 11 blocker, and no statistic can substitute"
        )
    if len(ids) > 2:
        raise AgreementUnmeasurable(
            f"batch {batch!r} has {len(ids)} passes: {ids}. Cohen's kappa is defined for "
            "a pair; for three or more annotators use Fleiss' kappa, which is not "
            "implemented because the plan specifies two"
        )

    a_id, b_id = ids
    pass_a, pass_b = passes[a_id], passes[b_id]
    pairs = align(pass_a, pass_b)

    ids_a = {x.record_id for x in pass_a}
    ids_b = {x.record_id for x in pass_b}
    escalated = sum(
        1
        for rid in ids_a & ids_b
        if any(x.escalate for x in pass_a if x.record_id == rid)
        or any(x.escalate for x in pass_b if x.record_id == rid)
    )

    return AgreementReport(
        batch=batch,
        annotator_a=a_id,
        annotator_b=b_id,
        n_paired=len(pairs),
        n_escalated=escalated,
        n_unpaired=len(ids_a ^ ids_b),
        constructs=[
            construct_agreement(pairs, c, bootstrap=bootstrap, seed=seed) for c in constructs
        ],
    )


def disagreements(
    pairs: Sequence[tuple[GoldLabel, GoldLabel]], constructs: Sequence[str]
) -> list[dict[str, Any]]:
    """Every item-construct pair the two annotators disagreed on.

    This is the adjudication worklist. Ordered by how far apart they were, so
    the session starts on the cases that actually move the rubric rather than on
    2-vs-3 intensity quibbles.
    """
    out: list[dict[str, Any]] = []
    for a, b in pairs:
        for construct in constructs:
            va, vb = a.value_for(construct), b.value_for(construct)
            ia, ib = a.intensity_for(construct), b.intensity_for(construct)
            if va == vb and ia == ib:
                continue
            out.append(
                {
                    "record_id": a.record_id,
                    "text": a.text,
                    "construct": construct,
                    f"{a.annotator_id}_value": va,
                    f"{a.annotator_id}_intensity": ia,
                    f"{a.annotator_id}_spans": list(a.spans_for(construct)),
                    f"{b.annotator_id}_value": vb,
                    f"{b.annotator_id}_intensity": ib,
                    f"{b.annotator_id}_spans": list(b.spans_for(construct)),
                    "presence_disagreement": (va == "none") != (vb == "none"),
                    "distance": abs(ia - ib) + (2 if (va == "none") != (vb == "none") else 0),
                    "either_uncertain": a.uncertain or b.uncertain,
                }
            )
    return sorted(out, key=lambda d: -d["distance"])
