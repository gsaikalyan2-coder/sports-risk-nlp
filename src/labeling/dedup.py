"""Deduplication: pay for each distinct prompt once, then fan the answer out.

At `temperature: 0.0` two calls with an identical payload are the same call.
Paying for both is paying twice for one answer, so the batch planner groups
utterances by prompt hash, sends one representative per group, and copies the
result onto the rest.

**The measurement that decided the design, and it contradicts the brief.**

`phase10_handover.md` and `reports/eda.md` both put the saving at ~31%: 9,302
utterances over 6,444 distinct texts. That figure is correct and it does not
survive contact with the requirement to pass the parent record as context. Two
identical utterances in different parent records produce *different prompts*, so
they are not the same call and their answers may legitimately differ. Keying the
cache on utterance text alone would silently assign one record's context to
another record's label.

Recomputed on `data/interim/synth_precomp_v1` at generator v1.4:

| Key                                | Distinct | Saving |
|------------------------------------|----------|--------|
| utterance text alone               | 6,444    | 30.7%  |
| (utterance, parent record) -- used | 9,185    |  1.3%  |

636 utterance texts appear in more than one distinct parent record, and they are
the frequent ones -- `"Results from the heats should be up by lunchtime."`
occurs 109 times across 109 different records. So nearly the whole of the 31%
came from exactly the strings whose context differs.

**The saving was given up, deliberately.** The whole pass costs on the order of
$1 on the cheap tier (`config/model_routing.yaml`'s own worked estimate), so the
difference between the two keys is roughly $0.35. Buying context for the
constructs that need it -- `appraisal_orientation` is a stance toward an event
and a 17-token clause frequently does not carry one -- is worth $0.35. Had the
pass cost $300 the trade would deserve a real argument; at $1 it does not.

`--no-context` exists so the abandoned option remains measurable rather than
merely asserted. It is an ablation, not a shortcut.

The correctness property is what makes the key defensible at all: the key is a
hash of the **exact bytes sent to the model**, so "same key implies same answer"
is true by construction rather than by an argument about which parts of the
prompt matter.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field

from src.preprocessing.records import InterimRecord

from .prompt import build_user_prompt, prompt_hash


@dataclass(frozen=True)
class PromptUnit:
    """One distinct prompt payload, plus every record that shares it."""

    key: str
    user_prompt: str
    representative: InterimRecord
    members: tuple[InterimRecord, ...]

    @property
    def fanout(self) -> int:
        return len(self.members)


@dataclass
class DedupPlan:
    """The batch plan: what will be sent, and what will be copied."""

    units: list[PromptUnit] = field(default_factory=list)
    total_records: int = 0

    @property
    def calls(self) -> int:
        return len(self.units)

    @property
    def copied(self) -> int:
        return self.total_records - self.calls

    @property
    def saving_fraction(self) -> float:
        if self.total_records == 0:
            return 0.0
        return self.copied / self.total_records

    def summary(self) -> str:
        return (
            f"{self.total_records} utterance(s) -> {self.calls} distinct prompt(s); "
            f"{self.copied} copied ({100 * self.saving_fraction:.1f}% of calls saved)"
        )


def parent_context(records: Sequence[InterimRecord]) -> dict[str, str]:
    """Reconstruct each parent record's text from its utterances.

    Rebuilt from `data/interim/` rather than re-read from `data/raw/` on
    purpose: the raw text is not de-identified, and `docs/ethics.md` sec.5
    admits no exception for "it is only going into a prompt". The de-identified
    utterances joined in `utterance_index` order are the same passage with the
    identifiers removed, which is exactly what may be sent to a third party.
    """
    grouped: dict[str, list[InterimRecord]] = defaultdict(list)
    for record in records:
        grouped[record.parent_record_id].append(record)
    return {
        parent: " ".join(r.text for r in sorted(group, key=lambda r: r.utterance_index))
        for parent, group in grouped.items()
    }


def build_plan(
    records: Sequence[InterimRecord],
    *,
    system_prompt: str,
    use_context: bool = True,
) -> DedupPlan:
    """Group records by prompt payload, preserving input order.

    Order matters for reproducibility: the first record of each group in corpus
    order becomes the representative, so the same corpus always sends the same
    prompts in the same sequence, and a partially-completed run resumes to the
    same place.
    """
    contexts = parent_context(records) if use_context else {}

    order: list[str] = []
    by_key: dict[str, list[InterimRecord]] = {}
    prompts: dict[str, str] = {}

    for record in records:
        user = build_user_prompt(
            text=record.text,
            context=contexts.get(record.parent_record_id) if use_context else None,
            time_to_competition_days=record.time_to_competition_days,
        )
        key = prompt_hash(system_prompt, user)
        if key not in by_key:
            by_key[key] = []
            prompts[key] = user
            order.append(key)
        by_key[key].append(record)

    units = [
        PromptUnit(
            key=key,
            user_prompt=prompts[key],
            representative=by_key[key][0],
            members=tuple(by_key[key]),
        )
        for key in order
    ]
    return DedupPlan(units=units, total_records=len(records))
