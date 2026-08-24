"""Phase 18 -- ablations, risk-layer sensitivity, and the claim ledger.

`PROJECT_PLAN.md` Phase 18 names three ablations: baseline vs transformer,
+/- silver data, and +/- risk fusion. Two of the three cannot be run as written,
and the interesting engineering in this module is what happens instead.

**+/- silver.** OPEN-028: no live OpenRouter call has ever been made (OPEN-008),
so all 9,302 silver labels are `rng.randrange` output keyed on the prompt hash.
"Train with silver added" is therefore "train with noise added", and running it
on the transformer costs ~5 hours of CPU to measure a fact already known by
construction. It is run on the *classical* models instead -- seconds, no torch --
where it demonstrates the collapse rather than asserting it, and the transformer
arm is **refused in writing** with the rationale attached. A refusal that carries
its reason is evidence; a missing table row is a gap a reviewer fills in for you.

**+/- risk fusion.** There is no observed risk outcome anywhere in this project.
`src/risk/calibration.calibrate_risk_index` raises rather than substituting a
proxy, and that decision (Phase 15) binds here: scoring the fused index against a
target derived from planted labels would measure whether the model recovers this
project's own generator, which is circular. So "+/- fusion" becomes a
**structural sensitivity analysis** -- what the fusion layer *does*, quantified,
with no accuracy claim attached:

1. Which constructs actually move the index, and by how much.
2. How much the unresolved-polarity default changes the ranking (the
   `PolarityPolicy` question a reviewer will ask).
3. Whether taxonomy-grounded fusion orders records any differently from naively
   counting detected constructs. If it does not, the fusion layer is decoration,
   and that is a finding the paper should report rather than hide.

**The claim ledger** implements the Phase 18 gate literally. The gate is "every
claim the paper will make is backed by a logged experiment", which is only
checkable if the claims are enumerated somewhere a program can read. `CLAIMS`
below is that enumeration; `ClaimLedger.unbacked()` is the gate.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src.evaluation.harness import Comparison
from src.risk.fusion import LinearRiskScorer, PolarityPolicy


class AblationStatus(Enum):
    """Why an ablation row looks the way it does.

    `REFUSED` and `UNMEASURABLE` are deliberately distinct. Refused means the
    experiment is runnable and we chose not to run it, with a reason. Unmeasurable
    means the experiment cannot be run because the data it needs does not exist.
    Collapsing them into "not done" loses the distinction a reviewer cares about.
    """

    MEASURED = "measured"
    REFUSED = "refused"
    UNMEASURABLE = "unmeasurable"


@dataclass(frozen=True)
class Ablation:
    """One ablation, measured or explicitly not."""

    id: str
    question: str
    status: AblationStatus
    rationale: str
    comparison: Comparison | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status is AblationStatus.MEASURED and self.comparison is None and not self.detail:
            raise ValueError(
                f"ablation {self.id!r} claims MEASURED but carries neither a comparison nor "
                "detail. A measured ablation with no measurement in it is the OPEN-007 "
                "failure mode wearing a green badge."
            )
        if self.status is not AblationStatus.MEASURED and not self.rationale.strip():
            raise ValueError(
                f"ablation {self.id!r} is {self.status.value} with no rationale; an unexplained "
                "absence reads as an oversight"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "status": self.status.value,
            "rationale": self.rationale,
            "comparison": self.comparison.as_dict() if self.comparison else None,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# The two ablations that cannot be run as written
# ---------------------------------------------------------------------------


def refuse_transformer_silver_ablation() -> Ablation:
    """The +/- silver arm on the transformer, declined with its reason recorded."""
    return Ablation(
        id="silver_transformer",
        question="Does adding the silver-labelled utterances to transformer training help?",
        status=AblationStatus.REFUSED,
        rationale=(
            "OPEN-028: every silver label is `rng.randrange` output from the offline stub "
            "(OPEN-008, no live OpenRouter call has ever been made). The experiment would "
            "measure the effect of adding uniform noise to the training set, which is known "
            "by construction, at a cost of roughly ten CPU-hours across the two arms. The "
            "cheap classical arm (`silver_classical`) demonstrates the collapse instead. "
            "This ablation becomes worth running the day a real labelling run exists; until "
            "then its result would be a fact about `random`, not about weak supervision."
        ),
        detail={"blocked_by": ["OPEN-028", "OPEN-008"], "estimated_cost_cpu_hours": 10},
    )


# ---------------------------------------------------------------------------
# Risk-layer structural sensitivity (the "+/- fusion" ablation, reframed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskSensitivity:
    """What the Phase 15 fusion layer does, quantified. No accuracy claim.

    `naive_rho` is the one to read first. It is the rank correlation between the
    taxonomy-grounded risk index and a flat count of detected constructs. Near
    1.0 means the directions and magnitudes in `config/taxonomy.yaml` are not
    changing who gets flagged, and the interpretable layer is buying
    interpretability rather than discrimination -- which is a defensible thing
    to buy, but only if the paper says so.
    """

    n: int
    #: construct -> mean |contribution| as a share of total absolute movement.
    contribution_share: dict[str, float]
    #: construct -> how often it was detected but directionally unresolved.
    unresolved_rate: dict[str, float]
    #: PolarityPolicy name -> rank correlation with the NEUTRAL default.
    polarity_rho: dict[str, float | None]
    #: PolarityPolicy name -> mean absolute shift in the index.
    polarity_mean_shift: dict[str, float]
    #: Rank correlation of the risk index against a naive count of detected constructs.
    naive_rho: float | None
    #: Rank correlation under seeded +/-epsilon noise on the input probabilities.
    perturbation_rho: float | None
    perturbation_epsilon: float

    @property
    def zeroed_constructs(self) -> tuple[str, ...]:
        """Constructs that never moved the index at all.

        Under the default `PolarityPolicy.NEUTRAL`, a polarity-bearing construct
        with no sub-label resolved contributes exactly zero. That is the
        conservative choice Phase 15 made deliberately, but its consequence is
        that part of the taxonomy is inert in the risk layer, and a decomposition
        the paper presents as ten-construct is really fewer. Counted here so the
        number is stated rather than discovered by a reviewer.
        """
        return tuple(name for name, share in sorted(self.contribution_share.items()) if share == 0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "contribution_share": dict(sorted(self.contribution_share.items())),
            "zeroed_constructs": list(self.zeroed_constructs),
            "unresolved_rate": dict(sorted(self.unresolved_rate.items())),
            "polarity_rho": self.polarity_rho,
            "polarity_mean_shift": self.polarity_mean_shift,
            "naive_rho_vs_construct_count": self.naive_rho,
            "perturbation_rho": self.perturbation_rho,
            "perturbation_epsilon": self.perturbation_epsilon,
            "is_accuracy": False,
            "note": (
                "Structural sensitivity of the fusion layer. No observed risk outcome "
                "exists (Phase 15; `calibrate_risk_index` refuses), so none of these "
                "numbers is a measure of whether the risk index is correct."
            ),
        }


def risk_sensitivity(
    rows: Sequence[Mapping[str, float]],
    *,
    scorer: LinearRiskScorer | None = None,
    epsilon: float = 0.05,
    seed: int = 42,
) -> RiskSensitivity:
    """Profile the fusion layer over a set of per-construct probability rows.

    `rows` is what `PredictionSet.probabilities_for` yields, one mapping per
    record. Everything here is deterministic given `seed`.
    """
    # Imported inside the function on purpose. A module-level
    # `from src.explainability.faithfulness import spearman` closes an import
    # cycle -- src.evaluation/__init__ -> ablations -> explainability.faithfulness
    # -> explainability.attribution -> models.dataset -> models/__init__ ->
    # classical -> evaluation.baselines -> back into a half-built
    # src.evaluation/__init__. The cycle only bites when src.explainability is
    # imported FIRST, so a full-suite run hides it and importing
    # tests/test_explainability.py alone raises ImportError. Keep this local.
    from src.explainability.faithfulness import spearman

    scorer = scorer or LinearRiskScorer()
    if not rows:
        raise ValueError("risk_sensitivity needs at least one probability row")

    base = [scorer.score(row) for row in rows]
    base_index = [s.index for s in base]

    # 1. Which constructs move the index.
    abs_total: dict[str, float] = {}
    unresolved: dict[str, int] = {}
    for score in base:
        for c in score.contributions:
            abs_total[c.construct] = abs_total.get(c.construct, 0.0) + abs(c.contribution)
            if c.polarity_unresolved:
                unresolved[c.construct] = unresolved.get(c.construct, 0) + 1
    grand = sum(abs_total.values())
    share = {k: (v / grand if grand else 0.0) for k, v in abs_total.items()}
    unresolved_rate = {k: unresolved.get(k, 0) / len(rows) for k in abs_total}

    # 2. How much the unresolved-polarity default matters.
    polarity_rho: dict[str, float | None] = {}
    polarity_shift: dict[str, float] = {}
    for policy in (PolarityPolicy.PESSIMISTIC, PolarityPolicy.OPTIMISTIC):
        alt_scorer = LinearRiskScorer(
            directions=scorer.directions,
            magnitudes=scorer.magnitudes,
            polarity_policy=policy,
            temperature=scorer.temperature,
            is_calibrated=scorer.is_calibrated,
        )
        alt = [alt_scorer.score(row).index for row in rows]
        polarity_rho[policy.name] = spearman(base_index, alt)
        polarity_shift[policy.name] = sum(
            abs(a - b) for a, b in zip(alt, base_index, strict=True)
        ) / len(rows)

    # 3. Does fusion order records differently from counting?
    naive = [sum(1.0 for v in row.values() if v >= 0.5) for row in rows]
    naive_rho = spearman(base_index, naive)

    # 4. Rank stability under small input perturbation.
    rng = random.Random(seed)
    jittered = [
        scorer.score(
            {k: min(1.0, max(0.0, v + rng.uniform(-epsilon, epsilon))) for k, v in row.items()}
        ).index
        for row in rows
    ]
    perturbation_rho = spearman(base_index, jittered)

    return RiskSensitivity(
        n=len(rows),
        contribution_share=share,
        unresolved_rate=unresolved_rate,
        polarity_rho=polarity_rho,
        polarity_mean_shift=polarity_shift,
        naive_rho=naive_rho,
        perturbation_rho=perturbation_rho,
        perturbation_epsilon=epsilon,
    )


def fusion_ablation(sensitivity: RiskSensitivity) -> Ablation:
    """Wrap a `RiskSensitivity` as the Phase 18 "+/- risk fusion" row."""
    rho = sensitivity.naive_rho
    if rho is None:
        reading = "rank correlation undefined (constant ordering)"
    elif rho >= 0.95:
        reading = (
            f"rho={rho:.3f} against a plain count of detected constructs -- the fusion layer "
            "barely reorders records. It is buying interpretability, not discrimination, and "
            "the paper must say so rather than imply the weighting is doing work."
        )
    else:
        reading = (
            f"rho={rho:.3f} against a plain count of detected constructs -- the taxonomy "
            "directions and magnitudes materially change the ordering."
        )
    return Ablation(
        id="risk_fusion",
        question="What does the construct->risk fusion layer contribute?",
        status=AblationStatus.MEASURED,
        rationale=(
            "Reframed as a structural sensitivity analysis. No observed risk outcome exists, "
            "so an accuracy-style +/- fusion comparison is impossible and a proxy target "
            "derived from planted labels would be circular (Phase 15). " + reading
        ),
        detail=sensitivity.as_dict(),
    )


# ---------------------------------------------------------------------------
# The claim ledger -- the Phase 18 gate, made checkable
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One assertion the paper intends to make, and where its evidence lives.

    `evidence_key` is looked up in the results payload. A claim whose key is
    absent is an unbacked claim, and the gate fails on it -- which is the whole
    point: "every claim is backed by a logged experiment" is unenforceable until
    the claims are written down somewhere a test can iterate over.

    `predicate` exists because presence is not support, and the first real run of
    this harness proved it. The `silver_is_noise` claim originally read "training
    on silver degrades a model"; the ablation measured delta=+0.033 at p=0.110 --
    no significant change in either direction -- and the gate went green anyway,
    because the evidence key was *present*. A gate that checks only that a result
    exists will happily certify a claim its own evidence contradicts, which is
    the Phase 17 lesson (an ethics guard passing its own test while bypassable
    through another field) recurring in a new place.

    So a claim may carry a callable that inspects the resolved evidence and
    returns whether it actually supports the sentence. Claims with no predicate
    are presence-checked as before.
    """

    id: str
    text: str
    evidence_key: str
    section: str
    predicate: Callable[[Any], bool] | None = None


#: The claims Phases 13-18 have earned the right to make. Add a row here *before*
#: writing the sentence into the paper, not after -- the ordering is what keeps
#: the ledger honest.
CLAIMS: tuple[Claim, ...] = (
    Claim(
        "transformer_beats_lexicon",
        "The fine-tuned transformer recovers more of the planted template grammar than "
        "the lexicon floor, on a template-disjoint split, and the gap survives a paired "
        "bootstrap.",
        "comparisons.transformer_vs_lexicon",
        "results",
        # The sentence says "beats" and "survives a paired bootstrap". Nothing
        # less than that backs it, so the gate checks for exactly that rather
        # than for the presence of a comparison that might say the opposite.
        predicate=lambda e: e.get("delta", 0.0) > 0 and bool(e.get("significant")),
    ),
    Claim(
        "memorisation_gap",
        "A random split massively overstates generalisation on this corpus; the "
        "template-disjoint gap is the honest number.",
        "comparisons.split_gap",
        "results",
    ),
    Claim(
        "per_construct_spread",
        "Performance is not uniform across the ten constructs; per-construct P/R/F1 with "
        "support is reported for every system.",
        "scores",
        "results",
    ),
    Claim(
        "silver_is_noise",
        "Adding the silver-labelled data produces no significant improvement, which is "
        "measured evidence for OPEN-028 rather than an assertion of it.",
        # Wording revised 2026-08-13 after the first real run. It previously read
        # "training on it degrades rather than improves a model"; the ablation
        # measured delta=+0.033 at p=0.110 -- no significant change in either
        # direction -- and the presence-only gate certified the claim anyway.
        # "No significant improvement" is what the experiment actually supports,
        # and it is still exactly the evidence OPEN-028 needs.
        "ablations.silver_classical",
        "ablation",
        predicate=lambda e: (
            e.get("status") == "measured"
            and not (
                (e.get("comparison") or {}).get("delta", 0.0) > 0
                and (e.get("comparison") or {}).get("significant", False)
            )
        ),
    ),
    Claim(
        "fusion_is_structural",
        "The construct->risk fusion layer is interpretable and deterministic, and its "
        "contribution is characterised structurally because no risk outcome exists to "
        "score it against.",
        "ablations.risk_fusion",
        "method",
    ),
    Claim(
        "explanations_beat_random",
        "Attributions are more faithful to the model than a random-span control, by "
        "comprehensiveness and sufficiency.",
        "explainability.faithfulness",
        "results",
    ),
    Claim(
        "reproduction_tolerance",
        "The artifact declares, per artefact, whether a reproduction is expected to be "
        "byte-identical or to fall within a stated numeric tolerance, and the tolerance "
        "was fixed before any re-run rather than fitted to one.",
        # Added at Phase 22, BEFORE the first reproduction run, because a
        # tolerance is a claim (Phase 19's corollary) and a tolerance chosen
        # after seeing the delta is not a gate. The evidence node is written by
        # `scripts/run_reproduction.py --declare` and merged into this payload by
        # `scripts/run_evaluation.py`; it carries the declared tolerance and the
        # SHA-256 of the declaring plan.
        "reproduction.declaration",
        "artifact",
        # The equality is the enforcement. `declared_sha256` is frozen when the
        # tolerances are declared; `plan_sha256` is recomputed from
        # src/reproducibility/manifest.py every time this gate runs. Widen a
        # tolerance afterwards and the two diverge, so the paper claim goes
        # unbacked instead of the edit passing unnoticed.
        predicate=lambda e: (
            isinstance(e.get("retrain_tolerance_macro_f1"), int | float)
            and e["retrain_tolerance_macro_f1"] > 0
            and bool(e.get("declared_sha256"))
            and e.get("declared_sha256") == e.get("plan_sha256")
        ),
    ),
    Claim(
        "not_accuracy",
        "No number reported is an accuracy; every score is agreement with generator-planted "
        "labels on synthetic text.",
        "provenance",
        "limitations",
    ),
)


@dataclass
class ClaimLedger:
    """Checks each claim against the results payload. This is the Phase 18 gate."""

    claims: tuple[Claim, ...] = CLAIMS

    @staticmethod
    def _resolve(payload: Mapping[str, Any], dotted: str) -> Any:
        node: Any = payload
        for part in dotted.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node

    def audit(self, payload: Mapping[str, Any]) -> dict[str, bool]:
        """claim id -> whether its evidence is present, non-empty, and supportive."""
        out: dict[str, bool] = {}
        for claim in self.claims:
            evidence = self._resolve(payload, claim.evidence_key)
            if evidence in (None, {}, [], ""):
                out[claim.id] = False
                continue
            out[claim.id] = claim.predicate(evidence) if claim.predicate else True
        return out

    def unbacked(self, payload: Mapping[str, Any]) -> tuple[Claim, ...]:
        backed = self.audit(payload)
        return tuple(c for c in self.claims if not backed[c.id])
