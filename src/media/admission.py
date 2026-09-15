"""The media admission gate: what counts as a photo or a video worth reading.

The brief was "the engine must ignore the unwanted photos or videos", and the
first question is what makes one unwanted. Three answers, in increasing order of
how much this module is entitled to claim:

1. **It is not what it says it is.** A file named `.jpg` whose first bytes are
   `PK\\x03\\x04` is a zip. Checked by magic number, never by extension, because
   the extension is supplied by whoever uploaded the file.
2. **It is too small, too large or structurally empty to read.** A 40x30 image
   carries no legible text; a 200 MB video will not be transcribed in a browser
   session. Both are refused with the number that refused them.
3. **Nothing readable came out of it.** This one is NOT decided here -- it is
   decided after extraction, by the caller, because it needs the extractor's
   answer. The gate's job is to stop obviously-unreadable files before any
   optional decoder is invoked at all.

Why pure bytes and no image library
-----------------------------------
`Pillow`, `opencv` and `ffprobe` would each answer more questions, and each is a
dependency the reproducibility property does not want: `docs/data_sources.md`
and the Phase 6 decision commit this repository to an artifact a reviewer runs
with no account and no install beyond the pinned requirements. Header parsing
gets the dimensions of every format this page accepts in about forty lines, and
a header is exactly the part of a file that cannot lie about the format without
also failing the magic-number check.

What it deliberately does not do
---------------------------------
It does not look at picture content. It cannot tell a photograph of an athlete
from a photograph of a sandwich, and it does not pretend to: a gate that claimed
to recognise "relevant" images would be asserting a classifier this project has
not built and cannot evaluate, on a page whose entire design is about not
asserting things. Irrelevant-but-valid images are caught one step later, by
producing no readable text and being reported as such.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import Enum

#: Refuse anything larger. A browser session is not a transcoding farm, and a
#: file this size is a sign the user meant to upload something else.
MAX_BYTES = 64 * 1024 * 1024

#: Below this an "image" is an icon, a tracking pixel or a corrupt stub.
MIN_BYTES = 256

#: Text small enough to sit in an image this size is not text anyone can read,
#: and neither can a decoder. Applies to the smaller of the two dimensions.
MIN_EDGE_PX = 64

#: An image this large is a camera original that will cost more to handle than
#: it can return. Not a correctness limit, a courtesy one.
MAX_EDGE_PX = 12_000


class MediaKind(Enum):
    """What a file actually is, determined from its bytes."""

    IMAGE = "image"
    VIDEO = "video"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MediaAdmission:
    """Whether a file may be read, and what to tell the person if it may not.

    Mirrors `src/dashboard/gibberish.py::TextAdmission` deliberately: same shape,
    same falsiness, same rule that `detail` is written to be shown rather than
    logged. The two gates guard the same page and there is no reason for a
    reader to meet two different vocabularies for "no".
    """

    admitted: bool
    kind: MediaKind
    reason: str
    detail: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0

    def __bool__(self) -> bool:
        return self.admitted


# ---------------------------------------------------------------------------
# Header parsing
# ---------------------------------------------------------------------------


def _png_size(data: bytes) -> tuple[int, int] | None:
    """PNG: IHDR is always the first chunk, at a fixed offset. No search needed."""
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _gif_size(data: bytes) -> tuple[int, int] | None:
    """GIF: logical screen descriptor, little-endian, immediately after the magic."""
    if len(data) < 10:
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return int(width), int(height)


def _webp_size(data: bytes) -> tuple[int, int] | None:
    """WebP: three sub-formats, and the dimensions sit in a different place in each.

    Handled rather than skipped because a phone screenshot shared through a
    messaging app very often arrives as WebP, which is precisely the file a user
    of this page would upload.
    """
    if len(data) < 30:
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8 ":
        if data[23:26] != b"\x9d\x01\x2a":
            return None
        width, height = struct.unpack("<HH", data[26:30])
        return int(width & 0x3FFF), int(height & 0x3FFF)
    if fourcc == b"VP8L":
        bits = struct.unpack("<I", data[21:25])[0]
        return int(bits & 0x3FFF) + 1, int((bits >> 14) & 0x3FFF) + 1
    if fourcc == b"VP8X":
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    return None


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    """JPEG: walk the marker segments to the start-of-frame.

    A JPEG has no fixed header offset -- EXIF, colour profiles and thumbnails all
    sit between the magic number and the frame, and a phone photo has all three.
    So the segments are walked. The loop is bounded by the buffer and by a
    segment count, because a truncated or hostile file is exactly the input that
    would otherwise spin here.
    """
    index, end, segments = 2, len(data), 0
    while index + 9 < end and segments < 512:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0xFF:
            # Fill byte. A marker may be preceded by any number of 0xFF octets
            # (ITU-T T.81 B.1.1.2), and real encoders emit them. Treating one as
            # a marker reads the next two bytes as a segment length and walks the
            # parser off into the entropy-coded data, where it finds nothing and
            # the file is reported as "not an image" -- which is how a perfectly
            # ordinary phone photo gets refused.
            index += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        # SOF0..SOF15, excluding the four that are not start-of-frame markers.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return int(width), int(height)
        index += 2 + length
        segments += 1
    return None


#: (magic bytes, offset, kind, dimension reader). Order matters only in that
#: every entry is tried; no two of these prefixes collide.
_SIGNATURES: tuple[tuple[bytes, int, MediaKind, object], ...] = (
    (b"\x89PNG\r\n\x1a\n", 0, MediaKind.IMAGE, _png_size),
    (b"\xff\xd8\xff", 0, MediaKind.IMAGE, _jpeg_size),
    (b"GIF87a", 0, MediaKind.IMAGE, _gif_size),
    (b"GIF89a", 0, MediaKind.IMAGE, _gif_size),
    (b"RIFF", 0, MediaKind.IMAGE, _webp_size),  # narrowed to WEBP below
    (b"ftyp", 4, MediaKind.VIDEO, None),  # MP4 / MOV / M4V, ISO base media
    (b"\x1a\x45\xdf\xa3", 0, MediaKind.VIDEO, None),  # Matroska / WebM
)


def sniff(data: bytes) -> tuple[MediaKind, int, int]:
    """What this file is and, for an image, how big, from the bytes alone.

    Returns `(UNKNOWN, 0, 0)` for anything unrecognised, including a file whose
    magic number matches but whose header will not parse -- a truncated PNG is
    not a PNG this page can use, and reporting it as one only moves the failure
    somewhere less explainable.
    """
    for magic, offset, kind, reader in _SIGNATURES:
        if data[offset : offset + len(magic)] != magic:
            continue
        if magic == b"RIFF":
            if data[8:12] != b"WEBP":
                continue
            reader = _webp_size
        if kind is MediaKind.VIDEO:
            return kind, 0, 0
        size = reader(data) if reader is not None else None  # type: ignore[operator]
        if size is None:
            return MediaKind.UNKNOWN, 0, 0
        return kind, size[0], size[1]
    return MediaKind.UNKNOWN, 0, 0


def admit_media(filename: str, data: bytes) -> MediaAdmission:
    """Decide whether an uploaded file may be read.

    `filename` is used for the message only, never for the decision: the
    extension is whatever the uploader called it, and this gate exists precisely
    because that cannot be trusted.
    """
    size = len(data)
    if size == 0:
        return MediaAdmission(
            False,
            MediaKind.UNKNOWN,
            "empty",
            "That file is empty. Upload a photo or a short video and it will be read.",
            size_bytes=0,
        )

    if size > MAX_BYTES:
        return MediaAdmission(
            False,
            MediaKind.UNKNOWN,
            "too_large",
            f"That file is {size / 1_048_576:.0f} MB, and the limit here is "
            f"{MAX_BYTES // 1_048_576} MB. Upload a shorter clip or a single frame.",
            size_bytes=size,
        )

    kind, width, height = sniff(data)

    if kind is MediaKind.UNKNOWN:
        return MediaAdmission(
            False,
            kind,
            "not_media",
            f"{filename!r} is not a photo or a video that this page can read. It "
            "accepts PNG, JPEG, GIF and WebP images, and MP4, MOV and WebM video.",
            size_bytes=size,
        )

    if size < MIN_BYTES:
        return MediaAdmission(
            False,
            kind,
            "too_small",
            "That file is too small to contain anything readable. It looks like an "
            "icon or a truncated upload rather than a photo.",
            width=width,
            height=height,
            size_bytes=size,
        )

    if kind is MediaKind.IMAGE:
        if min(width, height) < MIN_EDGE_PX:
            return MediaAdmission(
                False,
                kind,
                "too_few_pixels",
                f"That image is {width}x{height}. Text below about {MIN_EDGE_PX} "
                "pixels on its short edge cannot be read reliably, so nothing is "
                "scored from it.",
                width=width,
                height=height,
                size_bytes=size,
            )
        if max(width, height) > MAX_EDGE_PX:
            return MediaAdmission(
                False,
                kind,
                "too_many_pixels",
                f"That image is {width}x{height}, which is larger than this page "
                "handles. Crop it to the part with the writing in it.",
                width=width,
                height=height,
                size_bytes=size,
            )

    return MediaAdmission(True, kind, "ok", "", width=width, height=height, size_bytes=size)
