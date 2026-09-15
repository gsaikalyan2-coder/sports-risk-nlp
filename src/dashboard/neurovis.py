"""Renderers for the cognitive layer's three panels. Skeleton at Step 0.

What this module is
-------------------
The same thing `motion.py` is: self-contained HTML documents handed to
`st.components.v1.html`, because Streamlit has no hook for a motion system and
an iframe inherits nothing from the host page. Everything `motion.py`'s docstring
says about honesty not relaxing inside an iframe applies here unchanged, and two
further rules apply only here.

**The first is that a brain graphic is the most over-read object in sports
technology.** A reader who glances at a coloured network does not come away
thinking "that is a hypothesis drawn from a text model"; they come away thinking
they have seen a scan. So `assert_no_activation_vocabulary()` runs over every
rendered surface this module produces, and the atlas caption states
"hypothesised association, not imaging" as text rather than as a tooltip -- a
tooltip is not in a screenshot, and a screenshot is what ends up in a slide.

**The second is that a simulated trace is indistinguishable from a measured
one.** Every panel that renders a `BiosignalWindow` renders `window.stamp`
before the trace, in document order, for the same reason
`tests/test_dashboard_pages.py` requires the provenance stamp to appear before
any `st.expander`: a caveat below the fold is in the DOM and not on the screen.

Design language
---------------
Colour comes entirely from `theme.palette(mode)` and the surface tables below;
this module introduces no hex value of its own, so `DESIGNcohere.md` remains the
dashboard's single specification and the leak test in
`tests/test_dashboard_pages.py` stays true. What it *does* borrow from Material
Design 3 is shape and motion: the MD3 corner scale (mapped onto the existing
theme radii, not added alongside them) and MD3's emphasized easing curves, which
are a better fit than the panel's existing ease for the one thing this layer
animates that `motion.py` does not -- a ring that has to read as responding to a
signal rather than as playing an intro.

At Step 0 this module carries the shared parts only. `atlas_panel` arrives with
V1, `load_panel` with V3, `neurofeedback_panel` with V5.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from html import escape

from src.dashboard import copy as plain
from src.dashboard import motion, theme
from src.dashboard.view import assert_no_forbidden_language

#: Vocabulary that may not appear on any surface this module renders.
#:
#: Matched on word boundaries, which is the OPPOSITE choice from
#: `view.assert_no_forbidden_language` -- and the difference is deliberate, so
#: nobody "fixes" one to match the other. There, a loose substring match is the
#: safe direction: "detection accuracy" must be caught, and a word-boundary rule
#: would let it through. Here, the loose direction is the unsafe one, because
#: "activity" is a substring of nothing dangerous but a whole word inside the
#: perfectly ordinary phrase "physical activity", and a rule that fires on
#: honest copy gets relaxed rather than obeyed.
#:
#: "fMRI" is the exception and is matched as a plain substring: there is no
#: innocent context for it anywhere on these surfaces.
ACTIVATION_WORDS: tuple[str, ...] = ("activity", "activation", "activated", "measured")
ACTIVATION_SUBSTRINGS: tuple[str, ...] = ("fmri",)

#: Stated as text under every atlas figure, never as a tooltip or a title
#: attribute. `.claude.md` §11.2 rule 3 and the Phase 26 gate both turn on the
#: literal wording, so it lives here once and is asserted by the tests.
ATLAS_CAVEAT_TEXT = "hypothesised association, not imaging"


class ActivationVocabulary(ValueError):
    """Raised when a rendered surface reads as a claim about measured brain state."""


def assert_no_activation_vocabulary(text: str) -> None:
    """Refuse a surface that describes a hypothesis in the vocabulary of a scan.

    This is not about politeness of wording. The atlas is a re-expression of
    `ConstructBar.probability`, which came from a lexicon or a transformer
    reading synthetic text; there is no imaging anywhere in this repository and
    there is no person. A node labelled "activation" is a claim that no part of
    this project can support, and unlike most such claims it is one a reader
    forms in a fraction of a second from a picture, before reading any caption.
    """
    low = text.lower()
    for word in ACTIVATION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", low):
            raise ActivationVocabulary(
                f"{word!r} may not appear on a cognitive-layer surface. The atlas is a "
                "hypothesised association drawn from text, not imaging; see this "
                "module's docstring and .claude.md §11.2 rule 3."
            )
    for fragment in ACTIVATION_SUBSTRINGS:
        if fragment in low:
            raise ActivationVocabulary(
                f"{fragment!r} may not appear on a cognitive-layer surface. There is no "
                "imaging anywhere in this repository."
            )


#: Inlined binary payloads, stripped before the vocabulary screens run.
#:
#: An mp3 encoded as base64 is forty kilobytes of arbitrary letters, and
#: arbitrary letters contain words. The first narrated clip built in this
#: repository produced a payload containing the four characters "fmri" and the
#: activation screen refused to render the panel -- correctly, by its own rule,
#: and uselessly, because no reader will ever see those characters.
#:
#: The fix is NOT to loosen the screen. A guard that fires on binary noise gets
#: switched off by the next person who meets it, and then it is not protecting
#: the captions either. The fix is to screen what a reader can actually read:
#: the payload is removed first, the surface is screened whole, and anything
#: outside a data: URI is checked exactly as strictly as before.
_DATA_URI = re.compile(r"data:[a-z]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=]+")


def readable_surface(html: str) -> str:
    """The document with inlined binary payloads removed. See `_DATA_URI`."""
    return _DATA_URI.sub("data:[inlined payload]", html)


def screened(html: str) -> str:
    """Both screens, over the finished document, at the point it is produced.

    `view.render_text()` cannot see a string this module writes -- it is written
    here, not carried through the view -- which is exactly why `motion.py` screens
    at the same point. The activation screen is layered on top for this package.

    Screened over `readable_surface(html)` rather than `html`, so a base64 audio
    payload cannot trip a rule about words. The returned document is the original,
    payload and all -- the stripping is for the check, never for the output.
    """
    surface_text = readable_surface(html)
    assert_no_forbidden_language(surface_text)
    assert_no_activation_vocabulary(surface_text)
    return html


def surface(mode: str) -> dict[str, str]:
    """The token table for one appearance mode.

    Reuses `motion._SURFACES` rather than defining a parallel one. A second table
    is a second thing to forget to fill in for a new mode, and a half-filled mode
    is how a dark page ends up with dark text on dark -- a failure only the
    running browser can see, which `tests/test_dashboard_pages.py` records as
    already having happened once here.
    """
    return dict(motion._SURFACES.get(mode, motion._SURFACES[motion.DEFAULT_MODE]))


# ---------------------------------------------------------------------------
# Material Design 3 shape and motion, expressed in this project's own tokens
# ---------------------------------------------------------------------------

#: MD3 corner scale, mapped onto the radii `theme.py` already publishes rather
#: than added beside them. The mapping is not exact -- MD3's medium is 12px and
#: this system's nearest step is 16px -- and it is deliberately resolved towards
#: the existing token, because a panel that is 4px rounder than the card it sits
#: in is the sort of difference a reader registers without being able to name.
SHAPE: dict[str, str] = {
    "extra-small": theme.RADIUS_XS,
    "small": theme.RADIUS_SM,
    "medium": theme.RADIUS_MD,
    "large": theme.RADIUS_LG,
    "extra-large": theme.RADIUS_XL,
    "full": "9999px",
}

#: MD3 easing. `EMPHASIZED` is for a thing that starts and ends on screen (the
#: ring settling on a new radius), `DECELERATE` for something arriving,
#: `ACCELERATE` for something leaving. The panel in `motion.py` uses its own
#: [0.22, 1, 0.36, 1] for bars growing from zero and keeps it; these are for the
#: one behaviour that package does not have, which is a mark that responds
#: repeatedly to a changing value rather than animating once on load.
EASING: dict[str, str] = {
    "emphasized": "cubic-bezier(0.2, 0, 0, 1)",
    "emphasized-decelerate": "cubic-bezier(0.05, 0.7, 0.1, 1)",
    "emphasized-accelerate": "cubic-bezier(0.3, 0, 0.8, 0.15)",
    "standard": "cubic-bezier(0.2, 0, 0, 1)",
}

#: Durations in milliseconds, paired with the curves above per the MD3 table.
DURATION_MS: dict[str, int] = {
    "emphasized": 500,
    "emphasized-decelerate": 400,
    "emphasized-accelerate": 200,
    "standard": 300,
}


def stamp_row(stamp: str) -> str:
    """The provenance line every simulated panel opens with.

    A function rather than a template fragment so there is exactly one way to
    render it and the ordering test has one string to look for. It is returned
    already escaped-by-construction: the only input is a stamp this package
    generated.
    """
    if not stamp.strip():
        raise ValueError(
            "a panel was asked to render an empty provenance stamp. A simulated "
            "trace with no statement of what it is reads as a recording of a person."
        )
    return f'<p class="srn-stamp">{stamp}</p>'


STAMP_CSS = (
    ".srn-stamp{font-family:var(--srn-mono);font-size:14px;letter-spacing:.28px;"
    "line-height:1.4;color:var(--slate);margin:0 0 16px;padding:8px 12px;"
    f"border:1px solid var(--line);border-radius:{SHAPE['extra-small']}}}"
)


# ===========================================================================
# V1, the construct → brain network atlas
# ===========================================================================

#: Where each region sits, as a fraction of the figure box. Presentation, so it
#: lives here and not in `config/brain_atlas.yaml` -- a coordinate sitting beside
#: a citation invites the next reader to think the coordinate is cited too.
#:
#: The arrangement follows the left-lateral schematic in
#: `reports/cognitive_concepts.html`, which is the approved visual reference.
#: It is a cartoon: frontal regions to the left, parietal to the right, limbic
#: low and central. It is not a tracing of any atlas and is not to scale, which
#: is the point -- a figure that looked like a real rendering would be read as one.
REGION_POINTS: dict[str, tuple[float, float]] = {
    "dlpfc": (0.285, 0.417),
    "vmpfc": (0.278, 0.617),
    "dorsal_acc": (0.458, 0.333),
    "insula": (0.437, 0.694),
    "striatum": (0.517, 0.542),
    "amygdala": (0.403, 0.811),
    "posterior_parietal": (0.694, 0.411),
    "posterior_cingulate": (0.664, 0.606),
}

FIGURE_W = 720
#: 360 rather than the concept board's 420. The board reserved the bottom third
#: for a cerebellum this panel does not draw (see below), and an empty third
#: under a figure reads as a section that failed to load.
FIGURE_H = 360

#: Node radius in pixels as a function of detection strength:
#:
#:     radius = NODE_R_MIN + NODE_R_SPAN * probability
#:
#: Written as an affine function of one number the view already carries, with no
#: second term, so `probability` is recoverable from the rendered radius exactly.
#: `tests/test_neurovis.py` inverts it and asserts the result matches
#: `ConstructBar.probability` to three decimal places -- which is the testable
#: form of "the panel introduces no number the view does not carry". A radius
#: that also depended on, say, the contribution would make the figure assert
#: something the bars do not.
NODE_R_MIN = 7.0
NODE_R_SPAN = 13.0

#: How far apart two constructs drawn at the same region are fanned. Two rows
#: share `dorsal_acc` and two share nothing else, so without this the burnout
#: node would sit exactly under the cognitive-anxiety node and one of them would
#: be invisible -- a construct silently missing from a figure nobody counts.
#: Fanned horizontally rather than vertically (the fan starts at 0 rad, not at
#: -pi/2), because two nodes stacked vertically put the upper one's caption on
#: top of the lower one's circle. Visible only in a rendered figure.
FAN_PX = 70.0


def node_radius(probability: float) -> float:
    return NODE_R_MIN + NODE_R_SPAN * float(probability)


def probability_from_radius(radius: float) -> float:
    """The inverse. Exists so the test inverts the shipped function, not a copy."""
    return (float(radius) - NODE_R_MIN) / NODE_R_SPAN


def _node_points(atlas, constructs: Sequence[str]) -> dict[str, tuple[float, float]]:
    """Lay the drawn constructs out, fanning any that share a region."""
    by_region: dict[str, list[str]] = {}
    for construct in constructs:
        by_region.setdefault(atlas.row(construct).primary_region, []).append(construct)

    points: dict[str, tuple[float, float]] = {}
    for region, members in by_region.items():
        fx, fy = REGION_POINTS[region]
        cx, cy = fx * FIGURE_W, fy * FIGURE_H
        if len(members) == 1:
            points[members[0]] = (cx, cy)
            continue
        for i, construct in enumerate(sorted(members)):
            angle = 2.0 * math.pi * i / len(members)
            points[construct] = (cx + FAN_PX * math.cos(angle), cy + FAN_PX * math.sin(angle))
    return points


#: The cartoon outline. One path, no image, no font, no external reference, so
#: the figure is identical with the network cut -- the defect `motion.py` records
#: having shipped once, where a blocked CDN left the card empty and every unit
#: test stayed green.
_CORTEX_PATH = (
    # Outer silhouette of a left hemisphere seen from the side, facing left.
    # The lower-left "beak" is the temporal pole and the bottom edge is the
    # inferior temporal border -- without them the shape is an oval, which is
    # what the first two renderings of this panel actually produced.
    # Proportioned to a real lateral view -- about 470 wide by 290 tall, which
    # is roughly 1 : 0.6. The first attempts were 1 : 0.5 and read as an oval no
    # matter what was drawn inside them.
    "M132 210 C132 118 214 52 320 46 C424 40 520 78 566 140 "
    "C600 186 602 232 578 256 C560 274 534 278 512 270 "
    "C502 306 458 328 404 330 C344 332 286 318 244 296 "
    "C214 280 196 262 194 244 C176 240 146 230 132 210 Z"
)

#: The Sylvian fissure, which is what separates temporal from frontal and
#: parietal and is the single line that makes a silhouette read as a brain. The
#: central sulcus is the second. Both are open paths in the hairline colour:
#: they carry no node, no value and no claim, and exist only to orient a reader.
_SYLVIAN_PATH = "M190 236 C268 266 358 272 440 262 C470 258 488 250 500 240"
_CENTRAL_SULCUS_PATH = "M352 50 C372 100 382 152 398 206"

#: Drawn BEFORE the cortex so the cortex fill tucks them behind it, which is how
#: they sit in a lateral view. Drawn after, they read as two detached blobs --
#: the defect this panel shipped twice before the outline was rebuilt.
_CEREBELLUM_PATH = (
    "M506 254 C552 244 588 264 588 292 C588 318 552 330 520 322 C494 314 488 274 506 254 Z"
)
_BRAINSTEM_PATH = "M452 300 C462 328 464 348 458 360 L486 360 C492 340 488 314 480 292 Z"


def _atlas_svg(view, atlas, t: dict[str, str]) -> str:
    """The figure itself. Pure SVG: no script, no font file, no raster."""
    bars = {bar.construct: bar for bar in view.bars}
    drawn = [row.construct for row in atlas.mapped if row.construct in bars]
    points = _node_points(atlas, drawn)

    parts: list[str] = [
        f'<svg viewBox="0 0 {FIGURE_W} {FIGURE_H}" width="100%" '
        f'role="img" aria-label="{escape(plain.ATLAS_TITLE)}. {escape(plain.ATLAS_CAVEAT)}." '
        'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{escape(plain.ATLAS_CAVEAT)}</title>",
        # Hatch for inert nodes -- the id is namespaced because charts.py records
        # a defect where two figures on one page shared a pattern id and the
        # second one silently took the first one's fill.
        '<defs><pattern id="srn-atlas-hatch" width="6" height="6" '
        'patternTransform="rotate(45)" patternUnits="userSpaceOnUse">'
        f'<rect width="6" height="6" fill="{t["surface"]}"/>'
        f'<line x1="0" y1="0" x2="0" y2="6" stroke="{t["stone"]}" stroke-width="3"/>'
        "</pattern></defs>",
        f'<path d="{_CEREBELLUM_PATH}" fill="{t["surface"]}" stroke="{t["line"]}" stroke-width="1.6"/>',
        f'<path d="{_BRAINSTEM_PATH}" fill="{t["surface"]}" stroke="{t["line"]}" stroke-width="1.6"/>',
        f'<path d="{_CORTEX_PATH}" fill="{t["surface"]}" stroke="{t["line"]}" stroke-width="1.6"/>',
        f'<path d="{_SYLVIAN_PATH}" fill="none" stroke="{t["line"]}" stroke-width="1.3"/>',
        f'<path d="{_CENTRAL_SULCUS_PATH}" fill="none" stroke="{t["line"]}" stroke-width="1.3"/>',
    ]

    for a, b, _network in atlas.edges():
        if a not in points or b not in points:
            continue
        ax, ay = points[a]
        bx, by = points[b]
        weight = 1.0 + 3.2 * min(bars[a].probability, bars[b].probability)
        parts.append(
            f'<path d="M{ax:.1f} {ay:.1f} Q{(ax + bx) / 2:.1f} {(ay + by) / 2 - 18:.1f} '
            f'{bx:.1f} {by:.1f}" fill="none" stroke="{t["slate"]}" stroke-opacity="0.38" '
            f'stroke-width="{weight:.2f}"/>'
        )

    for construct in drawn:
        bar = bars[construct]
        x, y = points[construct]
        radius = node_radius(bar.probability)
        # A construct the text did not trigger still gets a node -- the node is
        # the construct's *place*, and removing it would make the figure change
        # shape between examples, which reads as the anatomy moving. It is drawn
        # faint so it does not read as a finding; the table beside it prints
        # "0.000 detected" in words, which is the channel that survives a
        # greyscale print.
        opacity = "1" if bar.detected else "0.38"
        if bar.inert:
            # Three channels, as charts.py requires: hatched fill, dashed outline,
            # and the literal word -- which is rendered in the row beside the
            # figure, because a word inside a 20px circle is not a channel.
            parts.append(
                f'<circle class="nd" data-c="{construct}" cx="{x:.1f}" cy="{y:.1f}" '
                f'r="{radius:.6f}" fill="url(#srn-atlas-hatch)" opacity="{opacity}" '
                f'stroke="{t["slate"]}" stroke-width="1.4" stroke-dasharray="4 3"/>'
            )
        else:
            colour = t["raise"] if bar.contribution >= 0 else t["lower"]
            parts.append(
                f'<circle class="nd" data-c="{construct}" cx="{x:.1f}" cy="{y:.1f}" '
                f'r="{radius:.6f}" fill="{colour}" fill-opacity="0.88" '
                f'opacity="{opacity}" stroke="{colour}" stroke-width="1"/>'
            )
        label = plain.CONSTRUCTS.get(construct, (construct.replace("_", " "), "", ""))[0]
        # Caption below a node in the upper half, above one in the lower half.
        # A single fixed side put three captions straight through the circle of
        # the node beneath them; the rule costs one line and the alternative was
        # per-node nudges that go stale the first time a region moves.
        upper = y < FIGURE_H * 0.5
        label_y = y + radius + 15 if upper else y - radius - 8
        parts.append(
            # paint-order puts the halo behind the glyphs so a caption stays
            # readable where it crosses the cortex outline or an edge. A halo
            # painted after the fill would erase the letters.
            f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle" '
            f'fill="{t["slate"]}" font-size="12" paint-order="stroke" '
            f'stroke="{t["surface"]}" stroke-width="3" stroke-linejoin="round"'
            f">{escape(label)}</text>"
        )

    parts.append("</svg>")
    return "".join(parts)


def _atlas_rows_html(view, atlas, t: dict[str, str]) -> str:
    """One row per construct: the two numbers, the anchor, and what backs the dot.

    Under the figure and always visible. `.claude.md` §11.4 offers a hover for
    this; a hover is not in a screenshot, and a screenshot is what reaches a
    slide. The same argument `tests/test_dashboard_pages.py` already makes about
    a provenance stamp inside a collapsed expander.
    """
    items: list[str] = []
    for row in atlas.rows:
        bar = next((b for b in view.bars if b.construct == row.construct), None)
        name = plain.CONSTRUCTS.get(row.construct, (row.construct.replace("_", " "), "", ""))[0]
        if row.unmapped:
            place = "<em>unmapped</em>"
            state = "is-unmapped"
        else:
            region = atlas.regions[row.primary_region]
            place = (
                f"{escape(region.plain_name)} <span class='anat'>{escape(region.anatomical)}</span>"
            )
            state = "is-inert" if (bar and bar.inert) else ""
        numbers = (
            f"{bar.probability:.3f} detected · "
            + ("counted as zero" if bar.inert else f"{bar.contribution:+.3f} on the index")
            if bar
            else "not in this view"
        )
        items.append(
            f'<tr class="{state}" data-row="{row.construct}">'
            f'<th scope="row">{escape(name)}</th>'
            f"<td>{place}</td>"
            f'<td class="num" data-num="{row.construct}">{escape(numbers)}</td>'
            f'<td class="anchor">{escape(row.instrument_anchor)}</td>'
            f'<td class="ev">{escape(row.evidence_short)}</td></tr>'
        )
    return "".join(items)


def atlas_height(view) -> int:
    """Iframe height in pixels. An iframe does not grow to its content.

    The constants are measured, not guessed: the panel was rendered headless at
    900px wide and the card's bounding box read back, then the per-row terms
    fitted to it with headroom. The first version of this function was guessed
    and was short by a thousand pixels, which in Streamlit means the bottom
    third of the panel -- the evidence table and the unmapped list, i.e. exactly
    the honesty material -- is simply not on the page. `tests/test_neurovis.py`
    asserts the declared height clears a floor derived the same way, so a future
    edit that adds a section and forgets this function fails rather than
    silently clipping the caveats.
    """
    from src.dashboard.atlas_map import load_atlas

    return 660 + FIGURE_H + 80 * len(view.bars) + 165 * len(load_atlas().unmapped)


def atlas_panel(view, *, mode: str = motion.DEFAULT_MODE, frames: Sequence = ()) -> str:
    """The whole atlas as one self-contained HTML document, in one surface mode.

    Reads `view.bars` and nothing else. Every colour comes from the mode's token
    table, so the panel introduces no hex value and `DESIGNcohere.md` stays the
    dashboard's single specification.

    `frames` makes the figure playable: pass the other committed views and the
    panel gets Prev / Play / Next controls that move every node between them.
    Nothing is interpolated into existence -- each frame is one real
    `DashboardView` over one committed example, and the tween only fills the gap
    between two states the fixture already contains. With no frames, or with
    JavaScript off, the panel is exactly the static figure it was: the server
    paints frame 0 into the SVG and the script only ever changes it.
    """
    from src.dashboard.atlas_map import load_atlas

    atlas = load_atlas()
    t = surface(mode)
    legend = "".join(
        f'<span class="lg"><i class="sw sw-{key}"></i>{escape(text)}</span>'
        for text, key in plain.ATLAS_LEGEND
    )
    # The full evidence sentences, once each, under the table. The cells carry
    # the short form; this is where the long one lives so that a reader who
    # looks up from the figure meets it without hunting for a tooltip.
    states = {row.network_evidence: row.evidence_note for row in atlas.mapped}
    evidence_notes = "".join(f"<li>{escape(note)}</li>" for note in sorted(states.values()))
    unmapped = "".join(
        f"<li><b>{escape(plain.CONSTRUCTS.get(row.construct, (row.construct, '', ''))[0])}</b>"
        f", {escape(' '.join(row.rationale.split()))}</li>"
        for row in atlas.unmapped
    )
    # Deduplicated by record id, not by object identity. The page builds `view`
    # and the frame list in two separate calls, so the current example arrives
    # twice as two equal-but-distinct objects and the panel offered "1 of 4" over
    # three examples. Visible only in the running app.
    timeline = [view]
    seen = {view.card.record_id}
    for frame in frames:
        if frame.card.record_id not in seen:
            seen.add(frame.card.record_id)
            timeline.append(frame)
    payload = json.dumps(
        {
            "frames": [
                {
                    "label": f.card.record_id,
                    "text": f.card.text,
                    "rows": {
                        bar.construct: {
                            "p": round(bar.probability, 4),
                            "c": round(bar.contribution, 4),
                            "inert": bar.inert,
                            "detected": bar.detected,
                        }
                        for bar in f.bars
                    },
                }
                for f in timeline
            ],
            "rMin": NODE_R_MIN,
            "rSpan": NODE_R_SPAN,
            "raise": t["raise"],
            "lower": t["lower"],
            "ease": EASING["emphasized"],
            "ms": DURATION_MS["emphasized"],
        }
    )
    controls = (
        "<div class='sim'>"
        "<button type='button' id='prev' aria-label='Previous example'>&#9664;</button>"
        "<button type='button' id='play' class='primary'>Play</button>"
        "<button type='button' id='next' aria-label='Next example'>&#9654;</button>"
        "<span class='simlab' id='simlab'></span>"
        "</div>"
        "<blockquote id='simtext'></blockquote>"
    )

    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        + _atlas_style(t)
        + "</head><body><div class='card'>"
        # The caveat is the first element in the document, before the figure,
        # for the same reason the provenance stamp precedes any expander.
        + f"<p class='srn-stamp'>{escape(plain.ATLAS_CAVEAT)}</p>"
        + f"<h2>{escape(plain.ATLAS_TITLE)}</h2>"
        + f"<p class='sub'>{escape(plain.ATLAS_PLAIN)}</p>"
        + controls
        + f"<div class='fig'>{_atlas_svg(view, atlas, t)}</div>"
        + f"<p class='cap'>{escape(plain.ATLAS_CAVEAT)}</p>"
        + f"<div class='legend'>{legend}</div>"
        + f"<p class='sub'>{escape(plain.ATLAS_HOW_TO_READ)}</p>"
        + f"<h3>{escape(plain.ATLAS_EVIDENCE_HEADING)}</h3>"
        + "<div class='scroll'><table><thead><tr>"
        + "<th>Signal</th><th>Where it is drawn</th><th>From the text</th>"
        + "<th>Questionnaire</th><th>What backs the dot</th>"
        + "</tr></thead><tbody>"
        + _atlas_rows_html(view, atlas, t)
        + "</tbody></table></div>"
        + f"<ul class='un'>{evidence_notes}</ul>"
        + f"<p class='sub'>{escape(plain.ATLAS_ANCHOR_NOTE)}</p>"
        + f"<h3>{escape(plain.ATLAS_UNMAPPED_PLAIN)}</h3>"
        + f"<ul class='un'>{unmapped}</ul>"
        + f"<p class='sub'>{escape(plain.ATLAS_WHAT_IT_IS_NOT)}</p>"
        + "</div>"
        + _SIMULATOR_SCRIPT.replace("__PAYLOAD__", payload)
        + "</body></html>"
    )
    return screened(document)


def _atlas_style(t: dict[str, str]) -> str:
    """The panel's stylesheet for one mode.

    Emitted inside a `<style>` element and never as a bare string. `motion.py`
    records the defect where a stylesheet reached the page as visible text; the
    concatenation order is the only thing that prevents it, so it is done in one
    place rather than at each call site.
    """
    return (
        t["fonts"]
        + f"""
<style>
  :root{{
    --ink:{t["ink"]};--muted:{t["muted"]};--slate:{t["slate"]};--line:{t["line"]};
    --card-border:{t["card-border"]};--surface:{t["surface"]};--stone:{t["stone"]};
    --raise:{t["raise"]};--lower:{t["lower"]};--accent:{t["accent"]};
    --srn-mono:{t["mono"]};
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:transparent;color:var(--ink);font-family:{t["font"]};
    font-size:16px;line-height:1.5}}
  .card{{background:var(--surface);border:1px solid var(--card-border);
    border-radius:{SHAPE["large"]};padding:32px}}
  {STAMP_CSS}
  h2{{font-family:{t["display"]};font-size:32px;font-weight:400;line-height:1.2;
    letter-spacing:-.32px;margin:0 0 8px}}
  h3{{font-size:18px;font-weight:400;margin:32px 0 8px;color:var(--ink)}}
  .sub{{color:var(--muted);margin:8px 0 24px;max-width:68ch}}
  .fig{{background:var(--surface);border:1px solid var(--line);
    border-radius:{SHAPE["medium"]};padding:8px}}
  .cap{{font-family:var(--srn-mono);font-size:14px;letter-spacing:.28px;
    text-transform:uppercase;color:var(--slate);margin:12px 0 0;text-align:center}}
  .legend{{display:flex;gap:24px;flex-wrap:wrap;margin:24px 0 0;font-size:14px;
    color:var(--slate)}}
  .lg{{display:inline-flex;align-items:center;gap:8px}}
  .sw{{width:11px;height:11px;border-radius:{SHAPE["full"]};display:inline-block}}
  .sw-raise{{background:var(--raise)}}
  .sw-lower{{background:var(--lower)}}
  .sw-inert{{border:1.4px dashed var(--slate)}}
  .sw-unmapped{{border:1.4px solid var(--line);background:var(--stone)}}
  .scroll{{overflow-x:auto}}
  table{{border-collapse:collapse;width:100%;font-size:14px}}
  th,td{{text-align:left;padding:12px 12px 12px 0;border-top:1px solid var(--line);
    vertical-align:top}}
  thead th{{border-top:0;font-family:var(--srn-mono);font-weight:400;
    letter-spacing:.28px;text-transform:uppercase;color:var(--slate);font-size:12px}}
  tbody th{{font-weight:400;color:var(--ink)}}
  .anat{{color:var(--slate);font-style:italic}}
  .num{{font-family:var(--srn-mono);white-space:nowrap;color:var(--muted)}}
  .anchor{{font-family:var(--srn-mono);color:var(--slate)}}
  .ev{{color:var(--muted);max-width:34ch}}
  tr.is-unmapped th,tr.is-unmapped td{{color:var(--slate)}}
  tr.is-inert th{{color:var(--slate)}}
  .sim{{display:flex;align-items:center;gap:8px;margin:0 0 12px}}
  .sim button{{font-family:{t["font"]};font-size:14px;font-weight:500;line-height:1.71;
    padding:6px 16px;border:1px solid var(--line);background:var(--surface);
    color:var(--ink);border-radius:{SHAPE["full"]};cursor:pointer;
    transition:background {DURATION_MS["standard"]}ms {EASING["standard"]}}}
  .sim button:hover{{background:var(--stone)}}
  .sim button.primary{{background:var(--ink);color:var(--surface);border-color:var(--ink);
    min-width:82px}}
  .simlab{{font-family:var(--srn-mono);font-size:12px;letter-spacing:.28px;
    text-transform:uppercase;color:var(--slate);margin-left:8px}}
  blockquote{{margin:0 0 16px;padding:12px 16px;border-left:2px solid var(--accent);
    background:var(--stone);border-radius:0 {SHAPE["extra-small"]} {SHAPE["extra-small"]} 0;
    color:var(--muted);font-size:15px;max-width:72ch}}
  circle.nd{{transition:none}}
  .tlab{{font-family:var(--srn-mono);font-size:12px;letter-spacing:.28px;
    text-transform:uppercase;color:var(--slate);margin:8px 0 2px}}
  .big{{font-family:{t["display"]};font-size:40px;font-weight:400;line-height:1;
    letter-spacing:-.4px;color:var(--ink);margin-left:8px}}
  #bl{{color:var(--slate)}}
  td.mn{{color:var(--muted)}}
  audio{{width:100%;max-width:520px;margin:0 0 12px;display:block}}
  .spoken{{font-size:17px;line-height:1.9;margin:0 0 20px;max-width:70ch;color:var(--muted)}}
  .spoken .wd{{padding:2px 1px;border-radius:3px;transition:background 120ms linear,
    color 120ms linear}}
  .spoken .wd.on{{background:var(--accent);color:var(--surface)}}
  .ph{{opacity:.55}}
  .stats .wu{{display:block;font-size:12px;color:var(--slate)}}
  .danger{{color:{t["accent"]};border:1px solid {t["accent"]};border-radius:{SHAPE["extra-small"]};
    padding:10px 14px;margin:0 0 16px;font-size:14px;line-height:1.5;max-width:72ch}}
  .ringwrap{{display:flex;justify-content:center;padding:16px}}
  .stats{{display:flex;gap:48px;flex-wrap:wrap;margin:16px 0 24px}}
  .stats .wl{{display:block;font-family:var(--srn-mono);font-size:12px;letter-spacing:.28px;
    text-transform:uppercase;color:var(--slate)}}
  .stats .big{{margin-left:0}}
  #ring{{transition:r 240ms {EASING["emphasized"]}, stroke 240ms {EASING["emphasized"]}}}
  ul.un{{margin:0;padding-left:20px;color:var(--muted);max-width:68ch}}
  ul.un li{{margin-bottom:8px}}
  @media (max-width:520px){{.card{{padding:20px}}.legend{{gap:12px}}}}
</style>
"""
    )


#: The simulator. A *classic* script with no imports and no network reference,
#: for the reason `motion.py` records at length: the first version of that panel
#: used a module from a CDN, and with the network cut the card rendered empty
#: while every unit test stayed green. Here the server has already painted frame
#: zero into the SVG, so a script that never runs costs the Play button and
#: nothing else.
#:
#: It invents no number. Each frame is one committed `DashboardView`; the tween
#: only fills the gap between two states the fixture already contains, and it
#: always lands exactly on the next frame's own values.
_SIMULATOR_SCRIPT = """
<script>
(function(){
  var D = __PAYLOAD__;
  var i = 0, timer = null, from = null;
  var nodes = {}, cells = {}, rows = {};
  document.querySelectorAll('circle.nd').forEach(function(el){ nodes[el.dataset.c] = el; });
  document.querySelectorAll('[data-num]').forEach(function(el){ cells[el.dataset.num] = el; });
  document.querySelectorAll('[data-row]').forEach(function(el){ rows[el.dataset.row] = el; });

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var lab = document.getElementById('simlab');
  var quote = document.getElementById('simtext');

  function numbers(r){
    return r.p.toFixed(3) + ' detected \\u00b7 ' +
      (r.inert ? 'counted as zero' : (r.c >= 0 ? '+' : '') + r.c.toFixed(3) + ' on the index');
  }
  function paint(f, t){
    Object.keys(nodes).forEach(function(k){
      var a = (from && from.rows[k]) || f.rows[k], b = f.rows[k];
      if(!b) return;
      var p = a.p + (b.p - a.p) * t;
      var el = nodes[k];
      el.setAttribute('r', (D.rMin + D.rSpan * p).toFixed(6));
      el.setAttribute('opacity', b.detected ? 1 : 0.38);
      if(!b.inert){
        var col = b.c >= 0 ? D['raise'] : D['lower'];
        el.setAttribute('fill', col); el.setAttribute('stroke', col);
      }
      if(t === 1 && cells[k]) cells[k].textContent = numbers(b);
    });
  }
  function show(n){
    var f = D.frames[n];
    lab.textContent = 'Example ' + (n + 1) + ' of ' + D.frames.length + ' \\u2014 ' + f.label;
    quote.textContent = f.text;
    if(reduce){ from = f; paint(f, 1); return; }
    var t0 = null, prev = from;
    function step(ts){
      if(t0 === null) t0 = ts;
      var t = Math.min(1, (ts - t0) / D.ms);
      // Ease-out, matching the Material 3 emphasized curve the stylesheet uses
      // for everything else in this panel. Cheap approximation of the cubic
      // bezier; the endpoint is exact, which is the part that matters.
      paint(f, 1 - Math.pow(1 - t, 3));
      if(t < 1) requestAnimationFrame(step); else { from = f; paint(f, 1); }
    }
    from = prev; requestAnimationFrame(step);
  }
  function go(n){ i = (n + D.frames.length) % D.frames.length; show(i); }

  document.getElementById('prev').onclick = function(){ stop(); go(i - 1); };
  document.getElementById('next').onclick = function(){ stop(); go(i + 1); };
  var playBtn = document.getElementById('play');
  function stop(){ if(timer){ clearInterval(timer); timer = null; playBtn.textContent = 'Play'; } }
  playBtn.onclick = function(){
    if(timer){ stop(); return; }
    playBtn.textContent = 'Pause';
    timer = setInterval(function(){ go(i + 1); }, D.ms + 1400);
  };
  from = D.frames[0];
  show(0);
})();
</script>
"""


# ===========================================================================
# V3, cognitive load
# ===========================================================================

TRACE_W = 720
TRACE_H = 120
METER_W = 720
METER_H = 46


#: Display smoothing window, in samples. The pupil channel is a slow level plus
#: per-sample noise, so at 600 points the raw trace renders as a band of static
#: in which the level -- the only thing that matters -- is invisible. Found by
#: looking at the panel. The number the meter uses is the mean of the RAW
#: series, never the smoothed one: smoothing is for the eye only, and the
#: caption says so.
SMOOTH_N = 12


def _smooth(values, n: int = SMOOTH_N) -> list[float]:
    """Centred moving average. Display only -- no feature is computed from this."""
    series = [float(v) for v in values]
    if n <= 1 or len(series) <= n:
        return series
    half = n // 2
    out = []
    for i in range(len(series)):
        lo, hi = max(0, i - half), min(len(series), i + half + 1)
        out.append(sum(series[lo:hi]) / (hi - lo))
    return out


def _polyline(values, x0: float, y0: float, w: float, h: float) -> str:
    """Map a series onto a box. Min-max scaled, which is stated in the caption.

    Scaled per window rather than against a fixed axis because the three
    channels have no shared unit and no absolute range anybody here could
    justify. That makes the trace a shape, not a level -- and the numbers beside
    it, which do carry units, are what a reader is meant to take away.
    """
    series = [float(v) for v in values]
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1.0
    step = w / max(1, len(series) - 1)
    return " ".join(
        f"{x0 + i * step:.1f},{y0 + h - (v - lo) / span * h:.1f}" for i, v in enumerate(series)
    )


def _load_meter(value: float, t: dict[str, str]) -> str:
    """One bar, no bands, no thresholds, no tick marks.

    `charts.py::risk_meter` refuses to band an uncalibrated ranking and says
    why; this meter is on the same footing and gets the same treatment. A
    coloured zone here would invent a threshold that nothing in this project
    supports, and it would read as a verdict about whoever the trace belonged to.
    """
    width = max(0.0, min(1.0, float(value))) * METER_W
    return (
        f'<svg viewBox="0 0 {METER_W} {METER_H}" width="100%" role="img" '
        f'aria-label="Load index {value:.2f}, {escape(plain.LOAD_NOT_CALIBRATED)}" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="0" y="14" width="{METER_W}" height="16" rx="8" fill="{t["stone"]}"/>'
        f'<rect id="meterfill" x="0" y="14" width="{width:.2f}" height="16" rx="8" '
        f'fill="{t["raise"]}"/>'
        "</svg>"
    )


def _channel_rows(window, t: dict[str, str]) -> str:
    from src.biosignals.features import LOAD_WEIGHTS

    rows = []
    for key, name, meaning in plain.LOAD_CHANNELS:
        value = window.features.get(key, 0.0)
        rows.append(
            f'<tr><th scope="row">{escape(name)}</th>'
            f'<td class="mn">{escape(meaning)}</td>'
            f'<td class="num" data-ch="{key}">{value:.2f}</td>'
            f'<td class="anchor">weight {LOAD_WEIGHTS[key]:+.2f}</td></tr>'
        )
    return "".join(rows)


def load_height(window) -> int:
    """Iframe height. Measured the same way `atlas_height` was; see its docstring."""
    return 1400


def load_panel(window, *, mode: str = motion.DEFAULT_MODE, frames: Sequence = ()) -> str:
    """The V3 panel: two traces, blink ticks, one unbanded meter, three rows.

    `window` is a frozen `BiosignalWindow`, which cannot exist without a
    provenance stamp -- so this panel cannot be handed an unstamped trace, and
    the stamp is rendered as the first element in the document rather than
    anywhere a crop could remove it.

    `frames` makes it playable: pass consecutive windows from the same source and
    the panel gets Prev / Play / Next. Every frame is a real window from a seeded
    source, so the same seed redraws the same session.
    """
    t = surface(mode)
    timeline = [window, *[w for w in frames if w is not window]]
    payload = json.dumps(
        {
            "frames": [
                {
                    "index": w.index,
                    "features": {k: round(v, 4) for k, v in w.features.items()},
                    "rr": [round(v, 2) for v in w.channels["rr_ms"]],
                    "pupil": [round(v, 4) for v in w.channels["pupil_z"]],
                    "blink": [int(b) for b in w.channels["blink"]],
                }
                for w in timeline
            ],
            "w": TRACE_W,
            "h": TRACE_H,
            "meterW": METER_W,
            "smoothN": SMOOTH_N,
            "ms": DURATION_MS["emphasized"],
        }
    )
    rr = window.channels["rr_ms"]
    pupil = window.channels["pupil_z"]
    blinks = list(window.channels["blink"])
    blink_step = TRACE_W / max(1, len(blinks) - 1)
    blink_marks = "".join(
        f'<line x1="{i * blink_step:.1f}" y1="0" x2="{i * blink_step:.1f}" y2="14" '
        'stroke="currentColor" stroke-width="1.5"/>'
        for i, b in enumerate(blinks)
        if b > 0.5
    )
    load = window.features["load_index"]

    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        + _atlas_style(t)
        + "</head><body><div class='card'>"
        # Provenance first, before any trace. Same ordering rule as the atlas
        # caveat and as the stamp above the widget grid.
        + stamp_row(escape(window.stamp))
        + f"<h2>{escape(plain.LOAD_TITLE)}</h2>"
        + f"<p class='sub'>{escape(plain.LOAD_PLAIN)}</p>"
        + "<div class='sim'>"
        "<button type='button' id='prev' aria-label='Previous window'>&#9664;</button>"
        "<button type='button' id='play' class='primary'>Play</button>"
        "<button type='button' id='next' aria-label='Next window'>&#9654;</button>"
        "<span class='simlab' id='simlab'></span>"
        "</div>"
        + "<div class='fig'>"
        + "<p class='tlab'>RR interval &mdash; beat to beat</p>"
        + f'<svg viewBox="0 0 {TRACE_W} {TRACE_H}" width="100%" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<polyline id="rr" fill="none" stroke="{t["raise"]}" stroke-width="2" '
        f'points="{_polyline(rr, 0, 6, TRACE_W, TRACE_H - 12)}"/>'
        + "</svg>"
        + "<p class='tlab'>Pupil &mdash; against its own baseline, smoothed for the eye</p>"
        + f'<svg viewBox="0 0 {TRACE_W} {TRACE_H}" width="100%" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<polyline id="pu" fill="none" stroke="{t["lower"]}" stroke-width="2" '
        f'points="{_polyline(_smooth(pupil), 0, 6, TRACE_W, TRACE_H - 12)}"/>'
        + "</svg>"
        + "<p class='tlab'>Blinks</p>"
        + f'<svg viewBox="0 0 {TRACE_W} 16" width="100%" xmlns="http://www.w3.org/2000/svg">'
        + f'<g id="bl">{blink_marks}</g></svg>'
        + "</div>"
        + f"<h3>Load index <span class='big' id='loadv'>{load:.2f}</span></h3>"
        + _load_meter(load, t)
        + f"<p class='cap'>{escape(plain.LOAD_NOT_CALIBRATED)}</p>"
        + f"<p class='sub'>{escape(plain.LOAD_HOW_TO_READ)}</p>"
        + "<div class='scroll'><table><thead><tr><th>Channel</th><th>What it is</th>"
        + "<th>This window</th><th>In the index</th></tr></thead><tbody>"
        + _channel_rows(window, t)
        + "</tbody></table></div>"
        + f"<p class='sub'>{escape(plain.LOAD_WEIGHTS_NOTE)}</p>"
        + f"<p class='sub'>{escape(plain.LOAD_WHAT_IT_IS_NOT)}</p>"
        + "</div>"
        + _LOAD_SCRIPT.replace("__PAYLOAD__", payload)
        + "</body></html>"
    )
    return screened(document)


#: Classic script, no imports, no network. Same argument as the atlas simulator
#: and as `motion.py`: the server has already drawn frame zero, so a script that
#: never runs costs the Play button and nothing else.
_LOAD_SCRIPT = """
<script>
(function(){
  var D = __PAYLOAD__;
  var i = 0, timer = null;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function smooth(vals){
    // Mirrors _smooth() in neurovis.py. Display only: every number on this
    // panel comes from the payload's features, which were computed server-side
    // from the raw series.
    var n = D.smoothN, half = n >> 1;
    if(n <= 1 || vals.length <= n) return vals;
    return vals.map(function(_, i){
      var lo = Math.max(0, i - half), hi = Math.min(vals.length, i + half + 1), s = 0;
      for(var k = lo; k < hi; k++) s += vals[k];
      return s / (hi - lo);
    });
  }
  function path(vals, h){
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var span = (hi - lo) || 1, step = D.w / Math.max(1, vals.length - 1);
    return vals.map(function(v, n){
      return (n * step).toFixed(1) + ',' + (6 + (h - 12) - (v - lo) / span * (h - 12)).toFixed(1);
    }).join(' ');
  }
  function show(n){
    var f = D.frames[n];
    document.getElementById('simlab').textContent =
      'Window ' + (n + 1) + ' of ' + D.frames.length + ' \\u2014 generated';
    document.getElementById('rr').setAttribute('points', path(f.rr, D.h));
    document.getElementById('pu').setAttribute('points', path(smooth(f.pupil), D.h));
    var step = D.w / Math.max(1, f.blink.length - 1), marks = '';
    f.blink.forEach(function(b, k){
      if(b) { var x = (k * step).toFixed(1);
        marks += '<line x1="' + x + '" y1="0" x2="' + x + '" y2="14" stroke="currentColor" stroke-width="1.5"/>'; }
    });
    document.getElementById('bl').innerHTML = marks;
    var load = f.features.load_index;
    document.getElementById('loadv').textContent = load.toFixed(2);
    var fill = document.getElementById('meterfill');
    if(reduce) fill.setAttribute('width', (load * D.meterW).toFixed(2));
    else {
      var from = parseFloat(fill.getAttribute('width')), t0 = null;
      requestAnimationFrame(function step2(ts){
        if(t0 === null) t0 = ts;
        var t = Math.min(1, (ts - t0) / D.ms), e = 1 - Math.pow(1 - t, 3);
        fill.setAttribute('width', (from + (load * D.meterW - from) * e).toFixed(2));
        if(t < 1) requestAnimationFrame(step2);
      });
    }
    document.querySelectorAll('[data-ch]').forEach(function(el){
      el.textContent = f.features[el.dataset.ch].toFixed(2);
    });
  }
  function go(n){ i = (n + D.frames.length) % D.frames.length; show(i); }
  var playBtn = document.getElementById('play');
  function stop(){ if(timer){ clearInterval(timer); timer = null; playBtn.textContent = 'Play'; } }
  document.getElementById('prev').onclick = function(){ stop(); go(i - 1); };
  document.getElementById('next').onclick = function(){ stop(); go(i + 1); };
  playBtn.onclick = function(){
    if(timer){ stop(); return; }
    playBtn.textContent = 'Pause';
    timer = setInterval(function(){ go(i + 1); }, D.ms + 900);
  };
  show(0);
})();
</script>
"""


# ===========================================================================
# V5, closed-loop neurofeedback, demo mode
# ===========================================================================

RING_BOX = 320
RING_MAX_R = 130.0
RING_MIN_R = 34.0


def ring_radius(ratio: float, target: float) -> float:
    """Ring radius from the alpha/theta ratio, in pixels.

    Affine in `ratio / (2 * target)`, clamped -- so the target always sits at
    exactly half the available span and the dashed reference circle can be drawn
    at a fixed place. Inverting it recovers the ratio, which is how
    `tests/test_neurovis.py` checks the ring introduces no number of its own.
    """
    if target <= 0:
        raise ValueError("the target must be positive.")
    fraction = max(0.0, min(1.0, float(ratio) / (2.0 * target)))
    return RING_MIN_R + (RING_MAX_R - RING_MIN_R) * fraction


def neurofeedback_height(session) -> int:
    """Iframe height. Measured, not guessed; see `atlas_height`."""
    return 1240


def neurofeedback_panel(session, ratios, *, mode: str = motion.DEFAULT_MODE, stamp: str) -> str:
    """The V5 panel: a ring, a target, a trace, and a demo-mode banner.

    The banner is the FIRST element in the document, before any control -- the
    same ordering rule the provenance stamp follows above the widget grid, and
    for the same reason: a warning below the fold is in the DOM and not on the
    screen. `tests/test_neurovis.py` asserts the ordering rather than the mere
    presence of the string.

    `session` is a `NeurofeedbackSession` and `ratios` a sequence from a
    simulated source. Every counter on screen is computed by
    `session.trace(ratios)` in pure Python; this function draws and does not
    calculate, so the arithmetic stays testable without a browser.
    """
    from src.biosignals.session import NeurofeedbackSession

    if not isinstance(session, NeurofeedbackSession):
        raise TypeError("neurofeedback_panel needs a NeurofeedbackSession.")
    t = surface(mode)
    states = session.trace(ratios)
    if not states:
        raise ValueError("a neurofeedback session needs at least one tick to draw.")
    first = states[0]
    target_r = ring_radius(session.target, session.target)
    c = RING_BOX / 2

    payload = json.dumps(
        {
            "states": [
                {
                    "r": round(ring_radius(s.ratio, session.target), 4),
                    "ratio": round(s.ratio, 4),
                    "onTarget": s.on_target,
                    "elapsed": round(s.elapsed_s, 2),
                    "inTarget": round(s.in_target_s, 2),
                    "longest": round(s.longest_hold_s, 2),
                }
                for s in states
            ],
            "raise": t["raise"],
            "lower": t["lower"],
            "slate": t["slate"],
            "tickMs": int(session.tick_s * 1000),
            "w": TRACE_W,
            "h": TRACE_H,
            "target": round(session.target, 4),
        }
    )

    ratio_series = [s.ratio for s in states]
    lo, hi = min(ratio_series), max(ratio_series)
    span = (hi - lo) or 1.0
    target_y = 6 + (TRACE_H - 12) - (session.target - lo) / span * (TRACE_H - 12)

    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        + _atlas_style(t)
        + "</head><body><div class='card'>"
        # Banner first. Before the stamp, before the controls, before the ring.
        + f"<p class='danger'>{escape(plain.NF_DEMO_ONLY)}</p>"
        + stamp_row(escape(stamp))
        + f"<h2>{escape(plain.NF_TITLE)}</h2>"
        + f"<p class='sub'>{escape(plain.NF_PLAIN)}</p>"
        + "<div class='sim'>"
        "<button type='button' id='play' class='primary'>Start</button>"
        "<button type='button' id='reset'>Reset</button>"
        "<span class='simlab' id='simlab'></span>"
        "</div>"
        + "<div class='fig ringwrap'>"
        + f'<svg viewBox="0 0 {RING_BOX} {RING_BOX}" width="{RING_BOX}" height="{RING_BOX}" '
        f'role="img" aria-label="{escape(plain.NF_HOW_TO_READ)}" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<circle cx="{c}" cy="{c}" r="{target_r:.4f}" fill="none" stroke="{t["slate"]}" '
        'stroke-width="2" stroke-dasharray="6 5"/>' + f'<circle id="ring" cx="{c}" cy="{c}" '
        f'r="{ring_radius(first.ratio, session.target):.4f}" fill="none" '
        f'stroke="{t["raise"] if first.on_target else t["slate"]}" stroke-width="6"/>'
        + "</svg></div>"
        + f"<p class='sub'>{escape(plain.NF_HOW_TO_READ)}</p>"
        + "<div class='stats'>"
        + f"<div><span class='wl'>Time in target</span><span class='big' id='intarget'>"
        f"{first.in_target_s:.0f}s</span></div>"
        + f"<div><span class='wl'>Longest hold</span><span class='big' id='longest'>"
        f"{first.longest_hold_s:.0f}s</span></div>"
        + f"<div><span class='wl'>Elapsed</span><span class='big' id='elapsed'>"
        f"{first.elapsed_s:.0f}s</span></div>"
        + "</div>"
        + "<p class='tlab'>Alpha / theta against the target</p>"
        + f'<svg viewBox="0 0 {TRACE_W} {TRACE_H}" width="100%" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<line x1="0" y1="{target_y:.1f}" x2="{TRACE_W}" y2="{target_y:.1f}" '
        f'stroke="{t["slate"]}" stroke-width="1.2" stroke-dasharray="5 4"/>'
        + f'<polyline id="tr" fill="none" stroke="{t["raise"]}" stroke-width="2" '
        f'points="{_polyline(ratio_series, 0, 6, TRACE_W, TRACE_H - 12)}"/>'
        + "</svg>"
        + f"<p class='danger'>{escape(plain.NF_ETHICS_GATE)}</p>"
        + "</div>"
        + _NF_SCRIPT.replace("__PAYLOAD__", payload)
        + "</body></html>"
    )
    return screened(document)


#: Classic script, no imports, no network -- the pattern `motion.py` records.
#: The server has already painted the first state, the ring, the trace and every
#: counter, so a script that never runs costs the Start button and nothing else.
#: The panel is still a complete, readable, correctly-captioned figure.
_NF_SCRIPT = """
<script>
(function(){
  var D = __PAYLOAD__;
  var i = 0, timer = null;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var ring = document.getElementById('ring');
  var playBtn = document.getElementById('play');
  function render(n){
    var s = D.states[n];
    ring.setAttribute('r', s.r.toFixed(4));
    ring.setAttribute('stroke', s.onTarget ? D['raise'] : D.slate);
    document.getElementById('intarget').textContent = s.inTarget.toFixed(0) + 's';
    document.getElementById('longest').textContent = s.longest.toFixed(0) + 's';
    document.getElementById('elapsed').textContent = s.elapsed.toFixed(0) + 's';
    document.getElementById('simlab').textContent =
      'Tick ' + (n + 1) + ' of ' + D.states.length + ' \\u2014 generated signal, no person';
  }
  function stop(){ if(timer){ clearInterval(timer); timer = null; playBtn.textContent = 'Start'; } }
  playBtn.onclick = function(){
    if(timer){ stop(); return; }
    playBtn.textContent = 'Pause';
    timer = setInterval(function(){
      i = (i + 1) % D.states.length;
      render(i);
    }, reduce ? D.tickMs * 2 : D.tickMs);
  };
  document.getElementById('reset').onclick = function(){ stop(); i = 0; render(0); };
  render(0);
})();
</script>
"""


# ===========================================================================
# V3, narrated, a clip of speech with the simulated body following it
# ===========================================================================

NARRATED_TRACE_H = 110


def narrated_height(session) -> int:
    """Iframe height. Measured, not guessed; see `atlas_height`."""
    return 1520


def narrated_panel(session, clip, *, mode: str = motion.DEFAULT_MODE) -> str:
    """A spoken clip, with a simulated body that responds to it as it plays.

    THE ARROW RUNS TEXT -> BODY, AND IT WAS DRAWN BY THIS CODE.

    That sentence is the whole design constraint. The panel is one step away
    from looking like a recording of a person having a physiological response to
    their own words, which is a claim this project cannot make and has
    deliberately deferred to a second paper. So three things are structural
    rather than editorial:

    * the voice is stated as synthetic on the surface, not only in a docstring;
    * the coupling is stated as imposed, above the trace rather than below it;
    * `NarratedSession` cannot be constructed without a SIMULATED stamp, and
      this function renders that stamp before the player.

    Everything is drawn server-side first. The classic script only moves a
    playhead and swaps readouts, so with JavaScript off the panel is a complete
    figure of the whole clip -- the pattern `motion.py` records.
    """
    t = surface(mode)
    windows = session.windows
    first = windows[0]

    # Plotted as BEATS PER MINUTE, not as the RR interval.
    #
    # The first version drew RR straight from the channel under a heading that
    # said "heart rate", and RR is the reciprocal: a rising line meant a SLOWING
    # heart, directly contradicting the bpm readout eight centimetres below it.
    # Both halves were individually correct and the figure as a whole said the
    # opposite of what it meant. Only the rendered panel could show that.
    beats = session.clip_rr
    bpm_series = [60000.0 / rr for _t, rr in beats]
    rr_points = (
        _polyline(bpm_series, 0, 6, TRACE_W, NARRATED_TRACE_H - 12) if len(bpm_series) > 1 else ""
    )
    pupil_from = 0
    pupil = list(session.pupil_z)[pupil_from:]
    pupil_points = _polyline(_smooth(pupil), 0, 6, TRACE_W, NARRATED_TRACE_H - 12)

    clip_blink = list(session.clip_blink)
    step = TRACE_W / max(1, len(clip_blink) - 1)
    blink_marks = "".join(
        f'<line x1="{i * step:.1f}" y1="0" x2="{i * step:.1f}" y2="12" '
        'stroke="currentColor" stroke-width="1.5"/>'
        for i, b in enumerate(clip_blink)
        if b > 0.5
    )

    words = "".join(
        f'<span class="wd" data-s="{w["start_s"]}" data-e="{w["end_s"]}">{escape(w["word"])}</span> '
        for w in clip.words
    )

    payload = json.dumps(
        {
            "duration": round(session.duration_s, 3),
            "step": round(session.duration_s / max(1, len(windows) - 1), 4)
            if len(windows) > 1
            else 1.0,
            "frames": [
                {
                    "t": round(w.t0_s, 3),
                    "bpm": round(w.features["heart_rate_bpm"], 1),
                    "pupil": round(w.features["pupil_effort"], 3),
                    "blink": round(w.features["blink_rate"], 1),
                    "load": round(w.features["load_index"], 4),
                }
                for w in windows
            ],
            "w": TRACE_W,
            "meterW": METER_W,
        }
    )

    document = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        + _atlas_style(t)
        + "</head><body><div class='card'>"
        + stamp_row(escape(session.stamp))
        + f"<p class='danger'>{escape(plain.NARRATED_VOICE_NOTE)}</p>"
        + f"<h2>{escape(plain.NARRATED_TITLE)}</h2>"
        + f"<p class='sub'>{escape(plain.NARRATED_PLAIN)}</p>"
        + f"<p class='danger'>{escape(plain.NARRATED_IMPOSED)}</p>"
        + f'<audio id="clip" controls preload="auto" src="{clip.data_uri()}"></audio>'
        + f'<p class="spoken" id="spoken">{words}</p>'
        + "<div class='fig'>"
        + "<p class='tlab'>Heart rate &mdash; beat to beat</p>"
        + f'<svg viewBox="0 0 {TRACE_W} {NARRATED_TRACE_H}" width="100%" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<polyline fill="none" stroke="{t["raise"]}" stroke-width="2" '
        f'points="{rr_points}"/>'
        + f'<line class="ph" id="ph1" x1="0" y1="0" x2="0" y2="{NARRATED_TRACE_H}" '
        f'stroke="{t["ink"]}" stroke-width="1.5"/>'
        + "</svg>"
        + "<p class='tlab'>Pupil &mdash; against its own baseline, smoothed for the eye</p>"
        + f'<svg viewBox="0 0 {TRACE_W} {NARRATED_TRACE_H}" width="100%" '
        'xmlns="http://www.w3.org/2000/svg">'
        + f'<polyline fill="none" stroke="{t["lower"]}" stroke-width="2" '
        f'points="{pupil_points}"/>'
        + f'<line class="ph" id="ph2" x1="0" y1="0" x2="0" y2="{NARRATED_TRACE_H}" '
        f'stroke="{t["ink"]}" stroke-width="1.5"/>'
        + "</svg>"
        + "<p class='tlab'>Blinks</p>"
        + f'<svg viewBox="0 0 {TRACE_W} 14" width="100%" xmlns="http://www.w3.org/2000/svg">'
        + f'<g id="bl">{blink_marks}</g></svg>'
        + "</div>"
        + "<div class='stats'>"
        + f"<div><span class='wl'>Heart rate</span><span class='big' id='bpm'>"
        f"{first.features['heart_rate_bpm']:.0f}</span><span class='wu'>bpm</span></div>"
        + f"<div><span class='wl'>Pupil effort</span><span class='big' id='pupil'>"
        f"{first.features['pupil_effort']:+.2f}</span><span class='wu'>z</span></div>"
        + f"<div><span class='wl'>Blink rate</span><span class='big' id='blink'>"
        f"{first.features['blink_rate']:.0f}</span><span class='wu'>per min</span></div>"
        + "</div>"
        + f"<h3>Load index <span class='big' id='loadv'>"
        f"{first.features['load_index']:.2f}</span></h3>"
        + _load_meter(first.features["load_index"], t)
        + f"<p class='cap'>{escape(plain.LOAD_NOT_CALIBRATED)}</p>"
        + f"<p class='sub'>{escape(plain.NARRATED_NO_HRV)}</p>"
        + f"<p class='sub'>{escape(plain.NARRATED_WHAT_IT_IS_NOT)}</p>"
        + "</div>"
        + _NARRATED_SCRIPT.replace("__PAYLOAD__", payload)
        + "</body></html>"
    )
    return screened(document)


_NARRATED_SCRIPT = """
<script>
(function(){
  var D = __PAYLOAD__;
  var audio = document.getElementById('clip');
  var words = [].slice.call(document.querySelectorAll('.wd'));
  var last = -1;
  function frameAt(t){
    var i = Math.round(t / D.step);
    return Math.max(0, Math.min(D.frames.length - 1, i));
  }
  function draw(t){
    var x = Math.max(0, Math.min(1, t / D.duration)) * D.w;
    document.getElementById('ph1').setAttribute('x1', x);
    document.getElementById('ph1').setAttribute('x2', x);
    document.getElementById('ph2').setAttribute('x1', x);
    document.getElementById('ph2').setAttribute('x2', x);
    var i = frameAt(t);
    if(i !== last){
      last = i;
      var f = D.frames[i];
      document.getElementById('bpm').textContent = f.bpm.toFixed(0);
      document.getElementById('pupil').textContent = (f.pupil >= 0 ? '+' : '') + f.pupil.toFixed(2);
      document.getElementById('blink').textContent = f.blink.toFixed(0);
      document.getElementById('loadv').textContent = f.load.toFixed(2);
      document.getElementById('meterfill').setAttribute('width', (f.load * D.meterW).toFixed(2));
    }
    words.forEach(function(el){
      var on = t >= parseFloat(el.dataset.s) && t < parseFloat(el.dataset.e);
      el.classList.toggle('on', on);
    });
  }
  audio.addEventListener('timeupdate', function(){ draw(audio.currentTime); });
  audio.addEventListener('seeked', function(){ draw(audio.currentTime); });
  audio.addEventListener('ended', function(){ draw(D.duration); });
  draw(0);
})();
</script>
"""
