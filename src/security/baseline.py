"""Interrogating `.secrets.baseline` before believing a clean detect-secrets run.

A baseline is a list of findings someone already decided to ignore. Running
`detect-secrets --baseline .secrets.baseline` and reporting "clean" is therefore
not a statement about the repository; it is a statement about the repository
MINUS whatever is in that file, evaluated by whatever filters that file
configures. `handover_phase_20.txt` C4 names this as OPEN-034 in a new costume,
and it is: a gate certifying a claim its own evidence does not support.

Three things this module checks that reading the file casually does not:

1. **Every suppressed entry's audit verdict.** detect-secrets records
   `is_secret: true` for "a human looked at this and it IS a secret" and
   `is_secret: false` for "reviewed, false positive". An entry sitting in a
   baseline marked `is_secret: true` is a *confirmed* secret being suppressed.
   That is the opposite of what a baseline is for and it fails the gate.

2. **Path-separator agreement.** detect-secrets matches a baseline entry to a
   new finding by filename STRING. A baseline generated on Windows records
   `reports\\baselines.json`; the same scan inside the Linux container reports
   `reports/baselines.json`. The strings differ, so on Linux the entries suppress
   nothing and the hook fails on findings it was supposed to have absolved --
   while on Windows the baseline's own `should_exclude_file` pattern, written
   with forward slashes, matches nothing and the directories it claims to
   exclude are scanned after all. The file is platform-locked in both
   directions, and neither direction is visible from a green hook run.

3. **Staleness against the tree it claims to describe.** A baseline has a
   `generated_at`; the pre-commit hook only ever scans files in the current
   commit. Files added since have never been scanned against it as a whole.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.security.audit import Finding, ScannerResult, Severity


@dataclass(frozen=True)
class BaselineAudit:
    """The facts about a baseline that a green hook run does not show."""

    generated_at: str
    suppressed_total: int
    files_suppressed: tuple[str, ...]
    confirmed_secret_entries: tuple[tuple[str, int], ...]
    windows_separator_entries: tuple[str, ...]
    exclude_patterns: tuple[str, ...]
    plugin_count: int


def audit_baseline(path: Path) -> tuple[BaselineAudit, ScannerResult]:
    """Read a detect-secrets baseline and report what it suppresses and why."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results: dict[str, list[dict]] = data.get("results", {})

    suppressed_total = sum(len(v) for v in results.values())
    confirmed = tuple(
        (filename, entry.get("line_number", -1))
        for filename, entries in results.items()
        for entry in entries
        if entry.get("is_secret") is True
    )
    windows = tuple(sorted(f for f in results if "\\" in f))
    excludes = tuple(
        pattern
        for filt in data.get("filters_used", [])
        if filt.get("path", "").endswith("regex.should_exclude_file")
        for pattern in _as_list(filt.get("pattern"))
    )

    audit = BaselineAudit(
        generated_at=str(data.get("generated_at", "unknown")),
        suppressed_total=suppressed_total,
        files_suppressed=tuple(sorted(results)),
        confirmed_secret_entries=confirmed,
        windows_separator_entries=windows,
        exclude_patterns=excludes,
        plugin_count=len(data.get("plugins_used", [])),
    )

    findings: list[Finding] = []
    if confirmed:
        findings.append(
            Finding(
                scanner="secrets-baseline",
                severity=Severity.HIGH,
                locator=path.name,
                summary=(
                    f"{len(confirmed)} baseline entr(y/ies) are marked `is_secret: true` -- "
                    "the audit verdict for 'a human looked at this and it IS a secret'. A "
                    "baseline is for reviewed FALSE POSITIVES; an entry marked true is a "
                    "confirmed secret being suppressed, and every subsequent clean hook run "
                    "silently inherits that suppression"
                ),
                evidence=", ".join(f"{f}:{ln}" for f, ln in confirmed),
                fix=(
                    "re-audit the entries (`detect-secrets audit .secrets.baseline`) and record "
                    "`is_secret: false` for each one confirmed to be a non-secret, or remove the "
                    "value from the file if it is a secret"
                ),
            )
        )
    if windows:
        findings.append(
            Finding(
                scanner="secrets-baseline",
                severity=Severity.HIGH,
                locator=path.name,
                summary=(
                    "baseline entries use Windows path separators, so they are matched by "
                    "string against POSIX filenames inside the container and in CI and never "
                    "match. The suppressions do not apply where the gate actually runs, and "
                    "the baseline's own forward-slash exclude patterns do not apply where it "
                    "was generated. A green hook on one platform proves nothing about the other"
                ),
                evidence=", ".join(windows),
                fix=(
                    "regenerate the baseline inside the container "
                    "(`docker compose run --rm app detect-secrets scan > .secrets.baseline`) so "
                    "paths are POSIX, and add a test that fails if any results key contains a backslash"
                ),
            )
        )
    return audit, ScannerResult(
        name="detect-secrets baseline interrogation (src/security/baseline.py)",
        what_it_covers=(
            f"The contents of `{path.name}` itself: how many findings it suppresses, each "
            "entry's recorded audit verdict, whether its filenames and exclude patterns use "
            "the separators of the platform the gate runs on, and when it was generated."
        ),
        does_not_cover=(
            "Whether the suppressed values are in fact harmless -- that judgement is made by a "
            "human and recorded in `docs/security.md` beside each entry, not by this code. It "
            "also does not run detect-secrets, does not scan the tree, and says nothing about "
            "files the baseline's exclude patterns remove from scope before scanning begins "
            f"(currently: {', '.join(excludes) or 'none'})."
        ),
        findings=tuple(findings),
        proven=True,
        notes=(
            f"Baseline generated {audit.generated_at}; {audit.plugin_count} detector plugins "
            f"configured; {suppressed_total} finding(s) suppressed across "
            f"{len(audit.files_suppressed)} file(s).",
        ),
    )


def files_added_since(generated_at: str, paths_with_dates: dict[str, str]) -> list[str]:
    """Tracked paths first committed after the baseline was generated.

    Passed in rather than shelled out, for the same reason `iter_release_paths`
    takes its file list: the test suite must not need a git repository.
    """
    try:
        cutoff = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return sorted(paths_with_dates)
    out = []
    for path, iso in paths_with_dates.items():
        try:
            when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            out.append(path)
            continue
        if when > cutoff:
            out.append(path)
    return sorted(out)


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]
