"""Phase 29 -- the press-conference route, and the match-day profile.

Written to pass with no network and with none of the optional packages present,
because that is the state of a clean checkout. Nothing here contacts YouTube: the
transcript layer is exercised through its parsing, its refusals and its stamp,
and the profile layer through a stub backend.
"""

from __future__ import annotations

import pytest

from src.dashboard.matchday import build_profile
from src.media.pressroom import (
    PRESS_STAMP,
    PressTranscript,
    TranscriptUnavailable,
    fetch_transcript,
    transcript_stack_status,
    video_id,
)

# ---------------------------------------------------------------------------
# 1. Reading a link
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120s",
        "dQw4w9WgXcQ",
    ],
)
def test_the_id_is_found_in_every_shape_a_person_pastes(url: str) -> None:
    assert video_id(url) == "dQw4w9WgXcQ"


def test_something_that_is_not_a_link_is_refused_with_an_instruction() -> None:
    with pytest.raises(TranscriptUnavailable, match="youtube.com/watch"):
        video_id("the press conference from yesterday")


def test_an_empty_link_produces_no_number() -> None:
    with pytest.raises(TranscriptUnavailable):
        video_id("")


# ---------------------------------------------------------------------------
# 2. What a transcript says about itself
# ---------------------------------------------------------------------------


def test_a_transcript_cannot_lose_its_machine_read_stamp() -> None:
    with pytest.raises(ValueError, match="MACHINE-READ"):
        PressTranscript(text="I feel ready", route="captions", video="x" * 11, stamp="clean")


def test_an_empty_transcript_is_refused_rather_than_scored() -> None:
    """The 0.50 problem arriving through the link door."""
    with pytest.raises(ValueError, match="0.50"):
        PressTranscript(text="   ", route="captions", video="x" * 11)


def test_the_stamp_says_the_words_were_machine_read_and_deidentified() -> None:
    assert "MACHINE-READ" in PRESS_STAMP.upper()
    assert "placeholder" in PRESS_STAMP.lower()


def test_the_status_names_each_missing_route_separately() -> None:
    status = transcript_stack_status()
    assert isinstance(status.captions, bool)
    assert isinstance(status.speech, bool)
    assert status.detail


def test_a_link_with_no_route_available_refuses_and_says_why(monkeypatch) -> None:
    monkeypatch.setenv("SRN_MATCHDAY_REAL_ATHLETES", "1")
    monkeypatch.setattr(
        "src.media.pressroom.transcript_stack_status",
        lambda: type("S", (), {"captions": False, "speech": False, "detail": ""})(),
    )
    with pytest.raises(TranscriptUnavailable, match="not installed"):
        fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


# ---------------------------------------------------------------------------
# 1b. The ethics gate -- blocked by default, see docs/ethics.md sec.15
# ---------------------------------------------------------------------------


def test_a_valid_link_is_refused_by_default_with_no_real_fetch_attempted(monkeypatch) -> None:
    """The gate fires before any network call, for a link that would otherwise work."""
    monkeypatch.delenv("SRN_MATCHDAY_REAL_ATHLETES", raising=False)

    def _would_hit_the_network(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("the ethics gate must refuse before any route is tried")

    monkeypatch.setattr("src.media.pressroom._from_captions", _would_hit_the_network)
    monkeypatch.setattr("src.media.pressroom._from_speech", _would_hit_the_network)
    with pytest.raises(TranscriptUnavailable, match="ethics.md"):
        fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_the_gate_opens_only_when_the_owner_sets_the_flag(monkeypatch) -> None:
    monkeypatch.setenv("SRN_MATCHDAY_REAL_ATHLETES", "1")
    monkeypatch.setattr(
        "src.media.pressroom.transcript_stack_status",
        lambda: type("S", (), {"captions": False, "speech": False, "detail": ""})(),
    )
    # With the flag set, the function proceeds past the gate to the ordinary
    # "no route installed" refusal instead of the ethics refusal.
    with pytest.raises(TranscriptUnavailable, match="not installed"):
        fetch_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


# ---------------------------------------------------------------------------
# 3. The profile
# ---------------------------------------------------------------------------


class _Backend:
    """Enough of a backend to prove the profile never reaches the scorer here."""

    name = "stub"

    def predict(self, text: str):  # pragma: no cover - never called in these paths
        raise AssertionError("the scorer must not be reached without a transcript")


def test_no_link_and_no_photo_produces_no_number() -> None:
    profile = build_profile(
        policy="Conservative: the default, and what the paper reports", backend=_Backend()
    )
    assert not profile
    assert profile.score_100 == 0
    assert profile.view is None
    assert profile.transcript_detail


def test_a_bad_link_is_reported_and_nothing_is_scored() -> None:
    profile = build_profile(
        policy="Conservative: the default, and what the paper reports",
        backend=_Backend(),
        url="not a link at all",
    )
    assert not profile
    assert profile.view is None
    assert "youtube" in profile.transcript_detail.lower()


def test_a_photo_without_consent_reads_no_face() -> None:
    profile = build_profile(
        policy="Conservative: the default, and what the paper reports",
        backend=_Backend(),
        photo=b"not really an image",
        consent=False,
    )
    assert profile.face_measured is False
    assert profile.face_weights == {}
    assert profile.face_detail
