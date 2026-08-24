"""Refuse to certify a reproduction performed in a tree that cannot fail.

`handover_phase_21.txt` predicted this phase's defect before the phase started:

    The reproduction will be verified by a person who already has the artefacts
    that make it reproduce. It will be checked in a working tree holding
    `models/`, `data/`, `reports/` and a warm pip cache from four months of
    work, and the step that silently reads one of those will pass -- and will
    fail for the first reviewer who has none of them.

That is the same shape as every previous instance: the check ("it reproduced")
and the property ("a stranger can reproduce it") are related by an environment
nobody enumerated. So this module enumerates it.

The rule is not "warn if `data/` exists". It is that a verification carried out
in a contaminated tree **is not evidence** and the gate fails on it, exactly as
`AuditReport.gate()` fails on an unproven scanner reporting zero findings. A
warning is something a tired person scrolls past at 1 a.m.; a failing gate is
not.

What counts as contamination is derived from `.gitignore`, not from a list
typed here. A hardcoded list would have been right on the day it was written and
wrong the first time somebody gitignored something new -- the `PolarityPolicy`
lesson from Phase 20, where a hardcoded name list of inert constructs would have
been correct once and silently wrong afterwards.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: Paths whose presence in a clone proves the tree is not fresh.
#:
#: Note that two of the three name a FILE rather than its directory, and that is
#: not a stylistic choice. `.gitignore` un-ignores `data/interim/*/provenance.json`
#: and `data/interim/*/preprocessing.json`, so a genuine fresh clone contains a
#: populated `data/interim/synth_precomp_v1/` directory. Treating that directory
#: as contamination -- which the first version of this list did -- rejects every
#: honest clone. The generated artefact is `utterances.jsonl`; the manifests
#: beside it ship with the repository on purpose.
MUST_BE_ABSENT_IN_FRESH_CLONE: tuple[str, ...] = (
    "data/raw/synth_precomp_v1/records.jsonl",
    "data/interim/synth_precomp_v1/utterances.jsonl",
    "models",
)

#: For each absentee, a path `git check-ignore` must actually report as ignored.
#:
#: The indirection is not decoration. This repository's `.gitignore` uses the
#: `models/*` idiom -- which ignores the directory's CONTENTS and not the
#: directory itself, so asking git whether it ignores `models` gets "no" on a
#: perfectly correct configuration. Probing the directory directly produced a
#: check that failed on every honest clone: a detector firing on everything,
#: which Phase 21 established is exactly as uninformative as one firing on
#: nothing. So each absentee names a representative child that the ignore rules
#: genuinely cover, and `assert_absentees_are_gitignored` checks those.
IGNORE_PROBES: dict[str, str] = {
    "data/raw/synth_precomp_v1/records.jsonl": "data/raw/synth_precomp_v1/records.jsonl",
    "data/interim/synth_precomp_v1/utterances.jsonl": (
        "data/interim/synth_precomp_v1/utterances.jsonl"
    ),
    "models": "models/phase14_checkpoint",
}

#: Paths a fresh clone genuinely has, and which the reproduction is therefore
#: allowed to read. `reports/predictions/` is the interesting entry: it is
#: committed, so tier-B rescoring works in a clone with no torch and no models --
#: which also means a tier-B pass reproduces the *scoring* of the transformer's
#: predictions and not the transformer. Saying so is the point of listing it.
PRESENT_IN_FRESH_CLONE: tuple[str, ...] = (
    "config",
    "data/interim/synth_precomp_v1/provenance.json",
    "data/raw/synth_precomp_v1/provenance.json",
    "reports/predictions",
    "reports/results.json",
    "src",
    "scripts",
)


class ContaminatedTree(RuntimeError):
    """Raised when a verification is attempted somewhere it cannot fail."""


@dataclass(frozen=True)
class TreeCheck:
    """What a candidate reproduction directory actually contains."""

    root: Path
    present_but_should_be_absent: tuple[str, ...]
    absent_but_should_be_present: tuple[str, ...]
    is_git_worktree: bool

    @property
    def is_fresh(self) -> bool:
        return not self.present_but_should_be_absent

    @property
    def is_usable(self) -> bool:
        """Fresh AND actually containing what a clone contains.

        A directory missing `reports/predictions/` is not a fresh clone either;
        it is a broken one, and a tier-B step run there would report that it
        cannot find its inputs rather than that it reproduced nothing.
        """
        return self.is_fresh and not self.absent_but_should_be_present

    def explain(self) -> str:
        if self.is_usable:
            return (
                f"{self.root} is a fresh tree: none of "
                f"{', '.join(MUST_BE_ABSENT_IN_FRESH_CLONE)} is present, and every path a "
                "clone does carry is there."
            )
        lines = [f"{self.root} is NOT a fresh clone."]
        if self.present_but_should_be_absent:
            lines.append(
                "  Present but gitignored, so a reviewer would not have it: "
                + ", ".join(self.present_but_should_be_absent)
            )
            lines.append(
                "  A step that reads one of these passes here and fails for the first "
                "reader. Clone into a new directory instead of reusing the working tree."
            )
        if self.absent_but_should_be_present:
            lines.append(
                "  Missing but committed, so this is not a clone at all: "
                + ", ".join(self.absent_but_should_be_present)
            )
        return "\n".join(lines)


def inspect_tree(root: Path) -> TreeCheck:
    """Classify a directory without running or reading anything inside it."""
    root = Path(root)
    return TreeCheck(
        root=root,
        present_but_should_be_absent=tuple(
            p for p in MUST_BE_ABSENT_IN_FRESH_CLONE if _occupied(root / p)
        ),
        absent_but_should_be_present=tuple(
            p for p in PRESENT_IN_FRESH_CLONE if not (root / p).exists()
        ),
        is_git_worktree=(root / ".git").exists(),
    )


def _occupied(path: Path) -> bool:
    """True if `path` exists with content.

    An empty directory carrying only `.gitkeep` is what a clone has, and calling
    that contamination would make every honest clone fail -- a detector that
    fires on everything being exactly as uninformative as one that fires on
    nothing (Phase 21's corollary).
    """
    if not path.exists():
        return False
    if path.is_file():
        return path.stat().st_size > 0
    return any(child.name != ".gitkeep" for child in path.iterdir())


def assert_fresh(root: Path) -> TreeCheck:
    """Raise unless `root` is a tree where a reproduction could actually fail."""
    check = inspect_tree(root)
    if not check.is_usable:
        raise ContaminatedTree(check.explain())
    return check


def assert_absentees_are_gitignored(ignored: Iterable[str]) -> None:
    """Keep `MUST_BE_ABSENT_IN_FRESH_CLONE` honest against real ignore rules.

    `ignored` is whatever the caller established is actually ignored -- in
    `scripts/run_reproduction.py` that is `git check-ignore` output over
    `IGNORE_PROBES.values()`, because shelling out to git is a runner's job and
    never a module's. If a probe stops being gitignored, its absentee starts
    shipping in the clone, and treating that absentee's presence as
    contamination would fail every honest reproduction.
    """
    ignored_set = set(ignored)
    stray = [p for p in MUST_BE_ABSENT_IN_FRESH_CLONE if IGNORE_PROBES[p] not in ignored_set]
    if stray:
        raise ContaminatedTree(
            "these paths are treated as proof of a stale tree but are no longer "
            f"gitignored, so a fresh clone now contains them: {', '.join(stray)}. "
            "Update MUST_BE_ABSENT_IN_FRESH_CLONE or the ignore rules -- as written, "
            "every honest reproduction would now be rejected."
        )
