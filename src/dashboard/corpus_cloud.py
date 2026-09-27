"""Loads, validates and freezes `reports/corpus_cloud.json`.

Why a loader and not a JSON read in the page
--------------------------------------------
The artifact is 4,000 records' worth of risk index, and a risk index is the most
over-read number this project produces. Read naively it is a list of floats that
a figure can draw without ever stating what they are. So it goes through the same
door every other number goes through: a validated object whose construction fails
if the provenance is missing, with each displayed value wrapped in a
`ScoreSurface` that cannot exist without its stamp.

`atlas_map.py` made this argument for a config file of claims; this makes it for
an artifact of numbers, and the refusals are the same shape -- structural, at
load, rather than a warning nobody reads.

What this refuses, and why each one is a refusal
------------------------------------------------
* **An artifact with no PROVISIONAL stamp.** Identical to `ScoreSurface`: a number
  without provenance is a claim with nothing attached. The artifact is committed,
  so a hand-edited copy is exactly the thing worth catching.
* **A lane naming a construct outside the frozen taxonomy, or a missing lane.**
  Both halves, for the reason `atlas_map` gives: an unknown lane draws a row for
  something the model does not predict, and a missing lane silently shows nine of
  ten while nobody counts rows.
* **A lane whose counts do not reconcile.** `n_scored + n_silent == n_planted` is
  the artifact's own arithmetic. If it does not hold, the caption "N plotted, M
  with nothing detected" is describing a different corpus from the dots.
* **A lane with a median and no scored records, or scored records and no median.**
  The `.claude.md` section 12.3 rule again, one level up: a lane the detector said
  nothing about does not get a number, and specifically does not get 0.50.
* **A dot outside 0 to 1.** The index is a squashed logistic; a value outside the
  range means the artifact was not produced by the code that claims to have
  produced it.
* **More dots than scored records.** The dots are a sample of the scored records.
  A file with more dots than records sampled is a file that invented some.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.dashboard.copy import CONSTRUCTS as PLAIN_CONSTRUCTS
from src.dashboard.view import ScoreSurface
from src.evaluation.harness import PROVISIONAL_STAMP
from src.models.dataset import CONSTRUCTS

REPO_ROOT = Path(__file__).resolve().parents[2]
CLOUD_PATH = REPO_ROOT / "reports" / "corpus_cloud.json"

REBUILD_HINT = (
    "The corpus cloud has not been built. It is a committed artifact produced by "
    "`python scripts/build_corpus_cloud.py`, which needs the regenerable corpus in "
    "data/raw/ (`python scripts/run_ingestion.py --seed 42`). Nothing on this page is "
    "computed live: scoring 4,000 records takes about three minutes, which is not a "
    "page load."
)


class CorpusCloudError(ValueError):
    """Raised when `corpus_cloud.json` says something it is not entitled to say."""


class CorpusCloudMissing(CorpusCloudError):
    """The artifact is absent. Carries the rebuild instruction for the page."""


@dataclass(frozen=True)
class CloudLane:
    """One construct's lane: what was planted, what was scored, and where it sits.

    `median` is `None` exactly when nothing in the lane was scored. Same structural
    rule as `ribbon.SentenceBand`: no detection, no number, and specifically not
    the 0.50 an all-zero decomposition squashes to.
    """

    construct: str
    plain_name: str
    n_planted: int
    n_scored: int
    n_silent: int
    median: ScoreSurface | None
    dots: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.construct not in CONSTRUCTS:
            raise CorpusCloudError(
                f"{self.construct!r} is not in the frozen taxonomy. A lane for a "
                "construct the model does not predict would be drawn from some other "
                "construct's records."
            )
        if self.n_scored + self.n_silent != self.n_planted:
            raise CorpusCloudError(
                f"{self.construct!r} counts do not reconcile: {self.n_scored} scored + "
                f"{self.n_silent} silent != {self.n_planted} planted. The lane caption "
                "would be describing a different corpus from the dots."
            )
        if (self.median is None) != (self.n_scored == 0):
            raise CorpusCloudError(
                f"{self.construct!r} has {self.n_scored} scored records and "
                f"{'no' if self.median is None else 'a'} median. A lane the detector "
                "said nothing about may not carry a number: an all-zero decomposition "
                "squashes to exactly 0.50. See .claude.md section 12.3."
            )
        if len(self.dots) > self.n_scored:
            raise CorpusCloudError(
                f"{self.construct!r} plots {len(self.dots)} dots from {self.n_scored} "
                "scored records; the dots are a sample, so this file invented some."
            )
        for value in self.dots:
            if not 0.0 <= value <= 1.0:
                raise CorpusCloudError(
                    f"{self.construct!r} carries a dot at {value}, outside the 0-to-1 "
                    "range a squashed index can occupy."
                )


@dataclass(frozen=True)
class CorpusCloud:
    """The whole validated artifact, frozen."""

    corpus: str
    backend: str
    policy: str
    stamp: str
    provenance: str
    scale_label: str
    caveat: str
    n_records: int
    n_scored: int
    n_silent: int
    n_unplanted: int
    dots_per_lane: int
    lanes: tuple[CloudLane, ...]

    def __post_init__(self) -> None:
        if PROVISIONAL_STAMP.split(" -- ")[0] not in self.stamp:
            raise CorpusCloudError(
                "corpus_cloud.json carries no PROVISIONAL provenance stamp. Every "
                "number in this repository is agreement with generator-planted labels "
                "on synthetic text; see src/evaluation/harness.py."
            )
        if self.n_scored + self.n_silent != self.n_records:
            raise CorpusCloudError(
                f"{self.n_scored} scored + {self.n_silent} silent != {self.n_records} "
                "records. Every record is one or the other."
            )
        named = {lane.construct for lane in self.lanes}
        if missing := set(CONSTRUCTS) - named:
            raise CorpusCloudError(
                f"corpus_cloud.json has no lane for {sorted(missing)}. Every construct "
                "gets a row, or the figure shows nine of ten and nobody counts rows."
            )

    @property
    def sample_note(self) -> str:
        """What the dots are, stated on the figure rather than in a footnote here."""
        return (
            "medians and counts are over every scored record; the dots are a fixed "
            f"stride sample of up to {self.dots_per_lane} per lane"
        )

    @property
    def surfaces(self) -> tuple[ScoreSurface, ...]:
        """The page's headline counts, each inseparable from its stamp."""
        return (
            ScoreSurface(
                label="Records plotted",
                value=float(self.n_scored),
                display=f"{self.n_scored} of {self.n_records}",
                detail="records where at least one construct was detected",
                stamp=self.stamp,
            ),
            ScoreSurface(
                label="Records with nothing detected",
                value=float(self.n_silent),
                display=f"{self.n_silent} of {self.n_records}",
                detail=(
                    "the word list matched nothing in these, so they carry no index and "
                    "are absent from the figure rather than drawn at the midpoint"
                ),
                stamp=self.stamp,
            ),
            ScoreSurface(
                label="Records with nothing planted",
                value=float(self.n_unplanted),
                display=f"{self.n_unplanted} of {self.n_records}",
                detail="generator planted no construct, so they belong to no lane",
                stamp=self.stamp,
            ),
        )

    def lane(self, construct: str) -> CloudLane:
        for lane in self.lanes:
            if lane.construct == construct:
                return lane
        raise KeyError(f"{construct!r} has no lane in corpus_cloud.json")


@lru_cache(maxsize=2)
def load_cloud(path: str | None = None) -> CorpusCloud:
    """Load, validate and freeze the artifact. Cached: the file does not change."""
    source = Path(path) if path else CLOUD_PATH
    if not source.exists():
        raise CorpusCloudMissing(REBUILD_HINT)
    data = json.loads(source.read_text(encoding="utf-8"))
    stamp = str(data.get("stamp", ""))
    # Checked here as well as in `CorpusCloud.__post_init__`, and the duplication is
    # deliberate: the surfaces are built *before* the container, so a stamp-less
    # artifact would otherwise be caught by `ScoreSurface` instead -- a correct
    # refusal wearing the wrong exception type and a message about one median rather
    # than about the file. The page catches `CorpusCloudError`; it should not have to
    # catch `ValueError` to survive a hand-edited artifact.
    if PROVISIONAL_STAMP.split(" -- ")[0] not in stamp:
        raise CorpusCloudError(
            f"{source.name} carries no PROVISIONAL provenance stamp, so none of its "
            "numbers may be shown. Rebuild it with scripts/build_corpus_cloud.py "
            "rather than editing it."
        )

    lanes: list[CloudLane] = []
    for entry in data.get("lanes") or ():
        construct = str(entry["construct"])
        plain_name = PLAIN_CONSTRUCTS.get(construct, (construct.replace("_", " "),))[0]
        median = entry.get("median")
        lanes.append(
            CloudLane(
                construct=construct,
                plain_name=plain_name,
                n_planted=int(entry["n_planted"]),
                n_scored=int(entry["n_scored"]),
                n_silent=int(entry["n_silent"]),
                median=(
                    ScoreSurface(
                        label=f"Median index, {plain_name}",
                        value=float(median),
                        display=f"{float(median):.2f}",
                        detail=(
                            "middle of the scored records the generator planted this "
                            "construct in; ranking only, not calibrated"
                        ),
                        stamp=stamp,
                    )
                    if median is not None
                    else None
                ),
                dots=tuple(float(value) for value in entry.get("dots") or ()),
            )
        )

    return CorpusCloud(
        corpus=str(data.get("corpus", "")),
        backend=str(data.get("backend", "")),
        policy=str(data.get("policy", "")),
        stamp=stamp,
        provenance=str(data.get("provenance", "")),
        scale_label=str(data.get("scale_label", "")),
        caveat=str(data.get("caveat", "")),
        n_records=int(data["n_records"]),
        n_scored=int(data["n_scored"]),
        n_silent=int(data["n_silent"]),
        n_unplanted=int(data["n_unplanted"]),
        dots_per_lane=int(data["dots_per_lane"]),
        lanes=tuple(sorted(lanes, key=lambda lane: lane.construct)),
    )
