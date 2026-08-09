"""Loaders for text that comes from a file rather than a generator.

Phase 7 ingests only A2 synthetic text, but the pipeline must not be
*synthetic-only* in shape. When the real gold set arrives -- an A3 consented
donation, or an A1 dataset once a licence is recorded -- it should land through
the same allow-list check, the same provenance write, and the same store, rather
than through a second path written under deadline pressure that skips a control.

So this module exists now, small and tested, rather than later and hurried.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .allowlist import IngestionRefused
from .records import RawRecord


def _coerce_int(value: Any, field_name: str, record_id: str) -> int | None:
    """Turn a spreadsheet-ish value into `int | None`, refusing ambiguity.

    Empty string, "NA", "null" and "none" mean *the source could not tell us*,
    which is `None`. A value that is present but unparseable is an error, not a
    silent `None` -- quietly discarding a malformed timestamp is exactly how a
    corpus ends up with unexplained missingness in the dataset table.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise IngestionRefused(
            "BAD_FIELD", f"record {record_id!r}: {field_name} is a bool, expected int or null"
        )
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text == "" or text.lower() in {"na", "n/a", "null", "none", "unknown"}:
        return None
    try:
        return int(float(text))
    except ValueError as exc:
        raise IngestionRefused(
            "BAD_FIELD",
            f"record {record_id!r}: {field_name}={value!r} is neither an integer "
            "nor a recognised missing-value marker",
        ) from exc


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"na", "n/a", "null", "none", "unknown"}:
        return None
    return text


def _row_to_record(row: dict[str, Any], source_id: str, index: int) -> RawRecord:
    record_id = _clean_str(row.get("record_id")) or f"{source_id}-{index:06d}"
    text = row.get("text")
    if text is None or not str(text).strip():
        raise IngestionRefused(
            "EMPTY_TEXT", f"record {record_id!r} in source {source_id!r} has no text"
        )
    return RawRecord(
        record_id=record_id,
        source_id=source_id,
        text=str(text).strip(),
        time_to_competition_days=_coerce_int(
            row.get("time_to_competition_days"), "time_to_competition_days", record_id
        ),
        sport=_clean_str(row.get("sport")),
        competition_level=_clean_str(row.get("competition_level")),
        region=_clean_str(row.get("region")),
        source_type=_clean_str(row.get("source_type")),
        language=_clean_str(row.get("language")),
        training_load_hint=_clean_str(row.get("training_load_hint")),
        synthetic=bool(row.get("synthetic", False)),
        deidentified=False,  # Phase 8 owns this flag.
    )


def read_jsonl(path: Path, source_id: str) -> Iterator[RawRecord]:
    """Stream records from a JSON Lines file."""
    if not path.exists():
        raise IngestionRefused("MISSING_INPUT", f"input file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            yield _row_to_record(json.loads(line), source_id, index)


def read_csv(path: Path, source_id: str) -> Iterator[RawRecord]:
    """Stream records from a CSV with at least a `text` column."""
    if not path.exists():
        raise IngestionRefused("MISSING_INPUT", f"input file not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or "text" not in reader.fieldnames:
            raise IngestionRefused(
                "BAD_SCHEMA", f"{path} has no 'text' column; columns are {reader.fieldnames}"
            )
        for index, row in enumerate(reader):
            yield _row_to_record(row, source_id, index)


def read_file(path: Path, source_id: str) -> Iterator[RawRecord]:
    """Dispatch on suffix. Unknown suffixes are refused, not guessed."""
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        return read_jsonl(path, source_id)
    if suffix == ".csv":
        return read_csv(path, source_id)
    raise IngestionRefused(
        "UNSUPPORTED_FORMAT",
        f"{path} has suffix {suffix!r}; supported formats are .jsonl, .ndjson, .csv",
    )
