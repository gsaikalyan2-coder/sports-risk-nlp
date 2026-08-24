"""The only sanctioned way to write into `data/interim/`.

Deliberately built as a mirror of `src/ingestion/store.py`. The invariants are
the same ones, restated one layer down, because a control that holds at
ingestion and lapses at preprocessing is not a control:

1. **`data/gold/` is human-owned.** Same guard, same refusal code. Phase 8 adds
   a second layer that could be pointed at the wrong root, so it gets the same
   check rather than an assumption that Phase 7 already handled it.

2. **Nothing is written without provenance.** The interim provenance is derived
   from the raw provenance rather than authored fresh, so an interim source
   cannot claim a licence basis its raw source never had. The one field that
   changes is `deidentified`, which flips to `true` -- and only because the
   pipeline that calls this has just run the de-identifier.

3. **A record that has not been de-identified cannot be written.**
   `InterimRecord` already refuses to exist with `deidentified=False`; the
   writer checks again on the way out. Two checks for one rule is not an
   accident. `docs/ethics.md` sec.5 admits no exception, and the cost of the
   redundant check is one comparison per record.

The manifest (`preprocessing.json`) is the artefact a reviewer reads to find
out what happened between `data/raw/` and `data/interim/`: how many records
went in, how many utterances came out, how many were dropped and why, and what
the de-identifier replaced. Counts, not adjectives.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Any

from src.ingestion.allowlist import IngestionRefused
from src.ingestion.provenance import Provenance

from .records import InterimRecord

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERIM_ROOT = REPO_ROOT / "data" / "interim"
GOLD_ROOT = REPO_ROOT / "data" / "gold"

UTTERANCES_FILENAME = "utterances.jsonl"
MANIFEST_FILENAME = "preprocessing.json"
PROVENANCE_FILENAME = "provenance.json"


def interim_provenance(raw: Provenance, *, utterance_count: int) -> Provenance:
    """Derive the interim provenance from the raw one.

    `deidentified` flips to True here and **only** here. Phase 7 wrote False
    into every raw provenance on the grounds that writing True would put a
    claim in the artefact that no code had earned. This function is called from
    exactly one place -- after the de-identifier has run over every record in
    the source -- which is what earns it.

    The raw provenance is left untouched. `data/raw/` still says
    `deidentified: false`, correctly: the raw text has not been de-identified
    and never will be. Rewriting it would misdescribe a file that still
    contains the original strings.
    """
    derived = Provenance(**raw.to_dict())
    derived.deidentified = True
    derived.record_count = utterance_count
    derived.notes = (
        f"{raw.notes} | Phase 8: normalised, segmented, language-checked, and "
        "de-identified per docs/ethics.md sec.5.1. Derived from "
        f"data/raw/{raw.source_id}/; the raw source retains deidentified=false."
    )
    return derived


class InterimWriter:
    """A writable handle on one interim source directory.

    Only obtainable from `InterimStore.open_source()`, which means only
    obtainable once a raw provenance has been read and carried forward.
    """

    def __init__(self, source_dir: Path, provenance: Provenance) -> None:
        self._dir = source_dir
        self._provenance = provenance
        self._path = source_dir / UTTERANCES_FILENAME
        self._count = 0
        self._handle: Any = None
        self._seen_ids: set[str] = set()
        self.manifest: dict[str, Any] = {}

    def __enter__(self) -> InterimWriter:
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
        # A crashed run leaves no provenance claiming a count it did not write,
        # for the same reason `SourceWriter` does not: a truncated corpus with a
        # confident manifest is worse than an obviously incomplete one.
        if exc_type is None:
            self._provenance.record_count = self._count
            self._provenance.write(self._dir)
            self._write_manifest()

    def _write_manifest(self) -> None:
        payload = {
            "phase": 8,
            "source_id": self._provenance.source_id,
            "written_on": _dt.date.today().isoformat(),
            "utterance_count": self._count,
            "deidentified": True,
            "policy": "docs/ethics.md sec.5.1",
            **self.manifest,
        }
        # See the newline note in __enter__: write_text translates newlines on
        # Windows too, so a manifest written there differs byte-wise from the
        # same manifest written in the container.
        with (self._dir / MANIFEST_FILENAME).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def write(self, record: InterimRecord) -> None:
        if self._handle is None:
            raise RuntimeError(
                "InterimWriter used outside a `with` block; the manifest and record "
                "count are only finalised on context exit"
            )
        if record.source_id != self._provenance.source_id:
            raise IngestionRefused(
                "SOURCE_ID_MISMATCH",
                f"record {record.record_id!r} claims source_id {record.source_id!r} "
                f"but is being written into {self._provenance.source_id!r}",
            )
        if record.record_id in self._seen_ids:
            raise IngestionRefused(
                "DUPLICATE_RECORD_ID",
                f"record_id {record.record_id!r} written twice to interim source "
                f"{self._provenance.source_id!r}",
            )
        if not record.deidentified:
            raise IngestionRefused(
                "NOT_DEIDENTIFIED",
                f"record {record.record_id!r} is not de-identified; docs/ethics.md "
                "sec.5 admits no exception",
            )
        self._seen_ids.add(record.record_id)
        self._handle.write(record.to_json_line() + "\n")
        self._count += 1

    def write_all(self, records: Iterable[InterimRecord]) -> int:
        for record in records:
            self.write(record)
        return self._count

    @property
    def count(self) -> int:
        return self._count

    @property
    def directory(self) -> Path:
        return self._dir


class InterimStore:
    """Owns `data/interim/` and the rules about what may enter it."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_INTERIM_ROOT
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
                f"refusing to use {resolved} as a preprocessing root: data/gold/ is "
                "human-owned and is never written by an agent (CLAUDE.md sec.4)",
            )

    def open_source(self, raw_provenance: Provenance) -> InterimWriter:
        """Open an interim source, carrying its raw provenance forward."""
        source_dir = self.root / raw_provenance.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        provenance = interim_provenance(raw_provenance, utterance_count=0)
        provenance.write(source_dir)
        return InterimWriter(source_dir, provenance)

    # -- reading back -------------------------------------------------------

    def source_dirs(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir())

    def read_source(self, source_id: str) -> tuple[Provenance, list[InterimRecord]]:
        source_dir = self.root / source_id
        provenance = Provenance.read(source_dir)
        path = source_dir / UTTERANCES_FILENAME
        if not path.exists():
            return provenance, []
        records = [
            InterimRecord.from_json_line(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return provenance, records

    def iter_all(self) -> Iterator[tuple[Provenance, list[InterimRecord]]]:
        for source_dir in self.source_dirs():
            if not (source_dir / PROVENANCE_FILENAME).exists():
                raise IngestionRefused(
                    "MISSING_PROVENANCE",
                    f"{source_dir} contains no provenance.json; an interim source with "
                    "no traceable origin cannot be labelled or published",
                )
            yield self.read_source(source_dir.name)

    def read_manifest(self, source_id: str) -> dict[str, Any]:
        path = self.root / source_id / MANIFEST_FILENAME
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist; preprocessing has not run")
        return json.loads(path.read_text(encoding="utf-8"))
