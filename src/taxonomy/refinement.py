"""Turn disagreement into a taxonomy decision -- the Phase 12 analysis.

Phase 11 produces a kappa per construct and an adjudication worklist. Neither
tells you what to *do*. A kappa of 0.31 on `burnout_signal` is compatible with
at least four different repairs, and they are not interchangeable:

| What the disagreement actually is | The repair |
|---|---|
| they disagree on *whether* it is present | the definition or the boundary is wrong -- revise the rubric |
| they agree it is present, disagree on *how strongly* | the intensity anchors are wrong -- revise the anchors |
| they agree on presence and intensity, disagree on *where* | the span rule is wrong -- revise the span rule |
| one annotator's evidence is the other's evidence for a different construct | the two constructs are not separable in text -- merge or sharpen |

Averaging those together and calling it "poor agreement" loses the only
information that says which fix to apply. So this module **decomposes**
disagreement before it recommends anything.

## Why the verdict is a recommendation and never an action

`REVISE_RUBRIC`, `DROP_CANDIDATE` and the rest are inputs to an owner decision
that `CLAUDE.md` sec.10 reserves for Saikalyan. Nothing here edits
`config/taxonomy.yaml`. A construct set that a script can quietly shrink is not
frozen, and "frozen at Phase 12" is a claim the paper makes.

## The trap this module is built to avoid

The obvious move at Phase 12 is to drop whatever scores badly. That optimises
the reported kappa and damages the paper, because the constructs that score
worst are the rare, clinically loaded ones -- `burnout_signal` above all -- and
those are the ones a reviewer cares most about. Dropping a construct because it
is *rare* rather than because it is *unreliable* is measuring the sample and
acting on the taxonomy.

`ConstructAgreement` already separates those two cases: `is_rare` flags the
kappa paradox, `is_degenerate` flags "nobody ever marked it". This module keeps
that separation all the way into the verdict, and `UNDER_SAMPLED` exists
precisely so a sampling problem cannot be recorded as a taxonomy problem.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from src.annotation.agreement import AgreementReport, ConstructAgreement, band

#: Conventional Landis-Koch boundaries. These are REPORTING thresholds; they
#: decide what a construct is flagged as, never whether the gate passes.
KAPPA_SUBSTANTIAL = 0.60
KAPPA_MODERATE = 0.40

#: Below this span F1 the two annotators are marking different text even when
#: they agree the construct is there, which is a span-rule failure and not a
#: definition failure.
SPAN_F1_WEAK = 0.50

#: A construct whose disagreements are overwhelmingly about intensity has an
#: anchor problem, not a boundary problem.
INTENSITY_DOMINANT = 0.60

VERDICT_KEEP = "KEEP"
VERDICT_REVISE_RUBRIC = "REVISE_RUBRIC"
VERDICT_REVISE_INTENSITY_ANCHORS = "REVISE_INTENSITY_ANCHORS"
VERDICT_REVISE_SPAN_RULE = "REVISE_SPAN_RULE"
VERDICT_MERGE_CANDIDATE = "MERGE_CANDIDATE"
VERDICT_DROP_CANDIDATE = "DROP_CANDIDATE"
VERDICT_UNDER_SAMPLED = "UNDER_SAMPLED"


@dataclass(frozen=True)
class DisagreementProfile:
    """What *kind* of disagreement a construct attracts."""

    construct: str
    n_disagreements: int
    presence: int
    intensity_only: int
    span_only: int
    either_uncertain: int

    @property
    def intensity_share(self) -> float:
        return self.intensity_only / self.n_disagreements if self.n_disagreements else 0.0

    @property
    def presence_share(self) -> float:
        return self.presence / self.n_disagreements if self.n_disagreements else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "n_disagreements": self.n_disagreements,
            "presence_disagreements": self.presence,
            "intensity_only_disagreements": self.intensity_only,
            "span_only_disagreements": self.span_only,
            "flagged_uncertain_by_either": self.either_uncertain,
            "intensity_share": round(self.intensity_share, 4),
            "presence_share": round(self.presence_share, 4),
        }


def profile_disagreements(
    rows: Sequence[dict[str, Any]], constructs: Sequence[str], *, annotators: Sequence[str]
) -> dict[str, DisagreementProfile]:
    """Decompose `agreement.disagreements()` rows by construct and by kind.

    Reads the two annotators' columns by name because `disagreements()` keys
    them by annotator id -- the worklist is written for a human to read, and
    this consumes it rather than recomputing from the passes, so the analysis
    and the adjudication session are looking at exactly the same rows.
    """
    if len(annotators) != 2:
        raise ValueError(f"expected exactly two annotator ids, got {list(annotators)}")
    a_id, b_id = annotators
    counts = {
        name: {"n": 0, "presence": 0, "intensity": 0, "span": 0, "uncertain": 0}
        for name in constructs
    }

    for row in rows:
        name = row.get("construct")
        if name not in counts:
            continue
        bucket = counts[name]
        bucket["n"] += 1
        if row.get("either_uncertain"):
            bucket["uncertain"] += 1
        if row.get("presence_disagreement"):
            bucket["presence"] += 1
            continue
        ia, ib = row.get(f"{a_id}_intensity"), row.get(f"{b_id}_intensity")
        if ia != ib:
            bucket["intensity"] += 1
            continue
        # Same presence, same intensity, still on the worklist: the value or the
        # spans differ. Either way it is a span/label-surface question.
        bucket["span"] += 1

    return {
        name: DisagreementProfile(
            construct=name,
            n_disagreements=bucket["n"],
            presence=bucket["presence"],
            intensity_only=bucket["intensity"],
            span_only=bucket["span"],
            either_uncertain=bucket["uncertain"],
        )
        for name, bucket in counts.items()
    }


def confusion_pairs(
    rows: Sequence[dict[str, Any]], *, annotators: Sequence[str], min_count: int = 2
) -> list[dict[str, Any]]:
    """Records where one annotator asserted A and the other asserted B instead.

    This is the merge signal, and it cannot be seen in any single construct's
    kappa: `perceived_stress` and `cognitive_anxiety` can each score moderately
    while the *same items* swap between them. Two constructs that systematically
    trade places are one construct that the rubric has split, or two whose
    boundary text needs to name the other by name.
    """
    a_id, b_id = annotators
    by_record: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        if not row.get("presence_disagreement"):
            continue
        rid = row["record_id"]
        slot = by_record.setdefault(rid, {"a": set(), "b": set()})
        if row.get(f"{a_id}_value") not in (None, "none"):
            slot["a"].add(row["construct"])
        if row.get(f"{b_id}_value") not in (None, "none"):
            slot["b"].add(row["construct"])

    tally: dict[tuple[str, str], int] = {}
    for slot in by_record.values():
        for left in slot["a"]:
            for right in slot["b"]:
                if left == right:
                    continue
                key = tuple(sorted((left, right)))  # unordered: who said which is not the point
                tally[key] = tally.get(key, 0) + 1

    return [
        {"constructs": list(pair), "co_swapped_items": count}
        for pair, count in sorted(tally.items(), key=lambda kv: -kv[1])
        if count >= min_count
    ]


@dataclass(frozen=True)
class ConstructVerdict:
    """A recommendation for one construct. An input to a decision, not a decision."""

    construct: str
    verdict: str
    kappa: float
    rationale: str
    marginal_hours: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "verdict": self.verdict,
            "kappa": round(self.kappa, 4),
            "band": band(self.kappa),
            "marginal_hours_over_batch": (
                round(self.marginal_hours, 3) if self.marginal_hours is not None else None
            ),
            "rationale": self.rationale,
        }


def verdict_for(
    agreement: ConstructAgreement,
    profile: DisagreementProfile | None,
    *,
    merge_partners: Sequence[str] = (),
    marginal_hours: float | None = None,
) -> ConstructVerdict:
    """One construct's recommendation, in the order the cases must be checked.

    Order matters. `UNDER_SAMPLED` is tested first because a construct nobody
    marked has an undefined kappa, and every later rule would read that
    undefined number as evidence of unreliability.
    """
    kappa = agreement.kappa

    if agreement.is_degenerate:
        return ConstructVerdict(
            construct=agreement.construct,
            verdict=VERDICT_UNDER_SAMPLED,
            kappa=kappa,
            marginal_hours=marginal_hours,
            rationale=(
                "Neither annotator marked it anywhere in the batch, so kappa is "
                "undefined -- there is nothing to agree about. This is a statement "
                "about the sample, not about the construct. Do NOT drop it on this "
                "evidence: decide whether the corpus fails to realise it (a generator "
                "gap, and a Phase 7 problem) or the sample missed it (a Phase 9 "
                "problem). Dropping here would be acting on the taxonomy to fix a "
                "sampling defect"
            ),
        )

    if merge_partners:
        return ConstructVerdict(
            construct=agreement.construct,
            verdict=VERDICT_MERGE_CANDIDATE,
            kappa=kappa,
            marginal_hours=marginal_hours,
            rationale=(
                f"Systematically traded with {list(merge_partners)} on the same items: "
                "one annotator asserts this, the other asserts that, on the same text. "
                "That is a boundary the rubric does not draw. Either merge, or add "
                "edge-case text to BOTH entries naming the other explicitly -- "
                "sharpening one side alone moves the confusion, it does not remove it"
            ),
        )

    if agreement.is_rare and kappa < KAPPA_MODERATE:
        return ConstructVerdict(
            construct=agreement.construct,
            verdict=VERDICT_KEEP,
            kappa=kappa,
            marginal_hours=marginal_hours,
            rationale=(
                f"Low kappa ({kappa:.2f}) at "
                f"{max(agreement.prevalence_a, agreement.prevalence_b):.1%} prevalence "
                f"with {agreement.percent_agreement:.1%} raw agreement. This is the "
                "kappa paradox, not poor annotation. The rare constructs here are the "
                "clinically loaded ones a reviewer cares most about; dropping them "
                "would optimise the headline number and weaken the paper. Report the "
                "prevalence beside the kappa and keep"
            ),
        )

    if profile and profile.n_disagreements:
        if profile.intensity_share >= INTENSITY_DOMINANT and kappa >= KAPPA_MODERATE:
            return ConstructVerdict(
                construct=agreement.construct,
                verdict=VERDICT_REVISE_INTENSITY_ANCHORS,
                kappa=kappa,
                marginal_hours=marginal_hours,
                rationale=(
                    f"{profile.intensity_share:.0%} of disagreements are intensity-only "
                    f"(weighted kappa {agreement.weighted_kappa:.2f} against "
                    f"{kappa:.2f} unweighted). They agree the construct is there and "
                    "disagree on how strongly, so the definition is working and the "
                    "0/1/2/3 anchors are not. Fix the anchors in "
                    "docs/annotation_guidelines.md; the construct itself is sound"
                ),
            )
        if agreement.span_f1 < SPAN_F1_WEAK and kappa >= KAPPA_MODERATE:
            return ConstructVerdict(
                construct=agreement.construct,
                verdict=VERDICT_REVISE_SPAN_RULE,
                kappa=kappa,
                marginal_hours=marginal_hours,
                rationale=(
                    f"Presence agreement is {band(kappa)} ({kappa:.2f}) but span F1 is "
                    f"only {agreement.span_f1:.2f}: they agree it is expressed and mark "
                    "different text. Contribution #2 is span-level explanation, so a "
                    "span rule this loose degrades the headline contribution while "
                    "leaving the kappa table looking healthy. Tighten the minimal-span "
                    "rule and add worked examples"
                ),
            )

    if kappa < KAPPA_MODERATE:
        return ConstructVerdict(
            construct=agreement.construct,
            verdict=VERDICT_DROP_CANDIDATE,
            kappa=kappa,
            marginal_hours=marginal_hours,
            rationale=(
                f"kappa {kappa:.2f} at "
                f"{max(agreement.prevalence_a, agreement.prevalence_b):.1%} prevalence -- "
                "not rare, so this is not the kappa paradox: two annotators reading the "
                "same rubric reach different judgements on a construct they both see "
                "often. Owner decision. Try one rubric revision and a re-annotation of "
                "the affected batch first; drop only if it does not move, and record "
                "the attempt either way -- an unreliable construct that survives into "
                "the corpus makes every model trained on it unreliable, silently"
            ),
        )

    if kappa < KAPPA_SUBSTANTIAL:
        return ConstructVerdict(
            construct=agreement.construct,
            verdict=VERDICT_REVISE_RUBRIC,
            kappa=kappa,
            marginal_hours=marginal_hours,
            rationale=(
                f"Moderate kappa ({kappa:.2f}), "
                f"{profile.presence_share if profile else 0:.0%} of disagreements about "
                "presence. Workable, not yet defensible. Revise the definition and "
                "edge-case text, then re-run the affected batch"
            ),
        )

    return ConstructVerdict(
        construct=agreement.construct,
        verdict=VERDICT_KEEP,
        kappa=kappa,
        marginal_hours=marginal_hours,
        rationale=f"{band(kappa)} agreement ({kappa:.2f}); span F1 {agreement.span_f1:.2f}",
    )


@dataclass
class RefinementReport:
    """The Phase 12 analysis for one batch."""

    batch: str
    annotators: tuple[str, str]
    verdicts: list[ConstructVerdict]
    profiles: dict[str, DisagreementProfile]
    confusions: list[dict[str, Any]]

    def by_verdict(self, verdict: str) -> list[str]:
        return [v.construct for v in self.verdicts if v.verdict == verdict]

    @property
    def needs_owner_decision(self) -> list[str]:
        return [
            v.construct
            for v in self.verdicts
            if v.verdict in (VERDICT_DROP_CANDIDATE, VERDICT_MERGE_CANDIDATE)
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": 12,
            "batch": self.batch,
            "annotators": list(self.annotators),
            "verdicts": [v.to_dict() for v in self.verdicts],
            "disagreement_profiles": [p.to_dict() for p in self.profiles.values()],
            "confusion_pairs": self.confusions,
            "requires_owner_decision": self.needs_owner_decision,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Phase 12 -- label validation and taxonomy refinement ({self.batch})",
            "",
            f"Annotators **{self.annotators[0]}** and **{self.annotators[1]}**.",
            "",
            "Every row is a **recommendation**. Nothing here edits `config/taxonomy.yaml`; "
            "the construct set is an owner decision (`CLAUDE.md` sec.10), and a taxonomy a "
            "script can quietly shrink is not frozen.",
            "",
            "| construct | kappa | verdict | marginal h | why |",
            "|---|---|---|---|---|",
        ]
        for row in sorted(self.verdicts, key=lambda v: v.kappa):
            hours = f"{row.marginal_hours:.2f}" if row.marginal_hours is not None else "--"
            lines.append(
                f"| {row.construct} | {row.kappa:.3f} | **{row.verdict}** | {hours} | "
                f"{row.rationale} |"
            )

        lines += ["", "## What kind of disagreement each construct attracts", ""]
        lines += [
            "| construct | n | presence | intensity only | span only | flagged uncertain |",
            "|---|---|---|---|---|---|",
        ]
        for prof in sorted(self.profiles.values(), key=lambda p: -p.n_disagreements):
            lines.append(
                f"| {prof.construct} | {prof.n_disagreements} | {prof.presence} | "
                f"{prof.intensity_only} | {prof.span_only} | {prof.either_uncertain} |"
            )

        lines += ["", "## Constructs that trade places", ""]
        if self.confusions:
            lines += ["| pair | items where they swapped |", "|---|---|"]
            for row in self.confusions:
                lines.append(f"| {' <-> '.join(row['constructs'])} | {row['co_swapped_items']} |")
            lines += [
                "",
                "A pair here is invisible in either construct's own kappa. Both can score "
                "moderately while the same items swap between them.",
            ]
        else:
            lines.append("None above threshold.")

        if self.needs_owner_decision:
            lines += [
                "",
                "## Owner decision required",
                "",
                f"`{'`, `'.join(self.needs_owner_decision)}`",
                "",
                "Do not proceed to the freeze until each is decided and the decision is "
                "written into the changelog with its reason. A construct dropped without "
                "a recorded reason cannot be defended to a reviewer who asks why the "
                "taxonomy has nine entries and the related-work section has ten.",
            ]
        return "\n".join(lines)


def analyse(
    agreement: AgreementReport,
    disagreement_rows: Sequence[dict[str, Any]],
    *,
    burden: Any = None,
    min_confusion: int = 2,
) -> RefinementReport:
    """Full Phase 12 analysis from Phase 11 artifacts.

    `burden` is an optional `burden.BurdenReport`; when supplied, each verdict
    carries the marginal hours that dropping the construct would return, which
    is the other half of the freeze criterion.
    """
    annotators = (agreement.annotator_a, agreement.annotator_b)
    constructs = [c.construct for c in agreement.constructs]
    profiles = profile_disagreements(disagreement_rows, constructs, annotators=annotators)
    confusions = confusion_pairs(disagreement_rows, annotators=annotators, min_count=min_confusion)

    partners: dict[str, list[str]] = {name: [] for name in constructs}
    for row in confusions:
        left, right = row["constructs"]
        partners[left].append(right)
        partners[right].append(left)

    hours: dict[str, float] = {}
    if burden is not None:
        hours = {c.construct: c.marginal_hours_batch for c in burden.per_construct}

    verdicts = [
        verdict_for(
            item,
            profiles.get(item.construct),
            merge_partners=partners.get(item.construct, ()),
            marginal_hours=hours.get(item.construct),
        )
        for item in agreement.constructs
    ]

    return RefinementReport(
        batch=agreement.batch,
        annotators=annotators,
        verdicts=verdicts,
        profiles=profiles,
        confusions=confusions,
    )
