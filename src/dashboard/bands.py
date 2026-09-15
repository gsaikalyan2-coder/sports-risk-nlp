"""The 0-100 presentation of the risk index, and the band label that goes with it.

Read this before changing anything here
---------------------------------------
`charts.py::risk_meter` refuses to draw bands, and says why: banding an
uncalibrated ranking score invents thresholds nothing in this project supports,
and a coloured band reads as a verdict about a person. That argument has not
changed. This module exists because the dashboard was asked for a 0-100 score
with labelled bands, and the honest way to give one is to make the band
inseparable from the statement of what it is not.

So three constructional decisions:

* **A band cannot be constructed without its caveat.** `Band.caveat` is a
  required field, `describe()` always emits it, and the widget that renders a
  band renders `describe()`, never `band.label` alone. There is no code path
  that produces the word "Elevated" on its own.
* **The thresholds are stated as what they are: thirds of the scale.** They are
  not derived from outcomes, because no observed outcome exists (OPEN-025), and
  they are not derived from the corpus distribution, because a percentile
  presented as a band is a stronger claim than this project can make. A third of
  a ranking scale is an arithmetic fact about the scale, and the caveat says so.
* **Bands never reach the paper figures.** `risk_meter` and the other marks in
  `charts.py` do not import this module, and `tests/test_dashboard_pages.py`
  asserts they never will. The band is a reading aid on one screen, not a result.

The 0-100 scaling is presentation too: it is the same index multiplied by 100
and rounded, carrying the same PROVISIONAL stamp. Multiplying a number by 100
does not make it a percentage, and `SCALE_NOTE` says that in words.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.dashboard.view import DashboardView, ScoreSurface, assert_no_forbidden_language

SCALE_NOTE = (
    "The 0-100 figure is the risk index multiplied by 100, nothing more. It is not a "
    "percentage, not a probability, and not a score out of 100 in the sense a test "
    "result is: it orders texts from calmer-sounding to more strained-sounding and "
    "carries no meaning on its own."
)

BAND_CAVEAT = (
    "Bands are thirds of the 0-100 scale, and nothing else. They are not severity "
    "levels, not thresholds anyone validated, and not a statement about a person -- no "
    "observed outcome exists in this project to calibrate a threshold against. Two "
    "texts either side of a boundary are barely different; the label changes, the "
    "reading does not."
)


@dataclass(frozen=True)
class Band:
    """A label for a stretch of the scale, inseparable from what it is not."""

    label: str
    lower: int
    upper: int
    caveat: str

    def __post_init__(self) -> None:
        if not self.caveat.strip():
            raise ValueError(
                f"Band({self.label!r}) has no caveat. A band label with no statement of "
                "what it is not is a verdict about a person; see this module's docstring "
                "and charts.py::risk_meter."
            )
        assert_no_forbidden_language(f"{self.label} {self.caveat}")

    def describe(self) -> str:
        """The only form in which a band may be shown to a reader."""
        return f"{self.label} ({self.lower}-{self.upper} on the scale): {self.caveat}"


#: Thirds. Named for where they sit on the scale, not for what they imply about
#: anyone: "lower third" is a position, "mild" would be a diagnosis-shaped word.
BANDS: tuple[Band, ...] = (
    Band("Lower third of the scale", 0, 33, BAND_CAVEAT),
    Band("Middle third of the scale", 34, 66, BAND_CAVEAT),
    Band("Upper third of the scale", 67, 100, BAND_CAVEAT),
)


def band_for(score_100: float) -> Band:
    """The band a 0-100 score falls in. Total over the scale by construction."""
    value = max(0.0, min(100.0, float(score_100)))
    for band in BANDS:
        if value <= band.upper:
            return band
    return BANDS[-1]


@dataclass(frozen=True)
class PsychologicalScore:
    """The Page 2 result: one number, its band, and its ten dimensions.

    Holds no arithmetic of its own beyond the ×100 scaling -- every value comes
    from a `DashboardView`, which has already been through the publication guard
    and the forbidden-vocabulary screen.
    """

    surface: ScoreSurface
    score_100: int
    band: Band
    dimensions: tuple[tuple[str, float, float], ...]
    detected: int

    @property
    def stamp(self) -> str:
        return self.surface.stamp


def score_from_view(view: DashboardView) -> PsychologicalScore:
    """Turn a scored view into the Page 2 presentation. No new numbers."""
    score_100 = int(round(view.risk.value * 100))
    return PsychologicalScore(
        surface=view.risk,
        score_100=score_100,
        band=band_for(score_100),
        dimensions=tuple((bar.construct, bar.probability, bar.contribution) for bar in view.bars),
        detected=sum(1 for bar in view.bars if bar.detected),
    )
