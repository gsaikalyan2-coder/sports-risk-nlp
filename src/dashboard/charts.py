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

from src.dashboard import theme
from src.dashboard.view import ConstructBar, ScoreSurface

#: Referenced by the honesty tests. A pattern id rather than a colour, because
#: the test is checking that a *non-colour* channel carries the marking.
INERT_HATCH_ID = "inert-hatch"

# Palette and type come from `theme.py`, which renders the same tokens into the
# shell's CSS and the panels' iframe CSS. One source, three surfaces -- the
# legend swatches on the panel drifted two phases behind the bars when each
# surface kept its own copy.
#
# Every encoding argument in this module's docstring still holds, because none
# of them was ever carried by colour. The diverging pair is coral (raises)
# against deep green (lowers): see `theme.RAISES` for why that pair and not a
# prettier one.
COLOUR_RAISES = theme.RAISES
COLOUR_LOWERS = theme.LOWERS
COLOUR_SEQUENTIAL = theme.SEQUENTIAL
COLOUR_INK = theme.INK
COLOUR_MUTED = theme.SLATE
COLOUR_RULE = theme.HAIRLINE
COLOUR_GRID = theme.BORDER_LIGHT
COLOUR_SURFACE = theme.CANVAS

FONT = theme.FONT_SVG

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
        "left of the rule lowers risk, right raises it; sign is position, not colour</text>",
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
                f'fill="{COLOUR_MUTED}" font-style="italic">inert, no direction</text>'
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
        suffix = ", inert" if bar.inert else ""
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
            "ranking only, not calibrated; no observed outcome exists to calibrate "
            "against</text>",
            "</svg>",
        ]
    )


# ---------------------------------------------------------------------------
# Phase 22b -- three charts that answer questions the first two do not
# ---------------------------------------------------------------------------
#
# The contribution and probability charts answer "what did each construct do?".
# Three questions a reader still could not answer from the page were:
#
#   "how did those ten rows become 0.87?"      -> risk_waterfall
#   "how much of this is actually evidenced?"  -> evidence_coverage_chart
#   "is the underlying detector any good?"     -> benchmark_chart
#
# All three obey the same rules as the originals: sign by position, inertness by
# hatch + dash + word, no colour carrying meaning alone, legible in grayscale.


def risk_waterfall(
    bars: Sequence[ConstructBar],
    *,
    raw_score: float,
    index: float,
    width: int = CHART_WIDTH,
) -> str:
    """How the weighted sum was accumulated, then squashed into the index.

    The single most-asked question about this page is why ten contributions that
    sum to +1.9 produce an index of 0.87. The answer is the logistic squash, and
    a decomposition chart that stops before it leaves the reader to guess. So the
    final step is drawn explicitly: the running total, and then the squash as its
    own labelled step.

    Only contributing constructs get a step -- an inert construct adds exactly
    zero, so drawing it as a step of zero width would imply the sum is longer
    than it is. They are counted in the footnote instead, which is where "these
    were detected and added nothing" belongs.
    """
    steps = [b for b in bars if not b.inert and b.contribution != 0.0]
    steps.sort(key=lambda b: -abs(b.contribution))
    n_inert = sum(1 for b in bars if b.inert)
    rows = len(steps) + 1
    height = rows * ROW_HEIGHT + 74
    plot_width = width - LABEL_WIDTH - 70

    running = 0.0
    reach = max(abs(raw_score), 0.001)
    for bar in steps:
        running += bar.contribution
        reach = max(reach, abs(running))
    # Headroom for the "sum ... -> index ..." annotation, which is the widest
    # label on the chart and was clipped by the viewBox on the first render --
    # found by screenshotting, not by the tests, which never measure text.
    scale = (plot_width - 190) / (2 * reach)
    zero_x = LABEL_WIDTH + plot_width / 2

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="How the weighted sum was accumulated and then squashed">',
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "How the number was built</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        "each detected construct adds its weighted push to a running total, which is "
        "then squashed into 0 to 1</text>",
    ]

    top = 46
    running = 0.0
    for i, bar in enumerate(steps):
        y = top + i * ROW_HEIGHT
        mid = y + ROW_HEIGHT / 2
        start, running = running, running + bar.contribution
        x0, x1 = zero_x + start * scale, zero_x + running * scale
        raises = bar.contribution > 0
        colour = COLOUR_RAISES if raises else COLOUR_LOWERS
        out.append(
            f'<text x="8" y="{mid + 4:.1f}" {FONT} font-size="11" fill="{COLOUR_INK}">'
            f"{escape(_label(bar.construct, False))}</text>"
        )
        out.append(
            f'<rect x="{min(x0, x1):.1f}" y="{y + 5:.1f}" '
            f'width="{max(abs(x1 - x0), 1.0):.1f}" height="14" fill="{colour}" rx="3"/>'
        )
        # The connector makes it a waterfall rather than a stack of bars: each
        # step visibly starts where the previous one stopped.
        if i:
            out.append(
                f'<line x1="{x0:.1f}" y1="{y - 7:.1f}" x2="{x0:.1f}" y2="{y + 5:.1f}" '
                f'stroke="{COLOUR_RULE}" stroke-width="1" stroke-dasharray="2 2"/>'
            )
        anchor, label_x = ("start", max(x0, x1) + 6) if raises else ("end", min(x0, x1) - 6)
        out.append(
            f'<text x="{label_x:.1f}" y="{mid + 4:.1f}" {FONT} font-size="10" '
            f'fill="{COLOUR_INK}" text-anchor="{anchor}">{bar.contribution:+.3f}</text>'
        )

    y = top + len(steps) * ROW_HEIGHT
    mid = y + ROW_HEIGHT / 2
    total_x = zero_x + raw_score * scale
    out.append(
        f'<text x="8" y="{mid + 4:.1f}" {FONT} font-size="11" fill="{COLOUR_INK}" '
        f'font-weight="600">total, then squashed</text>'
    )
    out.append(
        f'<line x1="{min(zero_x, total_x):.1f}" y1="{mid:.1f}" '
        f'x2="{max(zero_x, total_x):.1f}" y2="{mid:.1f}" stroke="{COLOUR_INK}" '
        'stroke-width="2"/>'
    )
    out.append(
        f'<circle cx="{total_x:.1f}" cy="{mid:.1f}" r="4.5" fill="{COLOUR_SURFACE}" '
        f'stroke="{COLOUR_INK}" stroke-width="2"/>'
    )
    anchor, label_x = ("start", total_x + 9) if raw_score >= 0 else ("end", total_x - 9)
    label_x = min(max(label_x, 8.0), float(width - 8))
    out.append(
        f'<text x="{label_x:.1f}" y="{mid + 4:.1f}" {FONT} font-size="10" '
        f'fill="{COLOUR_INK}" text-anchor="{anchor}">sum {raw_score:+.3f} '
        f"&#8594; index {index:.2f}</text>"
    )
    out.append(
        f'<line x1="{zero_x:.1f}" y1="{top}" x2="{zero_x:.1f}" y2="{y + ROW_HEIGHT}" '
        f'stroke="{COLOUR_RULE}" stroke-width="1.5"/>'
    )
    out.append(
        f'<text x="8" y="{height - 10}" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        f"{n_inert} inert constructs are not drawn: each adds exactly zero to the sum"
        "</text>"
    )
    out.append("</svg>")
    return "".join(out)


def evidence_coverage_chart(
    *,
    evidenced: int,
    unevidenced: int,
    corpus_evidenced: int = 16,
    corpus_unevidenced: int = 104,
    width: int = CHART_WIDTH,
) -> str:
    """Evidenced vs unevidenced drivers, this text against the whole corpus.

    Two stacked bars on one shared 100% scale, because the question is a
    proportion and the comparison is the point: a reader who sees only this
    text's split cannot tell whether it is typical. It is.

    The unevidenced share is drawn hatched rather than in a second hue -- it is
    an absence of evidence, and the same argument as the inert marking applies:
    the marking has to survive grayscale.
    """
    hatch = "coverage-hatch"
    rows = (
        ("This text", evidenced, unevidenced),
        ("Whole corpus", corpus_evidenced, corpus_unevidenced),
    )
    bar_h, gap = 26, 44
    height = len(rows) * gap + 74
    plot_x = 116
    plot_w = width - plot_x - 16

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Share of drivers with supporting spans, this text against the corpus">',
        f'<defs><pattern id="{hatch}" width="6" height="6" patternTransform="rotate(45)" '
        'patternUnits="userSpaceOnUse">'
        f'<rect width="6" height="6" fill="{COLOUR_SURFACE}"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{COLOUR_MUTED}" stroke-width="2"/>'
        "</pattern></defs>",
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "How much of this is actually evidenced</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        "solid = the text contains words supporting the push; hatched = it does not"
        "</text>",
    ]

    top = 48
    for i, (label, yes, no) in enumerate(rows):
        y = top + i * gap
        total = max(yes + no, 1)
        w_yes = plot_w * yes / total
        w_no = plot_w * no / total
        out.append(
            f'<text x="8" y="{y + bar_h / 2 + 4:.1f}" {FONT} font-size="11" '
            f'fill="{COLOUR_INK}">{escape(label)}</text>'
        )
        if w_yes >= 1:
            out.append(
                f'<rect x="{plot_x}" y="{y}" width="{w_yes:.1f}" height="{bar_h}" '
                f'fill="{COLOUR_SEQUENTIAL}" rx="3"/>'
            )
        if w_no >= 1:
            out.append(
                f'<rect x="{plot_x + w_yes:.1f}" y="{y}" width="{w_no:.1f}" '
                f'height="{bar_h}" fill="url(#{hatch})" stroke="{COLOUR_MUTED}" '
                'stroke-width="1.5" stroke-dasharray="3 2" rx="3"/>'
            )
        share = 100.0 * no / total
        out.append(
            f'<text x="{plot_x + plot_w:.1f}" y="{y + bar_h + 14:.1f}" {FONT} '
            f'font-size="10" fill="{COLOUR_MUTED}" text-anchor="end">'
            f"{no} of {yes + no} pushes have no supporting words ({share:.0f}%)</text>"
        )
    out.append("</svg>")
    return "".join(out)


def benchmark_chart(benchmarks, *, width: int = CHART_WIDTH) -> str:
    """Macro-F1 with intervals: the word-list floor, the model, and the gap.

    Intervals are drawn, not summarised, because the floor's interval and the
    model's interval on the honest split do not overlap and that is the whole
    claim. A bare pair of numbers invites "0.588 vs 0.462" to be read as exact.

    The seen-patterns bar is marked as inflated in words on the row itself, for
    the same reason inert rows carry the word "inert": a reader who takes the
    tallest bar as the headline has been misled by the picture.
    """
    rows = list(benchmarks.rows)
    bar_h, gap = 22, 46
    height = len(rows) * gap + 76
    plot_x = 150
    plot_w = width - plot_x - 60

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Macro-F1 with intervals for the word-list floor and the model">',
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "How well the detector agrees with the planted labels</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        f"{escape(benchmarks.caption)}</text>",
    ]

    top = 48
    for i, row in enumerate(rows):
        y = top + i * gap
        mid = y + bar_h / 2
        out.append(
            f'<text x="8" y="{y + 10:.1f}" {FONT} font-size="11" fill="{COLOUR_INK}">'
            f"{escape(row.label)}</text>"
        )
        out.append(
            f'<text x="8" y="{y + 23:.1f}" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
            f"{escape(row.split)}</text>"
        )
        out.append(
            f'<rect x="{plot_x}" y="{y}" width="{row.point * plot_w:.1f}" '
            f'height="{bar_h}" fill="{COLOUR_SEQUENTIAL}" rx="3"/>'
        )
        low_x, high_x = plot_x + row.low * plot_w, plot_x + row.high * plot_w
        out.append(
            f'<line x1="{low_x:.1f}" y1="{mid:.1f}" x2="{high_x:.1f}" y2="{mid:.1f}" '
            f'stroke="{COLOUR_INK}" stroke-width="1.5"/>'
        )
        for x in (low_x, high_x):
            out.append(
                f'<line x1="{x:.1f}" y1="{y + 4:.1f}" x2="{x:.1f}" y2="{y + bar_h - 4:.1f}" '
                f'stroke="{COLOUR_INK}" stroke-width="1.5"/>'
            )
        out.append(
            f'<text x="{plot_x + plot_w + 6}" y="{mid + 4:.1f}" {FONT} font-size="11" '
            f'fill="{COLOUR_INK}">{row.point:.3f}</text>'
        )
        out.append(
            f'<text x="{plot_x}" y="{y + bar_h + 12:.1f}" {FONT} font-size="10" '
            f'fill="{COLOUR_MUTED}">{escape(row.note)}</text>'
        )

    out.append(
        f'<line x1="{plot_x}" y1="{top - 6}" x2="{plot_x}" y2="{top + len(rows) * gap - 12}" '
        f'stroke="{COLOUR_GRID}" stroke-width="1"/>'
    )
    out.append(
        f'<text x="8" y="{height - 10}" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        f"bars from 0; whiskers are the interval &#8212; the two unseen-pattern intervals "
        f"do not overlap (difference {benchmarks.delta:+.3f})</text>"
    )
    out.append("</svg>")
    return "".join(out)


def per_construct_chart(rows: Sequence, *, caption: str = "", width: int = CHART_WIDTH) -> str:
    """Per-construct agreement, worst first, with the word-list floor marked.

    Two encodings on one row, not two charts: the bar is the trained model and
    the caret is the floor for the same construct. They share a scale and a
    meaning, which is the one case where overlaying is right -- the question is
    "did the model beat its floor here?", and putting the answer in two charts
    makes the reader do the subtraction.

    A construct where the caret sits on or past the bar is called out in words on
    the row. That is the honest reading of it, and a chart that left it to the
    eye would be relying on a 2-pixel difference to carry a negative result.
    """
    height = len(rows) * ROW_HEIGHT + 62
    plot_x = LABEL_WIDTH
    plot_w = width - plot_x - 200

    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Per-construct agreement against the word-list floor">',
        f'<rect width="{width}" height="{height}" fill="{COLOUR_SURFACE}"/>',
        f'<text x="8" y="18" {FONT} font-size="12" fill="{COLOUR_INK}" font-weight="600">'
        "Agreement per construct, weakest first</text>",
        f'<text x="8" y="34" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
        "bar = trained model; caret = the word-list floor for the same construct"
        "</text>",
    ]

    top = 44
    for i, row in enumerate(rows):
        y = top + i * ROW_HEIGHT
        mid = y + ROW_HEIGHT / 2
        out.append(
            f'<line x1="{plot_x}" y1="{y + 12:.1f}" x2="{plot_x + plot_w}" '
            f'y2="{y + 12:.1f}" stroke="{COLOUR_GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="8" y="{mid + 4:.1f}" {FONT} font-size="11" fill="{COLOUR_INK}">'
            f"{escape(row.construct.replace('_', ' '))}</text>"
        )
        length = max(row.f1, 0.0) * plot_w
        out.append(
            f'<rect x="{plot_x}" y="{y + 5:.1f}" width="{max(length, 1.0):.1f}" '
            f'height="14" fill="{COLOUR_SEQUENTIAL}" rx="3"/>'
        )
        floor_x = plot_x + max(row.floor_f1, 0.0) * plot_w
        out.append(
            f'<path d="M {floor_x:.1f} {y + 2:.1f} l 4 6 l -8 0 z" fill="{COLOUR_INK}"/>'
            f'<line x1="{floor_x:.1f}" y1="{y + 4:.1f}" x2="{floor_x:.1f}" '
            f'y2="{y + 20:.1f}" stroke="{COLOUR_INK}" stroke-width="1.5"/>'
        )
        suffix = "" if row.beats_floor else ", no better than the floor"
        out.append(
            f'<text x="{plot_x + plot_w + 6}" y="{mid + 4:.1f}" {FONT} font-size="10" '
            f'fill="{COLOUR_INK}">{row.f1:.2f}{suffix}</text>'
        )
    if caption:
        out.append(
            f'<text x="8" y="{height - 8}" {FONT} font-size="10" fill="{COLOUR_MUTED}">'
            f"{escape(caption[:120])}</text>"
        )
    out.append("</svg>")
    return "".join(out)
