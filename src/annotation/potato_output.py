"""Read Potato 2.7.1's **actual** on-disk artifacts.

## Why this module exists at all

`phase11_handover.md` Part D listed OPEN-027 as "the parser has never met real
Potato output -- five minutes converts an unexercised path into a tested one".
Those five minutes were spent, and the path did not work. This module is the
fix, and the discrepancy is worth recording because it is the same failure
`docs/open_issues.md` records as OPEN-007 and OPEN-008: **a code path that was
written against an assumed interface and never executed against the real one.**

`src/annotation/ingest.py` was written expecting a JSONL file per annotator
whose rows look like `{"id": ..., "annotations": {...}, "span_annotations":
[{"annotation": ..., "span": ...}]}`. Potato 2.7.1 writes nothing of the kind.
Three concrete mismatches, each read out of the installed package rather than
inferred:

| What ingest assumed | What Potato 2.7.1 actually writes |
|---|---|
| `annotation_output/**/*.jsonl` | `annotation_output/<user_id>/user_state.json` |
| item key `id` | `instance_id`, and in the state file the instance id is a **dict key** |
| span carries its surface text under `span`/`text` | span carries `start`/`end` **offsets only** |

The third was the dangerous one. `_collect_spans` skipped any span whose
surface string was empty, so against real output **every span would have been
silently dropped** -- and an item annotated with spans but no intensity would
then have been counted as "not yet annotated" rather than refused. A parser
that loses evidence quietly is worse than one that crashes, and this one lost
all of it.

## The two artifacts, and which one is authoritative

1. **`<output_annotation_dir>/<user_id>/user_state.json`** -- written by
   `UserState.save()` on every annotation, atomically. Always present. This is
   the authoritative record and the default this module reads.
2. **`.../exports/annotations.jsonl`** -- written only if the operator runs
   `python -m potato.export` or configures auto-export. Shape:
   `{instance_id, user_id, labels, spans, links}`.

Both are supported because an annotator who exports and hands over the export
should not get a different answer from one who hands over the raw project
directory. They are normalised to one internal payload, so `parse_annotation`
has a single input shape and the rubric's coupling rules are checked in exactly
one place.

## Offsets are an improvement, not an inconvenience

`SilverLabel` requires every evidence span to be a literal substring of the
utterance, because a paraphrased span breaks span-level explanation silently
(see `docs/labeling.md`). Gold now gets that property **by construction**: the
surface text is produced by slicing the utterance with Potato's own offsets, so
it cannot be anything but a substring. An offset pair that does not land inside
the utterance is refused rather than clipped -- a clipped span is a span the
annotator did not mark.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Potato's span scheme name, as emitted by `potato_project.build_config`.
SPAN_SCHEMA = "evidence"

#: The label Potato records for a span scheme's `bad_text_label` checkbox.
BAD_TEXT_LABEL = "bad_text"

#: Potato's default label name for a single-textarea `text` scheme
#: (`server_utils/schemas/textbox.py`: `labels = ["text_box"]`).
TEXT_BOX_LABEL = "text_box"

#: The filename `UserState.save()` writes.
USER_STATE_FILENAME = "user_state.json"


class PotatoOutputError(RuntimeError):
    """Potato's output directory is not shaped the way this version writes."""


@dataclass(frozen=True)
class PotatoPass:
    """One annotator's output, located on disk."""

    annotator_id: str
    path: Path
    kind: str  # "user_state" or "export"

    def describe(self) -> str:
        return f"{self.annotator_id} ({self.kind}: {self.path.name})"


def discover_passes(output_dir: Path) -> list[PotatoPass]:
    """Find every annotator pass under a Potato `output_annotation_dir`.

    Returns passes sorted by annotator id. An empty list means nobody has
    annotated anything yet, which is a normal state and not an error -- the
    caller reports it, because "no output" and "malformed output" need
    different advice.
    """
    passes: list[PotatoPass] = []
    if not output_dir.is_dir():
        return passes

    for user_dir in sorted(p for p in output_dir.iterdir() if p.is_dir()):
        state = user_dir / USER_STATE_FILENAME
        if state.is_file():
            passes.append(PotatoPass(annotator_id=user_dir.name, path=state, kind="user_state"))

    # The export lives under `exports/` and covers every user in one file, so it
    # is only consulted when no raw state was found -- otherwise the same pass
    # would be ingested twice.
    if not passes:
        export = output_dir / "exports" / "annotations.jsonl"
        if export.is_file():
            for user_id in sorted(_export_user_ids(export)):
                passes.append(PotatoPass(annotator_id=user_id, path=export, kind="export"))

    return passes


def _export_user_ids(path: Path) -> set[str]:
    users: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("user_id"):
            users.add(str(row["user_id"]))
    return users


def _labels_to_dict(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalise Potato's label storage to `{schema: {name: value}}`.

    `user_state.json` stores `instance_id_to_label_to_value` as a list of
    `[{"schema": ..., "name": ...}, value]` pairs; the export has already
    flattened it to a nested dict. Both appear in the wild, so both are handled
    here rather than at two call sites.
    """
    if isinstance(raw, dict):
        return {
            str(k): dict(v) if isinstance(v, dict) else {str(v): "true"} for k, v in raw.items()
        }

    out: dict[str, dict[str, Any]] = {}
    for entry in raw or []:
        if not isinstance(entry, list | tuple) or len(entry) != 2:
            continue
        label_obj, value = entry
        if not isinstance(label_obj, dict):
            continue
        schema = str(label_obj.get("schema", ""))
        name = str(label_obj.get("name", ""))
        out.setdefault(schema, {})[name] = value
    return out


def _spans_to_list(raw: Any) -> list[dict[str, Any]]:
    """Normalise Potato's span storage to a flat list of span dicts."""
    spans: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        # Export shape: {schema_name: [span, ...]}
        for span_list in raw.values():
            if isinstance(span_list, list):
                spans.extend(s for s in span_list if isinstance(s, dict))
        return spans

    for entry in raw or []:
        span_obj = entry
        if isinstance(entry, list | tuple) and len(entry) == 2:
            span_obj = entry[0]
        if isinstance(span_obj, dict):
            spans.append(span_obj)
    return spans


def _first_selected(values: Any) -> str:
    """Potato records a chosen radio option as `{"2 moderate": "true"}`."""
    if isinstance(values, dict):
        chosen = [k for k, v in values.items() if v not in (False, "false", None, "")]
        return str(chosen[0]) if chosen else ""
    return str(values or "")


def resolve_span_surface(span: dict[str, Any], item_text: str) -> str:
    """Slice the utterance with Potato's offsets. Refuses rather than clips.

    This is what makes the gold-side substring invariant structural. The
    annotator highlighted characters `[start, end)` of the utterance; the
    surface text is definitionally `item_text[start:end]`, so there is no
    opportunity for a paraphrase to enter.
    """
    try:
        start = int(span["start"])
        end = int(span["end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PotatoOutputError(
            f"span {span!r} carries no usable start/end offsets. Potato 2.7.1 records "
            "spans as offsets only, so without them the evidence cannot be recovered"
        ) from exc

    if not 0 <= start < end <= len(item_text):
        raise PotatoOutputError(
            f"span offsets [{start}, {end}) do not lie inside a {len(item_text)}-character "
            "utterance. This means the annotated text and the batch have diverged -- "
            "regenerate the project rather than clipping the span, because a clipped "
            "span is not the span the annotator marked"
        )

    surface = item_text[start:end]
    if not surface.strip():
        raise PotatoOutputError(
            f"span offsets [{start}, {end}) select only whitespace. An empty span cannot "
            "be evidence for anything"
        )
    return surface


def normalise_record(
    *,
    instance_id: str,
    labels: dict[str, dict[str, Any]],
    spans: list[dict[str, Any]],
    item_text: str,
) -> dict[str, Any]:
    """One Potato record -> the payload shape `parse_annotation` consumes.

    Deliberately does no rubric checking. The coupling rules (a present
    construct has a span, intensity 0 contradicts a span, the modifier needs an
    anxiety construct) stay in `ingest.py` so there is exactly one place where a
    gold label can be refused.
    """
    annotations: dict[str, Any] = {}

    for schema, entries in labels.items():
        if schema == SPAN_SCHEMA:
            if any(name == BAD_TEXT_LABEL and value for name, value in entries.items()):
                annotations["bad_text"] = True
            continue
        if schema == "note":
            note = entries.get(TEXT_BOX_LABEL)
            if note is None:
                # A named textbox, or a shape a future Potato uses: take the
                # first non-empty string rather than losing the note.
                note = next((v for v in entries.values() if isinstance(v, str) and v.strip()), "")
            annotations["note"] = str(note or "")
            continue
        if schema == "flags":
            annotations["flags"] = {
                name: value
                for name, value in entries.items()
                if value not in (False, "false", None)
            }
            continue
        annotations[schema] = _first_selected(entries)

    span_annotations = []
    for span in spans:
        if str(span.get("schema", SPAN_SCHEMA)) != SPAN_SCHEMA:
            continue
        span_annotations.append(
            {
                "annotation": str(span.get("name", "")),
                "span": resolve_span_surface(span, item_text),
                "start": int(span["start"]),
                "end": int(span["end"]),
            }
        )

    return {
        "id": instance_id,
        "annotations": annotations,
        "span_annotations": span_annotations,
    }


def read_pass(
    potato_pass: PotatoPass, *, item_texts: dict[str, str]
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """Read one annotator's pass into normalised payloads.

    Returns `(payloads, problems)`. A problem is `(instance_id, message)` for a
    record that could not even be normalised -- an unknown item id, or span
    offsets that do not fit the utterance. These are surfaced rather than
    dropped: an annotation nobody can place is a fact about the pass, and
    `run_annotation.py` prints it as a fix-list.
    """
    payloads: list[dict[str, Any]] = []
    problems: list[tuple[str, str]] = []

    for instance_id, labels, spans in _iter_records(potato_pass):
        item_text = item_texts.get(instance_id)
        if item_text is None:
            problems.append(
                (
                    instance_id,
                    "this id is not in the batch that was handed out. An annotation of an "
                    "item nobody was asked to label cannot enter the gold set",
                )
            )
            continue
        if not labels and not spans:
            continue
        try:
            payloads.append(
                normalise_record(
                    instance_id=instance_id, labels=labels, spans=spans, item_text=item_text
                )
            )
        except PotatoOutputError as exc:
            problems.append((instance_id, str(exc)))

    return payloads, problems


def _iter_records(potato_pass: PotatoPass):
    """Yield `(instance_id, labels, spans)` from either artifact."""
    if potato_pass.kind == "user_state":
        state = json.loads(potato_pass.path.read_text(encoding="utf-8"))
        label_data = state.get("instance_id_to_label_to_value") or {}
        span_data = state.get("instance_id_to_span_to_value") or {}
        for instance_id in sorted(set(label_data) | set(span_data)):
            yield (
                instance_id,
                _labels_to_dict(label_data.get(instance_id, {})),
                _spans_to_list(span_data.get(instance_id, [])),
            )
        return

    for line in potato_pass.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("user_id", "")) != potato_pass.annotator_id:
            continue
        yield (
            str(row.get("instance_id", "")),
            _labels_to_dict(row.get("labels") or {}),
            _spans_to_list(row.get("spans") or {}),
        )
