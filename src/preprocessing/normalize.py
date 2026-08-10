"""Text normalisation -- the first step, and the one that must lose nothing.

Normalisation runs *before* de-identification, and that ordering is not
arbitrary. A de-identifier that matches `@handle` will miss `＠handle` written
with a fullwidth at-sign; one that matches `Coach Renner` will miss
`Coach Renner` joined by a non-breaking space. Every unnormalised variant
is a hole in the redaction, so normalisation is a **safety** step here, not a
cosmetic one.

The rule this module follows: **fold representation, preserve content.** Curly
quotes become straight quotes because the difference is typographic. Casing is
never touched, because casing is evidence -- `docs/annotation_guidelines.md`
treats emphatic capitals as intensity evidence, and the de-identifier's
proper-noun detection depends on capitalisation entirely. Lowercasing here
would silently disable half the redaction logic downstream.

Everything is idempotent: `normalize(normalize(t)) == normalize(t)`, asserted
in the test suite. A normaliser that keeps changing its own output cannot be
reasoned about when it appears mid-pipeline.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Characters removed outright: C0/C1 controls except tab and newline, plus the
#: zero-width family, which is invisible and therefore both a tokenisation
#: hazard and a way for an identifier to survive a string comparison.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_ZERO_WIDTH_RE = re.compile(r"[​-‏⁠﻿]")

#: Quote and dash folding. The em dash is kept as an em dash -- it is a real
#: punctuation choice in athlete speech (hesitation, self-interruption) and the
#: corpus already contains it -- but its spacing is regularised.
_QUOTE_MAP = {
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "“": '"',
    "”": '"',
    "„": '"',
    "′": "'",
    "″": '"',
    "«": '"',
    "»": '"',
}
_DASH_MAP = {
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",  # en dash -> hyphen
    "−": "-",
}

_ELLIPSIS_RE = re.compile(r"\.{4,}")
_SPACES_RE = re.compile(r"[^\S\n]+")  # horizontal whitespace only; newlines survive
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%])")
_EM_DASH_SPACING_RE = re.compile(r"\s*—\s*")


@dataclass(frozen=True)
class NormalizationReport:
    """What normalisation actually changed, per record.

    Recorded rather than discarded because a corpus paper has to be able to
    answer "what did you do to the text?" with counts instead of adjectives.
    """

    changed: bool
    original_length: int
    normalized_length: int
    control_chars_removed: int
    zero_width_removed: int
    whitespace_collapsed: int

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "changed": self.changed,
            "original_length": self.original_length,
            "normalized_length": self.normalized_length,
            "control_chars_removed": self.control_chars_removed,
            "zero_width_removed": self.zero_width_removed,
            "whitespace_collapsed": self.whitespace_collapsed,
        }


def normalize(text: str) -> str:
    """Return `text` in canonical form. Casing and wording are untouched."""
    result, _ = normalize_with_report(text)
    return result


def normalize_with_report(text: str) -> tuple[str, NormalizationReport]:
    """Normalise and report what changed."""
    original = text
    original_length = len(text)

    # NFKC folds compatibility forms -- fullwidth `＠`, ligatures, non-breaking
    # spaces -- into the ASCII-ish equivalents the downstream regexes expect.
    text = unicodedata.normalize("NFKC", text)

    control_hits = len(_CONTROL_RE.findall(text))
    text = _CONTROL_RE.sub("", text)

    zero_width_hits = len(_ZERO_WIDTH_RE.findall(text))
    text = _ZERO_WIDTH_RE.sub("", text)

    for source, target in _QUOTE_MAP.items():
        text = text.replace(source, target)
    for source, target in _DASH_MAP.items():
        text = text.replace(source, target)

    text = text.replace("…", "...")
    text = _ELLIPSIS_RE.sub("...", text)

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    before_ws = text
    text = _SPACES_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    whitespace_collapsed = len(before_ws) - len(text)

    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _EM_DASH_SPACING_RE.sub(" — ", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()

    report = NormalizationReport(
        changed=text != original,
        original_length=original_length,
        normalized_length=len(text),
        control_chars_removed=control_hits,
        zero_width_removed=zero_width_hits,
        whitespace_collapsed=max(whitespace_collapsed, 0),
    )
    return text, report
