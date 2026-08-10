"""Word lists used by de-identification and the language filter.

Kept in one module, apart from the logic, for a reason that matters to the
paper rather than to the code: **these lists are the part of the
de-identifier a reviewer can audit.** The regexes are mechanical; the
judgement lives here, in which words are treated as ordinary language and
which are treated as evidence of an identifier. Burying that judgement inside
a function body would make it unreviewable.

Two asymmetries are deliberate.

1. `COMMON_WORDS` is a **safety list, not a dictionary**. A word here can never
   be redacted as a proper noun. Missing a word costs precision (an ordinary
   capitalised word gets replaced); adding a word that is also a real surname
   costs recall (a real name survives). `docs/ethics.md` sec.5.3 already states
   that residual re-identification risk is real, so where the two errors
   collide this file errs toward *keeping the list small* and letting the
   redaction fire.

2. `HEALTH_TERMS` is the opposite: it is a **trigger list**, and everything on
   it causes the surrounding clause to be deleted outright rather than
   placeholdered (`docs/ethics.md` sec.5.1, final row). Body parts are
   deliberately absent -- "my stomach is in knots" is `somatic_anxiety`
   evidence, the single most load-bearing construct in the taxonomy, and
   deleting it as "health data" would destroy the signal the project exists to
   measure.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Ordinary language
# ---------------------------------------------------------------------------

#: Verbs whose regular inflections are generated below. Kept separate from the
#: bulk list because the inflection matters: the single most common
#: false-positive shape in informal athlete text is `my physio keeps telling
#: me`, where a role noun is followed by a verb rather than a name. Without
#: "keeps" in the safety list, "keeps" gets redacted as a person.
COMMON_VERBS: frozenset[str] = frozenset(
    """
    ask beat breathe come decide drop eat expect feel finish focus forget get go happen hate
    help hold hope keep listen look lose love matter miss move need notice plan play pull push
    race remember rest run say seem show sleep sound speak start stop talk tell think train try
    turn wait want watch win work worry
    """.split()
)


def _inflect(verbs: frozenset[str]) -> frozenset[str]:
    """Generate regular -s / -ed / -ing forms.

    Deliberately crude and over-generating. A generated form that is not a real
    word ("beated") harms nothing; a missing form costs precision, because the
    de-identifier then treats an ordinary verb as a name.
    """
    forms: set[str] = set()
    for verb in verbs:
        stem = verb[:-1] if verb.endswith("e") else verb
        forms.update({verb, verb + "s", stem + "ed", stem + "ing", verb + "ed", verb + "ing"})
    return frozenset(forms)


#: Function words, common verbs and nouns, and sentence openers. Anything whose
#: lowercase form is here is never treated as a proper-noun candidate.
_BASE_COMMON_WORDS: frozenset[str] = frozenset(
    """
    a about above after again against all almost alone along already also although always am
    among an and another any anyone anything are around as ask at away back bad be because been
    before began begin behind being below best better between big bit both bring but by call
    came can cannot come coming could couple course day days deal did do does doing done down
    during each early either else end enough even ever every everybody everyone everything
    exactly far feel feeling felt few final finally find fine first for found from front full
    get getting give given go goes going gone good got great had half hard has have having he
    head hear heard help her here hers herself him himself his hold home honest honestly hope
    hour hours how however i if in inside instead into is it its itself just keep keeping kept
    kind knew know known last late later least leave left less let letting like little live
    long look looking lot made make making many mark mark's matter may maybe me mean meant might
    mind mine minute minutes moment monday month months more morning most much must my myself
    near need needed never new next night no nobody none nor not nothing now number of off
    often oh ok okay old on once one only onto or other others otherwise ought our ours out
    outside over own part people perhaps place plan point probably put quite rather ready real
    really rest right room round said same saw say saying says second see seem seems seen self
    sense set several shall she short should show side simply since sit small so some somebody
    somehow someone something sometimes soon sort sound speak spoke start started still stop
    such sure take taken taking talk talking tell telling ten than that the their theirs them
    themselves then there these they thing things think this those though thought three through
    time times to today together told tomorrow tonight too took top toward towards trust try
    trying turn two under until up upon us use used very want wanted was way we week weeks well
    went were what whatever when where whether which while who whole whom whose why will win
    winning wish with within without won word words work working worse worst would year years
    yes yesterday yet you your yours yourself
    """.split()
)

COMMON_WORDS: frozenset[str] = _BASE_COMMON_WORDS | _inflect(COMMON_VERBS)

#: Sport and competition vocabulary that is routinely capitalised in athlete
#: speech without naming anything. "The Final is on Sunday" names no event.
SPORT_WORDS: frozenset[str] = frozenset(
    """
    athlete athletes ball block blocks bout bouts camp coach coaching competition compete
    competing court crowd draw drill drills event fans field final finals fixture form game
    games gold gym heat heats home indoor injury lane leg legs lift lifts match matches medal
    medals meet meeting off-season opener opponent opponents outdoor pace performance pitch
    play player players playoff pool position preseason press qualifier qualifiers race races
    rank ranking recovery referee rep reps result results round rounds run runner running score
    season seed semi semis session sessions set sets shot side split sprint squad stadium
    stand start starter strength strong swim taper team teams technique test tests throw thrower
    throws track train trainer training trial trials umpire warm warmup weight weights win
    </>
    """.replace("</>", "").split()
)

#: Role nouns. A role is not an identity: "my coach" identifies nobody, so the
#: word survives. But a role noun immediately followed by an unknown token is
#: the strongest available cue that the unknown token is a person's name -- and
#: it is the only cue that works on lowercase names in informal text.
ROLE_NOUNS: frozenset[str] = frozenset(
    """
    agent boss captain chef coach dietician doctor gaffer keeper manager mentor nutritionist
    partner physician physio physiotherapist psych psychologist skipper teammate therapist
    trainer
    """.split()
)

#: Role nouns that imply a specific placeholder type. Anything not listed here
#: falls back to the untyped `[PERSON]`, which is the honest answer when the
#: relationship cannot be read off the sentence.
ROLE_PLACEHOLDER: dict[str, str] = {
    "coach": "[COACH]",
    "gaffer": "[COACH]",
    "manager": "[COACH]",
    "captain": "[TEAMMATE]",
    "skipper": "[TEAMMATE]",
    "teammate": "[TEAMMATE]",
}

WEEKDAYS: frozenset[str] = frozenset(
    "monday tuesday wednesday thursday friday saturday sunday".split()
)

MONTHS: tuple[str, ...] = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)

MONTH_ABBREVIATIONS: tuple[str, ...] = (
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
)

#: Units that make a bare number a measurement rather than an identifier.
#: `docs/ethics.md` sec.5.1 asks for jersey numbers and rankings, not for split
#: times -- "47 seconds" is performance data and redacting it would delete the
#: competitive context the risk index is supposed to be read against.
MEASUREMENT_UNITS: frozenset[str] = frozenset(
    """
    second seconds sec secs minute minutes min mins hour hours metre metres meter meters m km
    mile miles yard yards kilo kilos kg lb lbs pound pounds rep reps set sets lap laps length
    lengths degree degrees percent kmh mph point points
    """.split()
)

ORDINAL_WORDS: frozenset[str] = frozenset(
    """
    first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth
    """.split()
)

# ---------------------------------------------------------------------------
# Entity-type suffixes
# ---------------------------------------------------------------------------

#: A capitalised run ending in one of these is a venue, not a person.
VENUE_SUFFIXES: frozenset[str] = frozenset(
    """
    arena stadium ground grounds park centre center complex court courts field oval pool track
    velodrome gym gymnasium hall dome bowl
    """.split()
)

EVENT_SUFFIXES: frozenset[str] = frozenset(
    """
    invitational championship championships open cup cups games series trials classic masters
    league grand prix marathon meet nationals olympics regionals worlds
    """.split()
)

TEAM_SUFFIXES: frozenset[str] = frozenset(
    """
    academy athletic athletics club fc harriers hurricanes lions rangers rovers runners stars
    striders swifts titans united wanderers warriors wolves
    """.split()
)

ORG_SUFFIXES: frozenset[str] = frozenset(
    """
    apparel association college corporation federation foundation group gmbh inc institute ltd
    nutrition plc polytechnic school society sportswear trust university
    """.split()
)

#: Words that mark the following capitalised run as a place.
LOCATION_CUES: frozenset[str] = frozenset(
    """
    arrive arrived arriving based drive drove fly flew flown flying head heading land landed
    live lived moving moved relocate relocated travel travelled traveled travelling
    """.split()
)

#: Words that mark the following name as a rival.
OPPONENT_CUES: frozenset[str] = frozenset(
    """
    against beat beaten beating drawn face faced facing lose losing lost outrun play playing
    </>
    """.replace("</>", "").split()
)

#: Honorifics. A title is unambiguous evidence that what follows is a person.
TITLES: tuple[str, ...] = (
    "coach",
    "dr",
    "mr",
    "mrs",
    "ms",
    "miss",
    "prof",
    "professor",
    "sir",
    "captain",
    "capt",
)

SPEECH_VERBS: frozenset[str] = frozenset(
    """
    said says told adds added confirmed insisted admitted explained revealed announced
    """.split()
)

# ---------------------------------------------------------------------------
# Health -- removed entirely, never placeholdered
# ---------------------------------------------------------------------------

#: Diagnoses, procedures, and treatment vocabulary. `docs/ethics.md` sec.5.1
#: removes these outright; `config/data_sources_allowlist.yaml` P6 makes
#: health-subject text ineligible for the corpus in the first place, so this is
#: a second line of defence rather than the only one.
#:
#: NOTE the exclusions. Body parts (stomach, hands, legs, shoulder, chest,
#: breathing) are NOT here. They are the surface form of `somatic_anxiety`.
#: "physio" is not here either -- it appears in ROLE_NOUNS, because in athlete
#: speech it is usually a person, not a treatment episode.
STRONG_HEALTH_TERMS: frozenset[str] = frozenset(
    """
    acl mcl aneurysm appendicitis arthritis asthma bipolar bursitis cancer concussion diabetes
    diagnosed diagnosis dislocated dislocation epilepsy fracture fractured hernia mri
    prescribed prescription reconstruction rehab rehabilitation surgeon surgery surgical
    tendonitis tendinitis ultrasound
    """.split()
)

#: Words that mean a treatment episode in one context and ordinary English in
#: another. "torn about the decision" is not health data; "my hamstring is
#: torn" is. These fire only with a body part or a treatment cue nearby.
AMBIGUOUS_HEALTH_TERMS: frozenset[str] = frozenset(
    """
    inflammation infection operated operation scan strain strained tear therapy torn
    """.split()
)

#: Never a trigger on its own -- only context for an ambiguous term.
#:
#: This is the most consequential exclusion in the file. Somatic anxiety
#: surfaces almost entirely as body language: knotted stomach, shaking hands,
#: tight chest, heavy legs. Treating body parts as health data would delete the
#: evidence for one of the ten locked constructs and quietly gut the corpus.
BODY_PARTS: frozenset[str] = frozenset(
    """
    achilles ankle arm arms back calf calves chest elbow foot feet finger fingers groin hand
    hands hamstring head heart hip hips knee knees leg legs muscle neck quad quads ribs
    shoulder shoulders stomach thigh throat toe wrist
    """.split()
)

#: Treatment-episode cues that also license an ambiguous term.
HEALTH_CUES: frozenset[str] = frozenset(
    """
    appointment clinic consultant dose doctor hospital medication physio scan specialist
    treatment
    """.split()
)

#: Medication names. Necessarily a short list: there is no offline drug
#: dictionary in this project and inventing one would be worse than declaring
#: the limit. `docs/preprocessing.md` states plainly that an unlisted drug name
#: is a known miss, and the allow-list's P6 exclusion is what actually carries
#: this risk.
MEDICATION_TERMS: frozenset[str] = frozenset(
    """
    adderall amitriptyline citalopram codeine cortisone diazepam escitalopram fluoxetine
    gabapentin ibuprofen ketorolac lithium melatonin naproxen paroxetine prednisone propranolol
    sertraline tramadol venlafaxine zopiclone
    """.split()
)

#: The full trigger vocabulary, for reporting and tests.
ALL_HEALTH_TERMS: frozenset[str] = STRONG_HEALTH_TERMS | AMBIGUOUS_HEALTH_TERMS | MEDICATION_TERMS

# ---------------------------------------------------------------------------
# Language identification
# ---------------------------------------------------------------------------

#: Stopword profiles for a coarse, offline language filter. Not a language
#: identifier in the research sense -- see `language.py` for what it does and
#: does not claim.
#:
#: **Profile sizes are kept comparable on purpose.** The filter scores a text
#: as "share of tokens matching this profile", so an English profile smaller
#: than the Portuguese one makes English lose ties it should win. That is not
#: hypothetical: the first version of this table had 20 English entries and 21
#: Portuguese ones, and it classified "Slept a little lighter than usual last
#: night" as Portuguese, because "a" is a Portuguese article and none of the
#: other seven words were in the English list. Two perfectly good records were
#: dropped from the corpus before the counts were read closely enough to
#: notice. Unequal profiles produce a language filter that is really a
#: profile-size filter.
STOPWORD_PROFILES: dict[str, frozenset[str]] = {
    "en": frozenset(
        """
        a an the and or but is are was were be been am do does did have has had i you he she
        it we they me my your his her our their this that these those to of in on at for with
        from not no so if then than as by about out up down over
        """.split()
    ),
    "es": frozenset(
        """
        el la los las un una unos unas de del que y o pero es son era eran ser estar he ha han
        yo tu el ella nosotros ellos me mi tu su nuestro este esta esos a en por con para sin
        no si mas como sobre desde hasta muy
        """.split()
    ),
    "fr": frozenset(
        """
        le la les un une des du de que et ou mais est sont etait etaient etre avoir ai a ont je
        tu il elle nous ils me mon ton son notre ce cette ces a en dans sur pour avec sans ne
        pas si plus comme depuis jusqu tres
        """.split()
    ),
    "de": frozenset(
        """
        der die das ein eine einen und oder aber ist sind war waren sein haben habe hat hatten
        ich du er sie wir ihr mein dein sein unser dieser diese dieses zu in an auf für mit von
        ohne nicht kein wenn dann als wie sehr
        """.split()
    ),
    "pt": frozenset(
        """
        o a os as um uma uns umas de do da que e ou mas é são era eram ser estar tenho tem têm
        eu tu ele ela nós eles me meu teu seu nosso este esta esses em por com para sem não se
        mais como sobre desde até muito
        """.split()
    ),
    "it": frozenset(
        """
        il lo la i gli le un uno una di del che e o ma è sono era erano essere avere ho ha hanno
        io tu lui lei noi loro mi mio tuo suo nostro questo questa questi a in su per con senza
        non se più come sopra da molto
        """.split()
    ),
    "nl": frozenset(
        """
        de het een en of maar is zijn was waren hebben heb heeft hadden ik jij hij zij wij zij
        mij mijn jouw haar ons hun deze dit die dat te in op aan voor met van zonder niet geen
        als dan zoals sinds tot heel
        """.split()
    ),
}
