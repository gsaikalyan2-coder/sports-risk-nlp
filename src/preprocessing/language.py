"""A coarse, offline language filter.

**What this claims.** It separates English from a handful of other European
languages well enough to keep obviously-non-English records out of an
English-only corpus.

**What it does not claim.** It is not a language identifier. It has no model,
it was not evaluated against a benchmark, and it will do poorly on very short
text, code-switched text, and any language outside `STOPWORD_PROFILES`. The
paper should describe it as a filter with a stated threshold, not as language
identification, and `docs/preprocessing.md` says so.

Why not `langdetect` or `fasttext`? Both are better. Both also add a dependency
-- in fasttext's case a downloaded model binary -- to a pipeline that has to
run from a fresh clone with no network (`CLAUDE.md` sec.7). The current corpus
is 100% generated English, so the filter has nothing to do yet; it exists so
that the day real text arrives under OPEN-011 there is a declared, auditable
gate rather than an improvised one. When that day comes, swapping the
implementation behind `detect_language` is a contained change.

**Uncertain records are flagged, not deleted.** A record below the confidence
threshold is marked `uncertain` and kept for review. Silently dropping records
produces a corpus whose size nobody can explain, which is the same failure the
ingestion layer refuses at Phase 7.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .lexicons import STOPWORD_PROFILES

#: Below this many tokens, the stopword signal is noise. Short records are
#: returned as `uncertain` rather than guessed at.
MIN_TOKENS_FOR_DECISION = 5

#: Minimum share of tokens matching the winning profile.
DEFAULT_THRESHOLD = 0.10

#: Exclusion thresholds. These are deliberately stricter than the thresholds
#: for *identifying* a language, because the two decisions have different
#: costs. Mislabelling a record's language is a metadata error. Excluding it
#: deletes it from the corpus, and a deleted record cannot be recovered by a
#: later analyst noticing the mistake.
#:
#: So exclusion carries the burden of proof: a non-English profile must both
#: clear an absolute score and beat English by a margin. One shared function
#: word is not evidence.
MIN_EXCLUSION_SCORE = 0.20
MIN_EXCLUSION_MARGIN = 0.10

_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass(frozen=True)
class LanguageVerdict:
    """One language decision, with the evidence that produced it."""

    language: str  # ISO 639-1 code, or "und" for undetermined
    score: float  # share of tokens matching the winning profile
    margin: float  # winning score minus runner-up; low margin = ambiguous
    token_count: int
    uncertain: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "score": round(self.score, 4),
            "margin": round(self.margin, 4),
            "token_count": self.token_count,
            "uncertain": self.uncertain,
        }


def detect_language(text: str, *, threshold: float = DEFAULT_THRESHOLD) -> LanguageVerdict:
    """Score `text` against each stopword profile and return the best match."""
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    total = len(tokens)
    if total < MIN_TOKENS_FOR_DECISION:
        return LanguageVerdict("und", 0.0, 0.0, total, uncertain=True)

    scores = {
        code: sum(1 for t in tokens if t in profile) / total
        for code, profile in STOPWORD_PROFILES.items()
    }
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    (best_code, best_score), (_, runner_up) = ranked[0], ranked[1]
    margin = best_score - runner_up

    uncertain = best_score < threshold
    return LanguageVerdict(
        language=best_code if not uncertain else "und",
        score=best_score,
        margin=margin,
        token_count=total,
        uncertain=uncertain,
    )


def is_english(text: str, *, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Convenience predicate. `uncertain` counts as not-confidently-English."""
    verdict = detect_language(text, threshold=threshold)
    return verdict.language == "en" and not verdict.uncertain


def should_exclude(text: str) -> tuple[bool, str]:
    """Decide whether to drop `text` as non-English. Returns `(drop, reason)`.

    This, not `is_english`, is what the pipeline calls. The difference is the
    whole point: `is_english` asks "is this confidently English?" and answers
    no for a great deal of perfectly good English. Using it as a drop rule
    would delete every short, sparse, or idiomatic record -- which in this
    corpus means the terse, high-arousal utterances that carry the most
    construct signal.

    A record is dropped only when some other language both clears
    `MIN_EXCLUSION_SCORE` and beats English by `MIN_EXCLUSION_MARGIN`.
    Everything else is kept, including everything the filter is unsure about.
    """
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    total = len(tokens)
    if total < MIN_TOKENS_FOR_DECISION:
        return False, "too_short_to_judge"

    scores = {
        code: sum(1 for t in tokens if t in profile) / total
        for code, profile in STOPWORD_PROFILES.items()
    }
    english = scores.get("en", 0.0)
    other_code, other_score = max(
        ((c, s) for c, s in scores.items() if c != "en"), key=lambda item: item[1]
    )

    if other_score >= MIN_EXCLUSION_SCORE and other_score - english >= MIN_EXCLUSION_MARGIN:
        return True, f"scores_as_{other_code}({other_score:.2f}_vs_en_{english:.2f})"
    return False, "kept"
