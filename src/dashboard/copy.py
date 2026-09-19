"""Plain-English copy for the dashboard. One place, screened at import.

Why this module exists
----------------------
Phase 20 shipped a page that was *correct* and unreadable: every caption was
written for a reviewer who already knows what macro-F1, calibration, a polarity
policy and OPEN-021 are. A coach opening the demo could not tell what the risk
index was, what "inert" meant, or why a bar sat on the zero rule. A number a
reader cannot interpret is not more honest than a number they misread -- it is
just harder to argue with.

So the wording lives here, as data, next to the honesty layer rather than inside
the Streamlit callback:

* Every string in this module is passed through
  `assert_no_forbidden_language` **at import time** (see the loop at the bottom).
  A plain-English rewrite is exactly the change most likely to reintroduce the
  word "accuracy" or an upgraded validation claim, and the screen that catches
  that in `view.render_text()` never sees a caption the shell writes itself.
* Nothing here computes anything. Numbers come from `view`; this module only
  names things.

Register: written for a coach or an athlete with no machine-learning background.
The technical vocabulary is not deleted -- it is moved into `GLOSSARY`, so a
reviewer can still map every plain phrase back to the term in the paper.
"""

from __future__ import annotations

from src.dashboard.view import assert_no_forbidden_language

# ---------------------------------------------------------------------------
# What the page is
# ---------------------------------------------------------------------------

HEADLINE = "What this page does, in one line"

INTRO = (
    "It reads a short piece of writing from an athlete before a competition, looks for "
    "ten well-known psychological signals in the words, and combines them into a single "
    "0-to-1 number it calls the risk index, and then shows you exactly which words produced "
    "that number."
)

WHAT_IT_IS_NOT = (
    "It is a work in progress and a conversation starter, not a test, not a diagnosis "
    "and not a judgement about any real person. The text it was built on is synthetic, "
    "written by this project's own generator, so every number on this page measures "
    "*agreement with labels we planted ourselves*, not how well the system would read a "
    "real athlete."
)

HOW_IT_WORKS: tuple[tuple[str, str], ...] = (
    (
        "1. Read the text",
        "A sentence or two of what the athlete wrote or said before the event.",
    ),
    (
        "2. Look for ten signals",
        "Things sports psychologists already measure with questionnaires: worry, bodily "
        "nerves, self belief, tiredness, and so on. Each gets a strength from 0 to 1.",
    ),
    (
        "3. Combine them into one number",
        "Six of the ten signals have an agreed direction (worry pushes the number up, "
        "self belief pulls it down). They are added up with fixed weights.",
    ),
    (
        "4. Show the working",
        "For each signal, the words in the text that triggered it. If a signal moved the "
        "number but no words back it up, the page says so instead of hiding it.",
    ),
)

# ---------------------------------------------------------------------------
# The three headline numbers
# ---------------------------------------------------------------------------

RISK_PLAIN = (
    "Higher means more of the signals we treat as risky showed up in the words. "
    "It is a way of ordering texts from calmer to more strained, and it is **not** a "
    "probability, a percentage, or a score out of 1 that means anything on its own. "
    "0.87 does not mean an 87% chance of anything."
)

CONTRIBUTING_PLAIN = (
    "Ten signals are looked for; only six can push the number up or down. The other four "
    "(how the athlete frames the event, where their attention is, how they cope, what "
    "drives them) can be good *or* bad depending on which way they point, and the system "
    "is not yet allowed to decide which, so it detects them, shows them, and gives them "
    "a weight of zero. Those four are marked **inert**."
)

UNEVIDENCED_PLAIN = (
    "The honest weak spot. This counts signals that moved the number while the system "
    "could not point at any words that justify it. Across the whole synthetic corpus that "
    "happens in 104 of 120 cases, and we report it rather than quietly dropping those rows."
)

# ---------------------------------------------------------------------------
# The ten signals, in everyday words
# ---------------------------------------------------------------------------

#: construct -> (everyday name, one plain sentence, which way it pushes)
CONSTRUCTS: dict[str, tuple[str, str, str]] = {
    "cognitive_anxiety": (
        "Worry in the head",
        "Fear of failing, replaying the start, self-doubt, expecting the worst.",
        "raises",
    ),
    "somatic_anxiety": (
        "Nerves in the body",
        "Racing heart, shaky hands, butterflies, tight muscles, bad sleep.",
        "raises",
    ),
    "self_confidence": (
        "Self belief",
        "Expecting to perform well and to execute the plan under pressure.",
        "lowers",
    ),
    "perceived_stress": (
        "Feeling overloaded",
        "The demands feel bigger than what the athlete has to meet them with.",
        "raises",
    ),
    "burnout_signal": (
        "Running on empty",
        "Exhaustion, not caring anymore, feeling the sport is not worth it.",
        "raises",
    ),
    "resilience": (
        "Bounce-back",
        "Being able to recover if things go wrong, rather than expecting them to go right.",
        "lowers",
    ),
    "appraisal_orientation": (
        "Challenge or threat",
        "Is the event an opportunity to take, or a danger to survive?",
        "inert",
    ),
    "attentional_focus": (
        "Where attention sits",
        "On the job in hand, or on the crowd, the rivals and the result.",
        "inert",
    ),
    "coping_style": (
        "How pressure is handled",
        "Facing it with a plan and routine, or avoiding and shutting it out.",
        "inert",
    ),
    "motivation_orientation": (
        "What drives them",
        "Chasing something good, or dodging something bad.",
        "inert",
    ),
}

DIRECTION_PLAIN: dict[str, str] = {
    "raises": "pushes the number up",
    "lowers": "pulls the number down",
    "inert": "shown, but counted as zero",
}

# ---------------------------------------------------------------------------
# Section explainers
# ---------------------------------------------------------------------------

CHART_LEFT_PLAIN = (
    "How much each signal moved the final number. Bars to the right of the line pushed it "
    "up, bars to the left pulled it down. The four inert signals sit on the line with a "
    "hatched box: detected, but counted as nothing."
)

CHART_RIGHT_PLAIN = (
    "How strongly each signal was picked up in the words, before any weighting. A signal "
    "can be picked up loud and clear here and still move the final number by nothing, "
    "if it is one of the inert four."
)

SPANS_PLAIN = (
    "The receipts. For each signal that was detected, the exact words that triggered it. "
    "This is the part a coach should read first, because the number is only as good as the words "
    "underneath it."
)

TWO_TABS_PLAIN = (
    "**Known examples** replays results that were computed once, saved, and committed to "
    "the repository, so anyone re-running this gets the identical picture. **Score your "
    "own text** runs a simpler word-list scorer live in this session; it is weaker, and "
    "the yellow box on that tab says by how much."
)

WATERFALL_PLAIN = (
    "The ten signals are not averaged. Each detected one adds its own weighted push to a "
    "running total, and the total is then squeezed into the 0-to-1 range by an S-curve. "
    "That last step is why pushes adding up to +1.9 come out as 0.87 rather than 1.9: "
    "the curve flattens as it approaches the ends, so a very strained text and an "
    "extremely strained one both land near 0.9."
)

COVERAGE_PLAIN = (
    "Two bars on the same scale: this text, and the whole synthetic corpus. The hatched "
    "part is pushes the system could not back up with words. If the hatched part is most "
    "of the bar (and corpus-wide it is 104 of 120), the explanation layer is weaker than "
    "the number it explains. That comparison is here so nobody has to take our word for "
    "it being typical."
)

BENCHMARK_PLAIN = (
    "How well the detector agrees with the labels planted in the synthetic text. The "
    "word-list floor is what the live tab runs; the trained model is what the paper "
    "reports. Both are on the honest split, where the sentence patterns in the test set "
    "were never seen during training. The third bar is the same model on patterns it had "
    "seen: taller, and not a result to quote."
)

PER_CONSTRUCT_PLAIN = (
    "The single 0.588 figure is an average over ten signals, and the ten are not "
    "detected equally well. Attention and worry are the hardest; burnout is the one "
    "place where the trained model does no better than the dumb word list. Read the "
    "weak rows as a warning about the signals above, not as a footnote."
)

POLICY_PLAIN = (
    "The switch above changes how the four two-sided signals are counted, and it is the "
    "most honest thing on this page. Paste a text about attention and coping, then move "
    "the switch: the same words can read as 0.50, 0.98 or 0.02 depending purely on a "
    "guess the system is not entitled to make. That is why the default refuses to guess "
    "and every number in the paper uses it."
)

NON_DEFAULT_POLICY_EXPORT = (
    "The committed card is not shown under a non-default policy. That card is the "
    "paper's figure and it was produced under the conservative default; showing it "
    "beside numbers computed another way would imply the paper reports those numbers. "
    "Switch back to the default to see it."
)

# ---------------------------------------------------------------------------
# The two pages
# ---------------------------------------------------------------------------

ANNOUNCEMENT = (
    "Synthetic text only. Not a clinical instrument, and no claim about any identifiable person."
)

PAGE1_TITLE = "Ten signals, read from what an athlete wrote"
PAGE1_LEDE = (
    "Each tile below is one psychological signal the system looks for, showing only its "
    "numbers: how strongly it was detected, and how far it moved the overall index. "
    "Open any tile for the words behind it and what the number means."
)
PAGE1_GRID_LABEL = "Detected signals, strongest first"
PAGE1_OPEN_CTA = "Open explanation"

PAGE2_TITLE = "Score my own text"
PAGE2_LEDE = (
    "Paste anything an athlete wrote or said before a competition. It is scored in this "
    "browser session by the word-list baseline, shown back to you, and then forgotten. "
    "Nothing is stored, logged or cached."
)
# ---------------------------------------------------------------------------
# Phase 27: photo and video upload
# ---------------------------------------------------------------------------

MEDIA_UPLOAD_LABEL = "Or upload a photo or a short video instead"

MEDIA_PLAIN = (
    "A photo of something an athlete wrote, or a clip of them speaking. The words are "
    "read out of the file and then scored exactly as typed words are, by the same "
    "word-list scorer, under the same setting. The picture itself is not scored."
)

OFF_TOPIC_HEADLINE = "This does not read as an athlete talking about themselves."

OFF_TOPIC_PLAIN = (
    "The score below is still shown, and it is arithmetically what the word-list "
    "scorer makes of these particular words. What it is not is a reading of an "
    "athlete before a competition, so nothing about it should be carried into a "
    "conversation about a person."
)

#: Reported wherever the register test is explained, because a gate with no
#: number behind it is the thing this project spends ten modules refusing to
#: ship. Dev is the split the weights were chosen on; eval was untouched until
#: the weights were fixed. See tests/test_relevance.py.
RELEVANCE_MEASURED = (
    "The register test was fitted on the development split and reported on a "
    "held-out split it had never seen: it recognises 85% of the corpus's athlete "
    "utterances (340 of 400) and passes 1 of 20 authored off-topic texts. The "
    "off-topic texts were written by this project for the test, so that second "
    "figure is a sanity check rather than an estimate of what real uploads do."
)

MEDIA_REJECTED = "Nothing was scored from that file."

MEDIA_MACHINE_READ = (
    "These words were recovered from the file by a decoder. Recovery is imperfect, so "
    "check them against what was actually written before reading anything into the "
    "score below."
)

NONVERBAL_SWITCH_LABEL = "Let the face and voice channel move the score"

#: Phase 28 replaced the switch with the consent box above: facial cues now
#: always count when a face was actually read. The string stays because the
#: simulated three-value reading still appears when no face could be read.

NONVERBAL_OFF_PLAIN = (
    "Off. A non-verbal reading is taken from the file and shown, at a weight of "
    "exactly zero: the score comes from the words alone and is identical to the score "
    "those same words would get with nothing attached."
)

NONVERBAL_ON_PLAIN = (
    "On. Values taken from the file now move the score. Reading a state of mind off a "
    "face is not something the research supports doing reliably, the values here are "
    "generated rather than measured, and the weighting is a choice rather than a "
    "finding. Nothing produced this way belongs in the paper."
)

# ---------------------------------------------------------------------------
# Phase 28: facial cues, under consent, in the score
# ---------------------------------------------------------------------------

CONSENT_LABEL = "The face in this file is mine, or the person shown agreed to this"

CONSENT_PLAIN = (
    "Tick this only if it is true. With it ticked, the largest face in an uploaded "
    "photo is read for two things: how negative the expression looks and how "
    "activated it looks. Both go into the score. Nothing is stored, and the picture "
    "is dropped as soon as the page has finished drawing. Leave it unticked and "
    "nothing looks at the face at all."
)

FACE_CUES_HEADLINE = "What the face in the picture looks like"

#: The limitation `docs/ethics.md` sec.14 requires beside every face number. It is
#: rendered above the score and outside any expander, like the register flag, so
#: that it survives being screenshotted with the figure it qualifies.
FACE_CUES_LIMITATION = (
    "An expression is not a feeling. Research does not support reading a person's "
    "state of mind reliably from their face, and a competitor mid-effort looks "
    "strained for reasons that have nothing to do with how they are coping. These "
    "two values describe the picture, they carry a small weight that was chosen by "
    "hand rather than learned from outcomes, and nothing produced this way belongs "
    "in a conversation about a person."
)

FACE_CUES_MEASURED = (
    "A face was found and read. The two values below moved the score; the "
    "text-only score is shown beside it so you can see by how much."
)

FACE_CUES_NOT_MEASURED = (
    "No face was read, so the score below comes from the words alone. The three "
    "values shown are generated from the file's bytes to demonstrate the interface "
    "and are weighted as zero."
)

FACE_ONLY_HEADLINE = "Read from the face alone"

FACE_ONLY_PLAIN = (
    "There was nothing written in this picture, so the ten psychological signals could "
    "not be looked for and there are no words to point at. The figure below comes only "
    "from how the photographed expression looks, under weights chosen by hand. It is "
    "not the risk index and it is not a reading of the person."
)

FACE_ONLY_FIGURE_LABEL = "Face-only figure, out of 100"

FACE_TEXT_ONLY_LABEL = "Words only"

FACE_COMBINED_LABEL = "Words and face"

# ---------------------------------------------------------------------------
# Phase 29: the match-day profile (photograph + press conference)
# ---------------------------------------------------------------------------

MATCHDAY_TITLE = "One profile from a picture and a press conference"

MATCHDAY_LEDE = (
    "Paste a link to a press conference and, if you have one, add a photograph. The "
    "words are taken from the video's own captions, names are replaced with "
    "placeholders, and then they are scored exactly as typed words are. The picture "
    "adds two values describing how the expression looks. Nothing is stored."
)

MATCHDAY_LINK_LABEL = "Link to a press conference"

MATCHDAY_PHOTO_LABEL = "A photograph of the athlete (optional)"

MATCHDAY_SUBMIT = "Build the profile"

MATCHDAY_EMPTY = "Add a link, a photograph, or both, then press the button."

MATCHDAY_WORKING = "Reading the press conference, this can take a moment."

MATCHDAY_NOTHING = "Nothing was scored."

MATCHDAY_READ_BY = "by {route}"

MATCHDAY_NO_FACE = "No photograph was read, so this score comes from the words alone."

MATCHDAY_DEID_NOTE = (
    "Names and other identifying items were replaced before scoring: {count} "
    "replacement(s). What was scored is the de-identified text, not the original."
)

#: Shown instead of a score when `gibberish.admit` refuses the input.
#:
#: A heading, not the whole message: the specific reason comes from the
#: `TextAdmission` that refused it, so the reader is told which property failed
#: rather than being handed a generic rejection twice.
PAGE2_REJECTED = "Nothing was scored, because this is not something the scorer can read."

#: The second line, always shown with the reason. It exists to say the thing a
#: refusal most needs to say: that the absence of a number is the correct
#: answer here, not a failure of the app. A user who thinks the app broke will
#: paste the same string again.
PAGE2_REJECTED_WHY = (
    "The scorer reads words. Given something that is not words it would still "
    "produce a number, and that number would sit at the middle of the scale for "
    "no reason other than that nothing matched. Refusing is the honest answer."
)

PAGE2_SUBMIT = "Score this text"
PAGE2_EMPTY = "Nothing to score yet. Paste a few sentences above."

SCALE_NOTE_TEXT = (
    "The 0-100 figure is the risk index multiplied by 100, nothing more. It is not a "
    "percentage and not a probability: it orders texts, and carries no meaning on its own."
)

DETAIL_INTRO = (
    "Everything behind one tile: what the signal is, the words that triggered it, what "
    "it did to the index, and how well the detector handles this particular signal."
)

DIMENSIONS_NOTE = (
    "The ten dimensions are the constructs the taxonomy defines, each taken from an "
    "established sports-psychology questionnaire. Detection strength runs 0 to 1; the "
    "push is what that detection did to the index under the policy in force."
)

# ---------------------------------------------------------------------------
# Jargon, mapped back to the paper
# ---------------------------------------------------------------------------

GLOSSARY: tuple[tuple[str, str], ...] = (
    (
        "Construct",
        "One of the ten psychological signals. Called a construct because each one comes "
        "from an established sports-psychology questionnaire rather than being invented "
        "here.",
    ),
    (
        "Risk index",
        "The single 0-to-1 number. A weighted sum of the six directional signals.",
    ),
    (
        "Not calibrated / ranking only",
        "We never observed what actually happened to these athletes, so the number cannot "
        "be tied to a real-world rate. It orders texts; it does not estimate a chance.",
    ),
    (
        "Inert construct",
        "A signal that was detected but given a weight of zero, because whether it is good "
        "or bad news depends on a direction the system has not resolved.",
    ),
    (
        "Span",
        "A stretch of the actual text that the explanation points at as evidence.",
    ),
    (
        "Unevidenced driver",
        "A signal that moved the number with no span behind it.",
    ),
    (
        "Lexicon baseline",
        "The simple keyword-matching scorer used on the live tab. The deliberate floor the "
        "trained model is compared against.",
    ),
    (
        "macro-F1",
        "A single score for how well a detector agrees with the labels it is graded "
        "against, averaged evenly over all ten signals so a rare one counts as much as a "
        "common one. 0.462 for the word-list floor, 0.588 for the trained model.",
    ),
    (
        "PROVISIONAL stamp",
        "The grey line under every number. It says the number is agreement with labels "
        "this project planted in synthetic text: a property of the corpus, not "
        "performance on real athletes.",
    ),
    (
        "OPEN-011 / OPEN-021 / OPEN-025",
        "Open issues tracked in the repository: no real athlete text yet, the word-list "
        "scorer shares its vocabulary with the corpus generator, and the human-verified "
        "set is still empty.",
    ),
)

READ_FIRST = "New here? Read this first"
GLOSSARY_TITLE = "Every technical term on this page, in plain English"

# ---------------------------------------------------------------------------
# Phase 26 / V1, the brain atlas
#
# These strings are screened twice. `_screen()` below catches the vocabulary
# this whole module is forbidden, and `neurovis.assert_no_activation_vocabulary`
# catches the vocabulary that is forbidden only here -- the words that would
# turn a hypothesis drawn from text into a claim about a scan. The second screen
# runs over the rendered panel rather than over this module, because a caption
# is only dangerous once it is next to the picture.
#
# Register check for every line below: it has to survive being read by somebody
# who looked at the figure first and the words second, which is the order every
# reader actually uses.
# ---------------------------------------------------------------------------

ATLAS_TITLE = "Where these signals are usually talked about"

# Kept short on purpose. The panel is looked at, not read: a reader glances at
# the figure and takes maybe one line of text with it. Long paragraphs here were
# scrolled past, which made the caveats less visible rather than more.
ATLAS_PLAIN = (
    "The same ten signals from the dashboard, placed on a brain sketch instead of a bar "
    "chart. Nothing new was detected and nothing was scanned."
)

#: The exact wording the Phase 26 gate turns on. Quoted verbatim or not at all.
ATLAS_CAVEAT = "hypothesised association, not imaging"

ATLAS_WHAT_IT_IS_NOT = "No one here was scanned. The dots move only when the words change."

ATLAS_HOW_TO_READ = (
    "Bigger dot, picked up more strongly. Warm pushes the index up, dark green pulls it "
    "down, hollow dashed is counted as zero. Lines join signals in the same network."
)

ATLAS_UNMAPPED_PLAIN = "Left off the sketch on purpose"

ATLAS_TILE_LABEL = "Networks engaged"
ATLAS_TILE_CAPTION = "signals with a place on the sketch"

#: (caption, swatch key). The second element is a CSS class suffix, not prose.
#:
#: It was prose once ("warm", "hollow, dashed") and the renderer derived the
#: class from its first word, which produced `sw-hollow,` and four swatches that
#: silently did not render. Every unit test stayed green -- the strings were all
#: present in the document. Only the screenshot showed it.
ATLAS_LEGEND: tuple[tuple[str, str], ...] = (
    ("pushes up", "raise"),
    ("pulls down", "lower"),
    ("counted as zero", "inert"),
    ("no place on the sketch", "unmapped"),
)

ATLAS_EVIDENCE_HEADING = "Row by row"

ATLAS_ANCHOR_NOTE = (
    "The reference is the questionnaire the signal comes from. It says nothing about the "
    "part of the brain beside it."
)


# ---------------------------------------------------------------------------
# Phase 26 / V3, cognitive load
# ---------------------------------------------------------------------------

LOAD_TITLE = "Cognitive load, from a simulated body"

LOAD_PLAIN = (
    "Heart-rate variability from a chest strap and pupil and blink behaviour from a "
    "webcam, except that there is no strap and no webcam. Every trace here was generated."
)

#: The wording the V3 gate turns on: the same footing as the risk meter.
LOAD_NOT_CALIBRATED = "ranking only, not calibrated"

LOAD_HOW_TO_READ = (
    "The meter orders windows from calmer to more strained. It has no bands and no "
    "thresholds, because nothing in this project could set one."
)

LOAD_WEIGHTS_NOTE = (
    "The three channels are combined with fixed weights written into the code and stated "
    "below. Nothing was fitted, because there is no outcome in this project to fit against."
)

LOAD_CHANNELS: tuple[tuple[str, str, str], ...] = (
    ("hf_hrv", "Heart-rate variability", "beat-to-beat variation in the high-frequency band"),
    ("pupil_effort", "Pupil effort", "average pupil size against its own baseline"),
    ("blink_rate", "Blink rate", "blinks per minute"),
)

LOAD_TILE_LABEL = "Load index"
LOAD_TILE_CAPTION = "ranking only, not calibrated"

LOAD_WHAT_IT_IS_NOT = (
    "Nobody was recorded. Wearing a real strap would put this in a different privacy "
    "class and needs the ethics document updated first."
)

# ---------------------------------------------------------------------------
# Phase 26 / V5, closed-loop neurofeedback, demo mode
# ---------------------------------------------------------------------------

NF_TITLE = "Neurofeedback loop (demo)"

#: Rendered before the first control on the page, in red. Not negotiable: a
#: closed feedback loop changes the behaviour of the person inside it, which
#: makes it an intervention rather than an observation.
NF_DEMO_ONLY = (
    "DEMO MODE: the loop is closing against a generated signal and nobody is being "
    "trained. No headset is attached and no person is in this loop."
)

NF_ETHICS_GATE = (
    "Before this runs against any person it needs ethics approval and a clinician in the "
    "loop, and the ethics and model-card documents updated first. The page refuses to "
    "render for anything but a generated source."
)

NF_PLAIN = (
    "The ring grows while the generated signal holds above its target and shrinks when it "
    "drifts. That is the whole mechanism a real attention-training session uses."
)

NF_HOW_TO_READ = (
    "Dashed circle is the target. Solid ring is the current value. The counters below are "
    "session arithmetic over the ticks so far, nothing more."
)

NF_TILE_LABEL = "Time in target"
NF_TILE_CAPTION = "of the last demo session"

# ---------------------------------------------------------------------------
# Phase 26 / V3, narrated, a spoken clip with the simulated body under it
# ---------------------------------------------------------------------------

NARRATED_TITLE = "Listen, and watch the simulated body follow"

NARRATED_PLAIN = "Press play. The heart rate, pupil and blinks below move as the words go by."

#: Rendered in red, above the trace, on every render. The panel is one step away
#: from looking like a recording of a person reacting to their own words.
NARRATED_VOICE_NOTE = (
    "SYNTHETIC SPEECH over SYNTHETIC TEXT. Nobody was recorded. The words came "
    "from this project's own generator and the voice is a speech synthesiser."
)

NARRATED_IMPOSED = (
    "The body follows the words because this code told it to. The text model's "
    "signals drive the simulator: the arrow runs words to body, and it was drawn "
    "by us. It is not evidence that any real body agreed with any real text."
)

NARRATED_NO_HRV = (
    "Heart-rate variability is not shown here. A clip this short holds about a "
    "dozen beats, which is too few for any variability figure to mean anything, "
    "and a rate that is changing makes it worse, not better. The 60-second view "
    "on this page reports it; this one does not."
)

NARRATED_WHAT_IT_IS_NOT = (
    "A phrase the model could point to words for makes a bump. A signal it could "
    "not makes a flat lift across the whole clip instead, because it belongs to "
    "no moment in particular."
)

NARRATED_MISSING = (
    "The spoken clips are committed assets and are not on disk. Rebuild them with "
    "`python scripts/build_narration.py`, which needs espeak-ng and ffmpeg, neither "
    "of which the app itself requires."
)


def _screen() -> None:
    """Screen every string this module publishes, at import.

    Deliberately reflective over the module namespace rather than a hand-written
    list: a caption added next month is screened without anyone remembering to
    add it here, which is the only version of this check that stays true. Same
    argument as `DashboardView.render_text` -- screen the surface, not a
    template.
    """
    for name, value in list(globals().items()):
        if name.startswith("_"):
            continue
        for chunk in _strings(value):
            assert_no_forbidden_language(chunk)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for k, v in value.items():
            out.extend(_strings(k))
            out.extend(_strings(v))
        return out
    if isinstance(value, (tuple, list)):
        out = []
        for item in value:
            out.extend(_strings(item))
        return out
    return []


_screen()
