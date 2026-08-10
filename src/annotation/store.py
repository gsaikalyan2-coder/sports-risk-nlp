"""The only sanctioned way to write into `data/gold/`.

## This module is a deliberate exception, and the reasoning belongs on record

Three stores in this project refuse `data/gold/` outright:
`src/ingestion/store.py`, `src/preprocessing/store.py` and
`src/labeling/store.py` all raise `GOLD_IS_HUMAN_OWNED` if pointed at it. This
one writes there. That looks like the rule being quietly relaxed at the first
inconvenience, so here is why it is not.

`CLAUDE.md` sec.4 says **"Agents never overwrite `data/gold/` -- that is
human-owned."** Read literally as "no code may ever write there", gold can never
come into existence: a human's annotations live in an annotation tool's output
files and something has to move them. The rule's purpose is that **the content
of `data/gold/` originates from a person's judgement**, not that the bytes are
typed by hand.

So this store enforces the purpose, with four locks:

1. **`GoldLabel` cannot represent a machine author.** `author_kind` accepts only
   `human`; there is no enum member to set otherwise.
2. **The annotator must be on the roster.** `config/annotators.yaml` lists real
   people. An id that is not there is refused, so an agent cannot invent an
   annotator.
3. **Writing requires an `Annotator`, not a string.** The caller must have
   loaded the roster and selected a person. `scripts/run_annotation.py` obtains
   it from a mandatory `--annotator` argument, so a human types their own id
   every time gold is written.
4. **Silver can never become gold.** A `SilverLabel` is a different type with a
   `confidence` field this schema does not have and no `annotator_id`, so there
   is no accidental conversion path -- and `ingest_potato` is the only producer
   of `GoldLabel`s in the codebase.

**What this does NOT protect against, stated plainly:** a determined person can
hand-write a JSONL of fabricated annotations under their own roster id. No
schema stops research fraud. The locks stop *accident* -- a future session
deciding that silver labels are "good enough" to seed gold, which is the
realistic failure and the one that would silently destroy contribution #1.

## Layout

    data/gold/<batch>/<annotator_id>.jsonl   one annotator's pass
    data/gold/<batch>/manifest.json          counts, provenance, guidelines version
    data/gold/adjudicated/<batch>.jsonl      post-adjudication resolved labels

One file per annotator rather than one merged file, because independence is the
property the kappa rests on. Separate files make it structurally awkward to
overwrite one annotator's judgement with another's, and they make the second
pass unable to see the first.
"""

from __future__ import annotations

import datetime as _dt
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .schema import Annotator, GoldLabel, GoldSchemaError, load_annotators

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLD_ROOT = REPO_ROOT / "data" / "gold"

MANIFEST_FILENAME = "manifest.json"
ADJUDICATED_DIR = "adjudicated"

VALID_BATCHES = ("gold_dev", "gold_eval")


class GoldWriteRefused(RuntimeError):
    """Raised when a write into `data/gold/` violates the human-ownership rule."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"[{reason_code}] {message}")


class GoldStore:
    """Owns `data/gold/` and the rules about who may write into it."""

    def __init__(self, root: Path | None = None, roster: dict[str, Annotator] | None = None):
        self.root = Path(root) if root is not None else DEFAULT_GOLD_ROOT
        self._roster = roster

    @property
    def roster(self) -> dict[str, Annotator]:
        if self._roster is None:
            self._roster = load_annotators()
        return self._roster

    def resolve_annotator(self, annotator_id: str) -> Annotator:
        """Look up a person, refusing anyone not on the roster."""
        try:
            return self.roster[annotator_id]
        except KeyError:
            raise GoldWriteRefused(
                "UNKNOWN_ANNOTATOR",
                f"{annotator_id!r} is not in config/annotators.yaml. Gold labels come "
                f"from declared people; known ids are {sorted(self.roster)}",
            ) from None

    # -- writing ------------------------------------------------------------

    def write_pass(
        self,
        labels: Sequence[GoldLabel],
        *,
        annotator: Annotator,
        batch: str,
        overwrite: bool = False,
    ) -> Path:
        """Write one annotator's complete pass over one batch.

        `annotator` is an `Annotator` object rather than a string so the caller
        cannot supply an id it has not looked up. Overwriting is refused by
        default: a completed annotation pass is hours of human work, and
        silently replacing it because a script was re-run is not recoverable.
        """
        if batch not in VALID_BATCHES:
            raise GoldWriteRefused("UNKNOWN_BATCH", f"{batch!r} is not one of {VALID_BATCHES}")
        if annotator.annotator_id not in self.roster:
            raise GoldWriteRefused(
                "UNKNOWN_ANNOTATOR",
                f"{annotator.annotator_id!r} is not on the roster",
            )

        for label in labels:
            if label.author_kind != "human":
                raise GoldWriteRefused(
                    "NOT_HUMAN_AUTHORED",
                    f"{label.record_id!r} claims author_kind={label.author_kind!r}; "
                    "data/gold/ is human-owned (CLAUDE.md sec.4)",
                )
            if label.annotator_id != annotator.annotator_id:
                raise GoldWriteRefused(
                    "ANNOTATOR_MISMATCH",
                    f"{label.record_id!r} is attributed to {label.annotator_id!r} but is "
                    f"being written into {annotator.annotator_id!r}'s pass. One person "
                    "per file is what makes the two passes independent",
                )
            if label.batch != batch:
                raise GoldWriteRefused(
                    "BATCH_MISMATCH",
                    f"{label.record_id!r} is labelled batch={label.batch!r} but is being "
                    f"written into {batch!r}. gold_dev is calibration and gold_eval is "
                    "the evaluation set; mixing them costs evaluation power silently",
                )

        seen = [label.record_id for label in labels]
        duplicates = {r for r in seen if seen.count(r) > 1}
        if duplicates:
            raise GoldWriteRefused(
                "DUPLICATE_RECORD_ID",
                f"{sorted(duplicates)[:3]} annotated more than once in one pass",
            )

        batch_dir = self.root / batch
        batch_dir.mkdir(parents=True, exist_ok=True)
        path = batch_dir / f"{annotator.annotator_id}.jsonl"
        if path.exists() and not overwrite:
            raise GoldWriteRefused(
                "PASS_ALREADY_EXISTS",
                f"{path.name} already exists and overwrite=False. A completed pass is "
                "hours of human work; re-running a script must not silently replace it. "
                "Pass --overwrite if you really mean to",
            )

        with path.open("w", encoding="utf-8") as fh:
            for label in labels:
                fh.write(label.to_json_line() + "\n")

        self._write_manifest(batch)
        return path

    def _write_manifest(self, batch: str) -> None:
        batch_dir = self.root / batch
        passes = {}
        for path in sorted(batch_dir.glob("*.jsonl")):
            labels = self.read_pass(batch, path.stem)
            passes[path.stem] = {
                "items": len(labels),
                "escalated": sum(1 for x in labels if x.escalate),
                "uncertain": sum(1 for x in labels if x.uncertain),
                "abstained": sum(1 for x in labels if x.abstained),
            }
        payload = {
            "phase": 11,
            "batch": batch,
            "written_on": _dt.date.today().isoformat(),
            "content": "human gold annotations",
            "ground_truth": True,
            "guidelines": "docs/annotation_guidelines.md v1.0",
            "passes": passes,
            "double_annotated": len(passes) >= 2,
            "note": (
                "Agreement requires at least two independent passes. A single pass is "
                "a labelled set, not a gold standard."
            ),
        }
        (batch_dir / MANIFEST_FILENAME).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def write_adjudicated(
        self, labels: Iterable[GoldLabel], *, batch: str, overwrite: bool = False
    ) -> Path:
        """Write the post-adjudication resolved set.

        Kept in its own directory rather than replacing a pass, because the
        paper reports agreement *before* adjudication. Overwriting a raw pass
        with the adjudicated version would destroy the only evidence the kappa
        was computed from.
        """
        directory = self.root / ADJUDICATED_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{batch}.jsonl"
        if path.exists() and not overwrite:
            raise GoldWriteRefused(
                "ADJUDICATION_EXISTS", f"{path.name} exists; pass --overwrite to replace"
            )
        with path.open("w", encoding="utf-8") as fh:
            for label in labels:
                fh.write(label.to_json_line() + "\n")
        return path

    # -- reading ------------------------------------------------------------

    def annotator_ids(self, batch: str) -> list[str]:
        batch_dir = self.root / batch
        if not batch_dir.exists():
            return []
        return sorted(p.stem for p in batch_dir.glob("*.jsonl"))

    def read_pass(self, batch: str, annotator_id: str) -> list[GoldLabel]:
        path = self.root / batch / f"{annotator_id}.jsonl"
        if not path.exists():
            return []
        out: list[GoldLabel] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(GoldLabel.from_json_line(line))
            except GoldSchemaError as exc:
                raise GoldWriteRefused(
                    "CORRUPT_GOLD",
                    f"{path} contains a label that violates the schema: {exc}",
                ) from exc
        return out

    def read_batch(self, batch: str) -> dict[str, list[GoldLabel]]:
        return {aid: self.read_pass(batch, aid) for aid in self.annotator_ids(batch)}

    def read_manifest(self, batch: str) -> dict[str, Any]:
        path = self.root / batch / MANIFEST_FILENAME
        if not path.exists():
            raise FileNotFoundError(f"{path} does not exist; no pass has been written")
        return json.loads(path.read_text(encoding="utf-8"))
