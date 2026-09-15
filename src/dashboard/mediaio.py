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
from src.media.nonverbal import (
    NONVERBAL_STAMP,
    SimulatedNonVerbalReader,
    nonverbal_context_weights,
)
from src.media.relevance import judge

__all__ = [
    "MediaResult",
    "NONVERBAL_STAMP",
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

    def __bool__(self) -> bool:
        return self.ok


def read_upload(filename: str, data: bytes) -> MediaResult:
    """Run an uploaded file through all four gates and report the outcome.

    Returns a refusal rather than raising, at every stage, because every one of
    these outcomes is a normal thing for a person to do -- uploading a holiday
    photo, a clip with no talking, a PDF they meant to rename -- and an
    exception would turn an ordinary mistake into a stack trace.
    """
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
    reading = SimulatedNonVerbalReader().read(data)
    common = {
        "kind": admission.kind.value,
        "context": reading.features,
        "nonverbal_stamp": reading.stamp,
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
