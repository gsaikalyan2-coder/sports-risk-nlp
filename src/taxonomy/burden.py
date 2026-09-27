"""Annotation burden - the second half of the Phase 12 freeze criterion (OPEN-026).

`config/taxonomy.yaml` freezes the construct set at Phase 12 *"after checking
annotation burden and inter-annotator agreement."* Phase 11 made agreement
computable. This module makes burden computable, and it exists because the
freeze decision has two inputs and the project only had one.

## What this is, and what it is emphatically not

This is a **decision model**, not a measurement. It counts the decisions
`src/annotation/potato_project.py` actually puts in front of an annotator -
derived from the same `taxonomy.yaml` that generates the Potato schemes, so the
two cannot drift - and converts that count into time using per-decision
constants.

**Those constants are an assumption until someone holds a stopwatch.** That is
OPEN-026 and no amount of arithmetic closes it. So:

- `DEFAULT_TIMING` is marked `measured=False` and every report it produces says
  so in its own text. A burden figure that does not disclose its provenance is
  how an assumption becomes a citation.
- `TimingModel.from_measurement()` takes an observed minutes-per-item from a
  real `gold_dev` pass and rescales the whole model to it. One stopwatch reading
  over 100 items retires the assumption for all 400.

The distinction is load-bearing because of the failure OPEN-026 names: an
annotator who rushes the last 200 items produces a worse dataset than one who
carefully does 200, **and the damage is invisible in the kappa** - two tired
annotators drift toward the same defaults and agree *more*. Burden is therefore
not a comfort metric. It is the only guard against a kappa that looks good
because both people gave up.

## Marginal burden, not total burden

The useful question at Phase 12 is never "how long does the batch take" but
"what does dropping this construct buy". So `ConstructBurden` reports each
construct's **marginal** cost - the time that disappears from the whole batch if
it is removed - which is what gets weighed against its kappa. A construct with
poor agreement and high marginal cost is a drop candidate; the same poor
agreement on a cheap construct is an argument for fixing the rubric instead.

The span pass is *shared*: removing one construct does not remove the reading of
the utterance. Charging each construct a share of a cost that does not disappear
would overstate what dropping it saves, and overstating that is how a taxonomy
gets trimmed for no gain. Only the per-construct intensity judgement, and the
span-marking attributable to it, are marginal.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

#: Constructs the annotator answers for *every* item regardless of content, plus
#: the fixed per-item overhead. Kept as named parts rather than one number so a
#: measurement can be attributed to the step it actually came from.
READ_CONTEXT = "read_context"
SPAN_PASS = "span_pass"
INTENSITY_ONE = "intensity_one_construct"
MODIFIER = "interpretation_modifier"
FLAGS_AND_NOTE = "flags_and_note"


@dataclass(frozen=True)
class TimingModel:
    """Seconds per annotation decision.

    `measured` is not decoration. It is carried into every report so a reader
    can tell an estimate from a measurement, and `to_dict()` refuses to let it
    be dropped.
    """

    read_context_s: float = 22.0
    span_pass_s: float = 18.0
    intensity_per_construct_s: float = 6.0
    modifier_s: float = 5.0
    flags_and_note_s: float = 4.0
    measured: bool = False
    basis: str = (
        "UNMEASURED ASSUMPTION (OPEN-026). Numbers chosen to be plausible for a "
        "9-token median utterance read in its parent-record context; no human has "
        "been timed. Replace with TimingModel.from_measurement() after the "
        "gold_dev calibration pass."
    )

    def __post_init__(self) -> None:
        for field_name in (
            "read_context_s",
            "span_pass_s",
            "intensity_per_construct_s",
            "modifier_s",
            "flags_and_note_s",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")

    def seconds_per_item(self, n_constructs: int, *, modifier_applicable: bool = True) -> float:
        return (
            self.read_context_s
            + self.span_pass_s
            + self.intensity_per_construct_s * n_constructs
            + (self.modifier_s if modifier_applicable else 0.0)
            + self.flags_and_note_s
        )

    @classmethod
    def from_measurement(
        cls,
        *,
        observed_minutes_per_item: float,
        n_constructs: int,
        source: str,
    ) -> TimingModel:
        """Rescale the model so it reproduces a real observation.

        The *shape* of the model - that intensity scales with the construct
        count and the read does not - survives; only the level is corrected.
        That is the honest use of one stopwatch reading: it cannot tell you how
        the time split across steps, so it is not allowed to claim it did.
        """
        if observed_minutes_per_item <= 0:
            raise ValueError("observed_minutes_per_item must be positive")
        if not source.strip():
            raise ValueError(
                "a measured timing model must record where the measurement came from; "
                "an unattributed number is not better than a declared assumption"
            )
        base = cls()
        predicted = base.seconds_per_item(n_constructs)
        factor = (observed_minutes_per_item * 60.0) / predicted
        return replace(
            base,
            read_context_s=base.read_context_s * factor,
            span_pass_s=base.span_pass_s * factor,
            intensity_per_construct_s=base.intensity_per_construct_s * factor,
            modifier_s=base.modifier_s * factor,
            flags_and_note_s=base.flags_and_note_s * factor,
            measured=True,
            basis=(
                f"MEASURED: {observed_minutes_per_item:.2f} min/item over "
                f"{n_constructs} constructs. Source: {source}. The per-step split is "
                "the model's shape rescaled to the observation, not itself measured."
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "read_context_s": round(self.read_context_s, 3),
            "span_pass_s": round(self.span_pass_s, 3),
            "intensity_per_construct_s": round(self.intensity_per_construct_s, 3),
            "modifier_s": round(self.modifier_s, 3),
            "flags_and_note_s": round(self.flags_and_note_s, 3),
            "measured": self.measured,
            "basis": self.basis,
        }


DEFAULT_TIMING = TimingModel()

#: Above this, the batch is long enough that the fatigue failure OPEN-026
#: describes becomes the likely outcome rather than a risk. Two hours is one
#: sitting; past it a person is annotating tired, and tired annotators agree
#: with each other for the wrong reason.
FATIGUE_HOURS_PER_ANNOTATOR = 2.0


@dataclass(frozen=True)
class ConstructBurden:
    """What one construct costs, and what dropping it would return."""

    construct: str
    marginal_seconds_per_item: float
    marginal_hours_batch: float
    share_of_batch: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "construct": self.construct,
            "marginal_seconds_per_item": round(self.marginal_seconds_per_item, 3),
            "marginal_hours_over_batch": round(self.marginal_hours_batch, 3),
            "share_of_total_burden": round(self.share_of_batch, 4),
        }


@dataclass(frozen=True)
class BurdenReport:
    """Burden for one batch, per annotator, with the marginal breakdown."""

    batch: str
    n_items: int
    n_annotators: int
    constructs: tuple[str, ...]
    timing: TimingModel
    seconds_per_item: float
    per_construct: tuple[ConstructBurden, ...]

    @property
    def hours_per_annotator(self) -> float:
        return self.seconds_per_item * self.n_items / 3600.0

    @property
    def total_hours(self) -> float:
        return self.hours_per_annotator * self.n_annotators

    @property
    def exceeds_fatigue_threshold(self) -> bool:
        return self.hours_per_annotator > FATIGUE_HOURS_PER_ANNOTATOR

    @property
    def sittings(self) -> int:
        """Sittings of `FATIGUE_HOURS_PER_ANNOTATOR` the batch has to be split into."""
        import math

        return max(1, math.ceil(self.hours_per_annotator / FATIGUE_HOURS_PER_ANNOTATOR))

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": 12,
            "batch": self.batch,
            "n_items": self.n_items,
            "n_annotators": self.n_annotators,
            "n_constructs": len(self.constructs),
            "timing_model": self.timing.to_dict(),
            "estimate_is_measured": self.timing.measured,
            "seconds_per_item": round(self.seconds_per_item, 2),
            "hours_per_annotator": round(self.hours_per_annotator, 2),
            "total_person_hours": round(self.total_hours, 2),
            "fatigue_threshold_hours": FATIGUE_HOURS_PER_ANNOTATOR,
            "exceeds_fatigue_threshold": self.exceeds_fatigue_threshold,
            "recommended_sittings": self.sittings,
            "per_construct": [c.to_dict() for c in self.per_construct],
        }

    def to_markdown(self) -> str:
        provenance = (
            "**Measured.** " if self.timing.measured else "**ESTIMATE, NOT A MEASUREMENT.** "
        )
        lines = [
            f"# Annotation burden -- {self.batch}",
            "",
            provenance + self.timing.basis,
            "",
            f"{self.n_items} items x {self.n_annotators} annotator(s) x "
            f"{len(self.constructs)} constructs.",
            "",
            f"- **{self.seconds_per_item / 60:.2f} min/item**",
            f"- **{self.hours_per_annotator:.2f} h per annotator**",
            f"- **{self.total_hours:.2f} person-hours** for the batch",
            f"- recommended sittings per annotator: **{self.sittings}** "
            f"(at {FATIGUE_HOURS_PER_ANNOTATOR} h each)",
            "",
        ]
        if self.exceeds_fatigue_threshold:
            lines += [
                f"> The batch exceeds {FATIGUE_HOURS_PER_ANNOTATOR} h per annotator in one "
                "pass. Split it. OPEN-026: a rushed second half produces a worse dataset "
                "than a careful smaller one, and the damage does **not** show up in the "
                "kappa -- two tired annotators drift toward the same defaults and agree "
                "*more*.",
                "",
            ]
        lines += [
            "## Marginal cost per construct",
            "",
            "What *disappears from the batch* if the construct is dropped. The span pass "
            "and the context read are shared and do not disappear, so they are not "
            "charged here -- overstating what a drop saves is how a taxonomy gets "
            "trimmed for no gain.",
            "",
            "| construct | marginal s/item | marginal h (batch, all annotators) | share |",
            "|---|---|---|---|",
        ]
        for row in self.per_construct:
            lines.append(
                f"| {row.construct} | {row.marginal_seconds_per_item:.1f} | "
                f"{row.marginal_hours_batch:.2f} | {row.share_of_batch:.1%} |"
            )
        lines += [
            "",
            "Read this beside `reports/agreement_*.md`. A construct with poor kappa **and** "
            "high marginal cost is a drop candidate; the same poor kappa on a cheap "
            "construct is an argument for fixing the rubric, not for shrinking the "
            "taxonomy.",
        ]
        return "\n".join(lines)


def estimate_burden(
    *,
    batch: str,
    n_items: int,
    constructs: Sequence[str],
    n_annotators: int = 2,
    timing: TimingModel | None = None,
    modifier_applicable: bool = True,
) -> BurdenReport:
    """Burden for `n_items` items under `constructs`.

    `n_annotators` defaults to 2 because the plan mandates 100% double
    annotation; the person-hours number is what the project actually has to
    find, not what one person does.
    """
    if n_items < 0:
        raise ValueError("n_items must be non-negative")
    if n_annotators < 1:
        raise ValueError("n_annotators must be at least 1")
    names = tuple(constructs)
    model = timing or DEFAULT_TIMING

    per_item = model.seconds_per_item(len(names), modifier_applicable=modifier_applicable)
    total_seconds = per_item * n_items * n_annotators

    marginal = model.intensity_per_construct_s
    rows = tuple(
        ConstructBurden(
            construct=name,
            marginal_seconds_per_item=marginal,
            marginal_hours_batch=marginal * n_items * n_annotators / 3600.0,
            share_of_batch=(marginal * n_items * n_annotators / total_seconds)
            if total_seconds
            else 0.0,
        )
        for name in names
    )

    return BurdenReport(
        batch=batch,
        n_items=n_items,
        n_annotators=n_annotators,
        constructs=names,
        timing=model,
        seconds_per_item=per_item,
        per_construct=rows,
    )
