"""Phase 17 -- the expert-validation study: instrument, blinding, and agreement.

Why this module is the most important one in Phase 17
------------------------------------------------------
The Phase 3 literature review (`docs/related_work.md`) found that sports-XAI
explanations are almost never validated with practitioners. Filling that gap is
contribution #2 and, per `CLAUDE.md` sec.1, the paper's headline differentiator.
Everything else in `src/explainability/` produces explanations; this module is
the only part that produces *evidence that the explanations are any good to a
human*.

What raters are actually asked, and why it is not "is this athlete anxious?"
----------------------------------------------------------------------------
The rating task is:

    Given this highlighted phrase and this construct name, is the phrase a
    plausible textual cue for that construct?           [yes / partly / no]

It is deliberately **not** a judgement about an athlete's psychological state,
for three reasons that must survive review:

1. No athlete exists. The text is synthetic (OPEN-011). A question about a
   person's anxiety has no truth-maker here.
2. `docs/ethics.md` forbids inferring mental-health status of any identifiable
   person, and an instrument that asked raters to do so on synthetic text would
   normalise exactly the misuse the paper warns against.
3. Plausibility of a cue is the quantity the contribution actually claims. The
   claim is "our explanations are sensible to practitioners", not "our model is
   clinically accurate" -- which the project cannot claim and must not imply.

Framing it this way also makes the OPEN-004 rater problem tractable. Judging
whether *"my hands won't stop shaking"* is a plausible cue for somatic arousal
needs sports familiarity and the taxonomy rubric, not a clinical licence. A
sports-familiar student rater gives a defensible answer to *this* question,
where they could not to a clinical one.

Blinding, and the control items that make the number mean something
--------------------------------------------------------------------
An instrument that shows a rater only real model explanations measures the
rater's agreeableness as much as the model's quality. Nobody knows what 78%
"yes" is worth without a floor. So every generated sheet mixes three item types
in shuffled order, and the rater cannot tell them apart:

* **model** -- the model's genuine top span for a construct it predicted.
* **random_span** -- a randomly chosen span of the same length from the *same*
  record, paired with the same construct. This is the floor. If raters approve
  random spans nearly as often as model spans, the explanations have
  demonstrated nothing, however high the raw approval rate.
* **mismatched** -- the model's genuine top span paired with a *different*
  construct. This is the attention check. A rater who approves these is not
  discriminating between constructs, and their sheet should be treated with
  caution rather than averaged in silently.

The item type is stored in a separate answer key (`--key`), never in the sheet
the rater sees. `RatingSheet.render()` will not emit it.

Two raters, one kappa, and an honest denominator
-------------------------------------------------
Agreement between two raters on the model items is Cohen's kappa over three
ordered categories. `cohens_kappa` here is **unweighted**, and that is the
conservative choice: with an ordered scale, weighted kappa credits a
yes/partly disagreement partially and returns a higher number. Reporting the
lower one and saying why is the defensible direction to err in.

What this instrument cannot deliver
-----------------------------------
It cannot turn student raters into practitioners. OPEN-004 is not closed by
building a good instrument. The protocol in `docs/expert_validation_protocol.md`
states the rater population explicitly on the sheet's own cover page, and the
report labels the result a **pilot expert-review with sports-familiar raters**.
If a coach or sport-psych practitioner is recruited before code freeze, they run
the identical instrument and the same functions compute the same statistics --
that is why the rater population is a field on the sheet rather than a sentence
in a doc.
"""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.explainability.attribution import RecordExplanation, word_spans
from src.models.dataset import CONSTRUCTS

#: The rating scale. Ordered, three points.
#:
#: Three rather than five: a five-point Likert on a plausibility judgement
#: invites raters to use the middle as "I am not sure", which is a different
#: quantity from "partly plausible" and cannot be separated afterwards. Three
#: forced, defined points keep the categories interpretable and keep kappa's
#: cells populated -- a 5x5 kappa on ~90 items has cells with single-digit
#: counts and an unstable expected-agreement term.
SCALE: tuple[str, ...] = ("yes", "partly", "no")

ITEM_TYPES: tuple[str, ...] = ("model", "random_span", "mismatched")


@dataclass(frozen=True)
class StudyItem:
    """One thing a rater judges.

    `span_text` is a phrase from a synthetic record. `construct` is the label
    being tested against it. `item_type` is the blinding secret and must not
    reach the rater.
    """

    item_id: str
    record_id: str
    construct: str
    span_text: str
    #: The sentence the span came from, shown for context. A phrase judged with
    #: no context is judged unfairly -- "it is what it is" is a plausible cue for
    #: several constructs or none depending on what preceded it.
    context: str
    item_type: str
    span_start: int
    span_end: int

    def as_public(self) -> dict[str, Any]:
        """The rater-visible fields. `item_type` is deliberately absent."""
        return {
            "item_id": self.item_id,
            "construct": self.construct,
            "span_text": self.span_text,
            "context": self.context,
        }


@dataclass
class RatingSheet:
    """A blinded, shuffled set of items plus the private answer key."""

    items: tuple[StudyItem, ...]
    seed: int
    rater_population: str
    construct_definitions: dict[str, str] = field(default_factory=dict)

    # -- rater-facing ------------------------------------------------------

    def render(self) -> str:
        """The Markdown sheet a rater fills in.

        Contains no item types, no model probabilities, and no construct
        ordering that correlates with type. The cover states the rater
        population verbatim so the eventual claim in the paper is fixed at the
        moment of data collection rather than chosen afterwards to match
        whoever turned up.
        """
        lines = [
            "# Explanation plausibility rating sheet",
            "",
            f"**Rater population declared for this sheet:** {self.rater_population}",
            "",
            "## What you are judging",
            "",
            "Each item shows a **highlighted phrase**, the **sentence it came from**,",
            "and one **construct name**. Answer one question:",
            "",
            "> Is the highlighted phrase a plausible textual cue for that construct?",
            "",
            "Answer `yes`, `partly`, or `no` in the Rating column.",
            "",
            "- **yes** -- a reader who knows the construct definition would accept this",
            "  phrase as evidence for it.",
            "- **partly** -- the phrase is related but weak, ambiguous, or needs the rest",
            "  of the sentence to work.",
            "- **no** -- the phrase is not evidence for this construct.",
            "",
            "### Three things to keep in mind",
            "",
            "1. You are **not** judging whether the writer is anxious, stressed, or at",
            "   risk. You are judging whether the phrase is a sensible cue for the named",
            "   construct. There is no real person here -- all text is computer-generated.",
            "2. Judge only the highlighted phrase. The sentence is context, not the item.",
            "3. Some items will look odd. That is expected and it is part of the design.",
            "   Rate what you see; do not try to work out what the 'right' answer is.",
            "",
            "## Construct definitions",
            "",
        ]
        for name in sorted(self.construct_definitions):
            lines.append(f"- **{name}** -- {self.construct_definitions[name]}")
        lines += [
            "",
            "## Items",
            "",
            "| # | Construct | Highlighted phrase | Sentence | Rating |",
            "|---|---|---|---|---|",
        ]
        for index, item in enumerate(self.items, 1):
            context = item.context.replace("|", "/")
            phrase = item.span_text.replace("|", "/")
            lines.append(
                f"| {index} `{item.item_id}` | {item.construct} | **{phrase}** | {context} |  |"
            )
        lines += [
            "",
            "---",
            "",
            "_All text is synthetic (`synth_precomp_v1`). No real athlete produced any of",
            "it, and no rating here is a judgement about any person._",
            "",
        ]
        return "\n".join(lines)

    # -- private -----------------------------------------------------------

    def answer_key(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "rater_population": self.rater_population,
            "n_items": len(self.items),
            "counts_by_type": {
                t: sum(1 for i in self.items if i.item_type == t) for t in ITEM_TYPES
            },
            "items": [
                {
                    "item_id": i.item_id,
                    "record_id": i.record_id,
                    "construct": i.construct,
                    "item_type": i.item_type,
                    "span_text": i.span_text,
                    "span_start": i.span_start,
                    "span_end": i.span_end,
                }
                for i in self.items
            ],
        }

    def write(self, directory: Path, *, name: str = "rating_sheet") -> tuple[Path, Path]:
        """Write the sheet and the key to separate files.

        Separate files, not two sections of one file, because the single most
        likely way to break the blinding is to hand a rater the whole document.
        """
        directory.mkdir(parents=True, exist_ok=True)
        sheet_path = directory / f"{name}.md"
        key_path = directory / f"{name}_KEY.json"
        sheet_path.write_text(self.render(), encoding="utf-8")
        key_path.write_text(
            json.dumps(self.answer_key(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return sheet_path, key_path


def _random_span(text: str, length_words: int, rng: random.Random) -> tuple[str, int, int] | None:
    """A uniformly-chosen contiguous span of `length_words` words.

    Length-matched to the model span it controls for. Without matching, the
    control differs from the model item in two ways at once -- content and
    length -- and a rater's lower approval could be explained by either. Length
    matching removes the confound that costs nothing to remove.
    """
    spans = word_spans(text)
    if len(spans) < length_words or length_words <= 0:
        return None
    start_index = rng.randrange(0, len(spans) - length_words + 1)
    start = spans[start_index][0]
    end = spans[start_index + length_words - 1][1]
    return text[start:end], start, end


def _sentence_around(text: str, start: int, end: int) -> str:
    """The sentence containing the span, for context.

    Falls back to the whole record when no sentence boundary is found, which is
    common here: `synth_precomp_v1` records are short and the Phase 9b change
    joined discourse clauses with em dashes rather than full stops.
    """
    left = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("?", 0, start))
    right_candidates = [text.find(mark, end) for mark in ".!?"]
    right = min((c for c in right_candidates if c >= 0), default=-1)
    return text[left + 1 : right + 1 if right >= 0 else len(text)].strip() or text


def build_sheet(
    explanations: Sequence[RecordExplanation],
    *,
    rater_population: str,
    construct_definitions: dict[str, str] | None = None,
    n_model_items: int = 60,
    control_ratio: float = 0.25,
    mismatch_ratio: float = 0.15,
    seed: int = 42,
    constructs: Sequence[str] = CONSTRUCTS,
) -> RatingSheet:
    """Assemble a blinded sheet from a set of record explanations.

    Sampling is **stratified by construct** rather than uniform over
    explanations. Construct prevalence in `synth_precomp_v1` varies about
    two-fold, so a uniform draw would give `cognitive_anxiety` roughly twice the
    items of `motivation_orientation`, and the per-construct approval rates --
    which are the interesting part of the result -- would rest on very different
    sample sizes without that being visible in the table.

    Defaults give a ~90-item sheet: 60 model + 15 controls + 9 mismatched.
    At roughly 15 seconds per item that is about 25 minutes per rater, which is
    the practical ceiling for an unpaid rater before attention degrades and the
    later items become noise.
    """
    rng = random.Random(seed)
    definitions = dict(construct_definitions or {})

    # Pool every (record, construct) pair that has a usable top span.
    pool: list[tuple[RecordExplanation, str, Any]] = []
    for explanation in explanations:
        for construct_explanation in explanation.explanations:
            spans = construct_explanation.top_spans(limit=1)
            if spans and spans[0].text.strip():
                pool.append((explanation, construct_explanation.construct, spans[0]))

    by_construct: dict[str, list[tuple[RecordExplanation, str, Any]]] = {}
    for entry in pool:
        by_construct.setdefault(entry[1], []).append(entry)
    for entries in by_construct.values():
        rng.shuffle(entries)

    # Round-robin across constructs so the quota is spread as evenly as the
    # available pool allows, rather than exhausting the commonest construct
    # first.
    chosen: list[tuple[RecordExplanation, str, Any]] = []
    present = sorted(by_construct)
    cursor = {name: 0 for name in present}
    while len(chosen) < n_model_items and present:
        progressed = False
        for name in list(present):
            if len(chosen) >= n_model_items:
                break
            index = cursor[name]
            if index >= len(by_construct[name]):
                present.remove(name)
                continue
            chosen.append(by_construct[name][index])
            cursor[name] = index + 1
            progressed = True
        if not progressed:
            break

    items: list[StudyItem] = []
    for number, (explanation, construct, span) in enumerate(chosen):
        items.append(
            StudyItem(
                item_id=f"m{number:03d}",
                record_id=explanation.record_id,
                construct=construct,
                span_text=span.text,
                context=_sentence_around(explanation.text, span.start, span.end),
                item_type="model",
                span_start=span.start,
                span_end=span.end,
            )
        )

    # -- controls -----------------------------------------------------------
    n_control = max(1, round(len(items) * control_ratio)) if items else 0
    for number in range(n_control):
        explanation, construct, span = chosen[rng.randrange(len(chosen))]
        length = max(1, len(span.text.split()))
        drawn = _random_span(explanation.text, length, rng)
        if drawn is None:
            continue
        span_text, start, end = drawn
        items.append(
            StudyItem(
                item_id=f"c{number:03d}",
                record_id=explanation.record_id,
                construct=construct,
                span_text=span_text,
                context=_sentence_around(explanation.text, start, end),
                item_type="random_span",
                span_start=start,
                span_end=end,
            )
        )

    # -- mismatched ---------------------------------------------------------
    n_mismatch = max(1, round(len(chosen) * mismatch_ratio)) if chosen else 0
    for number in range(n_mismatch):
        explanation, construct, span = chosen[rng.randrange(len(chosen))]
        alternatives = [c for c in constructs if c != construct]
        items.append(
            StudyItem(
                item_id=f"x{number:03d}",
                record_id=explanation.record_id,
                construct=rng.choice(alternatives),
                span_text=span.text,
                context=_sentence_around(explanation.text, span.start, span.end),
                item_type="mismatched",
                span_start=span.start,
                span_end=span.end,
            )
        )

    rng.shuffle(items)
    return RatingSheet(
        items=tuple(items),
        seed=seed,
        rater_population=rater_population,
        construct_definitions=definitions,
    )


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def cohens_kappa(
    a: Sequence[str], b: Sequence[str], categories: Sequence[str] = SCALE
) -> float | None:
    """Unweighted Cohen's kappa between two raters.

    Returns `None` when it is undefined -- specifically when expected agreement
    is 1.0, which happens if both raters used exactly one category throughout.
    That case must not be reported as kappa=0 ("no agreement beyond chance")
    when the raters in fact agreed on every item; it is a degenerate marginal,
    and the honest report is the raw agreement rate with a note.
    """
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    expected = 0.0
    for category in categories:
        expected += (a.count(category) / n) * (b.count(category) / n)
    if expected >= 1.0:
        return None
    return (observed - expected) / (1 - expected)


@dataclass(frozen=True)
class StudyResult:
    """Everything the paper reports from the expert study."""

    rater_population: str
    n_items: int
    n_raters: int
    approval_by_type: dict[str, float]
    approval_by_construct: dict[str, float]
    kappa: float | None
    raw_agreement: float | None
    control_margin: float
    mismatch_approval: float
    passes_control: bool
    passes_attention_check: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "rater_population": self.rater_population,
            "n_items": self.n_items,
            "n_raters": self.n_raters,
            "approval_by_type": self.approval_by_type,
            "approval_by_construct": self.approval_by_construct,
            "cohens_kappa": self.kappa,
            "raw_agreement": self.raw_agreement,
            "control_margin": self.control_margin,
            "mismatch_approval": self.mismatch_approval,
            "passes_control": self.passes_control,
            "passes_attention_check": self.passes_attention_check,
        }


def analyse(
    sheet: RatingSheet,
    ratings: Sequence[dict[str, str]],
    *,
    approval: Sequence[str] = ("yes", "partly"),
    mismatch_ceiling: float = 0.30,
) -> StudyResult:
    """Compute approval rates, the control margin, and inter-rater kappa.

    `ratings` is one dict per rater, mapping `item_id -> rating`.

    **`partly` counts as approval by default, and that must be stated wherever
    the number appears.** It is the lenient reading. The strict reading
    (`approval=("yes",)`) is also computed by the runner and both are reported,
    because a single approval rate with an unstated threshold is the easiest
    number in this study to quietly optimise.

    `passes_control` -- model items approved more often than length-matched
    random spans -- is the actual claim. A high approval rate that does not beat
    its control is not evidence that the explanations are good.
    """
    by_id = {item.item_id: item for item in sheet.items}
    approved = set(approval)

    def rate(item_type: str) -> float:
        hits = total = 0
        for rater in ratings:
            for item_id, value in rater.items():
                item = by_id.get(item_id)
                if item is None or item.item_type != item_type:
                    continue
                total += 1
                hits += value in approved
        return hits / total if total else 0.0

    approval_by_type = {t: rate(t) for t in ITEM_TYPES}

    construct_rates: dict[str, float] = {}
    constructs = sorted({i.construct for i in sheet.items if i.item_type == "model"})
    for construct in constructs:
        hits = total = 0
        for rater in ratings:
            for item_id, value in rater.items():
                item = by_id.get(item_id)
                if item is None or item.item_type != "model" or item.construct != construct:
                    continue
                total += 1
                hits += value in approved
        construct_rates[construct] = hits / total if total else 0.0

    kappa = raw_agreement = None
    if len(ratings) >= 2:
        shared = sorted(
            item_id
            for item_id in set(ratings[0]) & set(ratings[1])
            if by_id.get(item_id) is not None and by_id[item_id].item_type == "model"
        )
        if shared:
            first = [ratings[0][i] for i in shared]
            second = [ratings[1][i] for i in shared]
            kappa = cohens_kappa(first, second)
            raw_agreement = sum(1 for x, y in zip(first, second, strict=True) if x == y) / len(
                shared
            )

    return StudyResult(
        rater_population=sheet.rater_population,
        n_items=len(sheet.items),
        n_raters=len(ratings),
        approval_by_type=approval_by_type,
        approval_by_construct=construct_rates,
        kappa=kappa,
        raw_agreement=raw_agreement,
        control_margin=approval_by_type["model"] - approval_by_type["random_span"],
        mismatch_approval=approval_by_type["mismatched"],
        passes_control=approval_by_type["model"] > approval_by_type["random_span"],
        passes_attention_check=approval_by_type["mismatched"] <= mismatch_ceiling,
    )
