"""The raw record schema.

One record is one unit of athlete text plus everything we know about where it
came from and when, relative to a competition.

The time-aware fields are the reason this file exists in Phase 7 rather than
later. `PROJECT_PLAN.md` Phase 7 puts it bluntly: timing and light context are
"cheap to record now and impossible to backfill later". Once a corpus is built
without `time_to_competition`, the only way to add it is to re-collect. So the
schema carries the fields from the first record, sparse or not.

**Nullable is a first-class value here.** A field that is absent from the source
is written as an explicit JSON `null`, never omitted and never defaulted to a
sentinel string. That distinction matters at analysis time: `null` means "this
source could not tell us", which is a different claim from "0 days before" and a
very different claim from a key that quietly vanished.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

#: Vocabulary for `source_type`, matching the allow-list's optional-field note.
SOURCE_TYPES = ("interview", "presser", "social", "journal", "synthetic")

#: Coarse competition levels. Coarse on purpose -- `docs/ethics.md` sec.5.2 warns
#: that quasi-identifier combinations re-identify as surely as a name, and a
#: precise level plus a sport plus a date is exactly such a combination.
COMPETITION_LEVELS = ("club", "regional", "national", "international", "elite")


@dataclass
class RawRecord:
    """One ingested utterance or passage, before any cleaning or labelling.

    Nothing here is labelled. Construct labels arrive in Phase 10 (silver) and
    Phase 11 (gold). Keeping the raw record label-free means a re-label never
    requires a re-ingest.
    """

    record_id: str
    source_id: str
    text: str

    # --- optional temporal / context metadata (nullable by design) ---
    time_to_competition_days: int | None = None
    sport: str | None = None
    competition_level: str | None = None
    region: str | None = None
    source_type: str | None = None
    language: str | None = None

    # Light non-text context, kept for the Phase 15 fusion-ready interface. A
    # free-form hint rather than a number, because no source in this corpus
    # reports calibrated training load and inventing a scale would be worse
    # than recording the phrase the source actually used.
    training_load_hint: str | None = None

    # --- flags ---
    synthetic: bool = False
    deidentified: bool = False  # Phase 8 flips this, not Phase 7.

    # --- generation metadata, synthetic records only ---
    #
    # WARNING, and it belongs in the schema rather than only in the docs:
    # `generation_spec` records which constructs the generator PLANTED in this
    # text. It is NOT a label and must never be used as evaluation ground truth.
    # Doing so would measure whether the model can recover the generator's own
    # template choices -- a circular result that says nothing about athlete
    # language. Evaluation rests on the human gold set (Phase 11) alone.
    # See docs/data_sources.md sec."Circularity risk".
    generation_spec: dict[str, Any] | None = None

    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.record_id or not str(self.record_id).strip():
            raise ValueError("record_id must be non-empty")
        if not self.source_id or not str(self.source_id).strip():
            raise ValueError("record_id must belong to a source: source_id is empty")
        if not self.text or not str(self.text).strip():
            raise ValueError(f"record {self.record_id!r} has empty text")
        if self.source_type is not None and self.source_type not in SOURCE_TYPES:
            raise ValueError(
                f"record {self.record_id!r}: source_type {self.source_type!r} "
                f"is not one of {SOURCE_TYPES}"
            )
        if self.competition_level is not None and self.competition_level not in COMPETITION_LEVELS:
            raise ValueError(
                f"record {self.record_id!r}: competition_level "
                f"{self.competition_level!r} is not one of {COMPETITION_LEVELS}"
            )
        if self.time_to_competition_days is not None:
            if not isinstance(self.time_to_competition_days, int) or isinstance(
                self.time_to_competition_days, bool
            ):
                raise ValueError(
                    f"record {self.record_id!r}: time_to_competition_days must be an "
                    f"int or None, got {type(self.time_to_competition_days).__name__}"
                )
            if self.time_to_competition_days < 0:
                raise ValueError(
                    f"record {self.record_id!r}: time_to_competition_days must be >= 0 "
                    "(days BEFORE the competition). This project is pre-competition; "
                    "a negative value would mean post-competition text."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serialise with every optional field present, null where unknown."""
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RawRecord:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def from_json_line(cls, line: str) -> RawRecord:
        return cls.from_dict(json.loads(line))


#: The optional metadata fields, named once so that documentation, tests, and
#: the coverage report in `docs/data_sources.md` all count the same things.
OPTIONAL_METADATA_FIELDS: tuple[str, ...] = (
    "time_to_competition_days",
    "sport",
    "competition_level",
    "region",
    "source_type",
    "training_load_hint",
)


def metadata_coverage(records: list[RawRecord]) -> dict[str, float]:
    """Fraction of records carrying a non-null value for each optional field.

    Feeds the coverage table in `docs/data_sources.md`. Sparse is acceptable
    per the Phase 7 gate; silently absent is not, and this is how the difference
    becomes visible rather than assumed.
    """
    if not records:
        return dict.fromkeys(OPTIONAL_METADATA_FIELDS, 0.0)
    total = len(records)
    return {
        name: sum(1 for r in records if getattr(r, name) is not None) / total
        for name in OPTIONAL_METADATA_FIELDS
    }
