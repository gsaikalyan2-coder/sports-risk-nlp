"""The ten construct widgets: values only, one per construct.

Page 1 shows numbers and no explanation -- that is the brief, and it is also the
riskiest screen this project has produced, because a number with its provenance
stripped off is exactly what `ScoreSurface` was built to prevent. Two mechanisms
keep it honest rather than two conventions:

* **Every widget carries the stamp of the surface it came from.** `Widget.stamp`
  is required and is read off the view, not attached at render time. The page
  renders it once above the grid (it is identical for every widget), and
  `tests/test_dashboard_pages.py` asserts it is on the page before any expander.
* **A widget names its own detail page.** `Widget.construct` is the key the
  detail page reads; there is no free-text route, so a widget cannot link to an
  explanation of a different construct.

The values shown are the two the view already holds for each construct --
detection strength and signed contribution -- and nothing derived from them.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.dashboard.copy import (
    ATLAS_TILE_CAPTION,
    ATLAS_TILE_LABEL,
    CONSTRUCTS,
    DIRECTION_PLAIN,
    LOAD_TILE_CAPTION,
    LOAD_TILE_LABEL,
    NF_TILE_CAPTION,
    NF_TILE_LABEL,
)
from src.dashboard.view import (
    POLICY_SHORT,
    ConstructBar,
    DashboardView,
)


@dataclass(frozen=True)
class Widget:
    """One construct's tile: a name, two values, and where it came from."""

    construct: str
    title: str
    value: str
    value_caption: str
    secondary: str
    secondary_caption: str
    inert: bool
    detected: bool
    stamp: str
    #: True for the four constructs whose direction the taxonomy leaves open.
    #: Carried rather than re-derived from a name list, so a tile cannot claim
    #: two-sidedness the arithmetic did not use -- the same rule
    #: `view._bars_for` applies to `inert`.
    two_sided: bool = False
    #: The policy that produced `secondary`, as `PolarityPolicy.value`.
    policy_key: str = "neutral"

    def __post_init__(self) -> None:
        if not self.stamp.strip():
            raise ValueError(
                f"Widget({self.construct!r}) has no provenance stamp. A tile showing a "
                "bare number with no statement of what it is is the failure mode this "
                "dashboard exists to avoid."
            )


def _widget(bar: ConstructBar, stamp: str, policy_key: str) -> Widget:
    """One tile, with the two-sided four reading off the policy in force.

    The four constructs whose direction the taxonomy leaves open are the reason
    the policy selector exists, and before this they were the only tiles on the
    grid that looked identical whichever way it was set: `inert` flipped, so the
    hatching went away, but the caption still said "shown, but counted as zero"
    because it was keyed off the taxonomy's static `direction` field rather than
    off the arithmetic. A tile that reports the wrong assumption is worse than a
    tile that reports none, so the caption is now derived from `policy_key` --
    the same value `fusion.score` used -- and the secondary value is the signed
    push the policy actually produced.

    Two-sidedness itself is still read off the live decomposition
    (`ConstructBar.direction == "polar"`), never off a name list, for the reason
    `view._bars_for` gives: a name list is correct until the first ablation.
    """
    title, _, direction = CONSTRUCTS.get(
        bar.construct, (bar.construct.replace("_", " "), "", "inert" if bar.inert else "raises")
    )
    two_sided = bar.direction == "polar"

    if bar.inert:
        # Conservative default: the construct was detected and then discarded.
        secondary = "counted as zero"
        secondary_caption = DIRECTION_PLAIN[direction]
    elif two_sided and not bar.detected:
        # The setting resolved this construct's direction, and the text did not
        # trigger it, so the resolution has nothing to multiply. Said out loud,
        # because the alternative is a reader moving the switch, watching four
        # tiles read +0.000 either way, and concluding the switch is broken --
        # which is how the first committed example actually behaves.
        secondary = f"{bar.contribution:+.3f}"
        secondary_caption = "not picked up in this text, so the setting cannot move it"
    elif two_sided:
        # The policy resolved it. Say which way, in the tile, next to the number
        # that moved -- a reader screenshotting one tile carries the assumption.
        #
        # The side is read off the POLICY, not off the sign of the contribution.
        # Taking it from the sign looks equivalent and is not: a contribution of
        # exactly zero has no sign, and every undetected construct would then be
        # labelled "good news" under both settings.
        secondary = f"{bar.contribution:+.3f}"
        side = "bad news" if policy_key == "pessimistic" else "good news"
        secondary_caption = f"read as {side} ({POLICY_SHORT.get(policy_key, policy_key)} setting)"
    else:
        secondary = f"{bar.contribution:+.3f}"
        secondary_caption = "push on the index"

    return Widget(
        construct=bar.construct,
        title=title,
        value=f"{bar.probability:.2f}",
        value_caption="detection strength, 0 to 1",
        secondary=secondary,
        secondary_caption=secondary_caption,
        inert=bar.inert,
        detected=bar.detected,
        stamp=stamp,
        two_sided=two_sided,
        policy_key=policy_key,
    )


def widgets_for(view: DashboardView) -> tuple[Widget, ...]:
    """Ten tiles, strongest detection first.

    Ordered by detection strength rather than alphabetically because the grid is
    scanned for "what did this text set off"; `charts.py` keeps alphabetical
    order for the figures, which are scanned for a named row. Same ten rows, two
    reading tasks.
    """
    bars = sorted(view.bars, key=lambda b: (b.inert, -b.probability, b.construct))
    return tuple(_widget(bar, view.risk.stamp, view.policy_key) for bar in bars)


def widget_for(view: DashboardView, construct: str) -> Widget:
    """The one tile a detail page was opened for."""
    for widget in widgets_for(view):
        if widget.construct == construct:
            return widget
    raise KeyError(f"{construct!r} is not a construct in this view.")


def atlas_widget(view: DashboardView) -> Widget:
    """The Phase 26 / V1 summary tile: how many signals have a place on the sketch.

    Built through the same `Widget` contract as the ten construct tiles, so it
    carries the view's stamp and cannot be constructed without one. It counts
    rows in `config/brain_atlas.yaml` rather than nodes in the rendered figure --
    a count taken off the picture would agree with the picture by construction
    and so could never catch the picture being wrong.

    The number is a count of mappings, not a detection, which is why the caption
    says "out of ten" rather than naming a strength: a construct with a place on
    the sketch has a place whether or not this text triggered it.
    """
    from src.dashboard.atlas_map import load_atlas

    atlas = load_atlas()
    mapped = len(atlas.mapped)
    detected = sum(1 for bar in view.bars if bar.detected and not atlas.row(bar.construct).unmapped)
    return Widget(
        construct="brain_atlas",
        title=CONSTRUCTS.get("brain_atlas", (ATLAS_TILE_LABEL, "", ""))[0],
        value=f"{mapped} of {len(atlas.rows)}",
        value_caption=ATLAS_TILE_CAPTION,
        secondary=f"{detected} picked up in this text",
        secondary_caption="the rest have a place on the sketch and nothing in the words",
        inert=False,
        detected=detected > 0,
        stamp=view.risk.stamp,
    )


def load_widget(window) -> Widget:
    """The Phase 26 / V3 summary tile: the load index and its provenance stamp.

    Takes the stamp off the window, so a tile cannot exist for a trace whose
    origin was not stated -- `BiosignalWindow` refuses to be built without one,
    and `Widget` refuses to be built without one, so the property holds at both
    ends rather than being carried by a convention in between.

    The caption is the uncalibrated wording verbatim. No band, no threshold and
    no severity word reaches this tile; `tests/test_neurovis.py` asserts it.
    """
    return Widget(
        construct="load_index",
        title=LOAD_TILE_LABEL,
        value=f"{window.features['load_index']:.2f}",
        value_caption=LOAD_TILE_CAPTION,
        secondary=f"{window.features['hf_hrv']:.0f} ms2 · {window.features['pupil_effort']:+.2f} z",
        secondary_caption="heart-rate variability and pupil, this window",
        inert=False,
        detected=True,
        stamp=window.stamp,
    )


def neurofeedback_widget(session, ratios, *, stamp: str) -> Widget:
    """The Phase 26 / V5 summary tile: time in target for the last demo session.

    The arithmetic comes from `NeurofeedbackSession.run`, which is pure and
    tested without a browser -- the tile reads a state, it does not count. The
    caption carries the demo wording, because a "time in target" figure lifted
    out of this page and into a slide would otherwise read as a training result
    for a person who does not exist.
    """
    state = session.run(ratios)
    return Widget(
        construct="neurofeedback",
        title=NF_TILE_LABEL,
        value=f"{state.in_target_s:.0f}s",
        value_caption=NF_TILE_CAPTION + ", generated signal, no person",
        secondary=f"{state.longest_hold_s:.0f}s longest hold",
        secondary_caption=f"over {state.elapsed_s:.0f}s of generated signal",
        inert=False,
        detected=True,
        stamp=stamp,
    )
