"""Measuring de-identification, and the manual audit that measurement cannot replace.

`PROJECT_PLAN.md` sets the Phase 8 gate as "spot-check sample shows no direct
identifiers remain". Run against `data/raw/synth_precomp_v1` that gate is
**vacuous**: the synthetic generator plants no personal names, so the
de-identifier removes nothing, the spot-check finds nothing, and the gate
passes having measured zero. That is OPEN-013, and it is why this module
exists.

So Phase 8 uses two gates, and says which is which.

* **The real gate** is `score_fixture` against `tests/fixtures/deid_cases.jsonl`
  -- 34 cases seeded with names, handles, venues, events, and eight negatives
  that must come back unchanged. Precision, recall, and exact match, broken out
  by difficulty band, because an aggregate number hides that the easy cases pass
  and the hard ones do not.
* **The corpus check** is `audit_sample`, which confirms the pipeline runs clean
  over `data/raw/` and produces a stratified sample for human reading. It is
  evidence of no regression, not evidence of recall.

## The metric that actually matters

`recall` here is placeholder-level agreement with the fixture's expected output.
That is the convenient metric. The one that matters ethically is
**`leak_rate`**: the share of cases where a string the fixture removed is still
present in the output. A case can score poorly on placeholder typing -- calling
a coach `[PERSON]` instead of `[COACH]` -- and still leak nothing. And a case
can match the expected placeholder count while leaking, if the de-identifier
replaced the wrong span. Both numbers are reported; only one of them is a
privacy claim.

Precision is reported for the reason `tests/fixtures/README.md` gives: a
de-identifier that blanks everything scores perfect recall and destroys the
corpus.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .deidentify import PLACEHOLDER_RE, deidentify_with_report

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "deid_cases.jsonl"

#: Tokens that carry no identifying information and are ignored when checking
#: whether a removed span leaked through. Without this, every case "leaks"
#: because the words around the identifier also differ.
_STOPWORDS = frozenset(
    "a an and at be by for from he i in is it me my of on or she that the to was we".split()
)


@dataclass
class CaseResult:
    """One fixture case, scored."""

    case_id: str
    category: str
    difficulty: str
    text: str
    expected: str
    produced: str
    expected_placeholders: list[str]
    produced_placeholders: list[str]
    true_positives: int
    false_positives: int
    false_negatives: int
    exact_match: bool
    leaked: list[str] = field(default_factory=list)

    @property
    def leaks(self) -> bool:
        return bool(self.leaked)

    def to_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "difficulty": self.difficulty,
            "text": self.text,
            "expected": self.expected,
            "produced": self.produced,
            "exact_match": self.exact_match,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "leaked": self.leaked,
        }


@dataclass
class FixtureScore:
    """Aggregate scores, plus every case so failures can be read individually."""

    cases: list[CaseResult]

    # -- placeholder-level agreement ---------------------------------------

    @property
    def true_positives(self) -> int:
        return sum(c.true_positives for c in self.cases)

    @property
    def false_positives(self) -> int:
        return sum(c.false_positives for c in self.cases)

    @property
    def false_negatives(self) -> int:
        return sum(c.false_negatives for c in self.cases)

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else 1.0

    @property
    def recall(self) -> float:
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def exact_match_rate(self) -> float:
        return sum(c.exact_match for c in self.cases) / len(self.cases) if self.cases else 0.0

    # -- the privacy metric -------------------------------------------------

    @property
    def leak_rate(self) -> float:
        """Share of cases where a removed string survived into the output."""
        return sum(c.leaks for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def leaking_cases(self) -> list[CaseResult]:
        return [c for c in self.cases if c.leaks]

    # -- over-redaction -----------------------------------------------------

    @property
    def negatives(self) -> list[CaseResult]:
        return [c for c in self.cases if c.category == "negative"]

    @property
    def negatives_preserved(self) -> int:
        return sum(c.produced == c.expected for c in self.negatives)

    def by(self, attribute: str) -> dict[str, FixtureScore]:
        """Re-score grouped by `difficulty` or `category`."""
        groups: dict[str, list[CaseResult]] = {}
        for case in self.cases:
            groups.setdefault(getattr(case, attribute), []).append(case)
        return {key: FixtureScore(value) for key, value in sorted(groups.items())}

    def to_dict(self) -> dict[str, object]:
        return {
            "n_cases": len(self.cases),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "exact_match_rate": round(self.exact_match_rate, 4),
            "leak_rate": round(self.leak_rate, 4),
            "negatives_preserved": f"{self.negatives_preserved}/{len(self.negatives)}",
        }


def load_cases(path: Path | None = None) -> list[dict[str, object]]:
    """Read the fixture. Raises if it is missing -- there is no silent skip.

    A missing fixture must fail the gate loudly. Skipping it would let Phase 8
    report a pass on the vacuous corpus check alone, which is precisely the
    failure OPEN-013 was raised to prevent.
    """
    path = path or DEFAULT_FIXTURE
    if not path.exists():
        raise FileNotFoundError(
            f"de-identification fixture not found: {path}. "
            "The Phase 8 gate cannot be evaluated without it (OPEN-013)."
        )
    cases = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if not cases:
        raise ValueError(f"{path} is empty")
    return cases


def _content_tokens(text: str) -> set[str]:
    cleaned = PLACEHOLDER_RE.sub(" ", text)
    return {
        token.strip(".,;:!?\"'()").lower()
        for token in cleaned.split()
        if token.strip(".,;:!?\"'()")
    } - _STOPWORDS


def _removed_strings(text: str, expected: str) -> set[str]:
    """Tokens present in the input that the fixture's expected output drops.

    Derived rather than declared, so the leak check stays correct if a case is
    edited without anyone remembering to update a separate list of secrets.
    """
    return _content_tokens(text) - _content_tokens(expected)


def score_case(case: dict[str, object]) -> CaseResult:
    """Run the de-identifier over one fixture case and score it."""
    text = str(case["text"])
    expected = str(case["expected"])
    produced, _ = deidentify_with_report(text)

    expected_ph = Counter(PLACEHOLDER_RE.findall(expected))
    produced_ph = Counter(PLACEHOLDER_RE.findall(produced))
    overlap = expected_ph & produced_ph
    true_positives = sum(overlap.values())

    leaked = sorted(_removed_strings(text, expected) & _content_tokens(produced))

    return CaseResult(
        case_id=str(case["case_id"]),
        category=str(case["category"]),
        difficulty=str(case.get("difficulty", "unknown")),
        text=text,
        expected=expected,
        produced=produced,
        expected_placeholders=sorted(expected_ph.elements()),
        produced_placeholders=sorted(produced_ph.elements()),
        true_positives=true_positives,
        false_positives=sum(produced_ph.values()) - true_positives,
        false_negatives=sum(expected_ph.values()) - true_positives,
        exact_match=produced == expected,
        leaked=leaked,
    )


def score_fixture(path: Path | None = None) -> FixtureScore:
    """Score every case in the fixture."""
    return FixtureScore([score_case(case) for case in load_cases(path)])


# ---------------------------------------------------------------------------
# The corpus-side check
# ---------------------------------------------------------------------------


@dataclass
class SampleFinding:
    """One record surfaced for human reading."""

    record_id: str
    stratum: str
    text: str
    flags: list[str]


def audit_sample(
    records: list[tuple[str, str, str, list[str]]],
    *,
    per_stratum: int = 3,
) -> list[SampleFinding]:
    """Draw a stratified sample for the manual audit.

    Input tuples are `(record_id, stratum, deidentified_text, residual_flags)`.

    Flagged records are drawn first. `docs/ethics.md` sec.5.2 requires a manual
    audit precisely because automation misses what it has no rule for, so a
    sample that ignores the pipeline's own uncertainty wastes the human's time
    on the cases the machine already handled.
    """
    by_stratum: dict[str, list[SampleFinding]] = {}
    for record_id, stratum, text, flags in records:
        by_stratum.setdefault(stratum, []).append(
            SampleFinding(record_id=record_id, stratum=stratum, text=text, flags=list(flags))
        )

    sample: list[SampleFinding] = []
    for stratum in sorted(by_stratum):
        found = sorted(by_stratum[stratum], key=lambda f: (not f.flags, f.record_id))
        sample.extend(found[:per_stratum])
    return sample
