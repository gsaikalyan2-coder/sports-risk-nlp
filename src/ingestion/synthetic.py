"""Category A2 -- construct-grounded synthetic pre-competition text.

Why this exists, stated plainly so the paper can repeat it
----------------------------------------------------------
The Phase 7 source survey (2026-08-09, recorded in `docs/data_sources.md`)
found no public corpus of *pre-competition* athlete text. Every athlete-speech
corpus located is **post-match**, which is the wrong side of the event for this
project: `appraisal_orientation` and anticipatory `cognitive_anxiety` are
constructs about an outcome that has not happened yet, and post-match speech
expresses relief, disappointment, and attribution instead.

`CLAUDE.md` sec.10 Q3 pre-authorised exactly this fallback -- "hybrid
synthetic-for-training + small real gold set" -- and told us to revisit it at
Phase 7. The owner confirmed synthetic-first on 2026-08-09.

How it is generated, and why not with an LLM (yet)
-------------------------------------------------
A seeded template grammar, not a language model. Three reasons:

1. **Reproducibility.** `CLAUDE.md` sec.9 makes a reproducible artifact part of
   "publication-ready". A reviewer regenerating this corpus with the same seed
   gets byte-identical text, with no API key and no cost. An LLM pass would not.
2. **OPEN-008.** There is no `OPENROUTER_API_KEY` in `.env`, so an LLM path
   could not have been executed or verified this session, and shipping an
   unexecuted generator would repeat the OPEN-007 mistake.
3. **Honesty about what it is.** A template grammar cannot pretend to be
   naturalistic athlete speech. That is a feature: it makes the limitation
   visible in the artefact rather than hidden behind fluent prose.

What this corpus is NOT
-----------------------
It is a **scaffold**, not the final training corpus. Lexical diversity is bounded
by the template bank below. `docs/data_sources.md` states the measured
type-token statistics rather than claiming diversity it does not have. An LLM
paraphrase pass to raise diversity is the recommended Phase 8/10 follow-on, and
`GeneratorStamp` records which generator produced which records so the two are
never confused.

**Circularity warning.** Each record carries a `generation_spec` naming the
constructs the generator planted. That is generation metadata, not a label. Using
it as evaluation ground truth would measure whether a model can recover this
file's template choices -- a circular result telling us nothing about athlete
language. Evaluation rests on the Phase 11 human gold set.

**No names.** Synthetic text uses role references ("my coach", "the girl in the
next lane") and never personal names, real or invented. Invented names risk
colliding with real people, and this corpus needs no identifiers. The
consequence, recorded honestly in `docs/data_sources.md`: the Phase 8
de-identifier has little to bite on in the synthetic portion, so its recall must
be validated against real text, not here.
"""

from __future__ import annotations

import datetime as _dt
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .allowlist import SourceDescriptor
from .provenance import GeneratorStamp
from .records import RawRecord
from .substitution_verdicts import is_defective

GENERATOR_NAME = "construct-template-grammar"

#: Version history, because the corpus is a dataset contribution and a reviewer
#: has to be able to tell which generator produced which numbers.
#:
#:   1.0  Phase 7. Template grammar only.
#:   1.1  Phase 7 follow-up. Lexical-variation layer (OPEN-012 mitigation).
#:        **The constant was never bumped**, so every artefact from that run is
#:        stamped `@1.0` while the docs call it v1.1. Recorded here rather than
#:        silently corrected: `data/raw/.../provenance.json` in commit 6f9561a
#:        says 1.0 and means 1.1.
#:   1.2  Phase 9. `("part", "portion", "corner", "piece")` removed (OPEN-015).
#:   1.3  Phase 9 follow-up. `_vary` is now GUARDED (OPEN-016): a substitution
#:        that would produce a ruled-defective token sequence is reverted. Zero
#:        synonym groups were deleted; realised vocabulary 643 -> 625 at n=4,000,
#:        against 594 had the implicated members been deleted instead, so
#:        OPEN-012's mitigation still stands. Default corpus size raised from
#:        1,200 to 4,000 records (OPEN-017): 4,000 is the measured minimum at
#:        which a 400-item gold set meets the 40-positive floor for all ten
#:        constructs.
#:   1.4  Phase 9b. Template bank doubled: **15 realisations per construct**
#:        (was 7-12), five per intensity level and five per categorical label
#:        (OPEN-020). Discourse suffixes 8 -> 17, neutral sentences 8 -> 16, and
#:        `_vary` now reaches the discourse frame, the interpretation modifier
#:        and the construct-free records -- all three previously bypassed it,
#:        which is why 87.4% of v1.3 utterances were exact duplicates
#:        (OPEN-018).
#:
#: A version bump changes the corpus. It also changes the RNG stream, because
#: `_vary` consumes randomness per matched token -- so removing one group moves
#: every downstream draw, not just the sentences that group touched. That is why
#: OPEN-015's fix required re-running the Phase 7, Phase 8 and benchmark gates
#: together instead of patching 21 records.
GENERATOR_VERSION = "1.4"

# ---------------------------------------------------------------------------
# Strata. Deliberately coarse: docs/ethics.md sec.5.2 warns that a precise
# combination of sport, level, and event re-identifies as surely as a name.
# Coarse strata are also what the paper can honestly report performance across.
# ---------------------------------------------------------------------------

SPORTS: tuple[str, ...] = (
    "athletics",
    "swimming",
    "tennis",
    "football",
    "basketball",
    "cricket",
    "badminton",
    "boxing",
    "rowing",
    "gymnastics",
)

#: Sport -> the noun an athlete in that sport uses for the contest itself, and
#: for the moment it begins. Slot-filled into the realisations below so the same
#: construct template reads naturally across sports.
SPORT_TERMS: dict[str, tuple[str, str]] = {
    "athletics": ("race", "start line"),
    "swimming": ("race", "blocks"),
    "tennis": ("match", "first serve"),
    "football": ("game", "kick-off"),
    "basketball": ("game", "tip-off"),
    "cricket": ("match", "first ball"),
    "badminton": ("match", "first serve"),
    "boxing": ("fight", "first bell"),
    "rowing": ("race", "start"),
    "gymnastics": ("competition", "first rotation"),
}

COMPETITION_LEVELS: tuple[str, ...] = ("club", "regional", "national", "international", "elite")
REGIONS: tuple[str, ...] = ("south_asia", "europe", "north_america", "oceania", "africa")
SOURCE_TYPES: tuple[str, ...] = ("interview", "presser", "journal", "social")

#: Days before the competition. Weighted toward the final week, because that is
#: where pre-competition anxiety literature concentrates and where the risk index
#: is intended to be used.
TIME_TO_COMPETITION_DAYS: tuple[int, ...] = (0, 0, 1, 1, 1, 2, 2, 3, 3, 5, 7, 10, 14, 21, 30)

TRAINING_LOAD_HINTS: tuple[str | None, ...] = (
    "tapering",
    "heavy block just finished",
    "light week",
    "back-to-back competitions",
    "returning from a rest week",
    None,
    None,
    None,
)

# ---------------------------------------------------------------------------
# Realisation bank.
#
# Every entry is grounded in `config/taxonomy.yaml`: the graded constructs are
# keyed by intensity 1-3 as defined by `intensity_scale`, and the categorical
# constructs are keyed by the exact label strings that taxonomy.yaml declares.
# Intensity 0 and the `none` label are represented by ABSENCE -- the construct
# simply is not planted -- which matches the annotation rule "when in doubt,
# label 0".
#
# Slots: {EVENT} the contest noun, {START} the starting moment.
# ---------------------------------------------------------------------------

GRADED_REALISATIONS: dict[str, dict[int, tuple[str, ...]]] = {
    "cognitive_anxiety": {
        1: (
            "There's a small part of me wondering how the {EVENT} will go.",
            "I've caught myself thinking about the result once or twice.",
            "I suppose there's a bit of doubt in the back of my mind.",
            "Every so often I wonder whether I've done enough.",
            "It crosses my mind now and then, but it passes quickly enough.",
        ),
        2: (
            "I keep turning over what happens if I get the first half wrong.",
            "I'm worried I'll let everyone down in this {EVENT}.",
            "I've been replaying last season's {EVENT} more than I should.",
            "The thought of coming up short has been sitting with me all week.",
            "I've been running through the bad version of this in my head.",
        ),
        3: (
            "I cannot stop thinking about all the ways this could fall apart.",
            "Every time I close my eyes I see myself failing at the {START}.",
            "I've convinced myself it's going to go wrong and I can't shift it.",
            "It's all I think about now — losing, and what everyone will say.",
            "I have already lost this in my head a hundred times this week.",
        ),
    },
    "somatic_anxiety": {
        1: (
            "There are a few butterflies, nothing I'm not used to.",
            "I can feel my heart pick up a bit when I think about the {START}.",
            "Slept a little lighter than usual last night.",
            "There is a flutter in my chest when the {EVENT} comes up in conversation.",
            "I noticed my breathing quicken while I was warming up yesterday.",
        ),
        2: (
            "My stomach has been unsettled since yesterday morning.",
            "My hands were shaking when I was packing my kit.",
            "I've barely slept properly for two nights and my chest feels tight.",
            "My shoulders have been tight since the team meeting.",
            "I woke at four and could not get back down again.",
        ),
        3: (
            "My stomach is in knots and my hands won't stop shaking.",
            "I couldn't sleep at all — heart going the whole night.",
            "I felt sick this morning and my legs have gone completely heavy.",
            "My whole body feels wired and I cannot switch it off.",
            "I was shaking so much this morning I could barely tie my laces.",
        ),
    },
    "self_confidence": {
        1: (
            "I think I can be competitive if things fall right.",
            "On a good day I belong in this field.",
            "I've done the work, so there's some belief there.",
            "I would give myself a fair chance if I get things right.",
            "There is enough there to make a decent account of it.",
        ),
        2: (
            "I back myself to execute the plan in this {EVENT}.",
            "I've beaten most of this field before and nothing has changed.",
            "I know what I'm capable of when it matters.",
            "I trust my preparation for this {EVENT} completely.",
            "I have handled this level before and I expect to handle it again.",
        ),
        3: (
            "I know I win this if I stick to my own {EVENT}.",
            "There is nobody here I'm afraid of. I've earned this.",
            "I have absolutely no doubt about what I'm going to do at the {START}.",
            "I expect to win this and I have expected it for weeks.",
            "I am the best prepared I have ever been going into a {EVENT}.",
        ),
    },
    "perceived_stress": {
        1: (
            "It's been a slightly busier week than I'd like.",
            "There's a bit more going on around this {EVENT} than usual.",
            "There is a little more noise around me than I would choose.",
            "The week has been fuller than I planned for.",
            "A few small things have piled up, nothing serious.",
        ),
        2: (
            "There's just a lot on right now — exams, selection, and now this {EVENT}.",
            "Everyone seems to want something from me this week.",
            "The schedule has been more than I can comfortably manage.",
            "Between travel and the {EVENT} I have not had a clear day in a fortnight.",
            "There have been too many demands on me to prepare the way I wanted.",
        ),
        3: (
            "It feels like it's all completely out of my hands.",
            "I'm being pulled in every direction and I cannot keep up with any of it.",
            "There is far too much on me right now and no way to put any of it down.",
            "Every day this week has been one more thing I could not say no to.",
            "I am running on empty and the demands have not stopped coming.",
        ),
    },
    "burnout_signal": {
        1: (
            "I'm a bit flat this week, if I'm honest.",
            "The enthusiasm isn't quite what it was at the start of the season.",
            "The spark is not quite there this block.",
            "I am going through the motions a bit more than I would like.",
            "It feels more like a duty than a choice this week.",
        ),
        2: (
            "I'm tired in a way that a rest day doesn't seem to fix.",
            "I'm finding it hard to care about this {EVENT} the way I should.",
            "Some mornings I struggle to see the point of the session.",
            "I have stopped looking forward to the {EVENT} the way I once did.",
            "The tiredness has been sitting on me for weeks, not days.",
        ),
        3: (
            "I'm just drained. I don't even care how this one goes anymore.",
            "I used to love this. Now it's a job I want to finish.",
            "Nothing I do seems to make the slightest difference these days.",
            "I have nothing left to give this and I have known it a while.",
            "Whether I compete or not stopped mattering to me some time ago.",
        ),
    },
    "resilience": {
        1: (
            "If something goes wrong I'd like to think I can steady myself.",
            "I've come back from worse than this before.",
            "I would probably find a way back if the {START} went badly.",
            "I have had rough patches before and got through them.",
            "A setback would not be the end of it, I do not think.",
        ),
        2: (
            "Whatever happens out there, I know I can reset and keep going.",
            "I've been behind in a {EVENT} before and come back — that doesn't scare me.",
            "A bad start wouldn't finish me. I'd find my way into it.",
            "If the plan goes I trust myself to build another one mid-{EVENT}.",
            "I have lost the opening exchanges before and still finished strongly.",
        ),
        3: (
            "There is nothing that can happen in this {EVENT} that I can't come back from.",
            "I've been through far worse and I'm still here — that's what I hold on to.",
            "Whatever this {EVENT} throws at me, I will find my way back into it.",
            "I have recovered from far worse than anything that can happen this week.",
            "No setback in this {EVENT} would stop me. I have proved that to myself.",
        ),
    },
}

CATEGORICAL_REALISATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "motivation_orientation": {
        "approach": (
            "I want to go out and take this {EVENT} on and see what I'm capable of.",
            "I'm here to find out how good I can actually be.",
            "I want to push it from the {START} and see where that takes me.",
            "I want to see how far I can push this before it pushes back.",
            "I am chasing something here, not protecting anything.",
        ),
        "avoidance": (
            "I just don't want to embarrass myself in front of that crowd.",
            "Mostly I need to not mess this one up again.",
            "I can't afford another performance like the last one.",
            "I just need to get through this without anything going badly wrong.",
            "As long as I do not repeat last month I will settle for that.",
        ),
        "mixed": (
            "I want the win, but mostly I need to not fall apart like last time.",
            "Part of me wants to attack it and part of me just wants to survive it.",
            "I would love a big one, but honestly I would take not falling apart.",
            "Half of me is chasing this and half of me is bracing for it.",
            "I want to attack this and I also want it over with.",
        ),
    },
    "attentional_focus": {
        "focused": (
            "All I'm thinking about is my first two minutes — nothing past that.",
            "My whole {EVENT} is the plan and the {START}. That's it.",
            "I'm keeping it to the things I can actually control.",
            "My attention is on the process and nothing beyond it.",
            "I have narrowed it down to the first few exchanges and nothing else.",
        ),
        "distracted": (
            "I keep checking what everyone else is doing instead of my own {EVENT}.",
            "I've been on my phone reading about this all week instead of preparing.",
            "I can't stop thinking about the scoreline instead of the process.",
            "I have spent more time on the timeline this week than on preparing.",
            "My head has been everywhere except the {EVENT} itself.",
        ),
        "mixed": (
            "I know my plan, but the noise keeps pulling me out of it.",
            "I'm mostly locked in, though I do keep glancing at the draw.",
            "I get into the plan and then something pulls me straight back out.",
            "Mostly I am on task, but the crowd keeps taking my attention.",
            "I hold my focus for a while and then lose it again.",
        ),
    },
    "coping_style": {
        "task_focused": (
            "When the nerves hit I go back to my breathing routine and my checklist.",
            "I've talked it through with my coach and we've got a plan for the {START}.",
            "I write down the three things I control and I read them back.",
            "I run the same warm-up routine every time and it settles me.",
            "I break it into small jobs and work through them one at a time.",
        ),
        "avoidance": (
            "I just try not to think about it at all until I'm at the {START}.",
            "I've been avoiding the video and anything to do with the draw.",
            "I'd rather not talk about the {EVENT} at all this week.",
            "I keep myself busy with anything that is not the {EVENT}.",
            "I have been switching the subject every time it comes up.",
        ),
        "mixed": (
            "I've been through it with my coach, but I'm still avoiding the footage.",
            "I do my routine, then I spend the rest of the day pretending it isn't happening.",
            "I do my preparation properly and then hide from the rest of it.",
            "I have worked the plan through, though I am still dodging the video.",
            "Half of my week has been preparation and half of it avoidance.",
        ),
    },
    "appraisal_orientation": {
        "challenge": (
            "This is exactly the kind of field I've been waiting to test myself against.",
            "This {EVENT} is an opportunity and I've got what it takes to meet it.",
            "It's a big one, and that's the point — that's why I train.",
            "This is a demand I have the tools for and I want it.",
            "A field this strong is the reason I have put the work in.",
        ),
        "threat": (
            "This field is way above me. I'm going to get exposed out there.",
            "I don't think I've got anywhere near enough for this {EVENT}.",
            "This is too big a step up and I know it.",
            "I have not got what this {EVENT} is going to ask of me.",
            "I am out of my depth here and everyone is going to see it.",
        ),
        "mixed": (
            "It's a huge opportunity, but I'm not sure I'm ready for it.",
            "Part of me thinks I can handle this and part of me knows I might not.",
            "It is the chance I wanted and I am not certain I can meet it.",
            "I can see the opportunity and I can also see myself falling short.",
            "This could be the making of me or the undoing of me.",
        ),
    },
}

#: The interpretation modifier from `taxonomy.yaml`. Only ever attached where a
#: parent anxiety construct is present with intensity >= 1, per the rubric.
INTERPRETATION_REALISATIONS: dict[str, tuple[str, ...]] = {
    "facilitative": (
        "The nerves are there, but that's how I know I'm switched on — I need them.",
        "I want to feel like this. Flat is worse.",
        "That edge is useful to me. It means I care about this {EVENT}.",
        "I would rather turn up nervous than turn up numb.",
    ),
    "debilitative": (
        "The nerves just wreck me. I lose the plot completely once they start.",
        "Once that feeling starts I know the {EVENT} is already slipping away.",
        "When it takes hold I stop being able to do the simple things.",
        "That feeling does not sharpen me, it takes the {EVENT} away from me.",
    ),
}

#: Neutral, construct-free sentences. Essential rather than decorative: a
#: multi-label classifier trained only on construct-bearing text learns that
#: every utterance expresses something, and the taxonomy's negative examples are
#: exactly this kind of logistics talk.
NEUTRAL_SENTENCES: tuple[str, ...] = (
    "We fly out on Thursday and the {EVENT} is on Saturday morning.",
    "The coach named the line-up earlier in the week.",
    "Training has been at the usual times this block.",
    "I've been reading a fair bit on the trip over.",
    "The {START} is scheduled for the evening session.",
    "Kit arrived yesterday, so that's one thing sorted.",
    "It's a strong field this year by all accounts.",
    "We had the team meeting this morning as normal.",
    "The travel schedule was confirmed on Monday.",
    "There is a media session booked for the day before the {EVENT}.",
    "Accreditation was sorted out at the hotel this morning.",
    "The warm-up area opens two hours before the {START}.",
    "We have been on the same food and sleep routine all week.",
    "The physio checked everyone over after the session on Tuesday.",
    "Results from the heats should be up by lunchtime.",
    "The venue is about forty minutes from where we are staying.",
)

#: Co-occurrence affinities, taken from `taxonomy.yaml`'s own edge-case notes --
#: e.g. "Threat appraisal frequently co-occurs with cognitive_anxiety" and
#: "Overlap with cognitive_anxiety is common [for perceived_stress]". Encoding
#: them makes the corpus reflect the rubric's stated reality rather than
#: sampling constructs independently, which would produce implausible records.
AFFINITIES: dict[str, tuple[str, ...]] = {
    "cognitive_anxiety": ("appraisal_orientation", "perceived_stress", "somatic_anxiety"),
    "appraisal_orientation": ("cognitive_anxiety", "self_confidence"),
    "perceived_stress": ("cognitive_anxiety", "burnout_signal"),
    "burnout_signal": ("perceived_stress", "coping_style"),
    "self_confidence": ("resilience", "appraisal_orientation"),
    "resilience": ("self_confidence", "coping_style"),
    "coping_style": ("somatic_anxiety", "attentional_focus"),
    "somatic_anxiety": ("coping_style", "cognitive_anxiety"),
    "attentional_focus": ("cognitive_anxiety", "coping_style"),
    "motivation_orientation": ("appraisal_orientation", "self_confidence"),
}

ALL_CONSTRUCTS: tuple[str, ...] = tuple(GRADED_REALISATIONS) + tuple(CATEGORICAL_REALISATIONS)


# ---------------------------------------------------------------------------
# Lexical variation layer (generator v1.1) -- the OPEN-012 mitigation.
#
# v1.0 measured 444 word types over 30k tokens (TTR 0.0146). A classifier
# trained on that learns template surface forms, not construct semantics.
#
# This layer swaps words for near-synonyms AFTER a template is rendered. Two
# properties matter and both are deliberate:
#
#   1. It raises the TYPE count, not just the token count. TTR is types/tokens,
#      so adding more copies of the same words would not have helped.
#   2. It does NOT change the template identity. `template_id` still names the
#      underlying template, so `src/evaluation/splits.py` can hold every
#      paraphrase of a template out together. A paraphrase of a template the
#      model saw in training is still leakage, and the split must treat it that
#      way -- otherwise this mitigation would quietly manufacture the very
#      inflation it exists to prevent.
#
# Synonyms are chosen to be construct-preserving. Swapping "worried" for
# "anxious" leaves cognitive_anxiety intact; swapping it for "annoyed" would
# not, so no such pair appears here.
# ---------------------------------------------------------------------------

SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    # NOTE ON WHAT IS *NOT* HERE. Substitution is word-for-word and
    # context-blind, so any group whose members take different grammatical
    # arguments produces broken English. A first pass included
    # ("thinking", "fixating") and generated "fixating ABOUT the result"
    # (it takes "on"); ("need", "must") generated "I must TO not mess this up";
    # ("lose", "fall short") generated "I fall short the plot". Those groups
    # were removed rather than special-cased. Every group below is safe under
    # blind substitution: same part of speech AND same argument structure.
    ("worried", "anxious", "uneasy", "apprehensive", "on edge"),
    ("scared", "afraid", "frightened", "fearful"),
    ("tired", "weary", "fatigued", "drained", "spent"),
    ("drained", "hollowed out", "emptied", "wrung out"),
    ("nervous", "jittery", "twitchy", "keyed up"),
    ("calm", "settled", "steady", "composed", "level"),
    ("confident", "assured", "certain", "self-assured"),
    ("ready", "prepared", "primed", "set"),
    ("focused", "locked in", "dialled in", "zeroed in"),
    ("distracted", "scattered", "unfocused", "pulled about"),
    ("plan", "process", "approach"),
    ("crowd", "stands", "spectators", "gallery"),
    ("coach", "trainer", "staff"),
    ("week", "fortnight", "build-up", "lead-in"),
    ("morning", "afternoon", "evening"),
    ("shaking", "trembling", "quivering", "unsteady"),
    ("sleep", "rest", "shut-eye"),
    ("stomach", "gut", "insides"),
    ("heart", "pulse", "chest"),
    ("wrong", "badly", "awry", "off the rails"),
    ("opportunity", "chance", "opening", "shot"),
    ("difficult", "hard", "tough", "demanding", "punishing"),
    ("manage", "handle", "cope with", "deal with"),
    ("beaten", "defeated", "outplayed", "bettered"),
    ("hope", "reckon", "believe", "trust"),
    ("honest", "truthful", "straight", "candid"),
    ("busy", "hectic", "crowded", "relentless"),
    ("pressure", "strain", "load", "weight"),
    ("doubt", "hesitation", "misgiving", "second thoughts"),
    ("excited", "eager", "keen", "fired up"),
    ("small", "slight", "faint", "minor"),
    ("big", "large", "major", "sizeable"),
    ("good", "solid", "decent", "strong"),
    ("bad", "poor", "rough", "ugly"),
    # Second pass, targeting the highest-frequency remaining template words.
    # Type count is what moves TTR, so breadth beats depth here.
    ("start", "outset", "opening", "beginning"),
    ("race", "event", "contest"),
    ("field", "line-up", "draw", "entry list"),
    ("season", "campaign", "year"),
    ("result", "outcome", "scoreline", "verdict"),
    ("training", "practice", "prep"),  # no "sessions": plural breaks verb agreement
    ("mistake", "error", "slip", "lapse"),
    ("think", "reckon", "figure", "suppose"),
    ("want", "intend", "mean", "aim"),
    ("everyone", "everybody", "all of them"),
    ("nothing", "not a thing", "none of it"),
    ("talk", "speak", "chat"),
    ("noise", "din", "racket", "clamour"),
    ("legs", "limbs", "quads"),
    ("hands", "fingers", "grip"),
    ("breathing", "breathwork", "breath control"),
    ("checklist", "cue card", "notes", "list"),
    ("phone", "feed", "timeline"),
    ("video", "footage", "tape", "replay"),
    ("meeting", "briefing", "huddle"),
    ("schedule", "calendar", "programme", "timetable"),
    ("exams", "coursework", "studies", "assessments"),
    ("selection", "team announcement", "the squad call"),
    ("sorted", "handled", "squared away", "done"),
    ("switched", "turned", "flicked"),
    ("point", "purpose", "reason"),
    ("job", "chore", "duty", "obligation"),
    ("difference", "impact", "dent", "change"),
    # ("part", "portion", "corner", "piece") was removed at Phase 9 (OPEN-015).
    # Every occurrence of "part" in the template bank sits inside the idiom
    # "part of me", and the idiom does not survive substitution: the group
    # generated "corner of me" (9 records), "portion of me" (10) and
    # "piece of me" (14) at seed 42 -- verified at Phase 9 by reconstructing the
    # v1.1 generator from `git show HEAD:` and regenerating. An earlier draft of
    # this comment said 11 for "corner of me"; the true count is 9, matching
    # docs/open_issues.md and phase8_handover.md, and the other two are correct.
    # All four members share a part of speech
    # AND an argument structure, which is the constraint this bank was reviewed
    # against -- so the review could not have caught it. **Idiom membership is
    # a third constraint**, and `src/ingestion/synonym_audit.py` now checks it
    # mechanically rather than by reading. Do not reinstate this group.
    ("moment", "instant", "second"),
    ("everything", "the whole lot", "all of it"),
)

#: word -> its synonym group. Built once. Multi-word entries are matched as
#: whole phrases before single words, so "on edge" is not broken up.
_SYNONYM_INDEX: dict[str, tuple[str, ...]] = {
    variant: group for group in SYNONYM_GROUPS for variant in group
}

#: Discourse framing. Adds register variety and vocabulary without altering the
#: construct expressed by the sentence it wraps.
DISCOURSE_PREFIXES: tuple[str, ...] = (
    "",
    "",
    "",
    "Honestly, ",
    "To be fair, ",
    "If I'm truthful, ",
    "Look, ",
    "Between us, ",
    "The way I see it, ",
    "Right now, ",
    "Truth be told, ",
    "In all honesty, ",
    "Put it this way, ",
    "If I'm being straight, ",
    "At this stage, ",
    "Sitting here now, ",
)

#: Discourse suffixes, as **clauses** rather than sentences (v1.4, OPEN-018).
#:
#: This is the fix that actually worked, and the first attempt is worth recording
#: because it looked right and was not. Expanding the bank from 8 entries to 17
#: spread the repeats but did not reduce them: every construct sentence still
#: drew a suffix, Phase 8 still segmented each suffix into its own standalone
#: utterance, and the corpus still put 38.6% of all utterances into twenty
#: strings. Bank size was never the lever. **Sentence-hood was.**
#:
#: So a suffix is now a lowercase clause joined to its parent with an em dash,
#: and `_frame` strips the parent's full stop before attaching. `"I'm nervous.
#: That's where my head is at."` becomes `"I'm nervous — that's where my head is
#: at."`: one utterance instead of two, and the segmenter has nothing to split.
#:
#: Two consequences, both wanted. Duplicate utterances fall because the repeated
#: text is no longer a whole utterance. And median utterance length rises, which
#: matters independently -- Phase 9 flagged a 9-token median as too short for an
#: annotator to judge `appraisal_orientation` from.
DISCOURSE_SUFFIXES: tuple[str, ...] = (
    "",
    "",
    "",
    " — that's just where I am.",
    " — anyway, that's the reality.",
    " — make of that what you will.",
    " — that's the honest version.",
    " — it is what it is.",
    " — that's about the size of it.",
    " — take that how you like.",
    " — that's where my head is at.",
    " — not much more to say on it.",
    " — that's the truth of it.",
    " — for what it's worth.",
    " — that's just how it feels.",
    " — I'll leave it there.",
    " — that's me being straight about it.",
)


def _vary(sentence: str, rng: random.Random, rate: float = 0.55) -> str:
    """Swap words for construct-preserving near-synonyms, deterministically.

    **Guarded since v1.3 (OPEN-016).** Every candidate substitution is applied,
    the result is checked against `substitution_verdicts.is_defective`, and the
    substitution is reverted if it would produce a token sequence a human ruled
    broken or degraded.

    Why guard rather than shrink the bank. `think -> figure` is broken in *"all
    I figure about"* and unremarkable in *"I figure I'm ready"*. The defect is a
    property of the **frame**, not of the word, and a context-blind bank can only
    accept or reject the word. Measured at n=4,000, seed 42: deleting the 34
    implicated members costs 49 realised types (643 -> 594); the guard costs 18
    (643 -> 625) and removes nothing from the bank, so a future template using
    one of those words in a good frame gets it back for free. Both reach zero
    defects. Full table in `substitution_verdicts.py`.

    **The RNG draw happens before the check, and is not retried.** A rejected
    substitution consumes its random numbers exactly as an accepted one does, so
    the stream depends only on which tokens are substitutable, not on which
    substitutions survived. Retrying until something passed would make the
    stream depend on the verdict table, and every future edit to that table
    would silently reshuffle the whole corpus.
    """
    # Phrase-level first, so multi-word synonyms survive tokenisation.
    for group in SYNONYM_GROUPS:
        for variant in group:
            if " " in variant and variant in sentence and rng.random() < rate:
                candidate = sentence.replace(variant, rng.choice(group), 1)
                if not is_defective(candidate):
                    sentence = candidate

    out: list[str] = []
    for token in sentence.split(" "):
        head = token.rstrip(".,!?;:—")
        tail = token[len(head) :]
        low = head.lower()
        group = _SYNONYM_INDEX.get(low)
        if group is not None and rng.random() < rate:
            replacement = rng.choice(group)
            if head[:1].isupper():
                replacement = replacement[0].upper() + replacement[1:]
            # Check against the sentence as it will actually read: the already
            # decided prefix, this candidate, and the untouched remainder. A
            # check against the candidate token alone would miss every
            # multi-token signature, which is most of them.
            decided = out + [replacement + tail]
            remainder = sentence.split(" ")[len(decided) :]
            if is_defective(" ".join(decided + remainder)):
                out.append(token)
            else:
                out.append(replacement + tail)
        else:
            out.append(token)
    return " ".join(out)


def _frame(sentence: str, rng: random.Random) -> str:
    """Optionally wrap a sentence in a discourse marker.

    The first word is lowercased when a prefix is attached -- except for "I"
    and its contractions, which stay capitalised. Missing that produced
    "The way I see it, i'd rather not talk about it", which no human writes.
    """
    prefix = rng.choice(DISCOURSE_PREFIXES)
    suffix = rng.choice(DISCOURSE_SUFFIXES)
    if prefix:
        first = sentence.split(" ", 1)[0].rstrip(".,!?;:")
        if not (first == "I" or first.startswith("I'")):
            sentence = sentence[0].lower() + sentence[1:]
        sentence = prefix + sentence
    if suffix:
        # Strip the parent's full stop so the suffix joins as a clause. Only a
        # period: a template ending in "?" or "!" is carrying its own force and
        # a trailing clause after it reads wrong, so those keep their sentence
        # boundary and their suffix is dropped rather than mangled.
        if sentence.endswith("."):
            sentence = sentence[:-1] + suffix
        return sentence
    return sentence


@dataclass(frozen=True)
class Stratum:
    """The contextual slot a record is generated into."""

    sport: str
    competition_level: str
    region: str
    source_type: str
    time_to_competition_days: int
    training_load_hint: str | None


def _fill(template: str, sport: str) -> str:
    event, start = SPORT_TERMS[sport]
    return template.replace("{EVENT}", event).replace("{START}", start)


def _draw_stratum(rng: random.Random) -> Stratum:
    return Stratum(
        sport=rng.choice(SPORTS),
        competition_level=rng.choice(COMPETITION_LEVELS),
        region=rng.choice(REGIONS),
        source_type=rng.choice(SOURCE_TYPES),
        time_to_competition_days=rng.choice(TIME_TO_COMPETITION_DAYS),
        training_load_hint=rng.choice(TRAINING_LOAD_HINTS),
    )


def _draw_constructs(rng: random.Random) -> list[str]:
    """Pick 0-3 constructs, using the taxonomy's co-occurrence notes."""
    n = rng.choices((0, 1, 2, 3), weights=(8, 34, 40, 18), k=1)[0]
    if n == 0:
        return []
    first = rng.choice(ALL_CONSTRUCTS)
    chosen = [first]
    while len(chosen) < n:
        pool = [c for c in AFFINITIES.get(chosen[-1], ALL_CONSTRUCTS) if c not in chosen]
        if not pool or rng.random() < 0.25:
            pool = [c for c in ALL_CONSTRUCTS if c not in chosen]
        if not pool:
            break
        chosen.append(rng.choice(pool))
    return chosen


def _realise(
    construct: str,
    rng: random.Random,
    sport: str,
    *,
    cap_intensity: int = 3,
) -> tuple[str, dict[str, Any]]:
    """Produce one sentence for a construct, plus what was planted."""
    if construct in GRADED_REALISATIONS:
        options = (1, 2, 3)[:cap_intensity]
        weights = (35, 42, 23)[:cap_intensity]
        intensity = rng.choices(options, weights=weights, k=1)[0]
        bank = GRADED_REALISATIONS[construct][intensity]
        index = rng.randrange(len(bank))
        # `template_id` is the stable identity of the underlying template, and
        # it survives the lexical-variation layer on purpose. It is what
        # src/evaluation/splits.py groups on to build a leakage-free split.
        spec = {
            "construct": construct,
            "intensity": intensity,
            "template_id": f"{construct}:i{intensity}:{index}",
        }
        return _fill(bank[index], sport), spec
    labels = CATEGORICAL_REALISATIONS[construct]
    label = rng.choices(tuple(labels), weights=(42, 42, 16), k=1)[0]
    bank = labels[label]
    index = rng.randrange(len(bank))
    spec = {
        "construct": construct,
        "label": label,
        "template_id": f"{construct}:{label}:{index}",
    }
    return _fill(bank[index], sport), spec


#: Construct pairs that cannot both be maximal in one coherent utterance. Drawn
#: from `taxonomy.yaml`'s own `risk_direction` field: these pairs sit on
#: opposite sides of the risk fusion, so a record maxing out both would be
#: simultaneously the highest- and lowest-risk text in the corpus.
_OPPOSED_PAIRS: tuple[frozenset[str], ...] = (
    frozenset({"cognitive_anxiety", "self_confidence"}),
    frozenset({"cognitive_anxiety", "resilience"}),
    frozenset({"burnout_signal", "self_confidence"}),
    frozenset({"burnout_signal", "resilience"}),
    frozenset({"perceived_stress", "resilience"}),
)


def _contradicts(spec: dict[str, Any], already: list[dict[str, Any]]) -> bool:
    """True when `spec` would be a maximal-intensity opposite of something planted."""
    if spec.get("intensity") != 3:
        return False
    for prior in already:
        if prior.get("intensity") != 3:
            continue
        if frozenset({spec["construct"], prior["construct"]}) in _OPPOSED_PAIRS:
            return True
    return False


def generate_records(
    count: int,
    *,
    seed: int,
    source_id: str,
) -> list[RawRecord]:
    """Generate `count` synthetic pre-competition records, deterministically.

    Same `seed` and `count` always produce identical output. There is one RNG
    and it is seeded once; nothing else in this module consumes randomness.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    rng = random.Random(seed)
    records: list[RawRecord] = []

    for index in range(count):
        stratum = _draw_stratum(rng)
        constructs = _draw_constructs(rng)

        sentences: list[str] = []
        planted: list[dict[str, Any]] = []

        # A neutral opener on roughly a third of records, so construct language
        # is not always utterance-initial.
        if rng.random() < 0.35:
            sentences.append(_vary(_fill(rng.choice(NEUTRAL_SENTENCES), stratum.sport), rng))

        for construct in constructs:
            sentence, spec = _realise(construct, rng, stratum.sport)
            # Contradiction guard. Simultaneous maxima on constructs that pull
            # in opposite directions ("I have absolutely no doubt" alongside "I
            # cannot stop thinking about how this falls apart") is not
            # ambivalence, it is an incoherent record. Ambivalence at moderate
            # intensity is real and is preserved; only the double-3 case is
            # softened, and only the second construct drawn is moved, so the
            # first construct's distribution is unaffected.
            if _contradicts(spec, planted):
                sentence, spec = _realise(construct, rng, stratum.sport, cap_intensity=2)
            # _vary AFTER _frame, not before (changed at v1.4, OPEN-018).
            # The old order varied the construct sentence and then bolted an
            # untouched prefix and suffix onto it, so the suffixes -- the
            # single largest source of duplicate utterances -- were the one
            # part of the corpus the variation layer never saw.
            sentences.append(_vary(_frame(sentence, rng), rng))
            planted.append(spec)

        # The interpretation modifier, constrained twice over.
        #
        # (a) The rubric permits it only where a parent anxiety construct is
        #     present. We additionally require intensity >= 2, because every
        #     realisation in INTERPRETATION_REALISATIONS is a strong statement
        #     ("the nerves just wreck me") and hanging one off "I've caught
        #     myself thinking about it once or twice" produces a record whose
        #     two halves disagree about how anxious the athlete is.
        #
        # (b) Theory-grounded coherence: under the Theory of Challenge and
        #     Threat States in Athletes [JonesMeijen2009], a challenge appraisal
        #     means resources are judged SUFFICIENT for the demand, which is
        #     incompatible with reading one's own arousal as debilitating. So a
        #     challenge appraisal admits only a facilitative reading, and a
        #     threat appraisal only a debilitative one. Sampling these
        #     independently would manufacture records that contradict the very
        #     framework the taxonomy cites.
        anxiety = [
            p
            for p in planted
            if p["construct"] in ("cognitive_anxiety", "somatic_anxiety")
            and p.get("intensity", 0) >= 2
        ]
        appraisal = next(
            (p.get("label") for p in planted if p["construct"] == "appraisal_orientation"),
            None,
        )
        interpretation: str | None = None
        if anxiety and rng.random() < 0.45:
            if appraisal == "challenge":
                interpretation = "facilitative"
            elif appraisal == "threat":
                interpretation = "debilitative"
            else:
                interpretation = rng.choice(("facilitative", "debilitative"))
            sentences.append(
                _vary(
                    _fill(rng.choice(INTERPRETATION_REALISATIONS[interpretation]), stratum.sport),
                    rng,
                )
            )

        # Records with no construct planted still need to be utterances.
        # Both of these used to bypass `_vary`, which is why a construct-free
        # record was byte-identical to every other record drawing the same
        # neutral sentence. v1.4 routes them through it like everything else.
        if not sentences:
            sentences.append(_vary(_fill(rng.choice(NEUTRAL_SENTENCES), stratum.sport), rng))
        if len(sentences) == 1 and not planted and rng.random() < 0.5:
            sentences.append(_vary(_fill(rng.choice(NEUTRAL_SENTENCES), stratum.sport), rng))

        records.append(
            RawRecord(
                record_id=f"{source_id}-{index:06d}",
                source_id=source_id,
                text=" ".join(sentences),
                time_to_competition_days=stratum.time_to_competition_days,
                sport=stratum.sport,
                competition_level=stratum.competition_level,
                region=stratum.region,
                source_type="synthetic",
                language="en",
                training_load_hint=stratum.training_load_hint,
                synthetic=True,
                deidentified=False,
                generation_spec={
                    "planted_constructs": planted,
                    "interpretation_modifier": interpretation,
                    "rendered_as": stratum.source_type,
                    "generator": f"{GENERATOR_NAME}@{GENERATOR_VERSION}",
                    "seed": seed,
                    "NOTE": (
                        "Generation metadata, NOT a label. Never use as evaluation "
                        "ground truth -- see docs/data_sources.md."
                    ),
                },
            )
        )

    return records


def generator_stamp(seed: int, *, generated_on: str | None = None) -> GeneratorStamp:
    """The `A2_synthetic` bookkeeping the allow-list requires."""
    return GeneratorStamp(
        name=GENERATOR_NAME,
        version=GENERATOR_VERSION,
        kind="template-grammar",
        seed=seed,
        generated_on=generated_on or _dt.date.today().isoformat(),
        prompts_location="src/ingestion/synthetic.py (version-controlled template bank)",
        notes=(
            "Deterministic seeded template grammar, no language model and no network "
            "call. Chosen over an LLM for byte-level reproducibility and because "
            "OPEN-008 leaves no OPENROUTER_API_KEY to verify an LLM path against. "
            "Lexical diversity is bounded by the template bank; see docs/data_sources.md."
        ),
        extra={
            "constructs_covered": list(ALL_CONSTRUCTS),
            "strata": {
                "sports": list(SPORTS),
                "competition_levels": list(COMPETITION_LEVELS),
                "regions": list(REGIONS),
                "time_to_competition_days": sorted(set(TIME_TO_COMPETITION_DAYS)),
            },
        },
    )


def synthetic_descriptor(
    source_id: str = "synth_precomp_v1",
    *,
    seed: int = 42,
) -> SourceDescriptor:
    """The allow-list descriptor for this generator's output.

    Every prohibition is declared explicitly. For synthetic text most are
    trivially true -- there is no real person, so there is no minor, no private
    communication, and no terms of service. Declaring them anyway is the point:
    `check_source` refuses a source that stays silent on any prohibition, so the
    trivial cases and the hard cases go through identical scrutiny.
    """
    return SourceDescriptor(
        source_id=source_id,
        source_name=(
            f"Synthetic pre-competition athlete utterances (template grammar v{GENERATOR_VERSION})"
        ),
        allowlist_category="A2_synthetic",
        url_or_citation=(
            "Generated for this project by src/ingestion/synthetic.py "
            f"({GENERATOR_NAME}@{GENERATOR_VERSION}, seed={seed}). Not derived from "
            "any external corpus."
        ),
        licence_or_consent_basis=(
            "Project-generated synthetic text. No third-party licence applies and no "
            "human subject is involved: no real person's words are reproduced, "
            "paraphrased, or used as a generation input. Released under the "
            "repository licence alongside the code that produces it."
        ),
        permitted_uses=(
            "Research use, training, evaluation, redistribution, and publication of "
            "verbatim examples. Because no real athlete is involved, this is the only "
            "category in the corpus from which examples may be quoted verbatim in the "
            "paper or dashboard (docs/ethics.md sec.3.3 condition 2)."
        ),
        redistribution_permitted=True,
        synthetic=True,
        subject_is_adult=True,  # No human subject exists; the athlete voice is fictional.
        language="en",
        notes=(
            "A2 fallback confirmed by the owner on 2026-08-09 after the Phase 7 survey "
            "found no public pre-competition athlete corpus. Scaffold corpus: bounded "
            "lexical diversity, no personal names, generation_spec is metadata not labels."
        ),
        sport=None,  # Varies per record; recorded at record level.
        competition_level=None,
        region=None,
        source_type="synthetic",
        time_to_competition_days=None,
        declares={
            "not_scraped_personal_social_media": True,
            "no_minors": True,
            "not_private_communication": True,
            "licence_and_tos_permit_this_use": True,
            "not_behind_auth_or_paywall": True,
            "not_health_injury_or_treatment_content": True,
            "provenance_is_complete": True,
        },
    )


def _tokens(records: Iterable[RawRecord]) -> list[str]:
    out: list[str] = []
    for record in records:
        out.extend(record.text.lower().split())
    return out


def type_token_ratio(records: Iterable[RawRecord]) -> float:
    """Distinct words over total words.

    Reported for continuity with the v1.0 figure, but **do not use it as the
    headline diversity metric**. Raw TTR falls as a corpus grows even when
    vocabulary is expanding, because the denominator grows without bound while
    the numerator saturates. Adding 9k tokens of paraphrase to this corpus
    raised the vocabulary by a quarter and left TTR flat, which is a property
    of the metric, not of the corpus. Use `mattr` and `vocabulary_size`.
    """
    tokens = _tokens(records)
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def vocabulary_size(records: Iterable[RawRecord]) -> int:
    """Distinct lowercased word types. Length-independent, unlike raw TTR."""
    return len(set(_tokens(records)))


def mattr(records: Iterable[RawRecord], window: int = 50) -> float:
    """Moving-average type-token ratio -- the length-corrected diversity metric.

    Mean TTR over every sliding window of `window` tokens. Because every window
    has the same denominator, MATTR is comparable across corpora of different
    sizes in a way raw TTR is not (Covington & McFall 2010). This is the number
    to quote when arguing the corpus is or is not lexically thin.
    """
    tokens = _tokens(records)
    if len(tokens) < window:
        return len(set(tokens)) / len(tokens) if tokens else 0.0
    total = 0.0
    windows = len(tokens) - window + 1
    for start in range(windows):
        total += len(set(tokens[start : start + window])) / window
    return total / windows


def distinct_text_rate(records: Iterable[RawRecord]) -> float:
    """Fraction of records whose exact text appears only once in the corpus."""
    texts = [r.text for r in records]
    if not texts:
        return 0.0
    return len(set(texts)) / len(texts)
