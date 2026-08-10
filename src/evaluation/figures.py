"""Figures for the Phase 9 report, written as SVG by hand.

Why not matplotlib
------------------
matplotlib is not in `requirements-base.txt` and adding it would put a plotting
stack into the light Docker image that every agent service pulls, to draw six
bar charts. `CLAUDE.md` §8.6 and the Phase 2 layering decision both point the
other way: the light image exists so the agent layer stays small, and a
dependency added for a figure is a dependency the whole pipeline then carries.

SVG is the right target for this project specifically:

* it renders inline in GitHub markdown, so `reports/eda.md` is readable in the
  browser with no build step;
* it is text, so `git diff` on a figure is meaningful and a regenerated figure
  with unchanged data produces an empty diff -- a binary PNG would show a diff
  every time regardless;
* it is vector, so the same file goes into the IEEE LaTeX build at any column
  width without resampling.

The cost is that this module hand-rolls axis layout, and it is deliberately
plain: no gridlines, no styling beyond what carries information. If Phase 18
needs publication figures with error bars and multiple series, that is the
point to reach for matplotlib in the ML layer, not now.

Everything here is deterministic: same numbers in, byte-identical SVG out.
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from pathlib import Path

#: Deliberately restrained. One ink colour plus a muted one for context, so the
#: figures survive greyscale printing -- an IEEE reviewer may well print them.
_INK = "#1f3a5f"
_MUTED = "#9bb0c7"
_TEXT = "#222222"
_FONT = "font-family='Helvetica,Arial,sans-serif'"


def _svg(width: int, height: int, body: str) -> str:
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' role='img'>\n"
        f"<rect width='{width}' height='{height}' fill='white'/>\n"
        f"{body}"
        "</svg>\n"
    )


def _title(text: str, width: int) -> str:
    return (
        f"<text x='{width // 2}' y='22' text-anchor='middle' {_FONT} font-size='14' "
        f"font-weight='bold' fill='{_TEXT}'>{escape(text)}</text>\n"
    )


def bar_chart(
    labels: Sequence[str],
    values: Sequence[float],
    title: str,
    *,
    width: int = 720,
    bar_height: int = 22,
    label_width: int = 190,
    value_format: str = "{:.0f}",
) -> str:
    """Horizontal bars. Horizontal because the labels are words, not numbers.

    Vertical bars would need rotated tick labels for `time_to_competition` bands
    and sport names, and rotated labels are the single most common reason a
    reviewer cannot read a figure at print size.
    """
    n = len(labels)
    top, bottom, gap = 40, 30, 6
    height = top + n * (bar_height + gap) + bottom
    plot_width = width - label_width - 90
    peak = max(values) if values and max(values) > 0 else 1.0

    parts = [_title(title, width)]
    for index, (label, value) in enumerate(zip(labels, values, strict=False)):
        y = top + index * (bar_height + gap)
        length = plot_width * (value / peak)
        parts.append(
            f"<text x='{label_width - 8}' y='{y + bar_height - 6}' text-anchor='end' "
            f"{_FONT} font-size='12' fill='{_TEXT}'>{escape(str(label))}</text>\n"
            f"<rect x='{label_width}' y='{y}' width='{length:.2f}' height='{bar_height}' "
            f"fill='{_INK}'/>\n"
            f"<text x='{label_width + length + 6:.2f}' y='{y + bar_height - 6}' "
            f"{_FONT} font-size='11' fill='{_TEXT}'>"
            f"{escape(value_format.format(value))}</text>\n"
        )
    return _svg(width, height, "".join(parts))


def histogram_chart(
    bins: Sequence[tuple[float, float, int]],
    title: str,
    x_label: str,
    *,
    width: int = 720,
    height: int = 320,
) -> str:
    """Vertical histogram over `(low, high, count)` bins from `profile.histogram`.

    Only every other bin edge is labelled. With twelve bins and four-digit
    counts the labels collide otherwise, and a collided axis is worse than a
    sparse one.
    """
    left, right, top, bottom = 60, 20, 40, 56
    plot_w = width - left - right
    plot_h = height - top - bottom
    peak = max((count for _, _, count in bins), default=1) or 1
    bar_w = plot_w / len(bins) if bins else plot_w

    parts = [_title(title, width)]
    parts.append(
        f"<line x1='{left}' y1='{top + plot_h}' x2='{left + plot_w}' y2='{top + plot_h}' "
        f"stroke='{_TEXT}' stroke-width='1'/>\n"
        f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top + plot_h}' "
        f"stroke='{_TEXT}' stroke-width='1'/>\n"
        f"<text x='{left - 8}' y='{top + 10}' text-anchor='end' {_FONT} font-size='10' "
        f"fill='{_TEXT}'>{peak}</text>\n"
        f"<text x='{left - 8}' y='{top + plot_h}' text-anchor='end' {_FONT} font-size='10' "
        f"fill='{_TEXT}'>0</text>\n"
        f"<text x='{left + plot_w / 2:.0f}' y='{height - 10}' text-anchor='middle' {_FONT} "
        f"font-size='11' fill='{_TEXT}'>{escape(x_label)}</text>\n"
    )
    for index, (low, _high, count) in enumerate(bins):
        bar_h = plot_h * (count / peak)
        x = left + index * bar_w
        parts.append(
            f"<rect x='{x:.2f}' y='{top + plot_h - bar_h:.2f}' width='{bar_w - 2:.2f}' "
            f"height='{bar_h:.2f}' fill='{_INK}'/>\n"
        )
        if index % 2 == 0:
            parts.append(
                f"<text x='{x:.2f}' y='{top + plot_h + 14}' text-anchor='middle' {_FONT} "
                f"font-size='10' fill='{_TEXT}'>{low:.0f}</text>\n"
            )
    return _svg(width, height, "".join(parts))


def grouped_bar_chart(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float]]],
    title: str,
    *,
    width: int = 720,
    row_height: int = 30,
    label_width: int = 190,
) -> str:
    """Two series per label. Used for the corpus-vs-gold-sample comparison.

    Two only, and the type signature does not stop you passing more because
    stopping you would be more code than it saves -- but the colour ramp has two
    distinguishable steps in greyscale and no more.
    """
    n = len(labels)
    top, bottom = 40, 40
    height = top + n * row_height + bottom
    plot_width = width - label_width - 90
    peak = max((max(values) for _, values in series if values), default=1.0) or 1.0
    colours = [_INK, _MUTED]
    sub_h = (row_height - 8) / max(1, len(series))

    parts = [_title(title, width)]
    for index, label in enumerate(labels):
        y0 = top + index * row_height
        parts.append(
            f"<text x='{label_width - 8}' y='{y0 + row_height / 2 + 4:.0f}' text-anchor='end' "
            f"{_FONT} font-size='12' fill='{_TEXT}'>{escape(str(label))}</text>\n"
        )
        for s_index, (_name, values) in enumerate(series):
            value = values[index] if index < len(values) else 0.0
            length = plot_width * (value / peak)
            y = y0 + s_index * sub_h
            parts.append(
                f"<rect x='{label_width}' y='{y:.2f}' width='{length:.2f}' "
                f"height='{sub_h - 2:.2f}' fill='{colours[s_index % len(colours)]}'/>\n"
            )
    for s_index, (name, _values) in enumerate(series):
        parts.append(
            f"<rect x='{label_width + s_index * 150}' y='{height - 24}' width='12' height='12' "
            f"fill='{colours[s_index % len(colours)]}'/>\n"
            f"<text x='{label_width + s_index * 150 + 18}' y='{height - 14}' {_FONT} "
            f"font-size='11' fill='{_TEXT}'>{escape(name)}</text>\n"
        )
    return _svg(width, height, "".join(parts))


def write(path: Path, svg: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return path
