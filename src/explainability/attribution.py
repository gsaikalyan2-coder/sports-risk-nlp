"""Phase 17 -- span-level, construct-specific attribution over the Phase 14 model.

What this module claims, stated before anything else
----------------------------------------------------
An attribution is a claim about **the model**, not about athlete psychology and
not about the text. It says: *these character spans are what moved this
construct's probability*. It does not say the span is a real cue for cognitive
anxiety in human beings, because the model that produced it was fine-tuned on
`synth_precomp_v1` against planted labels and no athlete wrote any of the text
(OPEN-011, OPEN-025). Every card, figure and report this module feeds carries
that provenance string, and `cards.py` refuses to render one without it.

Why two methods rather than one
-------------------------------
`PROJECT_PLAN.md` Phase 17 offers "SHAP and/or attention rollout". This module
implements **Integrated Gradients** and **SHAP Partition**, and deliberately does
not implement attention rollout as a headline method. The reason is a
well-known one and a reviewer will raise it: raw attention weights are not
explanations. Attention can be permuted substantially without changing a
model's output, so a heatmap of attention is not evidence about what the model
used. Reporting it as an explanation is the single easiest way to lose an XAI
reviewer.

That leaves the question of which faithful method, and the honest answer is that
no single attribution method is known to be correct. So the design is:

* **Integrated Gradients** -- cheap enough to run over the whole evaluation
  slice on CPU, and axiomatically grounded (completeness: the attributions sum
  to the difference between the prediction at the input and at the baseline, up
  to Riemann error, which `IntegratedGradients` measures and reports rather than
  assuming).
* **SHAP Partition** -- the method an XAI reviewer expects to see, run on a
  subsample because it is model-agnostic and therefore far more expensive.

Then `faithfulness.py` cross-checks them. Two methods that were derived from
different principles and agree are much better evidence than either alone; two
that disagree is itself a reportable finding about this corpus. Either outcome
is publishable. Picking one method and presenting its output as "the
explanation" is not.

Why character offsets and not token indices
-------------------------------------------
The Phase 17 gate says explanations must be **span-level**. A subword token
index is not a span -- it is an artefact of the tokenizer, it is not stable
across base models, and it cannot be shown to a rater. So every attribution
carries `(start, end)` character offsets into the original text, obtained from
the tokenizer's `return_offsets_mapping`, and `merge_into_spans` groups adjacent
tokens back into contiguous, readable word spans before anything human-facing
sees them.

This also makes the expert study possible at all. A rater is asked "is *'my
hands won't stop shaking'* a plausible cue for somatic_anxiety?" -- a question
about a phrase. There is no version of that question that can be asked about
token 14.

Dependencies
------------
torch and transformers are imported lazily through
`src.models.transformer.require_ml_stack`, following the convention that module
establishes: `src/evaluation/` and the light Docker image must keep importing
this package. `shap` is imported lazily and separately, because the IG path is
useful on a machine where shap will not install and should not be held hostage
to it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src.models.dataset import CONSTRUCTS

#: Provenance string attached to every explanation produced here. Deliberately
#: verbose and deliberately not configurable: an explanation card that escapes
#: into a slide deck without it becomes a claim about a person.
EXPLANATION_PROVENANCE = (
    "Attribution over a classifier fine-tuned on synthetic text "
    "(synth_precomp_v1) against generator-planted labels. No human-verified "
    "labels exist (OPEN-025) and no real athlete text was used (OPEN-011). "
    "This shows what the model used, not what predicts psychological risk in "
    "people. Not a clinical instrument."
)


class AttributionUnavailable(RuntimeError):
    """An attribution backend cannot run, for a configuration reason.

    Distinct from a wrong answer. Mirrors `MLDependencyMissing` in
    `src/models/transformer.py`: a missing optional dependency is a setup
    problem and the runner should exit 2, not report a failed experiment.
    """


# ---------------------------------------------------------------------------
# Data model (pure Python -- importable and testable with no ML stack present)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenAttribution:
    """One token's signed contribution to one construct's logit.

    `start`/`end` are character offsets into the *original* record text, not
    into anything the tokenizer produced. Special tokens (CLS/SEP/PAD) map to
    `(0, 0)` in every fast tokenizer and are dropped before this dataclass is
    constructed -- see `_drop_special`.

    The score is **signed**. A negative attribution means the token pushed the
    construct's probability *down*, and that is information a coach-facing card
    should keep: "you said you felt ready, which lowered the anxiety reading" is
    a more useful explanation than an absolute-value heatmap that shows only
    that the phrase mattered.
    """

    token: str
    start: int
    end: int
    score: float

    @property
    def is_real_span(self) -> bool:
        return self.end > self.start


@dataclass(frozen=True)
class SpanAttribution:
    """A contiguous, human-readable character span and its aggregated score.

    Produced by `merge_into_spans`. This is the unit the expert study rates and
    the unit the paper's figures show.
    """

    text: str
    start: int
    end: int
    score: float
    n_tokens: int


@dataclass(frozen=True)
class ConstructExplanation:
    """Why the model gave `construct` the probability it did, for one record."""

    construct: str
    probability: float
    method: str
    tokens: tuple[TokenAttribution, ...]
    #: Completeness residual for IG (see `IntegratedGradients`); None for
    #: methods that have no such axiom. Reported, never silently discarded --
    #: a large residual means the Riemann approximation was too coarse and the
    #: attributions should not be trusted at face value.
    completeness_error: float | None = None
    #: The record text these offsets index into.
    #:
    #: Carried here, duplicated from `RecordExplanation.text`, for a reason found
    #: by testing rather than by design: without it `top_spans` had to
    #: reconstruct span text by concatenating token strings, which silently drops
    #: the whitespace between words and produced spans like `shakingbefore`.
    #: Those go straight onto rating sheets and into paper figures, where a
    #: mangled phrase reads as a defect in the model rather than in the renderer.
    #: A span must be a substring of the original text, and the only way to
    #: guarantee that is to keep the original text within reach of the slice.
    source_text: str | None = None

    def top_spans(self, *, limit: int = 5, min_score: float = 0.0) -> tuple[SpanAttribution, ...]:
        """Highest-magnitude merged spans, largest first."""
        spans = merge_into_spans(self.tokens, source_text=self.source_text)
        ranked = sorted(spans, key=lambda s: -abs(s.score))
        return tuple(s for s in ranked if abs(s.score) >= min_score)[:limit]


@dataclass(frozen=True)
class RecordExplanation:
    """All construct explanations for one record, plus provenance.

    `provenance` is a field rather than a module constant lookup so that it
    travels with a serialised explanation. A JSON file that has been copied out
    of `reports/explain/` must still carry the warning.
    """

    record_id: str
    text: str
    method: str
    explanations: tuple[ConstructExplanation, ...]
    provenance: str = EXPLANATION_PROVENANCE

    def for_construct(self, construct: str) -> ConstructExplanation | None:
        for explanation in self.explanations:
            if explanation.construct == construct:
                return explanation
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "text": self.text,
            "method": self.method,
            "provenance": self.provenance,
            "explanations": [
                {
                    "construct": e.construct,
                    "probability": e.probability,
                    "completeness_error": e.completeness_error,
                    "tokens": [
                        {"token": t.token, "start": t.start, "end": t.end, "score": t.score}
                        for t in e.tokens
                    ],
                    "top_spans": [
                        {"text": s.text, "start": s.start, "end": s.end, "score": s.score}
                        for s in e.top_spans()
                    ],
                }
                for e in self.explanations
            ],
        }


# ---------------------------------------------------------------------------
# Token -> span aggregation (pure Python)
# ---------------------------------------------------------------------------

#: A gap of this many characters or fewer between two tokens is treated as
#: within-span. One character covers the single space between words, which is
#: what byte-level BPE produces for `distilroberta-base`. Two covers a space
#: plus a stray punctuation split. Anything larger is a real boundary.
_MAX_INTRA_SPAN_GAP = 1


def merge_into_spans(
    tokens: Sequence[TokenAttribution],
    *,
    max_gap: int = _MAX_INTRA_SPAN_GAP,
    source_text: str | None = None,
) -> tuple[SpanAttribution, ...]:
    """Group adjacent same-signed tokens into contiguous readable spans.

    Three rules, and each exists because of a specific way naive merging misleads:

    1. **Adjacency by character offset**, not by token index. Subword tokens of
       one word (`shak` + `ing`) are adjacent with gap 0 and merge into
       `shaking`. Dropping a token in the middle (because it was a special
       token) leaves a gap and correctly breaks the span.
    2. **Same sign only.** A token pushing the construct up and the next pushing
       it down must not be merged, because their scores would cancel and the
       merged span would report a small number for a region where two strong
       opposing effects sit. That is the merge producing an artefact rather than
       a summary.
    3. **Scores sum, they do not average.** A span's effect on the logit is the
       sum of its tokens' effects -- that is what additive attribution means.
       Averaging would make a long span look weaker than a short one carrying
       the same total, and long spans are exactly the ones a rater can judge.
    4. **A token scoring exactly zero breaks the span.** Found by
       `test_redacted_render_omits_the_record_text`, and it is a sharper bug than
       it sounds. Zero counts as non-negative, so under rule 2 alone a zero-
       scored token sits happily between two positive ones and welds them
       together. A record whose attributions are mostly zero therefore merges
       into a *single span covering the entire text* -- which is not an
       explanation (it highlights everything), and which silently defeats the
       redaction guard in `cards.py`, since "show only the spans" then shows the
       whole record. A token that contributed nothing must not extend the
       evidence.

    `source_text` is optional and used only to recover the exact substring; when
    omitted the span text is reconstructed from the token strings, which is
    correct for byte-level BPE but can lose original whitespace. The runner
    always passes it.
    """
    real = [t for t in tokens if t.is_real_span and t.score != 0.0]
    if not real:
        return ()
    ordered = sorted(real, key=lambda t: (t.start, t.end))

    spans: list[SpanAttribution] = []
    group: list[TokenAttribution] = [ordered[0]]

    def flush(items: list[TokenAttribution]) -> None:
        start, end = items[0].start, items[-1].end
        text = (
            source_text[start:end]
            if source_text is not None
            else "".join(i.token for i in items).replace("Ġ", " ").strip()
        )
        spans.append(
            SpanAttribution(
                text=text,
                start=start,
                end=end,
                score=sum(i.score for i in items),
                n_tokens=len(items),
            )
        )

    for token in ordered[1:]:
        previous = group[-1]
        # A gap larger than `max_gap` also arises when a zero-scored token was
        # filtered out above, which is exactly the wanted behaviour: the
        # contributing region ends where the contribution does.
        contiguous = token.start - previous.end <= max_gap
        same_sign = (token.score >= 0) == (previous.score >= 0)
        if contiguous and same_sign:
            group.append(token)
        else:
            flush(group)
            group = [token]
    flush(group)
    return tuple(spans)


def _drop_special(
    tokens: Sequence[str],
    offsets: Sequence[tuple[int, int]],
    scores: Sequence[float],
) -> list[TokenAttribution]:
    """Build `TokenAttribution`s, discarding special and zero-width tokens.

    Fast tokenizers give CLS/SEP/PAD an offset of `(0, 0)`. Keeping them would
    put a phantom span at character 0 of every record, and because CLS often
    carries a large gradient in a sequence-classification head, that phantom
    span would frequently rank first. It would then be shown to a rater as the
    model's top cue, which is both meaningless and embarrassing.
    """
    out: list[TokenAttribution] = []
    for token, (start, end), score in zip(tokens, offsets, scores, strict=True):
        if end <= start:
            continue
        out.append(
            TokenAttribution(token=token, start=int(start), end=int(end), score=float(score))
        )
    return out


# ---------------------------------------------------------------------------
# Integrated Gradients
# ---------------------------------------------------------------------------


@dataclass
class IntegratedGradients:
    """Path-integral attribution over the input embeddings.

    The method in one paragraph, since the owner is a sophomore and this is the
    part of Phase 17 that most needs to be defensible in a viva. Take the real
    input and a meaningless "baseline" input (here: every token replaced by the
    pad embedding, which is what the model sees as "nothing"). Walk in a
    straight line from the baseline to the real input in `n_steps` stops. At each
    stop, measure how sensitive the construct's logit is to each embedding
    dimension (the gradient). Average those gradients along the path and
    multiply by how far each dimension actually moved. The result is each
    token's share of the difference between "the model's output on nothing" and
    "the model's output on this text".

    **Why the completeness residual is computed and reported.** The paragraph
    above is exact only in the limit of infinitely many steps; with `n_steps=32`
    it is a Riemann sum with error. Completeness says the attributions must sum
    to `logit(input) - logit(baseline)`. Measuring the gap between that identity
    and what was actually produced is free, and it is the only automatic check
    available that the attribution is arithmetically sound. A large residual
    means raise `n_steps`. Silently not checking it is how a paper ends up
    reporting attributions that do not add up.

    **Why the pad-token baseline and not a zero-vector baseline.** A zero
    embedding is not a point the model has ever seen and its logit can be
    arbitrary, which makes `logit(baseline)` -- and therefore every attribution
    -- meaningless. The pad embedding under a full attention mask is at least an
    in-distribution "empty" input. This is a known soft spot of IG and it is
    stated in the report rather than hidden: IG attributions are relative to a
    baseline, and a different baseline gives different numbers.

    **Aggregation over the embedding dimension is a sum, not an L2 norm.** The
    sum preserves sign and satisfies completeness; the L2 norm is always
    positive and breaks it. Sign is wanted here (see `TokenAttribution`).
    """

    model: Any
    tokenizer: Any
    device: str = "cpu"
    n_steps: int = 32
    max_length: int = 128
    #: Batch of path steps evaluated per forward pass. 8 x 128 tokens fits
    #: comfortably in the 3-4 GB a laptop can spare; raise on a GPU.
    step_batch: int = 8

    def _encode(self, text: str) -> tuple[Any, Any, list[str], list[tuple[int, int]]]:
        encoded = self.tokenizer(
            text,
            truncation=True,
            max_length=self.max_length,
            return_offsets_mapping=True,
            return_tensors="pt",
        )
        offsets = [tuple(pair) for pair in encoded["offset_mapping"][0].tolist()]
        ids = encoded["input_ids"]
        tokens = self.tokenizer.convert_ids_to_tokens(ids[0].tolist())
        return ids.to(self.device), encoded["attention_mask"].to(self.device), tokens, offsets

    def attribute(
        self,
        text: str,
        construct_index: int,
    ) -> tuple[list[TokenAttribution], float, float]:
        """Attribute one construct's logit for one record.

        Returns `(token_attributions, probability, completeness_error)`.
        """
        from src.models.transformer import require_ml_stack

        torch, _ = require_ml_stack()

        input_ids, attention_mask, tokens, offsets = self._encode(text)
        embedder = self.model.get_input_embeddings()

        pad_id = self.tokenizer.pad_token_id
        if pad_id is None:  # pragma: no cover - every checkpoint here has one
            pad_id = self.tokenizer.eos_token_id or 0

        with torch.no_grad():
            inputs_embeds = embedder(input_ids)
            baseline_ids = torch.full_like(input_ids, int(pad_id))
            baseline_embeds = embedder(baseline_ids)

        delta = inputs_embeds - baseline_embeds

        # --- accumulate path gradients ------------------------------------
        total_grads = torch.zeros_like(inputs_embeds)
        # Midpoint rule rather than left/right endpoints: same cost, roughly an
        # order of magnitude less Riemann error, which shows up directly in the
        # completeness residual this method reports.
        alphas = [(i + 0.5) / self.n_steps for i in range(self.n_steps)]

        self.model.eval()
        for start in range(0, len(alphas), self.step_batch):
            chunk = alphas[start : start + self.step_batch]
            scaled = torch.cat([baseline_embeds + alpha * delta for alpha in chunk], dim=0).detach()
            scaled.requires_grad_(True)
            mask = attention_mask.repeat(len(chunk), 1)
            logits = self.model(inputs_embeds=scaled, attention_mask=mask).logits
            target = logits[:, construct_index].sum()
            (grads,) = torch.autograd.grad(target, scaled)
            total_grads = total_grads + grads.sum(dim=0, keepdim=True)

        average_grads = total_grads / len(alphas)
        attributions = (average_grads * delta).sum(dim=-1)[0].detach().cpu().tolist()

        # --- completeness check -------------------------------------------
        with torch.no_grad():
            real_logit = float(
                self.model(input_ids=input_ids, attention_mask=attention_mask).logits[
                    0, construct_index
                ]
            )
            baseline_logit = float(
                self.model(inputs_embeds=baseline_embeds, attention_mask=attention_mask).logits[
                    0, construct_index
                ]
            )
        completeness_error = abs(sum(attributions) - (real_logit - baseline_logit))
        probability = 1.0 / (1.0 + math.exp(-real_logit))

        return _drop_special(tokens, offsets, attributions), probability, completeness_error

    def explain_record(
        self,
        record_id: str,
        text: str,
        constructs: Sequence[str] = CONSTRUCTS,
        *,
        only: Sequence[str] | None = None,
    ) -> RecordExplanation:
        """Attribute every requested construct for one record.

        `only` restricts to a subset. The runner uses it to attribute solely the
        constructs the model actually predicted, because an attribution map for
        a construct the model scored 0.02 explains a non-prediction -- it is
        noise, it costs a full IG pass, and it would pad the expert study with
        unratable items.
        """
        wanted = set(only) if only is not None else set(constructs)
        explanations: list[ConstructExplanation] = []
        for index, construct in enumerate(constructs):
            if construct not in wanted:
                continue
            tokens, probability, error = self.attribute(text, index)
            explanations.append(
                ConstructExplanation(
                    construct=construct,
                    probability=probability,
                    method="integrated_gradients",
                    tokens=tuple(tokens),
                    completeness_error=error,
                    source_text=text,
                )
            )
        return RecordExplanation(
            record_id=record_id,
            text=text,
            method="integrated_gradients",
            explanations=tuple(explanations),
        )


# ---------------------------------------------------------------------------
# SHAP Partition
# ---------------------------------------------------------------------------

_WORD = re.compile(r"\S+")


@dataclass
class ShapPartition:
    """Model-agnostic Shapley attribution via `shap`'s Partition explainer.

    **Why Partition and not KernelSHAP.** Exact Shapley values need every subset
    of the input, which is exponential. KernelSHAP samples subsets and needs
    thousands of model evaluations per record to stabilise; on CPU with this
    encoder that is minutes per record per construct, which puts a 60-record
    subsample out of reach. Partition exploits the fact that text has hierarchy
    -- adjacent words form phrases -- and computes Owen values over a coalition
    tree instead, which is roughly linear in the number of words. The values it
    returns are Shapley values under an assumption about that hierarchy rather
    than unconditionally, and that assumption should be stated in the paper
    rather than glossed as "we used SHAP".

    **Why this runs on a subsample and IG runs on everything.** Cost, and it is
    recorded here so the asymmetry in the report is not read as cherry-picking.
    The subsample is drawn with a fixed seed by the runner, before any scores are
    seen.

    **Word-level, not subword-level.** `shap.maskers.Text` masks by regex tokens
    (words), so the units are already the readable spans Phase 17 wants. That
    also makes SHAP and IG directly comparable only after IG is aggregated to
    words, which `faithfulness.align_to_words` does -- comparing a subword series
    against a word series would produce a meaningless correlation.
    """

    model: Any
    tokenizer: Any
    device: str = "cpu"
    max_length: int = 128
    batch_size: int = 16
    #: `shap`'s evaluation budget per record. 200 is enough for Partition to
    #: resolve a ~40-word record; it is not enough for KernelSHAP, which is part
    #: of why Partition was chosen.
    max_evals: int = 200

    def _predict_fn(self) -> Callable[[Sequence[str]], Any]:
        from src.models.transformer import require_ml_stack

        torch, _ = require_ml_stack()
        import numpy as np

        def f(texts: Any) -> Any:
            self.model.eval()
            rows: list[list[float]] = []
            listed = [str(t) for t in texts]
            with torch.no_grad():
                for start in range(0, len(listed), self.batch_size):
                    encoded = self.tokenizer(
                        listed[start : start + self.batch_size],
                        truncation=True,
                        padding=True,
                        max_length=self.max_length,
                        return_tensors="pt",
                    ).to(self.device)
                    logits = self.model(**encoded).logits
                    rows.extend(logits.cpu().tolist())
            # Attribute the **logit**, not the probability. The sigmoid is
            # monotone but strongly saturating, so at p=0.97 a large logit
            # movement produces almost no probability movement and SHAP would
            # report every word as unimportant. Attributing in logit space keeps
            # the additive decomposition on the scale the model is linear in,
            # and it is the same scale IG attributes on -- which the two methods
            # must share for their agreement to mean anything.
            return np.array(rows)

        return f

    def explain_record(
        self,
        record_id: str,
        text: str,
        constructs: Sequence[str] = CONSTRUCTS,
        *,
        only: Sequence[str] | None = None,
    ) -> RecordExplanation:
        try:
            import shap
        except ModuleNotFoundError as exc:  # pragma: no cover - env dependent
            raise AttributionUnavailable(
                "shap is not installed, so the SHAP Partition cross-check cannot "
                "run.\n\n    pip install shap\n\n"
                "It is already pinned in requirements-ml.txt. Integrated "
                "Gradients does not need it, so "
                "`python scripts/run_explain.py --methods ig` still produces a "
                "complete span-level attribution set -- but the report will then "
                "carry only one method and the cross-check table will be absent, "
                "which is a real weakening of the Phase 17 evidence and is noted "
                "in the report rather than passed over."
            ) from exc

        predict = self._predict_fn()
        masker = shap.maskers.Text(r"\W+", collapse_mask_token=True)
        explainer = shap.Explainer(predict, masker, silent=True)
        values = explainer([text], max_evals=self.max_evals, batch_size=self.batch_size)

        wanted = set(only) if only is not None else set(constructs)
        probabilities = predict([text])[0]

        explanations: list[ConstructExplanation] = []
        for index, construct in enumerate(constructs):
            if construct not in wanted:
                continue
            scores = [float(row[index]) for row in values.values[0]]
            pieces = [str(p) for p in values.data[0]]
            tokens = _offsets_for_pieces(text, pieces, scores)
            explanations.append(
                ConstructExplanation(
                    construct=construct,
                    probability=1.0 / (1.0 + math.exp(-float(probabilities[index]))),
                    method="shap_partition",
                    tokens=tuple(tokens),
                    completeness_error=None,
                    source_text=text,
                )
            )
        return RecordExplanation(
            record_id=record_id,
            text=text,
            method="shap_partition",
            explanations=tuple(explanations),
        )


def _offsets_for_pieces(
    text: str,
    pieces: Sequence[str],
    scores: Sequence[float],
) -> list[TokenAttribution]:
    """Locate each shap text piece back in the original string.

    `shap.maskers.Text` returns the pieces it split on, including the trailing
    separator whitespace, but not their offsets. Recovering offsets by scanning
    forward with a cursor is exact as long as the pieces concatenate back to the
    original text, which they do for the `\\W+` splitter.

    A piece that cannot be located (which would mean the masker normalised the
    text) is emitted with a zero-width offset and therefore dropped by
    `_drop_special`, rather than being assigned a guessed position. A guessed
    span shown to a rater is worse than a missing one: the rater cannot tell it
    is wrong.
    """
    out: list[TokenAttribution] = []
    cursor = 0
    for piece, score in zip(pieces, scores, strict=True):
        stripped = piece.strip()
        if not stripped:
            cursor += len(piece)
            continue
        found = text.find(stripped, cursor)
        if found < 0:
            out.append(TokenAttribution(token=stripped, start=0, end=0, score=float(score)))
            continue
        out.append(
            TokenAttribution(
                token=stripped,
                start=found,
                end=found + len(stripped),
                score=float(score),
            )
        )
        cursor = found + len(stripped)
    return out


def word_spans(text: str) -> list[tuple[int, int]]:
    """Character offsets of every whitespace-delimited word.

    The shared coordinate system in which IG (subword) and SHAP (word) are made
    comparable, and the unit the expert study rates.
    """
    return [(m.start(), m.end()) for m in _WORD.finditer(text)]
