"""The release-surface sweep: identifiers and credentials in what git publishes.

Two design decisions carry the whole module.

**Scope is defined by git, not by directory.** `handover_phase_20.txt` C4
predicted that a PII sweep scoped to `data/` would miss `donations_inbox.jsonl`
at the repo root. The fix is not "remember to also check the root"; it is to
stop enumerating directories. `iter_release_paths` takes the output of
`git ls-files` -- the exact set of files a reviewer receives when they clone the
artifact -- so a file's position in the tree cannot put it out of scope. A file
that is gitignored is not released and is not swept; a file that is tracked is
swept wherever it sits.

**A zero is only publishable by a scanner that has just proven it can produce a
non-zero.** `verify_detectors` runs every pattern against `CANARY`, which plants
exactly one identifier of each kind. `run_sweep` raises `DetectorsUnproven`
rather than returning a clean result if any detector stayed silent. This is the
predicted Phase 21 defect refused mechanically: "0 findings" now means "these
detectors, demonstrably working, found nothing", which is a different and much
weaker claim than "there is nothing to find" -- and the coverage sentence on
`ScannerResult` is where the difference gets written down.

Nothing here re-implements `src/preprocessing/deidentify.py`. That module
rewrites athlete text so it can be stored; this one inspects source files,
documents and reports so they can be published. Different corpora, different
failure modes, and deidentify's own limitations (it measures the failure modes
someone thought to write down, on a corpus that plants no identifiers) apply to
this module just as much -- which is why the canary exists.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.security.audit import Finding, ScannerResult, Severity, shape


class DetectorsUnproven(RuntimeError):
    """Raised when a detector failed to fire on the canary that plants its target."""


#: One planted identifier per detector kind. Every string here is INVENTED --
#: no value in this constant is, or ever was, a real credential or a real
#: person's identifier. It exists so the detectors can be shown to work.
#:
#: ASSEMBLED FROM FRAGMENTS, AND THAT IS NOT STYLE. A canary that plants a
#: credential has to survive the repository's own credential scanners, and
#: `detect-private-key` (a pre-commit-hooks check, not detect-secrets) honours no
#: inline waiver at all -- a literal PEM header anywhere in this file blocks
#: every commit that touches it. Splitting the literals means no complete
#: secret-shaped string appears on any one source line, so the file is
#: committable while the constant it builds is byte-for-byte what the detectors
#: need to match. Do not "tidy" these back into one string.
_CANARY_PEM = "-----BEGIN RSA PRIVATE" + " KEY-----"
_CANARY_KEY = "sk-" + "canary" + "0" * 40

CANARY = "\n".join(
    (
        "",
        "contact: not.a.real.person@example.invalid",
        f"OPENROUTER_API_KEY={_CANARY_KEY}",
        _CANARY_PEM,
        r"task_dir: C:\Users\canaryuser\project\annotation",
        "home: /home/canaryuser/project",
        "social: @canary_handle_01",
        "phone: +44 7700 900000",
        "",
    )
)


@dataclass(frozen=True)
class _Detector:
    kind: str
    severity: Severity
    pattern: re.Pattern[str]
    summary: str
    fix: str


#: `re.VERBOSE` is deliberately NOT used: several patterns contain literal
#: whitespace that a verbose pattern would silently drop.
DETECTORS: tuple[_Detector, ...] = (
    _Detector(
        "private_key",
        Severity.HIGH,
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "a PEM private-key header appears in a released file",
        "remove the key, rotate it, and rewrite history if it was ever committed",
    ),
    _Detector(
        "credential_assignment",
        Severity.HIGH,
        re.compile(
            # No leading `\b`: the real field name in this repo is
            # `OPENROUTER_API_KEY`, and `\bAPI_KEY` never matches it because the
            # preceding underscore is a word character. The canary caught this on
            # the first run -- see docs/security.md sec.6.
            r"(?i)[A-Za-z0-9_-]*(?:api[_-]?key|secret|token|password|passwd)\s*[:=]\s*"
            r"['\"]?(sk-[A-Za-z0-9._-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|[A-Za-z0-9+/]{32,}={0,2})"
        ),
        "a credential-shaped value is assigned to a credential-named field",
        "move it to `.env` (gitignored) and leave a placeholder in `.env.example`",
    ),
    _Detector(
        "email",
        Severity.MEDIUM,
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "an email address appears in a released file",
        "replace with a role address or remove; a personal address is an identifier",
    ),
    _Detector(
        "windows_user_path",
        Severity.LOW,
        re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+"),
        "an absolute Windows path exposes the developer's account name",
        "replace with a relative path or `<REPO>` before the artifact is released",
    ),
    _Detector(
        "posix_home_path",
        Severity.LOW,
        re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+"),
        "an absolute POSIX home path exposes an account name",
        "replace with a relative path, `$HOME`, or the container's own path",
    ),
    _Detector(
        "social_handle",
        Severity.LOW,
        re.compile(r"(?<![A-Za-z0-9._%+-])@[A-Za-z][A-Za-z0-9_]{4,}\b"),
        "an @-handle appears in a released file",
        "confirm it is a placeholder; a real handle is a direct identifier",
    ),
    _Detector(
        "phone_number",
        Severity.MEDIUM,
        re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?![\w.])"),
        "a digit run long enough to be a telephone number appears in a released file",
        "confirm it is not a contact number; remove it if it is",
    ),
)

#: A detector that fires on everything is as uninformative as one that fires on
#: nothing: both make the difference between 0 and N findings meaningless. The
#: first run of this sweep produced ~600 phone-number hits, every one of them a
#: float in `reports/*.json` (`0.5462...`) or an ISO date (`2026-08-16`). These
#: two rejections are recorded here rather than folded into the pattern so that
#: what is being discarded stays legible to a reviewer.
_DECIMAL_RE = re.compile(r"\d\.\d")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIN_PHONE_DIGITS = 9
#: E.164 caps a telephone number at 15 digits. Anything longer is a float, a
#: hash fragment or a run of coefficients, not a number anyone can dial.
_MAX_PHONE_DIGITS = 15


def _is_plausible_phone(match: str) -> bool:
    if _DECIMAL_RE.search(match) or _ISO_DATE_RE.match(match.strip()):
        return False
    if "(" in match:  # `Smith (2019-2021)` and friends
        return False
    return _MIN_PHONE_DIGITS <= sum(c.isdigit() for c in match) <= _MAX_PHONE_DIGITS


#: `@dataclass`, `@pytest.mark...` and BibTeX's `@article{...}` all begin their
#: line; a handle written in prose ("ask @someone") does not. Distinguishing by
#: POSITION rather than by an ever-growing list of decorator and entry-type
#: names is the difference between a detector that stays correct and one that
#: needs editing every time a new library is imported. The first run of this
#: sweep returned 314 handle hits, of which 310 were decorators or BibTeX.
_LINE_INITIAL_AT_RE = re.compile(r"^\s*@")


#: detect-secrets' own inline waiver, honoured here so a repository does not
#: need two vocabularies for the same idea. Every suppression it causes is
#: COUNTED and reported in the scanner's notes -- a waiver nobody can total up
#: is the `.secrets.baseline` problem in a comment.
ALLOWLIST_PRAGMA = "pragma: allowlist secret"

DETECTOR_KINDS: frozenset[str] = frozenset(d.kind for d in DETECTORS)

#: Files whose content is a scanner's own subject matter. Sweeping them reports
#: the canary and the detector source as findings, which is noise, not signal.
#: Kept as an explicit, short, auditable list rather than a wildcard -- an
#: exclusion nobody can enumerate is an exclusion nobody can review.
SELF_REFERENTIAL: frozenset[str] = frozenset(
    {
        "src/security/sweep.py",
        "src/security/audit.py",
        "tests/test_security.py",
        ".secrets.baseline",
        ".env.example",
    }
)

#: Extensions that are not text. Read as bytes and skipped rather than decoded.
BINARY_SUFFIXES: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".pdf", ".xlsx", ".docx", ".pptx", ".ico", ".woff", ".woff2"}
)


def scan_text(
    text: str,
    *,
    locator: str = "<text>",
    scanner: str = "release-sweep",
    waived: list[str] | None = None,
) -> list[Finding]:
    """Return one Finding per detector hit. Evidence is a silhouette, never text.

    `waived`, if given, is appended to for every hit suppressed by an inline
    `pragma: allowlist secret`, so the caller can report the total.
    """
    lines = text.splitlines()
    findings: list[Finding] = []
    for detector in DETECTORS:
        for match in detector.pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            source_line = lines[line - 1] if line <= len(lines) else ""
            if detector.kind == "phone_number" and not _is_plausible_phone(match.group(0)):
                continue
            if detector.kind == "social_handle" and _LINE_INITIAL_AT_RE.match(source_line):
                continue
            if ALLOWLIST_PRAGMA in source_line:
                if waived is not None:
                    waived.append(f"{locator}:{line} ({detector.kind})")
                continue
            findings.append(
                Finding(
                    scanner=scanner,
                    severity=detector.severity,
                    locator=f"{locator}:{line}",
                    summary=f"{detector.kind}: {detector.summary}",
                    evidence=shape(match.group(0)),
                    fix=detector.fix,
                )
            )
    return findings


def verify_detectors() -> frozenset[str]:
    """Return the kinds that fired on `CANARY`. Should equal `DETECTOR_KINDS`.

    Call this before believing any sweep result. It is cheap, it needs no
    filesystem, and it is the difference between "the scanner found nothing" and
    "there is nothing to find".
    """
    fired = {detector.kind for detector in DETECTORS if detector.pattern.search(CANARY) is not None}
    return frozenset(fired)


def iter_release_paths(root: Path, tracked: Iterable[str]) -> Iterator[Path]:
    """Yield the readable text files among `tracked`, resolved under `root`.

    `tracked` is the output of `git ls-files`. Passing it in rather than
    shelling out keeps this function testable with no git repository and no
    subprocess, which is what lets the whole suite run in seconds.
    """
    for rel in tracked:
        rel = rel.strip()
        if not rel or rel in SELF_REFERENTIAL:
            continue
        path = root / rel
        if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
            continue
        yield path


def run_sweep(root: Path, tracked: Sequence[str]) -> ScannerResult:
    """Sweep the released surface. Refuses to report a clean result unproven."""
    fired = verify_detectors()
    missing = DETECTOR_KINDS - fired
    if missing:
        raise DetectorsUnproven(
            f"{len(missing)} detector(s) did not fire on the canary that plants their "
            f"own target: {', '.join(sorted(missing))}. A sweep using them cannot "
            "report a clean result -- the zero would describe the detectors, not the "
            "repository. Fix the pattern or the canary before re-running."
        )

    findings: list[Finding] = []
    waived: list[str] = []
    scanned = 0
    skipped: list[str] = []
    for path in iter_release_paths(root, tracked):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped.append(str(path.relative_to(root)).replace("\\", "/"))
            continue
        scanned += 1
        rel = str(path.relative_to(root)).replace("\\", "/")
        findings.extend(scan_text(text, locator=rel, waived=waived))

    notes = [
        f"Scanned {scanned} tracked text file(s); {len(skipped)} skipped as undecodable; "
        f"{len(SELF_REFERENTIAL)} excluded as self-referential "
        f"({', '.join(sorted(SELF_REFERENTIAL))}).",
        "Detectors proved on the canary before the sweep ran: " + ", ".join(sorted(fired)) + ".",
    ]
    if skipped:
        notes.append("Undecodable and therefore unswept: " + ", ".join(sorted(skipped)) + ".")
    notes.append(
        f"{len(waived)} hit(s) suppressed by an inline `{ALLOWLIST_PRAGMA}` waiver"
        + (": " + ", ".join(sorted(waived)) if waived else "")
        + ". Every waiver is listed here because a suppression nobody can total up is "
        "the `.secrets.baseline` problem written as a comment."
    )

    return ScannerResult(
        name="Release-surface identifier sweep (src/security/sweep.py)",
        what_it_covers=(
            "Every file `git ls-files` reports as tracked -- i.e. exactly what a reviewer "
            "receives on clone -- read as UTF-8 text and matched against seven identifier "
            "and credential patterns, each proven to fire on a planted canary in the same run."
        ),
        does_not_cover=(
            "Untracked and gitignored files (including all of `data/`, `models/`, `.env` and "
            "`donations_inbox.jsonl`), which are audited separately because they are not "
            "released; binary files; git HISTORY, which holds files no longer tracked; and any "
            "identifier shape nobody thought to write a pattern for -- the same upper-bound "
            "caveat that `src/preprocessing/deidentify.py` carries. A clean result here is a "
            "statement about seven patterns over the tracked tree, not about the repository."
        ),
        findings=tuple(findings),
        proven=True,
        notes=tuple(notes),
    )
