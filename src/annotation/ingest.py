"""Read Potato's output back into typed `GoldLabel`s.

Same governing rule as `src/labeling/parser.py`: **refuse rather than coerce.**
The reasoning is stronger here, not weaker. A coerced silver label is a bad
training signal; a coerced gold label is a corrupted measuring instrument, and
every number in the paper is measured against it.

## What Potato gives us, and the one thing it cannot

Potato's span annotations record the highlighted surface text and its offsets
into the displayed item. Because `potato_project.py` puts the **utterance** in
`text` and the parent record in a separate `pure_display` scheme, those offsets
are offsets into the utterance -- which is what `GoldLabel` needs.

The one thing the UI cannot enforce is the rubric's coupling rules: that a
present construct has a span, that intensity 0 and a span contradict each other,
that the interpretation modifier requires an anxiety construct at intensity >= 1.
Potato will happily record any combination a tired person clicks at item 300.
So those are checked here, and a violation is reported to the annotator to fix
rather than silently repaired.

## Two repairs that ARE performed, because they carry no judgement

1. **A span whose label names a categorical pole sets both the construct's value
   and its presence.** `motivation_orientation:avoidance` becomes
   `value="avoidance"`. That is decoding the encoding `potato_project.py` chose,
   not an opinion.
2. **Two poles of the same categorical construct become `mixed`.** Guidelines
   sec.2b defines `mixed` as exactly this -- both poles present, each with its
   own span -- and requires a span for each. Deriving it from the spans is
   therefore more faithful than offering a `mixed` button, which an annotator
   could press without evidencing either side.

Everything else raises `IngestError`, which `scripts/run_annotation.py` prints
as a fix-list against the annotator's own item ids.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .potato_output import PotatoPass, read_pass
from .schema import MODIFIER_CONSTRUCTS, GoldConstruct, GoldLabel, GoldSchemaError

#: The flags multiselect in `potato_project.py`. Matched by prefix rather than
#: by full string so that reflowing the human-readable half of a label does not
#: silently stop the flag being recorded.
FLAG_LOW_RESILIENCE = "low_resilience_explicit"
FLAG_UNCERTAIN = "uncertain"


class IngestError(RuntimeError):
    """One annotated item that cannot be read as a valid gold label."""

    def __init__(self, record_id: str, reason: str, detail: str) -> None:
        self.record_id = record_id
        self.reason = reason
        self.detail = detail
        super().__init__(f"{record_id}: {reason} -- {detail}")


@dataclass
class IngestReport:
    """What one ingest produced, and what it refused."""

    labels: list[GoldLabel]
    errors: list[IngestError]
    skipped_unannotated: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        return (
            f"{len(self.labels)} label(s) ingested, {len(self.errors)} refused, "
            f"{self.skipped_unannotated} item(s) not yet annotated"
        )


def _intensity_from_label(raw: Any) -> int:
    """`"2 moderate"` -> 2. Refuses anything else."""
    text = str(raw).strip()
    if not text:
        return 0
    head = text.split()[0]
    if not head.isdigit():
        raise ValueError(f"cannot read an intensity from {raw!r}")
    value = int(head)
    if not 0 <= value <= 3:
        raise ValueError(f"intensity {value} outside 0-3")
    return value


def _collect_spans(raw_spans: Any, *, record_id: str = "<unknown>") -> dict[str, list[str]]:
    """Group highlighted surface strings by their span label.

    A labelled span with no recoverable surface text is **refused**, not
    skipped. The earlier version skipped it, which meant that against Potato
    2.7.1 -- whose spans carry offsets and no surface text at all (see
    `potato_output.py`) -- every span vanished silently and the item was then
    misread as unannotated. Losing evidence quietly is the one failure mode this
    parser exists to prevent.
    """
    grouped: dict[str, list[str]] = {}
    if not raw_spans:
        return grouped
    if isinstance(raw_spans, dict):
        raw_spans = list(raw_spans.values())
    for span in raw_spans:
        if not isinstance(span, dict):
            continue
        label = str(span.get("annotation") or span.get("label") or "").strip()
        surface = str(span.get("span") or span.get("text") or "").strip()
        if not label:
            continue
        if not surface:
            raise IngestError(
                record_id,
                "SPAN_WITHOUT_SURFACE",
                f"span labelled {label!r} carries no text. Potato records spans as "
                "start/end offsets, so this output must be normalised through "
                "src/annotation/potato_output.py before parsing",
            )
        grouped.setdefault(label, []).append(surface)
    return grouped


def parse_annotation(
    payload: dict[str, Any],
    *,
    item_text: str,
    annotator_id: str,
    batch: str,
    valid_constructs: dict[str, dict[str, Any]],
) -> GoldLabel:
    """Turn one Potato annotation record into a `GoldLabel`, or raise."""
    record_id = str(payload.get("id") or payload.get("item_id") or "").strip()
    if not record_id:
        raise IngestError("<unknown>", "NO_ID", "annotation carries no item id")

    annotations = payload.get("annotations") or payload.get("label_annotations") or {}
    if not isinstance(annotations, dict):
        raise IngestError(record_id, "BAD_SHAPE", "annotations is not an object")

    spans = _collect_spans(
        payload.get("span_annotations") or annotations.get("evidence"), record_id=record_id
    )

    # Escalation: Potato's `bad_text_label` checkbox on the span scheme.
    escalated = bool(
        annotations.get("evidence:::bad_text")
        or annotations.get("bad_text")
        or payload.get("bad_text")
    )

    flags_raw = annotations.get("flags") or {}
    flags = set(flags_raw.keys()) if isinstance(flags_raw, dict) else set(flags_raw or [])
    flat_flags = " ".join(str(f) for f in flags)
    low_resilience = FLAG_LOW_RESILIENCE in flat_flags
    uncertain = FLAG_UNCERTAIN in flat_flags and "low_resilience" not in FLAG_UNCERTAIN

    note = str(annotations.get("note") or "").strip()

    if escalated:
        return GoldLabel(
            record_id=record_id,
            parent_record_id=str(payload.get("parent_record_id") or record_id.split("#")[0]),
            text=item_text,
            annotator_id=annotator_id,
            batch=batch,
            constructs=(),
            uncertain=uncertain,
            escalate=True,
            escalate_reason=note or "marked ESCALATE in the annotation tool, no reason given",
            note=note,
        )

    # -- assemble one GoldConstruct per construct the annotator touched ------
    per_construct: dict[str, dict[str, Any]] = {}

    for label, surfaces in spans.items():
        construct, _, pole = label.partition(":")
        if construct not in valid_constructs:
            raise IngestError(
                record_id, "UNKNOWN_CONSTRUCT", f"span label {label!r} is not in the taxonomy"
            )
        entry = per_construct.setdefault(construct, {"poles": set(), "spans": []})
        entry["spans"].extend(surfaces)
        if pole:
            entry["poles"].add(pole)

    for key, raw in annotations.items():
        if not str(key).startswith("intensity_"):
            continue
        construct = str(key)[len("intensity_") :]
        if construct not in valid_constructs:
            raise IngestError(
                record_id, "UNKNOWN_CONSTRUCT", f"intensity given for unknown {construct!r}"
            )
        value = raw
        if isinstance(raw, dict):
            chosen = [k for k, v in raw.items() if v]
            value = chosen[0] if chosen else ""
        try:
            intensity = _intensity_from_label(value)
        except ValueError as exc:
            raise IngestError(record_id, "BAD_INTENSITY", str(exc)) from exc
        per_construct.setdefault(construct, {"poles": set(), "spans": []})["intensity"] = intensity

    constructs: list[GoldConstruct] = []
    for construct, entry in sorted(per_construct.items()):
        spec = valid_constructs[construct]
        intensity = int(entry.get("intensity", 0))
        surfaces = tuple(dict.fromkeys(entry["spans"]))
        poles = entry["poles"]

        if spec.get("labels"):
            if len(poles) > 1:
                value = "mixed"
            elif poles:
                value = next(iter(poles))
            else:
                value = "none"
        else:
            value = "present" if (intensity >= 1 or surfaces) else "absent"

        # The coupling rules the UI cannot enforce.
        if surfaces and intensity == 0:
            raise IngestError(
                record_id,
                "SPAN_WITHOUT_INTENSITY",
                f"{construct}: a span was marked but intensity is 0. Either set an "
                "intensity of 1-3 or remove the span (guidelines sec.2a)",
            )
        if intensity >= 1 and not surfaces:
            raise IngestError(
                record_id,
                "INTENSITY_WITHOUT_SPAN",
                f"{construct}: intensity {intensity} with no span. Every non-zero label "
                "needs at least one span (guidelines sec.1)",
            )
        if value == "mixed" and len(surfaces) < 2:
            raise IngestError(
                record_id,
                "MIXED_WITHOUT_BOTH_SPANS",
                f"{construct}: mixed requires a span for EACH pole (guidelines sec.2b)",
            )
        if intensity == 0 and value in ("none", "absent"):
            continue

        try:
            constructs.append(
                GoldConstruct(
                    construct=construct,
                    value=value,
                    intensity=intensity,
                    evidence_spans=surfaces,
                )
            )
        except GoldSchemaError as exc:
            raise IngestError(record_id, "SCHEMA_VIOLATION", str(exc)) from exc

    modifier_raw = annotations.get("interpretation_modifier")
    if isinstance(modifier_raw, dict):
        chosen = [k for k, v in modifier_raw.items() if v]
        modifier_raw = chosen[0] if chosen else None
    modifier = str(modifier_raw).strip() if modifier_raw else None
    if modifier in ("", "None", "none"):
        modifier = None
    if modifier and not any(
        c.construct in MODIFIER_CONSTRUCTS and c.intensity >= 1 for c in constructs
    ):
        raise IngestError(
            record_id,
            "MODIFIER_WITHOUT_ANXIETY",
            f"interpretation_modifier={modifier!r} but neither anxiety construct is "
            ">= 1 (guidelines sec.2c). Clear the modifier or set the intensity",
        )

    try:
        return GoldLabel(
            record_id=record_id,
            parent_record_id=str(payload.get("parent_record_id") or record_id.split("#")[0]),
            text=item_text,
            annotator_id=annotator_id,
            batch=batch,
            constructs=tuple(constructs),
            interpretation_modifier=modifier,
            low_resilience_explicit=low_resilience,
            uncertain=uncertain,
            note=note,
        )
    except GoldSchemaError as exc:
        raise IngestError(record_id, "SCHEMA_VIOLATION", str(exc)) from exc


def ingest_passes(
    passes: Sequence[PotatoPass],
    *,
    item_texts: dict[str, str],
    annotator_id: str,
    batch: str,
    valid_constructs: dict[str, Any],
) -> IngestReport:
    """Ingest real Potato 2.7.1 output. **This is the production path.**

    `ingest_potato` below reads an already-normalised JSONL and is kept for
    hand-prepared input and for the tests that exercise the rubric rules
    directly. Anything coming out of an actual Potato server arrives here,
    because only `potato_output.read_pass` knows how to turn offset-only spans
    back into evidence.
    """
    labels: list[GoldLabel] = []
    errors: list[IngestError] = []

    for potato_pass in passes:
        payloads, problems = read_pass(potato_pass, item_texts=item_texts)
        for record_id, message in problems:
            reason = "UNKNOWN_ITEM" if "not in the batch" in message else "UNREADABLE_SPAN"
            errors.append(IngestError(record_id or potato_pass.path.name, reason, message))

        for payload in payloads:
            try:
                labels.append(
                    parse_annotation(
                        payload,
                        item_text=item_texts[payload["id"]],
                        annotator_id=annotator_id,
                        batch=batch,
                        valid_constructs=valid_constructs,
                    )
                )
            except IngestError as exc:
                errors.append(exc)

    skipped = len(item_texts) - len({x.record_id for x in labels} | {e.record_id for e in errors})
    return IngestReport(labels=labels, errors=errors, skipped_unannotated=max(skipped, 0))


def ingest_potato(
    annotation_paths: Sequence[Path],
    *,
    item_texts: dict[str, str],
    annotator_id: str,
    batch: str,
    valid_constructs: dict[str, dict[str, Any]],
) -> IngestReport:
    """Read one annotator's Potato output directory into gold labels."""
    labels: list[GoldLabel] = []
    errors: list[IngestError] = []
    skipped = 0

    for path in annotation_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(IngestError(path.name, "NOT_JSON", str(exc)))
                continue

            record_id = str(payload.get("id") or payload.get("item_id") or "")
            text = item_texts.get(record_id)
            if text is None:
                errors.append(
                    IngestError(
                        record_id or path.name,
                        "UNKNOWN_ITEM",
                        "this id is not in the batch that was handed out. An annotation "
                        "of an item nobody was asked to label cannot enter the gold set",
                    )
                )
                continue

            annotations = payload.get("annotations") or payload.get("label_annotations") or {}
            spans = payload.get("span_annotations")
            if not annotations and not spans:
                skipped += 1
                continue

            try:
                labels.append(
                    parse_annotation(
                        payload,
                        item_text=text,
                        annotator_id=annotator_id,
                        batch=batch,
                        valid_constructs=valid_constructs,
                    )
                )
            except IngestError as exc:
                errors.append(exc)

    return IngestReport(labels=labels, errors=errors, skipped_unannotated=skipped)
