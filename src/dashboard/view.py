"""The honesty layer. Everything the dashboard shows passes through here.

Why this module exists at all
------------------------------
It would be shorter to compute the bars inside the Streamlit callback. That is
precisely the arrangement `handover_phase_19.txt` C1 warns about: three phases
running, the check and the thing it protects were related by *assumption*. A
property enforced inside a Streamlit callback is a property no test can assert,
so "the card renders" quietly becomes the only thing anyone checks.

So the constraints from C2 are enforced *by construction* here, not documented
here:

* **A view cannot exist without the publication guard having run.**
  `assert_publication_safe` is called in `DashboardView.__post_init__` and
  records itself on the instance. A card carrying non-synthetic text does not
  raise -- pasted text is the user's own and may be shown back to them -- but the
  view is marked non-exportable and `export_markdown` re-raises. There is no
  third state.
* **A number cannot exist without its provenance.** `ScoreSurface` refuses an
  empty or unrecognised stamp at construction, the same trick
  `ExplanationCard.provenance` already uses. The stamp is not attached at render
  time, because the render is the step most likely to be reimplemented.
* **Inertness is read off the scorer, never hardcoded.** A construct is inert
  when its direction is `POLAR` *and* the active policy gave it zero weight.
  Under `PolarityPolicy.PESSIMISTIC` nothing is inert and the marking follows
  automatically. A name list would have been correct today and wrong the first
  time anyone ablated the policy -- and the picture would have asserted something
  the numbers did not.
* **Forbidden vocabulary is rejected at construction**, and screened again over
  the fully rendered surface. Both, because the first catches the labels this
  module writes and the second catches the ones it merely passes through.

Nothing here persists anything. There is no cache, no log, no session file. The
user's pasted text lives in a local variable for the duration of one render.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from src.dashboard.backend import BackendResult, PredictionBackend, ReplayBackend
from src.evaluation.harness import PROVISIONAL_STAMP
from src.explainability.attribution import SpanAttribution
from src.explainability.cards import (
    ExplanationCard,
    PublicationUnsafe,
    assert_publication_safe,
    build_card,
    render_markdown,
)
from src.risk.fusion import Direction, LinearRiskScorer, PolarityPolicy

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"

#: Vocabulary that may not reach any surface a reader sees.
#:
#: The first three are fixed by `docs/findings.md` sec.2.4: OPEN-004 was closed by
#: *decision*, not by recruitment, and closing a tracking item does not upgrade a
#: claim. The expert half of Phase 17 shipped as a pilot self-audit with
#: sports-familiar student raters; no coach or sport-psychology practitioner
#: rated anything.
#:
#: The fourth is the constraint that governs the whole repository. `data/gold/`
#: is empty, so there is no accuracy anywhere -- only agreement with labels this
#: project's own generator planted.
FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "expert-validated",
    "practitioner-validated",
    "coach-validated",
    "accuracy",
    "confidence in the athlete",
    "confidence in this athlete",
)

#: Fixed by `docs/findings.md` sec.2.4. Quoted verbatim wherever the pilot study
#: is mentioned, or not mentioned at all.
PILOT_STUDY_WORDING = (
    "Explanations were reviewed in a blinded pilot study by sports-familiar student "
    "raters. This is a pilot expert review, not practitioner validation: no coach or "
    "sport-psychology practitioner rated the explanations. Practitioner validation is "
    "the principal outstanding item for this contribution."
)

#: Fixed by `docs/findings.md` sec.3.3. The decomposition may not be called
#: ten-construct without this qualification attached.
SIX_OF_TEN_WORDING = (
    "The fusion layer decomposes risk over ten constructs, of which six carry a fixed "
    "direction under the default conservative policy; the remaining four are detected "
    "and displayed but do not move the index unless an interpretation direction is "
    "resolved."
)

CONTEXT_INERT_NOTICE = (
    "A non-verbal reading was taken from the uploaded file and is shown below, but it "
    "carries a weight of exactly zero: the score above was produced from words alone "
    "and is bit-identical to the score the same words would get with no file attached."
)

CONTEXT_ACTIVE_NOTICE = (
    "The non-verbal channel is switched ON, so values derived from the uploaded file "
    "moved the score. Those values are not a measurement of anyone and the weighting "
    "behind them was declared rather than fitted. No number produced this way appears "
    "in the paper, which is text-only throughout."
)

RANKING_NOTICE = "Risk index is a ranking only -- not calibrated. No observed outcome exists to calibrate against, and src/risk/calibration.py refuses to run."

LIVE_TEXT_NOTICE = (
    "The text above is yours. It is not stored, not logged, not cached and cannot be "
    "exported to a figure -- only records from the synthetic corpus can be."
)

#: The policies a reader may switch between on the page, in their own words.
#:
#: Exposed here rather than in the Streamlit shell because the shell may not
#: import `src.risk` (see `tests/test_dashboard.py`) and, more importantly,
#: because the label a reader sees and the policy the arithmetic uses have to be
#: the same fact. A selectbox holding its own strings would be a fourth place
#: for the two to drift apart.
POLICY_LABELS: dict[str, PolarityPolicy] = {
    "Conservative: the default, and what the paper reports": PolarityPolicy.NEUTRAL,
    "Pessimistic: read every unresolved signal as bad news": PolarityPolicy.PESSIMISTIC,
    "Optimistic: read every unresolved signal as good news": PolarityPolicy.OPTIMISTIC,
}

DEFAULT_POLICY_LABEL = "Conservative: the default, and what the paper reports"

#: Attached to every view, so the policy in force is part of the screened
#: surface rather than a widget state nobody can test.
POLICY_NOTES: dict[PolarityPolicy, str] = {
    PolarityPolicy.NEUTRAL: (
        "Polarity policy: conservative (the default). The four constructs whose "
        "direction is unresolved are detected, displayed, and given a weight of "
        "exactly zero. This is the policy every number in the paper uses."
    ),
    PolarityPolicy.PESSIMISTIC: (
        "Polarity policy: pessimistic. Every unresolved construct is read as the "
        "unfavourable side, so all ten constructs move the index and nothing is "
        "inert. This is an exploration of the fusion layer, not a result: no number "
        "produced under it appears in the paper."
    ),
    PolarityPolicy.OPTIMISTIC: (
        "Polarity policy: optimistic. Every unresolved construct is read as the "
        "favourable side. Like the pessimistic setting, this is an exploration of "
        "the fusion layer and produces no number the paper reports."
    ),
}


#: What the policy does to the four two-sided constructs, in tile-sized words.
#:
#: Keyed by `PolarityPolicy.value` rather than by the enum, so the Streamlit
#: shell and `widgets.py` can read it without importing `src.risk` -- the same
#: reason `POLICY_LABELS` lives here rather than in the page.
POLICY_TILE_NOTE: dict[str, str] = {
    "neutral": "two-sided, counted as zero under the conservative default",
    "pessimistic": "two-sided, read as the unfavourable side under this setting",
    "optimistic": "two-sided, read as the favourable side under this setting",
}

#: The short name of the assumption in force, for a tile that has room for three
#: words and not for thirty.
POLICY_SHORT: dict[str, str] = {
    "neutral": "conservative",
    "pessimistic": "pessimistic",
    "optimistic": "optimistic",
}


def scorer_for(
    label: str,
    *,
    context_weights: Mapping[str, float] | None = None,
) -> LinearRiskScorer:
    """The scorer a reader's policy choice selects.

    The only way `dashboard/app.py` can vary the fusion policy. It cannot build a
    `LinearRiskScorer` itself -- the shell may not import `src.risk` at all -- so
    an unlabelled or invented policy cannot reach the arithmetic.

    `context_weights` is the seam for the Phase 27 non-verbal channel and
    defaults to nothing at all. Empty weights is the text-only path in
    `fusion.score`, which is separately tested to produce a bit-identical index
    whether or not a context mapping is passed alongside it. So a page may
    always pass context; only a page that also passes weights can move a number
    with it, and that call site is visible in the diff.
    """
    try:
        policy = POLICY_LABELS[label]
    except KeyError:
        raise ValueError(
            f"{label!r} is not one of the offered polarity policies: {sorted(POLICY_LABELS)}"
        ) from None
    return LinearRiskScorer(polarity_policy=policy, context_weights=dict(context_weights or {}))


INERT_NOTE = "detected but does not move the index (direction unresolved under the conservative default policy)"


class ForbiddenLanguage(ValueError):
    """A surface used wording the project has forbidden."""


def _accuracy_claims(low: str) -> list[int]:
    """Offsets of every use of "accuracy" that is not an explicit denial.

    This exception exists because the guard caught the required provenance stamp
    on its first run: `PROVISIONAL_STAMP` reads "... corpus-property measurement,
    NOT accuracy", so a flat substring ban makes the mandated stamp unshippable
    and the two rules contradict each other.

    The resolution is narrow on purpose. The forbidden thing is a *claim* of
    accuracy; "not accuracy" is the opposite of a claim, and it is the only
    construction allowed through. It is matched literally rather than by trying
    to detect negation in general -- a cleverer rule would let
    "no reason to doubt the accuracy" through, which is a claim wearing a
    negation. If a future surface needs another phrasing, it adds a literal here
    and a test beside it, deliberately, rather than the guard quietly widening.
    """
    return [
        match.start()
        for match in re.finditer(r"accuracy", low)
        if not low[: match.start()].endswith("not ")
    ]


def assert_no_forbidden_language(text: str) -> None:
    """Refuse a string containing wording the paper may not use.

    Case-insensitive and substring-based on purpose: `"Expert-Validated"` and
    `"detection accuracy"` are both the mistake, and a word-boundary check would
    let the second through.
    """
    low = text.lower()
    for term in FORBIDDEN_SUBSTRINGS:
        if term == "accuracy":
            if _accuracy_claims(low):
                raise ForbiddenLanguage(
                    "'accuracy' may not appear on any surface a reader sees except as "
                    "the literal denial 'not accuracy'. data/gold/ is empty (OPEN-025): "
                    "there is no accuracy in this repository, only agreement with "
                    "generator-planted labels."
                )
            continue
        if term in low:
            raise ForbiddenLanguage(
                f"{term!r} may not appear on any surface a reader sees. "
                "See docs/findings.md sec.2.4 and sec.5, and src/dashboard/view.py's "
                "FORBIDDEN_SUBSTRINGS."
            )


@dataclass(frozen=True)
class ScoreSurface:
    """A number shown to a user, inseparable from the statement of what it is.

    A bare float labelled "risk 0.71" that escapes into a slide is a claim about
    a person. `RiskScore` already makes that argument for the risk layer; this
    makes it for every other number the dashboard puts on screen.
    """

    label: str
    value: float
    display: str
    detail: str = ""
    stamp: str = PROVISIONAL_STAMP

    def __post_init__(self) -> None:
        if PROVISIONAL_STAMP.split(" -- ")[0] not in self.stamp:
            raise ValueError(
                f"ScoreSurface({self.label!r}) has no PROVISIONAL provenance stamp. "
                "Every number in this repository is agreement with generator-planted "
                "labels on synthetic text; see src/evaluation/harness.py."
            )
        assert_no_forbidden_language(f"{self.label} {self.detail}")


@dataclass(frozen=True)
class ConstructBar:
    """One construct's row: how strongly it was detected, and what it did to risk.

    Both numbers are carried because either alone misleads. Probability without
    contribution suggests a strongly detected construct drove the score;
    contribution without probability hides that four constructs are detected and
    then discarded.
    """

    construct: str
    probability: float
    contribution: float
    weight: float
    direction: str
    inert: bool
    detected: bool
    spans: tuple[SpanAttribution, ...]
    note: str

    @property
    def has_evidence(self) -> bool:
        return bool(self.spans)


@dataclass(frozen=True)
class DashboardView:
    """Everything one screen shows, already checked.

    Construct through `build_view`. Direct construction is not forbidden -- the
    guards are in `__post_init__` and run either way -- but `build_view` is the
    only path the tests exercise and the only one `dashboard/app.py` may use.
    """

    card: ExplanationCard
    bars: tuple[ConstructBar, ...]
    risk: ScoreSurface
    surfaces: tuple[ScoreSurface, ...]
    scale_label: str
    source: str
    caveat: str
    notices: tuple[str, ...] = ()
    policy_note: str = POLICY_NOTES[PolarityPolicy.NEUTRAL]
    #: `PolarityPolicy.value` for the policy that produced these numbers. A
    #: plain string, so the render layer can branch on it without importing
    #: `src.risk`, and part of the screened surface rather than a widget state.
    policy_key: str = PolarityPolicy.NEUTRAL.value
    is_default_policy: bool = True
    publication_checked: bool = field(default=False, init=False)
    exportable: bool = field(default=False, init=False)
    unsafe_reason: str = field(default="", init=False)

    def __post_init__(self) -> None:
        try:
            assert_publication_safe((self.card,))
        except PublicationUnsafe as exc:
            object.__setattr__(self, "exportable", False)
            object.__setattr__(self, "unsafe_reason", str(exc))
        else:
            object.__setattr__(self, "exportable", True)
        # Set last, and only after the guard has actually run, so the flag cannot
        # be true for a view that skipped it.
        object.__setattr__(self, "publication_checked", True)
        assert_no_forbidden_language(self.render_text())

    # -- rendering ---------------------------------------------------------

    def render_text(self) -> str:
        """The complete textual surface of this view, as one string.

        Exists so the honesty tests can screen *what a reader sees* rather than
        what a template contains. Anything the app displays must appear here, or
        the screening has a hole in it -- see `dashboard/app.py`, which renders
        only from this object.
        """
        lines: list[str] = [
            f"Source: {self.source}",
            f"Bar scale: {self.scale_label}",
            self.caveat,
            "",
            self.policy_note,
            f"{self.risk.label}: {self.risk.display}",
            RANKING_NOTICE,
            self.risk.detail,
            "",
            SIX_OF_TEN_WORDING,
            "",
        ]
        for bar in self.bars:
            spans = (
                "; ".join(f"{s.text!r} ({s.score:+.2f})" for s in bar.spans)
                if bar.spans
                else "no supporting span"
            )
            lines.append(
                f"{bar.construct}: p={bar.probability:.2f} "
                f"contribution={bar.contribution:+.3f} [{bar.direction}] "
                f"-- {bar.note} -- evidence: {spans}"
            )
        lines.append("")
        lines.extend(self.notices)
        lines.append("")
        lines.append(self.card.provenance)
        lines.append(self.card.risk.provenance)
        lines.append(PROVISIONAL_STAMP)
        return "\n".join(lines)

    def export_markdown(self) -> str:
        """The Phase 17 card, unmodified, for the paper figure.

        Delegates to `src.explainability.cards.render_markdown` and adds nothing.
        C2.6: if the dashboard re-derived the highlighting, the paper figure and
        the demo would drift apart and one of them would then be wrong. The gate
        test compares this output to `reports/explain/cards.md` character for
        character, which is what makes that binding rather than aspirational.
        """
        if not self.exportable:
            raise PublicationUnsafe(
                self.unsafe_reason
                or "This view is built from text that is not part of the synthetic "
                "corpus and cannot be exported."
            )
        return render_markdown(self.card)

    @property
    def raw_score(self) -> float:
        """The weighted sum before the logistic squash.

        Surfaced so the waterfall chart can show the step every reader asks
        about -- how contributions summing to +1.9 become an index of 0.87 --
        without the Streamlit shell reaching into `card.risk` itself.
        """
        return self.card.risk.raw_score

    @property
    def two_sided_detected(self) -> int:
        """How many of the two-sided constructs this text actually triggered.

        The number that decides whether the policy selector does anything
        visible. It is entirely possible for a text to trigger none of them, and
        the first committed known example does exactly that: moving the selector
        changes the stated assumption and leaves every number identical, which
        reads as a broken control rather than as an honest one. Surfaced so the
        page can say which case the reader is in instead of leaving them to
        guess.
        """
        return sum(1 for bar in self.bars if bar.direction == "polar" and bar.detected)

    @property
    def evidenced_driver_count(self) -> int:
        """Drivers that do point at a span. The complement of the count below."""
        return len(self.card.drivers) - len(self.card.unevidenced_drivers)

    @property
    def unevidenced_driver_count(self) -> int:
        """Constructs that moved the index while pointing at nothing.

        Surfaced rather than hidden, exactly as `reports/explain/` counts it:
        104 of 120 driver rows (86.7%) corpus-wide. It is the honest boundary of
        the two-level claim and the most self-critical number the project has.
        """
        return len(self.card.unevidenced_drivers)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def _bars_for(card: ExplanationCard) -> tuple[ConstructBar, ...]:
    """One row per construct, with inertness derived from the live decomposition.

    A construct is inert when the scorer gave it `Direction.POLAR` *and* a weight
    of exactly zero -- which is what `PolarityPolicy.NEUTRAL` does to a
    polarity-bearing construct with no resolved sub-label. Reading both fields
    rather than a name list is the whole point: swap the policy and the marking
    follows, because the marking is the same fact the arithmetic used.
    """
    by_construct = {e.contribution.construct: e for e in card.evidence}
    bars: list[ConstructBar] = []
    for construct in sorted(by_construct):
        evidence = by_construct[construct]
        contribution = evidence.contribution
        inert = contribution.direction is Direction.POLAR and contribution.weight == 0.0
        detected = contribution.probability > 0.0
        if inert:
            note = INERT_NOTE
        elif not detected:
            note = "not detected"
        elif not evidence.spans:
            note = "moved the index with no supporting span"
        else:
            verb = "raises" if contribution.contribution > 0 else "lowers"
            note = f"{verb} the index, with supporting spans"
        bars.append(
            ConstructBar(
                construct=construct,
                probability=contribution.probability,
                contribution=contribution.contribution,
                weight=contribution.weight,
                direction=contribution.direction.value,
                inert=inert,
                detected=detected,
                spans=evidence.spans,
                note=note,
            )
        )
    return tuple(bars)


def _view_from_result(
    result: BackendResult,
    *,
    scorer: LinearRiskScorer,
    top_spans: int,
    context: Mapping[str, float] | None = None,
) -> DashboardView:
    risk = scorer.score(result.probabilities, context=dict(context) if context else None)
    card = build_card(
        explanation=result.explanation,
        risk=risk,
        synthetic=result.synthetic,
        top_spans=top_spans,
    )
    bars = _bars_for(card)
    n_inert = sum(1 for b in bars if b.inert)
    unevidenced = len(card.unevidenced_drivers)

    risk_surface = ScoreSurface(
        label="Risk index",
        value=risk.index,
        display=f"{risk.index:.2f}",
        detail=(
            f"{len(bars) - n_inert} of {len(bars)} constructs can move this number; "
            f"{n_inert} are detected but directionally unresolved."
        ),
    )
    surfaces = (
        risk_surface,
        ScoreSurface(
            label="Constructs contributing",
            value=float(len(bars) - n_inert),
            display=f"{len(bars) - n_inert} of {len(bars)}",
            detail="the remaining four carry no sign under the conservative default",
        ),
        ScoreSurface(
            label="Drivers with no supporting span",
            value=float(unevidenced),
            display=f"{unevidenced} of {len(card.drivers)}",
            detail=(
                "constructs that moved the index while no span in the text supports "
                "them; corpus-wide this is 104 of 120 driver rows"
            ),
        ),
    )

    notices: list[str] = []
    if not result.synthetic:
        notices.append(LIVE_TEXT_NOTICE)
    notices.append(PILOT_STUDY_WORDING)
    policy = scorer.polarity_policy
    if policy is not PolarityPolicy.NEUTRAL:
        # Loudest where it matters: a reader who changed the policy and then
        # screenshots the page must carry the reason the number moved.
        notices.append(POLICY_NOTES[policy])
    if context:
        # Said whether or not the weights are non-empty, because "context was
        # supplied" and "context changed the number" are different facts and the
        # reader is entitled to both. `scorer.context_weights` is the one that
        # decides, so it is the one quoted.
        if scorer.context_weights:
            notices.append(CONTEXT_ACTIVE_NOTICE)
        else:
            notices.append(CONTEXT_INERT_NOTICE)
    notices.append(
        "Research and decision-support only. This is not a clinical instrument and "
        "makes no individual-level claim about any identifiable person."
    )

    return DashboardView(
        card=card,
        bars=bars,
        risk=risk_surface,
        surfaces=surfaces,
        scale_label=result.scale_label,
        source=result.source,
        caveat=result.caveat,
        notices=tuple(notices),
        policy_note=POLICY_NOTES[scorer.polarity_policy],
        policy_key=scorer.polarity_policy.value,
        is_default_policy=scorer.polarity_policy is PolarityPolicy.NEUTRAL,
    )


def build_view(
    *,
    text: str | None = None,
    example_id: str | None = None,
    backend: PredictionBackend | None = None,
    scorer: LinearRiskScorer | None = None,
    top_spans: int = 3,
    context: Mapping[str, float] | None = None,
) -> DashboardView:
    """The dashboard's single entry point.

    Supply `example_id` to replay a committed known example, or `text` to score
    something live. Exactly one, because "score this text, or if you can't, show
    me a cached example that looks similar" is how a demo starts implying it did
    work it did not do.
    """
    if (text is None) == (example_id is None):
        raise ValueError("Pass exactly one of `text` or `example_id`.")
    scorer = scorer or LinearRiskScorer()

    if example_id is not None:
        if not isinstance(backend, ReplayBackend):
            raise TypeError("`example_id` requires a ReplayBackend.")
        result = backend.get(example_id)
    else:
        if backend is None:
            raise ValueError("Live scoring requires a backend.")
        assert text is not None
        if not text.strip():
            raise ValueError("Nothing to score.")
        result = backend.predict(text)

    return _view_from_result(result, scorer=scorer, top_spans=top_spans, context=context)


def known_examples(fixture_path: Path | None = None) -> ReplayBackend:
    """The committed known examples, as a ready backend."""
    return ReplayBackend.from_fixture(fixture_path or DEFAULT_FIXTURE)
