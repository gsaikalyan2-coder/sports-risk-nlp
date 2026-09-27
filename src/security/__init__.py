"""Phase 21 - the re-runnable half of the security audit.

Why this is a package and not a terminal transcript
---------------------------------------------------
A security phase is made almost entirely of gates, and this project has now
found the same defect four phases running: *the check and the thing it protects
were related by assumption rather than by construction*. Phase 21's instance was
predicted in `handover_phase_20.txt` C4 and it is the one every security review
makes:

    A SCANNER REPORTING "0 FINDINGS" IS ACCEPTED AS "THERE IS NOTHING TO FIND",
    WITHOUT ANYONE CHECKING WHAT THE SCANNER ACTUALLY LOOKED AT.

Three constructional answers live in this package, one per module:

* `audit.ScannerResult` **requires** a non-empty `does_not_cover` sentence. A
  findings table with no coverage statement is unconstructable, so the Phase 18
  defect (a gate that certifies existence rather than content) cannot recur in
  the report format itself.
* `sweep` derives its file set from what git would actually publish, never from
  a directory list. "The sweep was scoped to `data/` and missed the file at the
  repo root" is therefore not an available mistake.
* `sweep.verify_detectors` runs every detector against a canary carrying one
  planted identifier of each kind, and `run_sweep` REFUSES to report a clean
  result if any detector failed to fire. A zero is only publishable once the
  detectors have demonstrated on this run that they can produce a non-zero.

No ML stack. Standard library only. The suite runs in seconds without torch,
which is the line every phase since 15 has held.
"""

from src.security.audit import (
    AuditReport,
    Finding,
    ScannerResult,
    Severity,
    render_markdown,
    shape,
)
from src.security.baseline import BaselineAudit, audit_baseline
from src.security.deps import DependencyAudit, Requirement, audit_requirements
from src.security.sweep import (
    CANARY,
    DETECTOR_KINDS,
    DetectorsUnproven,
    run_sweep,
    scan_text,
    verify_detectors,
)

__all__ = [
    "CANARY",
    "DETECTOR_KINDS",
    "AuditReport",
    "BaselineAudit",
    "DependencyAudit",
    "DetectorsUnproven",
    "Finding",
    "Requirement",
    "ScannerResult",
    "Severity",
    "audit_baseline",
    "audit_requirements",
    "render_markdown",
    "run_sweep",
    "scan_text",
    "shape",
    "verify_detectors",
]
