"""Phase 29: a press conference on the web, turned into words this project scores.

What the owner asked for (2026-09-19)
-------------------------------------
Give the page a photograph of an athlete and a link to a press conference, and
have it report the metrics and one final score. This module is the link half.
`src/media/facecues.py` is the picture half, and
`src/dashboard/matchday.py` is the bridge that puts the two together.

How the words are obtained, in order
------------------------------------
1. **Published captions**, via `youtube-transcript-api`. This reads the caption
   track the video already publishes. It downloads no video, no audio and no
   pixels, which is both the fastest route and the one with the smallest
   footprint on somebody else's servers.
2. **Speech recognition**, via `faster-whisper` over audio pulled by `yt-dlp` --
   only if both are installed. A clean checkout has neither, and a Streamlit
   Community Cloud app will not carry them, so this path is optional by
   construction and its absence is reported rather than hidden.
3. **Nothing.** If neither works the page says which one failed and produces NO
   NUMBER. That is the Phase 27 rule applied to a third door: an input that
   cannot be read produces no number, never a zero and never a midpoint.

What comes back is a `PressTranscript`: the words, the route they came by, a
`MACHINE-READ` stamp, and the video id. The words then go through exactly the
pipeline typed text goes through -- de-identification, the language gate, the
register test, the ten constructs -- because they are words, and this project
scores words.

De-identification is not optional here
--------------------------------------
A press conference names people: the speaker, team-mates, opponents, reporters.
`src/preprocessing/deidentify.py` exists for precisely this and is applied to
every transcript before anything else sees it, so what reaches the scorer and
the screen carries placeholders rather than names. `docs/ethics.md` sec.3 requires
it for any real text, and a transcript is the first real text this project has
ever scored.

What this does not make permissible
-----------------------------------
Reading a public figure's press conference does not license a claim about that
person's psychological state. `docs/ethics.md` sec.1, sec.3.3 and sec.13.5 are
unchanged: this is research and decision-support over public material, every
surface says so, and the identity is stripped on the way in. Nothing is stored:
the transcript lives in a local variable for one render.

Blocked by default (added 2026-09-19, before this module's first commit)
--------------------------------------------------------------------------
This module was built and then found, on review, to be exactly the case
`docs/ethics.md` sec.13.4-13.5 and sec.2.3 already forbid in writing: a named,
identifiable public figure's own words, fetched and scored, with no consent
route available because the subject never agreed to any of it. `fetch_transcript`
therefore refuses unconditionally unless `ETHICS_GATE_ENV`
(`SRN_MATCHDAY_REAL_ATHLETES`) is set in the environment -- the same shape as
`GatedRealReader` in `src/media/nonverbal.py` before Phase 28 discharged it for
facial cues. See `docs/ethics.md` sec.15 for what an owner decision to set this
flag would actually have to weigh, and `CLAUDE.md` sec.14 for the phase record.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

__all__ = [
    "ETHICS_GATE_ENV",
    "PRESS_STAMP",
    "PressTranscript",
    "TranscriptUnavailable",
    "fetch_transcript",
    "transcript_stack_status",
    "video_id",
]

#: BLOCKED UNTIL EXPLICIT OWNER SIGN-OFF (see CLAUDE.md sec.14, docs/ethics.md
#: sec.15). Unlike Phase 28's face-cue reader, there is no consent route this
#: module can implement: the subject of the press conference did not agree to
#: this project scoring them, and docs/ethics.md sec.13.4 already states in
#: writing that public availability of a recording is not consent to
#: psychological inference about the person in it. A flag the *owner* sets
#: locally is therefore the only gate that fits -- it is a deliberate decision
#: to run the feature anyway, not a box a reader ticks on a stranger's behalf.
ETHICS_GATE_ENV = "SRN_MATCHDAY_REAL_ATHLETES"

PRESS_STAMP = (
    "MACHINE-READ FROM A PUBLISHED PRESS CONFERENCE, NOT AN INTERVIEW WITH THIS PROJECT: "
    "these words were taken from the video's own caption track or from automatic speech "
    "recognition, both of which mishear. Names have been replaced with placeholders "
    "before scoring. Nothing was stored, and no claim is made about any identifiable "
    "person."
)

#: Accepts the shapes a person actually pastes: a watch URL, a share link, an
#: embed, a Shorts link, or a bare eleven-character id.
_PATTERNS = (
    re.compile(r"(?:v=|/v/|/embed/|/shorts/|youtu\.be/|/live/)([A-Za-z0-9_-]{11})"),
    re.compile(r"^([A-Za-z0-9_-]{11})$"),
)


class TranscriptUnavailable(RuntimeError):
    """No words could be obtained from that link, and the reason is the message."""


@dataclass(frozen=True)
class PressTranscript:
    """The words of a press conference, and the statement of where they came from."""

    text: str
    route: str
    video: str
    stamp: str = PRESS_STAMP
    language: str = ""
    segments: int = 0

    def __post_init__(self) -> None:
        if "MACHINE-READ" not in self.stamp.upper():
            raise ValueError(
                "A PressTranscript without its MACHINE-READ stamp is indistinguishable "
                "from something an athlete wrote for this project. See this module's "
                "docstring."
            )
        if not self.text.strip():
            raise ValueError(
                "A PressTranscript may not be empty. An empty transcript scored as text "
                "lands the index on exactly 0.50; refusing is the honest answer. See "
                "CLAUDE.md sec.12.3."
            )


def video_id(url: str) -> str:
    """The eleven-character id inside whatever the reader pasted.

    Raises rather than returning an empty string, because an empty id would be
    passed happily to the transcript API and come back as a confusing upstream
    error about a video that does not exist.
    """
    candidate = (url or "").strip()
    for pattern in _PATTERNS:
        found = pattern.search(candidate)
        if found:
            return found.group(1)
    raise TranscriptUnavailable(
        "That does not look like a YouTube link. Paste the address from the browser "
        "bar of the press conference, for example "
        "https://www.youtube.com/watch?v=XXXXXXXXXXX"
    )


@dataclass(frozen=True)
class TranscriptStackStatus:
    """Which of the two routes are installed here, named individually."""

    captions: bool
    speech: bool
    detail: str = ""

    def __bool__(self) -> bool:
        return self.captions or self.speech


def transcript_stack_status() -> TranscriptStackStatus:
    """Probed per call, never cached at import, so an install takes effect on restart."""
    captions = True
    try:
        import youtube_transcript_api  # noqa: PLC0415, F401
    except ImportError:
        captions = False
    speech = True
    for module in ("yt_dlp", "faster_whisper"):
        try:
            __import__(module)
        except ImportError:
            speech = False
    if captions and speech:
        detail = "Captions and speech recognition are both available."
    elif captions:
        detail = (
            "Captions only. Videos that publish no caption track cannot be read here; "
            "installing yt-dlp and faster-whisper adds the speech route."
        )
    elif speech:
        detail = "Speech recognition only; youtube-transcript-api is not installed."
    else:
        detail = (
            "Neither youtube-transcript-api nor yt-dlp plus faster-whisper is "
            "installed, so no press conference can be read."
        )
    return TranscriptStackStatus(captions=captions, speech=speech, detail=detail)


# ---------------------------------------------------------------------------
# Route 1: the caption track
# ---------------------------------------------------------------------------


def _from_captions(video: str, languages: tuple[str, ...] = ("en",)) -> PressTranscript:
    """The published captions, through whichever API version is installed.

    youtube-transcript-api changed shape at 1.0: the old module exposed the
    classmethod `get_transcript`, the new one an instance with `fetch`. Both are
    tried, newest first, because a project that pins neither should not break on
    whichever one a reader's machine happens to have.
    """
    from youtube_transcript_api import YouTubeTranscriptApi  # noqa: PLC0415

    entries: list[dict] = []
    language = ""
    if hasattr(YouTubeTranscriptApi, "fetch") and not isinstance(
        getattr(YouTubeTranscriptApi, "fetch", None), classmethod
    ):
        fetched = YouTubeTranscriptApi().fetch(video, languages=languages)
        language = getattr(fetched, "language_code", "") or ""
        entries = [
            {"text": getattr(snippet, "text", "")} for snippet in getattr(fetched, "snippets", [])
        ]
    else:  # pragma: no cover - the pre-1.0 API
        entries = YouTubeTranscriptApi.get_transcript(video, languages=list(languages))
        language = languages[0]

    text = _join(entry.get("text", "") for entry in entries)
    if not text:
        raise TranscriptUnavailable(
            "That video publishes a caption track, but it contained no words."
        )
    return PressTranscript(
        text=text,
        route="published captions",
        video=video,
        language=language,
        segments=len(entries),
    )


# ---------------------------------------------------------------------------
# Route 2: speech recognition over the audio
# ---------------------------------------------------------------------------


def _from_speech(video: str, *, max_seconds: int = 600) -> PressTranscript:
    """Audio via yt-dlp, words via faster-whisper. Optional, and absent by default.

    Bounded at ten minutes of audio on purpose: a full press conference is long,
    a Streamlit rerun is not, and a page that appears to hang is a page a reader
    reloads in the middle of a download.
    """
    import tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    import yt_dlp  # noqa: PLC0415
    from faster_whisper import WhisperModel  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as workdir:
        target = str(Path(workdir) / "audio.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "outtmpl": target,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(
                f"https://www.youtube.com/watch?v={video}", download=True
            )
            path = downloader.prepare_filename(info)
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(path, beam_size=1, language="en")
        collected = []
        for segment in segments:
            if segment.start > max_seconds:
                break
            collected.append(segment.text)
    text = _join(collected)
    if not text:
        raise TranscriptUnavailable("Nothing was recognised in that video's audio.")
    return PressTranscript(
        text=text,
        route="speech recognition (faster-whisper tiny.en)",
        video=video,
        language="en",
        segments=len(collected),
    )


def _join(parts) -> str:
    """One passage of prose out of caption fragments.

    Caption tracks arrive as short lines with bracketed sound events and stray
    newlines. Those are stripped rather than scored: "[APPLAUSE]" is not an
    athlete saying anything, and a lexicon that saw it would be matching on the
    video's furniture.
    """
    cleaned = []
    for part in parts:
        line = re.sub(r"\[[^\]]*\]", " ", str(part))
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            cleaned.append(line)
    return " ".join(cleaned)


# ---------------------------------------------------------------------------
# The public entry point
# ---------------------------------------------------------------------------


def fetch_transcript(url: str, *, allow_speech: bool = True) -> PressTranscript:
    """Words from a press-conference link, by the cheapest route that works.

    Captions first, speech second, and a refusal that names both failures third.
    Every failure mode returns the same exception type carrying a sentence meant
    for the person who pasted the link, because "HTTP 404 from an upstream
    library" tells a coach nothing about what to do next.

    Refuses unconditionally unless `ETHICS_GATE_ENV` is set. This is the gate
    named in this module's docstring: fetching and scoring a real, identifiable
    public figure's own words is a materially different act from scoring a
    reader's own pasted sentences, and `docs/ethics.md` sec.13.4-13.5 already
    prohibit exactly this in writing. Nothing about setting the flag makes the
    prohibition go away -- see sec.15 for what has to be true before it is ever
    set on a deployment another person can reach.
    """
    # Shape first: telling a reader their paste is not a YouTube link carries no
    # privacy weight and needs no gate. Only once there is a real video id on the
    # table does the ethics question -- may this project fetch and score it --
    # apply, so the gate sits here rather than at the top of the function.
    video = video_id(url)
    if not os.environ.get(ETHICS_GATE_ENV):
        raise TranscriptUnavailable(
            "Reading a press conference is disabled in this build. Scoring a real, "
            "identifiable public figure from their own published words is not "
            "something this project's ethics policy currently permits -- see "
            "docs/ethics.md sec.15 and CLAUDE.md sec.14. It is not enabled by "
            "ticking the photo-consent box above: that consent covers the "
            "uploader's own photograph, not a third party's press conference."
        )
    status = transcript_stack_status()
    reasons: list[str] = []

    if status.captions:
        try:
            return _from_captions(video)
        except TranscriptUnavailable as exc:
            reasons.append(str(exc))
        except Exception as exc:  # noqa: BLE001 - upstream raises many distinct types
            reasons.append(f"Captions could not be read ({type(exc).__name__}).")
    else:
        reasons.append("youtube-transcript-api is not installed.")

    if allow_speech and status.speech:
        try:
            return _from_speech(video)
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"Speech recognition failed ({type(exc).__name__}).")
    elif allow_speech:
        reasons.append("yt-dlp plus faster-whisper is not installed, so audio was not read.")

    raise TranscriptUnavailable(
        "No words could be read from that link, so nothing was scored. " + " ".join(reasons)
    )
