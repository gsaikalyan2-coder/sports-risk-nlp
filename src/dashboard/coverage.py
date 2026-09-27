"""The evidence-coverage ledger: what this text could *not* speak to.

What this module is for
------------------------
Every other surface in this package reports what was found. The bars report
detections, the waterfall reports pushes, the atlas reports mappings, the cards
report spans. Nothing reports the negative space -- the validated instruments
the input gave no evidence about either way -- and the risk index is rendered
with no statement of how much evidence it rests on.

Phase 31 measured why that matters. Over the corpus, the widened cue list this
page actually runs is silent on 20.2% of texts, and the frozen list the paper
evaluates is silent on 58.8% -- and a silent detector reaches the fusion layer
with nothing detected and lands on the exact midpoint `CLAUDE.md` sec.12.3 is
written about. Both figures are from `reports/abstention.md` sec.4, which
measures the two lists side by side over one corpus; which list is in force
changes the number by a factor of three, so neither is quoted here without it.
(That report's sec.3 `no_detection` route reads 58.6% for the frozen list,
one text lower, because it files the single refused text under `refused`.) A
reader looking at a confident index has no way to see any of this. This module
supplies the denominator.

It computes no new number
--------------------------
Every state below is read off `ConstructBar.detected` and `ConstructBar.inert`,
which already exist and already carry the distinction; the only new thing is the
projection onto instruments and the fact that the *absences* are named. There is
no detection logic here, no threshold, no weight and no score. The ledger cannot
move the risk index because it never touches the scorer -- `coverage_for` takes a
finished `DashboardView` and returns a reading of it.

Why it does not import `src.evaluation.abstention`
---------------------------------------------------
That module names the same four states and it is tempting to import `CAUSES`
from it. The dependency direction inverts: `src.evaluation.abstention` already
imports `src.dashboard.gibberish`, so importing it from here closes the OPEN-036
cycle (`src.dashboard.__init__` -> `copy` -> `view` -> `backend` ->
`src.explainability.attribution`, partially initialised). That cycle was closed
once in Phase 31, broke
`test_explainability_imports_standalone_in_a_fresh_interpreter`, and was removed
rather than worked around. The two modules agree on the four states by
construction, and `tests/test_coverage.py` holds an agreement test that imports
both while the modules import neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.dashboard.copy import CONSTRUCTS
from src.dashboard.instruments import load_instruments
from src.dashboard.view import DashboardView, assert_no_forbidden_language
from src.evaluation.harness import PROVISIONAL_STAMP


class CoverageState(Enum):
    """What one text gave this subscale. Four states, answering to Phase 31's four.

    They correspond one-to-one with `src.evaluation.abstention.CAUSES` without
    sharing its words, because the two modules describe different grains:
    `abstention` reports one outcome for a whole text, this reports one per
    subscale. `silent` answers to `no_detection`, `inert` to `all_inert`,
    `evidenced` to `moved`, and `refused` is the same word on both sides. The
    map is written out and asserted as a bijection in
    `tests/test_coverage.py::STATE_TO_CAUSE`, which is the guard against either
    side quietly growing a fifth.

    `REFUSED` is never returned by `coverage_for`, and that is the point rather
    than an omission: a refused input never reaches the scorer, so no
    `DashboardView` exists for this module to read. It is named here so a page
    with nothing to show because a gate refused says so in the same word the
    rest of the project uses.
    """

    EVIDENCED = "evidenced"
    INERT = "inert"
    SILENT = "silent"
    REFUSED = "refused"


#: What each state is allowed to mean, in the words that go on screen.
#:
#: `SILENT` is the dangerous one and its wording is fixed rather than phrased at
#: the call site. Silent means the construct is absent, OR the athlete did not
#: mention it, OR the detector missed it -- and at Phase 31's measured silent
#: rate (20.2% on the widened list this page runs, 58.8% on the frozen one --
#: `reports/abstention.md` sec.4, which names the list beside each figure) the
#: third is common on either. "No evidence either way" is the only reading that
#: covers all three, so it is the only one written.
STATE_WORDS: dict[CoverageState, str] = {
    CoverageState.EVIDENCED: "evidenced",
    CoverageState.INERT: "inert",
    CoverageState.SILENT: "silent",
    CoverageState.REFUSED: "refused",
}

#: The glyph channel. Three channels per state -- glyph, hue AND the literal
#: word -- is the rule `charts.py` already applies, for the reason it gives:
#: hue alone fails in grayscale, in print, and for a CVD reader, and these
#: surfaces become paper figures.
STATE_GLYPHS: dict[CoverageState, str] = {
    CoverageState.EVIDENCED: "█",  # full block
    CoverageState.INERT: "▒",  # medium shade
    CoverageState.SILENT: "░",  # light shade
    CoverageState.REFUSED: "·",  # middle dot: nothing was read
}


def state_for(*, detected: bool, inert: bool) -> CoverageState:
    """The one decision this module makes, in one place.

    Ordering matters. `inert` is tested *after* `detected` because an inert
    construct was detected and then discarded by the polarity policy -- calling
    that SILENT would hide a detection, and calling it EVIDENCED would claim the
    text moved an index it did not move.
    """
    if not detected:
        return CoverageState.SILENT
    return CoverageState.INERT if inert else CoverageState.EVIDENCED


@dataclass(frozen=True)
class SubscaleCoverage:
    """One construct's state, with the topic a reader could raise instead.

    `prompt` is derived from `config/taxonomy.yaml`'s own `definition` by
    `instruments.prompt_for`. It is **not** an instrument item: CSAI-2, the ABQ,
    CD-RISC and TAIS are copyrighted and reproducing their items would be a
    licensing violation. See `src/dashboard/instruments.py`.
    """

    construct: str
    plain_name: str
    state: CoverageState
    prompt: str

    @property
    def word(self) -> str:
        return STATE_WORDS[self.state]

    @property
    def glyph(self) -> str:
        return STATE_GLYPHS[self.state]


@dataclass(frozen=True)
class InstrumentCoverage:
    """One instrument's row: its subscales and how many were evidenced."""

    name: str
    citation: str
    subscales: tuple[SubscaleCoverage, ...]

    @property
    def evidenced_count(self) -> int:
        return sum(1 for s in self.subscales if s.state is CoverageState.EVIDENCED)

    @property
    def total(self) -> int:
        return len(self.subscales)

    @property
    def spoken_to(self) -> bool:
        """Whether this text gave the instrument any evidence at all.

        One evidenced subscale is enough. A stricter rule -- all subscales --
        was considered and rejected: it would report CSAI-2 as unspoken-to for a
        text that plainly discusses competitive worry, which is a different and
        falser claim than the one this panel makes.
        """
        return self.evidenced_count > 0

    @property
    def unevidenced(self) -> tuple[SubscaleCoverage, ...]:
        """The subscales this text did not evidence, in file order."""
        return tuple(s for s in self.subscales if s.state is not CoverageState.EVIDENCED)


@dataclass(frozen=True)
class CoverageLedger:
    """The whole projection, frozen, and inseparable from its provenance.

    Refuses to exist without a PROVISIONAL stamp -- the same shape as
    `ScoreSurface` and `BiosignalWindow`, and for the same reason. "2 of 8" is a
    number, it is the most quotable number this panel produces, and a screenshot
    of it without the stamp is a claim that this project measured coverage
    against something real. It did not: the corpus is synthetic (OPEN-011) and
    the cue list is unevaluated (OPEN-025).
    """

    instruments: tuple[InstrumentCoverage, ...]
    spoken_to: int
    total: int
    stamp: str

    def __post_init__(self) -> None:
        if PROVISIONAL_STAMP.split(" -- ")[0] not in self.stamp:
            raise ValueError(
                "CoverageLedger has no PROVISIONAL provenance stamp. '2 of 8' is the "
                "most quotable figure this panel produces and it is a property of a "
                "synthetic corpus scored by an unevaluated cue list, not a "
                "measurement of anybody."
            )

    @property
    def subscales(self) -> tuple[SubscaleCoverage, ...]:
        return tuple(s for row in self.instruments for s in row.subscales)

    def count(self, state: CoverageState) -> int:
        return sum(1 for s in self.subscales if s.state is state)

    @property
    def summary(self) -> str:
        """The headline, as one sentence. Never a percentage.

        A percentage of eight instruments reads as a completion rate and invites
        exactly the item-level misreading R2 is about. "2 of 8" carries its own
        denominator.
        """
        return f"This text speaks to {self.spoken_to} of {self.total} instruments."


def coverage_for(view: DashboardView) -> CoverageLedger:
    """Project one already-scored view onto the instrument set.

    Reads `view.bars` and nothing else. Introduces no number the view does not
    carry: every count below is a count of bars, and the stamp is the view's own.
    """
    instrument_set = load_instruments()
    by_construct = {bar.construct: bar for bar in view.bars}

    rows: list[InstrumentCoverage] = []
    for row in instrument_set.rows:
        subscales: list[SubscaleCoverage] = []
        for sub in row.subscales:
            bar = by_construct.get(sub.construct)
            if bar is None:
                raise KeyError(
                    f"the view carries no bar for {sub.construct!r}; instruments.yaml "
                    "and the live decomposition have drifted apart."
                )
            plain_name = CONSTRUCTS.get(sub.construct, (sub.construct.replace("_", " "), "", ""))[0]
            subscales.append(
                SubscaleCoverage(
                    construct=sub.construct,
                    plain_name=plain_name,
                    state=state_for(detected=bar.detected, inert=bar.inert),
                    prompt=sub.prompt,
                )
            )
        rows.append(
            InstrumentCoverage(
                name=row.instrument,
                citation=row.citation,
                subscales=tuple(subscales),
            )
        )

    instruments = tuple(rows)
    # Screened here as well as at `copy` import, because the prompts are derived
    # from `taxonomy.yaml` at runtime and so are not module-level strings the
    # reflective screen in `copy._screen` can see.
    for sub in (s for r in instruments for s in r.subscales):
        assert_no_forbidden_language(f"{sub.plain_name} {sub.prompt}")

    return CoverageLedger(
        instruments=instruments,
        spoken_to=sum(1 for r in instruments if r.spoken_to),
        total=len(instruments),
        stamp=view.risk.stamp,
    )
