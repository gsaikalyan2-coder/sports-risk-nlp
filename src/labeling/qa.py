"""The Annotation-QA pass: decide what a human needs to look at.

The Annotation-QA Agent's contract (`src/agents/roster.py::ANNOTATION_QA`) is
narrow on purpose: *"You are a gatekeeper, not a second labeler. You do not
re-label."* This module honours that literally. It re-reads what was produced
and flags; it never changes a label.

**Every flag is computable without a model call.** The roster assigns this agent
the cheap tier, but the checks below are structural -- confidence thresholds,
missing spans, parse failures, distributional outliers -- and asking an LLM
whether a label "looks right" would be a second labeller in a gatekeeper's
clothes, at ~9,000 extra calls. Spending nothing here is not a shortcut; it is
what keeps the QA pass independent of the thing it is auditing.

**Every reason is derived from the label or the text, never from
`generation_spec`.** Flagging "the model missed a construct the generator
planted" would be the circularity trap wearing a QA badge: it would send the
review queue chasing the template bank rather than the language, and a human
working that queue would learn to reproduce the generator. The queue is
therefore blind to what was planted, exactly as a human annotator is.

The queue is a JSONL at `logs/review_queue.jsonl`, one row per flagged
utterance, grouped by reason so a person can work the highest-yield category
first rather than reading 9,000 rows in corpus order.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runner import LabelFailure, LabelingRun
from .schema import SilverLabel

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE_PATH = REPO_ROOT / "logs" / "review_queue.jsonl"

#: Reason codes, ordered by how much a human's time is worth on each.
REASON_PARSE_FAILURE = "PARSE_FAILURE"
REASON_LOW_CONFIDENCE = "LOW_CONFIDENCE"
REASON_ESCALATED = "ESCALATED_AND_UNCERTAIN"
REASON_MANY_CONSTRUCTS = "IMPLAUSIBLY_MANY_CONSTRUCTS"
REASON_CLINICAL_LANGUAGE = "CLINICAL_LANGUAGE_IN_RATIONALE"
REASON_BURNOUT = "BURNOUT_ASSERTED"
REASON_SPAN_IS_WHOLE_TEXT = "SPAN_IS_WHOLE_UTTERANCE"

#: A single 17-token utterance asserting six of ten constructs is not a rich
#: utterance, it is a model that has stopped discriminating. Four is generous:
#: the richest worked example in `docs/annotation_guidelines.md` sec.5 carries
#: five including the modifier, so this flags rather than rejects.
MAX_PLAUSIBLE_CONSTRUCTS = 4

#: `docs/annotation_guidelines.md` sec.0 rule 2 forbids clinical terms in notes,
#: and sec.8 makes it a pre-submission check. Applied to the machine labeller
#: for the same reason it is applied to humans: the rationale is user-facing at
#: Phase 16, and a clinical word in it is an ethics breach regardless of author.
CLINICAL_TERMS: tuple[str, ...] = (
    "depress",
    "disorder",
    "diagnos",
    "mental illness",
    "patholog",
    "psychiatric",
    "clinical",
    "suicid",
    "trauma",
    "therapy",
    "medication",
)


@dataclass(frozen=True)
class ReviewItem:
    """One flagged utterance."""

    record_id: str
    parent_record_id: str
    text: str
    reason: str
    detail: str
    confidence: float
    tier: str
    escalated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "parent_record_id": self.parent_record_id,
            "text": self.text,
            "reason": self.reason,
            "detail": self.detail,
            "confidence": round(float(self.confidence), 4),
            "tier": self.tier,
            "escalated": self.escalated,
        }


def _clinical_hits(rationale: str) -> list[str]:
    lowered = rationale.lower()
    return [term for term in CLINICAL_TERMS if term in lowered]


def review_reasons(label: SilverLabel, *, confidence_threshold: float) -> list[tuple[str, str]]:
    """Every reason this label warrants a human look. May be empty."""
    reasons: list[tuple[str, str]] = []

    weakest = label.min_label_confidence
    if weakest < confidence_threshold:
        code = REASON_ESCALATED if label.escalated else REASON_LOW_CONFIDENCE
        detail = f"weakest confidence {weakest:.2f} < {confidence_threshold:.2f}"
        if label.escalated:
            detail += " even after escalation to the mid tier"
        reasons.append((code, detail))

    present = label.present_labels
    if len(present) > MAX_PLAUSIBLE_CONSTRUCTS:
        reasons.append(
            (
                REASON_MANY_CONSTRUCTS,
                f"{len(present)} constructs asserted on one utterance: "
                f"{[x.construct for x in present]}",
            )
        )

    hits = _clinical_hits(label.rationale)
    if hits:
        reasons.append(
            (REASON_CLINICAL_LANGUAGE, f"rationale contains {hits}; guidelines sec.0 rule 2")
        )

    for item in present:
        if item.construct == "burnout_signal":
            # The most clinically loaded construct in the taxonomy, and the one
            # the rubric says to apply most strictly. Every assertion of it is
            # reviewed, not a sample of them.
            reasons.append(
                (REASON_BURNOUT, f"burnout_signal asserted at intensity {item.intensity}")
            )
        for span in item.evidence_spans:
            if span.strip() == label.text.strip():
                reasons.append(
                    (
                        REASON_SPAN_IS_WHOLE_TEXT,
                        f"{item.construct}: span is the entire utterance, so it localises "
                        "nothing (guidelines sec.1: minimal span)",
                    )
                )

    return reasons


def build_queue(
    labels: Sequence[SilverLabel],
    failures: Sequence[LabelFailure],
    *,
    confidence_threshold: float,
) -> list[ReviewItem]:
    """Assemble the review queue, highest-value reasons first.

    Failures lead. An utterance with no label at all is a hole in the dataset; an
    utterance with a shaky label is at least usable training signal.
    """
    items: list[ReviewItem] = [
        ReviewItem(
            record_id=failure.record_id,
            parent_record_id=failure.parent_record_id,
            text=failure.text,
            reason=REASON_PARSE_FAILURE,
            detail=f"{failure.reason}: {failure.detail}",
            confidence=0.0,
            tier=failure.tier,
            escalated=failure.escalated,
        )
        for failure in failures
    ]

    for label in labels:
        for code, detail in review_reasons(label, confidence_threshold=confidence_threshold):
            items.append(
                ReviewItem(
                    record_id=label.record_id,
                    parent_record_id=label.parent_record_id,
                    text=label.text,
                    reason=code,
                    detail=detail,
                    confidence=label.min_label_confidence,
                    tier=label.tier,
                    escalated=label.escalated,
                )
            )
    return items


def write_queue(items: Sequence[ReviewItem], path: Path | None = None) -> Path:
    target = path or DEFAULT_QUEUE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
    return target


def queue_summary(items: Sequence[ReviewItem]) -> dict[str, int]:
    """Counts per reason, plus the number of distinct utterances involved.

    Both numbers are reported because one utterance can be flagged for several
    reasons, and quoting only the row count would overstate the human workload.
    """
    counts = Counter(item.reason for item in items)
    summary = dict(sorted(counts.items()))
    summary["_rows"] = len(items)
    summary["_distinct_utterances"] = len({item.record_id for item in items})
    return summary


def run_qa(
    run: LabelingRun,
    *,
    confidence_threshold: float,
    path: Path | None = None,
) -> tuple[list[ReviewItem], dict[str, int]]:
    """The Annotation-QA Agent's whole job: flag, write, report."""
    items = build_queue(run.labels, run.failures, confidence_threshold=confidence_threshold)
    write_queue(items, path)
    return items, queue_summary(items)
