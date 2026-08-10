#!/usr/bin/env python
"""The Phase 10 gate: silver-label `data/interim/` into `data/processed/silver/`.

    python scripts/run_labeling.py                    # offline, whole corpus, free
    python scripts/run_labeling.py --project-only     # cost projection, no calls at all
    python scripts/run_labeling.py --live --limit 50  # a paid pilot, bounded
    python scripts/run_labeling.py --live             # the real pass
    python scripts/run_labeling.py --verify-only      # audit what is already written
    python scripts/run_labeling.py --no-context       # the dedup ablation

**Offline is the default and that is a safety property, not a convenience.**
`config/model_routing.yaml` sets `mode: offline`; this script never overrides it
implicitly. Spending money requires typing `--live`. A reviewer with no API key
must be able to run this and get a real artefact, which is the same property
`scripts/run_ingestion.py` and `scripts/run_preprocessing.py` already have.

**What an offline run does and does not prove.** It exercises the whole
pipeline -- dedup, routing, escalation, parsing, span validation, fan-out,
storage, QA queue -- against a seeded stub. It proves the plumbing. It proves
nothing whatsoever about label quality, because the stub's content is
meaningless by construction. Label quality is unmeasurable until the Phase 11
human gold set exists, and is never measured against `generation_spec`.

**Before any live run**, `python scripts/refresh_pricing.py --check` must pass.
A retired model ID returns 404 and kills a batch partway through (OPEN-009).
This script refuses `--live` without `--pricing-checked` for exactly that
reason: it cannot verify the catalogue itself without a network call the offline
path must not make.

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

from src.agents import (  # noqa: E402
    BudgetExceededError,
    ConfigError,
    CostLedger,
    build_llm,
    load_routing,
    load_taxonomy,
)
from src.ingestion.allowlist import IngestionRefused  # noqa: E402
from src.labeling import (  # noqa: E402
    SYSTEM_PROMPT_VERSION,
    SilverStore,
    build_plan,
    cached_system_prompt,
    format_report,
    label_records,
    overlap_report,
    project_cost,
    run_qa,
)
from src.labeling.ancestry import DEFAULT_OVERLAP_THRESHOLD  # noqa: E402
from src.preprocessing import InterimStore  # noqa: E402

#: Gate floors. Set from what the pipeline must structurally achieve, not from
#: what a particular run happened to score -- a floor tuned to an observed
#: number stops being a test of anything.
MAX_FAILURE_RATE = 0.02  # unparseable after one escalation
MIN_ABSTENTION_RATE = 0.01  # a labeller that never abstains is broken
MAX_ABSTENTION_RATE = 0.95  # ...and one that always abstains has not labelled


def _rule(title: str) -> None:
    print()
    print("-" * 78)
    print(title)
    print("-" * 78)


def load_corpus(interim_store: InterimStore):
    """Read every interim source. Returns (records, source_provenances)."""
    records = []
    provenances = {}
    for provenance, source_records in interim_store.iter_all():
        provenances[provenance.source_id] = provenance
        records.extend(source_records)
    return records, provenances


def report_plan(plan, *, use_context: bool) -> None:
    print(f"  {plan.summary()}")
    if use_context:
        print(
            "  key = hash(system + user), and the user prompt contains the parent "
            "record, so identical utterances in different records are different calls."
        )
        print(
            "  Text-only keying would give a bigger saving and a wrong answer -- "
            "see docs/labeling.md sec.3."
        )
    else:
        print("  --no-context: key is the utterance alone. This is the ABLATION, not the default.")


def report_run(run) -> bool:
    ok = True
    print(f"  {run.summary()}")
    print(f"  labels written : {len(run.labels)} / {run.plan.total_records} utterances")
    print(f"  distinct calls : {run.plan.calls} (+{run.escalations} escalations)")
    print(f"  abstention rate: {run.abstention_rate:.3f}")
    print(f"  tokens         : {run.input_tokens} in / {run.output_tokens} out")
    print(f"  cost           : ${run.cost_usd:.6f}")

    denominator = run.plan.total_records or 1
    failure_rate = len(run.failures) / denominator
    if failure_rate > MAX_FAILURE_RATE:
        print(f"  FAIL  failure rate {failure_rate:.3f} > {MAX_FAILURE_RATE}")
        ok = False
    else:
        print(f"  ok    failure rate {failure_rate:.3f} <= {MAX_FAILURE_RATE}")

    if run.labels:
        if not MIN_ABSTENTION_RATE <= run.abstention_rate <= MAX_ABSTENTION_RATE:
            print(
                f"  FAIL  abstention rate {run.abstention_rate:.3f} outside "
                f"[{MIN_ABSTENTION_RATE}, {MAX_ABSTENTION_RATE}]"
            )
            ok = False
        else:
            print("  ok    abstention is exercised and is not the only answer")

    print("  constructs asserted (silver, NOT ground truth):")
    counts = run.construct_counts()
    if not counts:
        print("    (none)")
    for construct, count in counts.items():
        print(f"    {construct:<26} {count}")
    return ok


def verify_silver(store: SilverStore) -> bool:
    """Audit what is on disk, independently of the run that produced it."""
    ok = True
    total = 0
    for provenance, labels in store.iter_all():
        total += len(labels)
        print(f"  {provenance.source_id}: {len(labels)} label(s)")
        if provenance.record_count != len(labels):
            print(f"  FAIL  provenance claims {provenance.record_count}, file holds {len(labels)}")
            ok = False
        missing_conf = [x.record_id for x in labels if not 0.0 <= x.confidence <= 1.0]
        missing_rat = [x.record_id for x in labels if not x.rationale.strip()]
        no_route = [x.record_id for x in labels if not x.tier or not x.model]
        stale = [x.record_id for x in labels if x.prompt_version != SYSTEM_PROMPT_VERSION]
        for name, offenders in (
            ("confidence out of range", missing_conf),
            ("empty rationale", missing_rat),
            ("no routing decision", no_route),
            (f"prompt version != {SYSTEM_PROMPT_VERSION}", stale),
        ):
            if offenders:
                print(f"  FAIL  {len(offenders)} label(s) with {name}: {offenders[:3]}")
                ok = False
        if labels:
            print("  ok    every label carries confidence, rationale and a routing decision")
    if total == 0:
        print("  FAIL  no silver labels on disk")
        ok = False
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 10 weak-labelling gate")
    parser.add_argument("--live", action="store_true", help="call OpenRouter and spend money")
    parser.add_argument(
        "--pricing-checked",
        action="store_true",
        help="assert scripts/refresh_pricing.py --check passed just now (required with --live)",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap on DISTINCT prompts sent")
    parser.add_argument("--no-context", action="store_true", help="dedup ablation: drop context")
    parser.add_argument("--project-only", action="store_true", help="cost projection, no calls")
    parser.add_argument(
        "--cache-discount",
        type=float,
        default=1.0,
        help=(
            "multiplier applied to the cached system prefix in the projection. "
            "1.0 (default) gives caching no credit and is the honest upper bound. "
            "Only pass a lower value once a pilot has MEASURED the provider's "
            "cache-read rate."
        ),
    )
    parser.add_argument("--verify-only", action="store_true", help="audit disk, write nothing")
    parser.add_argument("--interim-root", type=Path, default=None)
    parser.add_argument("--silver-root", type=Path, default=None)
    parser.add_argument("--queue", type=Path, default=REPO_ROOT / "logs" / "review_queue.jsonl")
    args = parser.parse_args(argv)

    use_context = not args.no_context

    try:
        routing = load_routing()
        taxonomy = load_taxonomy()
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.live and not args.pricing_checked:
        print(
            "ERROR: --live requires --pricing-checked. Run\n"
            "         python scripts/refresh_pricing.py --check\n"
            "       first. OPEN-009: a retired model ID returns 404 and kills the\n"
            "       batch partway through, leaving a half-written silver dataset.",
            file=sys.stderr,
        )
        return 2

    if args.live and not routing.api_key():
        print(
            f"ERROR: --live needs {routing.api_key_env} set in .env (see .env.example).",
            file=sys.stderr,
        )
        return 2

    try:
        interim_store = InterimStore(root=args.interim_root)
        silver_store = SilverStore(root=args.silver_root)
    except IngestionRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.verify_only:
        _rule("Verifying data/processed/silver/")
        ok = verify_silver(silver_store)
        print()
        print("Phase 10 gate (verify only):", "PASSED" if ok else "FAILED")
        return 0 if ok else 1

    _rule("Corpus")
    try:
        records, provenances = load_corpus(interim_store)
    except IngestionRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"  {len(records)} utterance(s) across {len(provenances)} source(s)")
    if not records:
        print("ERROR: nothing to label; run scripts/run_preprocessing.py first", file=sys.stderr)
        return 2

    _rule("Deduplication plan")
    system = cached_system_prompt()
    plan = build_plan(records, system_prompt=system, use_context=use_context)
    report_plan(plan, use_context=use_context)

    _rule("Cost projection (before anything is spent)")
    projection = project_cost(
        plan, routing=routing, system_prompt=system, cache_discount=args.cache_discount
    )
    for key, value in projection.items():
        print(f"  {key:<28} {value}")
    print(f"  monthly cap                  ${routing.budget.monthly_cap_usd:.2f} (enforced)")
    print(
        "  NOTE: config/model_routing.yaml's worked estimate (~$1.12) assumed ~400 "
        f"input tokens per call. The real rubric prompt is "
        f"{int(projection['system_prompt_tokens'])} tokens. See docs/labeling.md sec.5."
    )
    if projection["projected_usd"] > routing.budget.monthly_cap_usd:
        print(
            "  WARNING: the projection exceeds the cap. The ledger will refuse the run "
            "partway. Do NOT raise the cap to make it finish -- reduce --limit or "
            "shorten the prompt."
        )
    if args.project_only:
        print()
        print("Projection only; no calls made.")
        return 0

    mode = "live" if args.live else "offline"
    _rule(f"Labelling ({mode})")
    if args.live:
        print("  LIVE: this run spends money. Ledger enforcement is on.")

    # The offline stub is given only the GRADED construct names. It cannot know
    # a construct's label type, so a categorical construct would come back with
    # value "present", which the parser correctly refuses -- an offline run would
    # then measure the stub's ignorance rather than the pipeline. Narrowing the
    # stub's vocabulary is a property of the stub, not of the taxonomy.
    graded = tuple(
        name for name, spec in (taxonomy.get("constructs") or {}).items() if not spec.get("labels")
    )
    ledger = CostLedger(routing.budget)
    llm = build_llm(routing, mode=mode, ledger=ledger, constructs=graded)

    try:
        run = label_records(
            records,
            llm=llm,
            routing=routing,
            taxonomy=taxonomy,
            use_context=use_context,
            limit=args.limit,
            mode=mode,
        )
    except BudgetExceededError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        print(
            "The run stopped rather than silently truncating. Nothing was written.",
            file=sys.stderr,
        )
        return 2

    ok = report_run(run)
    log_path = run.write_log()
    print(f"  run log: {log_path.relative_to(REPO_ROOT)}")

    _rule("Writing data/processed/silver/")
    by_source: dict[str, list] = {}
    for label in run.labels:
        by_source.setdefault(label.source_id, []).append(label)
    for source_id, labels in sorted(by_source.items()):
        with silver_store.open_source(provenances[source_id]) as writer:
            writer.manifest = {
                "run_id": run.run_id,
                "mode": run.mode,
                "prompt_version": run.prompt_version,
                "context_used": use_context,
                "distinct_prompts": run.plan.calls,
                "escalations": run.escalations,
                "cost_usd": round(run.cost_usd, 6),
                "failures": len(run.failures),
            }
            writer.write_all(labels)
        print(f"  {source_id}: wrote {len(labels)} label(s)")

    _rule("Annotation-QA review queue")
    items, summary = run_qa(run, confidence_threshold=routing.confidence_threshold, path=args.queue)
    for reason, count in summary.items():
        print(f"  {reason:<30} {count}")
    print(f"  queue: {args.queue.relative_to(REPO_ROOT)}")

    _rule("Shared-ancestry probe (OPEN-021)")
    rows = overlap_report(run.labels, taxonomy)
    print(format_report(rows, threshold=DEFAULT_OVERLAP_THRESHOLD))
    if run.mode == "offline":
        print()
        print(
            "  Offline: the stub picks constructs at random, so any gap here is noise. "
            "This table is only interpretable on a live run."
        )

    _rule("Ledger")
    print(f"  {ledger.summary()}")

    (REPO_ROOT / "reports").mkdir(exist_ok=True)
    (REPO_ROOT / "reports" / "labeling_run.json").write_text(
        json.dumps(
            {
                "run": run.to_dict(),
                "projection": projection,
                "queue": summary,
                "ancestry": [row.to_dict() for row in rows],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    _rule("Verifying data/processed/silver/")
    ok = verify_silver(silver_store) and ok

    print()
    print("Phase 10 gate:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
