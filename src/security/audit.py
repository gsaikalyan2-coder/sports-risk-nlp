"""Report primitives shared by every scanner in this package.

The one idea worth carrying out of this module: a finding and the coverage
statement of the tool that produced it are the SAME object. They cannot drift,
because you cannot build the first without the second.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.dashboard.view import assert_no_forbidden_language


class Severity(Enum):
    """Ordered so that `sorted(findings, key=...)` puts the worst first.

    Plain `Enum`, not `str, Enum`: nothing compares a severity to a bare string,
    every render path goes through `.value`, and `str, Enum` trips ruff's UP042
    on this project's Python 3.11 target.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}[self.value]


def shape(text: str) -> str:
    """Return the character-class silhouette of `text`, never its characters.

    `docs/ethics.md` sec.3.3 permits verbatim quotation of the A2 synthetic
    source and nothing else, and a scanner's proudest output is the matched
    line. So no scanner in this package ever puts a matched string into a
    committed document; it puts this instead.

    >>> shape("k.mensah_07")
    'a.aaaaaa_99'

    Letters keep their case class (so a reader can still tell `AWS` from `aws`),
    digits become `9`, everything else is passed through as punctuation. The
    result is enough to recognise the KIND of thing matched and never enough to
    reconstruct it. A 40-character match is truncated, because a full-length
    silhouette of a high-entropy string is itself close to an identifier.
    """
    out = []
    for ch in text[:40]:
        if ch.isdigit():
            out.append("9")
        elif ch.isalpha():
            out.append("A" if ch.isupper() else "a")
        else:
            out.append(ch)
    return "".join(out) + ("..." if len(text) > 40 else "")


@dataclass(frozen=True)
class Finding:
    """One thing a scanner found, with the evidence already de-fanged."""

    scanner: str
    severity: Severity
    locator: str
    summary: str
    evidence: str = ""
    fix: str = ""

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a Finding with no summary is a row nobody can act on")
        assert_no_forbidden_language(f"{self.summary} {self.evidence} {self.fix}")


@dataclass(frozen=True)
class ScannerResult:
    """What one tool ran over, what it found, and what it CANNOT see.

    `does_not_cover` is mandatory and validated. That is the whole point of this
    class. A clean findings list is a claim about the scanner's scope, and a
    scope nobody wrote down is a scope nobody checked -- exactly the shape of
    OPEN-034, where a gate certified a claim its own evidence contradicted.
    """

    name: str
    what_it_covers: str
    does_not_cover: str
    findings: tuple[Finding, ...] = ()
    proven: bool = True
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for label, value in (
            ("what_it_covers", self.what_it_covers),
            ("does_not_cover", self.does_not_cover),
        ):
            if len(value.strip()) < 20:
                raise ValueError(
                    f"ScannerResult({self.name!r}).{label} is empty or perfunctory. "
                    "A findings table with no coverage statement is the Phase 18 "
                    "defect: it invites the reader to over-read a clean result. "
                    "Write the sentence that stops them."
                )
        assert_no_forbidden_language(f"{self.what_it_covers} {self.does_not_cover}")

    @property
    def clean(self) -> bool:
        """True only if nothing was found AND the scanner proved it can find.

        `proven=False` means the scanner never demonstrated, on this run, that
        its detectors fire. An unproven scanner reporting nothing is reporting
        nothing about the repository.
        """
        return self.proven and not self.findings

    def worst(self) -> Severity | None:
        return min((f.severity for f in self.findings), key=lambda s: s.rank, default=None)


@dataclass
class AuditReport:
    """Every scanner's result, plus the gate verdict over all of them."""

    scanners: list[ScannerResult] = field(default_factory=list)

    def add(self, result: ScannerResult) -> ScannerResult:
        self.scanners.append(result)
        return result

    @property
    def findings(self) -> list[Finding]:
        out = [f for s in self.scanners for f in s.findings]
        return sorted(out, key=lambda f: (f.severity.rank, f.scanner, f.locator))

    @property
    def unproven(self) -> list[ScannerResult]:
        return [s for s in self.scanners if not s.proven]

    def gate(self) -> tuple[bool, list[str]]:
        """Phase 21's gate, strengthened. Returns (passed, reasons-it-failed).

        The plan's gate is "no secrets in git history; no high-severity
        dependency issues; released data PII-clean". Three additions:

        1. An UNPROVEN scanner fails the gate even with zero findings. This is
           the predicted defect, refused mechanically.
        2. Any HIGH finding fails, wherever it came from -- not only from the
           dependency scan.
        3. A scanner with no coverage statement cannot exist, so the gate does
           not need to check for one.
        """
        reasons: list[str] = []
        for scanner in self.unproven:
            reasons.append(
                f"{scanner.name} did not prove its detectors fire on this run; "
                "its result is not evidence of anything"
            )
        for finding in self.findings:
            if finding.severity is Severity.HIGH:
                reasons.append(f"HIGH: {finding.scanner} -- {finding.locator}: {finding.summary}")
        return (not reasons, reasons)


def render_markdown(report: AuditReport, *, title: str = "Security audit") -> str:
    """Render the report, coverage statement mandatory and adjacent."""
    lines = [f"## {title}", ""]
    passed, reasons = report.gate()
    lines.append(f"**Gate:** {'PASS' if passed else 'FAIL'}")
    lines.append("")
    if reasons:
        for reason in reasons:
            lines.append(f"- {reason}")
        lines.append("")

    for scanner in report.scanners:
        lines.append(f"### {scanner.name}")
        lines.append("")
        lines.append(f"- **Covers:** {scanner.what_it_covers}")
        lines.append(f"- **Does NOT cover:** {scanner.does_not_cover}")
        lines.append(f"- **Detectors proven on this run:** {'yes' if scanner.proven else 'NO'}")
        lines.append("")
        for note in scanner.notes:
            lines.append(f"> {note}")
        if scanner.notes:
            lines.append("")
        if not scanner.findings:
            verdict = (
                "No findings."
                if scanner.proven
                else "No findings, but the detectors were not proven -- read this as "
                "'the scanner said nothing', not as 'there is nothing'."
            )
            lines.append(verdict)
            lines.append("")
            continue
        lines.append("| severity | locator | finding | evidence (silhouette only) | fix |")
        lines.append("|---|---|---|---|---|")
        for finding in sorted(scanner.findings, key=lambda f: f.severity.rank):
            cells = [
                finding.severity.value,
                f"`{finding.locator}`",
                finding.summary,
                f"`{finding.evidence}`" if finding.evidence else "--",
                finding.fix or "--",
            ]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        lines.append("")

    rendered = "\n".join(lines)
    assert_no_forbidden_language(rendered)
    return rendered
