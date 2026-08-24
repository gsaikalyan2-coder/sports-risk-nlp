"""Phase 22 -- the declared reproduction path, as data a test can iterate over.

The one idea worth carrying out of this module: **an artefact and the strength of
the claim made about reproducing it are the SAME object.** You cannot declare an
artefact without saying whether it comes back byte-identical, within a stated
numeric tolerance, or not at all -- and each of those three answers demands a
different field, checked at construction. There is no way to write "it
reproduces" and leave the strength unstated.

Why that matters here specifically
----------------------------------
`PROJECT_PLAN.md` Phase 22's gate is "fresh clone reproduces headline numbers
within tolerance". Every word in it is load-bearing and three of them were
unspecified:

* **"fresh clone"** -- the reproduction will be checked by the person who has
  four months of artefacts on disk. `data/` and `models/` are gitignored, so a
  genuine clone has neither, and a step that silently reads one of them passes
  for the author and fails for the first reviewer. `environment.py` refuses that
  mechanically rather than trusting anyone to remember.
* **"within tolerance"** -- a tolerance is a claim (Phase 19's corollary), and a
  tolerance chosen after seeing the delta is not a gate. So the tolerances are
  declared here, in source, hashed, and the hash is embedded in any verification
  that uses them. Editing a tolerance after a run invalidates that run.
* **"headline numbers"** -- some of them cannot be reproduced at all. Anything
  gold-derived is unreproducible by construction (OPEN-025, `data/gold/` is
  empty), and a one-command path that quietly skips them claims more than it
  delivers. `cannot_reproduce` is mandatory on every step for the same reason
  `ScannerResult.does_not_cover` is mandatory in `src/security/audit.py`.

The recurring defect this project has now found six times is a check and the
property it protects being related by *assumption* rather than by construction.
Two teeth here are aimed straight at it:

1. A step whose command installs a lock file carrying a PEP 440 *local version*
   (`torch==2.13.0+cpu`, which exists on no default index) must carry
   `--extra-index-url` in the command string itself. A reproduction command that
   only works because the reader remembers a flag is not a one-command path, and
   `MissingExtraIndex` makes writing one impossible.
2. A step declares the repository paths it is allowed to read. The runner
   verifies the clone against that declaration, so "what did it actually read"
   is answered by the plan rather than discovered by a reviewer.

Nothing in this module runs anything, touches the network, or writes to disk.
That is `scripts/run_reproduction.py`'s job, exactly as `src/security/` leaves
git, network and disk to `scripts/run_security_audit.py`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from src.dashboard.view import assert_no_forbidden_language

#: Lock files that pin at least one PEP 440 local version. Installing any of
#: these without an extra index fails, so a command naming one must carry the
#: flag. Kept as a tuple rather than inferred from disk: this module never reads
#: the filesystem, and a plan must be checkable in a tree that has no locks yet.
LOCAL_VERSION_LOCKS: tuple[str, ...] = (
    "requirements.lock.txt",
    "requirements-ml.lock.txt",
)

#: The index that serves the `+cpu` wheels. Quoted in full so a reader copying a
#: command out of a rendered report gets a working one.
CPU_WHEEL_INDEX = "https://download.pytorch.org/whl/cpu"


class MissingExtraIndex(ValueError):
    """Raised when a pip command would fail for a reader but not for the author."""


class Tier(Enum):
    """How expensive a step is, which decides whether a reviewer will run it.

    The tiers are ordered by cost, and the ordering is the point: a reader
    deciding how much of the artefact to reproduce needs to know that tiers A
    and B together take minutes and cover every headline number, while tier C
    takes roughly ten CPU-hours and covers one of them again from further back.
    """

    A_SEEDED = "A -- seeded, minutes, base dependencies only"
    B_RESCORE = "B -- rescoring a committed cache, seconds, base dependencies only"
    C_RETRAIN = "C -- retraining, ~10 CPU-hours, full ML stack"
    D_BLOCKED = "D -- cannot be run by anyone, including the author"


class Match(Enum):
    """The strength of the reproduction claim for one artefact.

    `BYTE_IDENTICAL` and `WITHIN_TOLERANCE` are deliberately distinct, for the
    same reason `AblationStatus.REFUSED` and `UNMEASURABLE` are distinct in
    `src/evaluation/ablations.py`: collapsing them into "it reproduces" throws
    away the part a reviewer cares about. Phase 13 asserts the classical
    baselines at full float precision, not `approx`; saying "within tolerance"
    about those would understate what this repository can actually promise.
    """

    BYTE_IDENTICAL = "byte-identical"
    WITHIN_TOLERANCE = "within tolerance"
    NOT_REPRODUCIBLE = "not reproducible"


@dataclass(frozen=True)
class Artefact:
    """One output, and exactly how strong a claim is made about reproducing it.

    The three-way invariant below is the whole reason this is a class and not a
    dict. A tolerance on a byte-identical artefact is a contradiction that would
    otherwise sit in a table looking like rigour.
    """

    name: str
    #: Repo-relative path, or a dotted key inside `reports/results.json`.
    locator: str
    match: Match
    #: Absolute tolerance. Required by `WITHIN_TOLERANCE`, forbidden otherwise.
    tolerance: float | None = None
    #: Required by `NOT_REPRODUCIBLE`. The sentence a reader gets instead of a number.
    why_not: str = ""
    #: What the number means, for artefacts that are numbers.
    units: str = ""

    def __post_init__(self) -> None:
        if self.match is Match.WITHIN_TOLERANCE:
            if self.tolerance is None or self.tolerance <= 0:
                raise ValueError(
                    f"artefact {self.name!r} claims WITHIN_TOLERANCE with no positive "
                    "tolerance. 'Within tolerance' without a number is not a gate -- it "
                    "is a tolerance chosen later, once the delta is known."
                )
            if not self.units.strip():
                raise ValueError(
                    f"artefact {self.name!r} has a tolerance of {self.tolerance} in no "
                    "stated units, so nobody can tell whether it is tight or absurd"
                )
        elif self.tolerance is not None:
            raise ValueError(
                f"artefact {self.name!r} is {self.match.value} but carries a tolerance. "
                "A tolerance on a byte-identical artefact understates what this "
                "repository can promise; on an unreproducible one it is fiction."
            )
        if self.match is Match.NOT_REPRODUCIBLE and len(self.why_not.strip()) < 20:
            raise ValueError(
                f"artefact {self.name!r} is unreproducible with no explanation. An "
                "absent number with no reason reads as an oversight; with a reason it "
                "is a result (see `AblationStatus.UNMEASURABLE`)."
            )
        assert_no_forbidden_language(f"{self.name} {self.why_not} {self.units}")

    def agrees(self, produced: float, expected: float) -> bool:
        """Whether a produced value satisfies this artefact's declared strength."""
        if self.match is Match.NOT_REPRODUCIBLE:
            raise ValueError(
                f"{self.name!r} is declared unreproducible; comparing a value for it "
                "asserts the opposite of what the plan says"
            )
        if self.match is Match.BYTE_IDENTICAL:
            return produced == expected
        assert self.tolerance is not None  # guaranteed by __post_init__
        return abs(produced - expected) <= self.tolerance


@dataclass(frozen=True)
class Step:
    """One command in the reproduction path, with its blast radius written down.

    `cannot_reproduce` is mandatory and validated, copying
    `ScannerResult.does_not_cover`. A step that produces artefacts and says
    nothing about what it leaves untouched invites the reader to over-read a
    green result, which is the Phase 18 defect.
    """

    id: str
    tier: Tier
    command: str
    purpose: str
    cannot_reproduce: str
    #: Repo-relative paths this step is permitted to read. Anything else it reads
    #: is a hidden input, which is the failure mode this whole phase is about.
    reads: tuple[str, ...] = ()
    #: False for a step the runner cannot execute from inside the tree it is
    #: verifying. `env` is the case: you cannot `git clone` the repository from
    #: within the clone, so that command is the reader's setup and the runner
    #: must not pretend to have run it. Marking it explicitly beats letting it
    #: fail and be ignored -- which is precisely what happened on the first real
    #: run, where `env` exited non-zero and the gate passed anyway.
    runnable: bool = True
    produces: tuple[Artefact, ...] = ()

    def __post_init__(self) -> None:
        if len(self.cannot_reproduce.strip()) < 20:
            raise ValueError(
                f"Step({self.id!r}).cannot_reproduce is empty or perfunctory. Every "
                "coverage statement in this repository exists because a clean result "
                "with no stated scope is a claim nobody checked. Write the sentence "
                "that stops a reader over-reading this step."
            )
        if len(self.purpose.strip()) < 20:
            raise ValueError(f"Step({self.id!r}).purpose is empty or perfunctory")
        self._assert_extra_index()
        assert_no_forbidden_language(f"{self.purpose} {self.cannot_reproduce} {self.command}")

    def _assert_extra_index(self) -> None:
        """A pip command that only works for someone who remembers a flag is a bug.

        `requirements.lock.txt` pins `torch==2.13.0+cpu`. That local version
        exists on the PyTorch CPU wheel index and on no default index, so
        `pip install -r requirements.lock.txt` fails outright without
        `--extra-index-url`. Documenting the flag in a comment is what the
        repository already did, and it is exactly the arrangement that produces a
        one-command path which is not one.
        """
        if "pip install" not in self.command:
            return
        for lock in LOCAL_VERSION_LOCKS:
            if lock in self.command and "--extra-index-url" not in self.command:
                raise MissingExtraIndex(
                    f"Step({self.id!r}) installs {lock}, which pins at least one PEP 440 "
                    "local version, but the command carries no --extra-index-url. That "
                    f"command fails for every reader. Append: --extra-index-url {CPU_WHEEL_INDEX}"
                )

    @property
    def artefact_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.produces)


@dataclass(frozen=True)
class ReproductionPlan:
    """The declared path, hashable so a later verification cannot outrun it."""

    steps: tuple[Step, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate step id {step.id!r}")
            seen.add(step.id)
        names: set[str] = set()
        for artefact in self.artefacts:
            if artefact.name in names:
                raise ValueError(
                    f"artefact {artefact.name!r} is produced by two steps; a reader "
                    "cannot tell which run the reported value came from"
                )
            names.add(artefact.name)

    @property
    def artefacts(self) -> tuple[Artefact, ...]:
        return tuple(a for s in self.steps for a in s.produces)

    def step(self, step_id: str) -> Step:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)

    def artefact(self, name: str) -> Artefact:
        for artefact in self.artefacts:
            if artefact.name == name:
                return artefact
        raise KeyError(name)

    def by_tier(self, tier: Tier) -> tuple[Step, ...]:
        return tuple(s for s in self.steps if s.tier is tier)

    @property
    def readable_paths(self) -> tuple[str, ...]:
        """Every path any step declares it may read, deduplicated and sorted."""
        return tuple(sorted({p for s in self.steps for p in s.reads}))

    def as_dict(self) -> dict[str, object]:
        return {
            "steps": [
                {
                    "id": s.id,
                    "tier": s.tier.value,
                    "command": s.command,
                    "purpose": s.purpose,
                    "cannot_reproduce": s.cannot_reproduce,
                    "reads": list(s.reads),
                    "runnable": s.runnable,
                    "produces": [
                        {
                            "name": a.name,
                            "locator": a.locator,
                            "match": a.match.value,
                            "tolerance": a.tolerance,
                            "units": a.units,
                            "why_not": a.why_not,
                        }
                        for a in s.produces
                    ],
                }
                for s in self.steps
            ]
        }

    def declaration_sha256(self) -> str:
        """Fingerprint of the declared plan, tolerances included.

        `scripts/run_reproduction.py` embeds this in every verification it
        writes. Change a tolerance afterwards and the stored verification no
        longer matches the plan that produced it, so the gate fails instead of
        silently blessing a number the tolerance was fitted to. This is the
        mechanical form of "a tolerance picked after seeing the delta is not a
        gate" -- the ordering is enforced, not requested.
        """
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
