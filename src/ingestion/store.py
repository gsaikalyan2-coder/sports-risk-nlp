"""The only sanctioned way to write into `data/raw/`.

Two invariants are enforced structurally rather than by convention:

1. **No record without provenance.** `RawStore.open_source()` runs the
   allow-list check and writes `provenance.json` *before* returning anything
   capable of writing a record. There is no public API that writes a record
   given only a path and some text, so "forgot the provenance" is not a mistake
   a caller can make -- it is a call they cannot express.

2. **`data/gold/` is human-owned.** `CLAUDE.md` sec.4 says agents never write
   there. The store refuses any root that resolves inside the gold directory,
   so an agent given a mis-set path fails loudly instead of quietly writing
   machine output into the human-verified set -- which would be near-impossible
   to detect afterwards and would silently invalidate every agreement number in
   the paper.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Any

from .allowlist import (
    Allowlist,
    IngestionRefused,
    SourceDescriptor,
    check_source,
    load_allowlist,
)
from .provenance import Provenance, provenance_from_descriptor
from .records import RawRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_ROOT = REPO_ROOT / "data" / "raw"
GOLD_ROOT = REPO_ROOT / "data" / "gold"

RECORDS_FILENAME = "records.jsonl"


class SourceWriter:
    """A writable handle on one source directory.

    Only obtainable from `RawStore.open_source()`, which means only obtainable
    after the allow-list check has passed and provenance has been written.
    """

    def __init__(self, source_dir: Path, provenance: Provenance) -> None:
        self._dir = source_dir
        self._provenance = provenance
        self._path = source_dir / RECORDS_FILENAME
        self._count = 0
        self._handle: Any = None
        self._seen_ids: set[str] = set()

    def __enter__(self) -> SourceWriter:
        # newline="\n" is not decoration. Without it, Python translates "\n" to
        # "\r\n" on Windows, so this file's bytes depend on which machine ran the
        # pipeline -- and Phase 22 found exactly that on the owner's disk:
        # records.jsonl carried LF and utterances.jsonl carried CRLF, identical
        # content, different bytes, generated two days apart on two platforms.
        # A byte-identity claim that holds only on one OS is not a byte-identity
        # claim. `src/evaluation/sampling.py` already used this idiom; the other
        # writers did not.
        self._handle = self._path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        # Only stamp the final count on a clean exit. A crashed run should not
        # leave a provenance file claiming a record count it did not write.
        if exc_type is None:
            self._provenance.record_count = self._count
            self._provenance.write(self._dir)

    def write(self, record: RawRecord) -> None:
        if self._handle is None:
            raise RuntimeError(
                "SourceWriter used outside a `with` block; the provenance record "
                "count is only finalised on context exit"
            )
        if record.source_id != self._provenance.source_id:
            raise IngestionRefused(
                "SOURCE_ID_MISMATCH",
                f"record {record.record_id!r} claims source_id "
                f"{record.source_id!r} but is being written into "
                f"{self._provenance.source_id!r}",
            )
        if record.record_id in self._seen_ids:
            raise IngestionRefused(
                "DUPLICATE_RECORD_ID",
                f"record_id {record.record_id!r} written twice to source "
                f"{self._provenance.source_id!r}",
            )
        # Synthetic provenance implies synthetic records. Catching the mismatch
        # here stops synthetic text from ever being filed as real, which
        # docs/ethics.md sec.3.1 A2 forbids in the corpus, the paper, and the
        # dashboard alike.
        if self._provenance.synthetic and not record.synthetic:
            raise IngestionRefused(
                "SYNTHETIC_FLAG_MISMATCH",
                f"record {record.record_id!r} has synthetic=False under a "
                "synthetic source; A2 requires record_field_synthetic_true",
            )
        self._seen_ids.add(record.record_id)
        self._handle.write(record.to_json_line() + "\n")
        self._count += 1

    def write_all(self, records: Iterable[RawRecord]) -> int:
        for record in records:
            self.write(record)
        return self._count

    @property
    def count(self) -> int:
        return self._count

    @property
    def directory(self) -> Path:
        return self._dir


class RawStore:
    """Owns `data/raw/` and the rules about what may enter it."""

    def __init__(
        self,
        root: Path | None = None,
        allowlist: Allowlist | None = None,
        *,
        refusal_log: Path | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else DEFAULT_RAW_ROOT
        self.allowlist = allowlist if allowlist is not None else load_allowlist()
        self.refusal_log = refusal_log
        self._guard_root(self.root)

    @staticmethod
    def _guard_root(root: Path) -> None:
        """Refuse any root inside `data/gold/`. Human-owned means human-owned."""
        try:
            resolved = root.resolve()
        except OSError:  # pragma: no cover -- exotic filesystem states
            resolved = root
        gold = GOLD_ROOT.resolve() if GOLD_ROOT.exists() else GOLD_ROOT
        if resolved == gold or gold in resolved.parents:
            raise IngestionRefused(
                "GOLD_IS_HUMAN_OWNED",
                f"refusing to use {resolved} as an ingestion root: data/gold/ is "
                "human-owned and is never written by an agent (CLAUDE.md sec.4)",
            )

    def open_source(
        self,
        descriptor: SourceDescriptor,
        *,
        generator: dict[str, Any] | None = None,
        collection_date: str | None = None,
    ) -> SourceWriter:
        """Check a source, write its provenance, and return a writer.

        This is the only public path to a `SourceWriter`, and therefore the only
        path to a record in `data/raw/`.
        """
        check_source(descriptor, self.allowlist, log_path=self.refusal_log)
        provenance = provenance_from_descriptor(
            descriptor,
            self.allowlist,
            collection_date=collection_date,
            generator=generator,
            log_path=self.refusal_log,
        )
        source_dir = self.root / descriptor.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        provenance.write(source_dir)
        return SourceWriter(source_dir, provenance)

    # -- reading back -------------------------------------------------------

    def source_dirs(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir())

    def read_source(self, source_id: str) -> tuple[Provenance, list[RawRecord]]:
        """Read one source back, refusing if its provenance is missing.

        The refusal is the point. An orphaned `records.jsonl` with no
        `provenance.json` beside it is exactly the untraceable record the Phase 7
        gate forbids, and reading it silently would let it through.
        """
        source_dir = self.root / source_id
        provenance = Provenance.read(source_dir)
        records_path = source_dir / RECORDS_FILENAME
        if not records_path.exists():
            return provenance, []
        records = [
            RawRecord.from_json_line(line)
            for line in records_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return provenance, records

    def iter_all(self) -> Iterator[tuple[Provenance, list[RawRecord]]]:
        for source_dir in self.source_dirs():
            if not (source_dir / "provenance.json").exists():
                # Not silently skipped: an unexplained directory under data/raw/
                # is a traceability failure and the gate must see it.
                raise IngestionRefused(
                    "MISSING_PROVENANCE",
                    f"{source_dir} contains no provenance.json; every raw record "
                    "must be traceable to a licensed, consented, or synthetic source",
                )
            yield self.read_source(source_dir.name)
