"""Honesty tests for the cognitive layer's rendered surfaces. Phase 26 / V1.

The atlas is the highest misreading risk this project has built. A coloured
brain network is read as a scan in a fraction of a second, before any caption,
and this one is drawn from a lexicon reading synthetic text. So the properties
below are not style checks -- each one is a specific false reading being made
impossible:

    (a) the file cannot claim what it does not have  -> atlas_map refuses a row
                                                        whose evidence status is
                                                        missing, and refuses any
                                                        number in the YAML
    (b) the surface cannot speak like a scan         -> the activation screen,
                                                        matched on word
                                                        boundaries, over the
                                                        whole rendered document
    (c) the figure introduces no number              -> node radius is an affine
                                                        function of one value the
                                                        view already carries, and
                                                        the test inverts the
                                                        shipped function
    (d) inert and unmapped survive greyscale         -> three channels each, as
                                                        charts.py already requires
    (e) the panel needs no network to render         -> no script, no font file,
                                                        no external reference
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

import pytest
import yaml

from src.dashboard import neurovis, plain
from src.dashboard.atlas_map import (
    EVIDENCE_SHORT,
    EVIDENCE_STATES,
    AtlasError,
    AtlasRow,
    load_atlas,
)
from src.dashboard.backend import ReplayBackend
from src.dashboard.view import build_view
from src.dashboard.widgets import atlas_widget

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"
ATLAS_PATH = REPO_ROOT / "config" / "brain_atlas.yaml"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"
REFS_PATH = REPO_ROOT / "paper" / "refs.bib"

MODES = ("light", "dark")


@pytest.fixture(scope="module")
def view():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return build_view(example_id=backend.example_ids[0], backend=backend)


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


@pytest.fixture(scope="module", params=MODES)
def panel(request, view):
    return neurovis.atlas_panel(view, mode=request.param)


# ---------------------------------------------------------------------------
# (a) the file cannot claim what it does not have
# ---------------------------------------------------------------------------


def test_every_taxonomy_construct_has_a_row_or_is_explicitly_unmapped(atlas):
    taxonomy = set(yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["constructs"])
    assert {row.construct for row in atlas.rows} == taxonomy
    assert atlas.mapped and atlas.unmapped, (
        "a file with nothing unmapped is a file that found a region for every "
        "construct, which is the outcome this project is least entitled to"
    )


def test_every_row_anchors_to_a_key_that_resolves_in_refs_bib(atlas):
    keys = set(re.findall(r"^@\w+\{([^,]+),", REFS_PATH.read_text(encoding="utf-8"), re.M))
    for row in atlas.rows:
        assert row.instrument_anchor in keys, f"{row.construct}: {row.instrument_anchor}"


def test_the_anchor_is_never_presented_as_supporting_the_region(atlas, panel):
    """The whole reason this file has two fields instead of one.

    `instrument_anchor` supports the construct -- it is the questionnaire the
    construct came from. Raedeke2001 is the Athlete Burnout Questionnaire;
    Raedeke wrote nothing about the cingulate cortex. A panel that printed the
    anchor beside a region with no further qualification would be claiming he
    did, and that claim would be invisible to every other test in this file.
    """
    for row in atlas.mapped:
        assert row.network_evidence in EVIDENCE_STATES
        assert row.evidence_short in EVIDENCE_SHORT.values()
    assert plain.ATLAS_ANCHOR_NOTE in panel
    assert "says nothing about the part of the brain" in panel
    # Every evidence state that appears in the file is spelled out in full
    # somewhere on the surface, not only in its abbreviated cell form.
    for row in atlas.mapped:
        assert row.evidence_note in panel


def test_no_evidence_state_claims_a_source_this_repository_does_not_have():
    """Both permitted states are admissions. A third would need a real source.

    Asserted on the state table rather than on the YAML so that adding a value
    that names evidence requires editing this list and meeting this test, rather
    than typing a new string into a config file and being accepted because the
    field was non-empty.
    """
    assert set(EVIDENCE_STATES) == {"none_in_repository", "outside_athlete_population"}
    for note in EVIDENCE_STATES.values():
        assert neurovis.ATLAS_CAVEAT_TEXT in note


def test_the_atlas_file_carries_no_number(atlas):
    """Node size comes from the view or it does not come at all."""
    raw = yaml.safe_load(ATLAS_PATH.read_text(encoding="utf-8"))
    for key, section in raw.items():
        if key in ("version", "phase"):
            continue
        _assert_no_numbers(section, key)


def _assert_no_numbers(node, path):
    if isinstance(node, bool):
        return
    assert not isinstance(node, (int, float)), f"number at {path}: {node!r}"
    if isinstance(node, dict):
        for k, v in node.items():
            _assert_no_numbers(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _assert_no_numbers(v, f"{path}[{i}]")


def test_a_mapped_row_cannot_be_built_without_an_evidence_state():
    with pytest.raises(AtlasError, match="network_evidence"):
        AtlasRow(
            construct="cognitive_anxiety",
            unmapped=False,
            regions=("dorsal_acc",),
            networks=("cingulo_opercular",),
            instrument_anchor="Martens1990",
            network_evidence="",
            rationale="anything",
        )
    with pytest.raises(AtlasError, match="network_evidence"):
        AtlasRow(
            construct="cognitive_anxiety",
            unmapped=False,
            regions=("dorsal_acc",),
            networks=("cingulo_opercular",),
            instrument_anchor="Martens1990",
            network_evidence="well_established",  # the value somebody will try
            rationale="anything",
        )


def test_a_row_cannot_be_built_without_an_anchor_or_a_rationale():
    with pytest.raises(AtlasError, match="instrument_anchor"):
        AtlasRow(
            "x", False, ("dorsal_acc",), ("cingulo_opercular",), "  ", "none_in_repository", "r"
        )
    with pytest.raises(AtlasError, match="rationale"):
        AtlasRow(
            "x",
            False,
            ("dorsal_acc",),
            ("cingulo_opercular",),
            "Martens1990",
            "none_in_repository",
            "",
        )
    with pytest.raises(AtlasError, match="reason"):
        AtlasRow("x", True, (), (), "Martens1990", "", "")


def test_an_unmapped_row_cannot_smuggle_in_a_region():
    with pytest.raises(AtlasError, match="unmapped"):
        AtlasRow("x", True, ("dorsal_acc",), (), "Martens1990", "", "reason")


def test_edges_are_derived_from_the_file_and_not_drawn_by_hand(atlas):
    """A hand-drawn edge survives a mapping change and asserts a stale link."""
    for a, b, network in atlas.edges():
        assert network in atlas.row(a).networks
        assert network in atlas.row(b).networks
    assert atlas.edges(), "the mapping shares no network at all; the figure has no edges"


# ---------------------------------------------------------------------------
# (b) the surface cannot speak like a scan
# ---------------------------------------------------------------------------


def test_the_panel_states_the_caveat_as_text_in_both_modes(panel):
    assert panel.count(neurovis.ATLAS_CAVEAT_TEXT) >= 2, (
        "the caveat appears before the figure and again under it; one of the two "
        "is missing, and the one under the figure is the one that survives a crop"
    )


def test_the_caveat_precedes_the_figure_in_document_order(panel):
    """Same ordering rule as the provenance stamp above an expander."""
    assert panel.index(neurovis.ATLAS_CAVEAT_TEXT) < panel.index("<svg")


def test_the_caveat_is_not_only_a_tooltip(panel):
    """A title attribute is not in a screenshot, and a screenshot is the artefact."""
    body = re.sub(r'title="[^"]*"', "", panel)
    body = re.sub(r"<title>.*?</title>", "", body, flags=re.S)
    body = re.sub(r'aria-label="[^"]*"', "", body)
    assert neurovis.ATLAS_CAVEAT_TEXT in body


def test_the_panel_carries_no_activation_vocabulary(panel):
    neurovis.assert_no_activation_vocabulary(panel)
    for word in ("activation", "fmri"):
        assert word not in panel.lower()


def test_the_activation_screen_is_word_bounded_not_substring():
    """Both directions asserted, because both mistakes are available here.

    Too loose and the screen fires on "physical activity" and gets relaxed by
    the next person; too tight and "brain activity" walks through. This is the
    opposite choice from `view.assert_no_forbidden_language`, whose docstring
    argues for substring matching -- so the difference is pinned here, or one
    gets "fixed" to match the other.
    """
    for bad in ("brain activity", "peak activation", "the region activated", "measured at rest"):
        with pytest.raises(neurovis.ActivationVocabulary):
            neurovis.assert_no_activation_vocabulary(bad)
    for fine in ("physical activities", "a proactive routine", "inactivity was noted"):
        neurovis.assert_no_activation_vocabulary(fine)


def test_every_atlas_copy_string_survives_both_screens():
    """`copy._screen()` runs the forbidden-language screen at import; it does not
    run the activation screen, because `copy` cannot import `neurovis` without a
    cycle. So the second screen is applied here, over the same strings."""
    for name in dir(plain):
        if not name.startswith("ATLAS_"):
            continue
        value = getattr(plain, name)
        chunks = [value] if isinstance(value, str) else [s for pair in value for s in pair]
        for chunk in chunks:
            neurovis.assert_no_activation_vocabulary(chunk)


def test_the_panel_carries_no_forbidden_language(panel):
    from src.dashboard.view import assert_no_forbidden_language

    assert_no_forbidden_language(panel)


# ---------------------------------------------------------------------------
# (c) the figure introduces no number the view does not carry
# ---------------------------------------------------------------------------


def test_node_radius_inverts_to_the_views_probability_to_three_places(view, atlas):
    """The testable form of "the panel introduces no number".

    Parsed out of the rendered SVG and pushed back through the shipped inverse,
    so this checks the figure rather than checking the formula against itself.
    """
    document = neurovis.atlas_panel(view, mode="light")
    radii = [float(r) for r in re.findall(r'<circle [^>]*\br="([0-9.]+)"', document)]
    drawn = {row.construct for row in atlas.mapped}
    expected = sorted(round(bar.probability, 3) for bar in view.bars if bar.construct in drawn)
    assert sorted(round(neurovis.probability_from_radius(r), 3) for r in radii) == expected


def test_no_node_is_labelled_with_a_value(view):
    """A node shows a name. The two numbers live in the table under the figure,
    where they are attached to the row that says what does and does not back
    them -- not floating beside a circle where they read as a reading."""
    document = neurovis.atlas_panel(view, mode="light")
    svg = document[document.index("<svg") : document.index("</svg>")]
    for text in re.findall(r"<text[^>]*>(.*?)</text>", svg, flags=re.S):
        assert not re.search(r"\d", text), f"a node caption carries a number: {text!r}"


def test_the_panel_shows_no_construct_the_view_does_not_have(view, atlas):
    present = {bar.construct for bar in view.bars}
    for row in atlas.rows:
        assert row.construct in present


# ---------------------------------------------------------------------------
# (d) inert and unmapped survive greyscale and a colour-blind reader
# ---------------------------------------------------------------------------


def test_an_inert_construct_keeps_three_channels(view, panel, atlas):
    """Hatch, dash, and the literal word -- as `charts.py` already requires.

    Colour alone fails a greyscale print, which `PROJECT_PLAN.md` Phase 24 gates
    on, and it fails a colour-blind reader in any medium.
    """
    inert = [b for b in view.bars if b.inert and not atlas.row(b.construct).unmapped]
    assert inert, "the fixture has no inert construct; this test proves nothing"
    assert "url(#srn-atlas-hatch)" in panel
    assert "stroke-dasharray" in panel
    assert "counted as zero" in panel


def test_an_unmapped_construct_says_the_word_and_is_listed(panel, atlas):
    assert "unmapped" in panel
    for row in atlas.unmapped:
        name = plain.CONSTRUCTS[row.construct][0]
        assert name in panel
        assert " ".join(row.rationale.split())[:60] in panel


def test_the_hatch_pattern_id_is_namespaced(panel):
    """charts.py records a defect where two figures on one page shared a pattern
    id and the second silently took the first one's fill. Same page, same risk."""
    assert 'id="srn-atlas-hatch"' in panel


def test_every_legend_swatch_has_a_matching_rule(panel):
    """The legend rendered four captions with no swatches for two revisions.

    The class was derived from the caption's first word, producing `sw-hollow,`,
    and every unit test stayed green because the strings were all in the
    document. Only the screenshot showed it. This asserts the join the renderer
    actually relies on.
    """
    used = set(re.findall(r'class="sw sw-([a-z-]+)"', panel))
    assert used == {key for _text, key in plain.ATLAS_LEGEND}
    for key in used:
        assert f".sw-{key}{{" in panel, f"legend swatch .sw-{key} has no rule"


# ---------------------------------------------------------------------------
# (e) the panel needs nothing from the network
# ---------------------------------------------------------------------------


def test_the_figure_is_pure_svg_with_no_script_and_no_font_file(view):
    """The defect `motion.py` records: a blocked CDN left the card empty while
    every unit test stayed green. This panel has no module to fail."""
    document = neurovis.atlas_panel(view, mode="light")
    svg = document[document.index("<svg") : document.index("</svg>")]
    for forbidden in ("<script", "xlink:href", "<image", "url(http", "@import"):
        assert forbidden not in svg
    assert "font-family" not in svg, (
        "the SVG names no font: with the webfont blocked it must fall back "
        "silently rather than render in a face the panel never chose"
    )


def test_the_panel_renders_in_every_mode_the_dashboard_offers(view):
    from src.dashboard import motion, theme

    for mode in (*theme.MODES, "claude", "claude-dark"):
        assert mode in motion._SURFACES
        document = neurovis.atlas_panel(view, mode=mode)
        assert "<svg" in document and neurovis.ATLAS_CAVEAT_TEXT in document


def test_the_two_modes_differ_and_neither_borrows_the_other_s_ink(view):
    from src.dashboard import theme

    light = neurovis.atlas_panel(view, mode="light")
    dark = neurovis.atlas_panel(view, mode="dark")
    assert light != dark
    assert f"--ink:{theme.INK}" in light
    assert f"--ink:{theme.DARK['ink']}" in dark
    assert theme.DEEP_GREEN not in dark, (
        "deep green is invisible on navy; motion._SURFACES substitutes its light "
        "sibling and the atlas must inherit that rather than re-introduce it"
    )


def test_the_declared_iframe_height_clears_the_rendered_panel(view):
    """An iframe does not grow to its content, so a short height silently crops.

    The floor is derived the way the constant was: the panel measured 2389 CSS
    pixels at 900px wide with this fixture. What gets cropped is the bottom of
    the panel, which is exactly where the evidence table and the unmapped list
    live -- the honesty material, removed from the page by an arithmetic slip.
    """
    assert neurovis.atlas_height(view) >= 2128


# ---------------------------------------------------------------------------
# the summary tile
# ---------------------------------------------------------------------------


def test_the_summary_tile_counts_the_file_and_not_the_picture(view, atlas):
    """A count taken off the rendered figure agrees with the figure by
    construction, so it could never catch the figure being wrong."""
    tile = atlas_widget(view)
    assert tile.value == f"{len(atlas.mapped)} of {len(atlas.rows)}"
    assert tile.stamp == view.risk.stamp


def test_the_summary_tile_cannot_lose_its_stamp(view):
    tile = atlas_widget(view)
    assert tile.stamp.strip()


def test_the_summary_tile_uses_no_band_or_threshold_language(view):
    tile = atlas_widget(view)
    text = " ".join(
        (tile.title, tile.value, tile.value_caption, tile.secondary, tile.secondary_caption)
    ).lower()
    for banned in ("low", "moderate", "high", "elevated", "severe", "normal"):
        assert not re.search(rf"\b{banned}\b", text), f"{banned!r} reads as a band label"


# ---------------------------------------------------------------------------
# (f) the simulation
# ---------------------------------------------------------------------------


def test_the_simulator_only_ever_replays_states_the_fixture_already_holds(view):
    """The Play control moves the figure. It must not be able to move it to a
    state no committed example produced -- that would be a picture of an athlete
    who does not exist, animated smoothly enough to look like a recording."""
    import json

    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    views = [build_view(example_id=e, backend=backend) for e in backend.example_ids]
    document = neurovis.atlas_panel(views[0], mode="light", frames=views)
    payload = json.loads(
        document[document.index("var D = ") + 8 : document.index(";\n  var i = 0")]
    )
    assert len(payload["frames"]) == len(views)
    for frame, source in zip(payload["frames"], views, strict=True):
        assert frame["label"] == source.card.record_id
        assert frame["text"] == source.card.text
        for bar in source.bars:
            assert frame["rows"][bar.construct]["p"] == round(bar.probability, 4)
            assert frame["rows"][bar.construct]["c"] == round(bar.contribution, 4)


def test_the_panel_is_the_static_figure_with_the_script_removed(view):
    """Classic-script-first, the pattern motion.py records: the server paints
    frame zero into the SVG, so a script that never runs costs the Play button
    and nothing else. Asserted by deleting the script and checking the figure,
    the caveat and the evidence table are all still there."""
    import re as _re

    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    views = [build_view(example_id=e, backend=backend) for e in backend.example_ids]
    document = neurovis.atlas_panel(views[0], mode="light", frames=views)
    without = _re.sub(r"<script>.*?</script>", "", document, flags=_re.S)
    assert "<script" not in without
    assert neurovis.ATLAS_CAVEAT_TEXT in without
    assert without.count('circle class="nd"') == len(load_atlas().mapped)
    radii = [float(r) for r in _re.findall(r'<circle [^>]*\br="([0-9.]+)"', without)]
    drawn = {row.construct for row in load_atlas().mapped}
    assert sorted(round(neurovis.probability_from_radius(r), 3) for r in radii) == sorted(
        round(b.probability, 3) for b in views[0].bars if b.construct in drawn
    )


def test_the_simulator_script_reaches_no_network(view):
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    views = [build_view(example_id=e, backend=backend) for e in backend.example_ids]
    document = neurovis.atlas_panel(views[0], mode="light", frames=views)
    # Scoped to the script. The SVG's xmlns is a namespace identifier, not a
    # URL anything fetches, and a document-wide check fails on it -- which is
    # how this kind of test gets deleted instead of fixed.
    script = document[document.index("<script>") : document.index("</script>")]
    for forbidden in ("import ", "fetch(", "http://", "https://", "XMLHttpRequest"):
        assert forbidden not in script, f"the simulator reaches for {forbidden!r}"
    # The stylesheet's webfont <link> stays: it is the same one every other
    # panel loads, and the figure is built not to need it (the SVG names no
    # font at all -- see the pure-SVG test above). A blocked font costs the
    # typeface and nothing else.


def test_the_panel_without_frames_is_unchanged(view):
    """A caller that passes no frames gets exactly the figure it got before."""
    document = neurovis.atlas_panel(view, mode="light")
    import json as _json

    payload = _json.loads(
        document[document.index("var D = ") + 8 : document.index(";\n  var i = 0")]
    )
    assert len(payload["frames"]) == 1


# ---------------------------------------------------------------------------
# (g) V3 - the cognitive-load panel
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def windows():
    from src.biosignals import SimulatedCardioOculoSource

    return SimulatedCardioOculoSource(seed=20260913).stream(8)


@pytest.fixture(scope="module", params=MODES)
def load_doc(request, windows):
    return neurovis.load_panel(windows[0], mode=request.param, frames=windows)


def test_the_load_panel_renders_its_stamp_before_any_trace(load_doc):
    """A simulated trace with its provenance below the fold is a recording."""
    assert "SIMULATED" in load_doc.upper()
    assert load_doc.upper().index("SIMULATED") < load_doc.index("<svg")


def test_the_load_panel_cannot_be_handed_an_unstamped_window():
    """Not asserted on the panel but on the type it takes: `BiosignalWindow`
    refuses to exist without a stamp, so there is no unstamped thing to pass."""
    from src.biosignals.sources import BiosignalWindow

    with pytest.raises(ValueError, match="SIMULATED"):
        BiosignalWindow(
            source="x",
            stamp="",
            index=0,
            t0_s=0.0,
            sample_rate_hz=10.0,
            channels={"rr_ms": (800.0, 810.0)},
            features={"load_index": 0.5},
        )


def test_the_load_meter_carries_the_uncalibrated_wording(load_doc):
    assert plain.LOAD_NOT_CALIBRATED in load_doc
    assert "ranking only" in load_doc and "not calibrated" in load_doc


def test_the_load_panel_contains_no_band_label(load_doc):
    """`charts.py::risk_meter` refuses to band an uncalibrated ranking and this
    meter is on the same footing. Matched on whole words so that ordinary copy
    ("high-frequency band", "below") cannot trip it and a real band label
    cannot slip past it."""
    body = _visible_text(load_doc)
    for banned in ("low", "moderate", "elevated", "severe", "critical", "normal"):
        assert not re.search(rf"\b{banned}\b", body, re.I), f"{banned!r} reads as a band"
    assert not re.search(r"\bhigh\b(?!-)", body, re.I)


def _visible_text(document: str) -> str:
    """Strip tags, style and script: what a reader actually sees."""
    body = re.sub(r"<style.*?</style>", " ", document, flags=re.S)
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def test_the_load_panel_names_its_weights_on_the_surface(load_doc):
    from src.biosignals.features import LOAD_WEIGHTS

    for weight in LOAD_WEIGHTS.values():
        assert f"{weight:+.2f}" in load_doc
    assert "Nothing was fitted" in load_doc


def test_the_load_panel_numbers_are_the_windows_own(windows):
    document = neurovis.load_panel(windows[0], mode="light", frames=windows)
    for key, _name, _meaning in plain.LOAD_CHANNELS:
        assert f"{windows[0].features[key]:.2f}" in document
    assert f"{windows[0].features['load_index']:.2f}" in document


def test_the_smoothing_is_display_only(windows):
    """The trace is smoothed so the level is visible; the number is not.

    If `pupil_effort` were ever computed from the smoothed series the two would
    drift apart silently, and the panel would disagree with its own caption.
    """
    from src.biosignals.features import pupil_effort

    raw = list(windows[0].channels["pupil_z"])
    assert neurovis._smooth(raw) != raw
    assert windows[0].features["pupil_effort"] == pytest.approx(pupil_effort(raw))


def test_the_load_panel_reaches_no_network(load_doc):
    script = load_doc[load_doc.index("<script>") : load_doc.rindex("</script>")]
    for forbidden in ("import ", "fetch(", "http://", "https://", "XMLHttpRequest"):
        assert forbidden not in script


# ---------------------------------------------------------------------------
# (h) cross-cutting checks over the surviving panels
# ---------------------------------------------------------------------------


def test_the_page_refuses_a_source_that_is_not_simulated():
    """The guard itself, not its absence. A hardware source reaching this page
    is the thing the whole phase is built to prevent."""
    from src.biosignals import EthicsGateError, require_simulated

    class Impostor:
        name = "muse-2"
        stamp = "SIMULATED"
        simulated = True

        def window(self, index):
            raise AssertionError("never reached")

    with pytest.raises(EthicsGateError):
        require_simulated(Impostor())


def test_the_load_tile_uses_no_band_language(windows):
    from src.dashboard.widgets import load_widget

    tile = load_widget(windows[0])
    text = " ".join((tile.title, tile.value_caption, tile.secondary_caption))
    for banned in ("low", "moderate", "high", "elevated", "severe", "normal"):
        assert not re.search(rf"\b{banned}\b", text, re.I)
    assert plain.LOAD_NOT_CALIBRATED in tile.value_caption


def test_the_load_panel_passes_the_activation_screen(load_doc):
    neurovis.assert_no_activation_vocabulary(load_doc)


def test_the_atlas_timeline_does_not_repeat_the_current_example(view):
    """The page builds `view` and the frame list separately, so the current
    example arrives twice as two equal-but-distinct objects. Deduplicated by
    record id; identity would not catch it, and the panel offered "1 of 4" over
    three examples until the running app showed it."""
    import json as _json

    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    views = [build_view(example_id=e, backend=backend) for e in backend.example_ids]
    again = build_view(example_id=backend.example_ids[0], backend=backend)
    assert again is not views[0]
    document = neurovis.atlas_panel(again, mode="light", frames=views)
    payload = _json.loads(
        document[document.index("var D = ") + 8 : document.index(";\n  var i = 0")]
    )
    labels = [f["label"] for f in payload["frames"]]
    assert labels == list(backend.example_ids)
    assert len(labels) == len(set(labels))


@pytest.fixture(scope="module")
def narrated():
    from src.biosignals import SimulatedCardioOculoSource, require_simulated
    from src.dashboard import narration

    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    rid = backend.example_ids[0]
    view = build_view(example_id=rid, backend=backend)
    clip = narration.clip_for(rid)
    source = require_simulated(SimulatedCardioOculoSource(seed=20260913))
    session = narration.narrated_windows(view, clip, source)
    return session, clip, neurovis.narrated_panel(session, clip, mode="light")


def test_the_narrated_heart_rate_trace_rises_when_the_heart_speeds_up(narrated):
    """The trace and the number beside it must move the same way.

    The first version plotted the RR interval under a heading that said "heart
    rate". RR is the reciprocal, so the line fell as the readout rose -- two
    correct halves making a figure that said the opposite of what it meant.
    Asserted by reading the polyline back out of the SVG and correlating it with
    the beat series it was drawn from.
    """
    session, clip, document = narrated
    beats = session.clip_rr
    if len(beats) < 3:
        pytest.skip("clip too short to have a shape")
    points = re.search(r'<polyline[^>]*points="([^"]+)"', document).group(1)
    ys = [float(pair.split(",")[1]) for pair in points.split()]
    bpm = [60000.0 / rr for _t, rr in beats]
    # SVG y grows downward, so a faster heart must give a SMALLER y.
    fastest = max(range(len(bpm)), key=lambda i: bpm[i])
    slowest = min(range(len(bpm)), key=lambda i: bpm[i])
    assert ys[fastest] < ys[slowest]


# ---------------------------------------------------------------------------
# (i) the narrated clip - the most over-readable surface in the project
# ---------------------------------------------------------------------------


def test_the_narrated_panel_says_the_voice_is_synthetic_before_the_player(narrated):
    """A voice plus a responding heart trace is one step from looking like a
    recording of a person. The disclaimer goes above the player, not below it."""
    _session, _clip, document = narrated
    # Compared escaped: the panel escapes every caption it renders, so the raw
    # constant is deliberately absent from the document.
    note = escape(plain.NARRATED_VOICE_NOTE)
    assert note in document
    assert document.index(note) < document.index("<audio")
    assert document.upper().index("SIMULATED") < document.index("<audio")


def test_the_narrated_panel_states_the_coupling_is_imposed(narrated):
    """The single most important sentence on this surface.

    The arrow runs text -> body and this code drew it. Without that stated, the
    panel reads as concordance evidence -- the deferred second-paper claim --
    which is the one thing it must never be mistaken for.
    """
    _session, _clip, document = narrated
    imposed = escape(plain.NARRATED_IMPOSED)
    assert imposed in document
    assert document.index(imposed) < document.index("<audio")
    assert "not evidence" in document.lower()


def test_the_narrated_panel_reports_no_heart_rate_variability(narrated):
    """Twelve beats cannot support an HRV estimate, so none is shown.

    Asserted as an absence with the reason on screen, because the tempting fix
    was to show one anyway -- and measured directly, every HRV statistic moved
    the WRONG WAY on this window length. See features.SHORT_LOAD_WEIGHTS.
    """
    session, _clip, document = narrated
    for window in session.windows:
        assert "hf_hrv" not in window.features
        assert "rmssd" not in window.features
    body = _visible_text(document)
    assert "variability is not shown" in body
    assert not re.search(r"\bHF-HRV\b\s*[:=]", body)


def test_the_narrated_load_index_uses_two_channels_and_names_them():
    from src.biosignals.features import LOAD_WEIGHTS, SHORT_LOAD_WEIGHTS

    assert set(SHORT_LOAD_WEIGHTS) == {"pupil_effort", "blink_rate"}
    assert "hf_hrv" in LOAD_WEIGHTS, "the 60-second index keeps HRV; only the short one drops it"
    assert all(w > 0 for w in SHORT_LOAD_WEIGHTS.values())


def test_every_hrv_statistic_moves_the_wrong_way_on_a_short_window():
    """Pins the finding that removed HRV from the narrated panel.

    This is a test of the PROBLEM, not of a fix. It exists so that the next
    person to think "we should show RMSSD here, it works on short windows" meets
    the counter-example instead of shipping it. If this test ever fails because
    the simulator changed, re-derive the conclusion before re-adding HRV.
    """
    from src.biosignals import SimulatedCardioOculoSource
    from src.biosignals.features import arousal_curve, rmssd

    source = SimulatedCardioOculoSource(seed=7)
    track = arousal_curve([(1.5, 0.9)], 7.2, samples=73)
    session = source.narrate(track, 7.2)
    calm = session.windows[2]
    strained = session.windows[-1]
    assert strained.features["arousal"] > calm.features["arousal"]
    # Arousal rose, so a valid vagal index should FALL. It rises instead --
    # the rate change inside the window is itself variability.
    assert rmssd(list(strained.channels["rr_ms"])) > rmssd(list(calm.channels["rr_ms"]))


def test_the_readable_surface_strips_binary_payloads_without_loosening_the_screen():
    """A forty-kilobyte base64 blob contains words by accident; the first clip
    built here contained "fmri" and refused to render. The screen is not relaxed
    -- the payload is removed before the words are checked, and everything
    outside a data: URI is checked exactly as strictly as before."""
    payload = "data:audio/mpeg;base64," + "fmriACTIVATIONmeasured" * 4
    assert "fmri" not in neurovis.readable_surface(payload)
    neurovis.assert_no_activation_vocabulary(neurovis.readable_surface(payload))
    with pytest.raises(neurovis.ActivationVocabulary):
        neurovis.assert_no_activation_vocabulary("<p>fmri evidence</p>" + payload)


def test_an_unevidenced_driver_lifts_the_baseline_and_makes_no_bump():
    """The distinction the trace exists to keep visible.

    A phrase the model can point at gets a moment; a driver it cannot gets the
    whole clip. Blending them would hide which is which, and on this corpus most
    drivers are unevidenced -- the dashboard already reports 104 cases in 120.
    """
    from src.dashboard import narration

    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    per_example = {}
    for rid in backend.example_ids:
        view = build_view(example_id=rid, backend=backend)
        clip = narration.clip_for(rid)
        per_example[rid] = (
            narration.arousal_events(view, clip),
            narration.baseline_arousal(view),
        )
    # At least one example is driven purely by unevidenced signals -- no events,
    # a lifted floor. That is the case a naive implementation renders flat.
    assert any(not events and base > 0.3 for events, base in per_example.values())
    # And at least one has real timed evidence.
    assert any(events for events, _base in per_example.values())


def test_the_narrated_session_cannot_exist_without_a_stamp():
    from src.biosignals.sources import NarratedSession

    with pytest.raises(ValueError, match="SIMULATED"):
        NarratedSession(
            windows=(),
            duration_s=1.0,
            stamp="recorded in the lab",
            beat_times_s=(),
            rr_ms=(),
            pupil_z=(),
            blink=(),
            pupil_rate_hz=10.0,
        )


def test_the_narrated_panel_needs_no_network(narrated):
    """The clip is inlined. An <audio src> pointing at a path Streamlit does not
    serve would fail exactly like the blocked CDN motion.py records: silently."""
    _session, _clip, document = narrated
    assert 'src="data:audio/mpeg;base64,' in document
    script = document[document.index("<script>") : document.rindex("</script>")]
    for forbidden in ("import ", "fetch(", "http://", "https://", "XMLHttpRequest"):
        assert forbidden not in script


def test_the_narrated_panel_renders_without_its_script(narrated):
    """Classic-script-first: the whole clip is drawn server-side, so JavaScript
    off costs the playhead and the live readouts, not the figure."""
    _session, _clip, document = narrated
    without = re.sub(r"<script>.*?</script>", "", document, flags=re.S)
    assert "<script" not in without
    assert escape(plain.NARRATED_VOICE_NOTE) in without
    assert escape(plain.NARRATED_IMPOSED) in without
    assert "<polyline" in without
    # Attribute quoting varies across this module's f-strings, so match the id
    # rather than a spelling of it.
    assert re.search(r"id=['\"]bpm['\"]", without)
    assert re.search(r"id=['\"]ph1['\"]", without)
