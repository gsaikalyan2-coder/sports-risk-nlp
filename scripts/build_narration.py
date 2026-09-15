"""Build the spoken-word assets for the V3 cognitive-load demo. Run once, offline.

WHAT THIS PRODUCES, AND WHAT IT IS NOT
==============================================================================
It produces SYNTHETIC SPEECH reading SYNTHETIC TEXT. There is no athlete, no
microphone and no recording anywhere in this pipeline. The words were written by
this project's own generator (Phase 7, OPEN-011: no real athlete text exists in
this repository), and the voice is espeak-ng, a formant synthesiser that sounds
like a machine on purpose.

The machine-sounding voice is a feature, not a limitation to be improved away.
A convincing human voice over generated words, paired with a heart-rate trace
that responds to it, would be the most over-read artefact this project could
possibly ship -- it would look and sound exactly like a recording of a real
person having a real physiological response. Everything else in Phase 26 is
built to stop a simulated signal being mistaken for a measured one; do not
undo that here by swapping in a neural TTS voice because this one sounds thin.

Each clip is committed to `assets/narration/` beside a manifest carrying its
duration and its word timings, so the dashboard never needs a TTS engine at
runtime and a reviewer can reproduce the assets with one command.

Run:  python scripts/build_narration.py
Needs: espeak-ng and ffmpeg on PATH. Neither is a runtime dependency of the app.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

OUT_DIR = REPO_ROOT / "assets" / "narration"
MANIFEST = OUT_DIR / "manifest.json"

#: espeak-ng settings. Slow-ish and low-pitched so the words are followable at
#: the pace a coach would actually listen at, and so the clip is long enough for
#: the physiology trace under it to show a shape rather than a spike.
VOICE = "en-gb"
WORDS_PER_MINUTE = 145
PITCH = 40

#: 48 kbps mono. The clip is embedded in the panel as a data URI, so every
#: kilobyte is paid for in page weight; speech at this bitrate is perfectly
#: intelligible and three clips come to well under a megabyte.
BITRATE = "48k"


def _require(tool: str) -> None:
    if shutil.which(tool) is None:
        raise SystemExit(
            f"{tool} is not on PATH. This script is a one-off asset build, not part "
            f"of the app: install {tool}, run it once, and commit assets/narration/."
        )


def wav_duration_s(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def word_timings(text: str, duration_s: float) -> list[dict]:
    """Approximate per-word start times, by character position.

    Deliberately crude, and its crudeness is the honest choice. espeak-ng can
    emit real phoneme timings, but consuming them would make this look like an
    alignment pipeline -- and the thing the timings drive (an arousal curve for
    a simulator) has no accuracy requirement at all, because nothing downstream
    of it is a measurement. A proportional split is legible in five lines and
    nobody can mistake it for forced alignment.

    Returned as a list rather than a mapping because a word can occur twice.
    """
    total = len(text) or 1
    out: list[dict] = []
    cursor = 0
    for word in text.split():
        start = text.index(word, cursor)
        cursor = start + len(word)
        out.append(
            {
                "word": word,
                "start_s": round(duration_s * start / total, 3),
                "end_s": round(duration_s * cursor / total, 3),
            }
        )
    return out


def build(record_id: str, text: str) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = OUT_DIR / f"{record_id}.wav"
    mp3_path = OUT_DIR / f"{record_id}.mp3"

    subprocess.run(
        [
            "espeak-ng",
            "-v",
            VOICE,
            "-s",
            str(WORDS_PER_MINUTE),
            "-p",
            str(PITCH),
            "-w",
            str(wav_path),
            text,
        ],
        check=True,
    )
    duration = wav_duration_s(wav_path)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(wav_path),
            "-ac",
            "1",
            "-b:a",
            BITRATE,
            str(mp3_path),
        ],
        check=True,
    )
    wav_path.unlink()
    return {
        "record_id": record_id,
        "file": mp3_path.name,
        "duration_s": round(duration, 3),
        "text": text,
        "voice": f"espeak-ng {VOICE}",
        "words": word_timings(text, duration),
        "provenance": (
            "SYNTHETIC SPEECH over SYNTHETIC TEXT. No athlete was recorded and no "
            "microphone was involved. The words came from this project's own "
            "generator; the voice is a formant synthesiser."
        ),
    }


def main() -> None:
    _require("espeak-ng")
    _require("ffmpeg")

    from src.dashboard.backend import ReplayBackend
    from src.dashboard.view import DEFAULT_FIXTURE

    backend = ReplayBackend.from_fixture(DEFAULT_FIXTURE)
    clips = [build(rid, backend.get(rid).text) for rid in backend.example_ids]
    MANIFEST.write_text(
        json.dumps({"version": 1, "clips": clips}, indent=2) + "\n", encoding="utf-8"
    )
    for clip in clips:
        size = (OUT_DIR / clip["file"]).stat().st_size
        print(f"{clip['record_id']}  {clip['duration_s']:>5.1f}s  {size / 1024:>6.1f} KiB")
    print(f"\nmanifest: {MANIFEST.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
