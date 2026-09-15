"""The face-and-voice channel. Read this whole docstring before changing it.

What was asked for, and what is built
--------------------------------------
The owner asked for uploaded photos and videos to be analysed and reported
"according to Optimistic, Pessimistic etc", including the non-verbal content --
faces and tone of voice -- not only the words. This module is that channel.

It is also the most dangerous file in this repository, and the reasons are not
squeamishness:

* **Inferring an emotional or psychological state from a person's face is not a
  solved problem.** The affective-science literature does not support a reliable
  mapping from facial configuration to internal state across people, contexts
  and cultures. A dashboard that draws one is asserting something the field does
  not have, on a page whose whole design is about not asserting things.
* **A face is not synthetic text.** Every number elsewhere in this project is
  agreement with labels the project planted in text it generated itself
  (OPEN-025). An uploaded photo is a real person, usually the person uploading
  it, sometimes not. `docs/ethics.md` is written for a corpus with no people in
  it, and that document does not currently cover this.
* **The failure is asymmetric.** A number that reads a calm athlete as strained
  travels into a conversation with a coach. Nothing downstream of that is
  recoverable by a caveat.

So the channel is built, and it is held down by construction rather than by
convention, in four ways:

1. **It cannot produce a number without stamping it.** `NonVerbalReading`
   refuses construction without `NONVERBAL_TOKEN` in its stamp, exactly as
   `BiosignalWindow` refuses without SIMULATED and `ScoreSurface` without
   PROVISIONAL.
2. **It does not move the risk index unless someone switches it on.**
   `nonverbal_context_weights()` returns `{}` by default. Empty weights is the
   text-only path in `LinearRiskScorer.score`, which is separately tested to be
   numerically identical with and without a context mapping. The paper's numbers
   therefore stay text-only whatever happens on this page.
3. **The default reader is simulated and says so.** With no vision stack
   installed, `SimulatedNonVerbalReader` derives its values deterministically
   from a digest of the file bytes. That is a *demonstration of the seam*, not a
   measurement, and its stamp says the words "SIMULATED" and "not a measurement"
   so that a screenshot cannot lose them.
4. **A real reader is gated.** Any reader that actually looks at a face must be
   a subclass of `GatedRealReader`, whose constructor raises until
   `docs/ethics.md` and `docs/model_card.md` carry a consent route, a retention
   rule, and a statement that biometric inference is a different privacy class
   from synthetic text. The gate is the same shape as
   `src/biosignals/sources.py::require_simulated`, for the same reason.

What the channel reports
-------------------------
Three bounded scalars, none of which names an emotion:

* `expressivity` -- how much variation there is across the sampled frames.
* `vocal_strain`  -- a coarse prosodic roughness proxy.
* `steadiness`    -- how stable the sampled signal is over the clip.

Named for properties of a signal rather than for states of a person on purpose.
"Anxious face: 0.8" is a claim about someone; "expressivity: 0.8" is a claim
about pixels, and only the second is one this project can defend. The mapping
from these to the risk index is a weighting the owner sets deliberately, in the
open, at the point of switching the channel on.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Every stamp must carry this word. Substring rather than equality, so a reader
#: may extend the sentence without being able to drop the word that matters.
NONVERBAL_TOKEN = "NOT A MEASUREMENT"

NONVERBAL_STAMP = (
    "SIMULATED NON-VERBAL READING, NOT A MEASUREMENT OF A PERSON: these values are "
    "generated deterministically from the uploaded file's bytes to demonstrate the "
    "interface. Nothing looked at a face, nothing listened to a voice, and no state "
    "of mind was inferred from anybody."
)

#: The feature names this channel may emit. Fixed, because `context_weights` is
#: keyed by name and a typo in one of the two places would silently weight
#: nothing -- the failure that looks exactly like a feature being switched off.
FEATURES: tuple[str, ...] = ("expressivity", "vocal_strain", "steadiness")


class NonVerbalEthicsGate(RuntimeError):
    """Raised when a reader that would look at a real person is constructed."""


@dataclass(frozen=True)
class NonVerbalReading:
    """Three bounded scalars and the statement of where they came from."""

    source: str
    stamp: str
    features: Mapping[str, float]

    def __post_init__(self) -> None:
        if NONVERBAL_TOKEN not in self.stamp.upper():
            raise ValueError(
                f"NonVerbalReading({self.source!r}) has no {NONVERBAL_TOKEN!r} stamp. "
                "A number derived from a face, with its provenance stripped off, is "
                "indistinguishable from a psychological assessment of a person; see "
                "this module's docstring."
            )
        unknown = set(self.features) - set(FEATURES)
        if unknown:
            raise ValueError(
                f"NonVerbalReading({self.source!r}) emitted unknown features "
                f"{sorted(unknown)}. The name set is fixed so that a feature and its "
                "weight cannot drift apart; add to FEATURES deliberately."
            )
        for name, value in self.features.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value!r}.")
        object.__setattr__(self, "features", dict(self.features))


@runtime_checkable
class NonVerbalReader(Protocol):
    """What the page may ask of a non-verbal reader."""

    name: str
    simulated: bool

    def read(self, data: bytes) -> NonVerbalReading:  # pragma: no cover - Protocol
        ...


class SimulatedNonVerbalReader:
    """The default: deterministic values derived from the file's own bytes.

    Deterministic rather than random so that a screenshot is reproducible and so
    that uploading the same file twice gives the same answer -- a channel whose
    numbers moved on re-upload would be obviously broken, and one whose numbers
    move invisibly is worse.

    It is emphatically not looking at anything. A SHA-256 of the bytes is folded
    into three values in [0, 1]. Two visually identical photos saved at different
    qualities give unrelated readings, which is the correct behaviour for a
    simulator and would be a serious defect in a measurement. The stamp says so.
    """

    name = "simulated-nonverbal"
    simulated = True

    def read(self, data: bytes) -> NonVerbalReading:
        digest = hashlib.sha256(data).digest()
        features = {name: digest[index * 4] / 255.0 for index, name in enumerate(FEATURES)}
        return NonVerbalReading(source=self.name, stamp=NONVERBAL_STAMP, features=features)


class GatedRealReader:
    """Base class for any reader that would look at an actual face or voice.

    # BLOCKED UNTIL ETHICS SIGN-OFF
    #
    # Constructing one of these raises. This is not a stub to be filled in later
    # by deleting the raise: the blocker is a document, not a missing model. See
    # this module's docstring, point 4, for exactly what has to be true first.
    """

    name = "real-nonverbal"
    simulated = False

    def __init__(self) -> None:
        raise NonVerbalEthicsGate(
            f"{type(self).__name__} would infer a psychological state from a real "
            "person's face or voice, and is refused. Before any such reader runs: "
            "docs/ethics.md and docs/model_card.md must be updated with a consent "
            "route, a retention rule for biometric data, and a statement that "
            "biometric inference is a different privacy class from synthetic text; "
            "and the limitation that facial configuration does not map reliably to "
            "internal state must be stated wherever the output is shown. The risk "
            "index is produced from words; this channel is context, and it is off."
        )


def nonverbal_context_weights(
    *, enabled: bool = False, magnitude: float = 0.25
) -> dict[str, float]:
    """The weights the non-verbal features carry into `LinearRiskScorer.context`.

    **Returns `{}` unless `enabled` is passed True.** That is the whole safety
    property of this module expressed as a default argument, and it is worth
    being precise about what it buys: `fusion.score` adds context terms only
    `if self.context_weights and context`, so empty weights means the context
    mapping is accepted, carried, displayed -- and arithmetically ignored. The
    index is bit-identical to the text-only path, which `tests/test_risk.py`
    already asserts and which this function is written to keep true.

    Switching it on is therefore a deliberate act with a visible argument at the
    call site, not a config file nobody re-reads. The signs are stated here
    rather than inferred: expressivity and vocal strain push up, steadiness
    pulls down. They are a declared prior, exactly like `fusion.MAGNITUDES`, and
    they are not fitted, because there is no observed outcome in this project to
    fit anything against (OPEN-025).
    """
    if not enabled:
        return {}
    return {
        "expressivity": +magnitude,
        "vocal_strain": +magnitude,
        "steadiness": -magnitude,
    }
