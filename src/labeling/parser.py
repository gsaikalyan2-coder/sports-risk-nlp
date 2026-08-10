"""Strict parsing of a model's label response.

The governing rule: **refuse malformed output rather than coerce it.**

Coercion is the tempting path and it is the wrong one. A parser that quietly
clamps `intensity: 7` to 3, invents a confidence of 0.5 where none was given, or
fuzzy-matches a paraphrased span onto the nearest real substring produces a
dataset that *looks* clean and is silently full of the parser's own opinions.
Those opinions are then indistinguishable from the model's, they never appear in
any metric, and at Phase 14 they are attributed to the labeller.

So the only repairs performed here are ones with no semantic content:

* stripping a ``` fence, because models wrap JSON in fences regardless of
  instructions and unwrapping is not interpretation;
* dropping labels whose intensity is 0 with a `none`/`absent` value, because the
  schema treats an unlisted construct as absent and an explicitly-absent one as
  the same claim -- keeping both representations would make two identical
  datasets compare unequal;
* normalising a categorical `none` to intensity 0, which the rubric already
  mandates (`docs/annotation_guidelines.md` sec.2b).

Everything else raises. A `LabelParseError` is not a crash: the runner catches
it, escalates once, and if the escalated answer is also malformed the utterance
goes to the human review queue **unlabelled**. An unlabelled utterance is a
known gap. A guessed one is a corrupted row.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .schema import (
    GRADED_VALUE_ABSENT,
    GRADED_VALUE_PRESENT,
    MODIFIER_CONSTRUCTS,
    MODIFIER_VALUES,
    ConstructLabel,
    SilverSchemaError,
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)

#: A response that is 0 labels AND does not say so is ambiguous: did the model
#: abstain, or did it fail to answer? The prompt requires `abstain` explicitly,
#: so a missing key is a malformed response rather than a default.
_REQUIRED_KEYS = ("abstain", "rationale", "confidence", "labels")


class LabelParseError(ValueError):
    """Raised when a model response cannot be read as a valid label set.

    Carries `reason` as a short machine-readable code so the review queue can
    be grouped by failure mode without regex over English.
    """

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class ParsedResponse:
    """A model response that survived validation. Not yet a `SilverLabel`."""

    abstain: bool
    rationale: str
    confidence: float
    labels: tuple[ConstructLabel, ...]
    interpretation_modifier: str | None
    low_resilience_explicit: bool


def _strip_fence(body: str) -> str:
    body = body.strip()
    match = _FENCE_RE.match(body)
    return match.group(1) if match else body


def _as_float(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise LabelParseError("BAD_CONFIDENCE", f"{field} is not a number: {value!r}") from exc
    if not 0.0 <= number <= 1.0:
        raise LabelParseError("BAD_CONFIDENCE", f"{field} = {number} is outside [0, 1]")
    return number


def _as_intensity(value: Any, construct: str) -> int:
    # bool is an int subclass in Python; `True` must not silently become 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LabelParseError("BAD_INTENSITY", f"{construct}: intensity {value!r} is not a number")
    if float(value) != int(value):
        raise LabelParseError(
            "BAD_INTENSITY", f"{construct}: intensity {value!r} is not an integer"
        )
    number = int(value)
    if not 0 <= number <= 3:
        raise LabelParseError("BAD_INTENSITY", f"{construct}: intensity {number} outside 0-3")
    return number


def parse_response(
    raw: str,
    *,
    text: str,
    valid_constructs: dict[str, dict[str, Any]],
) -> ParsedResponse:
    """Validate one model response against the taxonomy and the target text.

    `valid_constructs` is the taxonomy's `constructs` mapping. It is passed in
    rather than loaded here so that a test can validate against a small
    taxonomy without touching `config/taxonomy.yaml`, and so this module has no
    filesystem dependency at all.
    """
    body = _strip_fence(raw or "")
    if not body:
        raise LabelParseError("EMPTY_RESPONSE", "model returned no text")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LabelParseError("NOT_JSON", f"{exc.msg} at char {exc.pos}") from exc

    if not isinstance(payload, dict):
        raise LabelParseError("NOT_AN_OBJECT", f"top level is {type(payload).__name__}, not object")

    missing = [key for key in _REQUIRED_KEYS if key not in payload]
    if missing:
        raise LabelParseError("MISSING_KEYS", f"response omits {missing}")

    abstain = payload["abstain"]
    if not isinstance(abstain, bool):
        raise LabelParseError("BAD_ABSTAIN", f"abstain must be a boolean, got {abstain!r}")

    rationale = str(payload.get("rationale") or "").strip()
    if not rationale:
        raise LabelParseError("NO_RATIONALE", "rationale is empty")

    confidence = _as_float(payload["confidence"], "confidence")

    raw_labels = payload["labels"]
    if not isinstance(raw_labels, list):
        raise LabelParseError(
            "BAD_LABELS", f"labels must be a list, got {type(raw_labels).__name__}"
        )

    labels: list[ConstructLabel] = []
    seen: set[str] = set()
    for item in raw_labels:
        if not isinstance(item, dict):
            raise LabelParseError("BAD_LABEL_ITEM", f"label entry is {type(item).__name__}")
        construct = str(item.get("construct", "")).strip()
        if construct not in valid_constructs:
            # CLAUDE.md sec.3: agents never invent constructs. A model naming
            # `motivation` or `anxiety` is not close enough -- the taxonomy is
            # frozen and the label would be unmappable.
            raise LabelParseError(
                "UNKNOWN_CONSTRUCT",
                f"{construct!r} is not in the frozen taxonomy",
            )
        if construct in seen:
            raise LabelParseError("DUPLICATE_CONSTRUCT", f"{construct} listed twice")
        seen.add(construct)

        spec = valid_constructs[construct]
        intensity = _as_intensity(item.get("intensity"), construct)
        value = str(item.get("value", "")).strip()
        allowed = spec.get("labels")
        if allowed:
            if value not in allowed:
                raise LabelParseError(
                    "BAD_CATEGORICAL_VALUE",
                    f"{construct}: {value!r} not in {list(allowed)}",
                )
            if value == "none":
                # Rubric: `none` always takes intensity 0. Normalising rather
                # than rejecting because the two statements are identical in
                # meaning and models emit both.
                intensity = 0
        elif value not in (GRADED_VALUE_PRESENT, GRADED_VALUE_ABSENT):
            raise LabelParseError(
                "BAD_GRADED_VALUE",
                f"{construct}: graded value must be 'present' or 'absent', got {value!r}",
            )
        elif value == GRADED_VALUE_ABSENT:
            intensity = 0

        spans = item.get("evidence_spans") or []
        if not isinstance(spans, list):
            raise LabelParseError("BAD_SPANS", f"{construct}: evidence_spans is not a list")
        clean_spans = tuple(str(s) for s in spans if str(s).strip())
        for span in clean_spans:
            if span not in text:
                raise LabelParseError(
                    "SPAN_NOT_IN_TEXT",
                    f"{construct}: {span!r} is not a literal substring of the utterance",
                )

        label_confidence = _as_float(item.get("confidence", confidence), f"{construct}.confidence")

        absent = intensity == 0 and (value in ("none", GRADED_VALUE_ABSENT) or not clean_spans)
        if absent:
            # An explicit absence carries no information the schema does not
            # already encode by omission. Dropping it keeps one canonical form.
            continue

        try:
            labels.append(
                ConstructLabel(
                    construct=construct,
                    value=value,
                    intensity=intensity,
                    evidence_spans=clean_spans,
                    confidence=label_confidence,
                )
            )
        except SilverSchemaError as exc:
            raise LabelParseError("SCHEMA_VIOLATION", str(exc)) from exc

    modifier = payload.get("interpretation_modifier")
    if modifier is not None:
        modifier = str(modifier).strip().lower()
        if modifier in ("", "null", "none"):
            modifier = None
        elif modifier not in MODIFIER_VALUES:
            raise LabelParseError(
                "BAD_MODIFIER", f"interpretation_modifier {modifier!r} not in {MODIFIER_VALUES}"
            )
    if modifier is not None and not any(
        label.construct in MODIFIER_CONSTRUCTS and label.intensity >= 1 for label in labels
    ):
        # Dropped rather than raised: the modifier is an optional refinement,
        # and discarding an inapplicable one loses nothing, whereas discarding
        # a whole otherwise-valid label set over it would lose real labels.
        modifier = None

    low_resilience = payload.get("low_resilience_explicit", False)
    if not isinstance(low_resilience, bool):
        raise LabelParseError(
            "BAD_LOW_RESILIENCE", f"low_resilience_explicit must be boolean, got {low_resilience!r}"
        )

    present = [label for label in labels if label.is_present]
    if abstain and present:
        raise LabelParseError(
            "CONTRADICTORY_ABSTENTION",
            f"abstain=true but asserts {[label.construct for label in present]}",
        )
    if not abstain and not present:
        # Not an error. The model listed nothing present, which IS abstention;
        # it just failed to set the flag. Normalised so that "no constructs" has
        # exactly one representation in the dataset.
        abstain = True

    return ParsedResponse(
        abstain=abstain,
        rationale=rationale,
        confidence=confidence,
        labels=tuple(labels),
        interpretation_modifier=modifier,
        low_resilience_explicit=bool(low_resilience),
    )
