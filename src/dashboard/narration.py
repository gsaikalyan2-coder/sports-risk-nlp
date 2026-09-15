"""Spoken-word clips for the V3 panel, and the text -> simulator coupling.

WHAT THIS IS NOT
==============================================================================
It is not text<->physiology concordance. Concordance asks whether what an
athlete says agrees with what their body shows; it is answered by correlating
two MEASURED channels; it is the strongest scientific item in the concept board
and it is deliberately deferred to a second paper (`.claude.md` section 11,
"explicitly out of scope for this phase"). Nothing here measures anything.

This is the reverse arrow, and the reverse arrow is arithmetic. The construct
probabilities the text model already produced are used to drive a simulator, so
the trace under the clip responds to a phrase the listener just heard. The
coupling runs text -> body, it was written here, and it is stated on the panel
as imposed. If it ever reads as evidence that a body agreed with a text, that is
a defect in the labelling and not a finding.

The clip itself is SYNTHETIC SPEECH over SYNTHETIC TEXT -- espeak-ng reading
words this project's own generator wrote. No athlete was recorded, no microphone
was involved, and `scripts/build_narration.py` says at length why the voice is
deliberately left sounding like a machine.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.dashboard.view import REPO_ROOT

NARRATION_DIR = REPO_ROOT / "assets" / "narration"
MANIFEST_PATH = NARRATION_DIR / "manifest.json"

#: Samples per second in the arousal track handed to the simulator. Ten is well
#: above the rate at which anything in the panel moves and keeps the track small
#: enough to inline; it is a resolution choice, not a physiological one.
TRACK_HZ = 10.0

#: How often a trailing window is cut, in seconds. The audio player maps its
#: current time onto an index by dividing by this, so it also sets how finely the
#: readouts step as the clip plays.
STEP_S = 0.5

#: How much signal each window looks back over.
TRAILING_S = 10.0


class NarrationMissing(FileNotFoundError):
    """Raised when the committed clips are absent.

    A distinct type so the page can say "run scripts/build_narration.py" rather
    than surfacing a bare path, and so a missing asset cannot be mistaken for a
    missing feature -- the failure this repository has now met three times.
    """


@dataclass(frozen=True)
class Clip:
    """One committed spoken-word asset and everything needed to play it."""

    record_id: str
    path: Path
    duration_s: float
    text: str
    voice: str
    words: tuple[dict, ...]
    provenance: str

    def data_uri(self) -> str:
        """The audio inlined, because the panel may not reach the network.

        Same rule as every other asset in this layer: `motion.py` records a
        defect where a blocked CDN left a panel empty while the tests stayed
        green. An `<audio src="...">` pointing at a path Streamlit does not serve
        would fail the same way, silently, as a player that never starts.
        """
        raw = base64.b64encode(self.path.read_bytes()).decode("ascii")
        return f"data:audio/mpeg;base64,{raw}"


@lru_cache(maxsize=1)
def load_manifest() -> tuple[Clip, ...]:
    """Every committed clip. Cached: the assets do not change at runtime."""
    if not MANIFEST_PATH.exists():
        raise NarrationMissing(
            f"{MANIFEST_PATH} is missing. The spoken-word clips are committed "
            "assets, not generated at runtime; rebuild them with "
            "`python scripts/build_narration.py` (needs espeak-ng and ffmpeg)."
        )
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    clips = []
    for entry in data["clips"]:
        path = NARRATION_DIR / entry["file"]
        if not path.exists():
            raise NarrationMissing(f"{path} is named in the manifest and absent from disk.")
        clips.append(
            Clip(
                record_id=entry["record_id"],
                path=path,
                duration_s=float(entry["duration_s"]),
                text=entry["text"],
                voice=entry["voice"],
                words=tuple(entry["words"]),
                provenance=entry["provenance"],
            )
        )
    return tuple(clips)


def clip_for(record_id: str) -> Clip:
    for clip in load_manifest():
        if clip.record_id == record_id:
            return clip
    raise NarrationMissing(f"no committed clip for {record_id!r}")


def arousal_events(view, clip: Clip) -> tuple[tuple[float, float], ...]:
    """(time_s, weight) for every evidence span in the view, timed to the clip.

    One event per span. The weight is the construct's detection strength, signed
    by the direction it pushed the risk index -- so a worried phrase raises
    simulated arousal and a confident one lowers it.

    Three deliberate omissions, each of which would otherwise be a quiet claim:

    * **Inert constructs contribute nothing.** They carry no sign under the
      conservative policy, and inventing one here would make the trace assert a
      direction the index itself refuses to take.
    * **A construct with no spans is skipped.** Those are the unevidenced
      drivers the dashboard already reports and refuses to hide; they moved the
      index without the model being able to point at any words, so there is no
      moment in the audio to attach them to. Placing them at the midpoint would
      manufacture one.
    * **A span the model reports but the clip's text does not contain is
      skipped**, rather than approximated to the nearest match.

    Timed by character position, matching how `scripts/build_narration.py`
    derived the word timings, so the event lands on the word rather than near it.
    """
    text = clip.text
    total = len(text) or 1
    events: list[tuple[float, float]] = []
    for bar in view.bars:
        if bar.inert or not bar.spans:
            continue
        sign = 1.0 if bar.contribution >= 0 else -1.0
        for span in bar.spans:
            fragment = span.text.strip()
            if not fragment or fragment not in text:
                continue
            start = text.index(fragment)
            midpoint = start + len(fragment) / 2.0
            events.append((clip.duration_s * midpoint / total, sign * bar.probability))
    events.sort()
    return tuple(events)


#: How hard an unevidenced driver lifts the baseline. A display gain, chosen so
#: a text whose drivers are all unevidenced still produces a visibly different
#: trace from a calm one, and nothing more. Not fitted; nothing to fit against.
UNEVIDENCED_GAIN = 0.45


def baseline_arousal(view) -> float:
    """Where the trace sits when no phrase is acting, from the unevidenced drivers.

    `arousal_events` deliberately skips every construct the model could not point
    at words for. On this project's corpus that is most of them -- the dashboard
    already reports it as the honest weak spot, 104 cases in 120 -- so skipping
    them and stopping there produced a flat trace under two of the three clips,
    which reads as a broken feature rather than as a finding.

    They lift the floor instead. A driver with no words behind it is a claim
    about the whole text and not about any moment in it, so it acts on the whole
    clip and on no particular second of it. That is exactly what it is entitled
    to do, and the shape of the trace tells the two cases apart at a glance.
    """
    from src.biosignals.features import AROUSAL_FLOOR

    lift = 0.0
    for bar in view.bars:
        if bar.inert or bar.spans:
            continue
        sign = 1.0 if bar.contribution >= 0 else -1.0
        lift += sign * bar.probability
    return max(0.0, min(0.9, AROUSAL_FLOOR + UNEVIDENCED_GAIN * lift))


def narrated_windows(view, clip: Clip, source) -> tuple:
    """The simulated session for one clip, as trailing windows the player indexes.

    `source` must already have been through `require_simulated()`; this function
    does not repeat the gate, because a guard repeated in two places is a guard
    that can disagree with itself. The page calls it once, at the top.
    """
    from src.biosignals.features import arousal_curve

    samples = max(2, int(round(clip.duration_s * TRACK_HZ)) + 1)
    track = arousal_curve(
        arousal_events(view, clip),
        clip.duration_s,
        samples=samples,
        baseline=baseline_arousal(view),
    )
    return source.narrate(track, clip.duration_s, step_s=STEP_S, trailing_s=TRAILING_S)
