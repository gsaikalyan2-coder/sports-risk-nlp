"""Dependency audit across all three requirement layers, and what each can prove.

`handover_phase_20.txt` C4: "the dependency scan must cover
`requirements-base.txt`, `requirements-ml.txt` AND `requirements.lock.txt`.
Scanning only the first reports on the light image and says nothing about the
training image."

Working through that produced a finding sharper than the instruction. The three
files are not three views of one dependency set; they differ in KIND:

* `requirements-base.txt` and `requirements-ml.txt` state FLOORS (`torch>=2.2`)
  and occasional ceilings. A floor is not a version. There is no such thing as
  auditing `torch>=2.2` -- the answer depends entirely on what pip resolves on
  the day of the build, which is a different answer every day.
* `requirements.lock.txt` states 180 exact pins and is the only auditable
  surface in the repository.
* `Dockerfile` installs `requirements-base.txt` and `Dockerfile.train` installs
  `requirements-ml.txt`. **Neither image installs the lock file.** So the one
  file that can be audited is the one file neither image uses, and the images
  that ship are built from floors that resolve afresh at every build.

That gap is a reproducibility finding as much as a security one, which is why it
is handed forward to Phase 22 rather than patched here.

Advisories are injected, never fetched, so the tests are offline and
deterministic. `scripts/run_security_audit.py` owns the network call.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.security.audit import Finding, ScannerResult, Severity

_REQ_RE = re.compile(r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?P<spec>(?:[<>=!~]=?[^,;#\s]+\s*,?\s*)*)")


@dataclass(frozen=True)
class Requirement:
    """One line of a requirements file, classified by whether it can be audited."""

    name: str
    spec: str
    source: str

    @property
    def pinned_version(self) -> str | None:
        """The exact version, if this line states one. Local versions stripped.

        `torch==2.13.0+cpu` audits as `2.13.0`: the `+cpu` local segment marks a
        build variant of the same upstream source, and advisory databases index
        the upstream version.
        """
        match = re.fullmatch(r"==\s*([^,\s]+)", self.spec.strip())
        if not match:
            return None
        return match.group(1).split("+")[0]

    @property
    def auditable(self) -> bool:
        return self.pinned_version is not None


@dataclass(frozen=True)
class DependencyAudit:
    requirements: tuple[Requirement, ...]

    @property
    def pinned(self) -> tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if r.auditable)

    @property
    def unpinned(self) -> tuple[Requirement, ...]:
        return tuple(r for r in self.requirements if not r.auditable)


def parse_requirements(path: Path, *, source: str | None = None) -> list[Requirement]:
    """Parse one requirements file. `-r` includes are NOT followed.

    Deliberately: following them would silently merge the three layers back into
    one set and hide exactly the distinction this module exists to report.
    """
    source = source or path.name
    out: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].split(";", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _REQ_RE.match(line)
        if not match:
            continue
        out.append(
            Requirement(
                name=match.group("name").lower().replace("_", "-"),
                spec=match.group("spec").strip(),
                source=source,
            )
        )
    return out


def audit_requirements(
    files: Sequence[Path],
    advisories: Mapping[tuple[str, str], Sequence[str]],
    *,
    installed_by: Mapping[str, str] | None = None,
    lookup_failures: Sequence[str] = (),
    looked_up: bool = True,
) -> tuple[DependencyAudit, ScannerResult]:
    """Join pinned requirements against a supplied advisory table.

    `advisories` maps `(package, version)` to advisory ids. `installed_by` maps
    a requirements filename to the image that installs it, purely so the report
    can say which shipped artefact each result describes.
    """
    reqs: list[Requirement] = []
    for path in files:
        reqs.extend(parse_requirements(path))
    audit = DependencyAudit(tuple(reqs))
    installed_by = dict(installed_by or {})

    findings: list[Finding] = []
    for req in audit.pinned:
        ids = advisories.get((req.name, req.pinned_version or ""), ())
        if ids:
            findings.append(
                Finding(
                    scanner="dependencies",
                    severity=Severity.MEDIUM,
                    locator=f"{req.source}:{req.name}=={req.pinned_version}",
                    summary=(
                        f"a published advisory affects this pinned version ({', '.join(ids)})"
                    ),
                    fix=(
                        "check for a fixed release; if none exists, record whether the "
                        "vulnerable code path is reachable from this project"
                    ),
                )
            )

    by_source: dict[str, int] = {}
    for req in audit.unpinned:
        by_source[req.source] = by_source.get(req.source, 0) + 1
    for source, count in sorted(by_source.items()):
        image = installed_by.get(source)
        findings.append(
            Finding(
                scanner="dependencies",
                severity=Severity.MEDIUM,
                locator=source,
                summary=(
                    f"{count} requirement(s) state a floor or range rather than a version, so "
                    "this file cannot be audited at all -- what gets installed is decided by "
                    "pip at build time and differs between builds"
                    + (f", and this is the file `{image}` installs" if image else "")
                ),
                fix=(
                    "Phase 22 (reproducibility packaging): have the images install "
                    "`requirements.lock.txt`, or generate a per-layer lock, so the audited "
                    "versions and the shipped versions are the same versions"
                ),
            )
        )

    covered = ", ".join(sorted({r.source for r in audit.pinned})) or "none"
    return audit, ScannerResult(
        name="Dependency advisory audit (src/security/deps.py)",
        what_it_covers=(
            f"{len(audit.pinned)} exactly-pinned requirement(s) from {covered}, each queried "
            "against the PyPI advisory service by name and upstream version, with local "
            "version segments such as `+cpu` normalised away."
        ),
        does_not_cover=(
            f"{len(audit.unpinned)} floor-or-range requirement(s) from "
            f"{', '.join(sorted(by_source)) or 'none'} -- a range has no version to look up, so "
            "nothing here describes what `docker compose build` will actually install today. It "
            "also does not cover system packages from the images' `apt-get` layer, the base "
            "`python:3.11-slim` image itself, JavaScript or wheel-bundled native code, "
            "advisories published after the scan date, or whether a flagged code path is "
            "reachable from this project."
        ),
        findings=tuple(findings),
        proven=looked_up and not lookup_failures,
        notes=tuple(
            [
                f"Parsed {len(audit.requirements)} requirement line(s) across {len(files)} "
                f"file(s); {len(audit.pinned)} auditable, {len(audit.unpinned)} not.",
            ]
            + (
                []
                if looked_up
                else [
                    "No advisory lookup was performed on this run (offline mode). The absence "
                    "of advisory findings below is the absence of a query, not the absence of "
                    "advisories."
                ]
            )
            + (
                [
                    f"{len(lookup_failures)} advisory lookup(s) failed and those packages were "
                    "NOT checked: " + ", ".join(sorted(lookup_failures)) + "."
                ]
                if lookup_failures
                else []
            )
        ),
    )
