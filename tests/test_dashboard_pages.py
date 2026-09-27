"""Honesty tests for the two-page app: the widget grid, the detail page, Page 2.

The grid is the riskiest surface this project has built. It shows numbers with
no explanation beside them, which is precisely the thing `ScoreSurface` was
introduced to make impossible, and the 0-100 band on Page 2 is a shape
`charts.py::risk_meter` explicitly refuses to draw. Both were asked for; both
are allowed only because a mechanism, not a convention, keeps them honest.

    (a) every page obeys the shell rules  -> the structural checks that used to
                                             cover `dashboard/app.py` alone now
                                             walk every file under `dashboard/`,
                                             because a second page is exactly
                                             where a rule scoped to one filename
                                             stops applying.
    (b) a widget cannot lose its stamp    -> required field, rejected empty, and
                                             asserted present on the page above
                                             any collapsible container.
    (c) a band cannot lose its caveat     -> required field, rejected empty, and
                                             `describe()` is the only rendering
                                             path the pages use.
    (d) bands never reach the figures     -> `charts.py` is asserted not to
                                             import `bands`, and no chart may
                                             contain a band label.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.dashboard import plain
from src.dashboard.backend import LexiconBackend, ReplayBackend
from src.dashboard.bands import BANDS, Band, band_for, score_from_view
from src.dashboard.benchmarks import load_benchmarks
from src.dashboard.charts import benchmark_chart, risk_meter
from src.dashboard.view import ForbiddenLanguage, build_view
from src.dashboard.widgets import Widget, widget_for, widgets_for

REPO_ROOT = Path(__file__).resolve().parents[1]
SHELL_DIR = REPO_ROOT / "dashboard"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"

LIVE_TEXT = "My hands will not stop shaking and I keep replaying the start in my head."


def _shell_files() -> list[Path]:
    files = sorted(p for p in SHELL_DIR.rglob("*.py") if "__pycache__" not in p.parts)
    assert len(files) >= 3, "expected an entry point and two pages under dashboard/"
    return files


@pytest.fixture(scope="module")
def view():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return build_view(example_id=backend.example_ids[0], backend=backend)


@pytest.fixture(scope="module")
def live_view():
    return build_view(text=LIVE_TEXT, backend=LexiconBackend())


# ---------------------------------------------------------------------------
# (a) every page is a renderer, not just the entry point
# ---------------------------------------------------------------------------


def test_every_page_reaches_the_project_only_through_src_dashboard():
    """A rule that named one file stopped protecting the app the moment it grew.

    Phase 20 wrote this check against `dashboard/app.py`. Adding `pages/` would
    have left two files free to import `src.risk` and compute their own numbers,
    with the suite still green -- the sixth instance of the defect shape, wearing
    a new filename.
    """
    for path in _shell_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src."):
                assert node.module.startswith("src.dashboard"), (
                    f"{path.name} imports {node.module}; a page may only reach the project "
                    "through src.dashboard, or business logic migrates into the files the "
                    "Streamlit runtime executes."
                )


def test_no_page_constructs_a_view_or_a_card_itself():
    forbidden = {"DashboardView", "ExplanationCard", "CardSet", "build_card", "LinearRiskScorer"}
    for path in _shell_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & forbidden), f"{path.name} constructs {called & forbidden}"


#: Pages exempted from the above-the-fold stamp rule, and why.
#:
#: app.py was exempted on 2026-09-14 on the owner's explicit instruction, after
#: the consequence was put to him: Phase 26 gate #3 no longer holds for page 1,
#: and a screenshot of the risk index taken from it travels without the sentence
#: that says the number is agreement with planted labels and is not accuracy.
#: The stamp still renders in that page's provenance expander.
#:
#: This is a list rather than a deleted test on purpose. The rule still protects
#: every other page, adding a name here is a visible act with a reason attached,
#: and an empty exemption list is the state to get back to.
STAMP_ABOVE_FOLD_EXEMPT: dict[str, str] = {
    "app.py": "owner instruction 2026-09-14; stamp retained in the expander",
}


def _expander_lines(tree: ast.Module) -> list[int]:
    """Lines where the page actually calls `st.expander`.

    Read off the syntax tree rather than grepped for, because the rule is about
    collapsible sections the page *renders*. Phase 34 added a page whose docstring
    explains why it deliberately has none, and a substring check failed it for
    saying so -- the rule and the thing it protects related by assumption, which is
    the defect shape this file already names four times. Prose about an API is not
    a call to it.
    """
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "expander"
    ]


def _stamp_lines(tree: ast.Module) -> list[int]:
    """Lines where the page reads a `.stamp` attribute off something.

    Matched on any `.stamp` access, not on `risk.stamp`. The rule was written when
    the only stamped surface was the risk score; Phase 26 added pages whose stamp
    comes off a `BiosignalWindow` or a source, and Phase 34 pages whose stamp comes
    off a `Ribbon` or a `CorpusCloud`. A rule scoped to one attribute name stops
    protecting the app the moment a second kind of stamped surface arrives.
    """
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "stamp"
    ]


def test_every_page_that_shows_a_number_shows_the_stamp_before_any_expander():
    """A stamp inside a collapsed expander is in the DOM and not on the screen."""
    for path in _shell_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        expanders = _expander_lines(tree)
        if not expanders:
            continue
        stamps = _stamp_lines(tree)
        if path.name in STAMP_ABOVE_FOLD_EXEMPT:
            # Exempt from the ORDERING rule only. The stamp must still be on the
            # page somewhere, or the exemption has quietly become a deletion.
            assert stamps, (
                f"{path.name} is exempt from rendering the stamp above the fold, "
                "but has dropped it from the page entirely"
            )
            continue
        assert stamps, f"{path.name} has collapsible sections and no stamp"
        assert min(stamps) < min(expanders), (
            f"{path.name} renders the provenance stamp only inside a collapsed expander"
        )


def test_no_page_source_contains_a_forbidden_string():
    from src.dashboard.view import assert_no_forbidden_language

    for path in _shell_files():
        assert_no_forbidden_language(path.read_text(encoding="utf-8"))


def test_the_design_specification_ships_with_the_repository():
    """The pages implement a documented system; the document is part of the repo."""
    spec = REPO_ROOT / "DESIGNcohere.md"
    assert spec.exists(), "DESIGNcohere.md is missing; the theme has no specification"
    text = spec.read_text(encoding="utf-8")
    from src.dashboard import theme

    for token in (theme.DEEP_GREEN, theme.CORAL, theme.SOFT_STONE, theme.INK):
        assert token in text, f"{token} is used by theme.py but absent from DESIGNcohere.md"


# ---------------------------------------------------------------------------
# (b) widgets
# ---------------------------------------------------------------------------


def test_there_is_one_widget_per_construct_and_it_shows_values_only(view):
    tiles = widgets_for(view)
    assert len(tiles) == len(view.bars) == 10
    assert {t.construct for t in tiles} == {b.construct for b in view.bars}
    for tile in tiles:
        # The grid is value-only by design; the words live on the detail page.
        assert tile.value
        assert tile.stamp


def test_a_widget_cannot_be_constructed_without_a_stamp(view):
    tile = widgets_for(view)[0]
    with pytest.raises(ValueError):
        Widget(
            construct=tile.construct,
            title=tile.title,
            value=tile.value,
            value_caption="",
            secondary="",
            secondary_caption="",
            inert=False,
            detected=True,
            stamp="   ",
        )


def test_widget_values_are_the_view_s_values_and_not_re_derived(view):
    by_construct = {b.construct: b for b in view.bars}
    for tile in widgets_for(view):
        bar = by_construct[tile.construct]
        assert tile.value == f"{bar.probability:.2f}"
        assert tile.inert is bar.inert
        if bar.inert:
            assert tile.secondary == "counted as zero"
        else:
            assert tile.secondary == f"{bar.contribution:+.3f}"


def test_an_inert_widget_says_so_without_relying_on_styling(view):
    inert = [t for t in widgets_for(view) if t.inert]
    assert len(inert) == 4
    for tile in inert:
        assert "zero" in f"{tile.secondary} {tile.secondary_caption}".lower()


def test_a_widget_can_only_open_its_own_construct(view):
    with pytest.raises(KeyError):
        widget_for(view, "not_a_construct")
    assert widget_for(view, "burnout_signal").construct == "burnout_signal"


# ---------------------------------------------------------------------------
# (c) the 0-100 score and its band
# ---------------------------------------------------------------------------


def test_the_score_is_the_index_times_one_hundred_and_nothing_else(view, live_view):
    for source in (view, live_view):
        score = score_from_view(source)
        assert score.score_100 == round(source.risk.value * 100)
        assert score.stamp == source.risk.stamp
        assert len(score.dimensions) == len(source.bars)


def test_a_band_cannot_be_constructed_without_its_caveat():
    with pytest.raises(ValueError):
        Band("Upper third of the scale", 67, 100, "")
    with pytest.raises(ValueError):
        Band("Upper third of the scale", 67, 100, "   ")


def test_a_band_label_is_never_rendered_without_the_caveat():
    """`describe()` is the only rendering path, and the pages use only it."""
    for band in BANDS:
        described = band.describe()
        assert band.label in described
        assert band.caveat in described
        assert "not severity levels" in described
    # The property over the pages: a file that puts a band *label* on screen must
    # also put `describe()` on screen. Matched on the attribute access, not on
    # the word "band", so prose about design bands in a comment cannot trip it
    # and a real rendering cannot slip past it.
    for path in _shell_files():
        source = path.read_text(encoding="utf-8")
        if ".band.label" not in source:
            continue
        assert ".band.describe()" in source, (
            f"{path.name} renders a band label; it must also render band.describe(), "
            "which carries the caveat"
        )


def test_the_bands_cover_the_whole_scale_with_no_gap_and_no_overlap():
    assert [b.lower for b in BANDS] == [0, 34, 67]
    assert [b.upper for b in BANDS] == [33, 66, 100]
    for value, expected in ((0, 0), (33, 0), (34, 1), (66, 1), (67, 2), (100, 2)):
        assert band_for(value) is BANDS[expected]
    # Out-of-range input clamps rather than falling through to no band.
    assert band_for(-5) is BANDS[0]
    assert band_for(140) is BANDS[-1]


def test_band_labels_describe_the_scale_not_a_person():
    """A band names a stretch of an uncalibrated ranking, so it may not carry a
    severity word. `docs/ethics.md` and charts.py::risk_meter both turn on this."""
    banned = ("mild", "moderate risk", "severe", "high risk", "low risk", "critical", "normal")
    for band in BANDS:
        low = band.label.lower()
        for term in banned:
            assert term not in low, f"band label {band.label!r} reads as a verdict"
        assert "third of the scale" in low


def test_the_scale_note_denies_the_percentage_reading():
    from src.dashboard.bands import SCALE_NOTE

    assert "not a percentage" in SCALE_NOTE
    assert "not a percentage" in plain.SCALE_NOTE_TEXT


def test_a_band_carrying_forbidden_language_cannot_be_constructed():
    with pytest.raises(ForbiddenLanguage):
        Band("Upper third", 67, 100, "validated against coach-validated thresholds")


# ---------------------------------------------------------------------------
# (d) the bands stay off the figures
# ---------------------------------------------------------------------------


def test_the_charts_module_does_not_import_the_bands_module():
    """The paper's meter is unbanded, and must stay that way.

    Asserted at the import graph rather than by inspecting output, because an
    import is the thing a future edit would add first.
    """
    tree = ast.parse((REPO_ROOT / "src" / "dashboard" / "charts.py").read_text(encoding="utf-8"))
    modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("bands" in (m or "") for m in modules)


def test_no_band_label_appears_in_any_figure(view):
    figures = [
        risk_meter(view.risk),
        benchmark_chart(load_benchmarks()),
    ]
    for figure in figures:
        for band in BANDS:
            assert band.label not in figure
        assert "not calibrated" in figure or "planted" in figure or "interval" in figure


# ---------------------------------------------------------------------------
# (e) two design languages, two modes, one route into the explanation
# ---------------------------------------------------------------------------


def test_the_two_design_languages_do_not_leak_into_each_other():
    """Page 2 runs DESIGNclaude.md; the dashboard runs DESIGNcohere.md.

    Asserted on the emitted stylesheets rather than on the source, because the
    failure mode is a token borrowed in one place, not an import.
    """
    from src.dashboard import theme

    dashboard_css = theme.app_css("light") + theme.app_css("dark")
    claude = theme.claude_css("light") + theme.claude_css("dark")

    for token in (theme.CLAUDE_PRIMARY, theme.CLAUDE_CANVAS, theme.CLAUDE_SURFACE_CARD):
        assert token not in dashboard_css, f"{token} is a Claude token on a Cohere surface"
    for token in (theme.DEEP_GREEN, theme.SOFT_STONE, theme.CORAL, theme.ACTION_BLUE):
        assert token not in claude, f"{token} is a Cohere token on the Claude page"


def test_only_the_score_page_uses_the_claude_language():
    for path in _shell_files():
        source = path.read_text(encoding="utf-8")
        uses_claude = "claude_css(" in source
        assert uses_claude == (path.name == "2_Score_my_own_text.py"), (
            f"{path.name} disagrees with the rule that the Claude language is Page 2 only"
        )


def test_both_design_specifications_ship_with_the_repository():
    for name in ("DESIGNcohere.md", "DESIGNclaude.md"):
        assert (REPO_ROOT / name).exists(), f"{name} is missing; a theme with no specification"


def test_every_mode_defines_every_token():
    """A half-filled mode is how a dark page ends up with dark text on dark.

    Checked for both design languages: Page 2 follows the same light/dark choice
    in its own tokens, so it has the same failure available to it.
    """
    from src.dashboard import theme

    for family in (theme.MODES, theme.CLAUDE_MODES):
        names = set(next(iter(family.values())))
        assert names, "a palette family is empty"
        for mode, tokens in family.items():
            assert set(tokens) == names, f"{mode} is missing {names - set(tokens)}"
            for key, value in tokens.items():
                assert value.startswith("#"), f"{mode}.{key} is not a colour"


def test_dark_mode_inverts_the_text_against_its_own_canvas():
    """Cheap contrast check: ink and canvas must sit on opposite sides of mid-grey.

    Not a full WCAG calculation -- a relative-luminance gap of this size is
    enough to catch the only failure that matters here, which is a mode that
    forgot to invert one of the pair.
    """
    from src.dashboard import theme

    def luminance(hex_colour: str) -> float:
        r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    families = {
        **{f"cohere-{m}": t for m, t in theme.MODES.items()},
        **{f"claude-{m}": t for m, t in theme.CLAUDE_MODES.items()},
    }
    for mode, tokens in families.items():
        gap = abs(luminance(tokens["ink"]) - luminance(tokens["canvas"]))
        assert gap > 0.5, f"{mode}: ink and canvas are too close ({gap:.2f})"
        body_gap = abs(luminance(tokens["body"]) - luminance(tokens["canvas"]))
        assert body_gap > 0.35, f"{mode}: body text is too close to the canvas"


def test_the_panel_surfaces_cover_every_mode_the_pages_ask_for():
    from src.dashboard import motion, theme

    for mode in (*theme.MODES, "claude", "claude-dark"):
        assert mode in motion._SURFACES, f"the panel has no surface for {mode!r}"
    names = set(motion._SURFACES["light"])
    for mode, tokens in motion._SURFACES.items():
        assert set(tokens) == names, f"panel surface {mode} is missing {names - set(tokens)}"


def test_the_explanation_page_is_reachable_only_by_opening_a_tile():
    """Requirement: no menu entry for the detail page.

    Two halves, both asserted: the nav entry is hidden by the stylesheet every
    page emits, and the entry point still routes to it, so hiding the link did
    not strand the page.
    """
    from src.dashboard import theme

    for css in (
        theme.app_css("light"),
        theme.app_css("dark"),
        theme.claude_css("light"),
        theme.claude_css("dark"),
    ):
        assert 'a[href*="Signal_detail"]{display:none}' in css

    entry = (SHELL_DIR / "app.py").read_text(encoding="utf-8")
    assert "st.switch_page(DETAIL_PAGE)" in entry
    assert "pages/1_Signal_detail.py" in entry


def test_the_widget_grid_is_evenly_spaced():
    """Tiles are equal-height and equally gapped, in both languages.

    A grid whose rows stagger reads as the tiles meaning different things, and
    the difference would only ever be a title that wrapped to two lines.
    """
    from src.dashboard import theme

    for css in (
        theme.app_css("light"),
        theme.app_css("dark"),
        theme.claude_css("light"),
        theme.claude_css("dark"),
    ):
        assert "min-height:" in css
        assert "justify-content:space-between" in css
        assert '[data-testid="stHorizontalBlock"]{gap:' in css


def test_page_two_follows_the_dashboard_appearance_in_its_own_language():
    """Dark mode reaches Page 2, expressed in Claude tokens rather than Cohere ones.

    Both halves matter. If the page ignored the mode, a reader who chose dark
    would hit a cream page on the one screen where they paste their own words.
    If it borrowed the dashboard's dark tokens instead, Page 2 would stop being
    the Claude surface the brief asked for.
    """
    from src.dashboard import theme

    source = (SHELL_DIR / "pages" / "2_Score_my_own_text.py").read_text(encoding="utf-8")
    assert 'st.session_state.get("mode"' in source, "Page 2 ignores the reader's choice"
    assert "theme.claude_css(mode)" in source
    assert "claude-dark" in source

    dark = theme.claude_css("dark")
    assert theme.CLAUDE_SURFACE_DARK in dark
    # Matched on the variable, not the hex: #faf9f5 is the cream canvas in light
    # mode AND the on-dark text colour in dark mode -- one hex, two roles. A bare
    # substring check would fail on the correct stylesheet.
    assert f"--c-canvas:{theme.CLAUDE_CANVAS}" not in dark, "the cream canvas survived"
    assert f"--c-canvas:{theme.CLAUDE_SURFACE_DARK}" in dark
    assert f"--c-canvas:{theme.CLAUDE_CANVAS}" in theme.claude_css("light")
    # The coral is the one token that does not move between surfaces.
    assert theme.CLAUDE_PRIMARY in dark
    for token in (theme.DARK["canvas"], theme.DARK["surface"], theme.DEEP_GREEN):
        assert token not in dark, "Page 2 borrowed the dashboard's dark tokens"


def test_the_mode_is_carried_in_a_key_that_survives_navigation():
    """Streamlit drops widget state for widgets the current page does not render.

    So the choice cannot live in the radio's own key: the reader picks dark on
    the dashboard, opens Page 2, and Streamlit has already discarded it. Every
    page must read the plain `mode` key, and the pages that offer the control
    must write it.
    """
    for path in _shell_files():
        source = path.read_text(encoding="utf-8")
        if "app_css(" not in source and "claude_css(" not in source:
            continue
        assert "st.session_state" in source and '"mode"' in source, (
            f"{path.name} does not read the persisted appearance key"
        )
        if "st.sidebar.radio" in source:
            assert 'st.session_state["mode"] =' in source, (
                f"{path.name} offers the control but never persists the choice"
            )


# ---------------------------------------------------------------------------
# (f) Phase 26 — the cognitive pages, and the two halves of their feature flag
#
# `_shell_files()` already rglobs `dashboard/`, so every rule above walks the new
# pages with no change -- which was the point of writing it that way in Phase 20
# and is why this section adds rules rather than widening a walk.
#
# What it adds is the flag. `.claude.md` §11.3 says the Phase 26 pages "are not
# registered" when `SRN_COGNITIVE_LAYER` is unset. They are: Streamlit registers
# every file under `pages/` unconditionally and offers no API for a conditional
# page, so the spec as written is unbuildable. The rule that IS buildable has two
# halves, and neither is sufficient alone:
#
#   * the stylesheet hides the nav entries, and
#   * each page stops before its first `src.` import.
#
# Hiding alone leaves the pages reachable by URL. Stopping alone leaves three
# dead links in the menu. Both are asserted below, because a rule whose halves
# are related by assumption is the defect shape this repository has now found
# seven times.
# ---------------------------------------------------------------------------

COGNITIVE_PAGES = ("3_Brain_atlas.py", "4_Cognitive_load.py", "5_Neurofeedback_demo.py")


def _cognitive_shell_files() -> list[Path]:
    return [p for p in _shell_files() if p.name in COGNITIVE_PAGES]


def test_every_cognitive_page_checks_the_flag_before_it_loads_the_layer():
    """The check has to precede the import, or the import happens anyway.

    The rule used to say "before ANY src. import", and that was too strong once
    the gate itself needed `theme` to decide what the flag means. What actually
    matters is narrower and is what the flag was always for: `src/biosignals`
    must not load when the layer is off. So the assertion is on the modules that
    reach it -- `biosources` and `neurovis` -- rather than on the first `src.`
    line in the file.

    Asserted on line numbers in the parsed source because the failure is silent:
    the page still renders correctly, it has just imported a package it promised
    not to touch.
    """
    pages = _cognitive_shell_files()
    assert pages, "no cognitive pages found; this section is asserting nothing"
    for path in pages:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        guards = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "cognitive_layer_enabled"
        ]
        assert guards, f"{path.name} never calls theme.cognitive_layer_enabled()"
        layer_imports = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(part in (node.module or "") for part in ("biosources", "neurovis"))
        ]
        assert layer_imports, f"{path.name} imports no part of the cognitive layer"
        assert min(guards) < min(layer_imports), (
            f"{path.name} loads the cognitive layer on line {min(layer_imports)} before "
            f"it checks the flag on line {min(guards)}"
        )


def test_no_cognitive_page_parses_the_flag_itself():
    """One rule, one place. Two copies of a rule are two rules."""
    from src.dashboard import theme

    for path in _cognitive_shell_files():
        source = path.read_text(encoding="utf-8")
        assert "os.getenv" not in source, (
            f"{path.name} parses the flag itself instead of asking theme, so the page "
            "and the nav-hiding stylesheet can disagree about what the flag means"
        )
        assert f'"{theme.COGNITIVE_FLAG}"' not in source


def test_importing_the_dashboard_does_not_load_the_biosignal_layer():
    """The property the flag exists to deliver, checked for real rather than by
    reading the source: a fresh interpreter that imports `src.dashboard` must not
    end up with `src.biosignals` in sys.modules."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import src.dashboard; print('src.biosignals' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False", (
        "importing src.dashboard pulled in src.biosignals; the feature flag can no "
        "longer keep the layer out of a run that did not ask for it"
    )


def test_the_stylesheet_hides_the_cognitive_nav_entries_only_when_disabled():
    """The other half. Both directions, because a rule that always hides strands
    the pages and one that never hides is no rule at all.

    The layer is ON by default, so the interesting case is the explicit off
    value rather than the unset one -- see theme.cognitive_layer_enabled for why
    the default was inverted after the off state was mistaken for a bug three
    times running.
    """
    import os

    from src.dashboard import theme

    previous = os.environ.pop(theme.COGNITIVE_FLAG, None)
    try:
        for value in ("", "1", "yes"):
            os.environ[theme.COGNITIVE_FLAG] = value
            shown = theme.app_css("light") + theme.claude_css("light")
            for page in theme.COGNITIVE_PAGES:
                assert page not in shown, f"{page} is hidden with the layer on ({value!r})"
        del os.environ[theme.COGNITIVE_FLAG]
        unset = theme.app_css("light")
        for page in theme.COGNITIVE_PAGES:
            assert page not in unset, f"{page} is hidden when the flag is unset"
        for value in ("0", "false", "off", "no"):
            os.environ[theme.COGNITIVE_FLAG] = value
            hidden = theme.app_css("light") + theme.claude_css("light")
            for page in theme.COGNITIVE_PAGES:
                assert page in hidden, f"{page} is still in the menu with the layer off"
        # The Phase 20 rule is untouched in every state.
        for css in (unset, hidden):
            assert 'a[href*="Signal_detail"]{display:none}' in css
    finally:
        os.environ.pop(theme.COGNITIVE_FLAG, None)
        if previous is not None:
            os.environ[theme.COGNITIVE_FLAG] = previous


def test_no_cognitive_page_uses_the_claude_language():
    """Covered by `test_only_the_score_page_uses_the_claude_language` above; kept
    as a named case so the intent survives a refactor of that test."""
    for path in _cognitive_shell_files():
        assert "claude_css(" not in path.read_text(encoding="utf-8")


def test_the_compose_dashboard_service_passes_the_cognitive_flag():
    """The flag has to reach the container, not just the shell.

    This test exists because of a real failure. `SRN_COGNITIVE_LAYER` was
    documented in `.env.example`, the three pages were on disk, every test was
    green -- and the running dashboard showed two menu entries, because
    `docker compose` reads `.env` rather than the shell that typed `set`, and the
    nav-hiding rule then did exactly what it was written to do. The off state of
    a correct guard was indistinguishable from the feature not existing.

    Asserted on the compose file rather than on behaviour because that is where
    the gap was: nothing in the Python could see it.
    """
    from src.dashboard import theme

    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dashboard = compose[compose.index("  dashboard:") : compose.index("  train:")]
    assert theme.COGNITIVE_FLAG in dashboard, (
        "docker-compose.yml does not pass SRN_COGNITIVE_LAYER to the dashboard "
        "service, so the Phase 26 pages hide themselves in every containerised run"
    )
    assert "${" + theme.COGNITIVE_FLAG in dashboard, (
        "the flag is hardcoded rather than substituted; a reader cannot turn the "
        "layer off without editing the compose file"
    )


def test_the_entry_point_says_why_the_cognitive_pages_are_missing():
    """A guard whose off-state looks like a bug is a guard that gets ripped out.

    Still worth saying even now the layer defaults on, because somebody who sets
    the flag to 0 in a `.env` six months from now will otherwise meet the same
    silently-missing menu that cost three rounds of debugging.
    """
    from src.dashboard import theme

    entry = (SHELL_DIR / "app.py").read_text(encoding="utf-8")
    assert "cognitive_layer_enabled()" in entry
    assert "st.sidebar.caption" in entry
    # The flag NAME is interpolated from `theme.COGNITIVE_FLAG` rather than
    # typed, so the literal is deliberately absent from the page source -- a
    # renamed flag must not leave a stale name in a caption telling somebody to
    # set a variable that no longer exists.
    assert "theme.COGNITIVE_FLAG" in entry
    assert theme.COGNITIVE_FLAG == "SRN_COGNITIVE_LAYER"


def test_no_cognitive_page_prints_a_heading_its_panel_already_carries():
    """Each panel is a self-contained document with its own title and lede, so a
    shell that prints them too shows the same headline twice, stacked.

    Found by loading the running app; both halves were individually correct, so
    nothing in the suite could see it. Matched on the copy constants rather than
    on the rendered text, because that is what a page would actually reach for.
    """
    for path in _cognitive_shell_files():
        source = path.read_text(encoding="utf-8")
        for constant in ("ATLAS_TITLE", "LOAD_TITLE", "NF_TITLE", "theme.lede("):
            assert constant not in source, (
                f"{path.name} renders {constant}, which its panel already renders"
            )
