"""Provenance records -- one per source directory in `data/raw/`.

`docs/ethics.md` sec.4 states the rule plainly: **no provenance, no ingestion**.
This module makes that structural rather than procedural. A `Provenance` object
cannot be built with a missing required field, and `store.RawStore` will not
open a source for writing without one.

The required field list is not hardcoded here. It is read from
`config/data_sources_allowlist.yaml:provenance_required_fields`, so adding a
required field to the policy automatically tightens the code. Policy and
enforcement cannot drift apart, because there is only one list.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .allowlist import Allowlist, IngestionRefused, SourceDescriptor, refuse

PROVENANCE_FILENAME = "provenance.json"


@dataclass
class Provenance:
    """The complete, verifiable origin story of one source's text.

    Field names match `provenance_required_fields` / `provenance_optional_fields`
    in the allow-list exactly. That is deliberate -- a mismatch between the
    policy's vocabulary and the artefact's vocabulary is the kind of thing that
    looks fine until a reviewer asks for the mapping.
    """

    # --- required (allow-list: provenance_required_fields) ---
    source_id: str
    source_name: str
    allowlist_category: str
    url_or_citation: str
    collection_date: str
    licence_or_consent_basis: str
    permitted_uses: str
    redistribution_permitted: bool
    synthetic: bool
    subject_is_adult: bool
    language: str
    deidentified: bool
    notes: str

    # --- optional, time-aware / fusion-ready (nullable by design) ---
    time_to_competition: str | None = None
    sport: str | None = None
    competition_level: str | None = None
    region: str | None = None
    source_type: str | None = None

    # --- bookkeeping, not part of the policy's field list ---
    record_count: int = 0
    generator: dict[str, Any] | None = None
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, source_dir: Path) -> Path:
        """Write `provenance.json` into a source directory."""
        source_dir.mkdir(parents=True, exist_ok=True)
        path = source_dir / PROVENANCE_FILENAME
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        return path

    @classmethod
    def read(cls, source_dir: Path) -> Provenance:
        """Read `provenance.json` back. Raises if absent -- there is no default."""
        path = source_dir / PROVENANCE_FILENAME
        if not path.exists():
            raise IngestionRefused(
                "MISSING_PROVENANCE",
                f"{path} does not exist. docs/ethics.md sec.4: no provenance, no ingestion.",
            )
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416 - explicit is clearer
        return cls(**{k: v for k, v in data.items() if k in known})


def validate_provenance(
    provenance: Provenance,
    allowlist: Allowlist,
    *,
    log_path: Path | None = None,
) -> None:
    """Refuse a provenance record that is missing any policy-required field.

    "Missing" means absent, None, or empty-after-strip for strings. Booleans are
    exempt from the emptiness test, because `False` is a meaningful answer to
    `redistribution_permitted` and must not be mistaken for an unanswered field.
    """
    data = provenance.to_dict()
    for field_name in allowlist.provenance_required_fields:
        if field_name not in data:
            refuse(
                "MISSING_REQUIRED_PROVENANCE_FIELD",
                provenance.source_id,
                f"required field {field_name!r} is absent from the provenance record",
                log_path=log_path,
            )
        value = data[field_name]
        if isinstance(value, bool):
            continue
        if value is None or (isinstance(value, str) and not value.strip()):
            refuse(
                "MISSING_REQUIRED_PROVENANCE_FIELD",
                provenance.source_id,
                f"required field {field_name!r} is null or empty",
                log_path=log_path,
            )


def provenance_from_descriptor(
    descriptor: SourceDescriptor,
    allowlist: Allowlist,
    *,
    collection_date: str | None = None,
    generator: dict[str, Any] | None = None,
    log_path: Path | None = None,
) -> Provenance:
    """Build a validated `Provenance` from a checked `SourceDescriptor`.

    `deidentified` is hardcoded False here and that is not an oversight.
    De-identification is Phase 8. Writing `deidentified: true` at ingestion time
    would put a claim in the artefact that no code has yet earned, and the
    allow-list says the flag is "set true only after Phase 8".
    """
    date = collection_date or descriptor.collection_date or _dt.date.today().isoformat()

    time_to_competition = (
        f"{descriptor.time_to_competition_days} days before competition"
        if descriptor.time_to_competition_days is not None
        else None
    )

    provenance = Provenance(
        source_id=descriptor.source_id,
        source_name=descriptor.source_name,
        allowlist_category=descriptor.allowlist_category,
        url_or_citation=descriptor.url_or_citation,
        collection_date=date,
        licence_or_consent_basis=descriptor.licence_or_consent_basis,
        permitted_uses=descriptor.permitted_uses,
        redistribution_permitted=descriptor.redistribution_permitted,
        synthetic=descriptor.synthetic,
        subject_is_adult=descriptor.subject_is_adult,
        language=descriptor.language,
        deidentified=False,  # Phase 8 sets this, not Phase 7.
        notes=descriptor.notes,
        time_to_competition=time_to_competition,
        sport=descriptor.sport,
        competition_level=descriptor.competition_level,
        region=descriptor.region,
        source_type=descriptor.source_type,
        generator=generator,
    )
    validate_provenance(provenance, allowlist, log_path=log_path)
    return provenance


@dataclass(frozen=True)
class GeneratorStamp:
    """Who or what produced synthetic text, and when.

    `A2_synthetic` in the allow-list requires `generator_model_and_date_recorded`
    and `generation_prompts_version_controlled`. This is the first; the second is
    satisfied by keeping the template bank in `src/ingestion/synthetic.py` under
    version control rather than in an ad-hoc prompt somewhere.
    """

    name: str
    version: str
    kind: str  # "template-grammar" | "llm"
    seed: int
    generated_on: str
    prompts_location: str
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
