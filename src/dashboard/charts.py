"""SVG marks for the dashboard, drawn to survive being a paper figure.

Why these forms and not the obvious ones
-----------------------------------------
The brief said "construct bars and a risk gauge". Both defaults are wrong, and
the reasons are worth writing down because they recur:

**A radial gauge is the wrong mark for the risk index.** A dial's arc length is
read as a proportion of a whole, and the risk index is not a proportion of
anything -- it is an uncalibrated ranking score. Worse, the speedometer form
carries a strong "measurement of a thing" connotation, which for a number that
is explicitly *not* a measurement of a person is the connotation this project
most needs to avoid. The right form for a single ratio against a scale is a
**meter**: a linear track with a marker, which reads as a position rather than a
verdict, and which is legible at figure size in one column.

**A ten-bar categorical chart is the wrong mark for the decomposition.** Ten
categorical hues cannot be told apart by anyone, colourblind or not (`dataviz`
caps categorical series at eight, softly at six). But the constructs are not
series -- they are rows of a single comparison, so the encoding is *position*
down a shared axis with one hue per direction, which is a diverging bar chart.

**Sign is encoded by position, not by colour.** A bar left of the zero line
lowers risk and a bar right of it raises risk, and that is true in grayscale, in
print, under any colour vision, and with the stylesheet stripped. Colour is a
redundant second channel, never the carrier.

**The four inert constructs are marked three times over.** Hatch fill, dashed
outline, and the literal word `inert` in the row label. `PROJECT_PLAN.md` Phase
24 gates on "figures legible in grayscale", and a marking that leans on colour
would pass review here and fail there -- after the figure had been drawn. C2.5
is explicit: if the dashboard draws ten bars, the four inert ones must be
visibly non-contributing, or the picture asserts something the numbers do not.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from html import escape

from src.dashboard.view import ConstructBar, ScoreSurface

#: Referenced by the honesty tests. A pattern id rather than a colour, because
#: the test is checking that a *non-colour* channel carries the marking.
INERT_HATCH_ID = "inert-hatch"

# Diverging pair, from the dataviz reference palette. Blue lowers, red raises;
# the neutral midpoint is the zero rule itself.
COLOUR_RAISES = "#e34948"
COLOUR_LOWERS = "#2a78d6"
COLOUR_SEQUENTIAL = "#2a78d6"
COLOUR_INK = "#0b0b0b"
COLOUR_MUTED = "#898781"
COLOUR_RULE = "#c3c2b7"
COLOUR_GRID = "#e1e0d9"
COLOUR_SURFACE = "#fcfcfb"

FONT = 'font-family="system-ui, -apple-system, Segoe UI, sans-serif"'

ROW_HEIGHT = 26
LABEL_WIDTH = 200
CHART_WIDTH = 640


def _hatch_id(kind: str, bars: Sequence[ConstructBar]) -> str:
    """A pattern id unique to this chart's content, derived deterministically.

    Found by looking at a screenshot rather than by reasoning, which is the
    reason the verification step exists: SVG `id`s share one namespace per
    document, Streamlit keeps the DOM of *every* tab mounted, and a second chart
    defining `inert-hatch` silently won the reference for the first. The hatch
    disappeared on one tab while the tests -- which render each chart in
    isolation -- stayed green. Exactly the shape this phase was warned about: the
    check and the thing it protects related by assumption.

    Derived from the data rather than from a counter so the output stays
    byte-stable across runs: two charts drawing identical data get identical ids,
    which is harmless because they are the same picture.
    """
    payload = f"{kind}|" + "|".join(
        f"{b.construct}:{b.contribution:.6f}:{b.probability:.6f}:{b.inert}" for b in bars
    )
    return f"{INERT_HATCH_ID}-{hashlib.sha1(payload.encode()).hexdigest()[:8]}"


def _defs(hatch_id: str) -> str:
    """The hatch pattern that marks a non-contributing construct.

    45 degrees, tone-on-tone, inked in the muted ink rather than in a series
    colour -- an inert construct is the absence of a contribution, so giving it a
    hue would place it in the same visual family as the constructs that did
    contribute.
    """
    return (
        f'<defs><pattern id="{hatch_id}" width="6" height="6" '
        'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        f'<rect width="6" height="6" fill="{COLOUR_SURFACE}"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{COLOUR_MUTED}" stroke-width="2"/>'
        "</pattern></defs>"
    )


def _label(construct: str, inert: bool) -> str:
    pretty = construct.replace("_", " ")
    return f"{pretty} (inert)" if inert else pretty


def construct_contribution_chart(bars: Sequence[ConstructBar], *, width: int = CHART_WIDTH) -> str:
    """Signed contribution to the risk index, one row per construct.

    Diverging: left of the rule lowers risk, right of it raises risk. The four
    directionally unresolved constructs sit exactly on the rule with a hatched,
    dashed zero-width marker and an `(inert)` label, so a reader can see both
    that they were detected and that they did nothing.
    """
    rows = list(bars)
    height = len(rows) * ROW_HEIGHT + 56
    plot_width = width - LABEL_WIDTH - 60
    centre = LABEL_WIDTH + plot_width / 2
    span = max((abs(b.contribution) for b in rows), default=1.0) or 1.0
    scale = (plot_width / 2 - 8) / span
    hatch = _hatch_id("contribution", rows)

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Signed contribution to the risk index, per construct">',
        _defs(hatch),
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "Contribution to the risk index</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        "left of the rule lowers risk, right raises it — sign is position, not colour</text>",
    ]

    top = 46
    for i, bar in enumerate(rows):
        y = top + i * ROW_HEIGHT
        mid = y + ROW_HEIGHT / 2
        out.append(
            f'<text x="8" y="{mid + 4:.1f}" {FONT} font-size="11" '
            f'fill="{COLOUR_MUTED if bar.inert else COLOUR_INK}">'
            f"{escape(_label(bar.construct, bar.inert))}</text>"
        )
        if bar.inert:
            # A zero-length bar is invisible, so the marker is drawn as a small
            # hatched, dashed box straddling the rule: present, and plainly not
            # a contribution.
            out.append(
                f'<rect x="{centre - 9:.1f}" y="{y + 5:.1f}" width="18" height="14" '
                f'fill="url(#{hatch})" stroke="{COLOUR_MUTED}" stroke-width="1.5" '
                'stroke-dasharray="3 2" rx="3"/>'
            )
            out.append(
                f'<text x="{centre + 16:.1f}" y="{mid + 4:.1f}" {FONT} font-size="10" '
                f'fill="{COLOUR_MUTED}" font-style="italic">inert — no direction</text>'
            )
            continue

        length = abs(bar.contribution) * scale
        raises = bar.contribution > 0
        x = centre if raises else centre - length
        colour = COLOUR_RAISES if raises else COLOUR_LOWERS
        out.append(
            f'<rect x="{x:.1f}" y="{y + 5:.1f}" width="{max(length, 1.0):.1f}" height="14" '
            f'fill="{colour}" rx="3"/>'
        )
        label_x = centre + length + 6 if raises else centre - length - 6
        anchor = "start" if raises else "end"
        out.append(
            f'<text x="{label_x:.1f}" y="{mid + 4:.1f}" {FONT} font-size="10" '
            f'fill="{COLOUR_INK}" text-anchor="{anchor}">{bar.contribution:+.3f}</text>'
        )

    out.append(
        f'<line x1="{centre:.1f}" y1="{top}" x2="{centre:.1f}" y2="{top + len(rows) * ROW_HEIGHT}" '
        f'stroke="{COLOUR_RULE}" stroke-width="1.5"/>'
    )
    out.append("</svg>")
    return "".join(out)


def construct_probability_chart(bars: Sequence[ConstructBar], *, width: int = CHART_WIDTH) -> str:
    """How strongly each construct was detected, independent of what it did to risk.

    Sequential, one hue -- these are magnitudes on a shared scale, not identities.
    Drawn alongside the contribution chart rather than combined with it: two
    measures on different scales get two charts, never two axes.
    """
    rows = list(bars)
    height = len(rows) * ROW_HEIGHT + 56
    plot_width = width - LABEL_WIDTH - 60
    hatch = _hatch_id("probability", rows)
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Detection strength per construct">',
        _defs(hatch),
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "Detection strength per construct</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        "a construct can be strongly detected and still move the index by nothing</text>",
    ]
    top = 46
    for i, bar in enumerate(rows):
        y = top + i * ROW_HEIGHT
        mid = y + ROW_HEIGHT / 2
        out.append(
            f'<line x1="{LABEL_WIDTH}" y1="{y + 12:.1f}" x2="{LABEL_WIDTH + plot_width}" '
            f'y2="{y + 12:.1f}" stroke="{COLOUR_GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="8" y="{mid + 4:.1f}" {FONT} font-size="11" '
            f'fill="{COLOUR_MUTED if bar.inert else COLOUR_INK}">'
            f"{escape(_label(bar.construct, bar.inert))}</text>"
        )
        length = max(bar.probability, 0.0) * plot_width
        fill = f"url(#{hatch})" if bar.inert else COLOUR_SEQUENTIAL
        stroke = (
            f' stroke="{COLOUR_MUTED}" stroke-width="1.5" stroke-dasharray="3 2"'
            if bar.inert
            else ""
        )
        if length >= 1.0:
            out.append(
                f'<rect x="{LABEL_WIDTH}" y="{y + 5:.1f}" width="{length:.1f}" height="14" '
                f'fill="{fill}"{stroke} rx="3"/>'
            )
        suffix = " — inert" if bar.inert else ""
        out.append(
            f'<text x="{LABEL_WIDTH + length + 6:.1f}" y="{mid + 4:.1f}" {FONT} '
            f'font-size="10" fill="{COLOUR_INK}">{bar.probability:.2f}{suffix}</text>'
        )
    out.append("</svg>")
    return "".join(out)


def risk_meter(surface: ScoreSurface, *, width: int = CHART_WIDTH) -> str:
    """A linear meter, not a dial. See the module docstring for why.

    The track is unlabelled at its ends beyond `0` and `1` -- no "low / moderate
    / high" bands, because banding an uncalibrated ranking score invents
    thresholds that nothing in this project supports, and a coloured band is read
    as a verdict about a person.
    """
    height = 96
    track_x, track_w = 16, width - 32
    position = track_x + max(0.0, min(1.0, surface.value)) * track_w
    return "".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="Risk index meter, ranking only, not calibrated">',
            f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
            f'<text x="16" y="20" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
            f"{escape(surface.label)}</text>",
            f'<text x="{width - 16}" y="20" {FONT} font-size="22" fill="{COLOUR_INK}" '
            f'text-anchor="end">{escape(surface.display)}</text>',
            f'<rect x="{track_x}" y="38" width="{track_w}" height="10" rx="5" '
            f'fill="{COLOUR_GRID}"/>',
            f'<rect x="{track_x}" y="38" width="{position - track_x:.1f}" height="10" rx="5" '
            f'fill="{COLOUR_SEQUENTIAL}"/>',
            f'<line x1="{position:.1f}" y1="32" x2="{position:.1f}" y2="54" '
            f'stroke="{COLOUR_INK}" stroke-width="2.5"/>',
            f'<text x="{track_x}" y="68" {FONT} font-size="10" fill="{COLOUR_MUTED}">0</text>',
            f'<text x="{track_x + track_w}" y="68" {FONT} font-size="10" '
            f'fill="{COLOUR_MUTED}" text-anchor="end">1</text>',
            f'<text x="16" y="86" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
            "ranking only — not calibrated; no observed outcome exists to calibrate "
            "against</text>",
            "</svg>",
        ]
    )
