#!/usr/bin/env python
"""The Phase 12 gate: label validation and taxonomy refinement.

    python scripts/run_taxonomy_refinement.py --burden                  # OPEN-026
    python scripts/run_taxonomy_refinement.py --burden --measured-minutes-per-item 1.9 \
        --measured-source "gold_dev pass, A1, 2026-08-14, stopwatch"
    python scripts/run_taxonomy_refinement.py --propose config/taxonomy_v3.yaml
    python scripts/run_taxonomy_refinement.py --status

Offline, free and deterministic, like every other gate in this project.

**NOTE (2026-09-28): `--refine` no longer exists.** `config/taxonomy.yaml`
freezes the construct set at Phase 12 *"after checking annotation burden and
inter-annotator agreement."* By owner decision this project does not report
inter-annotator agreement (see `CLAUDE.md` sec.20-21 and
`config/annotators.yaml`'s header), so the disagreement-driven half of this
gate -- `src/taxonomy/refinement.py` and `src/annotation/agreement.py`, which
supplied its only input -- was deleted rather than left permanently blocked.
Backups are under `annotation/gold_dev/_backup_2026-09-28/removed_20260928/`.
Taxonomy freezing at Phase 12 now rests on burden alone plus owner rubric
review, not on a measured kappa.

- **Burden** needs nothing but the taxonomy, so `--burden` runs today and closes
  the arithmetic half of OPEN-026. It cannot close the *measurement* half; the
  report says so in its own text until someone passes
  `--measured-minutes-per-item`.

`--propose` is likewise runnable now: it diffs a candidate taxonomy against the
locked one and prices the silver re-labelling the change would force, so a
proposal can be costed before it is adopted rather than after.

**Nothing here writes `config/taxonomy.yaml`.** The construct set is an owner
decision (`CLAUDE.md` sec.10). A taxonomy a script can shrink is not frozen.

Exit codes: 0 gate passed, 1 gate blocked or failed, 2 configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

from src.agents.config import ConfigError, load_taxonomy  # noqa: E402
from src.annotation import GoldStore, load_annotators  # noqa: E402
from src.labeling.store import SilverStore  # noqa: E402
from src.taxonomy import (  # noqa: E402
    Changelog,
    TaxonomyVersionError,
    TimingModel,
    diff_taxonomy,
    estimate_burden,
    relabel_scope,
)

REPORTS = REPO_ROOT / "reports"
DOCS = REPO_ROOT / "docs"
GOLD_CANDIDATES = REPO_ROOT / "data" / "processed" / "gold_candidates"

#: Items per batch, read from the Phase 9 sampling plan rather than hardcoded so
#: burden tracks the sample that actually exists.
BATCH_FILES = {"gold_dev": "gold_dev.jsonl", "gold_eval": "gold_eval.jsonl"}


def _rule(title: str) -> None:
    print()
    print("-" * 78)
    print(title)
    print("-" * 78)


def _batch_size(batch: str) -> int:
    path = GOLD_CANDIDATES / BATCH_FILES[batch]
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Regenerate the sample with "
            "`python scripts/run_eda.py` -- do not redraw it by hand; the plan is what "
            "makes the evaluation set leakage-safe"
        )
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def cmd_burden(args, taxonomy) -> int:
    _rule("Annotation burden (OPEN-026)")
    constructs = list(taxonomy["constructs"])

    timing = None
    if args.measured_minutes_per_item is not None:
        if not args.measured_source:
            print(
                "ERROR: --measured-minutes-per-item requires --measured-source. An "
                "unattributed number is not better than a declared assumption.",
                file=sys.stderr,
            )
            return 2
        timing = TimingModel.from_measurement(
            observed_minutes_per_item=args.measured_minutes_per_item,
            n_constructs=len(constructs),
            source=args.measured_source,
        )

    try:
        roster = load_annotators()
    except Exception:  # noqa: BLE001 -- roster problems are Phase 11's gate, not this one
        roster = {}
    # Single-annotator by decision (2026-09-28) -- this used to be
    # max(2, len(roster)) because the plan mandated 100% double annotation.
    # It no longer does; burden is costed for the roster as it actually is.
    n_annotators = max(1, len(roster))

    reports = {}
    for batch in BATCH_FILES:
        try:
            n_items = _batch_size(batch)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        report = estimate_burden(
            batch=batch,
            n_items=n_items,
            constructs=constructs,
            n_annotators=n_annotators,
            timing=timing,
        )
        reports[batch] = report
        print()
        print(report.to_markdown())

    REPORTS.mkdir(exist_ok=True)
    md = "\n\n---\n\n".join(r.to_markdown() for r in reports.values())
    (REPORTS / "annotation_burden.md").write_text(md + "\n", encoding="utf-8")
    (REPORTS / "annotation_burden.json").write_text(
        json.dumps({k: v.to_dict() for k, v in reports.items()}, indent=2) + "\n",
        encoding="utf-8",
    )
    print()
    print("  wrote reports/annotation_burden.md")
    print("  wrote reports/annotation_burden.json")

    measured = timing is not None
    print()
    if measured:
        print("  OPEN-026: CLOSED -- the estimate is anchored to a real observation.")
    else:
        print("  OPEN-026: STILL OPEN. The arithmetic is done; the stopwatch is not.")
        print("  Time the gold_dev calibration pass and re-run with")
        print("    --measured-minutes-per-item <n> --measured-source '<who, when, how>'")
        print("  100 items with a stopwatch produces the number BEFORE the 400-item")
        print("  commitment is made, which is the whole point of doing it at gold_dev.")
    return 0


def cmd_propose(args, taxonomy) -> int:
    _rule(f"Proposed taxonomy: {args.propose}")
    path = Path(args.propose)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 2
    try:
        proposed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"ERROR: {path} is not valid YAML: {exc}", file=sys.stderr)
        return 2
    if not isinstance(proposed.get("constructs"), dict):
        print(f"ERROR: {path} has no readable 'constructs' mapping", file=sys.stderr)
        return 2

    changes = diff_taxonomy(taxonomy, proposed)
    print(f"  {len(changes)} change(s); {sum(c.invalidates_silver for c in changes)} invalidating")

    labels: list = []
    silver = SilverStore()
    for _provenance, rows in silver.iter_all():
        labels.extend(rows)
    # Records, not construct labels. `relabel_scope` counts the latter, and the
    # two differ by ~1.5x -- printing one under the other's name is how a cost
    # estimate quietly becomes wrong.
    print(f"  silver records on disk: {len(labels)}")

    scope = relabel_scope(changes, labels) if changes else None

    try:
        changelog = Changelog(
            old_version=int(taxonomy.get("version", 0)),
            new_version=int(proposed.get("version", 0)),
            reason=args.reason or "",
            changes=changes,
            scope=scope,
        )
    except TaxonomyVersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print()
    print(changelog.to_markdown())

    if args.write:
        DOCS.mkdir(exist_ok=True)
        out = DOCS / "taxonomy_changelog.md"
        out.write_text(changelog.to_markdown() + "\n", encoding="utf-8")
        print()
        print(f"  wrote {out.relative_to(REPO_ROOT)}")
        print("  NOTE: config/taxonomy.yaml was NOT modified. Applying the change is an")
        print("  owner action (CLAUDE.md sec.10).")
    return 0


def cmd_status(args, taxonomy) -> int:
    _rule("Phase 12 status")
    constructs = list(taxonomy["constructs"])
    print(f"  taxonomy v{taxonomy.get('version')} -- {len(constructs)} constructs")
    print(f"  locked at phase {taxonomy.get('locked_at_phase')} ({taxonomy.get('locked_on')})")

    print()
    print("  Freeze criterion: burden + owner rubric review (IAA dropped 2026-09-28,")
    print("  see CLAUDE.md sec.20-21).")
    burden_report = REPORTS / "annotation_burden.json"
    if burden_report.exists():
        data = json.loads(burden_report.read_text(encoding="utf-8"))
        measured = any(v.get("estimate_is_measured") for v in data.values())
        print(f"    burden    : computed ({'MEASURED' if measured else 'estimate only'})")
    else:
        print("    burden    : not computed -- run --burden")

    store = GoldStore()
    for batch in BATCH_FILES:
        ids = store.annotator_ids(batch)
        print(f"    gold      : {batch:<10} passes ingested: {ids or 'none'}")

    print()
    print("  Nothing in Phase 12 writes config/taxonomy.yaml.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 12 taxonomy refinement gate")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--burden", action="store_true", help="annotation burden (OPEN-026)")
    action.add_argument("--propose", metavar="PATH", help="diff a candidate taxonomy")
    action.add_argument("--status", action="store_true", help="where everything stands")

    parser.add_argument("--batch", default="gold_dev", choices=tuple(BATCH_FILES))
    parser.add_argument("--measured-minutes-per-item", type=float, default=None)
    parser.add_argument("--measured-source", default="", help="who timed it, when, how")
    parser.add_argument("--reason", default="", help="why the taxonomy is changing")
    parser.add_argument("--write", action="store_true", help="write docs/taxonomy_changelog.md")
    args = parser.parse_args(argv)

    try:
        taxonomy = load_taxonomy()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.burden:
        return cmd_burden(args, taxonomy)
    if args.propose:
        return cmd_propose(args, taxonomy)
    return cmd_status(args, taxonomy)


if __name__ == "__main__":
    raise SystemExit(main())
