"""Phase 27: reading an uploaded photo or video, and refusing most of them.

Three modules, in the order a file passes through them:

* `admission` -- is this file a photo or a video at all, and is it worth reading?
  Pure Python over the raw bytes: magic numbers, container boxes and header
  fields. No decoder, no dependency, no network. This is the "ignore the
  unwanted media" half, and it runs first so that nothing downstream ever sees a
  file the gate refused.
* `extract`   -- pull *text* out of an admitted file: characters from a photo,
  speech from a video. Protocol plus swappable backends, with a backend that
  honestly reports it cannot read anything when the optional tools are absent,
  rather than returning an empty string that the scorer would treat as silence.
* `facecues`  -- Phase 28. Two bounded cues read from a real detected face, under
  consent, carrying declared weight into the index. See its docstring for the
  engine, the three conditions, and what it refuses to claim.
* `nonverbal` -- the face-and-voice channel. Separate module, separate stamp,
  separate weight, and off by default. See its docstring for why it is the most
  dangerous file in this repository and what holds it down.

The rule that governs the whole package: **the risk index is produced from
words.** A photo contributes by yielding words; a video contributes by yielding
words. Anything read off a face or a voice enters through
`LinearRiskScorer.context`, whose weights default to empty, so the text-only
path stays numerically identical -- the property `tests/test_risk.py` already
guards and which this package is not permitted to break.

Nothing here persists anything. Uploaded bytes live in a local variable for the
duration of one render, exactly as pasted text does.
"""

from .admission import (
    MAX_BYTES,
    MediaAdmission,
    MediaKind,
    admit_media,
    sniff,
)
from .extract import (
    MediaExtraction,
    NullExtractor,
    TesseractOCR,
    TextExtractor,
    WhisperTranscriber,
    extractor_for,
)
from .facecues import (
    FACE_STAMP,
    FACE_WEIGHTS,
    FaceCueReader,
    FaceCueUnavailable,
    face_context_weights,
    face_cue_reader,
    face_stack_status,
)
from .nonverbal import (
    FACE_FEATURES,
    NONVERBAL_STAMP,
    NonVerbalReader,
    NonVerbalReading,
    SimulatedNonVerbalReader,
    nonverbal_context_weights,
)
from .relevance import (
    ON_TOPIC_THRESHOLD,
    RelevanceVerdict,
    judge,
)

__all__ = [
    "FACE_FEATURES",
    "FACE_STAMP",
    "FACE_WEIGHTS",
    "FaceCueReader",
    "FaceCueUnavailable",
    "face_context_weights",
    "face_cue_reader",
    "face_stack_status",
    "MAX_BYTES",
    "MediaAdmission",
    "MediaKind",
    "MediaExtraction",
    "NONVERBAL_STAMP",
    "NonVerbalReader",
    "NonVerbalReading",
    "NullExtractor",
    "SimulatedNonVerbalReader",
    "TesseractOCR",
    "TextExtractor",
    "WhisperTranscriber",
    "ON_TOPIC_THRESHOLD",
    "RelevanceVerdict",
    "judge",
    "admit_media",
    "extractor_for",
    "nonverbal_context_weights",
    "sniff",
]
