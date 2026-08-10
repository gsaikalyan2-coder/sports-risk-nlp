"""The Phase 8 pipeline: `data/raw/` -> `data/interim/`.

Four steps in a fixed order, and the order is the design:

    normalise -> segment -> language filter -> de-identify

**Normalise first**, because every later step matches on surface form. A
de-identifier looking for `@handle` misses the fullwidth variant; a segmenter
looking for `. ` misses a non-breaking space. Normalisation is what makes the
rest of the cascade able to see what is there.

**Segment before de-identify**, not after. De-identification changes text
length -- `Marcus Halloway` becomes `[ATHLETE]` -- so offsets computed after
redaction point into a string that no longer matches the raw record. Cutting
first means every utterance keeps an exact, checkable span into its parent's
normalised text, which is what span-level explanation will need at Phase 16.
The price is that `char_start`/`char_end` index the **normalised** parent, not
the de-identified utterance, and that is stated on the schema rather than left
for someone to discover.

**Language filter before de-identify**, because there is no point spending the
redaction cascade -- which is English-only in every lexicon it uses -- on text
it cannot read. A record it cannot read is dropped with a recorded reason, not
silently.

Everything here is deterministic, offline, and free. `pytest` cannot spend
money because nothing in this module can make a network call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.ingestion.records import RawRecord
from src.ingestion.store import RawStore

from .audit import SampleFinding, audit_sample
from .deidentify import deidentify_with_report
from .language import detect_language, should_exclude
from .normalize import normalize_with_report
from .records import InterimRecord
from .segment import segment, verify_offsets
from .store import InterimStore

#: Reasons a record or utterance can be dropped. Enumerated so that the
#: manifest reports a breakdown rather than a single total -- "we dropped 41"
#: is not an auditable statement, and a corpus whose size nobody can explain is
#: the failure `src/ingestion/allowlist.py` refuses at the layer above.
DROP_REASONS = (
    "empty_after_normalisation",
    "no_utterances",
    "non_english",
    "empty_after_deidentification",
)


@dataclass
class PreprocessResult:
    """What one source's preprocessing run produced."""

    source_id: str
    raw_records: int = 0
    utterances_written: int = 0
    dropped: dict[str, int] = field(default_factory=lambda: dict.fromkeys(DROP_REASONS, 0))
    replacements: dict[str, int] = field(default_factory=dict)
    health_clauses_removed: int = 0
    records_normalised: int = 0
    records_with_residual_flags: int = 0
    offset_violations: list[str] = field(default_factory=list)
    sample: list[SampleFinding] = field(default_factory=list)

    @property
    def dropped_total(self) -> int:
        return sum(self.dropped.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "raw_records": self.raw_records,
            "utterances_written": self.utterances_written,
            "dropped": dict(self.dropped),
            "dropped_total": self.dropped_total,
            "records_normalised": self.records_normalised,
            "deid_replacements": dict(sorted(self.replacements.items())),
            "deid_replacements_total": sum(self.replacements.values()),
            "health_clauses_removed": self.health_clauses_removed,
            "utterances_with_residual_flags": self.records_with_residual_flags,
            "offset_violations": len(self.offset_violations),
        }


def _stratum(record: RawRecord) -> str:
    """The stratum a record belongs to for the manual audit sample.

    `docs/ethics.md` sec.5.2 asks for a **stratified** sample. Sport crossed
    with time-to-competition is the stratification that matters here: the
    de-identifier's failure modes are lexical, so a sample drawn only from one
    sport would miss the vocabulary of the others, and timing bands are where
    the anticipatory constructs live.
    """
    days = record.time_to_competition_days
    if days is None:
        band = "unknown"
    elif days <= 1:
        band = "0-1d"
    elif days <= 7:
        band = "2-7d"
    else:
        band = "8d+"
    return f"{record.sport or 'unknown'}|{band}"


@dataclass
class RecordOutcome:
    """What became of one raw record."""

    utterances: list[InterimRecord]
    drops: dict[str, int]
    offset_violations: list[str]
    normalisation_changed: bool


def preprocess_record(record: RawRecord) -> RecordOutcome:
    """Turn one raw record into zero or more interim utterances.

    Zero utterances is a legitimate outcome -- a record whose only content was
    a health clause is correctly emptied -- and it is counted, not hidden.
    """
    drops: dict[str, int] = dict.fromkeys(DROP_REASONS, 0)

    normalised, norm_report = normalize_with_report(record.text)
    if not normalised.strip():
        drops["empty_after_normalisation"] += 1
        return RecordOutcome([], drops, [], norm_report.changed)

    verdict = detect_language(normalised)
    drop, _reason = should_exclude(normalised)
    if drop:
        # Note this calls `should_exclude`, not `is_english`. Excluding on "not
        # confidently English" deletes short, sparse, idiomatic records -- which
        # in this corpus are the terse high-arousal utterances carrying the most
        # construct signal. See `language.should_exclude`.
        drops["non_english"] += 1
        return RecordOutcome([], drops, [], norm_report.changed)

    utterances = segment(normalised)
    if not utterances:
        drops["no_utterances"] += 1
        return RecordOutcome([], drops, [], norm_report.changed)

    violations = verify_offsets(normalised, utterances)

    out: list[InterimRecord] = []
    for utterance in utterances:
        clean, report = deidentify_with_report(utterance.text)
        if not clean.strip():
            drops["empty_after_deidentification"] += 1
            continue
        out.append(
            InterimRecord(
                record_id=f"{record.record_id}#u{utterance.index}",
                source_id=record.source_id,
                parent_record_id=record.record_id,
                utterance_index=utterance.index,
                text=clean,
                char_start=utterance.start,
                char_end=utterance.end,
                time_to_competition_days=record.time_to_competition_days,
                sport=record.sport,
                competition_level=record.competition_level,
                region=record.region,
                source_type=record.source_type,
                language=record.language or verdict.language,
                training_load_hint=record.training_load_hint,
                synthetic=record.synthetic,
                deidentified=True,
                deid=report.to_dict(),
                language_verdict=verdict.to_dict(),
                generation_spec=record.generation_spec,
            )
        )
    return RecordOutcome(out, drops, violations, norm_report.changed)


def preprocess_source(
    source_id: str,
    *,
    raw_store: RawStore | None = None,
    interim_store: InterimStore | None = None,
    sample_per_stratum: int = 2,
) -> PreprocessResult:
    """Preprocess one raw source into `data/interim/`."""
    raw_store = raw_store or RawStore()
    interim_store = interim_store or InterimStore()

    provenance, records = raw_store.read_source(source_id)
    result = PreprocessResult(source_id=source_id, raw_records=len(records))
    sample_input: list[tuple[str, str, str, list[str]]] = []

    with interim_store.open_source(provenance) as writer:
        for record in records:
            outcome = preprocess_record(record)
            if outcome.normalisation_changed:
                result.records_normalised += 1
            for reason, count in outcome.drops.items():
                result.dropped[reason] += count
            result.offset_violations.extend(outcome.offset_violations)

            for utterance in outcome.utterances:
                writer.write(utterance)
                flags = list(utterance.deid.get("residual_flags", []))
                if flags:
                    result.records_with_residual_flags += 1
                for placeholder, count in utterance.deid.get("replacements", {}).items():
                    result.replacements[placeholder] = (
                        result.replacements.get(placeholder, 0) + count
                    )
                result.health_clauses_removed += int(
                    utterance.deid.get("health_clauses_removed", 0)
                )
                sample_input.append((utterance.record_id, _stratum(record), utterance.text, flags))

        result.utterances_written = writer.count
        writer.manifest = {
            **result.to_dict(),
            "steps": ["normalize", "segment", "language_filter", "deidentify"],
            "note": (
                "char_start/char_end index the NORMALISED parent text in data/raw/, "
                "not the de-identified utterance text stored here."
            ),
        }

    result.sample = audit_sample(sample_input, per_stratum=sample_per_stratum)
    return result


def preprocess_all(
    *,
    raw_store: RawStore | None = None,
    interim_store: InterimStore | None = None,
    sample_per_stratum: int = 2,
) -> list[PreprocessResult]:
    """Preprocess every source in `data/raw/`.

    Sources are enumerated through `RawStore.iter_all`, which refuses a source
    directory with no `provenance.json`. Preprocessing therefore inherits the
    Phase 7 traceability guarantee instead of re-implementing it -- and a raw
    directory someone dropped in by hand fails here too.
    """
    raw_store = raw_store or RawStore()
    interim_store = interim_store or InterimStore()
    return [
        preprocess_source(
            provenance.source_id,
            raw_store=raw_store,
            interim_store=interim_store,
            sample_per_stratum=sample_per_stratum,
        )
        for provenance, _ in raw_store.iter_all()
    ]
