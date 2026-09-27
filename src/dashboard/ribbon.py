"""Phase 34 V7 -- one passage, scored sentence by sentence, with its shape kept.

What this adds that the rest of the page does not
------------------------------------------------
Every other surface reduces a passage to one number and ten rows. A passage has
a *contour*: a calm opening, a spike in the middle, a flat close. That contour is
the closest thing this project has to the temporal claim `.claude.md` section 10
parks as Future Work, and it costs nothing new to show -- `segment()` has carried
character offsets since Phase 8 precisely so that every unit the model sees is
locatable in the text it came from.

The one defect this module is shaped around
-------------------------------------------
`.claude.md` section 12.3 is the whole design constraint. `LexiconBackend` scores
anything: a sentence with no cue match gets ten zero probabilities, a weighted
sum of 0.0, and a logistic squash of **exactly 0.50** -- a band drawn at
half-height, indistinguishable from a real middling sentence. A ribbon over ten
sentences would draw a flat mid-height fence and call it a contour.

So a band that detected nothing **cannot hold a number**. `SentenceBand` refuses
construction when `detected` and `surface` disagree, in the same way
`ScoreSurface` refuses a missing stamp and `BiosignalWindow` refuses a missing
provenance string. Not checked at render time: the render is the step most likely
to be reimplemented.

A second state exists and is marked separately. A sentence whose only detected
constructs are inert has a *real* index of 0.50 -- nothing was fabricated, the
pushes genuinely summed to zero -- and its band is drawn hatched with the words
"counted as zero", the three-channel marking `charts.py` already uses. Two
different facts, two different markings, neither of them a bare 0.50 bar.

Why the lexicon and not the paper's model
-----------------------------------------
Per-sentence scoring needs a backend that can score *new* text.
`ReplayBackend.predict` refuses by design, so the ribbon runs on
`LexiconBackend` and inherits `LEXICON_CAVEAT` verbatim -- the floor, with its
known upward bias (OPEN-021), carried on screen rather than quietly swapped for
the transformer's reputation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.dashboard.backend import LexiconBackend, PredictionBackend
from src.dashboard.gibberish import admit
from src.dashboard.view import ScoreSurface, build_view
from src.preprocessing.segment import segment, verify_offsets
from src.risk.fusion import LinearRiskScorer

#: A ribbon of one band is not a contour, it is a bar with a caption claiming to
#: be a shape. Refused rather than drawn, because the misreading is the feature.
MIN_SENTENCES = 2

#: Enough to read the shape; beyond this the rows stop being legible at figure
#: width and the page would be scrolling a chart. Extra sentences are not
#: silently dropped -- `build_ribbon` refuses and says how many it found.
MAX_SENTENCES = 24


class RibbonRefused(ValueError):
    """The passage cannot be drawn as a ribbon, and here is the plain reason.

    Carries user-facing wording in `str(exc)`: the page prints it unchanged. A
    refusal that says "invalid input" teaches the reader nothing and invites them
    to paste the same thing again -- the argument `gibberish.TextAdmission`
    already makes for its `detail` field.
    """


@dataclass(frozen=True)
class SentenceBand:
    """One sentence of the passage, and what the index did there.

    `surface` is `None` exactly when nothing was detected. That is the section
    12.3 rule made structural: an input that cannot be read produces no number,
    never a zero, never a default and never a midpoint.
    """

    index: int
    text: str
    start: int
    end: int
    detected: bool
    moved: bool
    surface: ScoreSurface | None
    constructs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.detected != (self.surface is not None):
            raise ValueError(
                f"sentence {self.index} is detected={self.detected} and disagrees with "
                "its own number. A sentence the detector had nothing to say about may "
                "not hold an index: an all-zero decomposition squashes to exactly 0.50, "
                "which draws as a middling sentence. See .claude.md section 12.3."
            )
        if self.moved and not self.detected:
            raise ValueError(f"sentence {self.index} moved the index without being detected")
        if self.end <= self.start:
            raise ValueError(f"sentence {self.index} has an empty span")

    @property
    def value(self) -> float | None:
        """The index, or `None` where there is nothing to draw."""
        return self.surface.value if self.surface else None

    @property
    def chars(self) -> int:
        """Band width is proportional to this: a long sentence is a wide band."""
        return self.end - self.start

    @property
    def state(self) -> str:
        """The three states, as the word the figure prints. Never a colour alone."""
        if not self.detected:
            return "nothing detected"
        if not self.moved:
            return "counted as zero"
        return "moves the index"


@dataclass(frozen=True)
class Ribbon:
    """A whole passage as a contour, plus the passage's own single number.

    `whole` is scored over the full text rather than averaged from the bands, and
    the figure says so. Averaging would be wrong twice: the logistic squash is
    not linear, and a sentence the detector skipped has no value to average in.
    """

    text: str
    bands: tuple[SentenceBand, ...]
    whole: ScoreSurface
    scale_label: str
    caveat: str
    source: str

    def __post_init__(self) -> None:
        if len(self.bands) < MIN_SENTENCES:
            raise ValueError(f"a ribbon needs at least {MIN_SENTENCES} bands")
        for band in self.bands:
            if self.text[band.start : band.end] != band.text:
                raise ValueError(
                    f"band {band.index} claims offsets [{band.start}:{band.end}] that do "
                    "not slice its own text. Span attribution would be pointing at the "
                    "wrong words -- the one failure a span-level explanation cannot "
                    "survive (src/preprocessing/segment.py)."
                )

    @property
    def stamp(self) -> str:
        return self.whole.stamp

    @property
    def n_silent(self) -> int:
        """Sentences the detector had nothing to say about. Printed, not hidden."""
        return sum(1 for b in self.bands if not b.detected)

    @property
    def n_inert_only(self) -> int:
        return sum(1 for b in self.bands if b.detected and not b.moved)

    @property
    def scored(self) -> tuple[SentenceBand, ...]:
        return tuple(b for b in self.bands if b.surface is not None)

    @property
    def peak(self) -> SentenceBand | None:
        """The highest-scoring sentence, or `None` if none was scored at all."""
        return max(self.scored, key=lambda b: b.surface.value, default=None)

    @property
    def spread(self) -> float:
        """Highest scored band minus lowest. Zero when fewer than two were scored.

        The one number that says whether the passage has a shape at all. A reader
        looking at a nearly flat ribbon is entitled to that in digits rather than
        being asked to eyeball four pixels.
        """
        values = [b.surface.value for b in self.scored]
        return max(values) - min(values) if len(values) > 1 else 0.0


def build_ribbon(
    text: str,
    *,
    backend: PredictionBackend | None = None,
    scorer: LinearRiskScorer | None = None,
    context: Mapping[str, float] | None = None,
) -> Ribbon:
    """Segment `text`, score each sentence on its own, and score the whole.

    Refuses rather than degrades, in three places, each with a reason a reader can
    act on: text that is not language (`gibberish.admit`, the paste-box door from
    Phase 27), a passage with too few sentences to have a shape, and one with too
    many to draw.
    """
    admission = admit(text)
    if not admission:
        raise RibbonRefused(admission.detail)

    utterances = segment(text)
    if problems := verify_offsets(text, utterances):
        # Cannot happen through `segment` -- asserted anyway, because the figure's
        # whole claim is that band N is *those* words.
        raise RibbonRefused(f"Segmentation produced an offset that does not hold: {problems[0]}")
    if len(utterances) < MIN_SENTENCES:
        raise RibbonRefused(
            "This is one sentence, and a ribbon is a comparison between sentences. "
            f"Paste at least {MIN_SENTENCES} -- a few lines of what an athlete wrote "
            "before a competition."
        )
    if len(utterances) > MAX_SENTENCES:
        raise RibbonRefused(
            f"That is {len(utterances)} sentences, and the figure stops being readable "
            f"past {MAX_SENTENCES}. Trim it rather than have the chart drop the tail "
            "without telling you."
        )

    backend = backend or LexiconBackend()
    whole = build_view(text=text, backend=backend, scorer=scorer, context=context)

    bands: list[SentenceBand] = []
    for utterance in utterances:
        view = build_view(text=utterance.text, backend=backend, scorer=scorer, context=context)
        detected = tuple(b.construct for b in view.bars if b.detected)
        moved = any(b.contribution != 0.0 for b in view.bars)
        bands.append(
            SentenceBand(
                index=utterance.index,
                text=utterance.text,
                start=utterance.start,
                end=utterance.end,
                detected=bool(detected),
                moved=moved,
                # The section 12.3 rule, at the only place it can be enforced: no
                # detection, no number. Not 0.0, not 0.5, not None drawn as zero.
                surface=view.risk if detected else None,
                constructs=detected,
            )
        )

    return Ribbon(
        text=text,
        bands=tuple(bands),
        whole=whole.risk,
        scale_label=whole.scale_label,
        caveat=whole.caveat,
        source=whole.source,
    )
