"""Phase 29: one profile from a photograph and a press conference.

The owner's request, 2026-09-19: upload an athlete's picture, paste a link to a
press conference, get the metrics and one final score. This module is the whole
of that computation, so the page under `dashboard/` renders and computes nothing
-- the same division `mediaio.py` keeps, and for the same reason: the page-shell
tests forbid a module under `dashboard/` from importing anything under `src.`
except `src.dashboard`, and a rule with one exception is not a rule.

What the final score is made of
-------------------------------
Two channels, both reported, both visible in the arithmetic:

* **Words** -- the transcript, de-identified, then scored by the same lexicon
  backend and the same fusion layer that score typed text. This produces the ten
  construct probabilities, their contributions and the risk index. It is the
  only channel with evidence behind it: every construct can point at the words
  that triggered it.
* **Face** -- `negative_valence` and `arousal` from the largest detected face,
  under consent, entering `LinearRiskScorer.context` at the declared weights in
  `facecues.FACE_WEIGHTS`.

The final score is the risk index with both channels in, multiplied by 100. The
words-only score is computed alongside and reported next to it, so the face's
contribution is a number the reader can see rather than a claim they have to
take.

What this module refuses to do
-------------------------------
* It does not invent a score when a channel is missing. No transcript and no
  face means no number at all. A transcript and no face means the words-only
  score, said plainly. A face and no transcript means the face-only figure from
  `facecues.face_only_index`, under its own stamp, with no constructs beside it
  because a photograph contains none.
* It does not skip de-identification. Every transcript passes through
  `src.preprocessing.deidentify` before the scorer or the screen sees it.
* It does not make a claim about the person in the video. Every surface it
  produces carries a stamp, and `docs/ethics.md` sec.1 and sec.3.3 are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.dashboard.gibberish import admit as admit_text
from src.dashboard.view import build_view, scorer_for
from src.media.facecues import (
    FACE_ONLY_STAMP,
    face_context_weights,
    face_cue_reader,
    face_only_index,
    face_stack_status,
)
from src.media.pressroom import (
    PRESS_STAMP,
    PressTranscript,
    TranscriptUnavailable,
    fetch_transcript,
    transcript_stack_status,
)
from src.media.relevance import judge

__all__ = [
    "FACE_ONLY_STAMP",
    "PRESS_STAMP",
    "MatchDayProfile",
    "build_profile",
    "face_stack_status",
    "transcript_stack_status",
]


@dataclass(frozen=True)
class MatchDayProfile:
    """Everything the page shows, already decided. The page branches and renders."""

    #: True when there is a final score. False means every channel failed and the
    #: page shows the reasons instead of a number.
    ok: bool = False
    #: The view behind the score. None on the face-only and refusal paths.
    view: object | None = None
    #: 0-100. The headline. Meaningful only when `ok`.
    score_100: int = 0
    #: 0-100 from the words alone, for the comparison beside the headline.
    text_only_100: int = 0
    #: The face-only figure, used when there are cues but no words.
    face_only_100: int = 0

    transcript: PressTranscript | None = None
    transcript_detail: str = ""

    face_measured: bool = False
    face_features: dict = field(default_factory=dict)
    face_weights: dict = field(default_factory=dict)
    face_stamp: str = ""
    face_detail: str = ""

    on_topic: bool = True
    relevance: float = 0.0
    relevance_detail: str = ""
    deidentified: bool = False
    replacements: int = 0

    def __bool__(self) -> bool:
        return self.ok


def _deidentify(text: str) -> tuple[str, int]:
    """Names out before anything else sees the words.

    Wrapped in a try/except on purpose: the de-identifier is the Phase 5 module
    and its surface has moved before. If it cannot be called, the transcript is
    NOT scored -- the failure is refusing to proceed, not proceeding without it.
    """
    from src.preprocessing import deidentify as module  # noqa: PLC0415

    reporter = getattr(module, "deidentify_with_report", None)
    if callable(reporter):
        cleaned, report = reporter(text)
        if cleaned.strip():
            # `replacements` is a per-placeholder mapping; the page wants one
            # number, and `total_replacements` is the property that gives it.
            return cleaned, int(getattr(report, "total_replacements", 0) or 0)
    for name in ("deidentify", "deidentify_text", "scrub", "apply"):
        function = getattr(module, name, None)
        if callable(function):
            result = function(text)
            if isinstance(result, tuple):
                cleaned = str(result[0])
            elif isinstance(result, str):
                cleaned = result
            else:
                cleaned = str(getattr(result, "text", "") or "")
            if cleaned.strip():
                changed = sum(
                    1 for a, b in zip(text.split(), cleaned.split(), strict=False) if a != b
                )
                return cleaned, changed
    raise RuntimeError(
        "src.preprocessing.deidentify exposes no callable this bridge recognises, so "
        "the transcript was not scored. docs/ethics.md sec.3 requires de-identification "
        "of real text and this is that requirement refusing to be skipped."
    )


def _read_face(data: bytes | None, *, consent: bool):
    """The face channel. Returns (features, measured, stamp, detail)."""
    if not data:
        return {}, False, "", ""
    reader, detail = face_cue_reader(consent=consent)
    if reader is None:
        return (
            {},
            False,
            "",
            detail or ("No consent was given for the photograph, so nothing looked at the face."),
        )
    try:
        reading = reader.read(data)
    except Exception as exc:  # noqa: BLE001 - every failure falls back, loudly
        return {}, False, "", str(exc)
    return dict(reading.features), True, reading.stamp, ""


def build_profile(
    *,
    policy: str,
    backend,
    url: str = "",
    photo: bytes | None = None,
    consent: bool = False,
) -> MatchDayProfile:
    """One profile from a link, a photograph, or both.

    `backend` is passed in rather than constructed here so the page keeps its
    `@st.cache_resource` lexicon and this module stays importable by a test with
    no Streamlit in the process.
    """
    features, measured, face_stamp, face_detail = _read_face(photo, consent=consent)
    weights = face_context_weights(measured=measured)

    transcript: PressTranscript | None = None
    transcript_detail = ""
    if url.strip():
        try:
            transcript = fetch_transcript(url)
        except TranscriptUnavailable as exc:
            transcript_detail = str(exc)
        except Exception as exc:  # noqa: BLE001
            transcript_detail = f"That link could not be read ({type(exc).__name__})."

    # --- no words -----------------------------------------------------------
    if transcript is None:
        if measured:
            return MatchDayProfile(
                ok=False,
                face_only_100=round(face_only_index(features) * 100),
                face_measured=True,
                face_features=features,
                face_weights=weights,
                face_stamp=face_stamp,
                transcript_detail=transcript_detail
                or "No press conference link was given, so there are no words to score.",
            )
        return MatchDayProfile(
            ok=False,
            transcript_detail=transcript_detail or "No press conference link was given.",
            face_detail=face_detail,
        )

    # --- words, de-identified before anything else sees them ----------------
    cleaned, replaced = _deidentify(transcript.text)

    admission = admit_text(cleaned)
    if not admission:
        return MatchDayProfile(
            ok=False,
            transcript=transcript,
            transcript_detail=(
                "Words came back from that link, but they do not read as English "
                f"prose, so nothing was scored. {admission.detail}"
            ),
            face_measured=measured,
            face_features=features,
            face_weights=weights,
            face_stamp=face_stamp,
            face_detail=face_detail,
            deidentified=True,
            replacements=replaced,
        )

    verdict = judge(cleaned)
    view = build_view(
        text=cleaned,
        backend=backend,
        scorer=scorer_for(policy, context_weights=weights),
        context=features,
    )
    text_only = build_view(text=cleaned, backend=backend, scorer=scorer_for(policy))

    return MatchDayProfile(
        ok=True,
        view=view,
        score_100=round(view.risk.value * 100),
        text_only_100=round(text_only.risk.value * 100),
        transcript=transcript,
        face_measured=measured,
        face_features=features,
        face_weights=weights,
        face_stamp=face_stamp,
        face_detail=face_detail,
        on_topic=verdict.on_topic,
        relevance=verdict.score,
        relevance_detail=verdict.detail,
        deidentified=True,
        replacements=replaced,
    )
