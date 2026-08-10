"""De-identification -- the implementation of `docs/ethics.md` sec.5.1.

The spec was written at Phase 5, before any data existed, and it is not
redesigned here. This module implements the removal table exactly as written:
typed placeholders for identifiers, and health detail **removed entirely**
rather than placeholdered.

---

## Three properties this module is built to have

**1. Typed, not blanked.** `[COACH]` and `[OPPONENT]` are different tokens
because they carry different meaning. `docs/ethics.md` sec.5.2 is explicit that
blanking "destroys the linguistic structure the model needs" -- and the
structure is the point here, not a nicety. "I'm worried about what [COACH]
thinks" and "I'm worried about what [OPPONENT] does" express different
constructs, and a de-identifier that renders both as `[REDACTED]` deletes the
distinction the classifier exists to learn.

**2. Irreversible, by construction.** There is no mapping table, no salt, no
reversible hash, and no parameter that would produce one. `docs/ethics.md`
sec.5.2 rules the mapping out of scope, and the honest way to enforce that is
for the code to have nowhere to put one. What comes back is text and counts.

**3. Fail-visible rather than fail-quiet.** `DeidReport.residual_flags` lists
things the module *suspects* it got wrong -- a surviving capitalised unknown
token, an unusually long digit run. A de-identifier that reports only what it
removed cannot be audited, because a perfect score and a broken regex look
identical from the outside.

---

## What this is not

It is not NER, and it is not a PII detection system in the commercial sense.
It is an ordered cascade of lexicon-and-cue rules, chosen over a statistical
model for the reason given in `docs/data_sources.md` sec.2: everything in this
pipeline has to run offline, deterministically, from a fresh clone, with no
model download and no API key (OPEN-008).

The cost of that choice is real and is stated rather than hidden. Rule cascades
miss nicknames they have no cue for, names that collide with ordinary words,
and any language the lexicons do not cover. `docs/ethics.md` sec.5.3 already
names residual re-identification risk as a limitation of the project; this
module is one of the reasons that sentence has to stay in the paper.

**Measured, not asserted.** `audit.py` scores this module against
`tests/fixtures/deid_cases.jsonl` and reports precision, recall, and exact
match per difficulty band. The fixture exists because the synthetic corpus
contains no names, so running the de-identifier over `data/raw/` would pass the
Phase 8 gate while measuring nothing (OPEN-013).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicons import (
    AMBIGUOUS_HEALTH_TERMS,
    BODY_PARTS,
    COMMON_WORDS,
    EVENT_SUFFIXES,
    HEALTH_CUES,
    LOCATION_CUES,
    MEASUREMENT_UNITS,
    MEDICATION_TERMS,
    MONTH_ABBREVIATIONS,
    MONTHS,
    OPPONENT_CUES,
    ORDINAL_WORDS,
    ORG_SUFFIXES,
    ROLE_NOUNS,
    ROLE_PLACEHOLDER,
    SPEECH_VERBS,
    SPORT_WORDS,
    STRONG_HEALTH_TERMS,
    TEAM_SUFFIXES,
    TITLES,
    VENUE_SUFFIXES,
    WEEKDAYS,
)

# ---------------------------------------------------------------------------
# Placeholder vocabulary
# ---------------------------------------------------------------------------

#: Every placeholder this module can emit. Named once so that the audit, the
#: tests, the annotation guidelines, and the dashboard all agree on the set --
#: an undocumented placeholder appearing in the corpus would be an unexplained
#: token that annotators have no rule for.
PLACEHOLDERS: tuple[str, ...] = (
    "[ATHLETE]",
    "[COACH]",
    "[TEAMMATE]",
    "[OPPONENT]",
    "[PERSON]",
    "[HANDLE]",
    "[CONTACT]",
    "[URL]",
    "[TEAM]",
    "[ORG]",
    "[LOCATION]",
    "[EVENT]",
    "[EVENT_WINDOW]",
    "[ID]",
)

PLACEHOLDER_RE = re.compile(r"\[[A-Z_]+\]")

#: Private-use sentinels. A replacement is locked behind these immediately so
#: that a later pass cannot match inside text this pass already redacted --
#: which is how a `[HANDLE]` becomes a `[PERSON]` containing a `[HANDLE]`.
#: Private-use codepoints are category Co: `\w`, `[A-Z]`, and `\d` all decline
#: to match them, so they behave as inert separators.
_LOCK_OPEN = ""
_LOCK_CLOSE = ""
_LOCK_RE = re.compile(r"(\d+)")

#: "Not whitespace and not a sentinel" -- used wherever `\S` would otherwise
#: swallow an already-locked replacement.
_NS = r"[^\s]"

#: Words that never begin a proper-noun candidate.
_SAFE_WORDS = COMMON_WORDS | SPORT_WORDS | WEEKDAYS | frozenset(MONTHS) | ROLE_NOUNS

#: A capitalised token. The segment after a hyphen or apostrophe must itself be
#: capitalised, so "Okonkwo-Bright" and "O'Neill" are single tokens while the
#: clitic in "I'm" is not swept in -- which would otherwise make "I'm" an
#: unknown capitalised token and therefore a name candidate in every record.
_CAP_TOKEN = r"[A-Z][A-Za-z]*(?:[-'][A-Z][A-Za-z]*)*"
_CAP_RUN_RE = re.compile(rf"{_CAP_TOKEN}(?:[ ]{_CAP_TOKEN})*")


@dataclass
class DeidReport:
    """What de-identification did to one text, and what it is unsure about."""

    replacements: dict[str, int] = field(default_factory=dict)
    health_clauses_removed: int = 0
    residual_flags: list[str] = field(default_factory=list)

    @property
    def total_replacements(self) -> int:
        return sum(self.replacements.values())

    @property
    def changed(self) -> bool:
        return self.total_replacements > 0 or self.health_clauses_removed > 0

    def count(self, placeholder: str) -> None:
        self.replacements[placeholder] = self.replacements.get(placeholder, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "replacements": dict(sorted(self.replacements.items())),
            "total_replacements": self.total_replacements,
            "health_clauses_removed": self.health_clauses_removed,
            "residual_flags": list(self.residual_flags),
        }


class _Locker:
    """Holds replacements outside the working text until every pass is done."""

    def __init__(self, report: DeidReport) -> None:
        self.slots: list[str] = []
        self.report = report

    def lock(self, placeholder: str) -> str:
        self.report.count(placeholder)
        self.slots.append(placeholder)
        return f"{_LOCK_OPEN}{len(self.slots) - 1}{_LOCK_CLOSE}"

    def unlock(self, text: str) -> str:
        return _LOCK_RE.sub(lambda m: self.slots[int(m.group(1))], text)


# ---------------------------------------------------------------------------
# Pass 1 -- health detail, removed entirely
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_CLAUSE_SPLIT_RE = re.compile(r"\s+(?:and|but)\s+|\s*;\s*")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")


def _health_trigger(clause: str) -> str | None:
    """Return the health term that makes `clause` health data, or None."""
    words = {w.lower() for w in _WORD_RE.findall(clause)}
    strong = words & (STRONG_HEALTH_TERMS | MEDICATION_TERMS)
    if strong:
        return sorted(strong)[0]
    ambiguous = words & AMBIGUOUS_HEALTH_TERMS
    if ambiguous and (words & BODY_PARTS or words & HEALTH_CUES):
        return sorted(ambiguous)[0]
    return None


def remove_health_detail(text: str, report: DeidReport) -> str:
    """Delete every clause carrying health, injury, or treatment detail.

    Clause-level rather than sentence-level because sentence-level over-removes.
    "I upped my sertraline dose before the trial and I felt flat all week"
    contains one clause of special-category data and one clause of exactly the
    affective language this project studies; deleting both would be safer and
    would also be the wrong trade, since `docs/ethics.md` sec.5.2 requires
    preserving the linguistic structure that survives redaction.

    Clauses are split on coordinating conjunctions only, never on commas.
    Comma-splitting fragments ordinary sentences and produces ungrammatical
    residue, and ungrammatical residue is worse than a slightly wider deletion.
    """
    kept_sentences: list[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        if not sentence.strip():
            continue
        if _health_trigger(sentence) is None:
            kept_sentences.append(sentence.strip())
            continue

        clauses = _CLAUSE_SPLIT_RE.split(sentence)
        if len(clauses) == 1:
            report.health_clauses_removed += 1
            continue

        kept = [c for c in clauses if _health_trigger(c) is None]
        report.health_clauses_removed += len(clauses) - len(kept)
        if not kept:
            continue

        rebuilt = " and ".join(c.strip() for c in kept if c.strip())
        rebuilt = rebuilt.strip()
        if rebuilt and rebuilt[-1] not in ".!?":
            rebuilt += "."
        # A clause promoted to sentence-initial position keeps its own casing
        # unless it is now the first word and starts lowercase.
        if rebuilt and rebuilt[0].islower():
            rebuilt = rebuilt[0].upper() + rebuilt[1:]
        kept_sentences.append(rebuilt)

    return " ".join(kept_sentences).strip()


# ---------------------------------------------------------------------------
# Pass 2 -- contact details
# ---------------------------------------------------------------------------

_URL_RE = re.compile(rf"\b(?:https?://|www\.){_NS}+", re.IGNORECASE)
_EMAIL_RE = re.compile(rf"\b{_NS}+@{_NS}+\.{_NS}{{2,}}\b")
_AT_HANDLE_RE = re.compile(r"@[A-Za-z0-9][A-Za-z0-9_.]{1,}")
#: The lookahead stops at a sentence-final period but not at an internal one.
#: A naive `[\s,.;!?]` boundary splits `k.mensah_07` after the first character
#: and emits two placeholders where one identifier stood.
_HANDLE_CUE_RE = re.compile(
    rf"\b(username|handle|tag|account|nickname)\s+(?:was|is)\s+({_NS}+?)"
    rf"(?=[\s,;!?]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)
#: A bare token shaped like a username: letters and digits joined by an
#: underscore or an internal dot. Deliberately narrow -- a looser rule starts
#: eating decimals and abbreviations.
_HANDLE_SHAPE_RE = re.compile(r"\b(?=[a-z0-9._]*[0-9])[a-z][a-z0-9]*[._][a-z0-9._]*[a-z0-9]\b")
#: A digit run long enough to be a phone number. Counted rather than matched
#: exactly, because phone formatting varies by country and an exact pattern
#: per country is a maintenance trap.
_DIGIT_RUN_RE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{5,}\d(?![\w])")
_MIN_PHONE_DIGITS = 9


def _replace_contacts(text: str, locker: _Locker) -> str:
    text = _URL_RE.sub(lambda _: locker.lock("[URL]"), text)
    text = _EMAIL_RE.sub(lambda _: locker.lock("[CONTACT]"), text)

    def _phone(match: re.Match[str]) -> str:
        digits = sum(c.isdigit() for c in match.group(0))
        if digits < _MIN_PHONE_DIGITS:
            return match.group(0)
        return locker.lock("[CONTACT]")

    text = _DIGIT_RUN_RE.sub(_phone, text)
    text = _AT_HANDLE_RE.sub(lambda _: locker.lock("[HANDLE]"), text)
    text = _HANDLE_CUE_RE.sub(lambda m: f"{m.group(1)} was {locker.lock('[HANDLE]')}", text)
    text = _HANDLE_SHAPE_RE.sub(lambda _: locker.lock("[HANDLE]"), text)
    return text


# ---------------------------------------------------------------------------
# Pass 3 -- exact dates
# ---------------------------------------------------------------------------

_MONTH_ALT = "|".join([*MONTHS, *MONTH_ABBREVIATIONS])
_DATE_PATTERNS = (
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_ALT})\.?(?:\s+\d{{4}})?\b",
    rf"\b(?:{_MONTH_ALT})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
    # Slash and dot forms only. A hyphenated `6-4` is a set score in half the
    # sports in this corpus, and redacting scores would delete competitive
    # context that the risk index has to be read against.
    r"\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b",
)
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)
_ON_DATE_RE = re.compile(rf"\bon\s+(?:{'|'.join(_DATE_PATTERNS)})", re.IGNORECASE)


def _replace_dates(text: str, locker: _Locker) -> str:
    """Replace exact dates with `[EVENT_WINDOW]`.

    The preposition is adjusted with the placeholder: an exact date is a point
    ("on 14 March") but the replacement names a period, so "on" becomes "in".
    Leaving "on [EVENT_WINDOW]" would be ungrammatical, and ungrammatical
    residue is a problem for a corpus whose labels are linguistic judgements.
    """
    text = _ON_DATE_RE.sub(lambda _: f"in {locker.lock('[EVENT_WINDOW]')}", text)
    return _DATE_RE.sub(lambda _: locker.lock("[EVENT_WINDOW]"), text)


# ---------------------------------------------------------------------------
# Pass 4 -- named entities and people
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(rf"\b({'|'.join(TITLES)})\.?\s*$", re.IGNORECASE)
_YEAR_PREFIX_RE = re.compile(r"\b(\d{4})\s+$")
_ROLE_NAME_RE = re.compile(
    rf"\b(my|our|the)\s+({'|'.join(sorted(ROLE_NOUNS))})\s+([a-z][a-z'-]{{1,}})\b"
)


def _previous_word(text: str, start: int) -> str:
    before = text[:start].rstrip()
    match = re.search(r"([A-Za-z][A-Za-z'-]*)$", before)
    return match.group(1).lower() if match else ""


def _word_before_previous(text: str, start: int) -> str:
    before = text[:start].rstrip()
    match = re.search(r"([A-Za-z][A-Za-z'-]*)\s+[A-Za-z][A-Za-z'-]*$", before)
    return match.group(1).lower() if match else ""


def _next_words(text: str, end: int, count: int = 2) -> list[str]:
    after = text[end:]
    return [w.lower() for w in _WORD_RE.findall(after)[:count]]


def _at_sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip()
    return not before or before[-1] in ".!?\n"


def _classify_run(text: str, start: int, end: int, tokens: list[str]) -> tuple[str, int, bool]:
    """Decide what a capitalised run is.

    Returns `(placeholder, span_start, cued)`.

    `span_start` may reach further left than the run itself, to swallow a
    title ("Coach Renner" -> `[COACH]`) or an event year ("2025 Coastal
    Series" -> `[EVENT]`).

    `cued` says whether the decision rests on positive evidence -- a suffix, a
    title, a role noun, a grammatical frame -- or on the bare fact that the
    word was capitalised and unrecognised. The caller needs the distinction:
    unrecognised-and-capitalised is weak enough evidence that it must not fire
    on a sentence opener, but a cue is strong enough that it should.
    """
    lower = [t.lower() for t in tokens]

    # Entity type by suffix. Requires two tokens: a bare "Arena" with nothing
    # in front of it names no venue.
    if len(tokens) >= 2:
        last = lower[-1]
        if last in VENUE_SUFFIXES:
            return "[LOCATION]", start, True
        if last in EVENT_SUFFIXES:
            year = _YEAR_PREFIX_RE.search(text[:start])
            return "[EVENT]", year.start(1) if year else start, True
        if last in TEAM_SUFFIXES:
            return "[TEAM]", start, True
        if last in ORG_SUFFIXES:
            return "[ORG]", start, True

    title = _TITLE_RE.search(text[:start])
    if title:
        role = title.group(1).lower()
        return ROLE_PLACEHOLDER.get(role, "[PERSON]"), title.start(1), True

    previous = _previous_word(text, start)
    if previous in ROLE_NOUNS:
        return ROLE_PLACEHOLDER.get(previous, "[PERSON]"), start, True
    if previous in OPPONENT_CUES:
        return "[OPPONENT]", start, True
    if previous in LOCATION_CUES:
        return "[LOCATION]", start, True
    if (
        previous in {"to", "in", "at", "from", "near"}
        and _word_before_previous(text, start) in LOCATION_CUES
    ):
        return "[LOCATION]", start, True

    following = _next_words(text, end)
    if following[:2] in (["and", "i"], ["and", "me"]):
        return "[TEAMMATE]", start, True
    if following and following[0] in SPEECH_VERBS and len(tokens) >= 2:
        # Third-person attribution of speech to a full name is the press-report
        # convention for naming the subject athlete. Two tokens are required:
        # "Renner said" alone is more likely a coach or an official.
        return "[ATHLETE]", start, True

    return "[PERSON]", start, False


def _replace_entities(text: str, locker: _Locker) -> str:
    """Replace capitalised proper-noun runs, typed by context."""

    # Lowercase names first: they are invisible to the capitalisation rule and
    # only a role cue can find them. `docs/ethics.md` sec.5.2 warns that
    # automated de-identification misses "nicknames, in-group references, and
    # unusual spellings" -- informal lowercase text is where that bites.
    def _role_name(match: re.Match[str]) -> str:
        determiner, role, candidate = match.group(1), match.group(2), match.group(3)
        if candidate in COMMON_WORDS or candidate in SPORT_WORDS or candidate in ROLE_NOUNS:
            return match.group(0)
        placeholder = ROLE_PLACEHOLDER.get(role, "[PERSON]")
        return f"{determiner} {role} {locker.lock(placeholder)}"

    text = _ROLE_NAME_RE.sub(_role_name, text)

    # Capitalised runs, rightmost first so that earlier spans keep their offsets.
    for match in reversed(list(_CAP_RUN_RE.finditer(text))):
        tokens = match.group(0).split(" ")
        start, end = match.span()

        # Trim leading safe words ("The Aldermere Invitational", "Coach Renner").
        while tokens and tokens[0].lower() in _SAFE_WORDS:
            start += len(tokens[0]) + 1
            tokens = tokens[1:]
        # Trim trailing safe words ("Karlsholm Monday" -> "Karlsholm").
        while tokens and tokens[-1].lower() in _SAFE_WORDS:
            end -= len(tokens[-1]) + 1
            tokens = tokens[:-1]
        if not tokens:
            continue

        placeholder, span_start, cued = _classify_run(text, start, end, tokens)

        # A single capitalised word opening a sentence is the sentence opener,
        # not evidence of a name -- unless something else in the sentence says
        # otherwise. "Mark my words" stays; "Nadia and I have trained together"
        # does not, because "X and I" is a frame that only a person fills.
        if not cued and len(tokens) == 1 and _at_sentence_start(text, start):
            continue

        text = text[:span_start] + locker.lock(placeholder) + text[end:]

    return text


# ---------------------------------------------------------------------------
# Pass 5 -- quasi-identifiers
# ---------------------------------------------------------------------------

_ORDINAL_ALT = "|".join(sorted(ORDINAL_WORDS)) + r"|\d{1,2}(?:st|nd|rd|th)"
_JERSEY_RE = re.compile(r"\b(?:number|no\.|#)\s*\d{1,3}\b", re.IGNORECASE)
_PLACING_RE = re.compile(
    rf"\b(finish|finished|finishing|placed|placing|came|coming|ranked|seeded)\s+"
    rf"(?:no\.?\s*)?({_ORDINAL_ALT})\b",
    re.IGNORECASE,
)
_UNIQUENESS_RE = re.compile(
    r"\bthe only\b[^,.;]*?(?=\s+(?:in|on|at|from|to|with)\b|[,.;]|$)", re.IGNORECASE
)
_UNIT_AFTER_RE = re.compile(rf"^\s*({'|'.join(sorted(MEASUREMENT_UNITS))})\b", re.IGNORECASE)


def _replace_quasi_identifiers(text: str, locker: _Locker) -> str:
    """Replace jersey numbers, placings, and uniqueness claims with `[ID]`.

    `docs/ethics.md` sec.5.2: "Sport plus event plus finishing position can
    re-identify as surely as a name." The uniqueness rule is the one that
    matters most and is the least obvious -- "the only left-handed thrower in
    the national squad" contains no name and identifies exactly one person.

    A number followed by a unit is left alone. A split time is performance
    data, not an identifier, and redacting it would remove the competitive
    context a risk score has to be interpreted against.
    """

    def _jersey(match: re.Match[str]) -> str:
        if _UNIT_AFTER_RE.match(text[match.end() :]):
            return match.group(0)
        return locker.lock("[ID]")

    text = _JERSEY_RE.sub(_jersey, text)
    text = _PLACING_RE.sub(lambda m: f"{m.group(1)} {locker.lock('[ID]')}", text)
    text = _UNIQUENESS_RE.sub(lambda _: locker.lock("[ID]"), text)
    return text


# ---------------------------------------------------------------------------
# Residual-risk flags
# ---------------------------------------------------------------------------

_LONG_DIGIT_RE = re.compile(r"\b\d{5,}\b")


def _residual_flags(text: str) -> list[str]:
    """Things the cascade did not redact but a human should look at.

    This is the honest half of the module. Every flag is a case the rules could
    not resolve, surfaced for the stratified manual audit that
    `docs/ethics.md` sec.5.2 requires every phase that touches data.
    """
    flags: list[str] = []
    stripped = PLACEHOLDER_RE.sub(" ", text)
    for match in _CAP_RUN_RE.finditer(stripped):
        tokens = [t for t in match.group(0).split(" ") if t.lower() not in _SAFE_WORDS]
        if not tokens:
            continue
        if len(tokens) == 1 and _at_sentence_start(stripped, match.start()):
            continue
        flags.append(f"unresolved_capitalised_token:{' '.join(tokens)}")
    for match in _LONG_DIGIT_RE.finditer(stripped):
        flags.append(f"long_digit_run:{match.group(0)}")
    return flags


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def deidentify(text: str) -> str:
    """Return `text` with identifiers replaced by typed placeholders."""
    result, _ = deidentify_with_report(text)
    return result


def deidentify_with_report(text: str) -> tuple[str, DeidReport]:
    """De-identify and report what was replaced and what remains suspicious.

    Pass order is load-bearing and is not safe to shuffle:

    1. **health** first, so nothing is spent placeholdering text about to be
       deleted, and so a name inside a removed clause disappears with it;
    2. **contacts** before entities, because `marcus@example-club.org` must be
       one `[CONTACT]` rather than a `[PERSON]` glued to a domain;
    3. **dates** before quasi-identifiers, so `06/09` is a date rather than two
       numbers;
    4. **entities** before quasi-identifiers, so `Aldermere Invitational 2025`
       does not lose its year to a number rule first;
    5. **quasi-identifiers** last, on what survived.
    """
    report = DeidReport()
    if not text or not text.strip():
        return "", report

    locker = _Locker(report)
    working = remove_health_detail(text, report)
    working = _replace_contacts(working, locker)
    working = _replace_dates(working, locker)
    working = _replace_entities(working, locker)
    working = _replace_quasi_identifiers(working, locker)

    result = locker.unlock(working)
    result = re.sub(r"[ \t]{2,}", " ", result).strip()
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    report.residual_flags = _residual_flags(result)
    return result, report
