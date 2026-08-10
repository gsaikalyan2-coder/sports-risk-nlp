"""Human rulings on what the near-synonym layer is allowed to produce.

Why this is a module of its own
--------------------------------
Phase 9's sweep (`synonym_audit.py`) enumerated every single-token substitution
the generator can make and had a human rule on each flagged frame. That table
was an **audit** artefact: it described defects after the fact.

OPEN-016 resolved it by making the same table a **generation-time guard**. So
the table is now imported by two modules that must not import each other:

    synthetic.py  ->  substitution_verdicts.py  <-  synonym_audit.py

`synonym_audit` imports `synthetic` (it enumerates the template bank), so
`synthetic` cannot import `synonym_audit` back. Extracting the shared table and
its tokeniser into a third module is the only arrangement that lets the
generator consult the verdicts without a circular import, and it has the useful
side effect of making the boundary explicit: **this file is data plus three
pure functions, and it depends on nothing in the project.**

Why a guard rather than deleting the offending synonym groups
---------------------------------------------------------------
`docs/open_issues.md` OPEN-016 lists four options. Deleting the 34 implicated
group members was the obvious one and it is the wrong one: those members are
part of what raised the corpus vocabulary from 444 to 643 types, which is the
entire evidence that OPEN-012 is "substantially mitigated". Deleting them fixes
grammaticality by partly undoing the diversity fix.

`think -> figure` is broken in *"all I figure about"* and unremarkable in *"I
figure I'm ready"*: the defect is a property of the **frame**, not of the word.
A context-blind bank can only accept or reject the word. A guard rejects the
frame, so *figure* stays in the corpus everywhere it is fine.

**The measured cost, both ways, at n=4,000 and seed 42** -- because "the guard
is cheaper" is a claim and claims get measured here:

| | Synonym bank | Realised vocabulary | Defective records |
|---|---|---|---|
| v1.2, unguarded | 64 groups | 643 types | 630 (15.75%) |
| Option (a): delete the 34 implicated members | 57 groups | **594** types | 0 |
| **Option (c): guard (chosen)** | **64 groups, unchanged** | **625** types | **0** |

Both options eliminate the defects. Deleting costs **49 types**; the guard costs
**18**. The guard is not free -- a word whose only frames in the bank were
defective now never appears -- but it keeps 31 more types than deletion and it
removes nothing from the bank, so a later template that uses one of those words
in a good frame gets the word back automatically. Deletion would not.

The honest cost, stated because a reviewer will ask
-----------------------------------------------------
The guard is only as good as the verdict table, and the table is hand-ruled. It
cannot catch a defect class nobody has thought of. What it *can* do -- and this
is the part worth defending -- is make the failure mode **non-recurring**: the
sweep enumerates exhaustively, the ratchet fails the build on an unruled
signature, and the guard prevents anything ruled bad from ever being generated.
A new defect class still requires a human to notice it once. It no longer
requires a human to notice it repeatedly.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

BROKEN = "broken"
DEGRADED = "degraded"
ACCEPTABLE = "acceptable"

#: Punctuation stripped from the edges of a token before matching. Internal
#: apostrophes and hyphens are kept: "won't" and "lead-in" are single tokens.
_EDGE_PUNCT = ".,!?;:—\"'()"


def tokenise(text: str) -> list[str]:
    """Lowercase whitespace tokens with edge punctuation removed.

    Used for the template bank, the corpus, and the generation-time guard, so a
    signature computed from a template matches the same sequence in a rendered
    utterance. One tokeniser, three callers -- two tokenisers would eventually
    disagree about `"won't"` and the guard would let a defect through.
    """
    return [t for t in (w.strip(_EDGE_PUNCT).lower() for w in text.split()) if t]


def sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation.

    A signature must not be allowed to match across a full stop. Without this,
    "I'm just hollowed out. I don't even care" yields the spurious bigram
    "hollowed out i", and both the audit and the guard would react to a defect
    that is only an artefact of throwing punctuation away.
    """
    out: list[str] = []
    current: list[str] = []
    for word in text.split():
        current.append(word)
        if word.rstrip("\"')").endswith((".", "!", "?")):
            out.append(" ".join(current))
            current = []
    if current:
        out.append(" ".join(current))
    return out


def contains(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """True when `needle` appears as a contiguous run inside `haystack`."""
    n = len(needle)
    if not n or n > len(haystack):
        return False
    return any(tuple(haystack[i : i + n]) == tuple(needle) for i in range(len(haystack) - n + 1))


# ---------------------------------------------------------------------------
# VERDICTS -- the human rulings, made at Phase 9 (2026-08-09) against the
# rendered frame shown by `synonym_audit.Finding.event.window()`.
#
# "broken"     : produces text no competent English speaker would write.
# "degraded"   : grammatical but changes meaning, register, or plausibility.
# "acceptable" : the probe fired, a human read it, it is fine.
#
# Only "broken" and "degraded" are defects. "acceptable" entries are kept rather
# than deleted, because a deleted verdict is indistinguishable from an unreviewed
# one and the ratchet would stop working.
# ---------------------------------------------------------------------------

VERDICTS: dict[str, str] = {
    # -- broken: indefinite-article agreement ------------------------------
    "a approach": BROKEN,
    "a event": BROKEN,
    "a obligation": BROKEN,
    "a ugly": BROKEN,
    "an chance": BROKEN,
    "an shot": BROKEN,
    # -- broken: wrong inflected form for the frame ------------------------
    "can composed": BROKEN,  # "I can composed myself"; steady is a verb here
    "can settled": BROKEN,
    "stop unsteady": BROKEN,  # "stop" selects a gerund
    # -- broken: idiom destroyed -------------------------------------------
    "a shut-eye day": BROKEN,  # "a rest day" is a compound noun
    "a sleep day": BROKEN,
    "all i figure about": BROKEN,  # "all I think about"
    "all i reckon about": BROKEN,
    "all i suppose about": BROKEN,
    # "start line" arrives through the {EVENT}/{START} slots, so these three
    # are only reachable for the sports whose start is a line.
    "beginning line": BROKEN,
    "opening line": BROKEN,
    "outset line": BROKEN,
    "half off the rails": BROKEN,  # the frame is "get X wrong"
    "like to figure": BROKEN,  # "I'd like to think"
    "like to reckon": BROKEN,
    "like to suppose": BROKEN,
    "out of my fingers": BROKEN,  # "out of my hands" = beyond my control
    "the first half awry": BROKEN,
    "the first half badly": BROKEN,
    "the first half off the rails": BROKEN,
    "the reason of the session": BROKEN,  # "reason for", not "reason of"
    "the shut-eye of the day": BROKEN,  # rest = remainder, not repose
    "the sleep of the day": BROKEN,
    # -- broken: number agreement ------------------------------------------
    "all of them else": BROKEN,
    "all of them seems": BROKEN,
    "grip were": BROKEN,
    "insides has": BROKEN,
    "insides is": BROKEN,
    "second thoughts in": BROKEN,  # "a bit of second thoughts"
    "that spectators": BROKEN,
    "that stands": BROKEN,
    # -- broken: argument structure ----------------------------------------
    "figure about": BROKEN,
    "none of it has": BROKEN,
    "none of it i": BROKEN,
    "none of it i'm": BROKEN,
    "none of it past": BROKEN,
    "none of it past that": BROKEN,
    "none of it that": BROKEN,
    "on edge i'll": BROKEN,  # "on edge" takes no clausal complement
    "reason of": BROKEN,
    "reckon about": BROKEN,
    "shut-eye at": BROKEN,  # "I couldn't shut-eye at all"
    "shut-eye of": BROKEN,
    "sleep of": BROKEN,
    "squared away enough": BROKEN,  # "done enough"
    "suppose about": BROKEN,
    # -- degraded: grammatical, but the sense or register moved ------------
    "entry list is": DEGRADED,  # a field is a set of rivals, a list is paper
    "misgiving about": DEGRADED,  # the frame wants the plural
    "not a thing past": DEGRADED,
    "not a thing past that": DEGRADED,
    "out of my grip": DEGRADED,  # "slipping away", not "beyond my control"
    "this entry list": DEGRADED,
    # -- acceptable: the probe fired, a human read it, it is fine ----------
    "aim to": ACCEPTABLE,
    "all of them down": ACCEPTABLE,
    "all of them will": ACCEPTABLE,
    "approach for": ACCEPTABLE,
    "approach in": ACCEPTABLE,
    "beginning of": ACCEPTABLE,
    "breath control routine": ACCEPTABLE,
    "chat about": ACCEPTABLE,
    "comfortably cope with": ACCEPTABLE,
    "comfortably deal with": ACCEPTABLE,
    "contest at": ACCEPTABLE,
    "contest on": ACCEPTABLE,
    "cope with this": ACCEPTABLE,
    "deal with this": ACCEPTABLE,
    "demanding to": ACCEPTABLE,
    "difficult to": ACCEPTABLE,
    "drained in": ACCEPTABLE,
    "entry list before": ACCEPTABLE,
    "entry list earlier": ACCEPTABLE,
    "entry list i've": ACCEPTABLE,
    "entry list this": ACCEPTABLE,
    "event at": ACCEPTABLE,
    "event on": ACCEPTABLE,
    "everybody down": ACCEPTABLE,
    "fatigued in": ACCEPTABLE,
    "fearful of": ACCEPTABLE,
    "frightened of": ACCEPTABLE,
    "hesitation about": ACCEPTABLE,
    "hesitation in": ACCEPTABLE,
    "intend to": ACCEPTABLE,
    "just hollowed out": ACCEPTABLE,
    "just wrung out": ACCEPTABLE,
    "mean to": ACCEPTABLE,
    "misgiving in": ACCEPTABLE,
    "my cue card": ACCEPTABLE,
    "not a thing has": ACCEPTABLE,
    "not a thing i": ACCEPTABLE,
    "not a thing i'm": ACCEPTABLE,
    "not a thing that": ACCEPTABLE,
    "off the rails and": ACCEPTABLE,
    "off the rails i'd": ACCEPTABLE,
    "on a decent day": ACCEPTABLE,
    "on a solid day": ACCEPTABLE,
    "on a strong day": ACCEPTABLE,
    "opening of": ACCEPTABLE,
    "outset of": ACCEPTABLE,
    "prepared for": ACCEPTABLE,
    "primed for": ACCEPTABLE,
    "process for": ACCEPTABLE,
    "process in": ACCEPTABLE,
    "punishing to": ACCEPTABLE,
    "purpose of": ACCEPTABLE,
    "rest at": ACCEPTABLE,
    "scared of": ACCEPTABLE,
    "second thoughts about": ACCEPTABLE,
    "set for": ACCEPTABLE,
    "speak about": ACCEPTABLE,
    "spent in": ACCEPTABLE,
    "squared away the": ACCEPTABLE,
    "team announcement and": ACCEPTABLE,
    "the entry list": ACCEPTABLE,
    "the purpose of the session": ACCEPTABLE,
    "the squad call and": ACCEPTABLE,
    "thing squared away": ACCEPTABLE,
    "tough to": ACCEPTABLE,
    "weary in": ACCEPTABLE,
    # -----------------------------------------------------------------
    # Ruled at Phase 9b (2026-08-10), against the frames created by the
    # expanded template bank (OPEN-020). 28 new signatures, all surfaced by
    # the ratchet rather than by reading -- which is the control working: the
    # build refused to pass until a human had looked at each one.
    # -----------------------------------------------------------------
    # -- broken: number agreement --------------------------------------
    "all of them is": BROKEN,  # "everyone is going to see it"
    "spectators keeps": BROKEN,  # "the crowd keeps taking my attention"
    "stands keeps": BROKEN,
    # -- broken: indefinite article ------------------------------------
    "a entry list": BROKEN,  # "a field this strong"
    # -- broken: argument structure / arity ----------------------------
    "candid back": BROKEN,  # "pulls me straight back out"
    "crowded with": BROKEN,  # "I keep myself busy with"
    "hectic with": BROKEN,
    "honest back": BROKEN,
    "none of it beyond": BROKEN,  # "nothing beyond it"
    "none of it else": BROKEN,
    "none of it left": BROKEN,  # "nothing left to give"
    "not a thing beyond": BROKEN,
    "not a thing else": BROKEN,
    "not a thing serious": BROKEN,
    "off the rails wrong": BROKEN,
    "relentless with": BROKEN,
    "squared away out": BROKEN,  # "accreditation was sorted out"
    "squared away this": BROKEN,  # "I have handled this level before"
    "truthful back": BROKEN,
    # -- degraded: grammatical, sense or register moved ----------------
    "badly off the rails": DEGRADED,  # doubles the adverbial
    "breath control quicken": DEGRADED,  # breathing quickens; breath control is a skill
    "none of it serious": DEGRADED,  # the head noun ("things") is plural
    "not a thing left": DEGRADED,  # archaic register for an athlete interview
    "went off the rails": DEGRADED,  # fine for a race, odd for a start line
    # -- acceptable: the probe fired, a human read it, it is fine ------
    "all of them over": ACCEPTABLE,  # "the physio checked all of them over"
    "cope with it": ACCEPTABLE,
    "deal with it": ACCEPTABLE,
    "everybody over": ACCEPTABLE,
}

#: Defects from a bank the generator no longer has.
#:
#: These three are OPEN-015: the `(part, portion, corner, piece)` group was
#: deleted at v1.2, so no probe can produce them any more. They are kept as
#: **guard** entries so that reinstating the group -- or writing a new one that
#: happens to reach the same frame -- cannot silently bring the defect back.
#:
#: They live here and not in `VERDICTS` because the two tables answer different
#: questions, and conflating them broke a real test.
#: `test_no_orphan_verdicts` asserts that every `VERDICTS` entry is a frame the
#: audit can still produce -- a stale ruling is dead weight the ratchet cannot
#: validate. That invariant is correct and worth keeping. A *guard* entry is
#: deliberately for a frame nothing currently produces, which is the exact
#: opposite property. Two purposes, two tables.
RETIRED_DEFECTS: tuple[str, ...] = (
    "corner of me",
    "piece of me",
    "portion of me",
)

#: Token sequences the generator must never emit.
DEFECTIVE_SIGNATURES: tuple[tuple[str, ...], ...] = tuple(
    sorted(
        {
            tuple(tokenise(signature))
            for signature, verdict in VERDICTS.items()
            if verdict in (BROKEN, DEGRADED)
        }
        | {tuple(tokenise(signature)) for signature in RETIRED_DEFECTS}
    )
)

#: first token -> the defective signatures beginning with it.
#:
#: An index, not a loop over all 59 signatures per position. `_vary` runs once
#: per sentence per record, and at 4,000 records the difference between an
#: indexed check and a linear one is the difference between a generator that
#: regenerates in seconds and one that regenerates in minutes -- which decides
#: whether a reviewer actually reruns it.
_BY_FIRST_TOKEN: dict[str, list[tuple[str, ...]]] = defaultdict(list)
for _signature in DEFECTIVE_SIGNATURES:
    _BY_FIRST_TOKEN[_signature[0]].append(_signature)


def is_defective(text: str) -> bool:
    """True if `text` contains any ruled-defective token sequence.

    Sentence-bounded: a signature may not match across a full stop.
    """
    for sentence in sentences(text):
        tokens = tokenise(sentence)
        for index, token in enumerate(tokens):
            for signature in _BY_FIRST_TOKEN.get(token, ()):
                end = index + len(signature)
                if end <= len(tokens) and tuple(tokens[index:end]) == signature:
                    return True
    return False


def defective_signatures_in(text: str) -> list[str]:
    """Every defective signature present, as space-joined strings. For reports."""
    found: list[str] = []
    for sentence in sentences(text):
        tokens = tokenise(sentence)
        for index, token in enumerate(tokens):
            for signature in _BY_FIRST_TOKEN.get(token, ()):
                end = index + len(signature)
                if end <= len(tokens) and tuple(tokens[index:end]) == signature:
                    found.append(" ".join(signature))
    return sorted(set(found))
