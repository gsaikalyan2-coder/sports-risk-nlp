"""The gold-label schema -- one human annotator's judgement on one utterance.

Deliberately close to `src/labeling/schema.py`, and deliberately not identical.
The similarities let Phase 14 compare silver against gold without a translation
layer. The three differences are the interesting part.

## Difference 1: no confidence, because humans do not have one

`SilverLabel` requires a calibrated `confidence` in [0,1]; the routing layer is
built on it. A human annotator does not produce a calibrated probability, and
asking for one would manufacture a number that looks like the model's and means
something entirely different. `docs/annotation_guidelines.md` sec.7 specifies
what humans give instead:

* `uncertain=True` -- "I labelled it but would not defend it." Routed to
  adjudication and reported in the agreement analysis.
* `escalate=True` -- "I am not labelling this at all": unreadable, off-topic,
  not athlete-authored, not pre-competition, or **identifying information
  survived de-identification**. An escalated item carries no labels by
  construction, and the last of those reasons is an ethics incident, not a data
  problem.

## Difference 2: every label names its annotator

Agreement is a property of a *pair* of annotators over the same item.
`annotator_id` is mandatory and is checked against a roster of real people
(`config/annotators.yaml`), because the whole value of `data/gold/` is that a
human produced it.

## Difference 3: authorship is asserted, and machines are refused

`author_kind` may only be `human`. There is no enum member for a model. This is
the schema-level expression of `CLAUDE.md` sec.4's "agents never write
`data/gold/`" -- a rule that has, until now, been enforced only by path guards
in three stores. A path guard stops an agent writing to the wrong directory; it
does not stop a well-meaning future session from converting silver into gold
and writing it there through the front door.

## What is shared, and why it is shared exactly

Span validity is enforced identically to `SilverLabel`: every span on a present
label must be a **literal substring of the utterance**. For the model that check
catches paraphrase. For a human it catches a mis-copied offset, which is the
overwhelmingly common failure when a person transcribes character positions by
hand -- and it is the reason this project uses an annotation tool at all rather
than a spreadsheet.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ANNOTATORS_PATH = REPO_ROOT / "config" / "annotators.yaml"

AUTHOR_HUMAN = "human"

MODIFIER_CONSTRUCTS = ("cognitive_anxiety", "somatic_anxiety")
MODIFIER_VALUES = ("facilitative", "debilitative", "unclear")

INTENSITY_MIN = 0
INTENSITY_MAX = 3


class GoldSchemaError(ValueError):
    """Raised when a proposed gold annotation violates the rubric's structure."""


@dataclass(frozen=True)
class GoldConstruct:
    """One construct's verdict from one annotator on one utterance."""

    construct: str
    value: str
    intensity: int
    evidence_spans: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.construct.strip():
            raise GoldSchemaError("construct must be non-empty")
        if not str(self.value).strip():
            raise GoldSchemaError(f"{self.construct}: value must be non-empty")
        if not isinstance(self.intensity, int) or isinstance(self.intensity, bool):
            raise GoldSchemaError(f"{self.construct}: intensity must be an int")
        if not INTENSITY_MIN <= self.intensity <= INTENSITY_MAX:
            raise GoldSchemaError(
                f"{self.construct}: intensity {self.intensity} outside "
                f"{INTENSITY_MIN}-{INTENSITY_MAX}"
            )
        if self.is_present and not [s for s in self.evidence_spans if s.strip()]:
            raise GoldSchemaError(
                f"{self.construct}: a present label needs at least one span "
                "(docs/annotation_guidelines.md sec.1 -- a label with no span is invalid)"
            )

    @property
    def is_present(self) -> bool:
        return self.intensity >= 1 and self.value not in ("none", "absent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "value": self.value,
            "intensity": self.intensity,
            "evidence_spans": list(self.evidence_spans),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldConstruct:
        return cls(
            construct=str(data["construct"]),
            value=str(data["value"]),
            intensity=int(data["intensity"]),
            evidence_spans=tuple(data.get("evidence_spans") or ()),
        )


@dataclass
class GoldLabel:
    """One annotator's complete judgement on one utterance."""

    record_id: str
    parent_record_id: str
    text: str
    annotator_id: str
    batch: str

    constructs: tuple[GoldConstruct, ...] = ()
    interpretation_modifier: str | None = None
    low_resilience_explicit: bool = False
    uncertain: bool = False
    escalate: bool = False
    escalate_reason: str = ""
    note: str = ""

    author_kind: str = AUTHOR_HUMAN
    guidelines_version: str = "1.0"
    annotated_on: str = field(
        default_factory=lambda: dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    )

    def __post_init__(self) -> None:
        if self.author_kind != AUTHOR_HUMAN:
            raise GoldSchemaError(
                f"gold label {self.record_id!r} claims author_kind={self.author_kind!r}. "
                "data/gold/ is human-owned (CLAUDE.md sec.4). There is no machine "
                "author for a gold label, and silver labels belong in "
                "data/processed/silver/"
            )
        if not self.record_id.strip():
            raise GoldSchemaError("record_id must be non-empty")
        if not self.annotator_id.strip():
            raise GoldSchemaError(
                f"gold label {self.record_id!r} has no annotator_id. Agreement is a "
                "property of a pair of annotators; an anonymous label cannot enter one"
            )
        if not self.text.strip():
            raise GoldSchemaError(f"gold label {self.record_id!r} has empty text")

        self.constructs = tuple(self.constructs)

        if self.escalate:
            if self.present_constructs:
                raise GoldSchemaError(
                    f"gold label {self.record_id!r} is escalated but asserts "
                    f"{[c.construct for c in self.present_constructs]}. Guidelines sec.7: "
                    "mark escalate and DO NOT label it"
                )
            if not self.escalate_reason.strip():
                raise GoldSchemaError(
                    f"gold label {self.record_id!r} is escalated with no reason. One of "
                    "these is an ethics incident (surviving identifiers) and the others "
                    "are not; the register has to be able to tell them apart"
                )

        seen: set[str] = set()
        for item in self.constructs:
            if not isinstance(item, GoldConstruct):
                raise GoldSchemaError(
                    f"gold label {self.record_id!r}: expected GoldConstruct, "
                    f"got {type(item).__name__}"
                )
            if item.construct in seen:
                raise GoldSchemaError(
                    f"gold label {self.record_id!r}: {item.construct!r} appears twice. "
                    "Guidelines sec.1: one construct label with several spans"
                )
            seen.add(item.construct)
            for span in item.evidence_spans:
                if span and span not in self.text:
                    raise GoldSchemaError(
                        f"gold label {self.record_id!r}: span {span!r} for "
                        f"{item.construct} is not a literal substring of the utterance"
                    )

        if self.interpretation_modifier is not None:
            if self.interpretation_modifier not in MODIFIER_VALUES:
                raise GoldSchemaError(
                    f"gold label {self.record_id!r}: interpretation_modifier "
                    f"{self.interpretation_modifier!r} not in {MODIFIER_VALUES}"
                )
            if not any(
                c.construct in MODIFIER_CONSTRUCTS and c.intensity >= 1 for c in self.constructs
            ):
                raise GoldSchemaError(
                    f"gold label {self.record_id!r}: interpretation_modifier set with no "
                    f"{' or '.join(MODIFIER_CONSTRUCTS)} at intensity >= 1 "
                    "(guidelines sec.2c)"
                )

    # -- derived ------------------------------------------------------------

    @property
    def present_constructs(self) -> tuple[GoldConstruct, ...]:
        return tuple(c for c in self.constructs if c.is_present)

    @property
    def abstained(self) -> bool:
        """No construct expressed. A valid, expected answer -- not a gap."""
        return not self.escalate and not self.present_constructs

    def value_for(self, construct: str) -> str:
        """This annotator's categorical verdict, `none` when not asserted.

        The default matters for agreement: an annotator who did not mark a
        construct is asserting it is absent, which is a real judgement and must
        enter the kappa as one. Treating it as missing data would silently
        restrict every kappa to the items both annotators happened to mark,
        which is the subset they already agree on.
        """
        for item in self.constructs:
            if item.construct == construct:
                return item.value if item.is_present else "none"
        return "none"

    def intensity_for(self, construct: str) -> int:
        for item in self.constructs:
            if item.construct == construct:
                return item.intensity
        return 0

    def spans_for(self, construct: str) -> tuple[str, ...]:
        for item in self.constructs:
            if item.construct == construct:
                return item.evidence_spans
        return ()

    # -- serialisation ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["constructs"] = [c.to_dict() for c in self.constructs]
        return data

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldLabel:
        known = set(cls.__dataclass_fields__)
        payload = {k: v for k, v in data.items() if k in known}
        payload["constructs"] = tuple(
            GoldConstruct.from_dict(c) for c in data.get("constructs", ())
        )
        return cls(**payload)

    @classmethod
    def from_json_line(cls, line: str) -> GoldLabel:
        return cls.from_dict(json.loads(line))


# ---------------------------------------------------------------------------
# The annotator roster
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Annotator:
    """One real person who may write into `data/gold/`."""

    annotator_id: str
    role: str
    is_owner: bool = False

    def __post_init__(self) -> None:
        if not self.annotator_id.strip():
            raise GoldSchemaError("annotator_id must be non-empty")


def load_annotators(path: Path | None = None) -> dict[str, Annotator]:
    """Load `config/annotators.yaml`.

    A roster file rather than a free-text field, for one reason: agreement
    statistics are only meaningful if "annotator A" means the same person on
    every item and across every batch. A typo in an id silently creates a third
    annotator with a handful of items and a wild kappa.
    """
    target = path or ANNOTATORS_PATH
    if not target.exists():
        raise GoldSchemaError(
            f"{target} does not exist. Phase 11 needs a declared roster of real "
            "people before any gold label can be written"
        )
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    entries = raw.get("annotators") or []
    roster = {
        str(e["annotator_id"]): Annotator(
            annotator_id=str(e["annotator_id"]),
            role=str(e.get("role", "annotator")),
            is_owner=bool(e.get("is_owner", False)),
        )
        for e in entries
    }
    if not roster:
        raise GoldSchemaError(f"{target} declares no annotators")
    return roster
