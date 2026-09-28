"""Phase 36 -- a squad of athletes, ranked, with the unreadable ones counted.

What this adds that the rest of the app does not
------------------------------------------------
Every other surface answers "what about this passage". A coach does not have one
passage, they have a squad, and the question they actually ask is *who do I talk
to first*. That is an ordering question, and ordering is the one thing this index
legitimately supports: `bands.py` and every caption on the site already say
"ranking only, not calibrated". So this page ranks, and refuses the two things a
squad view is usually built to do.

The two things it refuses
-------------------------
**There is no team score.** Not a mean, not a "squad risk index", not a gauge
with one needle. Averaging ten uncalibrated rankings produces a number with less
meaning than any of its inputs while looking like more, and the first thing that
number would do is get screenshotted beside a team name. The headline here is a
*distribution*: who is where in the order, how far apart they are, and how many
could not be read at all.

**The median is an order statistic, not an average.** `Squad.median` returns one
member's own `ScoreSurface`, selected, never a value computed from two. On an
even count it takes the lower of the two middle members rather than averaging
them. That keeps Phase 34's rule literally true -- every number on the surface is
one `build_view` produced for a real record -- instead of acquiring its first
exception here.

The defect this module is shaped around
---------------------------------------
`.claude.md` section 12.3, arriving by a new door for the fourth time.
`LexiconBackend` scores anything: a member the word list found nothing in gets ten
zero probabilities and a logistic squash of **exactly 0.50**, which in a ranked
squad lands mid-table looking like an average athlete. It is not an average
athlete, it is an athlete we cannot speak about, and in a triage view that
distinction is the whole point -- the person you cannot read is not the person you
can safely skip.

So `SquadMember` cannot hold a number it did not earn: `detected` and `surface`
must agree at construction, exactly as `SentenceBand` requires in `ribbon.py` and
`CloudLane` requires in `corpus_cloud.py`. Unreadable members are listed
separately under their own count, never ranked, never folded into the median.

Why the lexicon
---------------
Same reason as the ribbon: scoring freshly generated text needs a backend that can
read new text, and `ReplayBackend.predict` refuses by design. Every number here is
the word-list floor with its known upward bias (OPEN-021), and the page says so
rather than letting a reader assume the paper's model produced it.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.dashboard.backend import LexiconBackend, PredictionBackend
from src.dashboard.copy import CONSTRUCTS as PLAIN_CONSTRUCTS
from src.dashboard.view import ScoreSurface, build_view
from src.ingestion.scenarios import (
    LIFE_CONTEXT_LABELS,
    LIFE_CONTEXTS,
    SPORTS,
    MatchDayScenario,
    generate_scenario_record,
)
from src.risk.fusion import LinearRiskScorer

__all__ = [
    "MAX_SQUAD",
    "MIN_SQUAD",
    "Squad",
    "SquadMember",
    "SquadRefused",
    "build_squad",
]

#: Two athletes is a comparison, and page 7 already compares two texts properly.
#: A squad is the smallest group where an *order* carries information.
MIN_SQUAD = 3

#: Past this the ranked rows stop being legible at figure width. Extra members are
#: refused rather than silently dropped off the bottom of the chart.
MAX_SQUAD = 24


class SquadRefused(ValueError):
    """The squad cannot be built, in wording the page prints unchanged.

    Same contract as `RibbonRefused`: a refusal reading "invalid input" teaches the
    reader nothing and invites them to try the identical thing again.
    """


@dataclass(frozen=True)
class SquadMember:
    """One athlete's record and what the index did with it.

    `surface` is `None` exactly when nothing was detected -- the section 12.3 rule
    made structural rather than checked at render time, because the render is the
    step most likely to be reimplemented by someone who has not read this.
    """

    slot: int
    sport: str
    life_context: str
    plain_context: str
    seed: int
    text: str
    detected: bool
    moved: bool
    surface: ScoreSurface | None
    constructs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.detected != (self.surface is not None):
            raise ValueError(
                f"squad member {self.slot} is detected={self.detected} and disagrees with "
                "its own number. A member the detector had nothing to say about may not "
                "hold an index: an all-zero decomposition squashes to exactly 0.50, which "
                "in a ranked table reads as a middling athlete. See .claude.md sec.12.3."
            )
        if self.moved and not self.detected:
            raise ValueError(f"squad member {self.slot} moved the index without being detected")
        if not self.text.strip():
            raise ValueError(f"squad member {self.slot} has no text")

    @property
    def value(self) -> float | None:
        """The index, or `None` where there is nothing to rank on."""
        return self.surface.value if self.surface else None

    @property
    def state(self) -> str:
        """The three states, as the word the figure prints. Never a colour alone."""
        if not self.detected:
            return "nothing detected"
        if not self.moved:
            return "counted as zero"
        return "moves the index"


@dataclass(frozen=True)
class Squad:
    """A group of athletes as an ordering problem, plus what could not be ordered."""

    sport: str
    members: tuple[SquadMember, ...]
    median: ScoreSurface | None
    scale_label: str
    caveat: str
    source: str
    stamp: str

    def __post_init__(self) -> None:
        if len(self.members) < MIN_SQUAD:
            raise ValueError(f"a squad needs at least {MIN_SQUAD} members")
        if bool(self.scored) != (self.median is not None):
            raise ValueError(
                "a squad with no readable member has no median, and a squad with readable "
                "members must report one. The .claude.md sec.12.3 rule one level up: no "
                "readings, no summary number -- and specifically not 0.50."
            )

    @property
    def scored(self) -> tuple[SquadMember, ...]:
        """Members the detector actually read. The only ones that may be ranked."""
        return tuple(m for m in self.members if m.surface is not None)

    @property
    def silent(self) -> tuple[SquadMember, ...]:
        """Members with no reading. Listed, counted, never ranked and never hidden."""
        return tuple(m for m in self.members if m.surface is None)

    @property
    def ordered(self) -> tuple[SquadMember, ...]:
        """Readable members, highest index first. Ties broken by slot, so stable."""
        return tuple(sorted(self.scored, key=lambda m: (-m.surface.value, m.slot)))

    @property
    def n_silent(self) -> int:
        return len(self.silent)

    @property
    def n_inert_only(self) -> int:
        return sum(1 for m in self.scored if not m.moved)

    @property
    def spread(self) -> float:
        """Highest readable member minus lowest. Zero below two readable members.

        The number that says whether the ranking separates anyone at all. A coach
        looking at a squad whose top and bottom differ by 0.02 is entitled to that
        in digits instead of being asked to eyeball two dots.
        """
        values = [m.surface.value for m in self.scored]
        return max(values) - min(values) if len(values) > 1 else 0.0

    @property
    def prevalence(self) -> tuple[tuple[str, str, int], ...]:
        """How many members each construct was detected in, commonest first.

        A count of detections, not a score. Nothing here is averaged or weighted:
        a mean intensity across athletes is a psychometric claim this project has
        no basis for, and `.claude.md` sec.16.4 already refuses one for subscales
        one level down.
        """
        counts: dict[str, int] = {}
        for member in self.members:
            for construct in member.constructs:
                counts[construct] = counts.get(construct, 0) + 1
        rows = [
            (construct, PLAIN_CONSTRUCTS.get(construct, (construct,))[0], n)
            for construct, n in counts.items()
        ]
        rows.sort(key=lambda row: (-row[2], row[0]))
        return tuple(rows)


def _median_member(scored: Sequence[SquadMember]) -> SquadMember | None:
    """The middle member, selected -- never a value computed from two of them.

    On an even count this takes the lower of the two middle members rather than
    averaging them. Deliberate: it keeps every number on the page one that
    `build_view` actually produced for a real record, so Phase 34's "no new
    arithmetic" rule stays literally true instead of acquiring its first exception
    here.
    """
    if not scored:
        return None
    ranked = sorted(scored, key=lambda m: (m.surface.value, m.slot))
    return ranked[(len(ranked) - 1) // 2]


def _draw_contexts(n: int, seed: int) -> tuple[str, ...]:
    """A reproducible spread of life contexts across the squad.

    Seeded from the caller's seed so the same squad regenerates byte-identically,
    the determinism guarantee `scenarios.generate_scenario_record` already makes
    one level down. Shuffled without replacement while the pool lasts, so a small
    squad is varied rather than five copies of one scenario.
    """
    rng = random.Random(seed)
    pool = list(LIFE_CONTEXTS)
    rng.shuffle(pool)
    while len(pool) < n:
        extra = list(LIFE_CONTEXTS)
        rng.shuffle(extra)
        pool.extend(extra)
    return tuple(pool[:n])


def build_squad(
    *,
    sport: str,
    size: int,
    seed: int,
    policy_scorer: LinearRiskScorer | None = None,
    backend: PredictionBackend | None = None,
    context: Mapping[str, float] | None = None,
) -> Squad:
    """Generate `size` synthetic athletes in `sport` and rank the readable ones.

    Every member is a `scenarios.generate_scenario_record` draw -- the same seeded
    grammar as every other synthetic example in the project -- scored through the
    ordinary `build_view` path. No new scoring, no new weights, no new model.

    `timing` is fixed at `morning_of` deliberately. It is metadata in the
    generator: all three timings produce byte-identical text (they set only
    `time_to_competition_days` and the record id), so exposing it as a squad
    control would be a dropdown that changes nothing while implying otherwise.
    """
    if sport not in SPORTS:
        raise SquadRefused(f"{sport!r} is not one of the sports this generator writes for.")
    if size < MIN_SQUAD:
        raise SquadRefused(
            f"A squad of {size} is not a squad. Two athletes is a comparison, and the "
            f"compare page already does that properly -- ask for at least {MIN_SQUAD}."
        )
    if size > MAX_SQUAD:
        raise SquadRefused(
            f"{size} rows stop being readable at figure width. Ask for at most "
            f"{MAX_SQUAD} rather than have the chart drop the tail without saying so."
        )

    backend = backend or LexiconBackend()
    contexts = _draw_contexts(size, seed)

    members: list[SquadMember] = []
    reference = None
    for slot, life_context in enumerate(contexts):
        member_seed = seed + slot
        record = generate_scenario_record(
            MatchDayScenario(sport=sport, timing="morning_of", life_context=life_context),
            seed=member_seed,
        )
        view = build_view(text=record.text, backend=backend, scorer=policy_scorer, context=context)
        if reference is None:
            reference = view
        detected = tuple(bar.construct for bar in view.bars if bar.detected)
        members.append(
            SquadMember(
                slot=slot,
                sport=sport,
                life_context=life_context,
                plain_context=LIFE_CONTEXT_LABELS.get(life_context, life_context),
                seed=member_seed,
                text=record.text,
                detected=bool(detected),
                moved=any(bar.contribution != 0.0 for bar in view.bars),
                # No detection, no number. Not 0.0, not 0.5, not None drawn as zero.
                surface=view.risk if detected else None,
                constructs=detected,
            )
        )

    frozen = tuple(members)
    middle = _median_member([m for m in frozen if m.surface is not None])
    assert reference is not None  # size >= MIN_SQUAD, so the loop ran at least once
    return Squad(
        sport=sport,
        members=frozen,
        median=middle.surface if middle else None,
        scale_label=reference.scale_label,
        caveat=reference.caveat,
        source=reference.source,
        stamp=reference.risk.stamp,
    )
