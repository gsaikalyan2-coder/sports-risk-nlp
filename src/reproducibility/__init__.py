"""Phase 22 -- the reproduction path as checkable data.

Pure Python. No ML imports, no network, no disk writes: everything that shells
out, clones or writes belongs to `scripts/run_reproduction.py`, exactly as
`src/security/` leaves those to `scripts/run_security_audit.py`. That split is
why this package's tests run in about a second with no torch installed.
"""

from src.reproducibility.environment import (
    IGNORE_PROBES,
    MUST_BE_ABSENT_IN_FRESH_CLONE,
    PRESENT_IN_FRESH_CLONE,
    ContaminatedTree,
    TreeCheck,
    assert_absentees_are_gitignored,
    assert_fresh,
    inspect_tree,
)
from src.reproducibility.manifest import (
    FILE_DIGESTS,
    HEADLINE,
    PLAN,
    RETRAIN_TOLERANCE_MACRO_F1,
)
from src.reproducibility.plan import (
    CPU_WHEEL_INDEX,
    LOCAL_VERSION_LOCKS,
    Artefact,
    Match,
    MissingExtraIndex,
    ReproductionPlan,
    Step,
    Tier,
)
from src.reproducibility.verify import (
    ArtefactResult,
    Outcome,
    StepResult,
    VerificationReport,
    render_markdown,
)

__all__ = [
    "CPU_WHEEL_INDEX",
    "FILE_DIGESTS",
    "IGNORE_PROBES",
    "HEADLINE",
    "LOCAL_VERSION_LOCKS",
    "MUST_BE_ABSENT_IN_FRESH_CLONE",
    "PLAN",
    "PRESENT_IN_FRESH_CLONE",
    "RETRAIN_TOLERANCE_MACRO_F1",
    "Artefact",
    "ArtefactResult",
    "ContaminatedTree",
    "Match",
    "MissingExtraIndex",
    "Outcome",
    "ReproductionPlan",
    "Step",
    "StepResult",
    "Tier",
    "TreeCheck",
    "VerificationReport",
    "assert_absentees_are_gitignored",
    "assert_fresh",
    "inspect_tree",
    "render_markdown",
]
