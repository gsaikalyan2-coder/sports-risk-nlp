"""Utterance segmentation with character offsets.

Segmentation exists here for a reason that only shows up much later. The
project's headline contribution is **span-level** interpretability: an
explanation says "this construct, because of these words". That means every
unit the model ever sees has to be locatable in the text it came from, and the
only way to guarantee that is to carry `(start, end)` offsets from the first
split rather than reconstruct them at Phase 16 by searching for a substring
that may occur twice.

So `Utterance` carries offsets into the **normalised parent text**, and the
test suite asserts `parent[u.start:u.end] == u.text` for every utterance of
every record. If that invariant ever breaks, span attribution is silently
pointing at the wrong words, which is the one failure mode a coach-facing
explanation cannot survive.

The splitter is rule-based and offline. No `nltk`, no `spacy`: both would add a
model download to a pipeline that `CLAUDE.md` sec.8 requires to run
reproducibly from a fresh clone, and neither is obviously better on the short,
first-person, lightly-punctuated text this corpus is made of.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Abbreviations whose trailing period is not a sentence end. Deliberately
#: short: over-listing costs recall on real boundaries, and the honorifics are
#: the ones that actually matter here because they precede names.
_ABBREVIATIONS = frozenset(
    """
    dr mr mrs ms prof sr jr st vs etc no approx dept univ fig al inc ltd co
    e.g i.e a.m p.m u.s u.k
    """.split()
)

_MIN_UTTERANCE_CHARS = 2

#: A boundary candidate: terminal punctuation, optional closing quote/bracket,
#: then whitespace. The lookahead does not require an uppercase next character
#: -- informal athlete text frequently continues lowercase, and requiring caps
#: would merge half the corpus into single giant utterances.
_BOUNDARY_RE = re.compile(r"""([.!?]+)(["')\]]*)(\s+)""")

_ABBREV_TAIL_RE = re.compile(r"([A-Za-z][A-Za-z.]*)$")


@dataclass(frozen=True)
class Utterance:
    """One segment of a record, with offsets into the text it was cut from."""

    index: int
    text: str
    start: int
    end: int

    def to_dict(self) -> dict[str, int | str]:
        return {"index": self.index, "text": self.text, "start": self.start, "end": self.end}


def _is_abbreviation(text: str, punct_start: int) -> bool:
    """True if the period at `punct_start` closes a known abbreviation."""
    match = _ABBREV_TAIL_RE.search(text[:punct_start])
    if not match:
        return False
    token = match.group(1).lower().rstrip(".")
    if token in _ABBREVIATIONS:
        return True
    # A single letter followed by a period is an initial ("Ellery V. Vance"),
    # not a sentence end.
    return len(token) == 1 and token.isalpha()


def _is_decimal(text: str, punct_start: int, punct_end: int) -> bool:
    """True for the period inside `3.5` -- a decimal point, not a full stop."""
    before = text[punct_start - 1] if punct_start > 0 else ""
    after = text[punct_end] if punct_end < len(text) else ""
    return before.isdigit() and after.isdigit()


def segment(text: str) -> list[Utterance]:
    """Split normalised `text` into utterances carrying character offsets.

    Empty and whitespace-only input yields an empty list rather than one empty
    utterance. An empty utterance would pass through the pipeline, reach the
    labeller, and consume a paid API call to be told there is nothing there.
    """
    if not text or not text.strip():
        return []

    boundaries: list[int] = []
    for match in _BOUNDARY_RE.finditer(text):
        punct_start, punct_end = match.span(1)
        if _is_abbreviation(text, punct_start) or _is_decimal(text, punct_start, punct_end):
            continue
        boundaries.append(match.end(2))

    utterances: list[Utterance] = []
    cursor = 0
    index = 0
    for boundary in [*boundaries, len(text)]:
        raw = text[cursor:boundary]
        stripped = raw.strip()
        if len(stripped) >= _MIN_UTTERANCE_CHARS:
            offset = cursor + (len(raw) - len(raw.lstrip()))
            utterances.append(
                Utterance(
                    index=index,
                    text=stripped,
                    start=offset,
                    end=offset + len(stripped),
                )
            )
            index += 1
        cursor = boundary

    return utterances


def verify_offsets(parent_text: str, utterances: list[Utterance]) -> list[str]:
    """Return a list of offset violations. Empty means every span is exact.

    Used by the pipeline as an assertion rather than by tests alone, because a
    broken offset produces plausible-looking output and is invisible in a
    spot-check.
    """
    problems: list[str] = []
    for utterance in utterances:
        sliced = parent_text[utterance.start : utterance.end]
        if sliced != utterance.text:
            problems.append(
                f"utterance {utterance.index}: offsets [{utterance.start}:{utterance.end}] "
                f"slice {sliced!r} but text is {utterance.text!r}"
            )
    return problems
