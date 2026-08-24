"""Phase 21 gate, written before the audit was run.

The tests are grouped by the property they defend, and the first group is the
important one: it pins the predicted defect shut. Every test here runs with no
ML stack, no network and no git repository.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.dashboard.view import ForbiddenLanguage
from src.evaluation.harness import PROVISIONAL_STAMP
from src.security import (
    CANARY,
    DETECTOR_KINDS,
    AuditReport,
    DetectorsUnproven,
    Finding,
    ScannerResult,
    Severity,
    audit_baseline,
    audit_requirements,
    render_markdown,
    run_sweep,
    scan_text,
    shape,
    verify_detectors,
)
from src.security.baseline import files_added_since
from src.security.deps import parse_requirements
from src.security.sweep import DETECTORS


def _result(**kw) -> ScannerResult:
    base = dict(
        name="t",
        what_it_covers="a long enough sentence about what this covers",
        does_not_cover="a long enough sentence about what this does not cover",
    )
    base.update(kw)
    return ScannerResult(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1. THE PREDICTED DEFECT: "0 findings" accepted as "nothing to find"
# ---------------------------------------------------------------------------


def test_every_detector_fires_on_the_canary() -> None:
    """The canary plants one identifier per kind. All of them must be found."""
    assert verify_detectors() == DETECTOR_KINDS


def test_a_sweep_refuses_to_run_when_a_detector_is_silent(monkeypatch) -> None:
    """A broken pattern must abort the sweep, not quietly shrink its coverage.

    This is the whole phase in one test. If a detector stops matching -- a
    refactor, a bad escape, a Python regex change -- the sweep must fail loudly
    rather than return a shorter findings list that reads exactly like good news.
    """
    broken = tuple(
        d
        if d.kind != "email"
        else type(d)(d.kind, d.severity, re.compile(r"(?!x)x"), d.summary, d.fix)
        for d in DETECTORS
    )
    monkeypatch.setattr("src.security.sweep.DETECTORS", broken)
    with pytest.raises(DetectorsUnproven, match="email"):
        run_sweep(Path("."), [])


def test_an_unproven_scanner_fails_the_gate_even_with_zero_findings() -> None:
    report = AuditReport([_result(findings=(), proven=False)])
    passed, reasons = report.gate()
    assert not passed
    assert "did not prove" in reasons[0]


def test_a_clean_proven_scanner_passes_the_gate() -> None:
    assert AuditReport([_result(findings=(), proven=True)]).gate()[0]


def test_clean_is_false_for_an_unproven_scanner() -> None:
    assert not _result(proven=False).clean
    assert _result(proven=True).clean


# ---------------------------------------------------------------------------
# 2. A findings table with no coverage statement is unconstructable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["what_it_covers", "does_not_cover"])
@pytest.mark.parametrize("value", ["", "   ", "n/a", "nothing"])
def test_a_scanner_result_without_a_real_coverage_statement_cannot_exist(field, value) -> None:
    with pytest.raises(ValueError, match="Phase 18 defect|perfunctory|empty"):
        _result(**{field: value})


def test_the_rendered_report_always_prints_the_coverage_statement() -> None:
    text = render_markdown(
        AuditReport([_result(does_not_cover="binary blobs and git history entirely")])
    )
    assert "Does NOT cover" in text
    assert "binary blobs and git history entirely" in text


def test_a_clean_unproven_scanner_renders_a_warning_not_a_clean_bill() -> None:
    text = render_markdown(AuditReport([_result(proven=False)]))
    assert "the scanner said nothing" in text
    assert "not as 'there is nothing'" in text


# ---------------------------------------------------------------------------
# 3. No verbatim matched text ever reaches a committed document
# ---------------------------------------------------------------------------


def test_shape_returns_a_silhouette_and_never_the_characters() -> None:
    assert shape("k.mensah_07") == "a.aaaaaa_99"
    assert shape("AKIA1234") == "AAAA9999"


def test_shape_truncates_a_long_match() -> None:
    out = shape("a" * 100)
    assert out.endswith("...")
    assert len(out) == 43


def test_no_finding_carries_the_text_it_matched() -> None:
    """Scan the canary; every planted value must be absent from the findings."""
    findings = scan_text(CANARY, locator="canary")
    assert findings
    blob = json.dumps([f.__dict__ for f in findings], default=str)
    for planted in (
        "not.a.real.person@example.invalid",
        "sk-canary000000000000000000000000000000000000000",
        "canaryuser",
        "canary_handle_01",
    ):
        assert planted not in blob, f"{planted!r} leaked into the findings"


def test_findings_carry_a_line_number_so_a_human_can_go_and_look() -> None:
    findings = scan_text("ok\nok\ncontact: a@b.co\n", locator="f.md")
    assert any(f.locator == "f.md:3" for f in findings)


# ---------------------------------------------------------------------------
# 4. Project-wide language and provenance rules apply to this surface too
# ---------------------------------------------------------------------------


def test_a_finding_using_forbidden_wording_cannot_be_constructed() -> None:
    with pytest.raises(ForbiddenLanguage):
        Finding(
            scanner="t",
            severity=Severity.LOW,
            locator="x",
            summary="the expert-validated scan found nothing",
        )


def test_a_scanner_result_using_forbidden_wording_cannot_be_constructed() -> None:
    with pytest.raises(ForbiddenLanguage):
        _result(does_not_cover="does not measure the accuracy of the detector patterns at all")


def test_the_provisional_stamps_own_denial_is_still_permitted() -> None:
    """`PROVISIONAL_STAMP` contains 'NOT accuracy'. It must remain quotable."""
    render_markdown(AuditReport([_result(notes=(PROVISIONAL_STAMP,))]))


# ---------------------------------------------------------------------------
# 5. Scope comes from git, so a file's location cannot put it out of scope
# ---------------------------------------------------------------------------


def test_a_tracked_file_at_the_repo_root_is_swept(tmp_path: Path) -> None:
    """The `donations_inbox.jsonl` shape: outside `data/`, must not be missed."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "inner.md").write_text("clean\n", encoding="utf-8")
    (tmp_path / "root_file.jsonl").write_text(
        '{"contact": "a.person@example.com"}\n', encoding="utf-8"
    )
    result = run_sweep(tmp_path, ["data/inner.md", "root_file.jsonl"])
    assert [f.locator for f in result.findings] == ["root_file.jsonl:1"]


def test_an_untracked_file_is_not_swept_because_it_is_not_released(tmp_path: Path) -> None:
    (tmp_path / "secret_notes.md").write_text("me@example.com\n", encoding="utf-8")
    assert run_sweep(tmp_path, []).findings == ()


@pytest.mark.parametrize("noise", ["0.5462198765432", "2026-08-16", "1.2345678901234567"])
def test_floats_and_iso_dates_are_not_reported_as_phone_numbers(noise: str) -> None:
    """A detector that fires on everything is as uninformative as one that never does."""
    assert not [f for f in scan_text(f"value: {noise}\n") if "phone_number" in f.summary]


def test_a_real_looking_number_is_still_reported() -> None:
    assert [f for f in scan_text("call +44 7700 900123\n") if "phone_number" in f.summary]


@pytest.mark.parametrize("line", ["@dataclass", "  @pytest.mark.slow", "@article{smith2019,"])
def test_a_line_initial_at_is_a_decorator_or_bibtex_entry_not_a_handle(line: str) -> None:
    assert not [f for f in scan_text(line + "\n") if "social_handle" in f.summary]


def test_a_handle_written_in_prose_is_still_reported() -> None:
    assert [f for f in scan_text("ask @someone_real about it\n") if "social_handle" in f.summary]


def test_an_inline_allowlist_pragma_suppresses_and_is_counted() -> None:
    waived: list[str] = []
    line = "OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef0123  # pragma: allowlist secret\n"
    assert scan_text(line, locator="doc.md", waived=waived) == []
    assert waived == ["doc.md:1 (credential_assignment)"]


def test_the_same_line_without_the_pragma_is_a_high_finding() -> None:
    # The Python comment below waives this line for `detect-secrets`, which reads
    # source lines; the string it builds carries no pragma, which is what the
    # assertion needs. The two scanners look at different things and that is the
    # only reason both can be satisfied at once.
    line = "OPENROUTER_API_KEY=sk-or-v1-0123456789abcdef0123\n"  # pragma: allowlist secret
    findings = scan_text(line, locator="doc.md")
    assert [f.severity for f in findings] == [Severity.HIGH]


def test_every_waiver_is_named_in_the_sweeps_notes(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text(
        "token = abcdefghijklmnopqrstuvwxyz0123456789  # pragma: allowlist secret\n",
        encoding="utf-8",
    )
    result = run_sweep(tmp_path, ["doc.md"])
    assert result.findings == ()
    assert any("doc.md:1" in note for note in result.notes)


def test_binary_and_self_referential_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "fig.png").write_bytes(b"\x89PNG\x00me@example.com")
    result = run_sweep(tmp_path, ["fig.png", "src/security/sweep.py"])
    assert result.findings == ()


# ---------------------------------------------------------------------------
# 6. The baseline is interrogated, not trusted
# ---------------------------------------------------------------------------


def _baseline(tmp_path: Path, results: dict) -> Path:
    path = tmp_path / ".secrets.baseline"
    path.write_text(
        json.dumps(
            {
                "version": "1.5.0",
                "generated_at": "2026-08-12T13:35:43Z",
                "plugins_used": [{"name": "AWSKeyDetector"}],
                "filters_used": [
                    {
                        "path": "detect_secrets.filters.regex.should_exclude_file",
                        "pattern": ["^data/|^paper/"],
                    }
                ],
                "results": results,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_an_entry_marked_is_secret_true_is_a_high_finding(tmp_path: Path) -> None:
    path = _baseline(tmp_path, {"reports/a.json": [{"line_number": 9, "is_secret": True}]})
    audit, result = audit_baseline(path)
    assert audit.confirmed_secret_entries == (("reports/a.json", 9),)
    assert result.worst() is Severity.HIGH


def test_an_entry_marked_is_secret_false_is_a_reviewed_false_positive(tmp_path: Path) -> None:
    path = _baseline(tmp_path, {"reports/a.json": [{"line_number": 9, "is_secret": False}]})
    _, result = audit_baseline(path)
    assert result.findings == ()


def test_windows_separators_in_a_baseline_are_a_high_finding(tmp_path: Path) -> None:
    r"""`reports\a.json` never matches `reports/a.json` inside the container."""
    path = _baseline(tmp_path, {"reports\\a.json": [{"line_number": 9, "is_secret": False}]})
    audit, result = audit_baseline(path)
    assert audit.windows_separator_entries == ("reports\\a.json",)
    assert result.worst() is Severity.HIGH


def test_the_baselines_exclude_patterns_appear_in_its_coverage_statement(tmp_path: Path) -> None:
    _, result = audit_baseline(_baseline(tmp_path, {}))
    assert "^data/|^paper/" in result.does_not_cover


def test_files_added_after_the_baseline_are_reported_as_never_scanned() -> None:
    added = files_added_since(
        "2026-08-12T13:35:43Z",
        {"old.py": "2026-08-01T00:00:00Z", "new.py": "2026-08-16T00:00:00Z"},
    )
    assert added == ["new.py"]


# ---------------------------------------------------------------------------
# 7. Dependencies: a floor is not a version
# ---------------------------------------------------------------------------


def test_a_floor_requirement_is_not_auditable(tmp_path: Path) -> None:
    path = tmp_path / "requirements-ml.txt"
    path.write_text(
        "-r requirements-base.txt\ntorch>=2.2\ntransformers>=5.0,<6.0\n", encoding="utf-8"
    )
    reqs = parse_requirements(path)
    assert [r.name for r in reqs] == ["torch", "transformers"]
    assert all(not r.auditable for r in reqs)


def test_a_local_version_segment_is_normalised_for_lookup(tmp_path: Path) -> None:
    path = tmp_path / "requirements.lock.txt"
    path.write_text("torch==2.13.0+cpu\n", encoding="utf-8")
    assert parse_requirements(path)[0].pinned_version == "2.13.0"


def test_include_directives_are_not_followed(tmp_path: Path) -> None:
    """Following `-r` would merge the layers and hide the distinction."""
    (tmp_path / "requirements-base.txt").write_text("pyyaml==6.0\n", encoding="utf-8")
    ml = tmp_path / "requirements-ml.txt"
    ml.write_text("-r requirements-base.txt\ntorch>=2.2\n", encoding="utf-8")
    assert [r.name for r in parse_requirements(ml)] == ["torch"]


def test_an_unauditable_file_produces_a_finding_naming_the_image_that_ships_it(
    tmp_path: Path,
) -> None:
    ml = tmp_path / "requirements-ml.txt"
    ml.write_text("torch>=2.2\n", encoding="utf-8")
    _, result = audit_requirements(
        [ml], {}, installed_by={"requirements-ml.txt": "Dockerfile.train"}
    )
    assert any("Dockerfile.train" in f.summary for f in result.findings)


def test_an_advisory_on_a_pinned_version_is_reported(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.lock.txt"
    lock.write_text("chromadb==1.1.1\npyyaml==6.0\n", encoding="utf-8")
    _, result = audit_requirements([lock], {("chromadb", "1.1.1"): ["GHSA-xxxx"]})
    hits = [f for f in result.findings if "chromadb" in f.locator]
    assert len(hits) == 1
    assert "GHSA-xxxx" in hits[0].summary


def test_an_offline_dependency_run_is_unproven_and_so_fails_the_gate(tmp_path: Path) -> None:
    """No query was made, so "no advisories" is a statement about the network."""
    path = tmp_path / "requirements.lock.txt"
    path.write_text("pyyaml==6.0\n", encoding="utf-8")
    _, result = audit_requirements([path], {}, looked_up=False)
    assert not result.proven
    assert not AuditReport([result]).gate()[0]


def test_a_failed_advisory_lookup_is_reported_not_swallowed(tmp_path: Path) -> None:
    path = tmp_path / "requirements.lock.txt"
    path.write_text("pyyaml==6.0\n", encoding="utf-8")
    _, result = audit_requirements([path], {}, lookup_failures=["pyyaml==6.0"])
    assert not result.proven
    assert any("NOT checked" in n for n in result.notes)


def test_the_unpinned_count_reaches_the_coverage_statement(tmp_path: Path) -> None:
    path = tmp_path / "requirements-base.txt"
    path.write_text("streamlit>=1.37\npyyaml==6.0\n", encoding="utf-8")
    _, result = audit_requirements([path], {})
    assert "1 floor-or-range requirement" in result.does_not_cover


# --------------------------------------------------------------------------
# SEC-04 / OPEN-006, closed at Phase 22. Two halves, and both are needed.
#
# Removing the personal address is only half the fix: `docs/ethics.md` §7.1
# requires the replacement route to appear on every reader-facing surface,
# because a withdrawal right a reader cannot find is decorative. That mandate
# had gone unmet since Phase 5 -- neither README.md nor docs/model_card.md
# carried any contact route at all, while §7.1 asserted they must. Same shape
# as every defect this project has found: the rule and the thing it governs
# were related by assumption.
# --------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INSTITUTIONAL = "sk8069@srmist.edu.in"
_READER_FACING = (
    "README.md",
    "ARTIFACT.md",
    "docs/model_card.md",
    "docs/consent_form.md",
    "docs/ethics.md",
)


@pytest.mark.parametrize("relpath", _READER_FACING)
def test_every_reader_facing_surface_carries_the_contact_route(relpath: str) -> None:
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    assert _INSTITUTIONAL in text, (
        f"{relpath} has no contact route; docs/ethics.md §7.1 requires one on "
        "every surface a reader actually holds"
    )
    assert "Shankar Ram" in text, f"{relpath} names no supervisor / secondary contact"


@pytest.mark.parametrize("relpath", _READER_FACING + ("docs/recruitment.md", "docs/open_issues.md"))
def test_no_personal_webmail_survives_in_a_document(relpath: str) -> None:
    """The address is gone from the prose, including the historical notes.

    Quoting the old address back inside a 'retained for the record' block
    republishes exactly what the fix removed, so the record keeps the decision
    and redacts the value.
    """
    text = (_REPO_ROOT / relpath).read_text(encoding="utf-8")
    for domain in ("@gmail.com", "@googlemail.com", "@outlook.com", "@yahoo.com"):
        assert domain not in text, f"{relpath} still publishes a personal {domain} address"


# --------------------------------------------------------------------------
# The COMMITTED baseline, not a fixture. Every other baseline test in this file
# builds its own file under tmp_path, so they prove the parser works and prove
# nothing at all about the artefact that ships. On 2026-08-24 the suite was
# fully green while `.secrets.baseline` in the working tree was UTF-16LE with a
# BOM and unreadable by detect-secrets -- PowerShell's `>` redirect encodes
# UTF-16 by default, so `docker compose run ... detect-secrets scan >
# .secrets.baseline` corrupts the file it is supposed to regenerate.
#
# Seventh instance of this project's defect shape: the check (baseline parsing
# works) and the property (the shipped baseline parses) were related by
# assumption. The fix is to read the real path.
# --------------------------------------------------------------------------


def test_the_committed_baseline_is_utf8_and_parses() -> None:
    path = _REPO_ROOT / ".secrets.baseline"
    assert path.exists(), ".secrets.baseline is missing from the repository"

    raw = path.read_bytes()
    for bom, name in (
        (b"\xff\xfe", "UTF-16LE"),
        (b"\xfe\xff", "UTF-16BE"),
        (b"\xef\xbb\xbf", "UTF-8 with BOM"),
    ):
        assert not raw.startswith(bom), (
            f".secrets.baseline is {name}. detect-secrets reads UTF-8 and will "
            "fail on it. Regenerate with the redirect INSIDE the container: "
            "docker compose run --rm app sh -c 'detect-secrets scan > .secrets.baseline'"
        )

    payload = json.loads(raw.decode("utf-8"))
    assert "results" in payload, ".secrets.baseline has no results block"
    assert "generated_at" in payload, ".secrets.baseline records no scan time"


def test_the_committed_baseline_is_evidence_of_a_scan_that_saw_the_repo() -> None:
    """An empty baseline is indistinguishable from a scan that read no files.

    Found 2026-08-24. `detect-secrets scan` enumerates via `git ls-files`; run
    inside the container against the bind-mounted tree, git refuses the repo for
    dubious ownership, so the scan sees ZERO files and writes results: {}. That
    file then silently filters nothing, while looking exactly like a clean repo.
    Phase 21's canary corollary, in the artefact rather than the scanner: a
    result that a broken run and a clean run produce identically is not a result.

    The canary here is the project's own SHA-256 digests. They are known to be
    present, known not to be secrets, and their absence from the baseline proves
    the scan did not reach the source tree.
    """
    payload = json.loads((_REPO_ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
    results = payload.get("results", {})
    assert results, (
        "the baseline records zero findings over the whole repository. That is "
        "what a scan which read no files produces. Regenerate with git able to "
        "enumerate the tree:\n"
        "  docker compose run --rm app sh -c "
        "'git config --global --add safe.directory /app && "
        "detect-secrets scan > .secrets.baseline'"
    )
    scanned = {p.replace("\\", "/") for p in results}
    assert "src/reproducibility/manifest.py" in scanned, (
        "the baseline does not cover src/reproducibility/manifest.py, whose "
        "FILE_DIGESTS entries are high-entropy hex by construction. Either the "
        "scan missed the source tree or the exclusion list has drifted."
    )


def test_no_baseline_entry_is_left_unaudited() -> None:
    """Every entry carries a human verdict, and none of them is `true`.

    Phase 21 found all four entries marked is_secret: true -- the baseline was
    asserting the repository contained four live secrets. They are SHA-256
    digests: corpus fingerprints and a claim-ledger digest. A digest published
    on purpose is not a credential, but that is a judgement a person makes once
    and records, never one the tool makes.
    """
    payload = json.loads((_REPO_ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
    for path, entries in payload.get("results", {}).items():
        for entry in entries:
            assert "is_secret" in entry, (
                f"{path}:{entry.get('line_number')} has no verdict -- run "
                "`detect-secrets audit .secrets.baseline` and rule on it"
            )
            assert entry["is_secret"] is False, (
                f"{path}:{entry.get('line_number')} is marked as a REAL secret. "
                "Either it is one and must be removed from the repository, or "
                "the audit verdict is wrong."
            )


def test_every_committed_baseline_path_is_posix() -> None:
    """Phase 21 converted these; a Windows-host rescan silently reverts them."""
    payload = json.loads((_REPO_ROOT / ".secrets.baseline").read_text(encoding="utf-8"))
    offenders = [p for p in payload.get("results", {}) if "\\" in p]
    assert not offenders, (
        f"baseline paths are backslash-separated and platform-locked: {offenders}. "
        "The same entries will not match on a reviewer's machine."
    )
