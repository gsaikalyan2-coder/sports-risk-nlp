"""Renders `CoverageLedger` as one self-contained HTML document.

Same contract as `motion.motion_panel` and `neurovis.atlas_panel`: one document,
no external request, mounted with `st.components.v1.html`. A separate module
rather than another function in `neurovis.py` because that file is already 1364
lines and the coding rules cap a file at 800.

Three things this renderer is not allowed to do, each enforced by a test in
`tests/test_coverage.py`
-------------------------------------------------------------------------------
1. **Put a state on screen in hue alone.** Every state renders three channels --
   a glyph, a hue and the literal word. The rule is `charts.py`'s and the reason
   is its reason: these surfaces become paper figures, and hue alone fails in
   grayscale, in print and for a reader with a colour vision deficiency.
2. **Say a construct is absent.** "Silent" is rendered as the word silent, and
   the fixed wording in `copy.COVERAGE_SILENT_CAVEAT` sits above the table
   saying what it does and does not mean. The phrasings "no somatic anxiety",
   "free of", "does not have" appear nowhere and are asserted absent.
3. **Fetch anything.** No webfont, no script, no stylesheet, no image. The
   defect `motion.py` records -- a blocked CDN left the card empty while every
   unit test stayed green -- is not available here because there is nothing to
   block. The type stack is the local serif/system pair the mockup used.

Every colour comes from `theme.palette(mode)`. Nothing is written as a literal
hex in this file; a second palette is a second thing to forget to fill in for a
new mode, and a half-filled mode is how a dark page ends up unreadable.
"""

from __future__ import annotations

from html import escape

from src.dashboard import theme
from src.dashboard.copy import (
    COVERAGE_CAVEATS,
    COVERAGE_LEGEND,
    COVERAGE_PROMPTS_HEADING,
    COVERAGE_PROMPTS_NOTE,
    COVERAGE_SUBTITLE,
    COVERAGE_TITLE,
)
from src.dashboard.coverage import STATE_GLYPHS, CoverageLedger, CoverageState

#: Which palette token paints which state. The mapping is here rather than in
#: `coverage.py` because it is presentation: the ledger knows a subscale is
#: silent, it does not know what silent looks like. Same separation
#: `atlas_map.py` keeps by leaving geometry out of the YAML.
STATE_TOKENS: dict[CoverageState, str] = {
    CoverageState.EVIDENCED: "accent",
    CoverageState.INERT: "muted",
    CoverageState.SILENT: "hairline",
    CoverageState.REFUSED: "hairline",
}

#: Rows of table, plus the fixed furniture above and below it. Measured the way
#: `neurovis.atlas_height` was -- by rendering the panel and reading the height
#: the iframe needed -- rather than computed from a font metric the browser may
#: not honour.
_ROW_PX = 58
_CHROME_PX = 620
_PROMPT_PX = 34


def coverage_height(ledger: CoverageLedger) -> int:
    """Iframe height for this ledger. Grows with the prompt list, which varies."""
    prompts = sum(len(row.unevidenced) for row in ledger.instruments)
    return _CHROME_PX + _ROW_PX * len(ledger.instruments) + _PROMPT_PX * prompts


def _swatch(state: CoverageState) -> str:
    """One glyph in the state's hue. The word travels in the cell beside it."""
    return f'<span class="g s-{state.value}">{STATE_GLYPHS[state]}</span>'


def coverage_panel(ledger: CoverageLedger, *, mode: str = theme.DEFAULT_MODE) -> str:
    """The panel: a caveat block, a table of eight rows, a summary, the stamp.

    The caveats render **before** the first table row, outside anything
    collapsible, because a caveat below the number does not travel with a
    screenshot of the number. `tests/test_coverage.py` asserts the ordering in
    the document source, not merely the presence.
    """
    p = theme.palette(mode)

    caveats = "".join(f'<p class="caveat">{escape(c)}</p>' for c in COVERAGE_CAVEATS)

    legend = "".join(
        f'<span class="li"><span class="g s-{key}">{STATE_GLYPHS[CoverageState(key)]}</span>'
        f"<b>{escape(key)}</b> {escape(gloss)}</span>"
        for key, gloss in COVERAGE_LEGEND
    )

    rows = []
    for row in ledger.instruments:
        bars = "".join(_swatch(s.state) for s in row.subscales)
        if row.evidenced_count == row.total:
            detail = '<span class="done">all evidenced</span>'
        else:
            detail = " &middot; ".join(
                f'<span class="s-{s.state.value}-t">{escape(s.plain_name)}: {s.word}</span>'
                for s in row.unevidenced
            )
        rows.append(
            f'<tr><td class="name">{escape(row.name)}'
            f'<span class="cite">{escape(row.citation)}</span></td>'
            f'<td class="bars">{bars}'
            f'<span class="count">{row.evidenced_count} of {row.total}</span></td>'
            f'<td class="detail">{detail}</td></tr>'
        )

    prompts = "".join(
        f"<li><b>{escape(s.plain_name)}</b> &mdash; {escape(s.prompt)}</li>"
        for row in ledger.instruments
        for s in row.unevidenced
    )
    prompt_block = (
        f"<h3>{escape(COVERAGE_PROMPTS_HEADING)}</h3>"
        f'<p class="note">{escape(COVERAGE_PROMPTS_NOTE)}</p>'
        f"<ul>{prompts}</ul>"
        if prompts
        else ""
    )

    return f"""<!DOCTYPE html>
<meta charset="utf-8">
<style>
  :root{{
    --canvas:{p["canvas"]}; --surface:{p["surface"]}; --ink:{p["ink"]};
    --body:{p["body"]}; --muted:{p["muted"]}; --hairline:{p["hairline"]};
    --border:{p["border"]}; --accent:{p["accent"]};
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:transparent;color:var(--body);
    font:15px/1.55 Georgia,'Times New Roman',serif}}
  .panel{{background:var(--surface);border:1px solid var(--border);padding:22px 24px}}
  h2{{font-size:20px;margin:0 0 2px;color:var(--ink)}}
  .sub{{margin:0 0 14px;color:var(--muted);font-size:13px}}
  .caveat{{margin:0 0 8px;font-size:12px;color:var(--muted);
    padding-left:11px;border-left:2px solid var(--accent)}}
  .legend{{margin:14px 0 10px;font:11px/1.6 system-ui,sans-serif;color:var(--muted)}}
  .li{{margin-right:18px;white-space:nowrap}}
  .li b{{color:var(--body);margin:0 4px 0 5px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{text-align:left;font:11px/1 system-ui,sans-serif;text-transform:uppercase;
    letter-spacing:.09em;color:var(--muted);padding:0 0 8px;
    border-bottom:1px solid var(--hairline)}}
  td{{padding:10px 8px 10px 0;border-bottom:1px solid var(--hairline);
    vertical-align:top}}
  .name{{width:34%;color:var(--ink)}}
  .cite{{display:block;font-size:11px;color:var(--muted)}}
  .bars{{width:24%;white-space:nowrap}}
  .g{{font-size:17px;letter-spacing:2px}}
  .s-evidenced{{color:var(--accent)}}
  .s-inert{{color:var(--muted)}}
  .s-silent{{color:var(--hairline)}}
  .s-refused{{color:var(--hairline)}}
  .s-inert-t{{color:var(--body)}}
  .s-silent-t{{color:var(--muted)}}
  .count{{display:block;font-size:11px;color:var(--muted);
    font-family:system-ui,sans-serif;margin-top:3px}}
  .detail{{font-size:12px;color:var(--muted)}}
  .done{{color:var(--muted);opacity:.45}}
  .summary{{margin:16px 0 0;font-size:15px;color:var(--ink)}}
  h3{{font:11px/1 system-ui,sans-serif;text-transform:uppercase;
    letter-spacing:.09em;color:var(--muted);margin:22px 0 8px}}
  .note{{margin:0 0 8px;font-size:12px;color:var(--muted)}}
  ul{{margin:0;padding-left:18px;font-size:12px;color:var(--body)}}
  li{{margin-bottom:4px}}
  .stamp{{margin:16px 0 0;font:10px/1.45 system-ui,sans-serif;
    text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
    border-top:1px solid var(--hairline);padding-top:10px}}
</style>
<section class="panel">
<h2>{escape(COVERAGE_TITLE)}</h2>
<p class="sub">{escape(COVERAGE_SUBTITLE)}</p>
{caveats}
<p class="legend">{legend}</p>
<table>
<tr><th>Instrument</th><th>Subscales</th><th>Detail</th></tr>
{"".join(rows)}
</table>
<p class="summary">{escape(ledger.summary)}</p>
{prompt_block}
<p class="stamp">{escape(ledger.stamp)}</p>
</section>
"""
