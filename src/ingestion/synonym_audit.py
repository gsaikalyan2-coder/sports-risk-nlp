"""An exhaustive audit of the generator's lexical-variation layer.

Why this module exists
----------------------
OPEN-015 was found by a human reading roughly twenty records and noticing
"corner of me". That is not a method, it is luck, and luck does not scale to a
bank of 65 synonym groups.

The v1.1 bank was reviewed against a stated rule: every group shares a **part of
speech** and an **argument structure**. `("part", "portion", "corner", "piece")`
satisfies both, and still produced "corner of me", because the tokens sit inside
the idiom *part of me* and idiom membership is a third constraint neither of the
first two implies. Once one class of constraint has been shown to be missing,
the honest response is to enumerate the space rather than read more records.

The enumeration is small enough to be exhaustive
------------------------------------------------
`_vary` in `synthetic.py` performs **independent, context-blind, single-token**
substitutions. So every defect it can create is visible in some
(template, token position, replacement) triple. There are a few hundred of
those. This module generates all of them and applies five mechanical probes.

Two things follow, and both matter for the paper:

* Exhaustive over single substitutions is a real guarantee, not a sample. A
  defect this sweep does not flag is either outside the five probe classes or
  requires two simultaneous substitutions to appear.
* It is **not** exhaustive over rendered corpora. Discourse framing, slot
  filling and multiple substitutions in one sentence interact. The corpus-side
  counts in `corpus_prevalence` are what say how often a flagged frame was
  actually realised at a given seed.

The ratchet
-----------
Probes flag *candidates*; a human rules on each. Those rulings live in
`VERDICTS`, keyed by the literal token sequence the defect would leave in the
text. A test asserts that every flagged signature has a recorded verdict, so
editing `SYNONYM_GROUPS` or the template bank in a way that creates a new
flagged frame fails the build until somebody rules on it. That is the control
OPEN-015 did not have.

Scope note, easy to get wrong: `INTERPRETATION_REALISATIONS` and the
end-of-record neutral fallback are rendered **without** `_vary` (read
`generate_records`). They cannot carry a substitution defect, so they are not
enumerated here -- and that asymmetry is itself worth knowing, because it means
those sentences appear verbatim and inflate the corpus duplicate rate.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from .substitution_verdicts import (
    ACCEPTABLE,
    BROKEN,
    DEGRADED,
    VERDICTS,
    contains,
    sentences,
    tokenise,
)
from .synthetic import (
    _SYNONYM_INDEX,
    CATEGORICAL_REALISATIONS,
    GRADED_REALISATIONS,
    NEUTRAL_SENTENCES,
    SPORTS,
    _fill,
)

__all__ = [
    "ACCEPTABLE",
    "BROKEN",
    "DEGRADED",
    "VERDICTS",
    "Finding",
    "SubstitutionEvent",
    "audit",
    "contains",
    "corpus_prevalence",
    "defect_rate",
    "defective",
    "sentences",
    "substitution_events",
    "tokenise",
    "unreviewed",
    "varied_templates",
]

#: `tokenise`, `sentences` and `contains` used to live here. They moved to
#: `substitution_verdicts.py` at OPEN-016, when the generator started needing
#: them too and a circular import (`synthetic` -> `synonym_audit` -> `synthetic`)
#: made a shared third module the only workable arrangement. They are re-exported
#: above so every existing call site and test keeps working unchanged.

# ---------------------------------------------------------------------------
# Probe inputs. Each of these is a judgement written down once, in one place,
# rather than a judgement re-made by whoever reads the diff.
# ---------------------------------------------------------------------------

#: Fixed expressions occurring in the template bank, as token sequences.
#:
#: Hand-built, and it has to be: idiom membership is a lexical fact about
#: English, not a property derivable from the bank. It was built by reading all
#: 93 varied templates once. An entry earns its place by being a phrase whose
#: meaning is not the sum of its words, so that substituting any member changes
#: or destroys the sense even when the substitute is a fair synonym in isolation.
FIXED_EXPRESSIONS: tuple[str, ...] = (
    "part of me",  # OPEN-015. Group removed at v1.2; kept as a regression guard.
    "out of my hands",  # "beyond my control", not anatomy.
    "the rest of the day",  # rest = remainder, not repose.
    "a rest day",  # compound noun.
    "start line",  # compound noun, and it arrives through the {START} slot.
    "like to think",
    "the first half wrong",  # the frame is "get X wrong".
    "nothing past that",
    "on a good day",
    "the point of the session",
    "all i think about",
)

#: Tokens the bank treats as plural. Explicit rather than suffix-guessed:
#: "insides" is plural and "gas" is not, and no rule short of a lexicon tells
#: them apart.
PLURAL_TOKENS: frozenset[str] = frozenset(
    {
        "hands",
        "fingers",
        "legs",
        "limbs",
        "quads",
        "insides",
        "notes",
        "stands",
        "spectators",
        "exams",
        "studies",
        "assessments",
        "second thoughts",
        "all of them",
        "nerves",
    }
)

#: Determiners that force a singular head noun.
_SINGULAR_DETERMINERS = frozenset({"a", "an", "this", "that", "the slightest"})
#: Verb forms that force a singular subject.
_SINGULAR_VERBS = frozenset({"is", "was", "has", "seems", "feels", "does", "keeps", "wants"})
#: Verb forms that force a plural subject.
_PLURAL_VERBS = frozenset({"are", "were", "have", "seem", "feel", "do", "keep", "want"})

#: Prepositions and particles. A word's argument structure lives here, so any
#: substitution sitting immediately before one is a candidate defect.
_PARTICLES = frozenset(
    {
        "about",
        "of",
        "with",
        "on",
        "for",
        "to",
        "at",
        "from",
        "into",
        "in",
        "off",
        "up",
        "down",
        "back",
        "against",
        "over",
    }
)

#: Frames that select a particular inflected form of the following word.
_FORM_SELECTORS = frozenset({"can", "could", "cannot", "to", "stop", "will", "would", "must"})

_VOWELS = frozenset("aeiou")


@dataclass(frozen=True)
class SubstitutionEvent:
    """One thing `_vary` is capable of doing, in one place."""

    template_id: str
    original: str
    replacement: str
    index: int
    tokens: tuple[str, ...]
    #: Indices whose source token ended a sentence. A frame does not reach
    #: across a full stop, so neither does a probe.
    breaks: frozenset[int] = frozenset()

    @property
    def previous(self) -> str:
        if not self.index or (self.index - 1) in self.breaks:
            return ""
        return self.tokens[self.index - 1]

    @property
    def following(self) -> str:
        if self.index in self.breaks or self.index + 1 >= len(self.tokens):
            return ""
        return self.tokens[self.index + 1]

    def rendered(self) -> tuple[str, ...]:
        out = list(self.tokens)
        out[self.index : self.index + 1] = tokenise(self.replacement)
        return tuple(out)

    def window(self, before: int = 2, after: int = 2) -> str:
        rendered = self.rendered()
        width = len(tokenise(self.replacement))
        lo = max(0, self.index - before)
        hi = min(len(rendered), self.index + width + after)
        return " ".join(rendered[lo:hi])


@dataclass(frozen=True)
class Finding:
    """A flagged event, plus the literal string it would leave in the corpus."""

    event: SubstitutionEvent
    probe: str
    signature: str

    @property
    def verdict(self) -> str:
        return VERDICTS.get(self.signature, "UNREVIEWED")


def varied_templates() -> list[tuple[str, str]]:
    """Every template that `_vary` is applied to, as (template_id, text).

    **Filled with every sport, not one.** The first version of this function
    filled with a single sport on the assumption that `{EVENT}` and `{START}`
    never contain a substitutable token. The assumption was wrong and a test
    written to check it caught the mistake: `{EVENT}` fills with *race*, which
    is in `("race", "event", "contest")`, and `{START}` fills with *start line*
    and *start*, which are in `("start", "outset", "opening", "beginning")`.
    Filling with one sport would therefore have left frames unenumerated, and an
    exhaustive sweep that is not exhaustive is worse than no sweep, because it
    licenses the conclusion "we checked".

    Identical fillings are deduplicated -- several sports share a contest noun.
    """
    out: list[tuple[str, str]] = []
    for construct, by_intensity in GRADED_REALISATIONS.items():
        for intensity, bank in by_intensity.items():
            for i, template in enumerate(bank):
                out.append((f"{construct}:i{intensity}:{i}", template))
    for construct, by_label in CATEGORICAL_REALISATIONS.items():
        for label, bank in by_label.items():
            for i, template in enumerate(bank):
                out.append((f"{construct}:{label}:{i}", template))
    for i, template in enumerate(NEUTRAL_SENTENCES):
        out.append((f"neutral:{i}", template))

    filled: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for template_id, text in out:
        for sport in SPORTS:
            pair = (template_id, _fill(text, sport))
            if pair not in seen:
                seen.add(pair)
                filled.append(pair)
    return filled


def substitution_events() -> list[SubstitutionEvent]:
    """The complete single-token substitution space over the varied bank."""
    events: list[SubstitutionEvent] = []
    for template_id, text in varied_templates():
        tokens: list[str] = []
        breaks: set[int] = set()
        for sentence in sentences(text):
            tokens.extend(tokenise(sentence))
            breaks.add(len(tokens) - 1)
        frozen, frozen_breaks = tuple(tokens), frozenset(breaks)
        for index, token in enumerate(frozen):
            group = _SYNONYM_INDEX.get(token)
            if group is None:
                continue
            for replacement in group:
                if replacement == token:
                    continue
                events.append(
                    SubstitutionEvent(template_id, token, replacement, index, frozen, frozen_breaks)
                )
    return events


# ---------------------------------------------------------------------------
# The five probes. Each returns a signature when it fires, otherwise None.
# ---------------------------------------------------------------------------


def _probe_idiom(event: SubstitutionEvent) -> str | None:
    """The substituted token sits inside a fixed expression. This is OPEN-015."""
    for phrase in FIXED_EXPRESSIONS:
        needle = tokenise(phrase)
        n = len(needle)
        for start in range(max(0, event.index - n + 1), event.index + 1):
            if tuple(event.tokens[start : start + n]) == tuple(needle):
                broken = list(event.tokens[start : start + n])
                broken[event.index - start : event.index - start + 1] = tokenise(event.replacement)
                return " ".join(broken)
    return None


def _probe_article(event: SubstitutionEvent) -> str | None:
    """`a` before a vowel, or `an` before a consonant."""
    if event.previous not in {"a", "an"}:
        return None
    first = tokenise(event.replacement)[0][:1]
    needs_an = first in _VOWELS
    if (event.previous == "an") == needs_an:
        return None
    return f"{event.previous} {event.replacement.lower()}"


def _probe_number(event: SubstitutionEvent) -> str | None:
    """Singular/plural disagreement with a determiner or a neighbouring verb."""
    original_plural = event.original in PLURAL_TOKENS
    replacement_plural = event.replacement.lower() in PLURAL_TOKENS
    if original_plural == replacement_plural:
        return None
    if event.previous in _SINGULAR_DETERMINERS and replacement_plural:
        return f"{event.previous} {event.replacement.lower()}"
    if event.following in _SINGULAR_VERBS and replacement_plural:
        return f"{event.replacement.lower()} {event.following}"
    if event.following in _PLURAL_VERBS and not replacement_plural:
        return f"{event.replacement.lower()} {event.following}"
    return None


def _probe_particle(event: SubstitutionEvent) -> str | None:
    """The substitution is immediately followed by a preposition or particle.

    Verb and adjective argument structure lives in exactly this position --
    "think **about**" but not "figure about", "worried **that**" but not "on
    edge that". The probe cannot decide which pairs are attested without a
    lexicon, so it flags the frame and `VERDICTS` records the ruling.
    """
    if event.following not in _PARTICLES:
        return None
    return f"{event.replacement.lower()} {event.following}"


def _probe_form(event: SubstitutionEvent) -> str | None:
    """A modal or `to` selects a bare form; a replacement in -ed/-ing breaks it."""
    if event.previous not in _FORM_SELECTORS:
        return None
    replacement = event.replacement.lower()
    original_inflected = event.original.endswith(("ed", "ing"))
    replacement_inflected = replacement.endswith(("ed", "ing"))
    if original_inflected == replacement_inflected:
        return None
    return f"{event.previous} {replacement}"


def _probe_arity(event: SubstitutionEvent) -> str | None:
    """A single word is swapped for a phrase, or the reverse.

    The riskiest shape of all, and the one the particle probe cannot see. A
    multi-word substitute carries its own internal syntax into a slot that was
    cut for one word: "I'm worried I'll let everyone down" becomes "I'm **on
    edge** I'll let everyone down", because *on edge* takes no clausal
    complement while *worried* does. The following token there is a pronoun, so
    no particle is adjacent and nothing else in this module would notice.
    """
    if (len(tokenise(event.replacement)) > 1) == (len(tokenise(event.original)) > 1):
        return None
    # A signature must carry at least one context token, or it stops being
    # diagnostic: bare "off the rails" matches both the broken "get the first
    # half off the rails" and the perfectly good "it's going to go off the
    # rails", and `corpus_prevalence` would then charge the second to the first.
    # At a sentence end there is no following token, so take the preceding one.
    if event.following:
        return f"{event.replacement.lower()} {event.following}"
    if event.previous:
        return f"{event.previous} {event.replacement.lower()}"
    return None


PROBES = (
    ("idiom", _probe_idiom),
    ("article", _probe_article),
    ("number", _probe_number),
    ("particle", _probe_particle),
    ("form", _probe_form),
    ("arity", _probe_arity),
)


def audit(events: Iterable[SubstitutionEvent] | None = None) -> list[Finding]:
    """Run every probe over every event. Deterministic and offline."""
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for event in events if events is not None else substitution_events():
        for name, probe in PROBES:
            signature = probe(event)
            if signature is None or (name, signature) in seen:
                continue
            seen.add((name, signature))
            findings.append(Finding(event, name, signature))
    return sorted(findings, key=lambda f: (f.probe, f.signature))


def unreviewed(findings: Iterable[Finding]) -> list[str]:
    """Signatures with no recorded human ruling. Must be empty (see tests)."""
    return sorted({f.signature for f in findings if f.verdict == "UNREVIEWED"})


def corpus_prevalence(findings: Iterable[Finding], texts: Iterable[str]) -> dict[str, int]:
    """How many of `texts` actually contain each flagged signature.

    A flagged frame is a thing the generator *can* produce. This is the count of
    what it *did* produce at the seed in use, which is the number the report
    quotes -- the two differ, and quoting the first as the second would overstate
    the defect by the size of the search space.
    """
    signatures = {f.signature: tokenise(f.signature) for f in findings}
    counts = dict.fromkeys(signatures, 0)
    for text in texts:
        pieces = [tokenise(s) for s in sentences(text)]
        for signature, needle in signatures.items():
            if any(contains(tokens, needle) for tokens in pieces):
                counts[signature] += 1
    return counts


# ---------------------------------------------------------------------------
# The rulings themselves live in `substitution_verdicts.VERDICTS`, imported
# above. They moved there at OPEN-016 so the generator can consult them at
# generation time instead of the audit merely reporting on them afterwards --
# the difference between describing a defect and preventing it.
# ---------------------------------------------------------------------------


def defective(findings: Iterable[Finding]) -> list[Finding]:
    """Findings a human ruled `broken` or `degraded`."""
    return [f for f in findings if f.verdict in (BROKEN, DEGRADED)]


def defect_rate(findings: Iterable[Finding], texts: Sequence[str]) -> tuple[int, int]:
    """(texts containing at least one defective signature, total texts).

    Record-level, not occurrence-level, and deliberately so. Signatures overlap
    -- "none of it past" and "none of it past that" describe the same broken
    sentence -- so summing occurrence counts would double-charge. What a
    reviewer wants to know is how many records they would have to throw away.
    """
    needles = [tokenise(f.signature) for f in defective(findings)]
    if not needles:
        return 0, len(texts)
    hits = 0
    for text in texts:
        pieces = [tokenise(s) for s in sentences(text)]
        if any(contains(tokens, n) for n in needles for tokens in pieces):
            hits += 1
    return hits, len(texts)
