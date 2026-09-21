"""Where the dashboard's construct probabilities come from.

Two backends ship, and the difference between them is the honest difference
between a demo and a result:

`ReplayBackend` replays a committed fixture derived from
`reports/explain/cards.md`. Those numbers *are* the paper's numbers -- the Phase
14 checkpoint's probabilities and the Phase 17 attributions, frozen. It cannot
score new text, and that is the point: reproducing a known example is the gate.

`LexiconBackend` scores arbitrary pasted text with the Phase 13 lexicon baseline
(`src.evaluation.baselines.CONSTRUCT_CUES`) in pure Python. It is **not the
paper's model**. It scores macro-F1 0.462 template-disjoint -- the honest floor
the transformer is measured against -- and it carries a known upward bias
(OPEN-021: its cue list and the template bank are both descended from
`taxonomy.yaml`'s positive examples). Every view built on it says so on screen.

Why no live transformer here
-----------------------------
The `dashboard` service in `docker-compose.yml` runs the *light* image, which has
no torch by design (Phase 2). Loading the checkpoint would mean the multi-GB
train image, a slow cold start, and a Docker gate that no longer runs in the
image the rest of the project uses. More importantly C2.7 binds: the paper's
model must not silently change, and the surest way to guarantee that is for the
demo not to hold it. A `TransformerBackend` satisfying this same Protocol is a
contained addition if a live demo is ever needed; `TransformerBaseline.load`
restores the tuned thresholds and must be used unmodified.

The lexicon emits presence, not probability -- and that is left visible
-----------------------------------------------------------------------
`LexiconBaseline.predict` returns a set of matched constructs. It has no
probability to give. Rather than invent one from cue-hit counts -- an arbitrary
formula that would look exactly like a model score on a bar chart -- the live
path reports **1.0 for matched and 0.0 for not matched**, and the view labels the
axis accordingly. The bars look blocky. Blocky and true beats smooth and
fabricated; a made-up magnitude on a screening tool is the kind of number that
gets quoted back without its formula.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.evaluation.baselines import CONSTRUCT_CUES
from src.explainability.attribution import (
    EXPLANATION_PROVENANCE,
    ConstructExplanation,
    RecordExplanation,
    TokenAttribution,
)
from src.models.dataset import CONSTRUCTS

#: What the length of a construct bar means. Different per backend, because it
#: genuinely differs, and a single axis label covering both would be false for
#: one of them.
PROBABILITY_SCALE = "P(construct present) from the Phase 14 checkpoint, replayed from cache"
PRESENCE_SCALE = "lexicon cue match: 1 = at least one cue matched, 0 = none. Not a probability"

LEXICON_CAVEAT = (
    "Live scoring uses the **lexicon baseline**, not the paper's model. The lexicon "
    "scores macro-F1 0.462 on the template-disjoint split -- the honest floor the "
    "transformer's 0.588 is measured against -- and it is not independent of the "
    "corpus (OPEN-021): its cue list and the corpus template bank were both written "
    "from the same taxonomy examples. Treat what you see as a floor with a known "
    "upward bias. The transformer is not loaded in this image (see the module "
    "docstring in src/dashboard/backend.py)."
)

REPLAY_CAVEAT = (
    "Replayed from a committed fixture derived from reports/explain/cards.md. These "
    "are the Phase 14 checkpoint's cached outputs on synthetic corpus records, not a "
    "live computation."
)


@dataclass(frozen=True)
class BackendResult:
    """One scored piece of text, in the shape the view needs and no other.

    `synthetic` is carried rather than inferred. It decides whether the resulting
    card can be exported to a figure, and inferring it from, say, whether a
    record id was supplied would be exactly the Phase 17 defect: a guard keyed to
    a field adjacent to the one that matters.
    """

    record_id: str
    text: str
    probabilities: dict[str, float]
    explanation: RecordExplanation
    synthetic: bool
    scale_label: str
    caveat: str
    source: str


@runtime_checkable
class PredictionBackend(Protocol):
    """Anything that can turn text into construct probabilities.

    Deliberately narrow. A backend does not know about risk fusion, cards,
    charts or Streamlit; the view composes those. Widening this Protocol is how
    business logic starts leaking toward the runtime.
    """

    name: str

    def predict(self, text: str) -> BackendResult: ...


# ---------------------------------------------------------------------------
# Lexicon backend -- live, pure Python, honest about what it is
# ---------------------------------------------------------------------------


def _cue_matches(text: str, cues: Sequence[str]) -> list[tuple[int, int]]:
    """Character spans of every cue occurrence.

    Mirrors `LexiconBaseline._matches` exactly -- phrase cues match as
    substrings, single-word cues match on a word boundary prefix -- but returns
    *positions* rather than a boolean, because the dashboard's first
    interpretability level is span -> construct and a detector that cannot point
    at anything has nothing to show.
    """
    low = text.lower()
    found: list[tuple[int, int]] = []
    for cue in cues:
        if " " in cue:
            start = low.find(cue)
            while start != -1:
                found.append((start, start + len(cue)))
                start = low.find(cue, start + 1)
        else:
            for match in re.finditer(rf"\b{re.escape(cue)}", low):
                found.append((match.start(), match.end()))
    return sorted(set(found))


#: Broadens detection for the LIVE dashboard demo only -- `CONSTRUCT_CUES` above
#: stays untouched because it also drives `src.evaluation.baselines.LexiconBaseline`,
#: whose macro-F1 0.462 is already committed in `reports/`. `LexiconBackend` is
#: already documented as "not the paper's model" (module docstring), so giving
#: its live copy a wider net is a difference this backend already has, not a new
#: one. The point raised on 2026-09-20: detection should reflect a stronger, more
#: robust sense of each construct -- more of the ways it is actually said -- not
#: a handful of exact phrases a generator can be tuned to reproduce. Drawn from
#: the same `taxonomy.yaml`-grounded realisation vocabulary every construct's
#: bank already uses in `src/ingestion/synthetic.py`, so nothing here is invented
#: outside the instruments already anchoring each construct.
DASHBOARD_EXTRA_CUES: dict[str, tuple[str, ...]] = {
    "cognitive_anxiety": (
        "nervous",
        "afraid",
        "scared",
        "second thoughts",
        "keep thinking",
        "turning over",
        "hundred times",
        "lost this in my head",
        "convinced myself",
        "wonder whether",
        # Phase 31 -- see the note below this dict.
        "thinking about the result",
        "crosses my mind",
        "coming up short",
        "the bad version",
        "see myself failing",
        "what everyone will say",
    ),
    "somatic_anxiety": (
        "butterflies",
        "wired",
        "flutter",
        "unsettled",
        "shaking",
        "trembling",
        "quivering",
        "racing",
        "woke at",
        "breathing quicken",
        "lighter than usual",
    ),
    "self_confidence": (
        "trust my preparation",
        "handled this before",
        "expect to win",
        "best prepared",
        "nothing to fear",
        "know what i'm capable",
        "fair chance",
        "done the work",
        "can be competitive",
        "decent account",
        "handled this level",
    ),
    "perceived_stress": (
        "on right now",
        "no clear day",
        "running on empty",
        "not stopped coming",
        "fuller than",
        "piled up",
        "juggling",
        "demands",
        "busier week",
        "more going on",
        "more noise around",
        "want something from me",
        "clear day",
        "could not say no",
    ),
    "burnout_signal": (
        "just drained",
        "going through the motions",
        "stopped mattering",
        "nothing left to give",
        "not what it was",
        "spark is not",
        "duty than a choice",
        "job i want to finish",
        "enthusiasm",
        "rest day",
        "stopped looking forward",
        "tiredness",
        "slightest difference",
    ),
    "resilience": (
        "find my way",
        "recovered from",
        "hold on to",
        "not the end of it",
        "proved that to myself",
        "get through them",
        "another plan",
        "find a way back",
        "rough patches",
        "would not be the end",
        "build another one",
        "finished strongly",
    ),
    "motivation_orientation": (
        "find out how good",
        "push it from",
        "chasing something",
        "not embarrass myself",
        "not to mess",
        "settle for",
        "attack it",
        "going badly wrong",
        "not fall apart",
        "not falling apart",
        "bracing for it",
    ),
    "attentional_focus": (
        "narrowed it down",
        "on the process",
        "nothing past that",
        "on my phone",
        "checking what everyone",
        "everywhere except",
        "pulls me straight back",
        "scoreline",
        "on the timeline",
        "is the plan and",
    ),
    "coping_style": (
        "go back to",
        "have a plan for",
        "three things i control",
        "same warm-up",
        "break it into",
        "avoiding the video",
        "switching the subject",
        "keep myself busy",
        "hide from the rest",
        "dodging the video",
    ),
    "appraisal_orientation": (
        "chance to meet it",
        "tools for it",
        "reason i train",
        "out of my depth",
        "too big a step",
        "chance i wanted",
        "making of me",
        "undoing of me",
        "i have the tools",
        "put the work in",
        "anywhere near enough",
        "part of me thinks i can handle",
    ),
}

#: **Phase 31 extension (2026-09-21), and how the additions were chosen.**
#:
#: `reports/abstention.md` measured the cost of the narrow list: 58.6% of the
#: corpus reaches the scorer, matches no cue at all, and is handed back an index
#: of exactly 0.50 -- the `no_detection` route, which no gate addresses because
#: the text is perfectly good. Widening the demo list is the cheapest honest
#: lever on that number, and the owner chose it on 2026-09-21 over the three
#: alternatives (a different polarity policy, both, or removing the sec.12.3
#: refusal rule -- measured at +0.2% and declined).
#:
#: **The additions were not invented and were not mined from the corpus.** Every
#: phrase above came from a realisation template in
#: `src.ingestion.synthetic.GRADED_REALISATIONS` or `CATEGORICAL_REALISATIONS`
#: that states its own construct plainly and that the previous list still
#: missed -- e.g. burnout's "I'm tired in a way that a rest day doesn't seem to
#: fix" matched nothing at all. Those banks are anchored to
#: `config/taxonomy.yaml` instruments, so provenance is unchanged from the
#: original additions.
#:
#: Mining the *corpus text* would have been the wrong source: it fits the
#: detector to the evaluation set, which is OPEN-021 arriving by another route.
#: Mining the *templates* fits it to the taxonomy's own vocabulary, which is
#: what a lexicon is supposed to encode.
#:
#: **This list still has no measured score**, and widening it does not give it
#: one. `LexiconBaseline` is untouched, so macro-F1 0.462 and every figure
#: derived from it stand. `tests/test_abstention.py` holds the two lists apart.


@dataclass
class LexiconBackend:
    """The Phase 13 lexicon baseline, wired for one piece of text at a time.

    Detection uses `CONSTRUCT_CUES` widened with `DASHBOARD_EXTRA_CUES` (live
    demo only -- see that dict's docstring for why the two lists are separate).
    """

    name: str = "lexicon"

    def predict(self, text: str) -> BackendResult:
        probabilities: dict[str, float] = {}
        explanations: list[ConstructExplanation] = []
        for construct in CONSTRUCTS:
            cues = CONSTRUCT_CUES.get(construct, ()) + DASHBOARD_EXTRA_CUES.get(construct, ())
            spans = _cue_matches(text, cues)
            probabilities[construct] = 1.0 if spans else 0.0
            if spans:
                explanations.append(
                    ConstructExplanation(
                        construct=construct,
                        probability=1.0,
                        method="lexicon_cue_match",
                        tokens=tuple(
                            TokenAttribution(token=text[start:end], start=start, end=end, score=1.0)
                            for start, end in spans
                        ),
                        source_text=text,
                    )
                )
        return BackendResult(
            # Not a corpus id, and deliberately not derived from the text -- no
            # hash of the user's words is retained anywhere.
            record_id="pasted-text",
            text=text,
            probabilities=probabilities,
            explanation=RecordExplanation(
                record_id="pasted-text",
                text=text,
                method="lexicon_cue_match",
                explanations=tuple(explanations),
                provenance=(
                    "Lexicon cue matching against taxonomy-derived cues. No model was "
                    "run. This shows which cue words were present, not what predicts "
                    "psychological risk in people. Not a clinical instrument."
                ),
            ),
            # False: the text belongs to whoever pasted it. This is what makes
            # the resulting view non-exportable.
            synthetic=False,
            scale_label=PRESENCE_SCALE,
            caveat=LEXICON_CAVEAT,
            source="lexicon (live)",
        )


# ---------------------------------------------------------------------------
# Replay backend -- the known examples the gate reproduces
# ---------------------------------------------------------------------------


@dataclass
class ReplayBackend:
    """Replays committed Phase 17 outputs. The only path that can be exported.

    Built from a fixture rather than from `reports/explain/attributions.json`
    directly so the gate has something byte-stable to compare against: the report
    is regenerated whenever `scripts/run_explain.py` runs, and a gate that moves
    with its subject is not a gate.
    """

    name: str = "replay"
    examples: dict[str, BackendResult] = field(default_factory=dict)
    fixture_path: Path | None = None

    @property
    def example_ids(self) -> tuple[str, ...]:
        return tuple(self.examples)

    @classmethod
    def from_fixture(cls, path: Path) -> ReplayBackend:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        examples: dict[str, BackendResult] = {}
        for entry in payload["examples"]:
            explanations = tuple(
                ConstructExplanation(
                    construct=e["construct"],
                    probability=float(e["probability"]),
                    method=e["method"],
                    tokens=tuple(
                        TokenAttribution(
                            token=t["token"],
                            start=int(t["start"]),
                            end=int(t["end"]),
                            score=float(t["score"]),
                        )
                        for t in e["tokens"]
                    ),
                    completeness_error=e.get("completeness_error"),
                    source_text=entry["text"],
                )
                for e in entry["explanations"]
            )
            examples[entry["record_id"]] = BackendResult(
                record_id=entry["record_id"],
                text=entry["text"],
                probabilities={k: float(v) for k, v in entry["probabilities"].items()},
                explanation=RecordExplanation(
                    record_id=entry["record_id"],
                    text=entry["text"],
                    method=entry["method"],
                    explanations=explanations,
                    provenance=entry.get("provenance", EXPLANATION_PROVENANCE),
                ),
                synthetic=bool(entry["synthetic"]),
                scale_label=PROBABILITY_SCALE,
                caveat=REPLAY_CAVEAT,
                source="replay (cached Phase 14 checkpoint)",
            )
        return cls(examples=examples, fixture_path=Path(path))

    def get(self, example_id: str) -> BackendResult:
        try:
            return self.examples[example_id]
        except KeyError:
            raise KeyError(
                f"{example_id!r} is not a committed known example. Available: "
                f"{', '.join(self.examples)}"
            ) from None

    def predict(self, text: str) -> BackendResult:
        """Replay by exact text match, or refuse.

        A replay backend that silently returned the nearest example would make
        the dashboard look as though it had scored the user's text. It refuses
        instead.
        """
        for result in self.examples.values():
            if result.text == text:
                return result
        raise KeyError(
            "The replay backend holds only committed known examples and cannot "
            "score new text. Switch to the lexicon backend for live scoring."
        )
