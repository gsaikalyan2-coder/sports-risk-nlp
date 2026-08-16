"""Phase 17 -- two-level explanation cards: span -> construct -> risk.

What a card is, and why it is the paper's contribution #2
---------------------------------------------------------
`CLAUDE.md` sec.1 names "two-level, expert-validated interpretability" as the
headline differentiator. The two levels are:

    level 1   span -> construct     ("my hands won't stop shaking" -> somatic_anxiety)
    level 2   construct -> risk     (somatic_anxiety p=0.81 raised the index by 0.16)

Level 1 comes from `attribution.py`. Level 2 comes from `src/risk/fusion.py`,
which has produced signed, taxonomy-anchored `Contribution` objects since Phase
15. Neither half is novel alone -- token attribution is standard, and a weighted
sum is a weighted sum. **The contribution is that they compose into one artefact
a practitioner can read end to end**, so that a risk number is traceable back to
the words that produced it without leaving the page.

A card is therefore the unit of the expert study, the unit of the dashboard
(Phase 19), and the unit of the paper's qualitative figure. It exists in exactly
one implementation so those three cannot drift apart.

The ethics constraint is enforced here, not documented here
-----------------------------------------------------------
The Phase 17 handover binds: *no verbatim corpus text in the paper, dashboard or
figures; no individual-level output; no claim about an identifiable person.*
Three of those are enforced mechanically in this module rather than left to
whoever writes the LaTeX:

* `ExplanationCard.provenance` is mandatory and non-empty, and `render_markdown`
  emits it above the text every time. A card without it cannot be constructed.
* `render_markdown(..., redact=True)` -- the default for anything paper-bound --
  emits only the highlighted spans and their scores, never the full record. A
  span is the evidence; the surrounding sentence is corpus.
* `assert_publication_safe` refuses a card whose record is not flagged
  `synthetic`, so the day real A3 donated text lands in the corpus (OPEN-011) the
  figure pipeline fails loudly instead of quietly publishing a donor's words.

That last guard is the one worth arguing for. Today every record is synthetic and
the check is a no-op, so it looks like ceremony. It stops looking like ceremony
in the precise week the project is most likely to make the mistake: the week
real text first arrives, when the figure scripts already exist and nobody
re-reads the ethics doc before regenerating them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from src.explainability.attribution import (
    EXPLANATION_PROVENANCE,
    RecordExplanation,
    SpanAttribution,
)
from src.risk.fusion import Contribution, RiskScore


class PublicationUnsafe(RuntimeError):
    """A card would leak text that `docs/ethics.md` does not permit publishing."""


@dataclass(frozen=True)
class ConstructEvidence:
    """One construct's row on a card: its risk contribution and its text evidence.

    The pairing is the point. `Contribution` alone says "somatic_anxiety raised
    the score by 0.16" and a reader must take that on trust. `spans` alone says
    "the model looked at 'hands won't stop shaking'" and a reader cannot tell
    whether it mattered. Together they are checkable.
    """

    contribution: Contribution
    spans: tuple[SpanAttribution, ...]
    method: str

    @property
    def has_evidence(self) -> bool:
        return bool(self.spans)

    def covers_whole_record(self, text: str, *, threshold: float = 0.9) -> bool:
        """True when the 'evidence' spans most of the record.

        A span that highlights everything explains nothing -- it is the
        attribution equivalent of a model that predicts the majority class. It
        also breaks the redaction guarantee: `render_markdown(redact=True)`
        promises to withhold the record and show only the spans, and that
        promise is void if the spans *are* the record.

        Reported rather than silently dropped, because a genuinely diffuse
        attribution is a real and interesting state -- it means the model's
        decision rests on the sentence as a whole rather than any phrase, which
        for a template-grammar corpus is a plausible and reportable outcome.
        """
        if not self.spans or not text:
            return False
        covered = sum(s.end - s.start for s in self.spans)
        return covered / len(text) >= threshold


@dataclass(frozen=True)
class ExplanationCard:
    """One record, fully explained at both levels."""

    record_id: str
    text: str
    risk: RiskScore
    evidence: tuple[ConstructEvidence, ...]
    method: str
    synthetic: bool
    provenance: str = EXPLANATION_PROVENANCE

    def __post_init__(self) -> None:
        if not self.provenance.strip():
            raise ValueError(
                "An explanation card without provenance is a risk claim with no "
                "attached statement of what produced it. Refused at construction "
                "rather than checked at render time, because the render is the "
                "step most likely to be reimplemented."
            )

    @property
    def drivers(self) -> tuple[ConstructEvidence, ...]:
        """Evidence rows that actually moved the score, largest effect first."""
        moving = [e for e in self.evidence if e.contribution.contribution != 0]
        return tuple(sorted(moving, key=lambda e: -abs(e.contribution.contribution)))

    @property
    def unevidenced_drivers(self) -> tuple[ConstructEvidence, ...]:
        """Constructs that moved the risk index but produced no text evidence.

        **This is a diagnostic, not a leftover.** A construct that shifts the
        risk score while no span in the text supports it is the model asserting
        something it cannot point at. It is the single most useful thing on the
        card for a reviewer, and the report counts it explicitly rather than
        letting it hide among the rows that look fine.
        """
        return tuple(e for e in self.drivers if not e.has_evidence)

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "text": self.text,
            "synthetic": self.synthetic,
            "method": self.method,
            "provenance": self.provenance,
            "risk_index": self.risk.index,
            "risk_is_calibrated": self.risk.is_calibrated,
            "risk_provenance": self.risk.provenance,
            "evidence": [
                {
                    "construct": e.contribution.construct,
                    "probability": e.contribution.probability,
                    "direction": e.contribution.direction.value,
                    "weight": e.contribution.weight,
                    "contribution": e.contribution.contribution,
                    "polarity_unresolved": e.contribution.polarity_unresolved,
                    "spans": [
                        {"text": s.text, "start": s.start, "end": s.end, "score": s.score}
                        for s in e.spans
                    ],
                }
                for e in self.evidence
            ],
        }


def build_card(
    *,
    explanation: RecordExplanation,
    risk: RiskScore,
    synthetic: bool,
    top_spans: int = 3,
    min_span_score: float = 0.0,
) -> ExplanationCard:
    """Join a `RecordExplanation` to a `RiskScore` on construct name.

    Joined on name rather than on position, and the two sources are iterated
    independently, because `RiskScore.contributions` is sorted by construct name
    (`fusion.score` iterates `sorted(self.magnitudes)`) while `RecordExplanation`
    preserves taxonomy order. Zipping them would silently pair each construct's
    risk contribution with a different construct's spans -- every field would be
    populated, every type would check, and every card would be wrong.
    """
    by_construct = {e.construct: e for e in explanation.explanations}
    evidence: list[ConstructEvidence] = []
    for contribution in risk.contributions:
        found = by_construct.get(contribution.construct)
        spans = (
            found.top_spans(limit=top_spans, min_score=min_span_score) if found is not None else ()
        )
        evidence.append(
            ConstructEvidence(
                contribution=contribution,
                spans=spans,
                method=found.method if found is not None else explanation.method,
            )
        )
    return ExplanationCard(
        record_id=explanation.record_id,
        text=explanation.text,
        risk=risk,
        evidence=tuple(evidence),
        method=explanation.method,
        synthetic=synthetic,
        provenance=explanation.provenance,
    )


def assert_publication_safe(cards: Sequence[ExplanationCard]) -> None:
    """Refuse to emit paper-bound artefacts containing non-synthetic text.

    See the module docstring. `docs/ethics.md` sec.3.3 permits verbatim quotation
    of the A2 synthetic source alone.
    """
    unsafe = [c.record_id for c in cards if not c.synthetic]
    if unsafe:
        raise PublicationUnsafe(
            f"{len(unsafe)} card(s) carry non-synthetic text and cannot be "
            f"rendered verbatim: {', '.join(unsafe[:5])}"
            f"{' ...' if len(unsafe) > 5 else ''}.\n\n"
            "docs/ethics.md sec.3.3 permits verbatim quotation of the A2 synthetic "
            "source only. If this is consented A3 donation text, render with "
            "redact=True (spans only, no full record) and confirm the consent "
            "form covers quotation before it reaches a figure."
        )


def highlight(text: str, spans: Sequence[SpanAttribution], *, marker: str = "**") -> str:
    """Wrap the attributed spans in the source text.

    Overlapping spans are merged rather than nested, because nesting produces
    `**a **b** c**`, which no Markdown renderer resolves the way the author
    intended, and the resulting figure would misstate which words were
    highlighted.
    """
    if not spans:
        return text
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    merged: list[list[int]] = []
    for span in ordered:
        if merged and span.start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], span.end)
        else:
            merged.append([span.start, span.end])

    out: list[str] = []
    cursor = 0
    for start, end in merged:
        out.append(text[cursor:start])
        out.append(f"{marker}{text[start:end]}{marker}")
        cursor = end
    out.append(text[cursor:])
    return "".join(out)


def render_markdown(card: ExplanationCard, *, redact: bool = False) -> str:
    """One card as Markdown.

    `redact=True` omits the full record and shows only the highlighted spans.
    Use it for anything paper-bound or dashboard-bound; use `False` for
    `reports/explain/`, which is an internal artefact of a synthetic corpus.
    """
    lines: list[str] = [f"### `{card.record_id}`", ""]
    lines.append(f"> {card.provenance}")
    lines.append("")

    if redact:
        lines.append("_Full record withheld; attributed spans only._")
        diffuse = [
            e.contribution.construct for e in card.drivers if e.covers_whole_record(card.text)
        ]
        if diffuse:
            # Redaction promises the record stays withheld. A span covering the
            # whole record would break that promise through the evidence column,
            # so the spans are suppressed too and the reason is stated.
            lines.append("")
            lines.append(
                f"_Evidence spans suppressed for {', '.join(diffuse)}: the attribution "
                "covers effectively the whole record, so printing the spans would "
                "reproduce the withheld text._"
            )
    else:
        top = [s for e in card.drivers for s in e.spans]
        lines.append(f"**Text.** {highlight(card.text, top)}")
    lines.append("")

    flag = "" if card.risk.is_calibrated else "  _(ranking only -- not calibrated)_"
    lines.append(f"**Risk index {card.risk.index:.2f}**{flag}")
    lines.append("")
    lines.append("| construct | p | direction | contribution | evidence spans |")
    lines.append("|---|---|---|---|---|")
    for row in card.drivers:
        contribution = row.contribution
        if redact and row.covers_whole_record(card.text):
            spans = "_suppressed (attribution covers the whole record)_"
        elif row.spans:
            spans = "; ".join(f"`{s.text}` ({s.score:+.2f})" for s in row.spans)
        else:
            spans = "_none -- construct moved the score with no supporting span_"
        lines.append(
            f"| {contribution.construct} | {contribution.probability:.2f} | "
            f"{contribution.direction.value} | {contribution.contribution:+.3f} | {spans} |"
        )

    if not card.drivers:
        lines.append("| _no construct moved the score_ |  |  |  |  |")

    missing = card.unevidenced_drivers
    if missing:
        lines.append("")
        lines.append(
            f"**Diagnostic.** {len(missing)} construct(s) moved the risk index with no "
            f"supporting text span: {', '.join(e.contribution.construct for e in missing)}. "
            "The model is asserting something it cannot point at."
        )
    lines.append("")
    return "\n".join(lines)


@dataclass
class CardSet:
    """A rendered collection, with the aggregate diagnostics the report needs."""

    cards: tuple[ExplanationCard, ...] = field(default_factory=tuple)

    def summary(self) -> dict[str, Any]:
        n = len(self.cards)
        if n == 0:
            return {"n": 0}
        driver_rows = [e for c in self.cards for e in c.drivers]
        unevidenced = [e for c in self.cards for e in c.unevidenced_drivers]
        return {
            "n": n,
            "n_driver_rows": len(driver_rows),
            "n_unevidenced_driver_rows": len(unevidenced),
            "unevidenced_rate": (len(unevidenced) / len(driver_rows)) if driver_rows else 0.0,
            "all_synthetic": all(c.synthetic for c in self.cards),
            "mean_risk_index": sum(c.risk.index for c in self.cards) / n,
        }

    def render(self, *, redact: bool = False) -> str:
        return "\n".join(render_markdown(c, redact=redact) for c in self.cards)
