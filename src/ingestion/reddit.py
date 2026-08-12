"""Category A5 harvester -- topic-scoped pre-competition text from public forums.

Read `docs/ethics.md` §3.5 before this file. That section is authoritative, it
records the argument *against* this collection route as well as for it, and it
defines the eleven binding conditions (C1-C11) that this module exists to
enforce. Nothing here may be relaxed without amending that section first.

What this module does, and the one thing it structurally cannot do
------------------------------------------------------------------
It collects **posts matched by topic** -- a subreddit plus a pre-competition
query -- and turns them into `RawRecord`s.

It **cannot collect posts by author**, and that is enforced by the shape of the
code rather than by a check inside it. There is no author parameter anywhere in
this module's public surface: not on `HarvestQuery`, not on `harvest`, not on
`fetch_listing`. A caller who wants a user timeline cannot express the request.
That is condition **C1**, the load-bearing one, and it is the difference between
studying a discourse and profiling a person (`docs/ethics.md` §3.5).

A validation check would have been the obvious implementation. It was rejected:
a check can be deleted by a future session in one line and the deletion looks
like a cleanup. An absent parameter has to be *added back*, which is a visible
design change that shows up in review.

Why this route exists at all
----------------------------
Phase 7 established that **no public corpus of pre-competition athlete text
exists** -- all four surveyed candidates were post-match, which is the wrong
side of the event for an anticipatory taxonomy (`appraisal_orientation`,
anticipatory `cognitive_anxiety`). That is **OPEN-011**, the project's highest
live risk, because contribution #1 needs real athlete text.

Amateur endurance communities contain genuinely anticipatory pre-competition
writing. The owner amended prohibition P1 on 2026-08-11 to permit topic-scoped
collection from them as category A5. **P1 still prohibits account-centred
collection without exception.**

The honest caveat, restated here because a reader of this file should not have
to go looking for it: the original objection to social-media collection was that
*authors do not anticipate psychological profiling*. Pseudonymity, official API
use and amateur status address identifiability. **None of them addresses
anticipation of use.** A5 accepts a residual ethical cost rather than
eliminating one. `docs/ethics.md` §3.5.2 carries the full argument and the paper
must carry it too.

Fail closed, everywhere
-----------------------
Every exclusion below drops the post and writes a line to
`logs/ingestion_refusals.log`. There is no `--force`, no `strict=False`, no
`skip_checks`. The allow-list's enforcement contract says *"never add a bypass
flag to this checking path"* and that applies to this module in full.

Exclusions are deliberately **over-inclusive**. `is_health_content` will drop
posts that merely mention a niggle, and `mentions_minor` will drop an adult
writing about their kid's race. Both cost recall. Both are the right direction
of error: the cost of wrongly dropping a post is one lost record from a corpus
that has thousands of candidates, and the cost of wrongly keeping one is a
health disclosure or a minor's words in a psychological risk corpus. Those are
not comparable, so the thresholds are not balanced.

Offline by default
------------------
`harvest` takes an iterable of already-fetched posts. It performs no network
I/O. That keeps the whole filtering and provenance path unit-testable with no
credentials, no rate limit and no live dependency -- the lesson of OPEN-027,
where a parser that had never met its real input turned out to be broken in
three ways. `fetch_listing` is the thin, separately-tested network edge.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingestion.allowlist import SourceDescriptor, log_refusal
from src.ingestion.records import RawRecord

#: Communities permitted for A5 collection. An explicit list, not a parameter
#: with a default: adding a community is a governance decision (is it adult? is
#: it amateur? is it about competing rather than about injury?) and it should
#: require editing this file, where the question is visible in review.
#:
#: Deliberately excludes anything school-, college- or youth-scoped, because
#: P2 (minors) stands unweakened under A5 and an age filter applied post hoc is
#: much weaker than not collecting from a youth community in the first place.
PERMITTED_COMMUNITIES: tuple[str, ...] = (
    "running",
    "triathlon",
    "swimming",
    "climbing",
    "AdvancedRunning",
    "Marathon_Training",
    "rowing",
    "cycling",
)

#: Phrases that mark a post as anticipatory. A5's entire justification is that
#: this text is pre-competition, so a post that does not look forward to a
#: competition is out of scope regardless of how much construct language it
#: contains -- keeping it would quietly reintroduce the post-match problem that
#: disqualified all four Phase 7 candidates.
PRE_COMPETITION_CUES: tuple[str, ...] = (
    "tomorrow",
    "this weekend",
    "next week",
    "in a few days",
    "race day",
    "first race",
    "first marathon",
    "first meet",
    "upcoming",
    "coming up",
    "about to",
    "getting ready",
    "taper",
    "tapering",
    "night before",
    "day before",
    "week out",
    "days out",
    "starting line",
    "start line",
    "nervous about",
    "anxious about",
    "worried about",
    "excited for",
    "counting down",
    "prep for",
    "preparing for",
    "goal race",
)

#: Past-tense markers. A post carrying these is a race report, not anticipation.
POST_COMPETITION_CUES: tuple[str, ...] = (
    "race report",
    "finished in",
    "crossed the line",
    "pr'd",
    "pb'd",
    "i ran a",
    "i swam a",
    "yesterday's race",
    "last weekend",
    "post race",
    "post-race",
    "recap",
    "results are in",
    "dnf'd",
    "podium",
    "i won",
    "i placed",
    "final time",
    "official time",
)

#: P6 / C4. Health, injury and treatment content is special-category data and
#: outside the pre-competition psychological-language scope. Pre-race nerves are
#: in scope; a disclosed anxiety disorder is not, and the line between them is
#: exactly where this list has to be conservative.
HEALTH_CUES: tuple[str, ...] = (
    "injury",
    "injured",
    "physio",
    "physical therapy",
    "surgery",
    "surgeon",
    "mri",
    "x-ray",
    "fracture",
    "stress fracture",
    "tendon",
    "tendinitis",
    "tendinopathy",
    "plantar",
    "itbs",
    "shin splints",
    "sprain",
    "torn",
    "diagnosed",
    "diagnosis",
    "prescribed",
    "medication",
    "meds",
    "dosage",
    "antidepressant",
    "ssri",
    "beta blocker",
    "adhd",
    "ocd",
    "ptsd",
    "eating disorder",
    "anorexi",
    "bulimi",
    "red-s",
    "reds ",
    "relative energy",
    "depression",
    "depressive",
    "anxiety disorder",
    "panic attack",
    "panic disorder",
    "therapist",
    "therapy session",
    "psychiatrist",
    "counsell",
    "counsel",
    "self-harm",
    "suicid",
    "concussion",
    "long covid",
    "rehab",
)

#: P2 / C3. Age and school signals. Over-inclusive on purpose.
MINOR_CUES: tuple[str, ...] = (
    "high school",
    "highschool",
    "middle school",
    "secondary school",
    "year 9",
    "year 10",
    "year 11",
    "grade 9",
    "grade 10",
    "grade 11",
    "grade 12",
    "freshman",
    "sophomore year",
    "junior year",
    "senior year",
    "my mum",
    "my mom drives",
    "my parents drive",
    "my coach at school",
    "u14",
    "u15",
    "u16",
    "u17",
    "u18",
    "under-18",
    "under 18",
    "school team",
    "school meet",
    "junior nationals",
    "youth nationals",
)

#: Explicit self-reported ages below 18, e.g. "I'm 16", "16f", "(17m)".
_AGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bi(?:'m| am)\s+(\d{1,2})\b", re.I),
    re.compile(r"\b(\d{1,2})\s*[mf]\b", re.I),
    re.compile(r"\((\d{1,2})\s*[mf]\)", re.I),
    re.compile(r"\bage[d]?\s+(\d{1,2})\b", re.I),
)

#: C11. The only fields that may be carried off the platform. Author, karma,
#: history, awards, flair and the cross-posting graph are all absent by design.
ALLOWED_POST_FIELDS: frozenset[str] = frozenset(
    {"id", "subreddit", "title", "selftext", "created_utc", "over_18"}
)

MIN_WORDS = 25
MAX_WORDS = 400


@dataclass(frozen=True)
class HarvestQuery:
    """A topic-scoped request. **There is no author field, by design (C1).**

    `subreddit` must be in `PERMITTED_COMMUNITIES`; `harvest` refuses otherwise
    rather than trusting the caller.
    """

    subreddit: str
    query: str = "race OR meet OR competition"
    limit: int = 200

    def __post_init__(self) -> None:
        if self.subreddit not in PERMITTED_COMMUNITIES:
            raise ValueError(
                f"subreddit {self.subreddit!r} is not in PERMITTED_COMMUNITIES. "
                "Adding one is a governance decision -- edit src/ingestion/reddit.py "
                "and record the reasoning, per docs/ethics.md §3.5."
            )


@dataclass
class HarvestStats:
    """Why posts were dropped. Reported so the yield is auditable.

    A harvest that keeps 4% of what it saw is not obviously wrong, but it is
    something the owner should see rather than infer from a small output file.
    """

    seen: int = 0
    kept: int = 0
    dropped: dict[str, int] = field(default_factory=dict)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def as_lines(self) -> list[str]:
        lines = [f"seen {self.seen}, kept {self.kept}"]
        for reason, count in sorted(self.dropped.items(), key=lambda kv: -kv[1]):
            lines.append(f"  dropped {count:>5}  {reason}")
        return lines


# ---------------------------------------------------------------------------
# Filters -- pure, offline, individually testable
# ---------------------------------------------------------------------------


def _body(post: dict[str, Any]) -> str:
    return f"{post.get('title', '')}\n{post.get('selftext', '')}".strip()


def _contains(text: str, cues: Sequence[str]) -> str | None:
    """Return the first matching cue, or None. Returns the cue so refusal logs
    say *what* matched -- a refusal log that only says "health content" cannot
    be audited for false positives."""
    lowered = text.lower()
    for cue in cues:
        if cue in lowered:
            return cue
    return None


def mentions_minor(text: str) -> str | None:
    """C3 / P2. Any signal of a minor author. Over-inclusive on purpose.

    Catches both lexical school/youth markers and explicit self-reported ages
    under 18. An adult writing about their child's race is dropped too; that is
    a false positive this module accepts, because the alternative error puts a
    minor's words into a psychological risk corpus.
    """
    hit = _contains(text, MINOR_CUES)
    if hit:
        return hit
    for pattern in _AGE_PATTERNS:
        for match in pattern.finditer(text):
            try:
                age = int(match.group(1))
            except (TypeError, ValueError):  # pragma: no cover - regex guarantees digits
                continue
            # Ages under 13 are almost always distances, splits or years, not
            # ages ("I'm 5 minutes off PB"). 13-17 is the band that matters.
            if 13 <= age < 18:
                return f"self-reported age {age}"
    return None


def is_health_content(text: str) -> str | None:
    """C4 / P6. Injury, illness, treatment, or a disclosed clinical condition.

    The hardest boundary in this module. "Nervous about the race" is the target
    construct; "my anxiety disorder flares before races" is special-category
    health data and must not enter the corpus. The cue list resolves ambiguity
    toward exclusion, which costs recall on exactly the emotionally intense
    posts the taxonomy cares most about -- a real cost, accepted deliberately.
    """
    return _contains(text, HEALTH_CUES)


def is_pre_competition(text: str) -> bool:
    """Anticipatory, and not a race report.

    Requires a forward-looking cue AND the absence of past-tense race-report
    markers. Both halves matter: "nervous about tomorrow" in a race report's
    reflection paragraph is still a race report.
    """
    if _contains(text, POST_COMPETITION_CUES):
        return False
    return _contains(text, PRE_COMPETITION_CUES) is not None


def days_to_competition(text: str) -> int | None:
    """Coarse days-until-competition, when the post states it plainly.

    Feeds `RawRecord.time_to_competition_days`, which Phase 15's risk layer
    accepts as optional context. Returns None rather than guessing -- an
    invented number would flow into a fusion feature and be indistinguishable
    from a measured one.
    """
    lowered = text.lower()
    if "tomorrow" in lowered or "night before" in lowered or "day before" in lowered:
        return 1
    if "this weekend" in lowered or "in a few days" in lowered:
        return 3
    if "next week" in lowered or "week out" in lowered:
        return 7
    match = re.search(r"\b(\d{1,2})\s+days?\s+(?:out|to go|until|before)\b", lowered)
    if match:
        value = int(match.group(1))
        if 0 <= value <= 60:
            return value
    return None


def minimise(post: dict[str, Any]) -> dict[str, Any]:
    """C11. Drop every field not on the allow-list.

    Applied before anything else touches the post, so author metadata cannot
    reach a record even by accident. Whitelist rather than blacklist: a new
    field appearing in an API response is excluded by default.
    """
    return {k: v for k, v in post.items() if k in ALLOWED_POST_FIELDS}


# ---------------------------------------------------------------------------
# Harvest
# ---------------------------------------------------------------------------


def _record_id(source_id: str, post_id: str) -> str:
    """Stable, non-reversible record id.

    A hash of the post id rather than the post id itself. The post id is a
    direct handle back to the author's account, and C10 permits releasing ids
    only while C6 and C9 remain satisfiable -- so the corpus stores a digest and
    the mapping stays in the provenance file, out of the records themselves.
    """
    digest = hashlib.sha256(f"{source_id}:{post_id}".encode()).hexdigest()[:16]
    return f"{source_id}_{digest}"


def harvest(
    posts: Iterable[dict[str, Any]],
    *,
    source_id: str,
    subreddit: str,
    stats: HarvestStats | None = None,
    log_path: Path | None = None,
) -> Iterator[RawRecord]:
    """Filter fetched posts into `RawRecord`s, enforcing C1-C11.

    Takes already-fetched posts and performs no network I/O -- see the module
    docstring on why the network edge is separate.

    Note what is *not* a parameter: there is no author, no `strict`, no
    `skip_checks`. Every drop is logged to `logs/ingestion_refusals.log`.
    """
    stats = stats if stats is not None else HarvestStats()

    if subreddit not in PERMITTED_COMMUNITIES:
        log_refusal(
            "A5_COMMUNITY_NOT_PERMITTED",
            source_id,
            f"subreddit {subreddit!r} not in PERMITTED_COMMUNITIES",
            log_path=log_path,
        )
        return

    for raw in posts:
        stats.seen += 1
        post = minimise(raw)  # C11 first, before anything reads the post
        post_id = str(post.get("id", ""))
        text = _body(post)

        # `post_id` is bound as a default rather than closed over. A closure
        # would capture the loop variable by reference, so it stays correct only
        # while `_drop` is called inside the same iteration -- true today, and a
        # silent mislabelling of which post was refused the moment anyone defers
        # a call. Refusal logs are the audit trail for a governance control, so
        # they should not depend on that invariant holding.
        def _drop(reason: str, detail: str, _post_id: str = post_id) -> None:
            stats.drop(reason)
            log_refusal(reason, source_id, f"post {_post_id}: {detail}", log_path=log_path)

        if not post_id:
            _drop("A5_NO_POST_ID", "missing id; provenance would be incomplete (P7)")
            continue
        if post.get("over_18"):
            _drop("A5_NSFW", "flagged over_18 upstream")
            continue

        words = len(text.split())
        if words < MIN_WORDS:
            _drop("A5_TOO_SHORT", f"{words} words < {MIN_WORDS}")
            continue
        if words > MAX_WORDS:
            _drop("A5_TOO_LONG", f"{words} words > {MAX_WORDS}")
            continue

        minor_hit = mentions_minor(text)
        if minor_hit:
            _drop("A5_POSSIBLE_MINOR", f"matched {minor_hit!r} (C3/P2)")
            continue

        health_hit = is_health_content(text)
        if health_hit:
            _drop("A5_HEALTH_CONTENT", f"matched {health_hit!r} (C4/P6)")
            continue

        if not is_pre_competition(text):
            _drop("A5_NOT_PRE_COMPETITION", "no anticipatory cue, or reads as a race report")
            continue

        stats.kept += 1
        yield RawRecord(
            record_id=_record_id(source_id, post_id),
            source_id=source_id,
            text=text,
            time_to_competition_days=days_to_competition(text),
            sport=_sport_for(subreddit),
            # Left None deliberately. `COMPETITION_LEVELS` is
            # ('club','regional','national','international','elite') and a forum
            # post states none of them. Mapping the population to 'club' because
            # it is the lowest available tier would assert something no record
            # supports, and the value flows into Phase 15 as a context feature
            # where an invented level is indistinguishable from an observed one.
            # The population characteristic belongs in provenance notes, not in
            # a per-record field. This is also a real limitation for the paper:
            # A5 records carry no competition level.
            competition_level=None,
            source_type="social",
            language="en",
            synthetic=False,
            # C5: stays False until the Phase 8 de-identification pass runs.
            # Flipping it here would mark un-de-identified text as clean.
            deidentified=False,
        )


def _sport_for(subreddit: str) -> str:
    return {
        "running": "running",
        "AdvancedRunning": "running",
        "Marathon_Training": "running",
        "triathlon": "triathlon",
        "swimming": "swimming",
        "climbing": "climbing",
        "rowing": "rowing",
        "cycling": "cycling",
    }.get(subreddit, "unknown")


def a5_descriptor(
    source_id: str,
    subreddit: str,
    *,
    collection_date: str | None = None,
) -> SourceDescriptor:
    """The provenance claim for an A5 source, with the P1-P7 declarations.

    `not_scraped_personal_social_media` is asserted True because P1, as narrowed
    on 2026-08-11, prohibits *account-centred* collection -- and this module
    cannot do account-centred collection, since no author parameter exists on
    any of its entry points. The assertion is therefore structural rather than a
    promise, which is the only reason it is safe to make.
    """
    return SourceDescriptor(
        source_id=source_id,
        source_name=f"r/{subreddit} pre-competition posts (topic-scoped)",
        allowlist_category="A5_public_pseudonymous_forum",
        url_or_citation=f"https://www.reddit.com/r/{subreddit}/",
        licence_or_consent_basis=(
            "Public pseudonymous forum posts collected topic-scoped under "
            "docs/ethics.md §3.5 category A5 (owner amendment 2026-08-11). Not "
            "consented by authors; see §3.5.2 for the recorded argument against. "
            "Reddit User Agreement and API Terms; official API, registered "
            "application, declared research use."
        ),
        permitted_uses=(
            "Construct annotation and model training for this project only. "
            "Derived artefacts only. No verbatim publication (C6). No "
            "individual-level output (C7)."
        ),
        redistribution_permitted=False,
        synthetic=False,
        subject_is_adult=True,
        language="en",
        source_type="social",
        # None, not 'club'. See the note in `harvest`: the population is
        # recreational/amateur, but that is not one of COMPETITION_LEVELS and no
        # individual post states its author's level. Recorded in `notes` as a
        # population characteristic instead of asserted per record.
        competition_level=None,
        sport=_sport_for(subreddit),
        collection_date=collection_date,
        notes=(
            "A5. Topic-scoped, never account-scoped (C1). Population is "
            "recreational/amateur endurance athletes, but competition_level is "
            "left null on every record because no post states it and "
            "COMPETITION_LEVELS has no 'amateur' tier -- a known limitation for "
            "the paper. Minor and health filters are over-inclusive by design, "
            "costing recall on emotionally intense posts. deidentified=False "
            "until the Phase 8 pass runs (C5). OPEN-030: the §3.4 ethics "
            "exemption predates this amendment and should be reconfirmed before "
            "submission."
        ),
        declares={
            "not_scraped_personal_social_media": True,  # topic-scoped; no author parameter exists
            "no_minors": True,  # mentions_minor() drops on any signal
            "not_private_communication": True,  # public subreddit posts
            "licence_and_tos_permit_this_use": True,  # official API, research use declared
            "not_behind_auth_or_paywall": True,  # public listings only
            "not_health_injury_or_treatment_content": True,  # is_health_content() drops
            "provenance_is_complete": True,
        },
    )


#: Sent on every public request. Reddit asks for a descriptive User-Agent that
#: identifies the project and a contact; a default library UA is what gets an IP
#: rate-limited to zero. Not a credential -- it identifies the software, not a
#: user, and nothing here authenticates.
PUBLIC_USER_AGENT = (
    "python:sports-risk-nlp:0.1 (academic research; pre-competition "
    "psychological language; contact via docs/ethics.md §7.1)"
)

#: Seconds between public requests. Reddit's unauthenticated budget is roughly
#: 10 requests/minute; 6.5s stays inside it with margin. Deliberately not
#: configurable downward -- a parameter here is a parameter someone sets to 0.
_PUBLIC_REQUEST_INTERVAL = 6.5


def fetch_listing_public(
    query: HarvestQuery,
    *,
    pages: int = 1,
    user_agent: str = PUBLIC_USER_AGENT,
) -> Iterator[dict[str, Any]]:
    """Credential-free listing fetch via Reddit's public JSON endpoints.

    No app, no client id, no secret, no token. Reddit serves the same listings
    at `.../search.json` to unauthenticated callers, so this reads what any
    logged-out visitor sees.

    **Read `docs/ethics.md` §3.5.3 C2 before using this.** C2 originally required
    a registered application; it was relaxed on 2026-08-12 to permit public
    read-only endpoints, and the relaxation carries a caveat that is recorded
    there rather than hidden here: Reddit's Data API Terms ask programmatic
    users to register, so low-volume unauthenticated reads are a **gray area
    rather than a clearly permitted one**. P4 (ToS violation) is not
    automatically satisfied by this route. Registering a script application is
    free and removes the ambiguity; prefer `fetch_listing` where possible.

    Rate limited to one request per ~6.5s, single-threaded, sequential. The
    interval is a module constant and not a parameter, because the failure mode
    of a configurable politeness delay is that someone configures it to zero and
    gets the project's IP blocked -- taking the corpus with it.

    Still topic-scoped: the only inputs are a community and a query. There is no
    author parameter here either (C1).
    """
    import json as _json
    import time as _time
    import urllib.parse
    import urllib.request

    after: str | None = None
    for page in range(max(1, pages)):
        params = {
            "q": query.query,
            "restrict_sr": "on",
            "sort": "new",
            "limit": str(min(100, query.limit)),
            "t": "year",
        }
        if after:
            params["after"] = after
        url = f"https://www.reddit.com/r/{query.subreddit}/search.json?" + urllib.parse.urlencode(
            params
        )
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = _json.loads(response.read().decode("utf-8"))

        children = payload.get("data", {}).get("children", [])
        if not children:
            return
        for child in children:
            data = child.get("data", {})
            yield {
                "id": data.get("id"),
                "subreddit": query.subreddit,
                "title": data.get("title") or "",
                "selftext": data.get("selftext") or "",
                "created_utc": data.get("created_utc"),
                "over_18": bool(data.get("over_18", False)),
            }

        after = payload.get("data", {}).get("after")
        if not after:
            return
        if page + 1 < pages:
            _time.sleep(_PUBLIC_REQUEST_INTERVAL)


def fetch_listing(query: HarvestQuery, client: Any) -> Iterator[dict[str, Any]]:
    """The network edge. Thin on purpose; everything testable lives above it.

    `client` is a PRAW `Reddit` instance (or anything exposing the same
    `.subreddit(name).search(...)` surface). It is injected rather than
    constructed here so that credentials never live in this module and so the
    filtering path can be tested with no client at all.

    Yields raw dicts; `harvest` minimises them. Note again that the only inputs
    are a community and a topic query -- there is no code path from here to a
    user's post history.
    """
    listing = client.subreddit(query.subreddit).search(query.query, sort="new", limit=query.limit)
    for submission in listing:
        yield {
            "id": getattr(submission, "id", None),
            "subreddit": query.subreddit,
            "title": getattr(submission, "title", "") or "",
            "selftext": getattr(submission, "selftext", "") or "",
            "created_utc": getattr(submission, "created_utc", None),
            "over_18": bool(getattr(submission, "over_18", False)),
        }
