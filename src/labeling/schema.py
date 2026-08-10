"""The silver-label schema -- one LLM-proposed label set for one utterance.

This is the first artefact in the project that genuinely **is** a label. Every
prior record type carries `generation_spec`, which is generation metadata
wearing a label's clothes. The distinction is now load-bearing, so it is
enforced by the type rather than left to discipline: `SilverLabel` refuses to
be constructed with a `generation_spec` anywhere in it, and the store refuses
to write one.

Five invariants are checked in `__post_init__` rather than trusted. Each exists
because the alternative failure is silent:

**1. A confidence is mandatory and bounded.** The whole cost-aware design turns
on escalating low-confidence labels. A label with a missing or defaulted
confidence would route as though it were certain, which is the one thing the
routing layer must never do. There is no default value here for the same reason
`InterimRecord` has no way to say `deidentified=False`.

**2. A rationale is mandatory and non-empty.** The paper's second contribution
is two-level interpretability. A label whose justification was dropped cannot
participate in it, and a labeller that stopped producing rationales would
otherwise look identical to one that never had.

**3. Every present label is anchored to a span, and every span is a literal
substring of the utterance.** `docs/annotation_guidelines.md` sec.1 makes a
label with no span invalid. The substring check is the stronger half: an LLM
asked for a quotation will paraphrase it given the chance, and a paraphrased
span cannot be highlighted in a dashboard, cannot be compared with a human
annotator's span, and silently breaks span-level explanation at Phase 16. A
label that cannot point at its evidence is refused, not repaired.

**4. The interpretation modifier only exists where the rubric allows it.**
Guidelines sec.2c: only on `cognitive_anxiety` / `somatic_anxiety`, and only at
intensity >= 1. A modifier on an absent construct is a hallucination with a
plausible shape.

**5. Abstention is representable and is not an error.** `abstained=True` with an
empty label set is a well-formed, first-class answer. Roughly 8.6% of records
plant no construct at all, and inside construct-bearing records the neutral
logistics sentences realise nothing. A schema that could not express "none"
would force the labeller to invent something, and
`docs/annotation_guidelines.md` sec.6 is explicit that over-labelling is the
expensive direction of error.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: Graded constructs take `value="present"`; presence is implied by intensity.
#: Named here rather than re-derived so the parser, the store and the tests
#: cannot disagree about what a graded value looks like.
GRADED_VALUE_PRESENT = "present"
GRADED_VALUE_ABSENT = "absent"
GRADED_VALUES = (GRADED_VALUE_PRESENT, GRADED_VALUE_ABSENT)

#: Constructs the interpretation modifier may attach to (taxonomy.yaml
#: `interpretation_modifier.applies_to`, restated as a constant so a typo is a
#: NameError rather than a silently empty tuple).
MODIFIER_CONSTRUCTS = ("cognitive_anxiety", "somatic_anxiety")
MODIFIER_VALUES = ("facilitative", "debilitative", "unclear")

INTENSITY_MIN = 0
INTENSITY_MAX = 3


class SilverSchemaError(ValueError):
    """Raised when a proposed silver label violates the rubric's structure."""


@dataclass(frozen=True)
class ConstructLabel:
    """One construct's verdict on one utterance.

    `value` is `present`/`absent` for graded constructs and one of the
    construct's own `labels` for categorical ones. Keeping a single field for
    both, rather than two mutually-exclusive optional fields, means downstream
    code never has to branch on label type just to read the answer.
    """

    construct: str
    value: str
    intensity: int
    evidence_spans: tuple[str, ...] = ()
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.construct or not self.construct.strip():
            raise SilverSchemaError("construct must be non-empty")
        if not self.value or not str(self.value).strip():
            raise SilverSchemaError(f"{self.construct}: value must be non-empty")
        if not isinstance(self.intensity, int) or isinstance(self.intensity, bool):
            raise SilverSchemaError(
                f"{self.construct}: intensity must be an int, got {type(self.intensity).__name__}"
            )
        if not INTENSITY_MIN <= self.intensity <= INTENSITY_MAX:
            raise SilverSchemaError(
                f"{self.construct}: intensity {self.intensity} outside "
                f"{INTENSITY_MIN}-{INTENSITY_MAX} (taxonomy.yaml intensity_scale)"
            )
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise SilverSchemaError(
                f"{self.construct}: confidence {self.confidence} outside [0, 1]"
            )
        if self.is_present and not [s for s in self.evidence_spans if s.strip()]:
            raise SilverSchemaError(
                f"{self.construct}: a present label needs at least one evidence span "
                "(docs/annotation_guidelines.md sec.1 -- a label with no span is invalid)"
            )

    @property
    def is_present(self) -> bool:
        """True when this label asserts the construct is expressed.

        Intensity carries presence for graded constructs; for categorical ones a
        `none` value is absence regardless of what intensity was reported, which
        the parser normalises to 0 anyway.
        """
        return self.intensity >= 1 and self.value not in (GRADED_VALUE_ABSENT, "none")

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "value": self.value,
            "intensity": self.intensity,
            "evidence_spans": list(self.evidence_spans),
            "confidence": round(float(self.confidence), 4),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstructLabel:
        return cls(
            construct=str(data["construct"]),
            value=str(data["value"]),
            intensity=int(data["intensity"]),
            evidence_spans=tuple(data.get("evidence_spans") or ()),
            confidence=float(data.get("confidence", 0.0)),
        )


@dataclass
class SilverLabel:
    """The complete silver record for one utterance.

    Carries the routing decision alongside the label deliberately. The Phase 10
    gate asks for "every call carrying a routing decision", and a decision
    recorded only in `logs/cost_ledger.csv` cannot be joined back to the label
    it produced once the ledger has thousands of rows.
    """

    record_id: str
    parent_record_id: str
    source_id: str
    text: str

    labels: tuple[ConstructLabel, ...]
    rationale: str
    confidence: float

    abstained: bool = False
    interpretation_modifier: str | None = None
    low_resilience_explicit: bool = False

    # --- routing evidence -------------------------------------------------
    tier: str = "cheap"
    model: str = ""
    escalated: bool = False
    escalation_reason: str = ""
    offline: bool = True
    prompt_hash: str = ""
    prompt_version: str = ""
    context_used: bool = True

    # --- fan-out evidence -------------------------------------------------
    #: True when this record's label was copied from an identical prompt rather
    #: than paid for. Kept per record so the saving is auditable from the data
    #: itself, not only from a manifest that could drift from it.
    deduplicated: bool = False
    dedup_key: str = ""

    run_id: str = ""
    labeled_on: str = field(
        default_factory=lambda: dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        if not self.record_id or not str(self.record_id).strip():
            raise SilverSchemaError("record_id must be non-empty")
        if not self.parent_record_id or not str(self.parent_record_id).strip():
            raise SilverSchemaError(
                f"silver label {self.record_id!r} has no parent_record_id; the "
                "traceability chain to provenance and consent basis must not break here"
            )
        if not self.text or not str(self.text).strip():
            raise SilverSchemaError(f"silver label {self.record_id!r} has empty text")
        if not self.rationale or not str(self.rationale).strip():
            raise SilverSchemaError(
                f"silver label {self.record_id!r} has no rationale. Two-level "
                "interpretability is contribution #2; an unjustified label cannot "
                "participate in it"
            )
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise SilverSchemaError(
                f"silver label {self.record_id!r}: confidence {self.confidence} outside [0, 1]"
            )

        self.labels = tuple(self.labels)

        seen: set[str] = set()
        for label in self.labels:
            if not isinstance(label, ConstructLabel):
                raise SilverSchemaError(
                    f"silver label {self.record_id!r}: labels must be ConstructLabel, "
                    f"got {type(label).__name__}"
                )
            if label.construct in seen:
                raise SilverSchemaError(
                    f"silver label {self.record_id!r}: construct {label.construct!r} "
                    "appears twice. Guidelines sec.1: one construct label with several "
                    "spans, never two labels for the same construct"
                )
            seen.add(label.construct)
            for span in label.evidence_spans:
                if span and span not in self.text:
                    raise SilverSchemaError(
                        f"silver label {self.record_id!r}: evidence span {span!r} for "
                        f"{label.construct} is not a literal substring of the utterance. "
                        "A paraphrased span cannot be highlighted, cannot be compared "
                        "with a human span, and breaks span-level explanation silently"
                    )

        if self.abstained and self.present_labels:
            raise SilverSchemaError(
                f"silver label {self.record_id!r} claims abstention but asserts "
                f"{[label.construct for label in self.present_labels]}"
            )

        if self.interpretation_modifier is not None:
            if self.interpretation_modifier not in MODIFIER_VALUES:
                raise SilverSchemaError(
                    f"silver label {self.record_id!r}: interpretation_modifier "
                    f"{self.interpretation_modifier!r} not in {MODIFIER_VALUES}"
                )
            anxious = [
                label
                for label in self.labels
                if label.construct in MODIFIER_CONSTRUCTS and label.intensity >= 1
            ]
            if not anxious:
                raise SilverSchemaError(
                    f"silver label {self.record_id!r}: interpretation_modifier set with no "
                    f"{' or '.join(MODIFIER_CONSTRUCTS)} at intensity >= 1 "
                    "(docs/annotation_guidelines.md sec.2c)"
                )

    # -- derived ------------------------------------------------------------

    @property
    def present_labels(self) -> tuple[ConstructLabel, ...]:
        return tuple(label for label in self.labels if label.is_present)

    @property
    def min_label_confidence(self) -> float:
        """The weakest link. Escalation reads this, not the mean.

        A record whose confident labels average away one shaky one is exactly
        the record a human should see, so the aggregate is a minimum rather
        than an average.
        """
        if not self.labels:
            return float(self.confidence)
        return min(float(self.confidence), min(float(x.confidence) for x in self.labels))

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["labels"] = [label.to_dict() for label in self.labels]
        data["confidence"] = round(float(self.confidence), 4)
        # Stated on every row rather than only in the manifest: a JSONL file
        # gets copied out of its directory, and this warning has to travel with
        # the rows themselves.
        data["NOTE"] = (
            "Silver (LLM-proposed) label, NOT human ground truth. Never evaluate "
            "against generation_spec -- see docs/labeling.md sec.6."
        )
        return data

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SilverLabel:
        known = set(cls.__dataclass_fields__)
        payload = {k: v for k, v in data.items() if k in known}
        payload["labels"] = tuple(ConstructLabel.from_dict(item) for item in data.get("labels", ()))
        return cls(**payload)

    @classmethod
    def from_json_line(cls, line: str) -> SilverLabel:
        return cls.from_dict(json.loads(line))


#: Field names that must never appear in a silver record. `generation_spec` is
#: the whole point: it is the corpus generator's own template choices, and
#: storing it beside a real label is how a future session ends up evaluating
#: silver against it. The store enforces this; the constant is here so the
#: reason lives next to the schema it protects.
FORBIDDEN_FIELDS: tuple[str, ...] = ("generation_spec", "planted_constructs")
