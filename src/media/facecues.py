"""Phase 28: facial cues read from a real face, under consent, into the index.

What changed from Phase 27, and what did not
---------------------------------------------
Phase 27 built the non-verbal seam and then bolted it shut: `GatedRealReader`
raised on construction, and the only reader that existed derived three numbers
from a SHA-256 of the file's bytes. The owner's decision of 2026-09-16 opens the
seam under three conditions, all of which are enforced here rather than
promised:

1. **Consent is a precondition, not a preference.** `FaceCueReader` refuses
   construction without `consent=True`, which the page only passes when the
   reader has ticked the box in `copy.CONSENT_LABEL`. No consent means no face
   is looked at, and the simulated reader is used instead exactly as before.
2. **Only a *measured* reading may carry weight.** The weights in
   `face_context_weights()` are keyed to the two features this module produces
   from an actual detected face. The simulated reader's three features are not
   in that mapping, so a fallback reading is displayed and multiplies by nothing.
   That is the difference between "we could not read the face, so the score is
   the text score" and the silent substitution of a hash for a measurement.
3. **The claim is about the picture, never about the person.** The features are
   `negative_valence` (how negative the *expression* looks) and `arousal` (how
   activated it looks). Neither is an emotion label and neither is a state of
   mind. Everything this module emits carries the `NOT A MEASUREMENT` stamp that
   `NonVerbalReading.__post_init__` requires.

Why this engine
---------------
`hsemotion-onnx` (Apache-2.0, https://github.com/sb-ai-lab/EmotiEffLib), the
ONNX distribution of HSEmotion: Savchenko, "Video-based frame-level facial
analysis of affective behavior on mobile devices using EfficientNets", and
Savchenko et al., *IEEE Transactions on Affective Computing*, 2022. Three
reasons it was chosen over Py-Feat and LibreFace, in order:

* It runs on `onnxruntime` and needs no PyTorch. Streamlit Community Cloud gives
  an app 2.7 GB of memory; a torch wheel spends most of that before a model
  loads.
* Its valence/arousal head emits two *continuous* quantities, which is the
  circumplex parameterisation, rather than a discrete label like "fear". A
  bounded continuous cue is a defensible thing to weight; a categorical emotion
  claim about an athlete is not.
* It is published and competed (ABAW), so the paper can cite the engine rather
  than describe an unnamed model.

Face detection is OpenCV's Haar cascade, shipped inside `opencv-python-headless`,
pinned below 5.0. Two pins, two different failures being avoided:

* **headless** -- the full `opencv-python` wheel links libGL, absent from a
  Community Cloud image, and fails at import with a shared-object error that
  reads like a broken app rather than a missing system library.
* **<5** -- OpenCV 5.0 removed `cv2.CascadeClassifier` and the bundled cascade
  XML. On a 5.x wheel the import succeeds and the attribute does not exist, so
  `face_stack_status()` checks for the attribute rather than for the import.

First run downloads the weights
-------------------------------
`hsemotion-onnx` fetches its ONNX file from the upstream repository the first
time a recognizer is constructed, into the package directory. That means the
first photograph scored after a deployment is slower, and that a machine with no
outbound network reads no face and says so rather than failing. Nothing about
the download touches the uploaded image.

What this module does NOT do
----------------------------
It does not identify anybody, match a face against any gallery, or persist a
single byte: the image is decoded into a local array, reduced to two floats, and
dropped with the render. It does not read a voice; the video path still yields
words only. And it does not claim that an expression is a feeling. See
`docs/ethics.md` §14 for the limitation that must accompany every number it
produces.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.media.nonverbal import (
    FACE_FEATURES,
    NonVerbalEthicsGate,
    NonVerbalReading,
)

__all__ = [
    "FACE_ONLY_STAMP",
    "FACE_STAMP",
    "FACE_WEIGHTS",
    "FaceCueReader",
    "FaceCueUnavailable",
    "face_cue_reader",
    "face_context_weights",
    "face_stack_status",
]

#: Every reading this module emits carries this. It states three things a
#: screenshot must not be able to lose: that a real face was read, that an
#: expression is not a feeling, and that the number is not a measurement of a
#: person's psychological state.
FACE_STAMP = (
    "FACIAL CUES READ FROM A REAL FACE, NOT A MEASUREMENT OF A PERSON'S STATE OF MIND: "
    "these two values describe how the photographed expression looks, not how the "
    "person feels. Affective science does not support a reliable mapping from a facial "
    "configuration to an internal state across people, contexts and cultures, so this "
    "is weak evidence carried openly rather than a reading of anybody. Read under the "
    "consent the uploader affirmed; nothing was stored."
)

#: The weights the face features carry into `LinearRiskScorer.context`.
#:
#: Declared, not fitted, and small on purpose. There is no observed outcome in
#: this project to fit a weight against (OPEN-025), so a large weight would be a
#: number invented twice over. The signs are the stated prior: an expression
#: that looks more negative and more activated pushes the index up.
#:
#: Note what is absent: the three simulated features (`expressivity`,
#: `vocal_strain`, `steadiness`) are NOT keys here. `fusion.score` adds a context
#: term only for a name present in both the weights and the context mapping, so
#: a simulated reading is carried, displayed, and arithmetically ignored.
FACE_WEIGHTS: dict[str, float] = {
    "negative_valence": +0.20,
    "arousal": +0.10,
}

#: Phase 28b. Shown with a figure produced from a face and nothing else.
#:
#: This is a different object from the risk index and it says so in its first
#: clause, because the risk index means "ten sports-psychology constructs found
#: in an athlete's own words, fused". A photograph contains none of that, and a
#: figure derived from two facial cues wearing the risk index's name would be the
#: most misleading number this project has ever put on a screen.
FACE_ONLY_STAMP = (
    "FACE-ONLY READING, NOT THE RISK INDEX AND NOT A MEASUREMENT OF A PERSON: no words "
    "were found in this file, so none of the ten psychological signals were detected "
    "and none of the usual evidence exists. This figure is arithmetic over two cues "
    "describing how the photographed expression looks, under weights chosen by hand. "
    "An expression is not a feeling, a competitor mid-effort looks strained for reasons "
    "unrelated to how they are coping, and nothing here should be carried into a "
    "conversation about a person."
)


def face_only_index(features: dict[str, float]) -> float:
    """A 0-1 figure from facial cues alone, when a photograph carries no words.

    The owner asked (2026-09-19) for a photograph of an athlete to produce a
    reading even when there is nothing to read in it. This is that reading, and
    the shape of it is chosen so that it cannot be mistaken for the risk index:

    * It is a plain weighted mean of the two cues under `FACE_WEIGHTS`, which are
      the same declared weights the combined path uses. No logistic squash, so a
      file with nothing detected in it cannot land on 0.50 wearing a band -- the
      Phase 27 failure this repository is shaped around. Zero cues in, zero out.
    * It is returned with `FACE_ONLY_STAMP`, never with the risk stamp, and the
      page renders no construct tiles and no spans beside it, because neither
      exists for a picture.
    """
    total = sum(abs(weight) for weight in FACE_WEIGHTS.values())
    return _unit(
        sum(FACE_WEIGHTS[name] * float(features.get(name, 0.0)) for name in FACE_WEIGHTS) / total
    )


#: The model. `enet_b0_8_va_mtl` is the smallest published multi-task variant:
#: eight expression outputs plus the valence and arousal heads, a few megabytes
#: of ONNX, which is what keeps this inside a Community Cloud app's memory.
MODEL_NAME = "enet_b0_8_va_mtl"

#: The eight expression labels the model emits, in its own order. Used only to
#: derive a fallback valence when a build of the library returns expression
#: scores without the valence/arousal pair, so that a version change degrades to
#: a coarser reading rather than to a wrong one.
EXPRESSIONS: tuple[str, ...] = (
    "Anger",
    "Contempt",
    "Disgust",
    "Fear",
    "Happiness",
    "Neutral",
    "Sadness",
    "Surprise",
)

#: Which of those read as negative-looking, for that fallback only.
_NEGATIVE = ("Anger", "Contempt", "Disgust", "Fear", "Sadness")

#: Faces smaller than this in either dimension are refused. A 30-pixel face is
#: not a face the model has anything to say about, and a number derived from one
#: would look exactly like a number derived from a good one.
MIN_FACE_PIXELS = 64


class FaceCueUnavailable(RuntimeError):
    """Raised when the vision stack is absent or no face could be found."""


@dataclass(frozen=True)
class FaceStackStatus:
    """Whether a real reading is possible here, and if not, which part is missing.

    A status object rather than a bare bool for the reason `TesseractOCR`
    distinguishes "engine missing" from "language data missing": a page that
    cannot tell the reader which half is absent sends them to reinstall the
    wrong thing.
    """

    ok: bool
    detail: str
    engine: str = ""

    def __bool__(self) -> bool:
        return self.ok


def face_stack_status() -> FaceStackStatus:
    """Report whether `hsemotion-onnx` and OpenCV are importable, and say so.

    Resolved per call rather than cached at import, for the reason
    `extract.extractor_for` gives: a value captured at import cannot change when
    the packages are installed and the app is restarted, and it drifts from what
    the running process would actually find.
    """
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return FaceStackStatus(
            ok=False,
            detail=(
                "opencv-python-headless is not installed, so nothing here can find a "
                "face in an image. The score below is the text score."
            ),
        )
    if not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        # OpenCV 5.0 dropped the Haar cascade API and the bundled cascade files.
        # The import still succeeds there, so this has to be an attribute check:
        # without it the failure surfaces as an AttributeError mid-upload.
        return FaceStackStatus(
            ok=False,
            detail=(
                f"The installed OpenCV ({getattr(cv2, '__version__', 'unknown')}) has no "
                "Haar cascade support, so no face can be located. Install "
                "opencv-python-headless<5. The score below is the text score."
            ),
        )
    try:
        from hsemotion_onnx.facial_emotions import HSEmotionRecognizer  # noqa: PLC0415, F401
    except ImportError:
        return FaceStackStatus(
            ok=False,
            detail=(
                "hsemotion-onnx is not installed, so facial cues cannot be read. The "
                "score below is the text score."
            ),
        )
    return FaceStackStatus(
        ok=True, detail="", engine=f"hsemotion-onnx {MODEL_NAME}, cv2 {cv2.__version__}"
    )


class FaceCueReader:
    """Reads two bounded cues from the largest face in an image. Consent-gated.

    Construction is the gate. `consent` is a required keyword with no default,
    so a caller cannot acquire one of these by forgetting an argument, and
    passing False raises the same `NonVerbalEthicsGate` that Phase 27's
    `GatedRealReader` raised unconditionally. The exception type is deliberately
    unchanged: code and tests that treated the gate as the thing standing
    between this project and a face still see it fire.
    """

    name = "face-cues"
    simulated = False

    def __init__(self, *, consent: bool) -> None:
        if not consent:
            raise NonVerbalEthicsGate(
                "FaceCueReader refuses to run without consent. The uploader must "
                "affirm that the face in the file is their own, or that the person "
                "shown agreed to this, before anything looks at it. See "
                "docs/ethics.md sec.14.2. Without consent the simulated reader is used "
                "and the score comes from the words alone."
            )
        status = face_stack_status()
        if not status:
            raise FaceCueUnavailable(status.detail)
        self.engine = status.engine
        self._recognizer = None

    # -- the model ---------------------------------------------------------

    def _model(self):
        """Load once per reader. Streamlit caches the reader, not this call."""
        if self._recognizer is None:
            # hsemotion-onnx 0.3.1 fetches the ONNX weights on first use with
            # `urllib.request.urlretrieve` while importing only `urllib`, which
            # raises AttributeError on a process that has not imported the
            # submodule. Importing it here binds the attribute before the call.
            # Upstream bug, one line to neutralise, and it costs nothing once the
            # library is fixed.
            import urllib.request  # noqa: PLC0415, F401

            from hsemotion_onnx.facial_emotions import HSEmotionRecognizer  # noqa: PLC0415

            self._recognizer = HSEmotionRecognizer(model_name=MODEL_NAME)
        return self._recognizer

    # -- reading -----------------------------------------------------------

    def _largest_face(self, image):
        """The biggest detected face, as an RGB array. Raises when there is none.

        Largest rather than first: a press photograph has a crowd behind the
        subject, and the subject is the large face in the foreground. This is a
        heuristic and it is stated as one on the page, because a reading of the
        wrong face is worse than no reading.
        """
        import cv2  # noqa: PLC0415

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
        if len(faces) == 0:
            raise FaceCueUnavailable(
                "No face was found in that image, so no facial cues were read and the "
                "score below comes from the words alone."
            )
        x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        if min(w, h) < MIN_FACE_PIXELS:
            raise FaceCueUnavailable(
                f"The largest face found is {w}x{h} pixels, smaller than the "
                f"{MIN_FACE_PIXELS}-pixel minimum, so it was not read."
            )
        face = image[y : y + h, x : x + w]
        return cv2.cvtColor(face, cv2.COLOR_BGR2RGB)

    def read(self, data: bytes) -> NonVerbalReading:
        """Two cues from one image, or a refusal. Never a default and never a zero."""
        import cv2  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise FaceCueUnavailable(
                "That file could not be decoded as an image, so no facial cues were read."
            )
        face = self._largest_face(image)
        _, scores = self._model().predict_emotions(face, logits=False)
        features = _features_from_scores(list(np.asarray(scores, dtype=float).ravel()))
        return NonVerbalReading(source=self.name, stamp=FACE_STAMP, features=features)


def _features_from_scores(scores: list[float]) -> dict[str, float]:
    """Turn the model's output row into the two bounded features this project uses.

    The multi-task model returns eight expression scores followed by valence and
    arousal, each in [-1, 1]. Both are rescaled to [0, 1] because
    `NonVerbalReading` bounds every feature there, and valence is *inverted* on
    the way: the feature is `negative_valence`, so that a larger number means a
    more negative-looking expression and the declared weight can be positive
    like every other risk-raising term in `fusion.MAGNITUDES`.

    If a build returns only the eight expression scores, valence is derived from
    the negative-expression mass and arousal is left at the neutral midpoint,
    which is the coarser reading rather than a wrong one. The page shows the
    engine string, so which path ran is visible.
    """
    if len(scores) >= len(EXPRESSIONS) + 2:
        valence, arousal = scores[-2], scores[-1]
        return {
            "negative_valence": _unit((1.0 - float(valence)) / 2.0),
            "arousal": _unit((float(arousal) + 1.0) / 2.0),
        }
    if len(scores) >= len(EXPRESSIONS):
        total = sum(abs(value) for value in scores[: len(EXPRESSIONS)]) or 1.0
        negative = sum(abs(scores[EXPRESSIONS.index(name)]) for name in _NEGATIVE)
        return {"negative_valence": _unit(negative / total), "arousal": 0.5}
    raise FaceCueUnavailable(
        f"The engine returned {len(scores)} values, which this code does not know how "
        "to read. No cues were produced."
    )


def _unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def face_context_weights(*, measured: bool) -> dict[str, float]:
    """The weights a reading carries. Empty unless a real face was read.

    `measured` is what separates the two cases, and it is the reader's own
    `simulated` flag at the call site rather than a guess: a hash of file bytes
    is shown at weight zero, a face is weighted by `FACE_WEIGHTS`.
    """
    return dict(FACE_WEIGHTS) if measured else {}


def face_cue_reader(*, consent: bool):
    """A `FaceCueReader` when one can be built, otherwise None with the reason.

    Returns `(reader, detail)`. The page renders `detail` whenever `reader` is
    None, so "we did not read the face" is always accompanied by which of the
    four reasons it was: no consent, no library, no face, or a face too small.
    """
    if not consent:
        return None, ""
    try:
        return FaceCueReader(consent=True), ""
    except (NonVerbalEthicsGate, FaceCueUnavailable) as exc:
        return None, str(exc)


# Re-exported for the mediaio bridge, so it imports one name set from one place.
FACE_FEATURE_NAMES = FACE_FEATURES
