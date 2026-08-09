"""Phase 7 -- data ingestion with provenance and allow-list enforcement.

Public API. Import from here rather than from the submodules, so the enforced
path stays the obvious path.

    from src.ingestion import RawStore, synthetic_descriptor, generate_records

    store = RawStore()
    descriptor = synthetic_descriptor(seed=42)
    with store.open_source(descriptor, generator=generator_stamp(42).to_dict()) as writer:
        writer.write_all(generate_records(500, seed=42, source_id=descriptor.source_id))

Nothing here can write a record into `data/raw/` without first passing
`check_source` and writing a complete `provenance.json`. That is by construction,
not by discipline -- see `store.py`.
"""

from .allowlist import (
    REQUIRED_DECLARATIONS,
    Allowlist,
    AllowlistError,
    Category,
    IngestionRefused,
    Prohibition,
    SourceDescriptor,
    check_source,
    load_allowlist,
    log_refusal,
)
from .provenance import (
    GeneratorStamp,
    Provenance,
    provenance_from_descriptor,
    validate_provenance,
)
from .records import (
    COMPETITION_LEVELS,
    OPTIONAL_METADATA_FIELDS,
    SOURCE_TYPES,
    RawRecord,
    metadata_coverage,
)
from .sources import read_csv, read_file, read_jsonl
from .store import RawStore, SourceWriter
from .synthetic import (
    ALL_CONSTRUCTS,
    generate_records,
    generator_stamp,
    synthetic_descriptor,
    type_token_ratio,
)

__all__ = [
    "ALL_CONSTRUCTS",
    "COMPETITION_LEVELS",
    "OPTIONAL_METADATA_FIELDS",
    "REQUIRED_DECLARATIONS",
    "SOURCE_TYPES",
    "Allowlist",
    "AllowlistError",
    "Category",
    "GeneratorStamp",
    "IngestionRefused",
    "Prohibition",
    "Provenance",
    "RawRecord",
    "RawStore",
    "SourceDescriptor",
    "SourceWriter",
    "check_source",
    "generate_records",
    "generator_stamp",
    "load_allowlist",
    "log_refusal",
    "metadata_coverage",
    "provenance_from_descriptor",
    "read_csv",
    "read_file",
    "read_jsonl",
    "synthetic_descriptor",
    "type_token_ratio",
    "validate_provenance",
]
