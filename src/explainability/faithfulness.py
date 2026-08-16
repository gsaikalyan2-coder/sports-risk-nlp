"""Phase 17 -- does the explanation actually describe the model?

The distinction this module exists to enforce
---------------------------------------------
There are two separate questions about an explanation, they are routinely
conflated, and a paper that answers only one gets asked about the other:

* **Faithfulness** -- does the highlighted span actually drive the model's
  prediction? This is a property of the model and the attribution method, and it
  is measurable automatically. That is this module.
* **Plausibility** -- does the highlighted span look like a sensible cue to a
  human? This is a property of the explanation and the human, and it needs
  people. That is `study.py`.

They come apart in both directions, which is why both are reported. An
explanation can be perfectly faithful and implausible -- that is the model
having learned a shortcut, and it is a **finding**, not a defect in the
explainer. An explanation can be plausible and unfaithful -- that is the
dangerous case, because it looks right and is not, and it is exactly what a
coach-facing dashboard would ship if only the expert study were run.

For this project the asymmetry is sharper than usual. The model was trained on a
template grammar, so a faithful explanation may well highlight a template's
giveaway phrasing. If faithfulness is high and expert-rated plausibility is
low, the honest conclusion is *the model learned the generator, not the
construct* -- and Phase 17 will have produced real evidence for the limitation
that OPEN-011 has been asserting since Phase 7.

The metrics
-----------
All three follow the ERASER conventions so the numbers are comparable to
published work.

* **Comprehensiveness** = p(full text) - p(text with the top-k% attributed
  words removed). If the explanation found what mattered, deleting it should
  make the prediction collapse, so **higher is better**.
* **Sufficiency** = p(full text) - p(only the top-k% attributed words kept). If
  the explanation is enough on its own, keeping only it should reproduce the
  prediction, so **lower is better** (near zero is ideal, and negative means
  the fragment scored *higher* than the whole text).
* **AOPC** -- both metrics averaged over k in {1, 5, 10, 20, 50}%, so the result
  does not depend on one arbitrary choice of k.

**The random control is not optional.** Deleting any 20% of a sentence degrades
a prediction somewhat, so comprehensiveness is positive for a random
"explanation" too. Reporting comprehensiveness without that floor is reporting a
number whose scale is unknown. `random_control` runs the identical protocol on
uniformly-sampled words at a fixed seed, and the reportable quantity is the
**margin over random**. A method that does not beat its own random control has
not been shown to explain anything.

No torch here
-------------
Every function takes a `predict_fn: Sequence[str] -> list[list[float]]`
callable. The model lives behind that callable, so this module is pure Python,
runs in the light Docker image, and is unit-testable against a stub scorer with
no ML stack installed -- which is how its arithmetic was verified.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src.explainability.attribution import TokenAttribution, word_spans

#: Deletion fractions. Starts at 1% so that on a ~40-word record the first point
#: is a single word -- the sharpest test of whether the top-ranked span alone
#: carries the prediction.
DEFAULT_FRACTIONS: tuple[float, ...] = (0.01, 0.05, 0.10, 0.20, 0.50)

PredictFn = Callable[[Sequence[str]], list[list[float]]]


# ---------------------------------------------------------------------------
# Aligning subword attributions onto words
# ---------------------------------------------------------------------------


def align_to_words(
    text: str,
    tokens: Sequence[TokenAttribution],
) -> list[float]:
    """Sum subword attributions onto whitespace-delimited words.

    Returns one score per word, in `word_spans(text)` order.

    **Sum, not mean**, for the reason `merge_into_spans` sums: additive
    attribution means a word's effect is the total of its pieces'. Averaging
    would systematically shrink long, morphologically complex words -- and in
    this corpus those are words like `catastrophising` and `overthinking`, which
    are precisely the construct-bearing ones.

    A token overlapping two words (rare, and only from a tokenizer that merges
    across whitespace) is assigned to the word it overlaps most. Splitting it
    proportionally would be defensible too; assigning it to *both* would double
    count and inflate every downstream total, which is the error worth guarding
    against.
    """
    spans = word_spans(text)
    scores = [0.0] * len(spans)
    for token in tokens:
        if not token.is_real_span:
            continue
        best_index, best_overlap = -1, 0
        for index, (start, end) in enumerate(spans):
            overlap = min(end, token.end) - max(start, token.start)
            if overlap > best_overlap:
                best_index, best_overlap = index, overlap
        if best_index >= 0:
            scores[best_index] += token.score
    return scores


def _mask_text(text: str, drop: set[int]) -> str:
    """Rebuild `text` with the words at the given indices removed.

    Removed rather than replaced with a mask token. A mask token is
    out-of-distribution for a model that never saw masked input during
    fine-tuning (this one was trained with a plain classification objective, not
    MLM), and inserting one measures the model's reaction to an alien symbol as
    much as to the missing content. Deletion keeps the remaining text
    well-formed for the encoder.

    The cost is that deletion also perturbs sentence length and syntax, and that
    is a known limitation of every erasure metric. It applies identically to the
    random control, which is the reason the control is the thing actually
    reported.
    """
    spans = word_spans(text)
    kept = [text[start:end] for index, (start, end) in enumerate(spans) if index not in drop]
    return " ".join(kept)


def _keep_text(text: str, keep: set[int]) -> str:
    spans = word_spans(text)
    return " ".join(text[start:end] for index, (start, end) in enumerate(spans) if index in keep)


def _top_k_indices(scores: Sequence[float], k: int) -> set[int]:
    """Indices of the `k` highest-scoring words.

    Ranked by **signed** score, not absolute value, and this is a deliberate
    choice worth defending. Comprehensiveness asks "remove the evidence *for*
    this construct and does the probability fall?". A strongly negative word is
    evidence *against*; removing it should make the probability rise, which
    would show up as negative comprehensiveness and read as a failure of the
    explainer when it is the metric being asked the wrong question.
    """
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    return set(order[:k])


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaithfulnessScore:
    """One (record, construct, method) faithfulness measurement."""

    record_id: str
    construct: str
    method: str
    baseline_probability: float
    comprehensiveness: float
    sufficiency: float
    random_comprehensiveness: float
    random_sufficiency: float
    n_words: int

    @property
    def comprehensiveness_margin(self) -> float:
        """The reportable number. See the module docstring."""
        return self.comprehensiveness - self.random_comprehensiveness

    @property
    def sufficiency_margin(self) -> float:
        """Random minus method, so that -- like every other margin here --
        **positive is better**. Sufficiency itself is better when lower, and
        flipping the sign at the point of comparison rather than at the point of
        measurement keeps a reader from having to remember which column runs
        which way."""
        return self.random_sufficiency - self.sufficiency


def score_record(
    *,
    record_id: str,
    text: str,
    construct: str,
    construct_index: int,
    method: str,
    tokens: Sequence[TokenAttribution],
    predict_fn: PredictFn,
    fractions: Sequence[float] = DEFAULT_FRACTIONS,
    seed: int = 42,
) -> FaithfulnessScore | None:
    """Comprehensiveness / sufficiency AOPC for one record and construct.

    Returns `None` for a record with fewer than two words -- AOPC over a
    one-word record is a single degenerate point and averaging it in would drag
    the corpus figure toward an artefact.
    """
    words = word_spans(text)
    if len(words) < 2:
        return None

    scores = align_to_words(text, tokens)
    rng = random.Random(f"{seed}:{record_id}:{construct}")

    baseline = predict_fn([text])[0][construct_index]

    comprehensive: list[float] = []
    sufficient: list[float] = []
    random_comprehensive: list[float] = []
    random_sufficient: list[float] = []

    for fraction in fractions:
        k = max(1, round(len(words) * fraction))
        if k >= len(words):
            # Deleting everything measures the empty string, not the
            # explanation. Skipped rather than clamped, so a short record
            # contributes fewer points instead of one meaningless point.
            continue

        top = _top_k_indices(scores, k)
        control = set(rng.sample(range(len(words)), k))

        batch = [
            _mask_text(text, top),
            _keep_text(text, top),
            _mask_text(text, control),
            _keep_text(text, control),
        ]
        probabilities = [row[construct_index] for row in predict_fn(batch)]

        comprehensive.append(baseline - probabilities[0])
        sufficient.append(baseline - probabilities[1])
        random_comprehensive.append(baseline - probabilities[2])
        random_sufficient.append(baseline - probabilities[3])

    if not comprehensive:
        return None

    mean = lambda xs: sum(xs) / len(xs)  # noqa: E731
    return FaithfulnessScore(
        record_id=record_id,
        construct=construct,
        method=method,
        baseline_probability=baseline,
        comprehensiveness=mean(comprehensive),
        sufficiency=mean(sufficient),
        random_comprehensiveness=mean(random_comprehensive),
        random_sufficiency=mean(random_sufficient),
        n_words=len(words),
    )


# ---------------------------------------------------------------------------
# Method agreement
# ---------------------------------------------------------------------------


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Rank correlation, with average ranks for ties. `None` if undefined.

    Implemented here rather than pulled from scipy for one reason: `scipy` is
    not in `requirements-base.txt`, and this module is required to import in the
    light image. It is thirty lines and it is exercised against known values in
    `tests/test_explainability.py`.

    Rank rather than Pearson correlation because the two methods work on
    different scales -- IG attributions are logit units under a pad baseline,
    SHAP values are logit units under a marginalisation baseline -- so their
    magnitudes are not commensurable but their **orderings** are. The ordering
    is also what the explanation actually uses: every card and every
    faithfulness measurement takes the top-k, and top-k depends on rank alone.
    """
    if len(a) != len(b) or len(a) < 2:
        return None

    def ranks(xs: Sequence[float]) -> list[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        out = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for position in range(i, j + 1):
                out[order[position]] = average
            i = j + 1
        return out

    rank_a, rank_b = ranks(a), ranks(b)
    n = len(a)
    mean_a, mean_b = sum(rank_a) / n, sum(rank_b) / n
    covariance = sum((x - mean_a) * (y - mean_b) for x, y in zip(rank_a, rank_b, strict=True))
    variance_a = sum((x - mean_a) ** 2 for x in rank_a)
    variance_b = sum((y - mean_b) ** 2 for y in rank_b)
    if variance_a <= 0 or variance_b <= 0:
        # A constant series has no ordering, so no rank correlation exists. This
        # is a real case here: a construct the model scored near zero can have
        # uniformly negligible attributions. Returning 0.0 would report
        # "the methods disagree" for what is actually "there was nothing to
        # agree about", and those must not be averaged together.
        return None
    return covariance / (variance_a * variance_b) ** 0.5


def top_k_jaccard(a: Sequence[float], b: Sequence[float], *, k: int = 5) -> float | None:
    """Overlap of the two methods' top-k words.

    Reported alongside Spearman because they answer different questions and a
    reader needs both. Spearman is dominated by the long tail of near-zero
    attributions, where the two methods have no reason to agree and their
    disagreement is not interesting. Jaccard over the top-k measures agreement
    on the part that is actually shown to a human -- which is the only part the
    expert study and the cards ever use.
    """
    if len(a) != len(b) or not a:
        return None
    limit = min(k, len(a))
    top_a = _top_k_indices(a, limit)
    top_b = _top_k_indices(b, limit)
    union = top_a | top_b
    if not union:
        return None
    return len(top_a & top_b) / len(union)


@dataclass(frozen=True)
class MethodAgreement:
    """IG vs SHAP agreement for one record and construct."""

    record_id: str
    construct: str
    spearman: float | None
    top_k_jaccard: float | None
    n_words: int


def compare_methods(
    *,
    record_id: str,
    text: str,
    construct: str,
    ig_tokens: Sequence[TokenAttribution],
    shap_tokens: Sequence[TokenAttribution],
    k: int = 5,
) -> MethodAgreement:
    """Align both methods onto words, then correlate.

    The alignment is the load-bearing step and the reason this is a function
    rather than two calls at the call site. IG attributes subwords and SHAP
    attributes words; correlating those series directly would compare arrays of
    different lengths, or -- worse, if they happened to match -- compare
    unrelated positions and produce a number that looks like a result.
    """
    ig_scores = align_to_words(text, ig_tokens)
    shap_scores = align_to_words(text, shap_tokens)
    return MethodAgreement(
        record_id=record_id,
        construct=construct,
        spearman=spearman(ig_scores, shap_scores),
        top_k_jaccard=top_k_jaccard(ig_scores, shap_scores, k=k),
        n_words=len(ig_scores),
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def summarise(scores: Sequence[FaithfulnessScore]) -> dict[str, Any]:
    """Per-construct and overall faithfulness, plus the pass/fail signal.

    `beats_random` is the Phase 17 quality signal and it is deliberately a
    strict inequality on the **mean margin**, not on the raw metric. See the
    module docstring: a positive comprehensiveness alone shows only that
    deleting words hurts.
    """
    if not scores:
        return {"n": 0, "constructs": {}, "overall": None}

    def block(subset: Sequence[FaithfulnessScore]) -> dict[str, Any]:
        n = len(subset)
        mean = lambda f: sum(f(s) for s in subset) / n  # noqa: E731
        comprehensiveness_margin = mean(lambda s: s.comprehensiveness_margin)
        sufficiency_margin = mean(lambda s: s.sufficiency_margin)
        return {
            "n": n,
            "comprehensiveness": mean(lambda s: s.comprehensiveness),
            "sufficiency": mean(lambda s: s.sufficiency),
            "random_comprehensiveness": mean(lambda s: s.random_comprehensiveness),
            "random_sufficiency": mean(lambda s: s.random_sufficiency),
            "comprehensiveness_margin": comprehensiveness_margin,
            "sufficiency_margin": sufficiency_margin,
            "beats_random": comprehensiveness_margin > 0 and sufficiency_margin > 0,
        }

    constructs = sorted({s.construct for s in scores})
    return {
        "n": len(scores),
        "overall": block(scores),
        "constructs": {c: block([s for s in scores if s.construct == c]) for c in constructs},
    }
