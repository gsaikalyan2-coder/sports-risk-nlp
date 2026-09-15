"""Is the recovered text pre-competition athlete self-report, or something else?

The question this module is allowed to ask
-------------------------------------------
The owner's requirement is that the media path ignore irrelevant uploads, where
relevant means an athlete's own writing or an athlete speaking in an interview or
press conference. There are two ways to build that and only one of them is
honest here.

**The rejected way: classify the picture.** "This photograph contains an
athlete" is a trained visual classifier. Shipping one needs a labelled image set,
a held-out split and a reported number, and this repository has an empty
`data/gold/` and an open OPEN-011. A gate whose error rate nobody knows, on the
page whose whole design is about not asserting unmeasured things, would be the
single most reviewer-visible contradiction in the project. Reaching for a
pretrained off-the-shelf model would be worse: it would put a second
unaccounted-for model in the paper.

**The way taken: judge the words.** A photo of an athlete's journal page and a
clip of a press conference are both distinguished from a car-park sign, a recipe
or a news bulletin by the *register of the recovered text* -- first-person, about
the speaker's own situation and state, oriented at something upcoming. That is a
property of words, it is explainable line by line, and, critically, it is
measurable: `data/processed/gold_candidates/` is exactly this register, so the
gate can be fitted on the dev split and reported on the eval split instead of
being asserted.

Scored, not refused
--------------------
This gate does NOT stop the page. `gibberish.admit` refuses, because text that is
not language has no meaningful score at all. Off-register text is different: it
is real language, the scorer will process it correctly, and the number it gets is
arithmetically what that text deserves -- it just is not a reading of an athlete.
So the owner's decision is that the page scores it and says loudly what it is.
`RelevanceVerdict.on_topic` is a flag the page renders, never a gate it obeys.

Honest limitations, all three of which belong in the paper
-----------------------------------------------------------
1. **The negative set is authored.** `NEGATIVES` in `tests/test_relevance.py`
   was written for this test by the project. The reported false-positive rate is
   therefore a sanity check against plausible off-topic text, not an estimate of
   performance against whatever a user actually uploads.
2. **The positives are synthetic.** Same OPEN-011 that governs everything else:
   the register being matched is the register this project's own generator
   writes, which is a hypothesis about how athletes talk, not an observation.
3. **`STATE_WORDS` overlaps the construct lexicon.** Some words that raise the
   relevance score also raise construct probabilities. So relevance and detected
   signal are not independent, and a text can look on-topic partly because it is
   strained. The overlap is declared rather than engineered away, because
   removing every shared word would leave a register test that cannot see the
   thing the register is about.

Weights and threshold
----------------------
Chosen on the dev split, reported on the eval split, both stated in
`tests/test_relevance.py`. Round numbers on purpose: a threshold of 0.2537 found
by grid search over the split it is then reported on is a fit dressed as a
finding, and this project has a whole module (`src/risk/fusion.py`) arguing for
declared weights over fitted ones for exactly that reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Weight on the first-person rate. The dominant term by a wide margin: on the
#: dev split 80% of athlete utterances contain a first-person pronoun against 5%
#: of the authored negatives. It is a rate rather than a count so that a long
#: passage does not out-score a short one by sheer length.
W_FIRST_PERSON = 5.0

#: Weight on sport and competition vocabulary. Small, deliberately. A large
#: weight here would turn the gate into a topic detector that passes a match
#: report and fails an athlete writing about their sleep -- and the second is far
#: more of what this page is for than the first.
W_SPORT = 0.25

#: Weight on self-state vocabulary. See limitation 3 above.
W_STATE = 0.30

#: Penalties for the shape of signage and boilerplate: shouting and numbers.
#: "P 24 HOURS PAY AND DISPLAY" is caught here rather than by any word list.
W_CAPS = 1.0
W_DIGITS = 4.0

#: At or above this, the text reads as athlete self-report.
ON_TOPIC_THRESHOLD = 0.25

#: How many distinct hits saturate a vocabulary term. Three, so that one lucky
#: word cannot carry a text and a word-stuffed one cannot run away with it.
SATURATION = 3

FIRST_PERSON: frozenset[str] = frozenset("i me my mine myself we us our ours ourselves".split())

SPORT_WORDS: frozenset[str] = frozenset(
    """
    game games race races match matches final finals coach coaching training train
    trains trained session sessions team teams competition competing compete fight
    tournament physio squad lineup line-up warm-up warmup heat heats meet bout
    kick-off opponent opponents selection selected medal season gym pitch court
    track field athlete athletes sport sports play playing played win winning won
    lose losing lost score scoring start starts starting event tomorrow tonight
    weekend saturday sunday week
    """.split()
)

STATE_WORDS: frozenset[str] = frozenset(
    """
    feel feels feeling felt nervous nerves ready confident confidence worried worry
    worrying sleep sleeping slept think thinking thought know knowing want wanting
    hope hoping calm tired tiredness head mind focus focused focusing pressure
    stress stressed scared afraid fear anxious excited prepared honestly honest
    truth believe sure unsure doubt doubts
    """.split()
)

_WORD = re.compile(r"[a-z'\-]+")
_ALPHA = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class RelevanceVerdict:
    """How much the text reads as an athlete talking about their own situation.

    `on_topic` is advisory. Nothing in this package refuses an upload on the
    strength of it; the page shows the warning and scores the text anyway. See
    this module's docstring.
    """

    score: float
    on_topic: bool
    first_person: float
    sport_hits: int
    state_hits: int
    detail: str = ""

    def __bool__(self) -> bool:
        return self.on_topic


def judge(text: str) -> RelevanceVerdict:
    """Score `text` for pre-competition athlete self-report register.

    Every term is a counted property of the string with a declared weight, so a
    verdict can be explained to the person it was given about -- which matters
    more here than in most gates, because the message it produces amounts to
    telling someone their upload is not what they think it is.
    """
    tokens = _WORD.findall(text.lower())
    if not tokens:
        return RelevanceVerdict(0.0, False, 0.0, 0, 0, "There are no words here to judge.")

    words = _ALPHA.findall(text)
    first_person = sum(1 for token in tokens if token in FIRST_PERSON) / len(tokens)
    sport_hits = len({token for token in tokens if token in SPORT_WORDS})
    state_hits = len({token for token in tokens if token in STATE_WORDS})
    shouting = sum(1 for word in words if word.isupper() and len(word) > 1) / max(len(words), 1)
    numeric = sum(1 for character in text if character.isdigit()) / max(len(text), 1)

    score = (
        W_FIRST_PERSON * first_person
        + W_SPORT * (min(sport_hits, SATURATION) / SATURATION)
        + W_STATE * (min(state_hits, SATURATION) / SATURATION)
        - W_CAPS * shouting
        - W_DIGITS * numeric
    )
    score = max(0.0, min(1.0, score))
    on_topic = score >= ON_TOPIC_THRESHOLD

    if on_topic:
        detail = ""
    elif first_person == 0.0:
        detail = (
            "Nobody is talking about themselves here: the text contains no first-person "
            "words at all. It reads as description, signage or reportage rather than as "
            "an athlete's own account."
        )
    elif shouting > 0.3 or numeric > 0.1:
        detail = (
            "This reads as a sign, a label or a listing rather than as writing: it is "
            "mostly capitals and numbers."
        )
    else:
        detail = (
            "This does not read as an athlete writing or speaking about their own "
            "situation before a competition. It was scored anyway, and the score below "
            "is what the word-list scorer makes of these words, not a reading of an "
            "athlete."
        )
    return RelevanceVerdict(
        score=score,
        on_topic=on_topic,
        first_person=first_person,
        sport_hits=sport_hits,
        state_hits=state_hits,
        detail=detail,
    )
