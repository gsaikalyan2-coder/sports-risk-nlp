"""Taxonomy versioning, the changelog, and the re-label scope it implies.

Phase 12's deliverable is *"v2 taxonomy + changelog"* and its gate is *"dataset
frozen for modeling."* Two things have to be true for that freeze to mean
anything:

1. **The change is recorded with its reason.** A construct that vanishes between
   v2 and v3 with no entry is indefensible to a reviewer who counts ten
   constructs in the related-work section and nine in the table. `diff_taxonomy`
   produces the record mechanically so it cannot be forgotten, and refuses to
   emit a changelog for a version bump with no stated reason.

2. **Every silver label that the change invalidates is known.** 9,302 silver
   labels were written against v2. Some v2->v3 edits leave them all valid and
   some invalidate thousands, and the difference is not obvious by eye. Shipping
   a v3 taxonomy over v2 labels is how a dataset ends up internally inconsistent
   in a way no test catches -- the labels still parse, they just no longer mean
   what the rubric says they mean.

## Which changes invalidate labels, and which do not

The classification here is the load-bearing part of the module.

| Change | Invalidates silver? | Why |
|---|---|---|
| construct removed | yes, for that construct | the label refers to a construct that no longer exists |
| construct added | **yes, wholesale** | every existing label is silent on it, and silence is not a negative |
| definition or edge-case text changed | yes, for that construct | the labeller was prompted with the old text; the label is an answer to the old question |
| `labels` / `label_type` changed | yes, for that construct | the value space moved under the label |
| examples added, prose reworded without changing meaning | flagged `COSMETIC`, owner confirms | the prompt hash changes but the question does not |

**An added construct invalidates everything, and that is the counter-intuitive
one.** The instinct is that adding is safe. It is not: a v2 label asserting
`{cognitive_anxiety: 2}` says nothing about a new construct, and treating its
absence as "not present" fabricates a negative for every utterance in the
corpus. Fabricated negatives on a rare construct are worse than no labels at
all, because they train the model to be confidently wrong exactly where the
class is scarce.

`COSMETIC` is never inferred as safe on the module's own authority -- it is
surfaced for confirmation. Whether a reworded definition changed the question is
a judgement about meaning, and this module cannot read meaning.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

CHANGE_ADDED = "CONSTRUCT_ADDED"
CHANGE_REMOVED = "CONSTRUCT_REMOVED"
CHANGE_DEFINITION = "DEFINITION_CHANGED"
CHANGE_VALUE_SPACE = "VALUE_SPACE_CHANGED"
CHANGE_ANCHOR = "INSTRUMENT_ANCHOR_CHANGED"
CHANGE_COSMETIC = "COSMETIC"

#: Fields whose change alters the question the labeller was asked.
SEMANTIC_FIELDS = ("definition", "edge_cases", "risk_direction")
#: Fields whose change alters the space of permitted answers.
VALUE_FIELDS = ("label_type", "labels", "default")
#: Changed prose that does not move the question, but does move the prompt hash.
COSMETIC_FIELDS = ("positive_examples", "negative_examples", "note")


class TaxonomyVersionError(ValueError):
    """Refusal to produce a changelog that would not be defensible."""


@dataclass(frozen=True)
class TaxonomyChange:
    """One difference between two taxonomy versions."""

    kind: str
    construct: str
    field_name: str = ""
    before: Any = None
    after: Any = None

    @property
    def invalidates_silver(self) -> bool:
        """Whether silver labels written under the old version survive this."""
        return self.kind in (
            CHANGE_ADDED,
            CHANGE_REMOVED,
            CHANGE_DEFINITION,
            CHANGE_VALUE_SPACE,
        )

    @property
    def scope(self) -> str:
        """`all` when every label is affected, otherwise just this construct."""
        return "all" if self.kind == CHANGE_ADDED else self.construct

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "construct": self.construct,
            "field": self.field_name or None,
            "before": self.before,
            "after": self.after,
            "invalidates_silver": self.invalidates_silver,
            "relabel_scope": self.scope,
        }

    def describe(self) -> str:
        if self.kind == CHANGE_ADDED:
            return (
                f"**{self.construct} added.** Every existing silver label is silent on "
                "it, and silence is not a negative -- the whole corpus needs relabelling "
                "for this construct or it enters training as a fabricated negative"
            )
        if self.kind == CHANGE_REMOVED:
            return (
                f"**{self.construct} removed.** Existing labels refer to a construct "
                "that no longer exists; strip them rather than leave them unreferenced"
            )
        if self.kind == CHANGE_COSMETIC:
            return (
                f"{self.construct}.{self.field_name} reworded. Flagged COSMETIC: the "
                "prompt hash moves but the question may not. **Owner confirms** whether "
                "this changed what was being asked -- a module cannot read meaning"
            )
        return (
            f"{self.construct}.{self.field_name} changed. The labeller was prompted with "
            "the old text, so its answers are answers to the old question; relabel this "
            "construct"
        )


def _normalise(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_normalise(v) for v in value]
    return value


def diff_taxonomy(old: dict[str, Any], new: dict[str, Any]) -> list[TaxonomyChange]:
    """Every difference between two loaded taxonomies, classified by impact."""
    old_c = old.get("constructs") or {}
    new_c = new.get("constructs") or {}
    changes: list[TaxonomyChange] = []

    for name in sorted(set(new_c) - set(old_c)):
        changes.append(TaxonomyChange(kind=CHANGE_ADDED, construct=name, after=new_c[name]))
    for name in sorted(set(old_c) - set(new_c)):
        changes.append(TaxonomyChange(kind=CHANGE_REMOVED, construct=name, before=old_c[name]))

    for name in sorted(set(old_c) & set(new_c)):
        before, after = old_c[name] or {}, new_c[name] or {}
        for field_name in SEMANTIC_FIELDS:
            if _normalise(before.get(field_name)) != _normalise(after.get(field_name)):
                changes.append(
                    TaxonomyChange(
                        kind=CHANGE_DEFINITION,
                        construct=name,
                        field_name=field_name,
                        before=before.get(field_name),
                        after=after.get(field_name),
                    )
                )
        for field_name in VALUE_FIELDS:
            if _normalise(before.get(field_name)) != _normalise(after.get(field_name)):
                changes.append(
                    TaxonomyChange(
                        kind=CHANGE_VALUE_SPACE,
                        construct=name,
                        field_name=field_name,
                        before=before.get(field_name),
                        after=after.get(field_name),
                    )
                )
        if _normalise(before.get("instrument_anchor")) != _normalise(
            after.get("instrument_anchor")
        ):
            changes.append(
                TaxonomyChange(
                    kind=CHANGE_ANCHOR,
                    construct=name,
                    field_name="instrument_anchor",
                    before=before.get("instrument_anchor"),
                    after=after.get("instrument_anchor"),
                )
            )
        for field_name in COSMETIC_FIELDS:
            if _normalise(before.get(field_name)) != _normalise(after.get(field_name)):
                changes.append(
                    TaxonomyChange(
                        kind=CHANGE_COSMETIC,
                        construct=name,
                        field_name=field_name,
                        before=before.get(field_name),
                        after=after.get(field_name),
                    )
                )
    return changes


@dataclass(frozen=True)
class RelabelScope:
    """How much silver a proposed taxonomy change invalidates."""

    total_labels: int
    affected_labels: int
    affected_records: int
    whole_corpus: bool
    constructs: tuple[str, ...]
    distinct_texts_affected: int

    @property
    def share(self) -> float:
        return self.affected_labels / self.total_labels if self.total_labels else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_silver_labels": self.total_labels,
            "affected_labels": self.affected_labels,
            "affected_records": self.affected_records,
            "distinct_texts_to_relabel": self.distinct_texts_affected,
            "share_of_silver_invalidated": round(self.share, 4),
            "whole_corpus_relabel": self.whole_corpus,
            "constructs": list(self.constructs),
        }


def relabel_scope(
    changes: Sequence[TaxonomyChange],
    silver_labels: Iterable[Any],
) -> RelabelScope:
    """Count what a proposed change costs in re-labelling.

    Counts **distinct texts** as well as records because Phase 9 measured 87.4%
    exact duplication: the relabel bill is driven by the distinct set, not the
    record count, and quoting the record count would overstate the cost by
    roughly 4x and could talk the owner out of a change that is cheap.
    """
    affected = {c.construct for c in changes if c.invalidates_silver and c.kind != CHANGE_ADDED}
    whole = any(c.kind == CHANGE_ADDED for c in changes)

    total = 0
    affected_labels = 0
    records: set[str] = set()
    texts: set[str] = set()

    for label in silver_labels:
        labels = getattr(label, "labels", ()) or ()
        total += len(labels)
        hit = whole or any(getattr(item, "construct", None) in affected for item in labels)
        if whole:
            affected_labels += len(labels)
        else:
            affected_labels += sum(
                1 for item in labels if getattr(item, "construct", None) in affected
            )
        if hit:
            records.add(getattr(label, "record_id", ""))
            texts.add(getattr(label, "text", ""))

    return RelabelScope(
        total_labels=total,
        affected_labels=affected_labels,
        affected_records=len(records),
        whole_corpus=whole,
        constructs=tuple(sorted(affected)) if not whole else ("<all>",),
        distinct_texts_affected=len(texts),
    )


@dataclass
class Changelog:
    """The Phase 12 deliverable: what changed, why, and what it invalidated."""

    old_version: int
    new_version: int
    reason: str
    changes: list[TaxonomyChange]
    scope: RelabelScope | None = None
    decided_on: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).date().isoformat())

    def __post_init__(self) -> None:
        if self.new_version <= self.old_version:
            raise TaxonomyVersionError(
                f"new version {self.new_version} does not advance {self.old_version}. "
                "A taxonomy edit that reuses a version number makes every artifact "
                "stamped with that version ambiguous"
            )
        if self.changes and not self.reason.strip():
            raise TaxonomyVersionError(
                "a taxonomy version bump needs a stated reason. Phase 12's gate is "
                "'post-refinement agreement improves OR IS JUSTIFIED'; an unjustified "
                "change cannot satisfy the second half"
            )

    @property
    def invalidating(self) -> list[TaxonomyChange]:
        return [c for c in self.changes if c.invalidates_silver]

    @property
    def cosmetic(self) -> list[TaxonomyChange]:
        return [c for c in self.changes if c.kind == CHANGE_COSMETIC]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": 12,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "decided_on": self.decided_on,
            "reason": self.reason,
            "n_changes": len(self.changes),
            "n_invalidating": len(self.invalidating),
            "changes": [c.to_dict() for c in self.changes],
            "relabel_scope": self.scope.to_dict() if self.scope else None,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Taxonomy changelog -- v{self.old_version} to v{self.new_version}",
            "",
            f"Decided {self.decided_on}. **Reason:** {self.reason}",
            "",
        ]
        if not self.changes:
            lines += [
                "No changes. The v2 construct set is carried into the freeze unchanged, "
                "which is a Phase 12 outcome in good standing -- the phase exists to "
                "check, not to change.",
            ]
            return "\n".join(lines)

        lines += ["## Changes", ""]
        for change in self.changes:
            lines.append(f"- [{change.kind}] {change.describe()}")

        if self.cosmetic:
            lines += [
                "",
                "## Awaiting owner confirmation",
                "",
                "These reworded fields move the prompt hash. Whether they moved the "
                "*question* is a judgement about meaning that no diff can make:",
                "",
            ]
            for change in self.cosmetic:
                lines.append(f"- `{change.construct}.{change.field_name}`")

        if self.scope:
            s = self.scope
            lines += [
                "",
                "## Re-labelling this implies",
                "",
                f"- **{s.affected_labels:,}** of {s.total_labels:,} silver labels "
                f"invalidated (**{s.share:.1%}**)",
                f"- **{s.affected_records:,}** records, but only "
                f"**{s.distinct_texts_affected:,} distinct texts**",
                "",
                "The distinct-text count is the one that costs money. Phase 9 measured "
                "87.4% exact duplication, so quoting the record count would overstate "
                "the bill several-fold and could talk the owner out of a change that is "
                "cheap. Deduplicate before the API call, as Phase 10 does.",
            ]
            if s.whole_corpus:
                lines += [
                    "",
                    "> A construct was **added**. Every existing label is silent on it, "
                    "and silence is not a negative. The whole corpus is relabelled for "
                    "the new construct or it enters training as a fabricated negative on "
                    "every utterance -- worst precisely where the class is rare.",
                ]
        return "\n".join(lines)
