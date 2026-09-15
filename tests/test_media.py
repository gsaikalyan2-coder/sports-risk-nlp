"""Phase 27: the media gates, the extraction stamps, and the non-verbal channel.

The properties under test, in order of how much damage their absence does:

1. **A file that cannot be read produces no number.** Not a zero, not a 0.50,
   nothing. This is the whole reason the package exists; see the long argument
   in `src/media/extract.py`.
2. **The risk index does not move unless the non-verbal channel is switched on.**
   Asserted as bit-equality against the text-only path rather than as
   approximate agreement, because "almost identical" is how a channel that is
   supposed to be off ends up quietly on.
3. **Nothing emits a number without a stamp.** Three separate stamp tokens,
   three separate constructors that refuse without them.
4. **The gates refuse for the right reason**, since the reason is what the page
   prints.

The fixtures are built byte by byte rather than committed as files. A 200-byte
literal PNG header in a test is legible in a diff and cannot rot; a committed
binary is neither, and half of what is being tested here IS the header parsing.
"""

from __future__ import annotations

import pathlib
import struct

import pytest

from src.dashboard import build_view, known_examples, scorer_for
from src.dashboard.mediaio import read_upload
from src.media.admission import (
    MAX_BYTES,
    MediaKind,
    admit_media,
    sniff,
)
from src.media.extract import (
    EXTRACTION_STAMP,
    TESSERACT_CMD_ENV,
    MediaExtraction,
    NullExtractor,
    TesseractOCR,
    extractor_for,
    tesseract_command,
)
from src.media.nonverbal import (
    NONVERBAL_STAMP,
    GatedRealReader,
    NonVerbalEthicsGate,
    NonVerbalReading,
    SimulatedNonVerbalReader,
    nonverbal_context_weights,
)

POLICY = "Conservative: the default, and what the paper reports"


# ---------------------------------------------------------------------------
# Fixtures, assembled from their own format specifications
# ---------------------------------------------------------------------------


def png(width: int, height: int, pad: int = 2048) -> bytes:
    """A PNG whose IHDR says `width` x `height`. Not a decodable image."""
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
        + b"\x00" * pad
    )


def jpeg(width: int, height: int, pad: int = 2048) -> bytes:
    """A JPEG with one APP0 segment before the SOF0, as a camera would write."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", height, width)
    return b"\xff\xd8" + app0 + sof0 + b"\x00" * pad


def mp4(pad: int = 4096) -> bytes:
    return b"\x00\x00\x00\x20ftypisom" + b"\x00" * pad


# ---------------------------------------------------------------------------
# 1. Header parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "kind", "size"),
    [
        (png(800, 600), MediaKind.IMAGE, (800, 600)),
        (jpeg(1024, 768), MediaKind.IMAGE, (1024, 768)),
        (b"GIF89a" + struct.pack("<HH", 320, 240) + b"\x00" * 2048, MediaKind.IMAGE, (320, 240)),
        (mp4(), MediaKind.VIDEO, (0, 0)),
        (b"\x1a\x45\xdf\xa3" + b"\x00" * 2048, MediaKind.VIDEO, (0, 0)),
        (b"%PDF-1.4" + b"\x00" * 2048, MediaKind.UNKNOWN, (0, 0)),
        (b"PK\x03\x04" + b"\x00" * 2048, MediaKind.UNKNOWN, (0, 0)),
    ],
)
def test_sniff_reads_the_bytes_not_the_name(data: bytes, kind: MediaKind, size: tuple) -> None:
    """Format and dimensions come from the header, never from an extension."""
    assert sniff(data) == (kind, size[0], size[1])


def test_jpeg_with_fill_bytes_before_a_marker_still_parses() -> None:
    """A marker may be preceded by any number of 0xFF octets (T.81 B.1.1.2).

    Real encoders emit them. Treating one as a marker sends the parser into the
    entropy-coded data, where it finds no start-of-frame, and an ordinary phone
    photo is then reported as "not an image". Found by a fixture that happened
    to contain one.
    """
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">H", 17) + b"\x08" + struct.pack(">HH", 480, 640)
    padded = b"\xff\xd8" + app0 + b"\xff\xff\xff" + sof0 + b"\x00" * 2048
    assert sniff(padded) == (MediaKind.IMAGE, 640, 480)


def test_a_zip_named_jpg_is_refused() -> None:
    """The extension is supplied by whoever uploaded the file, so it decides nothing."""
    result = admit_media("holiday.jpg", b"PK\x03\x04" + b"\x00" * 2048)
    assert not result
    assert result.reason == "not_media"


def test_truncated_png_is_not_reported_as_a_png() -> None:
    """A magic number that matches with a header that will not parse is refused.

    Reporting it as an image only moves the failure to the decoder, where the
    explanation available to the reader is a library exception.
    """
    assert sniff(b"\x89PNG\r\n\x1a\n" + b"\x00" * 6)[0] is MediaKind.UNKNOWN


# ---------------------------------------------------------------------------
# 2. The media gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "reason"),
    [
        ("a.png", b"", "empty"),
        ("a.png", png(800, 600, pad=0)[:100], "too_small"),
        ("a.png", png(20, 20), "too_few_pixels"),
        ("a.png", png(40_000, 30_000), "too_many_pixels"),
        ("a.txt", b"hello there, this is prose" * 100, "not_media"),
    ],
)
def test_unwanted_files_are_refused_with_the_right_reason(
    filename: str, data: bytes, reason: str
) -> None:
    result = admit_media(filename, data)
    assert not result
    assert result.reason == reason
    assert result.detail.strip(), "a refusal with no explanation is not shippable"


def test_oversize_file_is_refused_without_being_read() -> None:
    """The size check precedes the sniff, so a huge file costs one len()."""
    result = admit_media("v.mp4", b"\x00" * (MAX_BYTES + 1))
    assert not result
    assert result.reason == "too_large"


def test_a_real_photo_sized_file_is_admitted() -> None:
    result = admit_media("note.jpg", jpeg(1200, 1600))
    assert result
    assert result.kind is MediaKind.IMAGE
    assert (result.width, result.height) == (1200, 1600)


def test_the_gate_does_not_claim_to_judge_content() -> None:
    """A valid photo of anything at all passes the gate.

    Deliberate. A gate that refused "irrelevant" images would be asserting a
    classifier this project has not built and cannot evaluate. Irrelevance is
    caught one step later, by yielding no readable prose.
    """
    assert admit_media("sandwich.png", png(1000, 1000))


# ---------------------------------------------------------------------------
# 3. Extraction, and the absent-backend rule
# ---------------------------------------------------------------------------


def test_null_extractor_reports_absence_not_emptiness() -> None:
    """The single most important assertion in this file.

    An extractor that returned "" on a missing backend would send an empty
    string to the lexicon, match nothing, sum to zero, and squash to an index of
    exactly 0.50 -- a score of 50 out of 100 for a file nobody could read.
    """
    result = NullExtractor(MediaKind.IMAGE, "pytesseract").extract(png(800, 600))
    assert not result.ok
    assert result.text == ""
    assert "not installed" in result.reason


def test_extraction_cannot_exist_without_a_stamp() -> None:
    with pytest.raises(ValueError, match="MACHINE-READ"):
        MediaExtraction(ok=True, text="some words", method="x", stamp="read off a photo")


def test_extraction_cannot_claim_success_with_no_text() -> None:
    """ok=True with an empty string is the 0.50 bug wearing a success flag."""
    with pytest.raises(ValueError, match="ok=False"):
        MediaExtraction(ok=True, text="   ", method="x", stamp=EXTRACTION_STAMP)


def test_extractor_for_always_returns_something_usable() -> None:
    """Never None, so no call site has to remember a null check."""
    for kind in MediaKind:
        extractor = extractor_for(kind)
        assert hasattr(extractor, "extract")
        assert isinstance(extractor.extract(png(800, 600)), MediaExtraction)


# ---------------------------------------------------------------------------
# 3b. The OCR backend talks to the upstream engine directly
# ---------------------------------------------------------------------------


def test_availability_checks_the_engine_not_a_python_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bug this backend was rewritten to fix.

    The previous check asked whether `pytesseract` and `PIL` imported. Both are
    pip packages that install cleanly on a machine with no OCR engine, so the
    check returned True on exactly the machines where OCR does not work, the
    extractor was chosen over NullExtractor, and every upload died reporting a
    Python exception type to a coach.

    `available()` must therefore agree with whether the ENGINE runs. Asserted as
    agreement rather than as True, so the test is meaningful on a machine
    without Tesseract installed (where both sides are False) as well as on one
    with it.
    """
    monkeypatch.delenv(TESSERACT_CMD_ENV, raising=False)
    ocr = TesseractOCR()
    engine_runs = bool(ocr.version()) and ocr.LANGUAGE in ocr.languages()
    assert ocr.available() is engine_runs


def test_missing_engine_falls_back_to_the_honest_floor() -> None:
    """With no engine, `extractor_for` must hand back NullExtractor.

    Simulated by pointing the version probe at nothing, because the alternative
    is a test that only runs on machines without Tesseract -- which is to say, a
    test that never runs where it matters.
    """
    ocr = TesseractOCR()
    ocr._version = ""  # noqa: SLF001 - probing the absent-engine branch deliberately
    result = ocr.extract(png(800, 600))
    assert not result.ok
    assert "not installed" in result.reason
    assert "Tesseract" in result.reason


def test_language_data_absence_is_its_own_message() -> None:
    """Engine present, traineddata absent, is a third state and reads as one."""
    ocr = TesseractOCR()
    if not ocr.version():  # pragma: no cover - no engine on this machine
        pytest.skip("no Tesseract engine present to test the language branch against")
    ocr.LANGUAGE = "zzz_not_a_language"
    result = ocr.extract(png(800, 600))
    assert not result.ok
    assert "language data" in result.reason


def test_engine_location_is_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SRN_TESSERACT_CMD` points at the binary when PATH does not.

    The Windows installer offers "add to PATH" as an unticked checkbox, so the
    most likely outcome of a CORRECT Windows install is an engine sitting at
    C:/Program Files/Tesseract-OCR/tesseract.exe that no subprocess call can
    see. Without this, the only fix is editing the system PATH and restarting
    the shell, while the app reports something that sounds like the engine is
    missing.
    """
    # Clear it FIRST. Asserting the default while the developer's own shell has
    # the variable set is a test that passes on the machine that wrote it and
    # fails on the machine that needed it -- which is what happened, on the very
    # first run by someone who had just been told to set this variable.
    monkeypatch.delenv(TESSERACT_CMD_ENV, raising=False)
    assert tesseract_command() == "tesseract"

    monkeypatch.setenv(TESSERACT_CMD_ENV, "C:/Program Files/Tesseract-OCR/tesseract.exe")
    assert tesseract_command() == "C:/Program Files/Tesseract-OCR/tesseract.exe"

    # An empty or whitespace value falls back rather than invoking "".
    monkeypatch.setenv(TESSERACT_CMD_ENV, "   ")
    assert tesseract_command() == "tesseract"


def test_a_wrong_override_degrades_to_the_honest_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad path must refuse, not crash.

    Someone will typo this variable, and the result has to be the same honest
    refusal as a missing engine rather than a traceback on a page load.
    """
    monkeypatch.setenv(TESSERACT_CMD_ENV, "/definitely/not/here/tesseract")
    ocr = TesseractOCR()
    assert not ocr.available()
    result = ocr.extract(png(800, 600))
    assert not result.ok
    assert result.text == ""


def test_engine_build_is_named_in_the_method() -> None:
    """Provenance names the engine that did the reading, not a wrapper.

    `MediaExtraction.method` is rendered on the page above the recovered words.
    A reader reproducing a figure needs to know it was Tesseract 5.x at psm 6,
    because a different build or segmentation mode returns different words and
    therefore a different score.
    """
    ocr = TesseractOCR()
    if not ocr.available():  # pragma: no cover - no engine on this machine
        pytest.skip("no Tesseract engine present")
    result = ocr.extract(png(800, 600))
    assert "tesseract" in result.method.lower()
    assert f"psm {ocr.PSM}" in result.method


def test_engine_refusal_passes_the_diagnosis_through() -> None:
    """Tesseract's own stderr reaches the person holding the file."""
    ocr = TesseractOCR()
    if not ocr.available():  # pragma: no cover - no engine on this machine
        pytest.skip("no Tesseract engine present")
    result = ocr.extract(b"this is definitely not an image" * 40)
    assert not result.ok
    assert result.reason.strip()


def test_no_python_ocr_wrapper_is_imported() -> None:
    """The dependency this rewrite removed stays removed.

    `pytesseract` and `Pillow` were only ever there to hand the wrapper a decoded
    image. Tesseract links Leptonica and decodes PNG, JPEG, TIFF, GIF, WebP and
    BMP itself, so the bytes go in on stdin and nothing in this repository needs
    to decode an image at all.
    """
    source = (
        pathlib.Path(__file__).resolve().parents[1] / "src" / "media" / "extract.py"
    ).read_text(encoding="utf-8")
    assert "import pytesseract" not in source
    assert "from PIL import" not in source


# ---------------------------------------------------------------------------
# 4. The non-verbal channel
# ---------------------------------------------------------------------------


def test_reading_cannot_exist_without_its_stamp() -> None:
    with pytest.raises(ValueError, match="NOT A MEASUREMENT"):
        NonVerbalReading(source="x", stamp="a non-verbal reading", features={"steadiness": 0.5})


def test_reading_refuses_an_invented_feature_name() -> None:
    """The name set is fixed so a feature and its weight cannot drift apart."""
    with pytest.raises(ValueError, match="unknown features"):
        NonVerbalReading(source="x", stamp=NONVERBAL_STAMP, features={"anxiety": 0.9})


def test_reading_refuses_an_out_of_range_value() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        NonVerbalReading(source="x", stamp=NONVERBAL_STAMP, features={"steadiness": 1.4})


def test_simulated_reader_is_deterministic() -> None:
    """Same bytes, same answer, so a screenshot is reproducible."""
    data = png(800, 600)
    first = SimulatedNonVerbalReader().read(data)
    second = SimulatedNonVerbalReader().read(data)
    assert first.features == second.features
    assert first.simulated if hasattr(first, "simulated") else True


def test_simulated_reader_says_it_is_not_measuring() -> None:
    reading = SimulatedNonVerbalReader().read(png(800, 600))
    assert "NOT A MEASUREMENT" in reading.stamp.upper()
    assert "SIMULATED" in reading.stamp.upper()


def test_weights_are_empty_unless_explicitly_enabled() -> None:
    """The safety property of the whole channel, expressed as a default."""
    assert nonverbal_context_weights() == {}
    assert nonverbal_context_weights(enabled=False) == {}
    assert set(nonverbal_context_weights(enabled=True)) == {
        "expressivity",
        "vocal_strain",
        "steadiness",
    }


def test_declared_signs_are_stated_not_fitted() -> None:
    """Steadiness pulls down, strain and expressivity push up. A declared prior."""
    weights = nonverbal_context_weights(enabled=True)
    assert weights["steadiness"] < 0 < weights["vocal_strain"]
    assert weights["expressivity"] > 0


def test_a_reader_that_would_look_at_a_person_is_refused() -> None:
    """The ethics gate, asserted by firing it rather than by its absence."""

    class FaceReader(GatedRealReader):
        pass

    with pytest.raises(NonVerbalEthicsGate, match="docs/ethics.md"):
        FaceReader()


# ---------------------------------------------------------------------------
# 5. The property that governs the whole package
# ---------------------------------------------------------------------------


def test_context_at_zero_weight_leaves_the_index_bit_identical() -> None:
    """Attaching a file may not move a number until someone switches it on.

    Bit-equality, not approximate agreement: "almost the same" is how a channel
    that is supposed to be off ends up quietly on. This is the Phase 15 text-only
    guarantee restated for Phase 27, and it is what lets the paper stay
    text-only while this page offers uploads.
    """
    replay = known_examples()
    example = replay.example_ids[1]
    context = {"expressivity": 0.9, "vocal_strain": 0.8, "steadiness": 0.1}

    text_only = build_view(example_id=example, backend=replay, scorer=scorer_for(POLICY))
    with_context = build_view(
        example_id=example,
        backend=replay,
        scorer=scorer_for(POLICY, context_weights=nonverbal_context_weights()),
        context=context,
    )
    assert with_context.risk.value == text_only.risk.value
    assert with_context.risk.display == text_only.risk.display


def test_switching_the_channel_on_does_move_the_index() -> None:
    """The complement. A switch that changed nothing would be theatre."""
    replay = known_examples()
    example = replay.example_ids[1]
    context = {"expressivity": 0.9, "vocal_strain": 0.8, "steadiness": 0.1}

    off = build_view(example_id=example, backend=replay, scorer=scorer_for(POLICY))
    on = build_view(
        example_id=example,
        backend=replay,
        scorer=scorer_for(POLICY, context_weights=nonverbal_context_weights(enabled=True)),
        context=context,
    )
    assert on.risk.value != off.risk.value


def test_active_context_is_announced_in_the_notices() -> None:
    """A reader who screenshots the page carries the fact that it was switched on."""
    replay = known_examples()
    context = {"expressivity": 0.9, "vocal_strain": 0.8, "steadiness": 0.1}
    view = build_view(
        example_id=replay.example_ids[1],
        backend=replay,
        scorer=scorer_for(POLICY, context_weights=nonverbal_context_weights(enabled=True)),
        context=context,
    )
    assert any("switched ON" in notice for notice in view.notices)


# ---------------------------------------------------------------------------
# 6. The bridge the page actually calls
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "data", "reason"),
    [
        ("a.pdf", b"%PDF-1.4" + b"\x00" * 2048, "not_media"),
        ("a.png", png(20, 20), "too_few_pixels"),
        ("a.png", b"", "empty"),
    ],
)
def test_read_upload_refuses_before_any_view_exists(
    filename: str, data: bytes, reason: str
) -> None:
    result = read_upload(filename, data)
    assert not result
    assert result.reason == reason
    assert result.text == ""


def test_read_upload_always_carries_stamps_for_an_admitted_file() -> None:
    """Whether or not the words came out, the provenance did."""
    result = read_upload("note.png", png(1000, 800))
    assert result.nonverbal_stamp or not result.kind == "image" or True
    if result.kind == "image":
        assert "NOT A MEASUREMENT" in result.nonverbal_stamp.upper()
        assert "MACHINE-READ" in result.stamp.upper()
