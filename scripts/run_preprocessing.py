#!/usr/bin/env python
"""The Phase 8 gate: clean, segment, and de-identify `data/raw/` into `data/interim/`.

    python scripts/run_preprocessing.py                # process + measure (default)
    python scripts/run_preprocessing.py --fixture-only # score the de-identifier, write nothing
    python scripts/run_preprocessing.py --verify-only  # audit data/interim/, write nothing
    python scripts/run_preprocessing.py --show-failures  # print every non-exact fixture case

Offline and free by design, matching `scripts/run_ingestion.py`: no network
call, no API key, deterministic. A reviewer must be able to rebuild
`data/interim/` from a fresh clone.

**Two gates, and the difference between them matters.**

The corpus check confirms the pipeline runs clean over `data/raw/`. It is
*not* a recall measurement: `synth_precomp_v1` contains no personal names by
design, so the de-identifier has nothing to find and "no identifiers remain" is
a true and worthless statement about it (OPEN-013).

The fixture score against `tests/fixtures/deid_cases.jsonl` is the gate that
measures anything. It is reported per difficulty band, with precision as well
as recall, because a de-identifier that blanks everything scores perfect recall
and destroys the corpus.

Exit codes: 0 gate passed, 1 gate failed, 2 configuration or policy error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion import IngestionRefused, RawStore  # noqa: E402
from src.preprocessing import (  # noqa: E402
    FixtureScore,
    InterimStore,
    PreprocessResult,
    deidentify,
    preprocess_all,
    score_fixture,
)

#: Minimum fixture scores for the gate to pass. Set from the measured baseline
#: at the end of Phase 8 so that a later change which *degrades* redaction
#: fails loudly. They are floors, not targets -- `tests/fixtures/README.md`
#: warns against tuning until the fixture is overfitted, and 34 cases cannot
#: certify a PII pipeline in any case.
MIN_RECALL = 0.90
MIN_PRECISION = 0.90
MAX_LEAK_RATE = 0.05
MIN_NEGATIVES_PRESERVED = 1.0  # over-redaction is a hard failure, not a soft one

#: A small held-out probe, deliberately NOT in `tests/fixtures/deid_cases.jsonl`
#: and deliberately not consulted while writing the rules.
#:
#: The fixture is the gate, and a gate you tune against stops being evidence.
#: These cases use different names, different sports, and different sentence
#: shapes, and they exist to answer one question: does the cascade generalise,
#: or has it learned this fixture? A large gap between the two scores means the
#: fixture number should not be believed.
GENERALISATION_PROBE: tuple[tuple[str, str], ...] = (
    (
        "Priya Anand told me the plan changes tomorrow.",
        "[ATHLETE] told me the plan changes tomorrow.",
    ),
    ("I have never beaten Kowalczyk on clay.", "I have never beaten [OPPONENT] on clay."),
    (
        "We drove to Bergholt for the altitude block.",
        "We drove to [LOCATION] for the altitude block.",
    ),
    ("The Thornbury Classic decides my whole season.", "The [EVENT] decides my whole season."),
    ("Eastvale Rovers gave me my first contract.", "[TEAM] gave me my first contract."),
    (
        "Email the entry to h.varga@example-club.test tonight.",
        "Email the entry to [CONTACT] tonight.",
    ),
    ("My handle is @coldstartkid these days.", "My handle is [HANDLE] these days."),
    ("I wore number 12 for six seasons.", "I wore [ID] for six seasons."),
    ("Nothing is going right and I cannot settle.", "Nothing is going right and I cannot settle."),
    (
        "The heats are on Friday and I feel sick about it.",
        "The heats are on Friday and I feel sick about it.",
    ),
)


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _pct(value: float) -> str:
    return f"{value:6.1%}"


# ---------------------------------------------------------------------------
# The fixture gate
# ---------------------------------------------------------------------------


def report_fixture(score: FixtureScore, *, show_failures: bool) -> bool:
    print(f"  cases: {len(score.cases)}   (tests/fixtures/deid_cases.jsonl)")
    print(f"    precision        {_pct(score.precision)}   (over-redaction check)")
    print(f"    recall           {_pct(score.recall)}")
    print(f"    F1               {_pct(score.f1)}")
    print(f"    exact match      {_pct(score.exact_match_rate)}")
    print(f"    leak rate        {_pct(score.leak_rate)}   <- the privacy number")
    print(
        f"    negatives intact {score.negatives_preserved}/{len(score.negatives)}"
        "   (must be all: blanking everything scores perfect recall)"
    )

    print("\n  by difficulty band:")
    print(f"    {'band':<8} {'n':>3}  {'precision':>9} {'recall':>8} {'exact':>8} {'leak':>7}")
    for band, group in score.by("difficulty").items():
        print(
            f"    {band:<8} {len(group.cases):>3}  {_pct(group.precision):>9} "
            f"{_pct(group.recall):>8} {_pct(group.exact_match_rate):>8} "
            f"{_pct(group.leak_rate):>7}"
        )

    print("\n  by category:")
    for category, group in score.by("category").items():
        print(
            f"    {category:<18} n={len(group.cases):<3} recall {_pct(group.recall)} "
            f"exact {_pct(group.exact_match_rate)}"
        )

    failures = [c for c in score.cases if not c.exact_match]
    if failures:
        print(f"\n  {len(failures)} case(s) did not match exactly:")
        for case in failures:
            marker = "LEAKS" if case.leaks else "typing/format only"
            print(f"    - {case.case_id} ({case.difficulty}, {marker})")
            if show_failures:
                print(f"        in  : {case.text}")
                print(f"        exp : {case.expected}")
                print(f"        got : {case.produced}")
                if case.leaked:
                    print(f"        leaked: {', '.join(case.leaked)}")

    ok = True
    if score.recall < MIN_RECALL:
        print(f"  FAIL: recall {score.recall:.3f} below floor {MIN_RECALL}")
        ok = False
    if score.precision < MIN_PRECISION:
        print(f"  FAIL: precision {score.precision:.3f} below floor {MIN_PRECISION}")
        ok = False
    if score.leak_rate > MAX_LEAK_RATE:
        print(f"  FAIL: leak rate {score.leak_rate:.3f} above ceiling {MAX_LEAK_RATE}")
        ok = False
    if (
        score.negatives
        and score.negatives_preserved / len(score.negatives) < MIN_NEGATIVES_PRESERVED
    ):
        print("  FAIL: a negative case was over-redacted")
        ok = False
    return ok


def report_probe() -> bool:
    """Score the held-out probe and compare it with the fixture.

    Reported, never gated. A probe that gates becomes a second fixture the next
    person tunes against, and then there is no held-out set left.
    """
    exact = 0
    misses: list[tuple[str, str, str]] = []
    for text, expected in GENERALISATION_PROBE:
        produced = deidentify(text)
        if produced == expected:
            exact += 1
        else:
            misses.append((text, expected, produced))

    rate = exact / len(GENERALISATION_PROBE)
    print(f"  held-out probe: {exact}/{len(GENERALISATION_PROBE)} exact ({rate:.0%})")
    for text, expected, produced in misses:
        print(f"    - in  : {text}")
        print(f"      exp : {expected}")
        print(f"      got : {produced}")
    if misses:
        print(
            "\n  These are not gate failures. They are the honest generalisation gap:\n"
            "  the fixture score is an upper bound on real-text performance, and the\n"
            "  distance between the two numbers is what the paper should quote."
        )
    return True


# ---------------------------------------------------------------------------
# The corpus side
# ---------------------------------------------------------------------------


def report_results(results: list[PreprocessResult]) -> bool:
    ok = True
    for result in results:
        print(f"\n  source: {result.source_id}")
        print(f"    raw records         : {result.raw_records}")
        print(f"    utterances written  : {result.utterances_written}")
        print(f"    normalisation changed: {result.records_normalised} records")
        print(f"    dropped             : {result.dropped_total}")
        for reason, count in result.dropped.items():
            if count:
                print(f"      {reason:<32} {count}")
        print(f"    health clauses removed: {result.health_clauses_removed}")
        if result.replacements:
            print("    placeholders written:")
            for placeholder, count in sorted(result.replacements.items()):
                print(f"      {placeholder:<18} {count}")
        else:
            print("    placeholders written: 0")
            print(
                "      NOTE: zero is expected for the A2 synthetic corpus, which plants\n"
                "      no personal names. This line measures nothing about recall --\n"
                "      the fixture gate above does (OPEN-013)."
            )
        print(f"    utterances flagged for manual audit: {result.records_with_residual_flags}")

        if result.offset_violations:
            print(f"    FAIL: {len(result.offset_violations)} offset violation(s)")
            for violation in result.offset_violations[:5]:
                print(f"      {violation}")
            ok = False
        if result.utterances_written == 0 and result.raw_records:
            print("    FAIL: a source with raw records produced no utterances")
            ok = False
    return ok


def verify_interim(store: InterimStore) -> bool:
    """Audit `data/interim/` against the Phase 8 gate."""
    ok = True
    try:
        sources = list(store.iter_all())
    except IngestionRefused as exc:
        print(f"  FAIL traceability: {exc}")
        return False

    if not sources:
        print("  FAIL: data/interim/ contains no sources")
        return False

    for provenance, records in sources:
        print(f"\n  source: {provenance.source_id}  ({len(records)} utterances)")
        print(f"    category    : {provenance.allowlist_category}")
        print(f"    deidentified: {provenance.deidentified}")
        if not provenance.deidentified:
            print("    FAIL: interim provenance must declare deidentified=true")
            ok = False
        if provenance.record_count != len(records):
            print(
                f"    FAIL: provenance claims {provenance.record_count} records, "
                f"found {len(records)}"
            )
            ok = False
        not_deidentified = [r.record_id for r in records if not r.deidentified]
        if not_deidentified:
            print(f"    FAIL: {len(not_deidentified)} record(s) not de-identified")
            ok = False
        orphans = [r.record_id for r in records if not r.parent_record_id]
        if orphans:
            print(f"    FAIL: {len(orphans)} utterance(s) with no parent record")
            ok = False
        flagged = sum(1 for r in records if r.deid.get("residual_flags"))
        print(f"    utterances carrying residual-risk flags: {flagged}")
    return ok


def write_audit_sample(results: list[PreprocessResult], path: Path) -> None:
    """Write the stratified manual-audit sample `docs/ethics.md` sec.5.2 requires."""
    lines = [
        "# Phase 8 - de-identification manual audit sample",
        "",
        "Stratified by sport × time-to-competition band. Records carrying residual-risk",
        "flags are drawn first: the automated cascade already handled the rest, so a",
        "sample that ignores the pipeline's own uncertainty wastes the reader's attention.",
        "",
        "**How to use this.** Read each passage and mark anything that could identify a",
        "person. Log failures here - `docs/ethics.md` §5.2 requires failures to be logged,",
        "and an audit with no written outcome is an audit nobody can check.",
        "",
    ]
    for result in results:
        lines.append(f"## {result.source_id}")
        lines.append("")
        for finding in result.sample:
            flags = ", ".join(finding.flags) if finding.flags else "none"
            lines.append(f"- **{finding.record_id}** _(stratum: {finding.stratum})_")
            lines.append(f"  - text: {finding.text}")
            lines.append(f"  - automated flags: {flags}")
            lines.append("  - auditor verdict: _(unreviewed)_")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(REPO_ROOT)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 8 preprocessing gate")
    parser.add_argument("--raw-root", type=Path, default=None)
    parser.add_argument("--interim-root", type=Path, default=None)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument("--show-failures", action="store_true")
    parser.add_argument(
        "--audit-sample",
        type=Path,
        default=REPO_ROOT / "reports" / "deid_audit_sample.md",
    )
    args = parser.parse_args(argv)

    ok = True

    _rule("De-identification fixture gate (the measurement that counts)")
    try:
        score = score_fixture()
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ok = report_fixture(score, show_failures=args.show_failures) and ok

    _rule("Held-out generalisation probe (reported, not gated)")
    report_probe()

    if args.fixture_only:
        print()
        print("Phase 8 gate (fixture only):", "PASSED" if ok else "FAILED")
        return 0 if ok else 1

    try:
        raw_store = RawStore(root=args.raw_root)
        interim_store = InterimStore(root=args.interim_root)
    except IngestionRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    results: list[PreprocessResult] = []
    if not args.verify_only:
        _rule("Preprocessing data/raw/ -> data/interim/")
        try:
            results = preprocess_all(raw_store=raw_store, interim_store=interim_store)
        except IngestionRefused as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            return 2
        ok = report_results(results) and ok

        _rule("Manual audit sample (docs/ethics.md sec.5.2)")
        write_audit_sample(results, args.audit_sample)

    _rule("Verifying data/interim/ against the Phase 8 gate")
    ok = verify_interim(interim_store) and ok

    print()
    print("Phase 8 gate:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
