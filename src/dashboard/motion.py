"""The animated plain-English panel. One HTML document, no framework.

Why an embedded document and not Streamlit widgets
--------------------------------------------------
Streamlit renders its own components server-side; it has no hook for a motion
system. So the readable half of the page is built as a single self-contained
HTML document and handed to `st.components.v1.html`, which mounts it in an
iframe. Inside that iframe we can use motion.dev (`animate`, `stagger`,
`inView`) to do the one thing static SVG cannot: show a bar *growing to* its
value, so a reader watches the number being assembled instead of arriving at a
finished picture and having to reverse-engineer it.

The honesty constraints do not relax inside an iframe
-----------------------------------------------------
* Every string this module emits is screened by `assert_no_forbidden_language`
  before it is returned (`_screened`). The `view.render_text()` screen cannot
  see this document -- it is written here, not carried through the view -- so the
  screen is applied where the text is produced.
* The panel renders **no number the view does not already carry**. It reads
  `ConstructBar.probability`, `.contribution` and `.inert` and nothing else, so
  it cannot disagree with the SVG figures beside it. It is a second rendering of
  one set of facts, never a second computation of them.
* Inert constructs keep all three redundant channels from `charts.py`: a hatched
  fill, a dashed outline, and the literal word. Animation is a fourth channel
  (inert rows do not grow), never a replacement for the other three.
* `prefers-reduced-motion` is honoured: the same layout, jumped to its end state.

The SVG charts in `charts.py` remain the paper figures. This is the demo
surface. They are drawn from the same `ConstructBar` tuple on purpose.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from html import escape

from src.dashboard import theme
from src.dashboard.copy import CONSTRUCTS, DIRECTION_PLAIN
from src.dashboard.view import ConstructBar, DashboardView, assert_no_forbidden_language

MOTION_CDN = "https://cdn.jsdelivr.net/npm/motion@11.11.13/+esm"

# Sized for the design system's 32px card padding and 16px/14px type pair.
ROW_PX = 74
CHROME_PX = 360


#: Surface tokens per mode. The panel is mounted in an iframe, which inherits
#: nothing from the host page -- so the mode has to be passed in rather than
#: read from a CSS variable, and every name has to be defined for every mode.
#: A mode that filled in half the names would produce the classic dark-on-dark
#: page, and it would do it only in the browser.
_SURFACES: dict[str, dict[str, str]] = {
    "light": {
        "ink": theme.INK,
        "muted": theme.BODY_MUTED,
        "slate": theme.SLATE,
        "line": theme.HAIRLINE,
        "card-border": theme.CARD_BORDER,
        "surface": theme.CANVAS,
        "stone": theme.SOFT_STONE,
        "raise": theme.RAISES,
        "lower": theme.LOWERS,
        "accent": theme.CORAL,
        "wash": theme.PALE_GREEN,
        "font": theme.FONT_UI,
        "display": theme.FONT_DISPLAY,
        "mono": theme.FONT_MONO,
        "radius": theme.RADIUS_LG,
        "fonts": theme.GOOGLE_FONTS,
    },
    "dark": {
        "ink": theme.DARK["ink"],
        "muted": theme.DARK["body"],
        "slate": theme.DARK["muted"],
        "line": theme.DARK["hairline"],
        "card-border": theme.DARK["card-border"],
        "surface": theme.DARK["surface"],
        "stone": theme.DARK["surface-alt"],
        "raise": theme.RAISES,
        "lower": "#4fb3a1",  # deep green is invisible on navy; its light sibling holds
        "accent": theme.CORAL,
        "wash": "#12304a",
        "font": theme.FONT_UI,
        "display": theme.FONT_DISPLAY,
        "mono": theme.FONT_MONO,
        "radius": theme.RADIUS_LG,
        "fonts": theme.GOOGLE_FONTS,
    },
    # Page 2 only, light. See theme.claude_css().
    "claude": {
        "ink": theme.CLAUDE_INK,
        "muted": theme.CLAUDE_BODY,
        "slate": theme.CLAUDE_MUTED,
        "line": theme.CLAUDE_HAIRLINE,
        "card-border": theme.CLAUDE_HAIRLINE,
        "surface": theme.CLAUDE_CANVAS,
        "stone": theme.CLAUDE_SURFACE_CARD,
        "raise": theme.CLAUDE_PRIMARY,
        "lower": theme.CLAUDE_SURFACE_DARK,
        "accent": theme.CLAUDE_PRIMARY,
        "wash": theme.CLAUDE_SURFACE_SOFT,
        "font": theme.CLAUDE_FONT_UI,
        "display": theme.CLAUDE_FONT_DISPLAY,
        "mono": theme.CLAUDE_FONT_MONO,
        "radius": "12px",
        "fonts": theme.CLAUDE_FONTS,
    },
    # Page 2 only, dark. DESIGNclaude.md's own dark surface family.
    "claude-dark": {
        "ink": theme.CLAUDE_DARK["ink"],
        "muted": theme.CLAUDE_DARK["body"],
        "slate": theme.CLAUDE_DARK["muted"],
        "line": theme.CLAUDE_DARK["hairline"],
        "card-border": theme.CLAUDE_DARK["hairline"],
        "surface": theme.CLAUDE_DARK["card"],
        "stone": theme.CLAUDE_DARK["soft"],
        "raise": theme.CLAUDE_PRIMARY,
        "lower": "#8fb8ae",  # surface-dark cannot be a bar on a dark card
        "accent": theme.CLAUDE_PRIMARY,
        "wash": "#2b2723",
        "font": theme.CLAUDE_FONT_UI,
        "display": theme.CLAUDE_FONT_DISPLAY,
        "mono": theme.CLAUDE_FONT_MONO,
        "radius": "12px",
        "fonts": theme.CLAUDE_FONTS,
    },
}

DEFAULT_MODE = "light"


def _style(mode: str) -> str:
    """The panel's stylesheet for one mode."""
    t = _SURFACES.get(mode, _SURFACES[DEFAULT_MODE])
    return (
        t["fonts"]
        + f"""
<style>
  :root{{
    --ink:{t["ink"]}; --muted:{t["muted"]}; --slate:{t["slate"]};
    --line:{t["line"]}; --card-border:{t["card-border"]};
    --surface:{t["surface"]}; --stone:{t["stone"]};
    --raise:{t["raise"]}; --lower:{t["lower"]};
    --accent:{t["accent"]}; --wash:{t["wash"]};
    --radius-card:{t["radius"]}; --radius-chip:8px;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:transparent;color:var(--ink);font-family:{t["font"]};}}
  .card{{background:var(--surface);border:1px solid var(--card-border);
    border-radius:var(--radius-card);padding:32px;}}
  .hero{{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;margin-bottom:4px}}
  .big{{font-family:{t["display"]};font-size:72px;font-weight:400;
    line-height:1;letter-spacing:-1.44px}}
  .hero h2{{font-family:{t["mono"]};font-size:14px;font-weight:400;margin:0;
    text-transform:uppercase;letter-spacing:.28px;color:var(--slate)}}
  .sub{{color:var(--muted);font-size:16px;line-height:1.5;margin:8px 0 24px;max-width:68ch}}
  .track{{position:relative;height:8px;border-radius:9999px;background:var(--stone);
    overflow:hidden}}
  .fill{{position:absolute;inset:0;width:100%;transform-origin:left center;
    background:var(--lower);border-radius:9999px}}
  .ends{{display:flex;justify-content:space-between;color:var(--slate);font-size:14px;
    font-family:{t["mono"]};letter-spacing:.28px;text-transform:uppercase;margin-top:8px}}
  .rows{{list-style:none;margin:32px 0 0;padding:0}}
  .row{{display:grid;grid-template-columns:220px 1fr;gap:24px;align-items:center;
    padding:16px 0;border-top:1px solid var(--line)}}
  .row:first-child{{border-top:0}}
  .nm{{font-size:18px;font-weight:400;line-height:1.4}}
  .mn{{font-size:14px;color:var(--muted);line-height:1.4;margin-top:2px}}
  .plot{{position:relative;height:30px}}
  .rule{{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line)}}
  .bar{{position:absolute;top:8px;height:14px;border-radius:4px}}
  .bar.up{{left:50%;transform-origin:left center;background:var(--raise)}}
  .bar.dn{{right:50%;transform-origin:right center;background:var(--lower)}}
  .val{{position:absolute;top:9px;font-size:14px;color:var(--ink)}}
  .inertbox{{position:absolute;left:calc(50% - 11px);top:7px;width:22px;height:16px;
    border:1.5px dashed var(--slate);border-radius:4px;
    background:repeating-linear-gradient(45deg,transparent 0 3px,var(--stone) 3px 5px)}}
  .inertlab{{position:absolute;left:calc(50% + 20px);top:9px;font-size:14px;
    color:var(--slate);font-style:italic}}
  .row.is-inert .nm,.row.is-inert .mn{{color:var(--slate)}}
  .legend{{display:flex;gap:24px;font-size:14px;font-family:{t["mono"]};
    letter-spacing:.28px;text-transform:uppercase;color:var(--slate);margin-top:32px;
    flex-wrap:wrap}}
  .swatch{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:8px}}
  @media (prefers-reduced-motion: reduce){{
    .row,.bar,.fill,.ev{{animation:none!important}}
  }}
  ul.ev{{list-style:none;margin:0;padding:0}}
  .ev{{border-top:1px solid var(--line);padding:20px 0}}
  .ev:first-child{{border-top:0}}
  .hd{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}}
  .hd b{{font-size:18px;font-weight:400}}
  .tech{{font-size:14px;color:var(--slate);letter-spacing:.28px;font-family:{t["mono"]}}}
  .badge{{font-size:14px;letter-spacing:.28px;text-transform:uppercase;
    font-family:{t["mono"]};color:var(--slate);margin-left:auto}}
  .sps{{margin-top:12px;font-size:16px;line-height:2.0}}
  mark.sp{{background:var(--wash);color:var(--ink);padding:4px 12px;
    border-radius:var(--radius-chip);margin-right:8px;
    box-shadow:inset 0 -2px 0 0 var(--accent)}}
  .none{{color:var(--slate);font-style:italic;font-size:14px}}
</style>
"""
    )


def panel_height(view: DashboardView) -> int:
    """Iframe height in pixels. An iframe does not grow to its content."""
    return CHROME_PX + ROW_PX * len(view.bars)


def _rows(bars: Sequence[ConstructBar]) -> list[dict]:
    """One dict per construct, ordered by how much it moved the index.

    Sorted by absolute contribution rather than alphabetically -- the SVG figure
    keeps alphabetical order because a figure is scanned for a named row, while
    a demo panel is scanned top-down for "what drove this". Same rows, same
    numbers, different question.
    """
    out = []
    for bar in bars:
        plain_name, plain_meaning, plain_direction = CONSTRUCTS.get(
            bar.construct,
            (bar.construct.replace("_", " "), "", "inert" if bar.inert else "raises"),
        )
        out.append(
            {
                "key": bar.construct,
                "name": plain_name,
                "technical": bar.construct.replace("_", " "),
                "meaning": plain_meaning,
                "direction": DIRECTION_PLAIN[plain_direction],
                "probability": round(bar.probability, 4),
                "contribution": round(bar.contribution, 4),
                "inert": bar.inert,
                "detected": bar.detected,
                "spans": [s.text for s in bar.spans],
            }
        )
    out.sort(key=lambda r: (r["inert"], -abs(r["contribution"]), -r["probability"]))
    return out


def _screened(html: str) -> str:
    assert_no_forbidden_language(html)
    return html


def motion_panel(view: DashboardView, *, mode: str = DEFAULT_MODE) -> str:
    """The whole panel as one HTML document, in one surface mode."""
    rows = _rows(view.bars)
    payload = json.dumps(
        {
            "risk": round(view.risk.value, 4),
            "rows": rows,
            "contributing": sum(1 for r in rows if not r["inert"]),
            "total": len(rows),
            "unevidenced": view.unevidenced_driver_count,
            "source": view.source,
        }
    )
    return _screened(
        _DOCUMENT.replace("__STYLE__", _style(mode))
        .replace("__PAYLOAD__", payload)
        .replace("__CDN__", MOTION_CDN)
    )


def spans_panel(view: DashboardView, *, mode: str = DEFAULT_MODE) -> str:
    """The evidence list: which words triggered which signal.

    Separate from `motion_panel` so a reader can be shown the number and the
    words that produced it in two beats rather than one wall.
    """
    items = []
    for row in _rows(view.bars):
        if not row["detected"]:
            continue
        if row["spans"]:
            quoted = "".join(f'<mark class="sp">{escape(t)}</mark>' for t in row["spans"])
        else:
            quoted = '<span class="none">no words in the text back this up</span>'
        badge = "counted as zero" if row["inert"] else row["direction"]
        items.append(
            f'<li class="ev"><div class="hd"><b>{escape(row["name"])}</b>'
            f'<span class="tech">{escape(row["technical"])}</span>'
            f'<span class="badge">{escape(badge)}</span></div>'
            f'<div class="sps">{quoted}</div></li>'
        )
    body = "".join(items) or '<li class="ev"><div class="sps">Nothing was detected.</div></li>'
    return _screened(
        _EVIDENCE.replace("__STYLE__", _style(mode))
        .replace("__ITEMS__", body)
        .replace("__CDN__", MOTION_CDN)
    )


def evidence_height(view: DashboardView) -> int:
    return 104 + 104 * max(1, sum(1 for b in view.bars if b.detected))


_DOCUMENT = """<!doctype html><html><head><meta charset="utf-8">__STYLE__</head><body>
<div class="card">
  <div class="hero">
    <h2>Risk index</h2>
    <div class="big" id="big">0.00</div>
  </div>
  <div class="sub">how strained the words sound overall &mdash; an ordering, not a probability</div>
  <div class="track"><div class="fill" id="fill"></div></div>
  <div class="ends"><span>0 &mdash; nothing flagged</span><span>1 &mdash; everything flagged</span></div>
  <ul class="rows" id="rows"></ul>
  <div class="legend">
    <span><i class="swatch" style="background:var(--raise)"></i>pushes the number up</span>
    <span><i class="swatch" style="background:var(--lower)"></i>pulls the number down</span>
    <span><i class="swatch" style="border:1.5px dashed var(--muted);background:none"></i>inert &mdash; shown, counted as zero</span>
  </div>
</div>
<script>
// Content first, animation second. This block is a *classic* script with no
// imports, so the panel renders in full even when the motion.dev module fails
// to load -- an offline container, a blocked CDN, a corporate proxy. Found by
// screenshotting the page with the network cut: the module never executed and
// the card came back empty while every unit test stayed green. Same shape as
// the hatch-id collision in charts.py -- only the rendered page could see it.
const data = __PAYLOAD__;
const span = Math.max(...data.rows.map(r => Math.abs(r.contribution)), 0.001);
document.getElementById("big").textContent = data.risk.toFixed(2);
document.getElementById("fill").style.transform = `scaleX(${data.risk})`;
document.getElementById("rows").innerHTML = data.rows.map(r => {
  const w = (Math.abs(r.contribution) / span) * 40;
  const plot = r.inert
    ? `<div class="rule"></div><div class="inertbox"></div><div class="inertlab">inert &mdash; counted as zero</div>`
    : `<div class="rule"></div>
       <div class="bar ${r.contribution >= 0 ? "up" : "dn"}" style="width:${w}%"></div>
       <div class="val" style="${r.contribution >= 0
          ? `left:calc(50% + ${w}% + 8px)` : `right:calc(50% + ${w}% + 8px)`}">${
          r.contribution >= 0 ? "+" : ""}${r.contribution.toFixed(3)}</div>`;
  return `<li class="row ${r.inert ? "is-inert" : ""}">
    <div><div class="nm">${r.name}</div><div class="mn">${r.meaning}</div></div>
    <div class="plot">${plot}</div></li>`;
}).join("");
</script>
<script type="module">
// Progressive enhancement only. Every keyframe below starts from a state this
// code sets itself and ends on the state the classic script already painted,
// so a failed import changes nothing a reader can see.
import { animate, stagger } from "__CDN__";
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const big = document.getElementById("big");
  animate(0, data.risk, {
    duration: 1.1, ease: [0.22, 1, 0.36, 1],
    onUpdate: v => big.textContent = v.toFixed(2),
  });
  animate("#fill", { transform: ["scaleX(0)", `scaleX(${data.risk})`] },
          { duration: 1.1, ease: [0.22, 1, 0.36, 1] });
  animate(".row", { opacity: [0, 1], transform: ["translateY(8px)", "translateY(0px)"] },
          { duration: 0.45, delay: stagger(0.05, { startDelay: 0.2 }) });
  animate(".bar", { transform: ["scaleX(0)", "scaleX(1)"] },
          { duration: 0.6, delay: stagger(0.05, { startDelay: 0.3 }),
            ease: [0.22, 1, 0.36, 1], transformOrigin: undefined });
}
</script></body></html>"""

_EVIDENCE = """<!doctype html><html><head><meta charset="utf-8">__STYLE__</head><body>
<div class="card"><ul class="ev" id="ev">__ITEMS__</ul></div>
<script type="module">
// Enhancement only; the list is already in the document above.
import { animate, stagger } from "__CDN__";
if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  animate(".ev", { opacity: [0, 1], transform: ["translateY(6px)", "translateY(0px)"] },
          { duration: 0.4, delay: stagger(0.07) });
}
</script></body></html>"""
