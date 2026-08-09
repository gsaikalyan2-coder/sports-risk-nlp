#!/usr/bin/env python
"""The Phase 7 gate: ingest sources into `data/raw/` with provenance.

    python scripts/run_ingestion.py                 # generate + verify (default)
    python scripts/run_ingestion.py --count 2000    # a larger corpus
    python scripts/run_ingestion.py --seed 7        # a different deterministic draw
    python scripts/run_ingestion.py --verify-only   # audit data/raw/, write nothing
    python scripts/run_ingestion.py --demo-refusal  # prove the allow-list refuses

Offline and free by design, matching the Phase 6 precedent in
`scripts/run_crew.py`: no network call, no API key, deterministic under a seed.
A reviewer must be able to rebuild the corpus from a fresh clone.

Exit codes: 0 gate passed, 1 gate failed, 2 configuration or policy error.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion import (  # noqa: E402
    AllowlistError,
    IngestionRefused,
    RawStore,
    SourceDescriptor,
    generate_records,
    generator_stamp,
    load_allowlist,
    metadata_coverage,
    synthetic_descriptor,
    type_token_ratio,
)

DEFAULT_COUNT = 1200
DEFAULT_SEED = 42
SOURCE_ID = "synth_precomp_v1"


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def ingest_synthetic(store: RawStore, count: int, seed: int) -> int:
    """Generate and write the A2 synthetic source. Returns the record count."""
    descriptor = synthetic_descriptor(SOURCE_ID, seed=seed)
    stamp = generator_stamp(seed)
    records = generate_records(count, seed=seed, source_id=descriptor.source_id)

    with store.open_source(descriptor, generator=stamp.to_dict()) as writer:
        writer.write_all(records)
        written = writer.count
        directory = writer.directory

    print(f"  wrote {written} records to {directory.relative_to(REPO_ROOT)}")
    print(f"  provenance: {(directory / 'provenance.json').relative_to(REPO_ROOT)}")
    return written


def demo_refusal(store: RawStore) -> bool:
    """Attempt a source that policy forbids, and confirm it is refused.

    Not a test -- a demonstration that runs in the gate. A control nobody
    exercises outside the test suite is a control nobody has watched work.
    """
    forbidden = SourceDescriptor(
        source_id="demo_refused_social_scrape",
        source_name="Scraped personal social-media posts (deliberately non-compliant)",
        allowlist_category="A9_personal_social_scrape",  # not in the allow-list
        url_or_citation="n/a -- demonstration only, nothing is fetched",
        licence_or_consent_basis="none",
        permitted_uses="none",
        redistribution_permitted=False,
        synthetic=False,
        subject_is_adult=True,
        language="en",
        declares=dict.fromkeys(
            (
                "not_scraped_personal_social_media",
                "no_minors",
                "not_private_communication",
                "licence_and_tos_permit_this_use",
                "not_behind_auth_or_paywall",
                "not_health_injury_or_treatment_content",
                "provenance_is_complete",
            ),
            True,
        ),
    )
    try:
        store.open_source(forbidden)
    except IngestionRefused as exc:
        print(f"  refused as expected: {exc}")
        print("  logged to logs/ingestion_refusals.log")
        return True
    print("  FAILED: a source outside the allow-list was accepted")
    return False


def verify(store: RawStore) -> bool:
    """Audit `data/raw/` against the Phase 7 acceptance gate."""
    ok = True
    try:
        sources = list(store.iter_all())
    except IngestionRefused as exc:
        print(f"  FAIL traceability: {exc}")
        return False

    if not sources:
        print("  FAIL: data/raw/ contains no sources")
        return False

    total = 0
    for provenance, records in sources:
        total += len(records)
        print(f"\n  source: {provenance.source_id}  ({len(records)} records)")
        print(f"    category   : {provenance.allowlist_category}")
        print(f"    licence    : {provenance.licence_or_consent_basis[:72]}...")
        print(f"    synthetic  : {provenance.synthetic}")
        print(f"    deidentified: {provenance.deidentified}  (Phase 8 sets this)")

        if provenance.record_count != len(records):
            print(
                f"    FAIL: provenance claims {provenance.record_count} records, "
                f"found {len(records)}"
            )
            ok = False

        coverage = metadata_coverage(records)
        print("    temporal/context coverage:")
        for name, fraction in coverage.items():
            print(f"      {name:<28} {fraction:6.1%}")

        # The gate wants temporal fields present where the source allows. This
        # generator controls timing entirely, so anything under 100% is a bug
        # in the generator rather than a property of the source.
        if provenance.synthetic and coverage["time_to_competition_days"] < 1.0:
            print("    FAIL: a synthetic source must set time_to_competition_days on every record")
            ok = False

        if records:
            ttr = type_token_ratio(records)
            sports = Counter(r.sport for r in records)
            print(f"    type-token ratio: {ttr:.4f}")
            print(f"    sports covered  : {len(sports)}")

    print(f"\n  total records across all sources: {total}")
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 7 ingestion gate")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--demo-refusal", action="store_true")
    args = parser.parse_args(argv)

    try:
        allowlist = load_allowlist()
    except AllowlistError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"allow-list v{allowlist.version}  default_action={allowlist.default_action}")
    print(f"permitted categories: {', '.join(allowlist.permitted_category_keys())}")

    try:
        store = RawStore(root=args.raw_root, allowlist=allowlist)
    except IngestionRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    ok = True

    if args.demo_refusal:
        _rule("Allow-list refusal demonstration")
        ok = demo_refusal(store) and ok

    if not args.verify_only:
        _rule(f"Ingesting A2 synthetic source (count={args.count}, seed={args.seed})")
        try:
            ingest_synthetic(store, args.count, args.seed)
        except IngestionRefused as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 2

    _rule("Verifying data/raw/ against the Phase 7 gate")
    ok = verify(store) and ok

    print()
    print("Phase 7 gate:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
