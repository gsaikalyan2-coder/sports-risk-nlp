"""Getting words out of an admitted photo or video.

The contract
------------
An extractor is handed bytes that `admission.admit_media` has already accepted,
and returns a `MediaExtraction`: the text it found, what it used to find it, and
a stamp saying so. It never returns a bare string, for the same reason
`ScoreSurface` never holds a bare float -- text whose origin has been stripped
off is about to be scored as if the athlete had typed it, and "the athlete wrote
this" and "a decoder guessed this off a blurry frame" are different claims.

The absent-backend problem, and why `NullExtractor` is not a no-op
------------------------------------------------------------------
OCR needs the Tesseract engine (a system package, not a Python one);
transcription needs a speech model. Neither is in `requirements-base.txt` and
neither may be, because the Phase 6 reproducibility property is that a reviewer
runs this artifact with no account and no install beyond the pinned
requirements. Both are therefore genuinely absent in a clean checkout, which is
why the absent-backend path below is the normal path rather than an edge case.

The tempting shape is an extractor that returns `""` when its backend is
missing. That is the single worst option available, and it is worth saying why
at length, because it looks like the safe one: an empty string flows into
`LexiconBackend`, matches nothing, produces ten probabilities of 0.0, sums to a
raw score of 0.0, and the logistic squash returns an index of exactly 0.50. The
page then reports a psychological score of 50 out of 100 for a photo nobody
could read. Every step is correct and the result is fabricated. It is the same
defect `gibberish.py` was written to close, arriving through a different door.

So `NullExtractor` returns `ok=False` and a reason, the caller refuses to build
a view, and the page says the photo could not be read. No number is produced.
The absence of a capability is reported as an absence, never as a zero.
"""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.media.admission import MediaKind

#: Where to find the Tesseract binary.
#:
#: Defaults to the bare name, resolved through PATH, which is what a Linux
#: container and a Homebrew install both give. It is overridable because the
#: Windows installer offers "add to PATH" as an unticked checkbox, so the single
#: most likely outcome of a correct Windows install is an engine that exists at
#: C:\Program Files\Tesseract-OCR\tesseract.exe and is invisible to every
#: subprocess call. Without the override the only fix is editing the system PATH
#: and restarting the shell, and the symptom in the meantime is a photo path
#: that refuses everything for a reason that sounds like the engine is missing
#: when it is installed.
#:
#: Read from the environment on every call rather than captured at import, for
#: the reason `theme.cognitive_layer_enabled()` gives: a value captured at import
#: cannot be changed by a test, and drifts from whatever the running process
#: actually consults.
TESSERACT_CMD_ENV = "SRN_TESSERACT_CMD"


def tesseract_command() -> str:
    """The binary to invoke. `SRN_TESSERACT_CMD`, or plain `tesseract`."""
    return os.getenv(TESSERACT_CMD_ENV, "").strip() or "tesseract"


#: Prefixed to every extraction, so text pulled off a picture cannot be quoted
#: as something an athlete wrote. Contains the word MACHINE-READ for the same
#: reason `SIMULATED_STAMP` contains SIMULATED: a chip gets cropped, a sentence
#: travels.
EXTRACTION_TOKEN = "MACHINE-READ"

EXTRACTION_STAMP = (
    "MACHINE-READ TEXT: these words were recovered from an uploaded file by a "
    "decoder, not typed by anyone. Recovery is imperfect and the words below may "
    "differ from what was actually written or said."
)


@dataclass(frozen=True)
class MediaExtraction:
    """Text recovered from a file, inseparable from how it was recovered.

    `ok` False means nothing usable came out, and `reason` says why in words
    meant for the person who uploaded it. `text` is then empty and must not be
    scored -- see this module's docstring for what happens if it is.
    """

    ok: bool
    text: str
    method: str
    stamp: str
    reason: str = ""

    def __post_init__(self) -> None:
        if EXTRACTION_TOKEN not in self.stamp.upper():
            raise ValueError(
                "MediaExtraction has no MACHINE-READ provenance stamp. Text with its "
                "origin stripped off is about to be scored as if an athlete typed it; "
                "see this module's docstring."
            )
        if self.ok and not self.text.strip():
            raise ValueError(
                "MediaExtraction(ok=True) with no text. An extractor that found "
                "nothing must report ok=False with a reason, because an empty string "
                "scores 0.50 rather than failing."
            )

    def __bool__(self) -> bool:
        return self.ok


@runtime_checkable
class TextExtractor(Protocol):
    """What the page may ask of an extractor. One method, bytes in, text out."""

    name: str

    def available(self) -> bool:  # pragma: no cover - Protocol
        ...

    def extract(self, data: bytes) -> MediaExtraction:  # pragma: no cover - Protocol
        ...


def _installed(module: str) -> bool:
    """True when `module` can be imported without importing it.

    `find_spec` rather than a try/import, so a heavy optional dependency is not
    pulled into the process merely to discover whether it is there -- the page
    calls this on every render.
    """
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # pragma: no cover - defensive
        return False


class NullExtractor:
    """The honest floor: reads nothing, and says so.

    Used whenever the optional backend for a kind of file is not installed. It
    is the default in a clean checkout, which means the media path ships in a
    state where it refuses rather than one where it invents.
    """

    def __init__(self, kind: MediaKind, missing: str) -> None:
        self.name = f"none ({kind.value})"
        self._kind = kind
        self._missing = missing

    def available(self) -> bool:
        return False

    def extract(self, data: bytes) -> MediaExtraction:
        noun = "photo" if self._kind is MediaKind.IMAGE else "video"
        return MediaExtraction(
            ok=False,
            text="",
            method=self.name,
            stamp=EXTRACTION_STAMP,
            reason=(
                f"This build cannot read words out of a {noun}: {self._missing} is not "
                "installed, or is installed somewhere this process cannot see. Nothing "
                "was scored, because a file that could not be read has no score. Paste "
                "the words in as text and they will be scored normally."
            ),
        )


class TesseractOCR:
    """Characters out of a photo, by running the Tesseract engine directly.

    Which Tesseract, and why not through a wrapper
    -----------------------------------------------
    This calls the upstream engine from https://github.com/tesseract-ocr/tesseract
    (Apache-2.0, LSTM engine, v4+) as a subprocess. It used to go through
    `pytesseract`, which is a thin third-party Python wrapper that shells out to
    exactly the same binary after writing the image to a temporary file. Going
    direct removes two dependencies (`pytesseract` and, with it, `Pillow`, which
    was only there to hand the wrapper a decoded image), removes the temporary
    file, and removes a layer between the provenance stamp and the thing that
    actually did the reading.

    Tesseract links Leptonica and decodes PNG, JPEG, TIFF, GIF, WebP and BMP
    itself, so nothing here needs to decode an image at all -- the bytes go in on
    stdin and text comes back on stdout, via the documented `tesseract stdin
    stdout` pseudo-filenames.

    The availability bug this replaces
    -----------------------------------
    The previous check asked whether `pytesseract` and `PIL` could be imported.
    Both are pip packages and both install cleanly on a machine with no OCR
    engine on it, so on such a machine `available()` returned True, the extractor
    was selected over `NullExtractor`, and every upload died in the generic
    exception handler reporting "TesseractNotFoundError" -- a Python type name,
    to a coach, in place of the sentence explaining that this build cannot read
    photos. The check now runs the binary, which is the only thing that can
    answer the question, and the honest floor is selected when it is absent.

    Language data is checked separately, because a present engine with no
    `eng.traineddata` is a third state that fails at the point of use with a
    message about a file path.
    """

    #: Page segmentation mode. 6 is "assume a single uniform block of text",
    #: which is what a photographed journal page, a note or a screenshot of a
    #: message actually is. The Tesseract default of 3 (fully automatic page
    #: segmentation) hunts for columns and headers in what is usually a single
    #: paragraph, and on a phone photo it tends to split one block into fragments
    #: ordered by position rather than by reading order.
    PSM = "6"

    #: OCR engine mode 1 is the LSTM engine alone. The default (3) falls back to
    #: the legacy character matcher when the LSTM is unavailable, and the legacy
    #: path needs its own traineddata that modern distributions no longer ship --
    #: so the default's fallback is, in practice, a different and worse error.
    OEM = "1"

    LANGUAGE = "eng"
    TIMEOUT_S = 60

    name = "tesseract"

    def __init__(self) -> None:
        self._version: str | None = None

    # -- availability ------------------------------------------------------

    def _run(self, args: list[str], data: bytes | None = None, timeout: int = 10):
        import subprocess  # noqa: PLC0415

        return subprocess.run(  # noqa: S603
            [tesseract_command(), *args],
            input=data,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def version(self) -> str:
        """The engine build, as the engine reports it. Cached per instance."""
        if self._version is None:
            try:
                result = self._run(["--version"])
                first = result.stdout.decode("utf-8", "replace").splitlines()
                self._version = first[0].strip() if first else "tesseract (unknown build)"
            except (OSError, ValueError):  # pragma: no cover - environment dependent
                self._version = ""
        return self._version

    def languages(self) -> tuple[str, ...]:
        """Installed traineddata, from `--list-langs`. Empty when none or absent."""
        try:
            result = self._run(["--list-langs"])
        except (OSError, ValueError):  # pragma: no cover - environment dependent
            return ()
        # The first line is a human-readable header naming the tessdata directory.
        lines = result.stdout.decode("utf-8", "replace").splitlines()
        return tuple(line.strip() for line in lines[1:] if line.strip())

    def available(self) -> bool:
        """True only when the engine runs AND the language data is present.

        Both, because they fail differently and a caller that cannot tell them
        apart reports the wrong one. See the class docstring.
        """
        try:
            import subprocess  # noqa: PLC0415, F401
        except ImportError:  # pragma: no cover - defensive
            return False
        return bool(self.version()) and self.LANGUAGE in self.languages()

    # -- extraction --------------------------------------------------------

    def extract(self, data: bytes) -> MediaExtraction:
        if not self.version():
            return NullExtractor(MediaKind.IMAGE, "the Tesseract OCR engine").extract(data)
        if self.LANGUAGE not in self.languages():
            return MediaExtraction(
                ok=False,
                text="",
                method=self.name,
                stamp=EXTRACTION_STAMP,
                reason=(
                    f"The OCR engine is installed but its English language data "
                    f"({self.LANGUAGE}.traineddata) is not, so it cannot read anything. "
                    "Nothing was scored. Paste the words in as text and they will be "
                    "scored normally."
                ),
            )

        method = f"{self.version()} (psm {self.PSM}, oem {self.OEM}, {self.LANGUAGE})"
        try:
            result = self._run(
                ["stdin", "stdout", "-l", self.LANGUAGE, "--psm", self.PSM, "--oem", self.OEM],
                data=data,
                timeout=self.TIMEOUT_S,
            )
        except Exception as exc:  # pragma: no cover - environment dependent
            return MediaExtraction(
                ok=False,
                text="",
                method=method,
                stamp=EXTRACTION_STAMP,
                reason=(
                    "The photo could not be read: the OCR engine did not finish "
                    f"({type(exc).__name__}). Nothing was scored."
                ),
            )

        if result.returncode != 0:
            # Tesseract puts its diagnosis on stderr and it is usually legible --
            # "Image too large", "Error in pixReadStream". Passed through rather
            # than swallowed, because the person holding the file is the only one
            # who can act on it.
            message = result.stderr.decode("utf-8", "replace").strip().splitlines()
            hint = message[-1] if message else "no diagnosis given"
            return MediaExtraction(
                ok=False,
                text="",
                method=method,
                stamp=EXTRACTION_STAMP,
                reason=f"The OCR engine refused that file: {hint}",
            )

        cleaned = " ".join(result.stdout.decode("utf-8", "replace").split())
        if not cleaned:
            return MediaExtraction(
                ok=False,
                text="",
                method=method,
                stamp=EXTRACTION_STAMP,
                reason=(
                    "No readable writing was found in that photo. This page scores "
                    "words, so a picture with no words in it has nothing to score."
                ),
            )
        return MediaExtraction(ok=True, text=cleaned, method=method, stamp=EXTRACTION_STAMP)


class WhisperTranscriber:
    """Speech out of a video, via faster-whisper, when it happens to be present.

    Same optionality, same reason. The model size is fixed at `tiny` and the
    language at English: this is a demo path on a page that already says the
    scorer only reads English, and a larger model would turn one upload into a
    minutes-long render with no visible progress.
    """

    name = "faster-whisper (tiny, en)"

    def available(self) -> bool:
        return _installed("faster_whisper")

    def extract(self, data: bytes) -> MediaExtraction:
        if not self.available():  # pragma: no cover - environment dependent
            return NullExtractor(MediaKind.VIDEO, "faster-whisper").extract(data)
        import tempfile  # noqa: PLC0415

        from faster_whisper import WhisperModel  # noqa: PLC0415

        try:
            # A temporary file, deleted on exit, because the decoder wants a path.
            # It is the one place in this package where bytes touch a disk, and it
            # is why `delete=True` is not left to a default.
            with tempfile.NamedTemporaryFile(suffix=".media", delete=True) as handle:
                handle.write(data)
                handle.flush()
                model = WhisperModel("tiny", device="cpu", compute_type="int8")
                segments, _ = model.transcribe(handle.name, language="en")
                text = " ".join(segment.text.strip() for segment in segments)
        except Exception as exc:  # pragma: no cover - environment dependent
            return MediaExtraction(
                ok=False,
                text="",
                method=self.name,
                stamp=EXTRACTION_STAMP,
                reason=f"The video could not be transcribed: {type(exc).__name__}.",
            )
        cleaned = " ".join(text.split())
        if not cleaned:
            return MediaExtraction(
                ok=False,
                text="",
                method=self.name,
                stamp=EXTRACTION_STAMP,
                reason=(
                    "No speech was found in that video. This page scores words, so a "
                    "clip with nobody talking in it has nothing to score."
                ),
            )
        return MediaExtraction(ok=True, text=cleaned, method=self.name, stamp=EXTRACTION_STAMP)


def extractor_for(kind: MediaKind) -> TextExtractor:
    """The best available extractor for a kind of file, or the honest floor.

    Resolved per call rather than cached, so installing Tesseract and reloading
    the page is enough to switch backends -- a cached choice would survive the
    install and report the old answer, which is the cousin of the caching defect
    `dashboard/app.py` documents at length.
    """
    if kind is MediaKind.IMAGE:
        ocr = TesseractOCR()
        return ocr if ocr.available() else NullExtractor(kind, "the Tesseract OCR engine")
    if kind is MediaKind.VIDEO:
        asr = WhisperTranscriber()
        return asr if asr.available() else NullExtractor(kind, "faster-whisper")
    return NullExtractor(kind, "a decoder for this file type")
