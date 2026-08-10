"""The interim record schema -- one utterance, cleaned and de-identified.

`RawRecord` (Phase 7) is one passage as it arrived. `InterimRecord` is one
**utterance** after normalisation, segmentation, language checking, and
de-identification. The split is deliberate: labelling in Phase 10 happens per
utterance, and a schema that made the labeller re-segment would put the segment
boundaries outside version control.

Three properties are enforced in `__post_init__` rather than trusted:

**1. `deidentified` cannot be False.** Phase 7 hardcoded it False everywhere
because no code had earned the claim yet. Here the claim is earned, and the
type refuses to represent the alternative -- there is no way to construct an
interim record that has not been through `deidentify`. That mirrors the Phase 7
choice to make "forgot the provenance" a call you cannot express rather than a
mistake you must remember not to make.

**2. Parentage is mandatory.** Every utterance names the raw record it was cut
from, so any interim record can be traced back to a `provenance.json` and from
there to a licence or consent basis. An utterance with no parent is exactly the
untraceable record the Phase 7 gate refuses.

**3. Offsets are into the *normalised* parent text**, and they are checked. The
project's headline contribution is span-level explanation; a `char_start` that
is off by two silently attributes a construct to the wrong words, and there is
no way to notice that by reading the output.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.ingestion.records import COMPETITION_LEVELS, SOURCE_TYPES


@dataclass
class InterimRecord:
    """One cleaned, de-identified utterance."""

    record_id: str
    source_id: str
    parent_record_id: str
    utterance_index: int
    text: str

    # Offsets into the normalised text of the parent record.
    char_start: int
    char_end: int

    # --- carried metadata (nullable by design, exactly as in RawRecord) ---
    #
    # Carried rather than re-derived. `docs/data_sources.md` calls the temporal
    # fields "impossible to backfill later"; dropping them at the interim stage
    # and planning to re-join on `parent_record_id` would work right up until
    # someone shares `data/interim/` without `data/raw/`.
    time_to_competition_days: int | None = None
    sport: str | None = None
    competition_level: str | None = None
    region: str | None = None
    source_type: str | None = None
    language: str | None = None
    training_load_hint: str | None = None

    # --- flags ---
    synthetic: bool = False
    deidentified: bool = True

    # --- processing evidence ---
    #
    # Kept on the record, not only in an aggregate report, because the manual
    # audit reads individual records and needs to see what the pipeline thought
    # it was doing to each one.
    deid: dict[str, Any] = field(default_factory=dict)
    language_verdict: dict[str, Any] = field(default_factory=dict)

    #: Carried verbatim from the parent. STILL NOT A LABEL -- the warning in
    #: `src/ingestion/records.py` applies unchanged here, and applies harder,
    #: because an interim record looks much more like training data than a raw
    #: one does.
    generation_spec: dict[str, Any] | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id or not str(self.record_id).strip():
            raise ValueError("record_id must be non-empty")
        if not self.parent_record_id or not str(self.parent_record_id).strip():
            raise ValueError(
                f"interim record {self.record_id!r} has no parent_record_id; every "
                "utterance must be traceable to a raw record and its provenance"
            )
        if not self.text or not str(self.text).strip():
            raise ValueError(f"interim record {self.record_id!r} has empty text")
        if not self.deidentified:
            raise ValueError(
                f"interim record {self.record_id!r} has deidentified=False. "
                "docs/ethics.md sec.5: every record passes de-identification before "
                "labelling, modelling, or human review. There is no exception and no "
                "flag to set here -- run the record through deidentify() instead."
            )
        if self.utterance_index < 0:
            raise ValueError(f"interim record {self.record_id!r}: utterance_index must be >= 0")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise ValueError(
                f"interim record {self.record_id!r}: invalid span "
                f"[{self.char_start}:{self.char_end}]"
            )
        if self.source_type is not None and self.source_type not in SOURCE_TYPES:
            raise ValueError(
                f"interim record {self.record_id!r}: source_type {self.source_type!r} "
                f"is not one of {SOURCE_TYPES}"
            )
        if self.competition_level is not None and self.competition_level not in COMPETITION_LEVELS:
            raise ValueError(
                f"interim record {self.record_id!r}: competition_level "
                f"{self.competition_level!r} is not one of {COMPETITION_LEVELS}"
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterimRecord:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_json_line(cls, line: str) -> InterimRecord:
        return cls.from_dict(json.loads(line))


#: Fields carried across from `RawRecord` unchanged. Named once so the pipeline,
#: the tests, and the coverage report cannot disagree about what "carried" means.
CARRIED_FIELDS: tuple[str, ...] = (
    "time_to_competition_days",
    "sport",
    "competition_level",
    "region",
    "source_type",
    "training_load_hint",
    "synthetic",
    "generation_spec",
)
