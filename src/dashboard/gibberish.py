"""The admission gate: is this text something the scorer is entitled to score?

Why a gate exists at all
------------------------
`LexiconBackend` is a keyword matcher. Hand it "asdkjh qwe zzzz" and it matches
nothing, every construct probability comes out 0.0, the fusion layer sums zero
contributions, the logistic squash turns a raw score of 0.0 into an index of
exactly 0.50, and the page reports a psychological score of 50 out of 100 with a
band, a stamp and ten tiles behind it. Every number on that screen is arithmetic
that ran correctly. The screen is still a lie, because 50 reads as "middling"
when the truthful answer is "there was nothing here to read".

That is the same class of defect this repository has found in six phases and
which `view.py` was built to prevent: the check and the thing it protects were
related by assumption. `ScoreSurface` guarantees a number carries its provenance.
It does not, and cannot, guarantee the number had an input worth having. This
module is the missing half, and it sits BEFORE the backend rather than after it,
because a score that exists is a score that can be screenshotted.

What it does and does not judge
-------------------------------
It judges **whether the input is language**, and nothing else. Specifically it
does NOT reject:

* Calm text. "Slept well, plan is clear, looking forward to it" triggers almost
  nothing in the lexicon and is a perfectly legitimate input whose honest answer
  is a low score with few detections. Rejecting it would be the gate deciding
  what an athlete is allowed to feel.
* Text about something other than sport. The taxonomy has no sport detector, and
  a gate that pretended to have one would be asserting a capability the paper
  does not claim.
* Short-but-real sentences, beyond the minimum below.

It rejects text that is not made of words: keyboard mash, symbol soup, a single
token repeated, digits and punctuation with nothing between them.

Pure Python, no ML stack, no network, no model. Every rule is a counted property
of the string with a stated threshold, so a rejection can be explained to the
person who was rejected -- `TextAdmission.detail` is written to be shown, not
logged. Nothing here persists anything.

Thresholds
----------
The numbers below are conservative on purpose: the cost of admitting one junk
string is a nonsense score the caveats already cover, and the cost of rejecting
one real sentence is a user being told their own writing is not writing. So
every threshold is set where a plausible real sentence clears it comfortably,
and they are stated as constants rather than buried in the expressions, so
changing one is a deliberate act with a test beside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Below this many word-shaped tokens there is not enough to read.
MIN_TOKENS = 4

#: Below this many characters likewise. Both apply; "no no no no" fails the
#: repetition rule rather than this one.
MIN_CHARS = 16

#: Share of the string that must be letters or spaces. "£$%^&*()" fails here.
MIN_LETTER_SHARE = 0.55

#: Share of tokens that must look like words (see `_is_word_shaped`).
MIN_WORD_SHAPE_SHARE = 0.60

#: Distinct tokens over total tokens, for texts long enough for the ratio to
#: mean anything. Real prose sits well above this even when repetitive.
MIN_TYPE_TOKEN_RATIO = 0.30
TYPE_TOKEN_MIN_TOKENS = 8

#: A real English sentence of this length essentially always contains at least
#: two distinct function words. This is the single strongest signal that a
#: string is English rather than a plausible-looking non-word sequence.
MIN_FUNCTION_WORDS = 2

#: Closed-class English words. Closed-class on purpose: the set does not grow
#: with topic, so this is a test for "is this English", not "is this about
#: sport" -- which the gate is not entitled to ask.
FUNCTION_WORDS: frozenset[str] = frozenset(
    """
    a an the this that these those my your his her its our their
    i me you he she it we they him them us
    is am are was were be been being
    do does did done have has had having
    will would shall should can could may might must
    and or but so if then than because though although while when where
    as at by for from in into of off on out over to up with without
    about after again against all any before both down during each few more
    most no nor not now once only other own same some such too very just
    there here how what which who whom why
    """.split()
)

#: A token that is a word almost always contains a vowel (or "y" doing the job).
_VOWELS = frozenset("aeiouy")

#: Three or more of the same letter in a row: "aaargh" is real, "aaaaaa" is not.
#: Set at four so the genuine three-letter emphatic forms survive.
_RUN = re.compile(r"(.)\1{3,}")

_TOKEN = re.compile(r"[a-z']+")
_ANY_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class TextAdmission:
    """Whether a string may be scored, and what to say if it may not.

    `detail` is user-facing and is the only thing the page shows. It names the
    property that failed in plain words, because "invalid input" teaches the
    person nothing and invites them to paste the same thing again.
    """

    admitted: bool
    reason: str
    detail: str

    def __bool__(self) -> bool:
        return self.admitted


def _is_word_shaped(token: str) -> bool:
    """A loose test for "this could be an English word".

    Deliberately loose. It passes anything with a vowel, a sane length and no
    long character run, which includes plenty of non-words -- that is fine,
    because it is one input to a share, not a verdict on a single token. A tight
    per-token test would reject names, loanwords and typos, all of which are
    things real athletes write.
    """
    if not (1 <= len(token) <= 20):
        return False
    if _RUN.search(token):
        return False
    return any(character in _VOWELS for character in token)


def admit(text: str) -> TextAdmission:
    """Decide whether `text` is language, and may therefore be scored.

    Returns an admitted result for anything that reads as English prose, and a
    refused one, carrying a plain-English reason, for anything that does not.
    The rules run in order from cheapest and most obvious to most inferential,
    so the reason a user sees is the most concrete one that applies.
    """
    stripped = text.strip()
    if not stripped:
        return TextAdmission(
            False,
            "empty",
            "There is nothing here to read. Type or paste a few sentences an athlete "
            "wrote before a competition.",
        )

    lowered = stripped.lower()
    all_tokens = _ANY_TOKEN.findall(lowered)
    letter_tokens = _TOKEN.findall(lowered)

    letters = sum(1 for character in stripped if character.isalpha() or character.isspace())
    if letters / len(stripped) < MIN_LETTER_SHARE:
        return TextAdmission(
            False,
            "not_letters",
            "This is mostly symbols, punctuation or digits rather than words. Enter a "
            "few sentences in ordinary English and it will be scored.",
        )

    if len(letter_tokens) < MIN_TOKENS or len(stripped) < MIN_CHARS:
        return TextAdmission(
            False,
            "too_short",
            f"That is too short to read anything from. Enter at least {MIN_TOKENS} "
            "words, ideally a sentence or two.",
        )

    word_shaped = sum(1 for token in letter_tokens if _is_word_shaped(token))
    if word_shaped / len(letter_tokens) < MIN_WORD_SHAPE_SHARE:
        return TextAdmission(
            False,
            "not_words",
            "Most of this does not look like words. Enter something an athlete "
            "actually wrote or said, in ordinary English.",
        )

    if len(all_tokens) >= TYPE_TOKEN_MIN_TOKENS:
        ratio = len(set(all_tokens)) / len(all_tokens)
        if ratio < MIN_TYPE_TOKEN_RATIO:
            return TextAdmission(
                False,
                "repetition",
                "This is the same few words repeated. Enter a sentence or two of real "
                "writing and it will be scored.",
            )

    found = {token for token in letter_tokens if token in FUNCTION_WORDS}
    if len(found) < MIN_FUNCTION_WORDS:
        return TextAdmission(
            False,
            "not_english",
            "This does not read as English prose. The scorer only reads English, and "
            "it needs whole sentences rather than isolated words.",
        )

    return TextAdmission(True, "ok", "")
