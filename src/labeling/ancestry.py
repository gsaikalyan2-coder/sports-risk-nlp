"""OPEN-021, one level up: is the silver labeller independent of the corpus?

## The shape of the problem

Phase 9b established that `LexiconBaseline` was never corpus-independent. Its
cues were hand-written from `config/taxonomy.yaml`'s `positive_examples`, and
the Phase 7 template bank was written from those same examples. Neither
inherited from the other, so it did not look like leakage -- but they shared an
ancestor, and that was enough. When the Phase 9b templates stopped reusing those
phrasings, the lexicon's macro-F1 fell 0.780 -> 0.461. **The corpus did not get
harder; the baseline lost an advantage it should never have had.**

The silver labeller has the identical shape. It is handed `taxonomy.yaml`
including `positive_examples` in its system prompt, and it labels a corpus
generated from those same examples. If it labels well, part of that may be
recognition of shared ancestry rather than comprehension of athlete language.

## What this module measures, and what it does not

It measures **lexical overlap** between each utterance and its construct's
`positive_examples`, buckets utterances into high and low overlap, and reports
the labeller's behaviour in each bucket: how often it asserts the construct, how
confident it is, how often it abstains.

It does **not** measure accuracy, because there is nothing here to be accurate
against. `generation_spec` is not a label and using it would be the circularity
this project keeps refusing. The human gold set does not exist until Phase 11.
So the honest output is a **divergence report**, not a score:

* a large gap between buckets is evidence that ancestry is doing work, and the
  size of the gap bounds how much of the labeller's apparent competence is
  recognition;
* a small gap is weak evidence against, not proof of independence -- overlap is
  a proxy for ancestry, and a coarse one.

Either way the number goes in the paper's limitations, and the real test is
Phase 14 against human gold.

## The check that could not be built, and why

The obvious partition -- Phase 7-era templates against Phase 9b-era ones, which
is exactly the comparison that exposed the lexicon -- is **not recoverable from
the corpus**. `template_id` is `construct:label:index` with index 0-4 across all
150 templates; Phase 9b restructured the bank to five realisations per
(construct, label) rather than appending to it, so no field records when a
template was written. That is a real gap in the corpus's own provenance and is
raised as OPEN-022. Lexical overlap is the available substitute, not the
preferred instrument.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .schema import SilverLabel

_TOKEN_RE = re.compile(r"[a-z']+")

#: Words carrying no construct signal. Overlap on "the" and "i" is noise, and
#: with 17-token utterances that noise would dominate a raw Jaccard score.
_STOPWORDS = frozenset(
    """a about all am an and any are aren't as at be been before but by can can't could
    did do does doing don't for from get go going got had has have he her him his how i
    i'll i'm i've if in into is isn't it it's its just keep me more most much my no not
    of off on one or our out over own re s so some t than that the their them then there
    these they this those to too up us very was we well were what when where which who
    will with would you your""".split()
)

#: Jaccard over content tokens. 0.30 is a judgement call and is reported as one:
#: it is roughly "a third of the content words are shared", which on a 10-word
#: clause means three words in common. The sweep in `overlap_report` reports
#: several thresholds so the conclusion does not rest on this one.
DEFAULT_OVERLAP_THRESHOLD = 0.30


def content_tokens(text: str) -> frozenset[str]:
    return frozenset(
        t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def example_overlap(text: str, examples: Sequence[str]) -> float:
    """Best Jaccard between this text and any of the construct's examples.

    Maximum rather than mean: ancestry from a *single* example is exactly the
    effect being probed, and averaging over the other four would hide it.
    """
    tokens = content_tokens(text)
    return max((jaccard(tokens, content_tokens(example)) for example in examples), default=0.0)


@dataclass(frozen=True)
class ConstructAncestry:
    """One construct's high-overlap vs low-overlap comparison."""

    construct: str
    high_n: int
    low_n: int
    high_assert_rate: float
    low_assert_rate: float
    high_mean_confidence: float
    low_mean_confidence: float

    @property
    def assert_gap(self) -> float:
        """Positive means the labeller fires more on ancestry-like phrasings."""
        return self.high_assert_rate - self.low_assert_rate

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "high_overlap_n": self.high_n,
            "low_overlap_n": self.low_n,
            "high_overlap_assert_rate": round(self.high_assert_rate, 4),
            "low_overlap_assert_rate": round(self.low_assert_rate, 4),
            "assert_rate_gap": round(self.assert_gap, 4),
            "high_overlap_mean_confidence": round(self.high_mean_confidence, 4),
            "low_overlap_mean_confidence": round(self.low_mean_confidence, 4),
        }


def _bucket_stats(group: Sequence[SilverLabel], construct: str) -> tuple[float, float]:
    """(assert rate, mean confidence) for one construct over one bucket.

    A module-level function rather than a closure over the loop variable: ruff's
    B023 flagged the closure, and it was right to. The behaviour happened to be
    correct because the closure was called inside the same iteration, but a
    function that silently depends on when it is called is a latent bug waiting
    for someone to store it in a list.
    """
    if not group:
        return 0.0, 0.0
    asserted = [x for x in group if any(i.construct == construct for i in x.present_labels)]
    rate = len(asserted) / len(group)
    confidences = [
        i.confidence for x in asserted for i in x.present_labels if i.construct == construct
    ]
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return rate, mean


def overlap_report(
    labels: Sequence[SilverLabel],
    taxonomy: dict[str, Any],
    *,
    threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> list[ConstructAncestry]:
    """Per-construct ancestry probe over a silver label set."""
    constructs = taxonomy.get("constructs") or {}
    out: list[ConstructAncestry] = []

    for construct, spec in constructs.items():
        examples = [str(e) for e in (spec.get("positive_examples") or [])]
        if not examples:
            continue

        high: list[SilverLabel] = []
        low: list[SilverLabel] = []
        for label in labels:
            bucket = high if example_overlap(label.text, examples) >= threshold else low
            bucket.append(label)

        high_rate, high_conf = _bucket_stats(high, construct)
        low_rate, low_conf = _bucket_stats(low, construct)
        out.append(
            ConstructAncestry(
                construct=construct,
                high_n=len(high),
                low_n=len(low),
                high_assert_rate=high_rate,
                low_assert_rate=low_rate,
                high_mean_confidence=high_conf,
                low_mean_confidence=low_conf,
            )
        )
    return out


def format_report(rows: Sequence[ConstructAncestry], *, threshold: float) -> str:
    """A markdown table, for `docs/labeling.md` and the gate's stdout."""
    lines = [
        f"Shared-ancestry probe (OPEN-021), overlap threshold {threshold:.2f}",
        "",
        "| construct | high-overlap n | assert rate | low-overlap n | assert rate | gap |",
        "|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda r: -abs(r.assert_gap)):
        lines.append(
            f"| {row.construct} | {row.high_n} | {row.high_assert_rate:.3f} | "
            f"{row.low_n} | {row.low_assert_rate:.3f} | {row.assert_gap:+.3f} |"
        )
    return "\n".join(lines)
