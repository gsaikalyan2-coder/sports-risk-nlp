"""Phase 21 runner - a thin shell over `src/security/`.

    python scripts/run_security_audit.py                # offline; no advisory lookup
    python scripts/run_security_audit.py --online       # query the PyPI advisory service
    python scripts/run_security_audit.py --out docs/security_generated.md

Everything worth testing lives in `src/security/`. This file owns exactly the
three things a test must never do: shell out to git, touch the network, and
write to disk.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.security import (  # noqa: E402
    AuditReport,
    audit_baseline,
    audit_requirements,
    render_markdown,
    run_sweep,
)

REQUIREMENT_FILES = (
    "requirements-base.txt",
    "requirements-ml.txt",
    "requirements.lock.txt",
)

#: Which shipped artefact installs which file. `Dockerfile.train` builds
#: `FROM sports-risk-nlp-base:latest`, so the training image carries both.
INSTALLED_BY = {
    "requirements-base.txt": "Dockerfile (light image, and the base of the train image)",
    "requirements-ml.txt": "Dockerfile.train",
    "requirements.lock.txt": "no image -- host installs only",
}


def git_tracked(repo: Path) -> list[str]:
    """`git ls-files`: exactly the set of files a reviewer receives on clone."""
    out = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line.strip()]


def pypi_advisories(
    pairs: list[tuple[str, str]],
) -> tuple[dict[tuple[str, str], list[str]], list[str]]:
    """Query PyPI's advisory service for each (name, version).

    PyPI is used rather than OSV because it is the index this project already
    installs from, so no additional network destination is introduced. The
    trade-off is recorded in `docs/security.md`: PyPI returns advisory ids and
    aliases but not severity scores, so severities in this report are assigned
    by a human reading the advisory, not by the tool.
    """

    def one(pair: tuple[str, str]) -> tuple[tuple[str, str], list[str] | None]:
        name, version = pair
        url = f"https://pypi.org/pypi/{name}/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=30) as handle:
                data = json.load(handle)
        except (urllib.error.URLError, OSError, ValueError):
            # A failed lookup is NOT "no advisories". Reported, not swallowed:
            # a silently-degraded scan producing a clean report is the exact
            # defect this phase was told to expect.
            return pair, None
        return pair, [
            v.get("id", "?") for v in data.get("vulnerabilities", []) if not v.get("withdrawn")
        ]

    advisories: dict[tuple[str, str], list[str]] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        for (name, version), ids in pool.map(one, pairs):
            if ids is None:
                failures.append(f"{name}=={version}")
            elif ids:
                advisories[(name, version)] = ids
    return advisories, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="query the PyPI advisory service")
    parser.add_argument("--out", type=Path, default=None, help="write the rendered report here")
    args = parser.parse_args()

    report = AuditReport()

    tracked = git_tracked(REPO)
    report.add(run_sweep(REPO, tracked))

    baseline_path = REPO / ".secrets.baseline"
    if baseline_path.exists():
        _, baseline_result = audit_baseline(baseline_path)
        report.add(baseline_result)

    files = [REPO / name for name in REQUIREMENT_FILES if (REPO / name).exists()]
    advisories: dict[tuple[str, str], list[str]] = {}
    failures: list[str] = []
    if args.online:
        from src.security.deps import parse_requirements

        pairs = [
            (r.name, r.pinned_version)
            for path in files
            for r in parse_requirements(path)
            if r.pinned_version
        ]
        advisories, failures = pypi_advisories(pairs)
    _, dep_result = audit_requirements(
        files,
        advisories,
        installed_by=INSTALLED_BY,
        lookup_failures=failures,
        looked_up=args.online,
    )
    report.add(dep_result)

    rendered = render_markdown(report, title="Security audit (generated)")
    if args.out:
        args.out.write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(rendered)

    passed, reasons = report.gate()
    if not passed:
        print("\nGATE FAILED:", file=sys.stderr)
        for reason in reasons:
            print(f"  - {reason}", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
