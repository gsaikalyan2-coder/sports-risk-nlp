"""Parent context for annotation items -- the Phase 11 blocker, fixed here.

## The defect this module exists to close

`docs/annotation_guidelines.md` sec.3, step 1 is the first instruction an
annotator reads:

> **Read the whole record once** before marking anything. Context changes labels.

`data/processed/gold_candidates/gold_eval.jsonl` carries `parent_record_id` but
**not the parent text**. An annotator opening that file cannot follow step 1.
The rubric and the deliverable contradict each other, and the deliverable is the
one that is wrong.

Measured on the drawn set: **226 of the 325 parent records behind `gold_eval`'s
400 items have more than one utterance**, so the context exists in
`data/interim/` and was simply never surfaced.

## Why it matters twice over

1. **Agreement.** The constructs that need context are exactly the ones Phase 9
   flagged as fragile. `appraisal_orientation` is a stance toward an event, and
   a 19-token median clause frequently does not carry one. Two annotators
   guessing from a fragment disagree, and the resulting kappa measures the
   fragment, not the construct.
2. **Fairness of the Phase 14 comparison.** The Phase 10 silver labeller *was*
   given the parent record -- that was requirement #3 of the Phase 10 brief and
   the reason its deduplication saving collapsed from 31% to 0.5%
   (`docs/labeling.md` sec.3). If humans annotate without context and the model
   had it, "the model agreed with the human X% of the time" measures a context
   asymmetry rather than label quality.

So the annotation view shows the same context the labeller saw. Not more, not
less. That symmetry is the point, and it is asserted by a test.

## What is deliberately NOT done

**Spans are still marked on the utterance alone.** The parent record is shown
read-only, beside the target. If spans could be drawn anywhere in the parent,
their offsets would be into the record and would no longer align with
`InterimRecord.char_start/char_end`, with `SilverLabel.evidence_spans`, or with
anything Phase 16 highlights. Context is for *judging*; the unit of annotation
is unchanged (`docs/annotation_guidelines.md` sec.1).

**`generation_spec` is not reintroduced.** The Phase 9 sampler strips it, and an
annotator who can see what the generator planted is not an annotator. Verified
absent on load rather than assumed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTERIM = REPO_ROOT / "data" / "interim"
DEFAULT_CANDIDATES = REPO_ROOT / "data" / "processed" / "gold_candidates"

#: Fields whose mere PRESENCE in a gold candidate is a defect. These are the
#: generator's own template choices; an annotator who can see them is
#: transcribing, not annotating, and the Phase 9 sampler strips them.
FORBIDDEN_FIELDS: tuple[str, ...] = ("generation_spec", "planted_constructs")

#: Fields that legitimately exist on a candidate but must not reach the screen.
#: `annotation_batch` is one: it is how the sampler records dev-vs-eval, so it
#: belongs in the file, but an annotator who can see which items are the
#: evaluation set may unconsciously treat them differently.
#:
#: The distinction between this list and `FORBIDDEN_FIELDS` was got wrong on the
#: first attempt -- `annotation_batch` was put in the refusal list and the build
#: died on a field the Phase 9 sampler writes on purpose. Presence and display
#: are different questions, and conflating them made valid data look defective.
#: Nothing enforces this list, because `AnnotationItem.to_potato_row` is a
#: whitelist: only id, text, context and a metadata line ever reach Potato.
NOT_DISPLAYED_FIELDS: tuple[str, ...] = ("annotation_batch",)


class ContextError(RuntimeError):
    """Raised when an annotation item cannot be given honest context."""


@dataclass(frozen=True)
class AnnotationItem:
    """One utterance as an annotator will see it: target plus its record."""

    record_id: str
    parent_record_id: str
    text: str
    parent_text: str
    utterance_index: int
    siblings: int
    time_to_competition_days: int | None = None
    sport: str | None = None
    competition_level: str | None = None

    @property
    def has_context(self) -> bool:
        """True when the parent record says more than the utterance alone."""
        return self.siblings > 1

    def context_html(self) -> str:
        """The parent record with the target utterance marked, for display.

        The target is wrapped in a `<mark>` rather than merely being listed
        first, because an annotator scanning a three-sentence record needs to
        see *which* sentence they are labelling without re-reading. Everything
        is escaped before the mark is inserted -- the corpus is synthetic today,
        but an A3 donation under a future consent basis is arbitrary text and
        must not be able to inject markup into the annotator's browser.
        """
        from html import escape

        parent = escape(self.parent_text)
        target = escape(self.text)
        if target and target in parent:
            return parent.replace(target, f"<mark>{target}</mark>", 1)
        # Defensive: if the join ever stops lining up, show the record plainly
        # rather than silently displaying an unmarked wall of text that looks
        # correct. A visible oddity beats an invisible one.
        return parent

    def to_potato_row(self) -> dict[str, Any]:
        """One row of Potato's input file."""
        return {
            "id": self.record_id,
            "text": self.text,
            "context_html": self.context_html(),
            "meta": (
                f"{self.siblings} utterance(s) in this record | "
                f"{self.time_to_competition_days} day(s) before competition"
                if self.time_to_competition_days is not None
                else f"{self.siblings} utterance(s) in this record"
            ),
        }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise ContextError(f"{path} does not exist")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def parent_texts(interim_root: Path | None = None) -> dict[str, str]:
    """Rebuild every parent record's text from its utterances.

    Rebuilt from `data/interim/` rather than read from `data/raw/` for the
    reason `src/labeling/dedup.py` gives and which applies with more force
    here: the raw text is not de-identified, and `docs/ethics.md` sec.5 admits
    no exception for "it is only being shown to our own annotator". The
    de-identified utterances joined in `utterance_index` order are the same
    passage with the identifiers removed.

    This is deliberately the same reconstruction the labeller used, so the
    human and the model see the same context.
    """
    root = interim_root or DEFAULT_INTERIM
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        path = source_dir / "utterances.jsonl"
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            grouped[row["parent_record_id"]].append(row)
    return {
        parent: " ".join(r["text"] for r in sorted(group, key=lambda r: r["utterance_index"]))
        for parent, group in grouped.items()
    }


def sibling_counts(interim_root: Path | None = None) -> dict[str, int]:
    root = interim_root or DEFAULT_INTERIM
    counts: dict[str, int] = defaultdict(int)
    for source_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        path = source_dir / "utterances.jsonl"
        if not path.exists():
            continue
        for row in _read_jsonl(path):
            counts[row["parent_record_id"]] += 1
    return dict(counts)


def build_items(
    candidates: Sequence[dict[str, Any]],
    *,
    contexts: dict[str, str],
    siblings: dict[str, int],
) -> list[AnnotationItem]:
    """Attach context to gold candidates, refusing to guess when it is missing.

    A candidate whose parent is absent from `data/interim/` raises rather than
    silently falling back to the bare utterance. A silent fallback would
    reintroduce exactly the defect this module exists to close, on a subset,
    invisibly -- and a kappa computed over a mixture of contextualised and
    uncontextualised items is not interpretable.
    """
    items: list[AnnotationItem] = []
    for row in candidates:
        for field in FORBIDDEN_FIELDS:
            if field in row:
                raise ContextError(
                    f"gold candidate {row.get('record_id')!r} carries {field!r}. "
                    "An annotator who can see what the generator planted is not an "
                    "annotator -- the Phase 9 sampler strips this and it must stay stripped"
                )
        parent = row["parent_record_id"]
        if parent not in contexts:
            raise ContextError(
                f"gold candidate {row['record_id']!r} names parent {parent!r}, which is "
                "not in data/interim/. Refusing to fall back to the bare utterance: "
                "docs/annotation_guidelines.md sec.3 step 1 requires the whole record, "
                "and a partial fallback would be invisible in the resulting kappa"
            )
        items.append(
            AnnotationItem(
                record_id=row["record_id"],
                parent_record_id=parent,
                text=row["text"],
                parent_text=contexts[parent],
                utterance_index=int(row.get("utterance_index", 0)),
                siblings=int(siblings.get(parent, 1)),
                time_to_competition_days=row.get("time_to_competition_days"),
                sport=row.get("sport"),
                competition_level=row.get("competition_level"),
            )
        )
    return items


def load_batch(
    batch: str,
    *,
    candidates_dir: Path | None = None,
    interim_root: Path | None = None,
) -> list[AnnotationItem]:
    """Load `gold_dev` or `gold_eval` with context attached.

    `gold_dev` is loaded by the same code path as `gold_eval` on purpose. The
    calibration pass has to be a faithful rehearsal of the real one, or it
    calibrates the annotators against a task they will not then perform.
    """
    if batch not in ("gold_dev", "gold_eval"):
        raise ContextError(f"unknown batch {batch!r}; expected 'gold_dev' or 'gold_eval'")
    directory = candidates_dir or DEFAULT_CANDIDATES
    rows = _read_jsonl(directory / f"{batch}.jsonl")
    return build_items(
        rows,
        contexts=parent_texts(interim_root),
        siblings=sibling_counts(interim_root),
    )


def context_coverage(items: Sequence[AnnotationItem]) -> dict[str, float | int]:
    """How much context the batch actually gained. Reported, not assumed."""
    total = len(items)
    with_context = sum(1 for item in items if item.has_context)
    return {
        "items": total,
        "with_multi_utterance_context": with_context,
        "context_fraction": round(with_context / total, 4) if total else 0.0,
        "distinct_parents": len({item.parent_record_id for item in items}),
        "mean_parent_tokens": (
            round(sum(len(i.parent_text.split()) for i in items) / total, 1) if total else 0.0
        ),
        "mean_target_tokens": (
            round(sum(len(i.text.split()) for i in items) / total, 1) if total else 0.0
        ),
    }
