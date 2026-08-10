#!/usr/bin/env python
"""The Phase 11 gate: build the annotation project, ingest passes, report agreement.

    python scripts/run_annotation.py --build --batch gold_dev     # make the Potato project
    python scripts/run_annotation.py --build --batch gold_eval
    python scripts/run_annotation.py --ingest --batch gold_dev --annotator A1
    python scripts/run_annotation.py --agreement --batch gold_dev
    python scripts/run_annotation.py --status                     # where is everything

Offline, free and deterministic, like every other gate in this project. No
network, no API key, no model.

**The order is load-bearing.** `gold_dev` first: both annotators label it, you
compare, you argue about the rubric, you amend `docs/annotation_guidelines.md`,
and only then does anyone open `gold_eval`. `gold_dev` is drawn from
training-side templates precisely so that burning it on rubric arguments costs
zero evaluation power. An item read during an argument about the rubric is no
longer an independent measurement.

**This gate can fail for a reason no code can fix.** Agreement needs two people.
With one pass on disk, `--agreement` reports UNMEASURABLE and exits non-zero.
That is not a bug to route around; it is the Phase 11 blocker being visible.

Exit codes: 0 gate passed, 1 gate failed, 2 configuration or policy error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agents.config import ConfigError, load_taxonomy  # noqa: E402
from src.annotation import (  # noqa: E402
    POTATO_VERSION,
    AgreementUnmeasurable,
    ContextError,
    GoldSchemaError,
    GoldStore,
    GoldWriteRefused,
    align,
    compute_agreement,
    context_coverage,
    disagreements,
    discover_passes,
    ingest_passes,
    load_annotators,
    load_batch,
    write_project,
)

DEFAULT_PROJECT_ROOT = REPO_ROOT / "annotation"
REPORTS = REPO_ROOT / "reports"

#: The Phase 12 decision threshold. `config/taxonomy.yaml` says any construct
#: with poor agreement is a candidate to drop; 0.40 is the conventional
#: moderate/fair boundary and is a REPORTING threshold, not a pass/fail one.
#: A gate that failed on it would block Phase 11 on a number the phase exists
#: to discover.
KAPPA_REVIEW_THRESHOLD = 0.40


def _rule(title: str) -> None:
    print()
    print("-" * 78)
    print(title)
    print("-" * 78)


def cmd_build(args, taxonomy) -> int:
    _rule(f"Building the Potato project for {args.batch}")
    try:
        items = load_batch(args.batch)
    except ContextError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    coverage = context_coverage(items)
    for key, value in coverage.items():
        print(f"  {key:<32} {value}")
    print()
    print(
        "  Parent context is attached. docs/annotation_guidelines.md sec.3 step 1 "
        "requires the whole record, and the gold candidates did not carry it."
    )
    print(
        "  The Phase 10 labeller saw the same context, so the Phase 14 comparison "
        "is not measuring a context asymmetry."
    )

    try:
        roster = load_annotators()
    except GoldSchemaError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    paths = write_project(
        items,
        batch=args.batch,
        taxonomy=taxonomy,
        root=args.project_root,
        port=args.port,
        annotators=sorted(roster),
    )
    print()
    for name, path in paths.items():
        print(f"  {name:<8} {path.relative_to(REPO_ROOT)}")

    print()
    print(f"  Annotators on the roster: {sorted(roster)}")
    if len(roster) < 2:
        print()
        print("  WARNING: only one annotator is on the roster.")
        print("  Kappa is undefined with one annotator, so contribution #1 -- 'a corpus")
        print("  with reported inter-annotator agreement' -- cannot exist yet. Add the")
        print("  second person to config/annotators.yaml once they have agreed.")
    print()
    print(f"  Next:  pip install potato-annotation=={POTATO_VERSION}")
    print(
        f"         cd {paths['config'].parent.relative_to(REPO_ROOT)} && potato start config.yaml"
    )
    return 0


def cmd_ingest(args, taxonomy) -> int:
    _rule(f"Ingesting {args.annotator}'s pass over {args.batch}")
    store = GoldStore()
    try:
        annotator = store.resolve_annotator(args.annotator)
    except GoldWriteRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        items = load_batch(args.batch)
    except ContextError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    item_texts = {item.record_id: item.text for item in items}

    output_dir = (args.project_root or DEFAULT_PROJECT_ROOT) / args.batch / "annotation_output"
    discovered = discover_passes(output_dir)
    passes = [p for p in discovered if p.annotator_id == args.annotator]
    if not passes and discovered:
        print(
            f"ERROR: {output_dir} holds passes for {[p.annotator_id for p in discovered]}, "
            f"but not for {args.annotator!r}. Potato names the directory after the id the "
            "annotator logged in with, so this usually means they used a different one.",
            file=sys.stderr,
        )
        return 2
    if not passes:
        print(
            f"ERROR: no annotation output under {output_dir}. Has {args.annotator} "
            "finished a pass in Potato? Expected "
            f"{output_dir.name}/<annotator-id>/user_state.json",
            file=sys.stderr,
        )
        return 2
    for potato_pass in passes:
        print(f"  reading {potato_pass.describe()}")

    report = ingest_passes(
        passes,
        item_texts=item_texts,
        annotator_id=args.annotator,
        batch=args.batch,
        valid_constructs=taxonomy["constructs"],
    )
    print(f"  {report.summary()}")

    if report.errors:
        print()
        print("  REFUSED -- fix these in Potato and re-ingest. Nothing was written.")
        print("  (Refusing beats repairing: a coerced gold label is a corrupted ruler.)")
        for error in report.errors[: args.max_errors]:
            print(f"    {error.record_id}  {error.reason}")
            print(f"      {error.detail}")
        if len(report.errors) > args.max_errors:
            print(f"    ... and {len(report.errors) - args.max_errors} more")
        return 1

    if not report.labels:
        print("  nothing to write")
        return 1

    try:
        path = store.write_pass(
            report.labels, annotator=annotator, batch=args.batch, overwrite=args.overwrite
        )
    except GoldWriteRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"  wrote {path.relative_to(REPO_ROOT)}")
    escalated = [x for x in report.labels if x.escalate]
    if escalated:
        print()
        print(f"  {len(escalated)} item(s) escalated and NOT labelled:")
        for label in escalated[:5]:
            print(f"    {label.record_id}: {label.escalate_reason[:80]}")
        print(
            "  If any reason is surviving identifying information, that is an ethics "
            "incident under docs/ethics.md sec.5 -- report it before continuing."
        )
    return 0


def cmd_agreement(args, taxonomy) -> int:
    _rule(f"Inter-annotator agreement -- {args.batch}")
    store = GoldStore()
    passes = store.read_batch(args.batch)
    print(f"  passes on disk: {sorted(passes)}")

    constructs = list(taxonomy["constructs"])
    try:
        report = compute_agreement(passes, constructs, batch=args.batch, bootstrap=args.bootstrap)
    except AgreementUnmeasurable as exc:
        print()
        print("  UNMEASURABLE")
        print(f"  {exc}")
        print()
        print("Phase 11 gate: FAILED (not a code failure -- the second annotator is missing)")
        return 1

    print()
    print(report.to_markdown())

    REPORTS.mkdir(exist_ok=True)
    md_path = REPORTS / f"agreement_{args.batch}.md"
    md_path.write_text(report.to_markdown() + "\n", encoding="utf-8")
    json_path = REPORTS / f"agreement_{args.batch}.json"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    pairs = align(passes[report.annotator_a], passes[report.annotator_b])
    work = disagreements(pairs, constructs)
    queue_path = REPO_ROOT / "logs" / f"adjudication_{args.batch}.jsonl"
    queue_path.parent.mkdir(exist_ok=True)
    with queue_path.open("w", encoding="utf-8") as fh:
        for row in work:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print()
    print(f"  wrote {md_path.relative_to(REPO_ROOT)}")
    print(f"  wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"  adjudication worklist: {queue_path.relative_to(REPO_ROOT)} ({len(work)} rows)")

    weak = report.below(KAPPA_REVIEW_THRESHOLD)
    if weak:
        print()
        print(f"  Constructs below kappa {KAPPA_REVIEW_THRESHOLD}: {weak}")
        print("  REPORTED, NOT FAILED. config/taxonomy.yaml freezes the construct set at")
        print("  Phase 12 after exactly this check; a gate that failed here would block")
        print("  the phase on the number the phase exists to produce. Read each one's")
        print("  interpretation column first -- a low kappa on a rare construct is the")
        print("  kappa paradox, not necessarily poor annotation.")

    degenerate = [c.construct for c in report.constructs if c.is_degenerate]
    if degenerate:
        print()
        print(f"  Never marked by either annotator: {degenerate}")
        print("  Kappa is undefined for these, and Phase 12 needs to know whether that is")
        print("  a sampling gap or a construct this corpus does not realise.")

    print()
    print("Phase 11 gate:", "PASSED" if report.n_paired > 0 else "FAILED")
    return 0 if report.n_paired > 0 else 1


def cmd_status(args, taxonomy) -> int:
    _rule("Phase 11 status")
    try:
        roster = load_annotators()
        print(f"  roster: {sorted(roster)}")
        if len(roster) < 2:
            print("    BLOCKER: kappa needs two annotators; one is on the roster")
    except GoldSchemaError as exc:
        print(f"  roster: ERROR {exc}")

    store = GoldStore()
    for batch in ("gold_dev", "gold_eval"):
        ids = store.annotator_ids(batch)
        project = (args.project_root or DEFAULT_PROJECT_ROOT) / batch / "config.yaml"
        print()
        print(f"  {batch}")
        print(f"    potato project : {'built' if project.exists() else 'NOT BUILT'}")
        print(f"    passes ingested: {ids or 'none'}")
        if len(ids) >= 2:
            print("    agreement      : computable")
        else:
            print("    agreement      : NOT computable")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 11 annotation gate")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", action="store_true", help="generate the Potato project")
    action.add_argument("--ingest", action="store_true", help="read a completed pass")
    action.add_argument("--agreement", action="store_true", help="compute and report kappa")
    action.add_argument("--status", action="store_true", help="where everything stands")

    parser.add_argument("--batch", default="gold_dev", choices=("gold_dev", "gold_eval"))
    parser.add_argument("--annotator", help="your annotator id from config/annotators.yaml")
    parser.add_argument(
        "--annotator-dir",
        action="store_true",
        help="filter output files by annotator id in the path",
    )
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--overwrite", action="store_true", help="replace an existing pass")
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--max-errors", type=int, default=25)
    args = parser.parse_args(argv)

    try:
        taxonomy = load_taxonomy()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.ingest and not args.annotator:
        # Deliberately mandatory. Writing gold requires a human to type their own
        # id: see the four locks in src/annotation/store.py.
        print("ERROR: --ingest requires --annotator <your-id>", file=sys.stderr)
        return 2

    if args.build:
        return cmd_build(args, taxonomy)
    if args.ingest:
        return cmd_ingest(args, taxonomy)
    if args.agreement:
        return cmd_agreement(args, taxonomy)
    return cmd_status(args, taxonomy)


if __name__ == "__main__":
    raise SystemExit(main())
