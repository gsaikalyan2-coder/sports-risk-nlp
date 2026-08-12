"""Construct probabilities -> an interpretable pre-competition risk index.

What this layer is, and why it is deliberately simple
-----------------------------------------------------
Phase 14 produces, per utterance, ten numbers: the probability that each
taxonomy construct is present. This module turns those ten numbers into one
number in [0, 1] plus a **decomposition** -- how much each construct pushed the
score up or down.

The obvious implementation is to learn the fusion: train a second model mapping
ten construct probabilities to a risk target. That is not done here, for a reason
that decides the design. **There is no risk target.** No athlete in this corpus
has a measured pre-competition risk score; there is no CSAI-2 administration, no
outcome, no clinician rating. A learned fusion needs a supervision signal that
does not exist, and inventing one -- say, "risk = fraction of anxiety constructs
present" -- would be learning to predict a formula someone wrote down, dressed up
as a model.

So the fusion is **deterministic and declared**: a weighted sum whose weights come
from `config/taxonomy.yaml`'s `risk_direction` field, which is itself anchored to
published sports-psychology instruments. Every weight traces to a citation rather
than to a fit. `CLAUDE.md` sec.8 rule 4 -- prefer the option that is easier to
justify to a reviewer -- points the same way: "we sum construct evidence with signs
taken from the CSAI-2 and ABQ traditions" is defensible on its own, while "we
learned weights against a target we constructed" invites the question of where
the target came from, and the honest answer would be "we made it up".

`PROJECT_PLAN.md` Phase 15 leaves room for a learned variant later. The interface
below is built so that swapping `LinearRiskScorer` for a fitted scorer changes one
class and nothing else. When a real risk target exists -- an administered CSAI-2
alongside text, which is what OPEN-011's data conversation should try to secure --
that swap becomes possible and this docstring becomes wrong. It should be updated
then, not before.

Signs, and where they come from
-------------------------------
`config/taxonomy.yaml` records a `risk_direction` per construct. Six constructs
raise risk, four lower it, and four of the ten carry a *polarity* -- their
direction depends on which sub-label is present:

| construct | direction |
|---|---|
| `cognitive_anxiety` | raises |
| `somatic_anxiety` | raises |
| `perceived_stress` | raises |
| `burnout_signal` | raises |
| `self_confidence` | lowers |
| `resilience` | lowers |
| `motivation_orientation` | avoidance raises, approach lowers |
| `attentional_focus` | distracted raises, focused lowers |
| `coping_style` | avoidance raises, task-focused lowers |
| `appraisal_orientation` | threat raises, challenge lowers |

The polarity cases are the interesting ones and the taxonomy is explicit about
them: `resilience` and challenge-appraisal are **protective**, threat-appraisal
and debilitative interpretation are **aggravating**. A fusion that treated
"appraisal_orientation is present" as risk-raising regardless of whether the
athlete framed the event as a challenge or a threat would invert the construct's
meaning in half the cases, and would still produce a plausible-looking number.

Because the Phase 14 classifier is multi-label over construct *presence* and does
not currently emit sub-labels, polarity-bearing constructs are handled by
`PolarityPolicy` (below) rather than assumed. The default policy is the
conservative one: **treat an unresolved polarity as contributing nothing.**
Guessing "probably threat" would manufacture risk from the absence of
information, which for a construct whose whole point is that direction matters is
the worst available default.

The interpretation modifier
---------------------------
`config/taxonomy.yaml` defines a facilitative/debilitative modifier on the two
anxiety constructs: *the same anxiety intensity carries different risk depending
on how the athlete reads it* [Jones1992]. Two athletes equally nervous, one
energised and one unravelled, are not equally at risk. This is one of the things
that makes the project more than sentiment analysis, so the fusion carries it
explicitly as a multiplier on the anxiety terms rather than dropping it. Default
is `unclear`, which multiplies by 1.0 -- again, no guessing.

Squashing, and why not a plain average
--------------------------------------
The weighted sum is unbounded; the index must be in [0, 1]. A logistic squash is
used rather than min-max normalisation over the observed batch, because min-max
makes an individual's score depend on who else was scored in the same run --
the same athlete's text would receive a different risk index depending on the
batch it arrived in, which is indefensible for anything decision-adjacent.

The squash has a `temperature`, fitted in `src/risk/calibration.py`. Until it is
fitted the index is *ranked* correctly but not *calibrated*: 0.7 means "higher
than 0.5", not "70% of such athletes". `RiskScore.is_calibrated` carries that
distinction so a consumer cannot read a probability into an uncalibrated number.

Context features
----------------
`PROJECT_PLAN.md` Phase 15 requires the interface to accept optional light
non-text context (timing before competition, training load) so that multimodal
fusion is a drop-in later, while **text-only remains the primary reported model**.
`score()` therefore takes an optional `context` mapping and ignores it unless
`context_weights` were supplied. The text-only path is not merely the default; it
is a separate, tested code path, so adding context cannot silently change the
number the paper reports.

What this layer does not do
---------------------------
It does not decide anything about a person. `docs/ethics.md` and `CLAUDE.md`
sec.1 govern: this is a research and decision-support instrument, the constructs
are inferred from text rather than measured, and the classifier feeding it was
trained on synthetic data against planted labels (OPEN-025, OPEN-011). A risk
index computed from those inputs is a research artifact end to end. `RiskScore`
carries `provenance` so that fact travels with the number instead of being
attached to it in prose that gets dropped in the next copy-paste.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from math import exp
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"


class Direction(Enum):
    """Which way a construct moves risk."""

    RAISES = "raises"
    LOWERS = "lowers"
    #: Direction depends on a sub-label the presence classifier does not emit.
    POLAR = "polar"


class PolarityPolicy(Enum):
    """What to do with a polarity-bearing construct whose sub-label is unknown.

    `NEUTRAL` (default) contributes zero. The alternatives exist to be *ablated
    against* in Phase 18, not because either is a good default:

    * `PESSIMISTIC` assumes the risk-raising pole. It manufactures risk from
      missing information, which for a screening instrument is the direction that
      does harm -- it flags athletes on the basis of an absent sub-label.
    * `OPTIMISTIC` assumes the protective pole and hides risk for the same reason.

    Reporting the three side by side quantifies how much of the index depends on
    an unresolved modelling gap, which is more useful than picking one and hoping.
    """

    NEUTRAL = "neutral"
    PESSIMISTIC = "pessimistic"
    OPTIMISTIC = "optimistic"


#: Default magnitudes. Deliberately coarse -- three tiers, not ten hand-tuned
#: decimals.
#:
#: A reviewer asking "why is cognitive_anxiety 0.87 and perceived_stress 0.63?"
#: deserves an answer, and with no risk target to fit against there is no honest
#: one. Coarse tiers give a defensible answer instead: the two anxiety constructs
#: and burnout carry the most weight because they are the constructs the CSAI-2
#: and ABQ traditions treat as primary indicators of maladaptive pre-competition
#: state; the rest carry standard weight.
#:
#: `reports/calibration.md` runs a sensitivity check over these, because a
#: conclusion that survives only at one weighting is a conclusion about the
#: weighting.
DEFAULT_MAGNITUDES: dict[str, float] = {
    "cognitive_anxiety": 1.5,
    "somatic_anxiety": 1.0,
    "perceived_stress": 1.0,
    "burnout_signal": 1.5,
    "self_confidence": 1.0,
    "resilience": 1.0,
    "motivation_orientation": 1.0,
    "attentional_focus": 1.0,
    "coping_style": 1.0,
    "appraisal_orientation": 1.0,
}

#: Multiplier on the anxiety terms, from the taxonomy's interpretation modifier.
#: `unclear` is 1.0 and is the default: bare reports of anxiety do not get a
#: direction guessed for them.
INTERPRETATION_MULTIPLIER: dict[str, float] = {
    "facilitative": 0.5,
    "debilitative": 1.5,
    "unclear": 1.0,
}


def load_directions(path: Path | None = None) -> dict[str, Direction]:
    """Read `risk_direction` per construct from `config/taxonomy.yaml`.

    Parsed from the taxonomy rather than restated here, so the sign of a
    construct's contribution cannot drift away from the file the annotation
    guidelines are written against. If Phase 12's freeze is ever lifted and a
    direction changes, the fusion follows automatically.

    The taxonomy states polarity cases as prose ("avoidance raises risk; approach
    lowers it") rather than as an enum, so anything that is not exactly `raises`
    or `lowers` is treated as `POLAR`. That is a conservative read: an
    unrecognised direction becomes a construct whose contribution defaults to
    zero, rather than one silently assigned a sign.
    """
    source = path or TAXONOMY_PATH
    taxonomy = yaml.safe_load(source.read_text(encoding="utf-8"))
    out: dict[str, Direction] = {}
    for name, body in taxonomy["constructs"].items():
        raw = str(body.get("risk_direction", "")).strip().lower()
        if raw == "raises":
            out[name] = Direction.RAISES
        elif raw == "lowers":
            out[name] = Direction.LOWERS
        else:
            out[name] = Direction.POLAR
    return out


@dataclass(frozen=True)
class Contribution:
    """One construct's push on the risk index, with everything needed to explain it.

    This dataclass is the unit of the paper's *second* contribution -- two-level
    interpretability. The first level is span -> construct (Phase 17); this is the
    second, construct -> risk. A number without `probability`, `direction` and
    `weight` alongside it cannot be shown to a coach and defended, so they travel
    together rather than being reconstructible in principle.
    """

    construct: str
    probability: float
    direction: Direction
    weight: float
    #: `probability * weight`, signed. The quantity actually summed.
    contribution: float
    #: Set when a polarity construct was zeroed for want of a sub-label.
    polarity_unresolved: bool = False

    def as_sentence(self) -> str:
        """Human-readable, for profile cards and the dashboard.

        Readability here is a **gate condition** for Phase 15, not decoration.
        """
        if self.polarity_unresolved:
            return (
                f"{self.construct}: detected (p={self.probability:.2f}) but its direction "
                f"is unresolved, so it did not move the score"
            )
        if self.contribution == 0:
            return f"{self.construct}: not detected (p={self.probability:.2f}), no effect"
        verb = "raised" if self.contribution > 0 else "lowered"
        return (
            f"{self.construct}: detected (p={self.probability:.2f}), {verb} the score "
            f"by {abs(self.contribution):.2f}"
        )


@dataclass(frozen=True)
class RiskScore:
    """A risk index and the full account of how it was produced.

    `provenance` and `is_calibrated` are not metadata in the decorative sense.
    They are the reason this dataclass exists instead of a bare float: a float
    labelled "risk: 0.71" that escapes into a slide is a claim about a person,
    and there is nothing attached to it that says the classifier was trained on
    synthetic text against planted labels.
    """

    index: float
    raw_score: float
    contributions: tuple[Contribution, ...]
    is_calibrated: bool
    provenance: str
    context_used: tuple[str, ...] = ()

    @property
    def top_drivers(self) -> tuple[Contribution, ...]:
        """Contributions sorted by absolute effect, largest first."""
        return tuple(sorted(self.contributions, key=lambda c: -abs(c.contribution)))

    def explain(self, *, limit: int = 4) -> str:
        """A short, readable account of the score. Phase 15's gate checks this."""
        lines = [
            f"Risk index {self.index:.2f}"
            + ("" if self.is_calibrated else "  (RANKING ONLY -- not calibrated)"),
            f"  {self.provenance}",
        ]
        movers = [c for c in self.top_drivers if c.contribution != 0][:limit]
        if not movers:
            lines.append("  No construct moved the score.")
        for contribution in movers:
            lines.append(f"  - {contribution.as_sentence()}")
        unresolved = [c for c in self.contributions if c.polarity_unresolved]
        if unresolved:
            lines.append(
                f"  ({len(unresolved)} construct(s) detected but directionally "
                f"unresolved, so excluded: "
                f"{', '.join(c.construct for c in unresolved)})"
            )
        if self.context_used:
            lines.append(f"  Context features used: {', '.join(self.context_used)}")
        return "\n".join(lines)


def _logistic(value: float, temperature: float) -> float:
    """Numerically safe logistic squash.

    The guard matters: `exp(800)` overflows, and an overflow here would surface
    as a crash halfway through a scoring run rather than as a saturated score.
    """
    scaled = value / temperature if temperature else value
    if scaled >= 0:
        return 1.0 / (1.0 + exp(-min(scaled, 700.0)))
    return exp(max(scaled, -700.0)) / (1.0 + exp(max(scaled, -700.0)))


@dataclass
class LinearRiskScorer:
    """Deterministic, taxonomy-grounded construct -> risk fusion.

    Not fitted to anything, by design (see the module docstring). `temperature`
    is the one free parameter and it is set by `src/risk/calibration.py` against
    held-out data; until then the scorer reports `is_calibrated=False` and every
    consumer can see the score is a ranking rather than a probability.
    """

    directions: dict[str, Direction] = field(default_factory=load_directions)
    magnitudes: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_MAGNITUDES))
    polarity_policy: PolarityPolicy = PolarityPolicy.NEUTRAL
    temperature: float = 1.0
    is_calibrated: bool = False
    #: Optional weights for light non-text context. Empty means the text-only
    #: path, which is the primary reported model (`PROJECT_PLAN.md` Phase 15).
    context_weights: dict[str, float] = field(default_factory=dict)
    provenance: str = (
        "Research artifact. Constructs inferred from text by a classifier trained "
        "on synthetic data against planted labels; no human-verified labels exist "
        "(OPEN-025) and no real athlete text has been used (OPEN-011). Not a "
        "clinical instrument and not a judgement about any real person."
    )

    def _signed_weight(
        self,
        construct: str,
        polarity: str | None,
    ) -> tuple[float, bool]:
        """Signed weight for a construct, plus whether its polarity was unresolved.

        Returns `(0.0, True)` when the construct is polarity-bearing, no sub-label
        was supplied, and the policy is `NEUTRAL` -- the conservative default. See
        `PolarityPolicy`.
        """
        magnitude = self.magnitudes.get(construct, 1.0)
        direction = self.directions.get(construct, Direction.POLAR)

        if direction is Direction.RAISES:
            return magnitude, False
        if direction is Direction.LOWERS:
            return -magnitude, False

        # Polar. A caller-supplied sub-label resolves it definitively.
        if polarity is not None:
            raising = {"avoidance", "distracted", "threat", "debilitative"}
            lowering = {"approach", "focused", "task_focused", "challenge", "facilitative"}
            if polarity in raising:
                return magnitude, False
            if polarity in lowering:
                return -magnitude, False
            # An unrecognised sub-label is not silently treated as neutral-by-luck;
            # it falls through to the policy below, and the caller sees
            # `polarity_unresolved=True` in the decomposition.

        if self.polarity_policy is PolarityPolicy.PESSIMISTIC:
            return magnitude, True
        if self.polarity_policy is PolarityPolicy.OPTIMISTIC:
            return -magnitude, True
        return 0.0, True

    def score(
        self,
        probabilities: Mapping[str, float],
        *,
        polarities: Mapping[str, str] | None = None,
        interpretation: str = "unclear",
        context: Mapping[str, float] | None = None,
    ) -> RiskScore:
        """Fuse one utterance's construct probabilities into a risk index.

        `probabilities` maps construct name -> P(present), as emitted by
        `TransformerBaseline.predict_proba`. `polarities` optionally resolves the
        four polarity-bearing constructs. `interpretation` applies the
        facilitative/debilitative modifier to the anxiety terms. `context` is
        ignored unless `context_weights` were configured -- the text-only path is
        primary and stays numerically identical whether or not context is passed.
        """
        polarities = polarities or {}
        multiplier = INTERPRETATION_MULTIPLIER.get(interpretation, 1.0)

        contributions: list[Contribution] = []
        total = 0.0
        for construct in sorted(self.magnitudes):
            probability = float(probabilities.get(construct, 0.0))
            weight, unresolved = self._signed_weight(construct, polarities.get(construct))
            if construct in ("cognitive_anxiety", "somatic_anxiety"):
                weight *= multiplier
            contribution = probability * weight
            total += contribution
            contributions.append(
                Contribution(
                    construct=construct,
                    probability=probability,
                    direction=self.directions.get(construct, Direction.POLAR),
                    weight=weight,
                    contribution=contribution,
                    polarity_unresolved=unresolved and probability > 0.0,
                )
            )

        used: list[str] = []
        if self.context_weights and context:
            for name, weight in sorted(self.context_weights.items()):
                if name in context:
                    total += float(context[name]) * weight
                    used.append(name)

        return RiskScore(
            index=_logistic(total, self.temperature),
            raw_score=total,
            contributions=tuple(contributions),
            is_calibrated=self.is_calibrated,
            provenance=self.provenance,
            context_used=tuple(used),
        )

    def score_many(
        self,
        rows: Sequence[Mapping[str, float]],
        **kwargs: Any,
    ) -> list[RiskScore]:
        """Score a batch.

        Each row is scored independently and identically. No batch statistic
        enters any score -- see the module docstring on why min-max normalisation
        was rejected. This is asserted in `tests/test_risk.py`, because it is the
        kind of property that a later "optimisation" quietly breaks.
        """
        return [self.score(row, **kwargs) for row in rows]

    def manifest(self) -> dict[str, Any]:
        """Everything needed to reproduce or audit a scoring run."""
        return {
            "scorer": "LinearRiskScorer",
            "fitted": False,
            "why_not_fitted": (
                "No risk target exists. No athlete in this corpus has a measured "
                "pre-competition risk score, so a learned fusion would be fitting an "
                "invented target."
            ),
            "directions": {k: v.value for k, v in sorted(self.directions.items())},
            "magnitudes": dict(sorted(self.magnitudes.items())),
            "interpretation_multiplier": dict(INTERPRETATION_MULTIPLIER),
            "polarity_policy": self.polarity_policy.value,
            "temperature": self.temperature,
            "is_calibrated": self.is_calibrated,
            "context_weights": dict(sorted(self.context_weights.items())),
            "text_only": not self.context_weights,
            "provenance": self.provenance,
        }
