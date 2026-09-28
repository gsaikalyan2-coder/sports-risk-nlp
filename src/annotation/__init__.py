"""Human gold annotation (Phase 11).

Turns `data/processed/gold_candidates/` into a runnable Potato project, reads
the annotators' output back as typed `GoldLabel`s.

    from src.annotation import load_batch, write_project

Submodules, in workflow order:

    context         attach the parent record to each item -- the Phase 11 defect fix
    potato_project  emit a Potato project from config/taxonomy.yaml
    ingest          read Potato output back; refuses malformed annotations
    schema          GoldLabel / GoldConstruct; only a human can author one
    store           the only write path into data/gold/

The annotation UI is **Potato** (`davidjurgens/potato`), installed separately
and not vendored. `docs/annotation_tooling.md` explains the integration and
pins the version.

NOTE (2026-09-28): this project no longer computes inter-annotator agreement.
`agreement.py` (Cohen's kappa, weighted kappa, span F1, the adjudication
worklist) was deleted by owner decision -- see `CLAUDE.md` sec.20-21 and
`config/annotators.yaml`'s header. A backup of the deleted module is under
`annotation/gold_dev/_backup_2026-09-28/removed_20260928/agreement.py`.
"""

from __future__ import annotations

from .context import (
    AnnotationItem,
    ContextError,
    build_items,
    context_coverage,
    load_batch,
    parent_texts,
    sibling_counts,
)
from .ingest import (
    IngestError,
    IngestReport,
    ingest_passes,
    ingest_potato,
    parse_annotation,
)
from .potato_output import (
    PotatoOutputError,
    PotatoPass,
    discover_passes,
    normalise_record,
    read_pass,
    resolve_span_surface,
)
from .potato_project import POTATO_VERSION, build_config, span_labels, write_project
from .schema import (
    Annotator,
    GoldConstruct,
    GoldLabel,
    GoldSchemaError,
    load_annotators,
)
from .store import GoldStore, GoldWriteRefused

__all__ = [
    "POTATO_VERSION",
    "AnnotationItem",
    "Annotator",
    "ContextError",
    "GoldConstruct",
    "GoldLabel",
    "GoldSchemaError",
    "GoldStore",
    "GoldWriteRefused",
    "IngestError",
    "IngestReport",
    "PotatoOutputError",
    "PotatoPass",
    "build_config",
    "build_items",
    "context_coverage",
    "discover_passes",
    "ingest_passes",
    "ingest_potato",
    "load_annotators",
    "load_batch",
    "normalise_record",
    "parent_texts",
    "parse_annotation",
    "read_pass",
    "resolve_span_surface",
    "sibling_counts",
    "span_labels",
    "write_project",
]
