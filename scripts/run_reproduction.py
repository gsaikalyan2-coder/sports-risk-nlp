"""Phase 22 gate -- declare the reproduction path, then verify it in a fresh clone.

    python scripts/run_reproduction.py --declare
    python scripts/run_reproduction.py --verify --root /path/to/fresh/clone --tiers A,B

Two subcommands, and the order between them is the gate:

* `--declare` freezes the tolerances in `reports/reproduction.json` together
  with the SHA-256 of the plan that declared them. It runs nothing and measures
  nothing, which is the point -- a tolerance must exist before there is a delta
  for it to be fitted to.
* `--verify` runs the plan's steps in a directory it first proves is a fresh
  clone, compares what came out against the frozen declaration, and fails if the
  plan has changed in between.

This script owns the three things `src/reproducibility/` must never do: it
shells out (git, pip, the step commands), it touches the filesystem, and it
writes reports. Same split as `scripts/run_security_audit.py`, and the same
reason -- it keeps the package's tests runnable in about a second with no ML
stack installed.

Exit codes: 0 gate passed, 1 gate failed, 2 the run could not be attempted
(contaminated tree, missing declaration). 2 is deliberately not 1: "I refuse to
measure here" and "I measured and it is wrong" are different messages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.reproducibility import (  # noqa: E402
    FILE_DIGESTS,
    HEADLINE,
    PLAN,
    RETRAIN_TOLERANCE_MACRO_F1,
    ArtefactResult,
    ContaminatedTree,
    Match,
    Outcome,
    StepResult,
    Tier,
    VerificationReport,
    assert_absentees_are_gitignored,
    inspect_tree,
    render_markdown,
)
from src.reproducibility.environment import IGNORE_PROBES  # noqa: E402

RECORD = REPO_ROOT / "reports" / "reproduction.json"
RENDERED = REPO_ROOT / "reports" / "reproduction.md"

TIER_BY_LETTER = {
    "A": Tier.A_SEEDED,
    "B": Tier.B_RESCORE,
    "C": Tier.C_RETRAIN,
    "D": Tier.D_BLOCKED,
}


def _rule(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


# ---------------------------------------------------------------------------
# --declare
# ---------------------------------------------------------------------------


def declare(args: argparse.Namespace) -> int:
    """Freeze the tolerances and the plan hash. Runs nothing."""
    _rule("Declaring the reproduction plan")
    payload: dict[str, Any] = {}
    if RECORD.exists():
        payload = json.loads(RECORD.read_text(encoding="utf-8"))

    previous = (payload.get("declaration") or {}).get("declared_sha256")
    current = PLAN.declaration_sha256()
    if previous and previous != current and not args.redeclare:
        print("FAIL: a declaration already exists and the plan has changed since.")
        print(f"      declared {previous[:12]}, plan is now {current[:12]}.")
        print("      Re-declaring after a verification invalidates that verification, so")
        print("      this needs --redeclare and a note in the handover saying why.")
        return 2

    payload["declaration"] = {
        "declared_on": args.declared_on or date.today().isoformat(),
        "declared_sha256": current,
        "plan_sha256": current,
        "retrain_tolerance_macro_f1": RETRAIN_TOLERANCE_MACRO_F1,
        "byte_identical_artefacts": [
            a.name for a in PLAN.artefacts if a.match is Match.BYTE_IDENTICAL
        ],
        "within_tolerance_artefacts": {
            a.name: {"tolerance": a.tolerance, "units": a.units}
            for a in PLAN.artefacts
            if a.match is Match.WITHIN_TOLERANCE
        },
        "not_reproducible_artefacts": {
            a.name: a.why_not for a in PLAN.artefacts if a.match is Match.NOT_REPRODUCIBLE
        },
        "headline": HEADLINE,
        "plan": PLAN.as_dict(),
    }
    # Any verification recorded against an older plan is stale by definition.
    if previous and previous != current:
        payload.pop("verification", None)

    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  plan sha256   : {current}")
    print(f"  retrain tol   : +/-{RETRAIN_TOLERANCE_MACRO_F1} absolute macro-F1")
    print(f"  byte-identical: {len(payload['declaration']['byte_identical_artefacts'])} artefacts")
    print(
        f"  unreproducible: {len(payload['declaration']['not_reproducible_artefacts'])} artefacts"
    )
    print(f"  written       : {RECORD.relative_to(REPO_ROOT)}")
    return 0


# ---------------------------------------------------------------------------
# --verify
# ---------------------------------------------------------------------------


def _read_locator(root: Path, locator: str) -> Any:
    """Resolve `path` or `path:dotted.key` inside a reproduction tree."""
    if ":" in locator and not locator[1:2] == ":":  # not a Windows drive letter
        rel, dotted = locator.split(":", 1)
        target = root / rel
        if not target.exists():
            return None
        node: Any = json.loads(target.read_text(encoding="utf-8"))
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node
    target = root / locator
    return target.read_bytes() if target.exists() else None


def _expected(name: str) -> Any:
    return HEADLINE.get(name)


def _run(command: str, cwd: Path, *, dry: bool) -> tuple[int, str]:
    if dry:
        return (0, "(dry run -- command not executed)")
    proc = subprocess.run(  # noqa: S602 -- the commands are this repo's own, declared in PLAN
        command, cwd=cwd, shell=True, capture_output=True, text=True
    )
    return (proc.returncode, (proc.stdout + proc.stderr)[-4000:])


def verify(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    _rule(f"Verifying the reproduction in {root}")

    if not RECORD.exists():
        print(f"FAIL: no declaration at {RECORD.relative_to(REPO_ROOT)}.")
        print("      Run --declare first. A tolerance established during the run it")
        print("      judges is not a tolerance.")
        return 2
    payload = json.loads(RECORD.read_text(encoding="utf-8"))
    declaration = payload.get("declaration") or {}
    declared_sha = declaration.get("declared_sha256", "")

    # The absentee list must still describe reality. If one of these paths stops
    # being gitignored it starts shipping in the clone, and treating its presence
    # as contamination would reject every honest reproduction.
    try:
        ignored = _gitignored(root, tuple(IGNORE_PROBES.values()))
        assert_absentees_are_gitignored(ignored)
    except (ContaminatedTree, GitUnavailable) as exc:
        print(f"FAIL: {exc}")
        return 2

    tree = inspect_tree(root)
    print(tree.explain())
    if not tree.is_usable and not args.force:
        print()
        print("Refusing to measure. A reproduction verified in a tree that already holds")
        print("the artefacts is not evidence that a stranger can reproduce anything --")
        print("this is the defect handover_phase_21.txt predicted for this phase.")
        return 2

    wanted = {TIER_BY_LETTER[letter.strip().upper()] for letter in args.tiers.split(",")}
    report = VerificationReport(
        plan=PLAN,
        tree=tree,
        declared_sha256=declared_sha,
        attempted_tiers=tuple(sorted(wanted, key=lambda t: t.name)),
    )

    for step in PLAN.steps:
        if step.tier is Tier.D_BLOCKED:
            report.add(
                StepResult(
                    step_id=step.id,
                    ran=False,
                    artefacts=tuple(
                        ArtefactResult(artefact=a, outcome=Outcome.BLOCKED, note=a.why_not)
                        for a in step.produces
                    ),
                    note=step.cannot_reproduce,
                )
            )
            continue

        if not step.runnable:
            report.add(
                StepResult(
                    step_id=step.id,
                    ran=False,
                    note=(
                        "not executable from inside the tree being verified; the reader "
                        "performs it by hand before the checker exists"
                    ),
                )
            )
            continue

        if step.tier not in wanted:
            report.add(
                StepResult(
                    step_id=step.id,
                    ran=False,
                    artefacts=tuple(
                        ArtefactResult(
                            artefact=a,
                            outcome=Outcome.SKIPPED,
                            note=f"tier {step.tier.value}; not selected on this pass",
                        )
                        for a in step.produces
                    ),
                )
            )
            continue

        _rule(f"step {step.id}")
        print(f"  $ {step.command}")
        if args.dry_run:
            # A dry run previews the path; it does not walk it. Its artefacts are
            # SKIPPED, which makes the gate fail rule 5 for any attempted tier --
            # deliberately. "I printed the commands" must not read as "it
            # reproduced".
            report.add(
                StepResult(
                    step_id=step.id,
                    ran=False,
                    artefacts=tuple(
                        ArtefactResult(
                            artefact=a,
                            outcome=Outcome.SKIPPED,
                            note="dry run -- the command was printed, not executed",
                        )
                        for a in step.produces
                    ),
                    note="dry run",
                )
            )
            continue

        code, tail = _run(step.command, root, dry=False)
        if code != 0:
            print(tail)
            report.add(
                StepResult(
                    step_id=step.id,
                    ran=True,
                    artefacts=tuple(
                        ArtefactResult(
                            artefact=a,
                            outcome=Outcome.DEVIATED,
                            expected=_expected(a.name)
                            if _expected(a.name) is not None
                            else "present",
                            produced="step failed",
                            note=f"command exited {code}",
                        )
                        for a in step.produces
                    ),
                    note=f"exit {code}",
                    exit_code=code,
                )
            )
            continue

        results = []
        for artefact in step.produces:
            produced = _read_locator(root, artefact.locator)
            expected = _expected(artefact.name)
            if produced is None:
                results.append(
                    ArtefactResult(
                        artefact=artefact,
                        outcome=Outcome.DEVIATED,
                        expected=expected if expected is not None else "present",
                        produced="absent",
                        note="the step reported success but produced nothing at its locator",
                    )
                )
                continue
            if isinstance(produced, bytes) and artefact.name in FILE_DIGESTS:
                # A recorded digest turns "the step wrote something" into "the
                # step wrote the same thing". Without it a file artefact can only
                # be existence-checked, and rendering that as "byte-identical /
                # reproduced" overstates by exactly the amount that matters.
                digest = hashlib.sha256(produced).hexdigest()
                expected_digest = FILE_DIGESTS[artefact.name]
                results.append(
                    ArtefactResult(
                        artefact=artefact,
                        outcome=(
                            Outcome.REPRODUCED if digest == expected_digest else Outcome.DEVIATED
                        ),
                        expected=f"sha256:{expected_digest[:16]}",
                        produced=f"sha256:{digest[:16]}",
                        note=(
                            ""
                            if digest == expected_digest
                            else "content or line endings differ; see FILE_DIGESTS"
                        ),
                    )
                )
                continue
            if isinstance(produced, bytes) or expected is None:
                # A file with no recorded headline value: presence is all this
                # pass can check, and saying so beats implying more.
                results.append(
                    ArtefactResult(
                        artefact=artefact,
                        outcome=Outcome.REPRODUCED,
                        expected="present",
                        produced="present",
                        note=(
                            "existence only -- no headline value is recorded for this "
                            "artefact, so this pass checks that it was produced and not "
                            "what is in it"
                        ),
                    )
                )
                continue
            value = float(produced)
            agrees = artefact.agrees(value, float(expected))
            results.append(
                ArtefactResult(
                    artefact=artefact,
                    outcome=Outcome.REPRODUCED if agrees else Outcome.DEVIATED,
                    expected=float(expected),
                    produced=value,
                )
            )
        report.add(StepResult(step_id=step.id, ran=True, artefacts=tuple(results)))

    rendered = render_markdown(report)
    RENDERED.write_text(rendered + "\n", encoding="utf-8")
    payload["verification"] = report.as_dict()
    RECORD.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    passed, reasons = report.gate()
    _rule("Gate")
    print("PASS" if passed else "FAIL")
    for reason in reasons:
        print(f"  - {reason}")
    print(f"\n  written: {RENDERED.relative_to(REPO_ROOT)}")
    return 0 if passed else 1


class GitUnavailable(RuntimeError):
    """git could not answer, which is not the same as git answering 'no'."""


def _gitignored(root: Path, paths: tuple[str, ...]) -> list[str]:
    """Ask git which of `paths` it ignores. Shelling out is a runner's job.

    The exit-code handling matters more than it looks. `git check-ignore` exits
    0 when something is ignored, 1 when nothing is, and 128 on an error -- no
    repository, no git binary, a broken index. Folding 128 into 1 would make
    this check fire on every environment where git cannot answer, and a check
    that fires on everything is exactly as uninformative as one that fires on
    nothing (Phase 21's corollary). So an error raises rather than reporting an
    empty ignore set.
    """
    try:
        proc = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "--no-index", *paths],
            cwd=root,
            capture_output=True,
            text=True,
        )
    except (OSError, FileNotFoundError) as exc:  # no git binary at all
        raise GitUnavailable(f"could not run git in {root}: {exc}") from exc
    if proc.returncode not in (0, 1):
        raise GitUnavailable(
            f"`git check-ignore` exited {proc.returncode} in {root} "
            f"({proc.stderr.strip() or 'no stderr'}). That is git failing to answer, not "
            "git saying these paths are tracked -- so this run cannot establish whether "
            "the tree is fresh, and refuses rather than guessing."
        )
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--declare", action="store_true", help="freeze tolerances; runs nothing")
    parser.add_argument(
        "--redeclare", action="store_true", help="overwrite an existing declaration"
    )
    parser.add_argument("--declared-on", default="")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--root", default=str(REPO_ROOT), help="the tree to verify IN")
    parser.add_argument("--tiers", default="A,B", help="comma-separated tier letters")
    parser.add_argument("--dry-run", action="store_true", help="print commands, run none")
    parser.add_argument(
        "--force",
        action="store_true",
        help="measure even in a contaminated tree; the gate still fails, by design",
    )
    args = parser.parse_args()

    if args.declare:
        return declare(args)
    if args.verify:
        return verify(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
