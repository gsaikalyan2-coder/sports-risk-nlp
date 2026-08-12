#!/usr/bin/env python
"""Category A5 collection runner -- topic-scoped pre-competition forum text.

    python scripts/run_reddit.py --dry-run                    # plan; no network
    python scripts/run_reddit.py --public --subreddit running --pages 2
    python scripts/run_reddit.py --public --all-communities --pages 2
    python scripts/run_reddit.py --verify-only                # inspect what exists

READ FIRST: `docs/ethics.md` §3.5. This runner collects real people's words under
a policy amendment that narrowed a previously absolute prohibition. §3.5.2
records the argument *against* that amendment and §3.5.5 records the caveat on
unauthenticated collection. Neither is optional reading before running this.

What this does
--------------
Query a permitted community for pre-competition posts, filter them through the
eleven A5 conditions (`src/ingestion/reddit.py`), and write survivors to
`data/raw/<source_id>/` with a complete `provenance.json`.

Two fetch routes, per C2:

* **route (a)** `--client` -- official API via a registered application (PRAW).
  Preferred. Requires credentials, which live in `.env` and never in the repo.
* **route (b)** `--public` -- unauthenticated public JSON endpoints, rate
  limited to one request per 6.5s. Added 2026-08-12 because the owner could not
  register an application. **This is a weaker compliance position than route
  (a)** -- Reddit's Data API Terms ask programmatic users to register, so P4 is
  not automatically satisfied. See §3.5.5 and OPEN-031.

What it deliberately does not do
--------------------------------
There is no author parameter, on this script or on anything it calls. C1 permits
collecting posts matched by topic and prohibits collecting people matched by
identity, and that is enforced by the absence of the parameter rather than by a
check that could be deleted.

There is no `--force`, no `--skip-checks`, no way to write a record that failed a
condition. Every drop is logged to `logs/ingestion_refusals.log` with the cue
that triggered it, so the filters can be audited for false positives.

`deidentified` stays **False** on every record this writes. Flipping it is Phase
8's job (`scripts/run_preprocessing.py`), and doing it here would mark
un-de-identified text as clean.

Exit codes: 0 success, 1 nothing collected, 2 configuration or policy refusal.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.allowlist import IngestionRefused  # noqa: E402
from src.ingestion.reddit import (  # noqa: E402
    PERMITTED_COMMUNITIES,
    HarvestQuery,
    HarvestStats,
    a5_descriptor,
    fetch_listing_public,
    harvest,
)
from src.ingestion.store import RawStore  # noqa: E402

#: Default query. Broad on purpose -- `is_pre_competition` in the harvester does
#: the real scope work, and a narrow server-side query would silently bias the
#: sample toward whichever phrasing the query happened to use.
DEFAULT_QUERY = "race OR meet OR competition OR marathon OR nervous"


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7/A5 Reddit collection")
    parser.add_argument("--subreddit", default="running", choices=PERMITTED_COMMUNITIES)
    parser.add_argument("--all-communities", action="store_true")
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--limit", type=int, default=100, help="posts per page (max 100)")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument(
        "--public",
        action="store_true",
        help="route (b): unauthenticated public JSON. See docs/ethics.md §3.5.5.",
    )
    parser.add_argument("--source-id", default=None)
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="plan only; no network, no writes")
    parser.add_argument("--verify-only", action="store_true", help="report an existing source")
    args = parser.parse_args(argv)

    communities = list(PERMITTED_COMMUNITIES) if args.all_communities else [args.subreddit]
    source_id = args.source_id or f"reddit_a5_{date.today().isoformat().replace('-', '')}"
    store = RawStore(root=args.raw_root) if args.raw_root else RawStore()

    if args.verify_only:
        return _verify(store, source_id)

    _rule("A5 collection plan")
    print(f"  source_id   : {source_id}")
    print(f"  communities : {', '.join(communities)}")
    print(f"  query       : {args.query!r}")
    print(f"  pages/limit : {args.pages} x {args.limit}")
    print(f"  route       : {'(b) PUBLIC, unauthenticated' if args.public else '(a) official API'}")
    print()
    print("  Conditions enforced at ingestion: C1 topic-scoped (no author parameter exists),")
    print("  C3 minors, C4 health content, C5 deidentified=False, C11 minimisation.")
    print("  Every drop is logged to logs/ingestion_refusals.log with the cue that matched.")

    if args.public:
        print()
        print("  ROUTE (b) CAVEAT -- docs/ethics.md §3.5.5, OPEN-031:")
        print("  Reddit's Data API Terms ask programmatic users to register an application.")
        print("  Unauthenticated reads are a GRAY AREA, not a clearly permitted method, so")
        print("  P4 (ToS) is not automatically satisfied. Registering is free and removes")
        print("  the ambiguity. The paper must describe the method as 'public read-only")
        print("  endpoints, unauthenticated', never as 'via the Reddit API'.")

    if args.dry_run:
        print("\n  Dry run: no network call made, nothing written.")
        return 0

    if not args.public:
        print(
            "\nERROR: route (a) needs a PRAW client, which this script does not construct.\n"
            "Credentials must not live in the repo. Either:\n"
            "  - pass --public to use route (b), or\n"
            "  - import fetch_listing() from src.ingestion.reddit in your own script,\n"
            "    building the praw.Reddit client from environment variables.",
            file=sys.stderr,
        )
        return 2

    stats = HarvestStats()
    written = 0
    fetch_failures = 0

    try:
        descriptor = a5_descriptor(source_id, communities[0])
        with store.open_source(descriptor) as writer:
            for community in communities:
                query = HarvestQuery(
                    subreddit=community, query=args.query, limit=min(100, args.limit)
                )
                print(f"\n  fetching r/{community} ...", flush=True)
                try:
                    posts = list(fetch_listing_public(query, pages=args.pages))
                except Exception as exc:  # noqa: BLE001 - network/ToS failures are user-facing
                    fetch_failures += 1
                    print(f"    FETCH FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
                    print(
                        "    If this is a 403 or 429, treat it as an answer rather than an\n"
                        "    obstacle (docs/ethics.md §3.5.5 point 4). Do not retry harder.",
                        file=sys.stderr,
                    )
                    continue
                print(f"    fetched {len(posts)} posts", flush=True)

                for record in harvest(posts, source_id=source_id, subreddit=community, stats=stats):
                    writer.write(record)
                    written += 1
    except IngestionRefused as exc:
        print(f"\nREFUSED: {exc}", file=sys.stderr)
        print("Logged to logs/ingestion_refusals.log.", file=sys.stderr)
        return 2

    _rule("Result")
    for line in stats.as_lines():
        print(" ", line)
    if fetch_failures:
        print(f"  fetch failures: {fetch_failures} of {len(communities)} communities")
    print(f"\n  written to data/raw/{source_id}/: {written} records")

    if written == 0:
        # An empty source directory still carries a provenance.json asserting an
        # A5 collection, so every later phase sees a source that collected
        # nothing and reports it forever -- Phase 8 preprocessed exactly such a
        # directory on 2026-08-12. Provenance for a collection that did not
        # happen is worse than no directory at all.
        source_dir = (args.raw_root or (REPO_ROOT / "data" / "raw")) / source_id
        print(
            f"\n  Empty source directory left at {source_dir}.\n"
            "  Its provenance.json asserts a collection that produced nothing, and "
            "every\n"
            "  later phase will pick it up. Remove it unless you are about to retry:\n"
            f"    Remove-Item -Recurse -Force {source_dir}"
        )

    if written == 0:
        # Two very different failures, previously reported as one. Saying
        # "nothing survived the filters" after a total fetch failure sends the
        # reader to tune filters that never ran -- observed 2026-08-12, when
        # every request returned 403 and the message blamed the filters.
        if stats.seen == 0 and fetch_failures:
            print(
                f"\n  NOTHING WAS FETCHED. {fetch_failures} of {len(communities)} "
                "communities failed at the network, so the filters never ran.\n"
                "  This is NOT a filter-tuning problem and widening the query will "
                "not help.\n\n"
                "  A 403 on route (b) is Reddit refusing unauthenticated "
                "programmatic reads.\n"
                "  Per docs/ethics.md §3.5.5 point 4, that is an answer: collection "
                "stops here.\n"
                "  Do NOT rotate User-Agents, use a proxy, or impersonate a browser -- "
                "that is\n"
                "  circumventing an access control (P5) and violates the condition "
                "this route\n"
                "  was granted under.\n\n"
                "  Remaining routes: register an application and use route (a), or "
                "switch to\n"
                "  A3 consented donation, which needs no API at all.",
                file=sys.stderr,
            )
        else:
            print(
                f"\n  Fetched {stats.seen} posts; none survived the filters. That is a\n"
                "  legitimate outcome, not a bug -- the minor and health filters are\n"
                "  over-inclusive by design. Check logs/ingestion_refusals.log to see\n"
                "  which condition dominated.",
                file=sys.stderr,
            )
        return 1

    print("\n  NEXT: de-identify before anything reads this text (C5).")
    print("    python scripts/run_preprocessing.py")
    print("  Records carry deidentified=False until that runs.")
    return 0


def _verify(store: RawStore, source_id: str) -> int:
    """Report what a collected source actually contains."""
    try:
        provenance, records = store.read_source(source_id)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot read source {source_id!r}: {exc}", file=sys.stderr)
        return 2

    _rule(f"Source: {source_id}")
    print(f"  records        : {len(records)}")
    print(f"  category       : {provenance.allowlist_category}")
    print(f"  collected      : {provenance.collection_date}")
    print(f"  deidentified   : {provenance.deidentified}")
    print(f"  synthetic      : {provenance.synthetic}")

    deidentified = sum(1 for r in records if r.deidentified)
    print(f"  records marked deidentified: {deidentified}/{len(records)}")
    if deidentified == 0:
        print("    (correct before Phase 8; C5 requires the pass before model use)")

    with_timing = sum(1 for r in records if r.time_to_competition_days is not None)
    print(f"  with days-to-competition   : {with_timing}/{len(records)}")
    lengths = sorted(len(r.text.split()) for r in records)
    if lengths:
        print(f"  words: min {lengths[0]}, median {lengths[len(lengths) // 2]}, max {lengths[-1]}")
    print("\n  Reminder (C6): no text from this source may appear verbatim in the paper,")
    print("  the dashboard, or any figure. A distinctive sentence is an identifier.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
