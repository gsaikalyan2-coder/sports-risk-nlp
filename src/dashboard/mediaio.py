"""The one door between an uploaded file and the scoring page.

`tests/test_dashboard_pages.py` enforces that a module under `dashboard/` may
import from `src.dashboard` and from nowhere else under `src.`. The media layer
lives in `src.media`, so without this module the page would either violate that
rule or the rule would be quietly relaxed for one feature -- which is how a
structural constraint stops being one.

So the page asks exactly one question, `read_upload(name, bytes)`, and gets back
a `MediaResult` that already carries everything the page is allowed to render:
the words recovered, the context mapping, every stamp, and, when the file was
refused, the sentence to show instead. The page branches on `ok` and renders. It
computes nothing.

The order of operations is the point
-------------------------------------
    admit the file  ->  extract words  ->  admit the words  ->  judge the register
                                                             ->  and score either way

Each gate is cheaper and more certain than the next, and each one that fires
means no `DashboardView` is ever constructed -- so there is no number in
existence to screenshot. In particular the *text* gate runs on machine-read
words too: OCR on a photo of a bus timetable returns real words that are not
writing by an athlete about anything, and `gibberish.admit` catches the
worst of that for the same reason it catches keyboard mash. Media that survives
the first three gates is scored exactly as typed text is, by the same backend,
under the same policy.

The fourth step is not a gate. `relevance.judge` asks whether the recovered words
read as an athlete's own account, and the answer is carried on the result for the
page to render loudly. It does not withhold the score: off-register text is real
language, the number it gets is arithmetically what those words deserve, and the
honest response is to publish it next to a statement of what it is a reading of.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from src.dashboard.gibberish import admit as admit_text
from src.media.admission import admit_media
from src.media.extract import extractor_for
from src.media.facecues import (
    FACE_ONLY_STAMP,
    FACE_STAMP,
    FACE_WEIGHTS,
    face_context_weights,
    face_cue_reader,
    face_only_index,
    face_stack_status,
)
from src.media.nonverbal import (
    NONVERBAL_STAMP,
    SimulatedNonVerbalReader,
    nonverbal_context_weights,
)
from src.media.relevance import judge

__all__ = [
    "FACE_ONLY_STAMP",
    "FACE_STAMP",
    "FACE_WEIGHTS",
    "MediaResult",
    "NONVERBAL_STAMP",
    "face_stack_status",
    "media_context_weights",
    "read_upload",
]

#: Re-exported so the page can offer the switch without importing `src.media`.
media_context_weights = nonverbal_context_weights


@dataclass(frozen=True)
class MediaResult:
    """Everything the page needs about one uploaded file, already decided."""

    ok: bool
    #: The words to score. Empty whenever `ok` is False.
    text: str = ""
    kind: str = "unknown"
    #: How the words were recovered, for the line above the quoted text.
    method: str = ""
    #: The MACHINE-READ stamp. Rendered with the text, never separately.
    stamp: str = ""
    #: Why the file was refused, in words meant for the person who uploaded it.
    detail: str = ""
    #: Which gate refused it. For the page's own branching and for tests.
    reason: str = ""
    #: The non-verbal features, always computed, weighted only on request.
    context: Mapping[str, float] = field(default_factory=dict)
    nonverbal_stamp: str = ""
    dimensions: tuple[int, int] = (0, 0)
    #: Whether the recovered words read as an athlete's own account. ADVISORY:
    #: nothing here refuses an upload on the strength of it. Off-register text is
    #: real language and the scorer handles it correctly; what it is not is a
    #: reading of an athlete, and the page says so beside the number rather than
    #: withholding the number. Owner's decision, 2026-09-15.
    on_topic: bool = True
    relevance: float = 0.0
    relevance_detail: str = ""
    #: Phase 28. True when a real face was found and read under consent. False
    #: means the reading on `context` came from the simulated reader, and
    #: `context_weights` is then empty, so it multiplies by nothing.
    face_measured: bool = False
    #: Why no face was read, in words for the uploader: no consent, no library,
    #: no face, or a face too small. Empty when one was read.
    face_detail: str = ""
    #: The weights this result's context carries into the scorer. Empty unless a
    #: real face was read. The page passes this straight to `scorer_for`, so the
    #: page cannot weight a reading the reader did not actually take.
    context_weights: Mapping[str, float] = field(default_factory=dict)
    #: Phase 28b. True when the file carried no readable words but a face WAS
    #: read: there is a face-only figure to show, and there are no constructs,
    #: no spans and no risk index, because a picture contains none of those.
    face_only: bool = False
    #: The face-only figure, in [0, 1]. Meaningful only when `face_only` is True.
    face_index: float = 0.0

    def __bool__(self) -> bool:
        return self.ok


def _read_face(data: bytes, *, consent: bool):
    """The face reading, or the simulated one, and always the reason which.

    Three outcomes, and the middle one is the point: consent given and a face
    found gives a measured reading that carries weight; consent given and
    anything missing -- no library, no face, a face too small -- gives the
    simulated reading at zero weight AND the sentence saying so; no consent
    gives the simulated reading with nothing looked at. There is no fourth
    outcome in which a number appears without the reader being told where it
    came from.
    """
    reader, detail = face_cue_reader(consent=consent)
    if reader is not None:
        try:
            return reader.read(data), True, ""
        except Exception as exc:  # noqa: BLE001 - any failure falls back, loudly
            detail = str(exc)
    return SimulatedNonVerbalReader().read(data), False, detail


def read_upload(filename: str, data: bytes, *, consent: bool = False) -> MediaResult:
    """Run an uploaded file through all four gates and report the outcome.

    Returns a refusal rather than raising, at every stage, because every one of
    these outcomes is a normal thing for a person to do -- uploading a holiday
    photo, a clip with no talking, a PDF they meant to rename -- and an
    exception would turn an ordinary mistake into a stack trace.
    """
    # `consent` defaults False so that every existing caller, and every future
    # one that forgets, gets the Phase 27 behaviour: nothing looks at a face.
    admission = admit_media(filename, data)
    if not admission:
        return MediaResult(
            ok=False,
            kind=admission.kind.value,
            detail=admission.detail,
            reason=admission.reason,
            dimensions=(admission.width, admission.height),
        )

    extraction = extractor_for(admission.kind).extract(data)
    reading, measured, face_detail = _read_face(data, consent=consent)
    common = {
        "kind": admission.kind.value,
        "context": reading.features,
        "nonverbal_stamp": reading.stamp,
        "face_measured": measured,
        "face_detail": face_detail,
        "context_weights": face_context_weights(measured=measured),
        "dimensions": (admission.width, admission.height),
        "method": extraction.method,
        "stamp": extraction.stamp,
    }

    if not extraction:
        return MediaResult(ok=False, detail=extraction.reason, reason="unreadable", **common)

    # The text gate again, on machine-read words this time. An OCR pass over a
    # photo of a car park returns "P 24 HOURS PAY HERE": real characters, no
    # prose, and a lexicon that matches none of it -- which is the 0.50 problem
    # arriving through the media door instead of the paste box.
    verdict = admit_text(extraction.text)
    if not verdict:
        if common.get("face_measured"):
            # A photograph of an athlete with no writing in it. The owner asked
            # for this to produce a reading rather than a refusal, so it does --
            # from the face alone, under its own stamp, with no construct tiles
            # and no spans beside it, because neither exists for a picture.
            return MediaResult(
                ok=False,
                face_only=True,
                face_index=face_only_index(dict(common["context"])),
                detail=(
                    "No words were found in that file, so the ten psychological "
                    "signals could not be looked for. The face-only reading below "
                    "is what the picture alone supports."
                ),
                reason="face_only",
                **common,
            )
        return MediaResult(
            ok=False,
            detail=(
                f"Words were recovered from that file, but they do not read as "
                f"English prose. {verdict.detail}"
            ),
            reason=f"text_{verdict.reason}",
            **common,
        )

    # Register, not language. `admit_text` above has already established that
    # these are words; this asks whether they are an athlete talking about
    # themselves, and the answer only ever decorates the result.
    verdict = judge(extraction.text)
    return MediaResult(
        ok=True,
        text=extraction.text,
        on_topic=verdict.on_topic,
        relevance=verdict.score,
        relevance_detail=verdict.detail,
        **common,
    )
