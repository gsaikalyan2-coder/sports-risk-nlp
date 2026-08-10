"""Phase 8 -- preprocessing and de-identification.

Public API. Import from here rather than from the submodules, so the enforced
path stays the obvious path -- the same convention `src/ingestion/__init__.py`
established at Phase 7.

    from src.preprocessing import preprocess_all, deidentify, score_fixture

    results = preprocess_all()          # data/raw/ -> data/interim/
    score = score_fixture()             # the gate that actually measures recall

Nothing here can write into `data/interim/` without carrying a raw
`provenance.json` forward, and nothing can construct an `InterimRecord` that
has not been de-identified. Both are structural, not procedural -- see
`store.py` and `records.py`.

The whole package is pure Python: no numpy, no scikit-learn, no model
download, no network. It runs in the light Docker image and `pytest` cannot
spend money.
"""

from .audit import (
    CaseResult,
    FixtureScore,
    SampleFinding,
    audit_sample,
    load_cases,
    score_case,
    score_fixture,
)
from .deidentify import (
    PLACEHOLDER_RE,
    PLACEHOLDERS,
    DeidReport,
    deidentify,
    deidentify_with_report,
    remove_health_detail,
)
from .language import (
    DEFAULT_THRESHOLD,
    LanguageVerdict,
    detect_language,
    is_english,
)
from .normalize import NormalizationReport, normalize, normalize_with_report
from .pipeline import (
    DROP_REASONS,
    PreprocessResult,
    RecordOutcome,
    preprocess_all,
    preprocess_record,
    preprocess_source,
)
from .records import CARRIED_FIELDS, InterimRecord
from .segment import Utterance, segment, verify_offsets
from .store import InterimStore, InterimWriter, interim_provenance

__all__ = [
    "CARRIED_FIELDS",
    "DEFAULT_THRESHOLD",
    "DROP_REASONS",
    "PLACEHOLDERS",
    "PLACEHOLDER_RE",
    "CaseResult",
    "DeidReport",
    "FixtureScore",
    "InterimRecord",
    "InterimStore",
    "InterimWriter",
    "LanguageVerdict",
    "NormalizationReport",
    "PreprocessResult",
    "RecordOutcome",
    "SampleFinding",
    "Utterance",
    "audit_sample",
    "deidentify",
    "deidentify_with_report",
    "detect_language",
    "interim_provenance",
    "is_english",
    "load_cases",
    "normalize",
    "normalize_with_report",
    "preprocess_all",
    "preprocess_record",
    "preprocess_source",
    "remove_health_detail",
    "score_case",
    "score_fixture",
    "segment",
    "verify_offsets",
]
