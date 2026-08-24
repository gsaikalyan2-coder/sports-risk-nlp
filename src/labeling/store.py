"""The only sanctioned way to write into `data/processed/silver/`.

A third restatement of the same invariants that govern `src/ingestion/store.py`
and `src/preprocessing/store.py`, one layer further down. The repetition is
deliberate and was argued in the Phase 8 store: a control that holds at
ingestion and lapses at labelling is not a control.

What is new at this layer, and specific to it:

**`generation_spec` is refused on the way out.** Phase 10 is the first phase
that writes something which genuinely is a label. It writes it into a directory
that sits beside records carrying the generator's own template choices. If a
silver row ever carried `generation_spec`, a future session would join the two
and report how well the labeller "recovered" the constructs -- which measures
whether an LLM can reverse-engineer this project's template bank, and says
nothing at all about athlete language. The check is one `in` test per record and
it removes the possibility rather than warning against it.

**The gold guard is unchanged and unweakened.** `data/gold/` is human-owned. The
root check refuses a silver root inside it, with the same refusal code the other
two stores use, so a grep for `GOLD_IS_HUMAN_OWNED` finds every place the rule
is enforced.

**Provenance is derived, never authored.** The silver provenance descends from
the interim provenance, which descends from the raw one. A silver source cannot
claim a licence basis its raw source never had. `record_count` becomes the
number of *labels*, and the note records that the content is machine-proposed --
because the single most likely misreading of this directory, by a future
collaborator or a reviewer, is that it contains ground truth.
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

from .schema import FORBIDDEN_FIELDS, SilverLabel

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SILVER_ROOT = REPO_ROOT / "data" / "processed" / "silver"
GOLD_ROOT = REPO_ROOT / "data" / "gold"

LABELS_FILENAME = "silver.jsonl"
MANIFEST_FILENAME = "labeling.json"
PROVENANCE_FILENAME = "provenance.json"


def silver_provenance(interim: Provenance, *, label_count: int) -> Provenance:
    """Derive the silver provenance from the interim one.

    The `deidentified` flag is carried, not re-asserted: labelling does not
    de-identify anything, and a layer that re-set the flag would let a
    non-de-identified source acquire the claim by passing through here.
    """
    derived = Provenance(**interim.to_dict())
    derived.record_count = label_count
    derived.notes = (
        f"{interim.notes} | Phase 10: silver labels proposed by an LLM under cost-aware "
        "routing. MACHINE-PROPOSED, NOT HUMAN GROUND TRUTH. Human gold labels are "
        "Phase 11 and live in data/gold/, which no agent writes."
    )
    return derived


class SilverWriter:
    """A writable handle on one silver source directory."""

    def __init__(self, source_dir: Path, provenance: Provenance) -> None:
        self._dir = source_dir
        self._provenance = provenance
        self._path = source_dir / LABELS_FILENAME
        self._count = 0
        self._handle: Any = None
        self._seen_ids: set[str] = set()
        self.manifest: dict[str, Any] = {}

    def __enter__(self) -> SilverWriter:
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
        # A run that died mid-batch -- a 404 on a retired model ID, a budget
        # refusal -- leaves no provenance claiming a count it did not write.
        # `config/model_routing.yaml` already argues that a job dying loudly is
        # recoverable and a silently truncated dataset is not; this is the same
        # argument applied to the artefact rather than the call.
        if exc_type is None:
            self._provenance.record_count = self._count
            self._provenance.write(self._dir)
            self._write_manifest()

    def _write_manifest(self) -> None:
        payload = {
            "phase": 10,
            "source_id": self._provenance.source_id,
            "written_on": _dt.date.today().isoformat(),
            "label_count": self._count,
            "content": "machine-proposed silver labels",
            "ground_truth": False,
            "policy": "docs/labeling.md",
            **self.manifest,
        }
        # See the newline note in __enter__: write_text translates newlines on
        # Windows too, so a manifest written there differs byte-wise from the
        # same manifest written in the container.
        with (self._dir / MANIFEST_FILENAME).open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    def write(self, label: SilverLabel) -> None:
        if self._handle is None:
            raise RuntimeError(
                "SilverWriter used outside a `with` block; the manifest and label "
                "count are only finalised on context exit"
            )
        if label.source_id != self._provenance.source_id:
            raise IngestionRefused(
                "SOURCE_ID_MISMATCH",
                f"label {label.record_id!r} claims source_id {label.source_id!r} "
                f"but is being written into {self._provenance.source_id!r}",
            )
        if label.record_id in self._seen_ids:
            raise IngestionRefused(
                "DUPLICATE_RECORD_ID",
                f"record_id {label.record_id!r} labelled twice in silver source "
                f"{self._provenance.source_id!r}",
            )
        row = label.to_dict()
        for forbidden in FORBIDDEN_FIELDS:
            if forbidden in row:
                raise IngestionRefused(
                    "GENERATION_SPEC_IN_SILVER",
                    f"label {label.record_id!r} carries {forbidden!r}. Generation "
                    "metadata must never be stored beside a label -- that is the "
                    "circularity docs/labeling.md sec.6 exists to prevent",
                )
        self._seen_ids.add(label.record_id)
        self._handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._count += 1

    def write_all(self, labels: Iterable[SilverLabel]) -> int:
        for label in labels:
            self.write(label)
        return self._count

    @property
    def count(self) -> int:
        return self._count

    @property
    def directory(self) -> Path:
        return self._dir


class SilverStore:
    """Owns `data/processed/silver/` and the rules about what may enter it."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else DEFAULT_SILVER_ROOT
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
                f"refusing to use {resolved} as a labelling root: data/gold/ is "
                "human-owned and is never written by an agent (CLAUDE.md sec.4)",
            )

    def open_source(self, interim_provenance: Provenance) -> SilverWriter:
        source_dir = self.root / interim_provenance.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        provenance = silver_provenance(interim_provenance, label_count=0)
        provenance.write(source_dir)
        return SilverWriter(source_dir, provenance)

    # -- reading back -------------------------------------------------------

    def source_dirs(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.iterdir() if p.is_dir())

    def read_source(self, source_id: str) -> tuple[Provenance, list[SilverLabel]]:
        source_dir = self.root / source_id
        provenance = Provenance.read(source_dir)
        path = source_dir / LABELS_FILENAME
        if not path.exists():
            return provenance, []
        labels = [
            SilverLabel.from_json_line(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return provenance, labels

    def iter_all(self) -> Iterator[tuple[Provenance, list[SilverLabel]]]:
        for source_dir in self.source_dirs():
            if not (source_dir / PROVENANCE_FILENAME).exists():
                raise IngestionRefused(
                    "MISSING_PROVENANCE",
                    f"{source_dir} contains no provenance.json; silver labels with no "
                    "traceable origin cannot be used for training or published",
                )
            yield self.read_source(source_dir.name)

    def read_manifest(self, source_id: str) -> dict[str, Any]:
        path = self.root / source_id / MANIFEST_FILENAME
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist; labelling has not run")
        return json.loads(path.read_text(encoding="utf-8"))
