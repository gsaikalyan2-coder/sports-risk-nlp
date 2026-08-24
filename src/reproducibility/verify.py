"""Compare a reproduction run against the declared plan, and gate on it.

Five refusals live here, and each one exists because a softer version of it has
already failed somewhere in this project:

1. **A verification in a contaminated tree fails the gate**, rather than warning.
   `AuditReport.gate()` fails an unproven scanner reporting zero findings for the
   same reason: a result produced where it could not have failed is not evidence.
2. **A verification whose declaration hash does not match the plan fails.** This
   is what stops a tolerance being widened after the delta is known. The plan is
   hashed at declaration time and the hash travels with the run.
3. **An artefact the report never mentions fails the gate**, even if every
   artefact it does mention reproduced. A one-command path that quietly skips
   the gold-derived figures is claiming more than it delivers; here it cannot
   stay quiet, because silence about a declared artefact is a failure condition.

4. **A pass that reproduced nothing fails.** Rules 1-3 were all satisfied by a
   run with no tiers selected: every artefact honestly SKIPPED, every box
   ticked, gate green, nothing reproduced. That is Phase 18's corollary wearing
   a new costume -- a gate that only checks a result exists. It was found by
   rendering the report and reading it, not by any test here, which is Phase
   20's lesson arriving on schedule.
5. **An artefact inside an attempted tier may not be skipped.** A tier is
   exercised or not selected; skipping within one lets an omission ride along
   with a green result.

Rule 3 is the one that took the longest to get right. The obvious design reports
what ran; this one reports the declared set and forces every member of it to
carry a verdict, so `SKIPPED` and `BLOCKED` are things the reader sees rather
than things the reader has to notice are missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.dashboard.view import assert_no_forbidden_language
from src.evaluation.harness import PROVISIONAL_STAMP
from src.reproducibility.environment import TreeCheck
from src.reproducibility.plan import Artefact, Match, ReproductionPlan, Tier


class Outcome(Enum):
    """What happened to one declared artefact on one run.

    `SKIPPED` and `BLOCKED` are distinct for the reason `REFUSED` and
    `UNMEASURABLE` are distinct in `src/evaluation/ablations.py`. Skipped means
    the reader could have run it and this run did not (tier C, ten CPU-hours).
    Blocked means nobody can run it, including the author (tier D, `data/gold/`
    is empty). Collapsing them would let a ten-hour omission hide behind a
    permanent one.
    """

    REPRODUCED = "reproduced"
    DEVIATED = "deviated"
    SKIPPED = "skipped -- runnable, not run on this pass"
    BLOCKED = "blocked -- not runnable by anyone"


@dataclass(frozen=True)
class ArtefactResult:
    """One artefact's verdict, with the numbers that produced it."""

    artefact: Artefact
    outcome: Outcome
    expected: float | str | None = None
    produced: float | str | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.outcome in (Outcome.REPRODUCED, Outcome.DEVIATED):
            if self.expected is None or self.produced is None:
                raise ValueError(
                    f"{self.artefact.name!r} claims {self.outcome.value} but carries no "
                    "pair of values. A verdict with no comparison behind it is the "
                    "OPEN-034 shape: a gate certifying something its evidence never said."
                )
        if self.outcome is Outcome.BLOCKED and self.artefact.match is not Match.NOT_REPRODUCIBLE:
            raise ValueError(
                f"{self.artefact.name!r} is reported BLOCKED but the plan declares it "
                f"{self.artefact.match.value}. One of the two is wrong, and a report is "
                "not the place to settle it."
            )
        assert_no_forbidden_language(f"{self.note}")

    @property
    def delta(self) -> float | None:
        if isinstance(self.expected, int | float) and isinstance(self.produced, int | float):
            return float(self.produced) - float(self.expected)
        return None


@dataclass(frozen=True)
class StepResult:
    """What one step of the plan did on this run."""

    step_id: str
    ran: bool
    artefacts: tuple[ArtefactResult, ...] = ()
    note: str = ""
    #: Paths the runner observed this step read, when it could observe them.
    observed_reads: tuple[str, ...] = ()
    #: Non-zero exit from the step's command. Tracked separately from artefact
    #: verdicts because a step that produces no artefacts -- `env` installs
    #: dependencies and produces nothing measurable -- would otherwise be able to
    #: fail silently. It did, on the first real run.
    exit_code: int = 0

    def __post_init__(self) -> None:
        assert_no_forbidden_language(self.note)


@dataclass
class VerificationReport:
    """Every declared artefact's verdict, plus the gate over all of them."""

    plan: ReproductionPlan
    tree: TreeCheck
    #: `plan.declaration_sha256()` as recorded when the tolerances were declared.
    declared_sha256: str
    steps: list[StepResult] = field(default_factory=list)
    provenance: str = PROVISIONAL_STAMP
    #: Tiers this pass set out to run. Empty means "nothing was attempted", and
    #: the gate refuses to pass on that -- see `gate()`.
    attempted_tiers: tuple[Tier, ...] = ()

    def add(self, result: StepResult) -> StepResult:
        self.steps.append(result)
        return result

    @property
    def results(self) -> list[ArtefactResult]:
        return [a for s in self.steps for a in s.artefacts]

    @property
    def unreported(self) -> tuple[str, ...]:
        """Declared artefacts carrying no verdict at all."""
        reported = {a.artefact.name for a in self.results}
        return tuple(a.name for a in self.plan.artefacts if a.name not in reported)

    @property
    def undeclared_reads(self) -> tuple[str, ...]:
        """Paths a step was observed reading that the plan never authorised."""
        out: list[str] = []
        for step_result in self.steps:
            declared = set(self.plan.step(step_result.step_id).reads)
            for path in step_result.observed_reads:
                if not any(path == d or path.startswith(f"{d}/") for d in declared):
                    out.append(f"{step_result.step_id}:{path}")
        return tuple(sorted(set(out)))

    def gate(self) -> tuple[bool, list[str]]:
        """Returns (passed, reasons-it-failed). See the module docstring."""
        reasons: list[str] = []

        if not self.tree.is_usable:
            reasons.append(
                "the verification did not happen in a fresh clone, so it is not "
                "evidence that a stranger can reproduce anything:\n" + self.tree.explain()
            )

        current = self.plan.declaration_sha256()
        if current != self.declared_sha256:
            reasons.append(
                "the plan has changed since its tolerances were declared "
                f"(declared {self.declared_sha256[:12]}, current {current[:12]}). A "
                "tolerance edited after a run is fitted to that run, not a gate on it. "
                "Re-declare, then re-verify."
            )

        for result in self.results:
            if result.outcome is Outcome.DEVIATED:
                reasons.append(
                    f"{result.artefact.name}: expected {result.expected}, got "
                    f"{result.produced} -- outside the declared "
                    f"{result.artefact.match.value}"
                    + (
                        f" of {result.artefact.tolerance} {result.artefact.units}"
                        if result.artefact.tolerance is not None
                        else ""
                    )
                )

        for name in self.unreported:
            reasons.append(
                f"{name} is declared in the plan and carries no verdict. Silence about "
                "a declared artefact is how a reproduction path claims more than it "
                "delivers -- report it as skipped or blocked, with the reason."
            )

        # A pass must be evidence OF something. Without this, selecting no tiers
        # produces a report in which every artefact is honestly marked SKIPPED,
        # every other check is satisfied, and the gate goes green having
        # reproduced nothing -- Phase 18's corollary ("a gate that only checks a
        # result exists is worse than no gate") in a new costume. Found by
        # rendering the report and reading it, which is Phase 20's lesson; no
        # test in this file caught it.
        runnable = [t for t in self.attempted_tiers if t is not Tier.D_BLOCKED]
        if not runnable:
            reasons.append(
                "no runnable tier was attempted, so this pass reproduced nothing. A "
                "verification in which every artefact is skipped is a correctly-filled-in "
                "form, not evidence. Select at least one of tiers A, B or C."
            )
        else:
            expected_names = {
                a.name for t in runnable for s in self.plan.by_tier(t) for a in s.produces
            }
            by_name = {r.artefact.name: r for r in self.results}
            for name in sorted(expected_names):
                result = by_name.get(name)
                if result is not None and result.outcome is Outcome.SKIPPED:
                    reasons.append(
                        f"{name} belongs to an attempted tier but is reported skipped. A "
                        "tier is either exercised or not selected; skipping inside one "
                        "lets an omission ride along with a green result."
                    )

        for step_result in self.steps:
            if step_result.exit_code != 0:
                reasons.append(
                    f"step {step_result.step_id} exited {step_result.exit_code}. A step "
                    "that produces no artefact still has to succeed; without this the "
                    "environment setup can fail and the gate passes on the strength of "
                    "the later steps, which is what happened on this phase's first real run."
                )

        for entry in self.undeclared_reads:
            reasons.append(
                f"hidden input: {entry} was read but no step declares it. This is the "
                "defect the phase exists to catch -- the corpus has to come from "
                "somewhere, and a path nobody declared is a path a reviewer will not have."
            )

        return (not reasons, reasons)

    # -- reporting ---------------------------------------------------------

    def coverage_lines(self) -> list[str]:
        """The 'what this does NOT reproduce' section, assembled from verdicts."""
        lines: list[str] = []
        for result in self.results:
            if result.outcome in (Outcome.SKIPPED, Outcome.BLOCKED):
                why = result.artefact.why_not or result.note
                lines.append(f"- **{result.artefact.name}** -- {result.outcome.value}. {why}")
        return lines

    def as_dict(self) -> dict[str, object]:
        passed, reasons = self.gate()
        return {
            "phase": 22,
            "gate": "PASS" if passed else "FAIL",
            "reasons": reasons,
            "declared_sha256": self.declared_sha256,
            "plan_sha256": self.plan.declaration_sha256(),
            "tree": {
                "root": str(self.tree.root),
                "is_fresh": self.tree.is_fresh,
                "is_usable": self.tree.is_usable,
                "contaminants": list(self.tree.present_but_should_be_absent),
                "missing": list(self.tree.absent_but_should_be_present),
            },
            "provenance": self.provenance,
            "attempted_tiers": [t.name for t in self.attempted_tiers],
            "is_accuracy": False,
            "artefacts": [
                {
                    "name": r.artefact.name,
                    "locator": r.artefact.locator,
                    "declared_match": r.artefact.match.value,
                    "tolerance": r.artefact.tolerance,
                    "units": r.artefact.units,
                    "outcome": r.outcome.value,
                    "expected": r.expected,
                    "produced": r.produced,
                    "delta": r.delta,
                    "note": r.note,
                }
                for r in self.results
            ],
            "unreported": list(self.unreported),
            "undeclared_reads": list(self.undeclared_reads),
        }


def render_markdown(report: VerificationReport, *, title: str = "Reproduction check") -> str:
    """Render the report. The coverage section is not optional."""
    passed, reasons = report.gate()
    lines = [f"## {title}", "", f"**Gate:** {'PASS' if passed else 'FAIL'}", ""]
    lines.append(f"> {report.provenance}")
    lines.append("")
    lines.append(f"Verified in `{report.tree.root}` -- {report.tree.explain()}")
    lines.append("")
    attempted = ", ".join(t.name for t in report.attempted_tiers) or "none"
    lines.append(f"Tiers attempted on this pass: **{attempted}**.")
    lines.append("")
    if reasons:
        lines.append("### Why it failed")
        lines.append("")
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    for tier in Tier:
        steps = report.plan.by_tier(tier)
        if not steps:
            continue
        lines.append(f"### Tier {tier.value}")
        lines.append("")
        for step in steps:
            ran = next((s for s in report.steps if s.step_id == step.id), None)
            lines.append(f"**`{step.id}`** -- {step.purpose}")
            lines.append("")
            lines.append(f"```\n{step.command}\n```")
            lines.append("")
            lines.append(f"- **Reads:** {', '.join(step.reads) or 'nothing in the repository'}")
            lines.append(f"- **Cannot reproduce:** {step.cannot_reproduce}")
            lines.append(f"- **Ran on this pass:** {'yes' if ran and ran.ran else 'no'}")
            if not step.runnable:
                lines.append(
                    "- **Not runnable by the checker:** this command is the reader's own "
                    "setup and cannot be executed from inside the tree it produces."
                )
            if ran is not None and ran.exit_code != 0:
                lines.append(f"- **Exit code:** {ran.exit_code}")
            lines.append("")
        rows = [r for r in report.results if r.artefact.name in _tier_artefacts(report, tier)]
        if rows:
            lines.append("| artefact | declared | outcome | expected | produced | delta |")
            lines.append("|---|---|---|---|---|---|")
            for r in rows:
                declared = r.artefact.match.value + (
                    f" (+/-{r.artefact.tolerance} {r.artefact.units})"
                    if r.artefact.tolerance is not None
                    else ""
                )
                delta = "--" if r.delta is None else f"{r.delta:+.4f}"
                lines.append(
                    f"| {r.artefact.name} | {declared} | {r.outcome.value} | "
                    f"{r.expected if r.expected is not None else '--'} | "
                    f"{r.produced if r.produced is not None else '--'} | {delta} |"
                )
            lines.append("")

    coverage = report.coverage_lines()
    lines.append("### What this run does NOT reproduce")
    lines.append("")
    lines.extend(coverage or ["- Nothing: every declared artefact was produced on this pass."])
    lines.append("")

    rendered = "\n".join(lines)
    assert_no_forbidden_language(rendered)
    return rendered


def _tier_artefacts(report: VerificationReport, tier: Tier) -> set[str]:
    return {a.name for s in report.plan.by_tier(tier) for a in s.produces}
