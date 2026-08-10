"""Phase 9 -- corpus profiling over `data/interim/`.

Why this module exists, and why it is not a notebook
-----------------------------------------------------
Phase 9's gate is "documented data-quality issues and a stratified sampling
plan". Both are claims that end up in a paper, so both have to be recomputable
by a reviewer from a fresh clone. A notebook cannot carry that guarantee: its
outputs are stored state, they drift from the code that produced them, and
nothing fails when they do. So the arithmetic lives here, under `pytest`, and
`notebooks/01_eda.ipynb` is a thin viewer that calls these functions.

Why `data/interim/` and never `data/raw/`
------------------------------------------
`data/raw/` is not de-identified -- `docs/ethics.md` §5 makes de-identification
a precondition of *any* human review, and a profile is human review. For the
current corpus the two would give nearly the same numbers, because the A2
generator plants no identifiers, and that is precisely the trap: the habit
formed here is the habit that will run against A3 consented donations, where
the two are not the same at all. `load_interim` is therefore the only loader in
this module, and it takes a source id, not a path.

Three counting rules that are easy to get wrong
------------------------------------------------
**1. The unit changed at Phase 8.** 1,200 raw *records* became 4,141
*utterances*. Every statistic below is tagged with its unit in the field name
(`..._per_utterance` / `..._per_record`), because "mean length 41 tokens" is a
different claim depending on which one it is, and the two are not comparable
across phases.

**2. Placeholders are tokens.** `[ATHLETE]`, `[EVENT_WINDOW]` and the rest are
inserted by the de-identifier, so they are artefacts of *our pipeline*, not of
athlete language. Vocabulary is reported **both** ways (`VocabularyStats` is
computed twice) and the report states which figure it is quoting. Related and
carried forward to Phase 13: a subword tokeniser will happily split
`[EVENT_WINDOW]` into `[`, `EVENT`, `_`, `WINDOW`, `]`, which turns one
privacy artefact into five vocabulary items and puts a fragment boundary inside
a span the explainability layer will later attribute over. They must be added
as special tokens.

**3. `generation_spec` is generator metadata, not labels.** It records which
templates the generator *planted*. A prevalence table built from it describes
the template bank, not athlete language, and would be circular as evaluation
ground truth. It is computed here because "how balanced is the corpus we are
about to sample from" is a real question, but it is returned in a separately
named structure -- `GeneratorMetadataProfile` -- so a caller cannot use it by
accident, and every rendering of it must carry the warning.

The corpus is 100% synthetic
-----------------------------
OPEN-011. Every distribution in this module is a distribution over a template
grammar written by this project. Nothing here is evidence about how athletes
talk, and the report says so on every table rather than once at the top.

Pure Python: no numpy, no pandas, no matplotlib. It imports in the light Docker
image, and `pytest` cannot spend money running it.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from src.evaluation.metrics import Interval, bootstrap_statistic, proportion_ci
from src.preprocessing.records import InterimRecord
from src.preprocessing.store import InterimStore

#: The de-identifier's output vocabulary. Matched as whole bracketed tokens so
#: an ordinary bracket in the text cannot be miscounted as a placeholder.
PLACEHOLDER_TOKEN_RE = re.compile(r"\[[A-Z][A-Z_]*\]")

#: Word tokenisation for profiling only. Deliberately *not* the model
#: tokeniser: this is a descriptive statistic about the text as written, and
#: tying it to a subword vocabulary would make the corpus statistics change
#: whenever the model choice changes.
_WORD_RE = re.compile(r"\[[A-Z][A-Z_]*\]|[A-Za-z']+")


def tokenise(text: str, *, keep_placeholders: bool = True) -> list[str]:
    """Lowercased word tokens; placeholders survive as single tokens.

    `keep_placeholders=False` drops them entirely rather than lowercasing them
    into ordinary words -- `[coach]` would otherwise collide with the real word
    *coach* and silently inflate its frequency.
    """
    out: list[str] = []
    for match in _WORD_RE.finditer(text):
        token = match.group(0)
        if PLACEHOLDER_TOKEN_RE.fullmatch(token):
            if keep_placeholders:
                out.append(token)
            continue
        out.append(token.lower())
    return out


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_interim(source_id: str, *, root: Any = None) -> list[InterimRecord]:
    """Every de-identified utterance for one source.

    The only loader in this module, and it goes through `InterimStore`, which
    refuses `data/gold/`. There is deliberately no path-taking variant: a
    function that accepts an arbitrary directory is a function that can be
    pointed at `data/raw/`.
    """
    store = InterimStore(root)
    _provenance, records = store.read_source(source_id)
    return records


def group_by_parent(records: Sequence[InterimRecord]) -> dict[str, list[InterimRecord]]:
    """Utterances grouped back into the raw records they were cut from.

    Needed for every per-record statistic. Reconstructing the record from its
    utterances is not the same as reading `data/raw/` -- these are the
    de-identified pieces -- and that difference is the point.
    """
    grouped: dict[str, list[InterimRecord]] = defaultdict(list)
    for record in records:
        grouped[record.parent_record_id].append(record)
    for pieces in grouped.values():
        pieces.sort(key=lambda r: r.utterance_index)
    return dict(grouped)


# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Distribution:
    """A numeric distribution, summarised the way a reviewer wants to read it."""

    unit: str
    n: int
    mean: float
    mean_ci: Interval
    sd: float
    minimum: float
    p25: float
    median: float
    p75: float
    p90: float
    maximum: float

    def as_row(self) -> str:
        return (
            f"{self.unit:<28} n={self.n:<6} mean={self.mean:7.2f} "
            f"[{self.mean_ci.low:.2f}, {self.mean_ci.high:.2f}] "
            f"sd={self.sd:6.2f} min={self.minimum:.0f} p25={self.p25:.0f} "
            f"med={self.median:.0f} p75={self.p75:.0f} p90={self.p90:.0f} "
            f"max={self.maximum:.0f}"
        )


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Nearest-rank quantile.

    Nearest-rank rather than interpolated on purpose: every quantity profiled
    here is a count of characters, tokens or utterances, so an interpolated
    "42.5 tokens" would be a value the corpus cannot contain.
    """
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return float(sorted_values[index])


def describe(values: Sequence[float], unit: str, *, seed: int = 42) -> Distribution:
    """Summarise a distribution, with a bootstrap CI on the mean.

    The CI is on the *mean* only. Quantiles are reported without intervals
    because a bootstrap interval on a nearest-rank quantile of an integer-valued
    distribution is mostly an artefact of the granularity, and printing one
    would suggest a precision that is not there.
    """
    if not values:
        empty = Interval(0.0, 0.0, 0.0, 0.95)
        return Distribution(unit, 0, 0.0, empty, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / (n - 1) if n > 1 else 0.0
    return Distribution(
        unit=unit,
        n=n,
        mean=mean,
        mean_ci=bootstrap_statistic(ordered, lambda xs: sum(xs) / len(xs), seed=seed),
        sd=math.sqrt(variance),
        minimum=ordered[0],
        p25=_quantile(ordered, 0.25),
        median=_quantile(ordered, 0.50),
        p75=_quantile(ordered, 0.75),
        p90=_quantile(ordered, 0.90),
        maximum=ordered[-1],
    )


def histogram(values: Sequence[float], *, bins: int = 12) -> list[tuple[float, float, int]]:
    """`(low, high, count)` per equal-width bin. Feeds the SVG figures."""
    if not values:
        return []
    low, high = min(values), max(values)
    if high == low:
        return [(low, high, len(values))]
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1
    return [(low + i * width, low + (i + 1) * width, counts[i]) for i in range(bins)]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VocabularyStats:
    """Type/token behaviour, with the length confound handled explicitly."""

    keep_placeholders: bool
    tokens: int
    types: int
    ttr: float
    mattr: float
    mattr_window: int
    hapax: int
    top_types: tuple[tuple[str, int], ...] = ()

    @property
    def hapax_rate(self) -> float:
        return self.hapax / self.types if self.types else 0.0


def mattr(tokens: Sequence[str], window: int = 50) -> float:
    """Moving-Average Type-Token Ratio.

    **Why this and not raw TTR.** TTR is types/tokens, and it falls
    mechanically as a text gets longer: every corpus eventually runs out of new
    words while it never runs out of tokens. So a TTR computed over 4,141
    utterances is not comparable with one computed over the 1,200 records those
    utterances came from, even though the underlying text is identical --
    the number would drop with no change in lexical richness whatsoever. That
    exact comparison is the one a reader of this report is most likely to make,
    which is why raw TTR is reported here only alongside MATTR and never alone.

    MATTR takes the TTR of every window of `window` consecutive tokens and
    averages them. Because every window has the same length, the length
    confound is gone by construction and the numbers *are* comparable across
    corpora of different sizes. Covington & McFall (2010).
    """
    if len(tokens) <= window:
        return len(set(tokens)) / len(tokens) if tokens else 0.0
    counts: Counter[str] = Counter(tokens[:window])
    total = len(counts) / window
    windows = 1
    for i in range(window, len(tokens)):
        outgoing, incoming = tokens[i - window], tokens[i]
        counts[outgoing] -= 1
        if counts[outgoing] == 0:
            del counts[outgoing]
        counts[incoming] += 1
        total += len(counts) / window
        windows += 1
    return total / windows


def vocabulary(
    texts: Iterable[str],
    *,
    keep_placeholders: bool = True,
    window: int = 50,
    top_n: int = 25,
) -> VocabularyStats:
    """Vocabulary statistics over a stream of texts.

    Tokens are concatenated across texts before the MATTR sweep, so a window
    may straddle an utterance boundary. That is the correct choice for a corpus
    whose utterances are one sentence long: windowing *within* utterances would
    mean almost every window is shorter than the window size, and MATTR would
    silently degenerate back into raw TTR -- the very thing it exists to avoid.
    """
    tokens: list[str] = []
    for text in texts:
        tokens.extend(tokenise(text, keep_placeholders=keep_placeholders))
    counts = Counter(tokens)
    return VocabularyStats(
        keep_placeholders=keep_placeholders,
        tokens=len(tokens),
        types=len(counts),
        ttr=len(counts) / len(tokens) if tokens else 0.0,
        mattr=mattr(tokens, window),
        mattr_window=window,
        hapax=sum(1 for c in counts.values() if c == 1),
        top_types=tuple(counts.most_common(top_n)),
    )


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DuplicateProfile:
    """Exact and near-duplicate structure, at one unit."""

    unit: str
    n: int
    distinct: int
    exact_duplicate_items: int
    exact_duplicate_rate_ci: Interval
    near_duplicate_items: int
    near_duplicate_rate_ci: Interval
    jaccard_threshold: float
    most_repeated: tuple[tuple[str, int], ...] = ()

    @property
    def distinct_rate(self) -> float:
        return self.distinct / self.n if self.n else 0.0


def _near_duplicate_flags(texts: Sequence[str], threshold: float) -> list[bool]:
    """Which texts have a near-duplicate elsewhere in the corpus.

    Jaccard over token *sets*, with a **prefix filter** so this stays near-linear
    instead of the 8.6M pairwise comparisons a naive sweep needs at n=4,141.

    Why a prefix and not just the rarest token. An earlier version of this
    function bucketed each text under its single rarest token and claimed that
    was exact. It is not, and a test caught it: *"...tomorrow morning again"*
    and *"...tomorrow morning too"* are Jaccard 0.8 to each other, but their
    rarest tokens are *again* and *too*, so they landed in different buckets and
    were never compared. The function silently **under-reported** near
    duplicates, which for this project is the dangerous direction -- the whole
    point of the measurement is to stop repeated items reaching the gold set and
    inflating a kappa.

    The correct bound is the standard prefix filter. Fix a global token order
    (rarest first). If ``J(A, B) >= t`` then ``|A ∩ B| >= t·max(|A|, |B|)``, so
    at most ``|A| - ceil(t·|A|)`` of A's tokens can be missing from B. Indexing
    A under its first ``|A| - ceil(t·|A|) + 1`` tokens in that order therefore
    guarantees that any B meeting the threshold shares at least one index entry
    with it. That is exact, not heuristic: no qualifying pair is missed.
    """
    token_sets = [frozenset(tokenise(t)) for t in texts]
    document_freq: Counter[str] = Counter()
    for tokens in token_sets:
        document_freq.update(tokens)

    def prefix(tokens: frozenset[str]) -> list[str]:
        ordered = sorted(tokens, key=lambda t: (document_freq[t], t))
        length = len(ordered) - math.ceil(threshold * len(ordered)) + 1
        return ordered[: max(1, length)]

    buckets: dict[str, list[int]] = defaultdict(list)
    for index, tokens in enumerate(token_sets):
        if not tokens:
            continue
        for token in prefix(tokens):
            buckets[token].append(index)

    flags = [False] * len(texts)
    compared: set[tuple[int, int]] = set()
    for members in buckets.values():
        for i_pos, i in enumerate(members):
            for j in members[i_pos + 1 :]:
                if (i, j) in compared:
                    continue
                compared.add((i, j))
                a, b = token_sets[i], token_sets[j]
                union = len(a | b)
                if union and len(a & b) / union >= threshold:
                    flags[i] = flags[j] = True
    return flags


def duplicate_profile(
    texts: Sequence[str],
    unit: str,
    *,
    threshold: float = 0.9,
    seed: int = 42,
    top_n: int = 10,
) -> DuplicateProfile:
    """Exact and near-duplicate rates with bootstrap CIs.

    "Duplicate items" counts every item that shares its text with another,
    including the first occurrence -- not `n - distinct`. The distinction
    matters for the sampling plan: what a gold-set designer needs to know is how
    many items they could draw that are indistinguishable from something else,
    and that includes the original.
    """
    counts = Counter(texts)
    exact_flags = [counts[t] > 1 for t in texts]
    near_flags = _near_duplicate_flags(texts, threshold)
    # Exact duplicates are near-duplicates too (Jaccard 1.0). Reported as a
    # superset rather than as disjoint classes, because subtracting them would
    # make "near" mean "near but not exact", which is not what anyone reads it as.
    return DuplicateProfile(
        unit=unit,
        n=len(texts),
        distinct=len(counts),
        exact_duplicate_items=sum(exact_flags),
        exact_duplicate_rate_ci=proportion_ci(exact_flags, seed=seed),
        near_duplicate_items=sum(near_flags),
        near_duplicate_rate_ci=proportion_ci(near_flags, seed=seed),
        jaccard_threshold=threshold,
        most_repeated=tuple(
            (text, count) for text, count in counts.most_common(top_n) if count > 1
        ),
    )


# ---------------------------------------------------------------------------
# Junk and degenerate utterances
# ---------------------------------------------------------------------------

#: Minimum word count below which an utterance carries too little context for a
#: human to assign a construct. Not a cleaning threshold -- nothing is deleted
#: on the strength of it. It exists so the sampling plan can avoid handing an
#: annotator a two-word fragment and then reporting the resulting disagreement
#: as annotator unreliability.
MIN_ANNOTATABLE_TOKENS = 4

JUNK_CHECKS: tuple[str, ...] = (
    "too_short",
    "no_alphabetic_content",
    "placeholder_only",
    "unbalanced_brackets",
    "truncated_ending",
    "repeated_token_run",
)


@dataclass(frozen=True)
class JunkProfile:
    """Degenerate utterances, by failure mode."""

    n: int
    flagged: int
    flagged_rate_ci: Interval
    by_check: dict[str, int] = field(default_factory=dict)
    examples: dict[str, str] = field(default_factory=dict)


def junk_flags(text: str) -> list[str]:
    """Every degeneracy check this text fails. Empty is the healthy result."""
    failures: list[str] = []
    words = tokenise(text)
    stripped = PLACEHOLDER_TOKEN_RE.sub("", text)

    if len(words) < MIN_ANNOTATABLE_TOKENS:
        failures.append("too_short")
    if not re.search(r"[A-Za-z]", stripped):
        failures.append("no_alphabetic_content")
    if words and all(PLACEHOLDER_TOKEN_RE.fullmatch(w) for w in words):
        failures.append("placeholder_only")
    if text.count("[") != text.count("]") or text.count("(") != text.count(")"):
        failures.append("unbalanced_brackets")
    if text.strip() and text.strip()[-1] not in ".!?\"'":
        # A segmenter that cuts mid-sentence produces spans whose offsets are
        # right and whose meaning is wrong -- the failure mode that would be
        # invisible in the offset check Phase 8 already passes.
        failures.append("truncated_ending")
    for index in range(len(words) - 2):
        if words[index] == words[index + 1] == words[index + 2]:
            failures.append("repeated_token_run")
            break
    return failures


def junk_profile(texts: Sequence[str], *, seed: int = 42) -> JunkProfile:
    by_check: Counter[str] = Counter()
    examples: dict[str, str] = {}
    flags: list[bool] = []
    for text in texts:
        failures = junk_flags(text)
        flags.append(bool(failures))
        for failure in failures:
            by_check[failure] += 1
            examples.setdefault(failure, text)
    return JunkProfile(
        n=len(texts),
        flagged=sum(flags),
        flagged_rate_ci=proportion_ci(flags, seed=seed),
        by_check=dict(sorted(by_check.items())),
        examples=examples,
    )


# ---------------------------------------------------------------------------
# Metadata coverage and strata
# ---------------------------------------------------------------------------

#: The time-aware fields contribution #3 rests on. Named once here so the
#: coverage table and the sampling strata cannot disagree about what "context
#: metadata" means.
CONTEXT_FIELDS: tuple[str, ...] = (
    "time_to_competition_days",
    "sport",
    "competition_level",
    "region",
    "source_type",
    "training_load_hint",
    "language",
)

#: Time-to-competition bands. Boundaries are days, chosen to match the
#: pre-competition taper structure the taxonomy assumes rather than to make the
#: bins equal-sized: day-of and day-before are psychologically distinct from
#: "next week", and a plan that split them evenly would merge them.
TIME_BANDS: tuple[tuple[str, int, int], ...] = (
    ("day_of", 0, 0),
    ("eve", 1, 2),
    ("final_week", 3, 7),
    ("taper", 8, 14),
    ("build", 15, 10_000),
)


def time_band(days: int | None) -> str:
    if days is None:
        return "unknown"
    for name, low, high in TIME_BANDS:
        if low <= days <= high:
            return name
    return "unknown"


def coverage(records: Sequence[InterimRecord], *, seed: int = 42) -> dict[str, Interval]:
    """Non-null rate per context field, with a CI on each.

    A CI on a coverage rate looks like overkill at 100%, and it is exactly the
    point: an interval of [1.00, 1.00] is a different statement from a bare
    "100%", and when the first A3 donation arrives with patchy metadata the
    same table will show the difference without anyone changing the code.
    """
    return {
        name: proportion_ci([getattr(r, name) is not None for r in records], seed=seed)
        for name in CONTEXT_FIELDS
    }


def stratum_counts(records: Sequence[InterimRecord], field_name: str) -> dict[str, int]:
    """Counts per stratum value. `time_to_competition_days` is banded."""
    counts: Counter[str] = Counter()
    for record in records:
        if field_name == "time_band":
            counts[time_band(record.time_to_competition_days)] += 1
        else:
            counts[str(getattr(record, field_name))] += 1
    return dict(sorted(counts.items()))


# ---------------------------------------------------------------------------
# Generator metadata -- fenced off on purpose
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratorMetadataProfile:
    """What the generator PLANTED. **These are not labels.**

    Deliberately a separate type with a name nobody can mistake, rather than a
    `constructs` field on the main profile. `generation_spec` records the
    template choices `src/ingestion/synthetic.py` made. A construct-prevalence
    table built from it is a description of the template bank; presented as
    corpus prevalence it would be a claim about athlete language that the
    corpus cannot support, and used as evaluation ground truth it would measure
    whether a model can recover this project's own template choices.

    It is computed because the sampling plan genuinely needs it -- a gold set
    that never shows an annotator a `resilience` frame cannot measure agreement
    on `resilience` -- and every renderer of it is required to print the
    warning.

    **A second trap, found by checking rather than assuming.** Phase 8 copies
    `generation_spec` from the raw record onto *every* utterance cut from it,
    unchanged and in full (verified: all utterances of a record carry a
    byte-identical spec). A record averaging 3.45 utterances and planting 2
    constructs therefore reports both constructs on all 3.45 utterances,
    including the ones that realise neither -- the neutral logistics sentence
    and the discourse suffix. So `planted_construct_utterances` is **not** a
    per-utterance quantity at all; it is a record-level count multiplied by
    utterances-per-record. It is retained only because its ratio to
    `planted_construct_records` is a useful check on that multiplier, and
    `planted_construct_records` is the field every downstream calculation uses.
    """

    warning: str = (
        "GENERATOR METADATA, NOT LABELS -- describes the template bank, "
        "not athlete language. Never use as evaluation ground truth."
    )
    planted_construct_utterances: dict[str, int] = field(default_factory=dict)
    planted_construct_records: dict[str, int] = field(default_factory=dict)
    label_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    template_count: int = 0
    #: How many DISTINCT constructs the generator planted per record. Named for
    #: what it counts: an earlier draft called this `templates_per_record`, which
    #: was wrong in a way no test would catch, because a record plants at most
    #: one template per construct so the two counts coincide here and would
    #: diverge silently the moment the generator changed.
    constructs_per_record: dict[int, int] = field(default_factory=dict)
    rendered_as: dict[str, int] = field(default_factory=dict)
    interpretation_modifier: dict[str, int] = field(default_factory=dict)


def generator_metadata_profile(records: Sequence[InterimRecord]) -> GeneratorMetadataProfile:
    per_utterance: Counter[str] = Counter()
    per_record: Counter[str] = Counter()
    labels: dict[str, Counter[str]] = defaultdict(Counter)
    templates: set[str] = set()
    per_record_constructs: Counter[int] = Counter()
    rendered: Counter[str] = Counter()
    modifiers: Counter[str] = Counter()

    seen_records: dict[str, set[str]] = defaultdict(set)
    for record in records:
        spec = record.generation_spec or {}
        planted = spec.get("planted_constructs", ())
        for item in planted:
            construct = item.get("construct")
            if not construct:
                continue
            per_utterance[construct] += 1
            seen_records[record.parent_record_id].add(construct)
            if item.get("label") is not None:
                labels[construct][str(item["label"])] += 1
            if "template_id" in item:
                templates.add(item["template_id"])

    for record in records:
        spec = record.generation_spec or {}
        rendered[str(spec.get("rendered_as"))] += 1
        modifiers[str(spec.get("interpretation_modifier"))] += 1

    for constructs in seen_records.values():
        for construct in constructs:
            per_record[construct] += 1
        per_record_constructs[len(constructs)] += 1

    return GeneratorMetadataProfile(
        planted_construct_utterances=dict(sorted(per_utterance.items())),
        planted_construct_records=dict(sorted(per_record.items())),
        label_counts={k: dict(sorted(v.items())) for k, v in sorted(labels.items())},
        template_count=len(templates),
        constructs_per_record=dict(sorted(per_record_constructs.items())),
        rendered_as=dict(sorted(rendered.items())),
        interpretation_modifier=dict(sorted(modifiers.items())),
    )


# ---------------------------------------------------------------------------
# The whole profile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusProfile:
    """Everything Phase 9 measured, in one recomputable object."""

    source_id: str
    n_utterances: int
    n_records: int

    utterance_chars: Distribution
    utterance_tokens: Distribution
    record_chars: Distribution
    record_tokens: Distribution
    utterances_per_record: Distribution

    vocabulary_with_placeholders: VocabularyStats
    vocabulary_without_placeholders: VocabularyStats
    placeholder_token_count: int

    utterance_duplicates: DuplicateProfile
    record_duplicates: DuplicateProfile
    junk: JunkProfile

    coverage: dict[str, Interval]
    strata: dict[str, dict[str, int]]

    generator_metadata: GeneratorMetadataProfile


def profile_corpus(
    records: Sequence[InterimRecord], source_id: str, *, seed: int = 42
) -> CorpusProfile:
    """Compute the whole Phase 9 profile. Deterministic under `seed`."""
    grouped = group_by_parent(records)
    utterance_texts = [r.text for r in records]
    record_texts = [" ".join(p.text for p in pieces) for pieces in grouped.values()]

    placeholder_tokens = sum(len(PLACEHOLDER_TOKEN_RE.findall(t)) for t in utterance_texts)

    return CorpusProfile(
        source_id=source_id,
        n_utterances=len(records),
        n_records=len(grouped),
        utterance_chars=describe(
            [len(t) for t in utterance_texts], "chars per utterance", seed=seed
        ),
        utterance_tokens=describe(
            [len(tokenise(t)) for t in utterance_texts], "tokens per utterance", seed=seed
        ),
        record_chars=describe([len(t) for t in record_texts], "chars per record", seed=seed),
        record_tokens=describe(
            [len(tokenise(t)) for t in record_texts], "tokens per record", seed=seed
        ),
        utterances_per_record=describe(
            [len(p) for p in grouped.values()], "utterances per record", seed=seed
        ),
        vocabulary_with_placeholders=vocabulary(utterance_texts, keep_placeholders=True),
        vocabulary_without_placeholders=vocabulary(utterance_texts, keep_placeholders=False),
        placeholder_token_count=placeholder_tokens,
        utterance_duplicates=duplicate_profile(utterance_texts, "utterance", seed=seed),
        record_duplicates=duplicate_profile(record_texts, "record", seed=seed),
        junk=junk_profile(utterance_texts, seed=seed),
        coverage=coverage(records, seed=seed),
        strata={
            "sport": stratum_counts(records, "sport"),
            "competition_level": stratum_counts(records, "competition_level"),
            "region": stratum_counts(records, "region"),
            "time_band": stratum_counts(records, "time_band"),
            "training_load_hint": stratum_counts(records, "training_load_hint"),
        },
        generator_metadata=generator_metadata_profile(records),
    )
