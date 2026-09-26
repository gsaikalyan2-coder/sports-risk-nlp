"""Phase 32 -- evidence coverage: the config, the ledger and the panel.

This feature's output IS the limitation, which changes what the tests are for.
Most suites here check that a number is right. These check that a number cannot
be read as something it is not, because "somatic anxiety: silent" beside a
confident risk index is one careless word away from "this athlete has no
somatic anxiety" -- a claim nothing in this repository can support, about a
person who does not exist.

Five groups:

    (a) the config cannot lie      -> every construct mapped exactly once, every
                                      citation resolving, no numbers, and a
                                      closed field set so the file can never
                                      grow a question (the copyright rule)
    (b) the ledger cannot drift    -> states derived only from the view, counts
                                      exhaustive, stamp mandatory
    (c) it agrees with Phase 31    -> the same four states, checked against
                                      `src.evaluation.abstention` by a test that
                                      imports both while the modules import
                                      neither
    (d) the panel cannot mislead   -> fixed caveats above the table, three
                                      channels per state, no absence language,
                                      nothing fetched
    (e) it changes nothing         -> the risk index is bit-identical with and
                                      without the ledger
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest
import yaml

from src.dashboard import theme
from src.dashboard.backend import LexiconBackend, ReplayBackend
from src.dashboard.copy import (
    COVERAGE_CAVEATS,
    COVERAGE_LEGEND,
    COVERAGE_SILENT_CAVEAT,
)
from src.dashboard.coverage import (
    STATE_GLYPHS,
    CoverageLedger,
    CoverageState,
    coverage_for,
    state_for,
)
from src.dashboard.coverage_panel import coverage_height, coverage_panel
from src.dashboard.instruments import (
    INSTRUMENTS_PATH,
    InstrumentError,
    InstrumentRow,
    SubscaleRow,
    load_instruments,
    prompt_for,
)
from src.dashboard.view import build_view
from src.dashboard.widgets import coverage_widget
from src.evaluation.harness import PROVISIONAL_STAMP

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"
CORPUS_PATH = REPO_ROOT / "data" / "processed" / "gold_candidates" / "gold_dev.jsonl"

#: Phrasings that turn a coverage state into a claim about a person. Each one
#: is a real sentence somebody could write from this panel's data and none of
#: them is supportable: silent means no evidence either way, and "no evidence
#: of X" is not "no X".
ABSENCE_LANGUAGE = (
    "no somatic anxiety",
    "no cognitive anxiety",
    "free of",
    "does not have",
    "shows no",
    "healthy",
    "at risk",
    "diagnos",
)


@pytest.fixture(scope="module")
def view():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return build_view(example_id=backend.example_ids[0], backend=backend)


@pytest.fixture(scope="module")
def ledger(view):
    return coverage_for(view)


@pytest.fixture(scope="module")
def panel(ledger):
    return coverage_panel(ledger, mode="light")


def _corpus() -> tuple[str, ...]:
    if not CORPUS_PATH.exists():  # pragma: no cover - thin checkout
        pytest.skip("gold_candidates corpus is not present.")
    with CORPUS_PATH.open(encoding="utf-8") as handle:
        return tuple(json.loads(line)["text"] for line in handle if line.strip())


def _write(tmp_path: Path, data: dict) -> str:
    path = tmp_path / "instruments.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(path)


def _valid_payload() -> dict:
    """A minimal file that loads, so each refusal test breaks exactly one thing."""
    raw = yaml.safe_load(INSTRUMENTS_PATH.read_text(encoding="utf-8"))
    return {"version": 1, "phase": 32, "instruments": raw["instruments"]}


# ---------------------------------------------------------------------------
# (a) the config cannot lie
# ---------------------------------------------------------------------------


def test_every_taxonomy_construct_appears_in_exactly_one_instrument_row():
    """Not zero, and not two.

    Zero is the failure `atlas_map.py` already records for the atlas: a
    construct with no row disappears from a table and nobody counts rows. Two is
    the failure specific to this panel -- the headline is "N of 8 instruments",
    and a construct counted under two of them makes that denominator a fiction
    while the table still looks right.
    """
    taxonomy = set(yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["constructs"])
    named = list(load_instruments().constructs)
    assert set(named) == taxonomy
    assert len(named) == len(set(named)) == len(taxonomy)


def test_every_citation_key_resolves_in_the_bibliography():
    from src.dashboard.instruments import _bib_keys, _cited_keys

    keys = _bib_keys()
    for row in load_instruments().rows:
        cited = _cited_keys(row.citation)
        assert cited, f"{row.key} cites nothing"
        for key in cited:
            assert key in keys, f"{row.key} cites {key}, absent from refs.bib"


def test_a_row_with_an_empty_citation_is_refused(tmp_path):
    payload = _valid_payload()
    payload["instruments"]["pss"]["citation"] = "  "
    with pytest.raises(InstrumentError, match="no citation"):
        load_instruments(_write(tmp_path, payload))


def test_a_citation_key_absent_from_the_bibliography_is_refused(tmp_path):
    payload = _valid_payload()
    payload["instruments"]["pss"]["citation"] = "[NotAKeyAnywhere2099]"
    with pytest.raises(InstrumentError, match="does not resolve"):
        load_instruments(_write(tmp_path, payload))


def test_a_construct_absent_from_the_taxonomy_is_refused(tmp_path):
    payload = _valid_payload()
    payload["instruments"]["pss"]["subscales"] = ["vibes"]
    with pytest.raises(InstrumentError, match="not in the frozen taxonomy"):
        load_instruments(_write(tmp_path, payload))


def test_a_taxonomy_construct_with_no_row_is_refused(tmp_path):
    payload = _valid_payload()
    del payload["instruments"]["abq"]
    with pytest.raises(InstrumentError, match="has no row for"):
        load_instruments(_write(tmp_path, payload))


def test_a_construct_counted_under_two_instruments_is_refused(tmp_path):
    payload = _valid_payload()
    payload["instruments"]["pss"]["subscales"] = ["perceived_stress", "burnout_signal"]
    with pytest.raises(InstrumentError, match="under two instruments"):
        load_instruments(_write(tmp_path, payload))


def test_any_numeric_field_is_refused(tmp_path):
    """The same walk `atlas_map.py` uses, for the same reason.

    A number here would reach the screen with no provenance. Coverage state is
    read off `DashboardView.bars` at render time or it is not read at all.
    """
    payload = _valid_payload()
    payload["instruments"]["pss"]["weight"] = 0.4
    with pytest.raises(InstrumentError, match="carries a number"):
        load_instruments(_write(tmp_path, payload))


def test_an_unrecognised_field_is_refused(tmp_path):
    """R1, enforced at the file boundary rather than by review.

    The field set is closed so this file cannot grow a `prompt:` or an
    `item_text:`. CSAI-2, the ABQ, CD-RISC and TAIS are copyrighted; the one
    field that must never appear here is a question.
    """
    payload = _valid_payload()
    payload["instruments"]["pss"]["prompt"] = "How overloaded do you feel right now"
    with pytest.raises(InstrumentError, match="unrecognised field"):
        load_instruments(_write(tmp_path, payload))


def test_the_instruments_file_contains_no_question():
    """R1 again, this time over the committed file's raw bytes.

    The closed field set above stops a *new* field carrying an item. This stops
    one being smuggled into an allowed field -- a `full_name` phrased as a
    question would pass every structural check.
    """
    body = INSTRUMENTS_PATH.read_text(encoding="utf-8")
    prose = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    assert "?" not in prose, "instruments.yaml carries a question outside its commentary"


def test_every_prompt_is_derived_from_the_projects_own_taxonomy():
    """R1, the part that actually protects the reader-facing string.

    The prompt shown for an unevidenced subscale must be this project's own
    `definition`, never the instrument's wording. Asserted as an identity
    against `taxonomy.yaml`, so a hand-written prompt cannot be introduced
    without this failing.
    """
    definitions = yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))["constructs"]
    for row in load_instruments().rows:
        for sub in row.subscales:
            assert sub.prompt == prompt_for(sub.construct)
            normalised = " ".join(str(definitions[sub.construct]["definition"]).split())
            assert normalised.startswith(sub.prompt), (
                f"{sub.construct}'s prompt is not a prefix of its taxonomy definition; "
                "it has been authored rather than derived"
            )
            assert "?" not in sub.prompt


def test_a_subscale_row_refuses_an_empty_prompt():
    with pytest.raises(InstrumentError, match="no prompt"):
        SubscaleRow(construct="resilience", prompt="   ")


def test_an_instrument_row_refuses_no_subscales():
    with pytest.raises(InstrumentError, match="covers no subscale"):
        InstrumentRow(key="x", instrument="X", full_name="X", citation="[Cohen1983]", subscales=())


# ---------------------------------------------------------------------------
# (b) the ledger cannot drift
# ---------------------------------------------------------------------------


def test_a_ledger_without_a_provisional_stamp_is_refused(ledger):
    """Same shape as `ScoreSurface` and `BiosignalWindow`.

    "2 of 8" is the most quotable figure this feature produces and it is a
    property of a synthetic corpus scored by an unevaluated cue list. Unstamped
    it reads as a measurement.
    """
    with pytest.raises(ValueError, match="PROVISIONAL"):
        CoverageLedger(
            instruments=ledger.instruments,
            spoken_to=ledger.spoken_to,
            total=ledger.total,
            stamp="coverage report",
        )
    assert PROVISIONAL_STAMP.split(" -- ")[0] in ledger.stamp


def test_a_detected_but_inert_bar_yields_inert_and_never_evidenced():
    """The one ordering decision in the module, asserted directly.

    Calling it SILENT would hide a detection; calling it EVIDENCED would claim
    the text moved an index it did not move.
    """
    assert state_for(detected=True, inert=True) is CoverageState.INERT
    assert state_for(detected=True, inert=False) is CoverageState.EVIDENCED
    assert state_for(detected=False, inert=False) is CoverageState.SILENT
    # A bar cannot be undetected and inert in the live decomposition, but the
    # rule must still not silently promote it to a detection.
    assert state_for(detected=False, inert=True) is CoverageState.SILENT


def test_state_counts_are_exhaustive(ledger):
    """No subscale falls through. A gap here would shrink the denominator."""
    total = sum(ledger.count(state) for state in CoverageState)
    assert total == len(ledger.subscales) == len(load_instruments().constructs)


def test_the_ledger_introduces_no_number_the_view_does_not_carry(view, ledger):
    """Every count is a count of bars, to the integer.

    Note what INERT is NOT. `ConstructBar.inert` is true for all four polar
    constructs whatever the text said, because it is derived from direction and
    weight alone -- so the view carries four inert bars even when the text
    triggered none of them. Reporting that as four inert subscales would claim
    four detections that did not happen. INERT here means detected AND
    discarded; a polar construct the text never raised is SILENT, which is what
    the approved mockup shows and what `state_for` implements.
    """
    assert ledger.count(CoverageState.EVIDENCED) == sum(
        1 for bar in view.bars if bar.detected and not bar.inert
    )
    assert ledger.count(CoverageState.INERT) == sum(
        1 for bar in view.bars if bar.detected and bar.inert
    )
    assert ledger.count(CoverageState.SILENT) == sum(1 for bar in view.bars if not bar.detected)
    assert ledger.total == len(load_instruments().rows)
    assert ledger.spoken_to <= ledger.total


def test_coverage_for_never_returns_the_refused_state(ledger):
    """A refused input never reaches the scorer, so no view exists to read.

    `REFUSED` is in the enum so the vocabulary matches Phase 31's, not because
    this path can produce it.
    """
    assert ledger.count(CoverageState.REFUSED) == 0


def test_all_three_live_states_are_reachable_over_the_real_corpus():
    """A state nothing produces is a state nobody has seen rendered."""
    backend = LexiconBackend()
    seen: set[CoverageState] = set()
    for text in _corpus():
        for sub in coverage_for(build_view(text=text, backend=backend)).subscales:
            seen.add(sub.state)
        if len(seen) == 3:
            break
    assert seen == {CoverageState.EVIDENCED, CoverageState.INERT, CoverageState.SILENT}


def test_a_realistic_passage_speaks_to_a_minority_of_the_instrument_set():
    """The finding this whole feature exists to put on screen.

    Not a threshold on quality -- it is the measurement `reports/abstention.md`
    motivates, asserted so that a change making coverage look comfortable fails
    loudly instead of quietly flattering the system.

    The bound is the *measured* shape, not a comfortable one. An earlier version
    asserted a mean below 2.0, which the real mean of 0.62 clears by a factor of
    three -- a test that passes however much the finding softens is not a guard.
    Measured over `gold_dev` (n=100) on 2026-09-23: mean 0.62 of 8, distribution
    {0: 40, 1: 58, 2: 2}. The assertions below allow drift in both directions and
    fail if the headline changes character: if the typical text starts speaking
    to more than one instrument, or if the "speaks to nothing at all" share stops
    being a large minority, this stops being the feature `docs/dashboard.md`
    describes and the docs must be rewritten with it.
    """
    backend = LexiconBackend()
    counts = [coverage_for(build_view(text=t, backend=backend)).spoken_to for t in _corpus()]
    mean = sum(counts) / len(counts)
    silent_entirely = sum(1 for c in counts if c == 0) / len(counts)

    assert max(counts) < 8, "a corpus text now speaks to every instrument; verify the cue list"
    assert mean < 1.0, f"the typical text now speaks to more than one instrument (mean {mean:.2f})"
    assert silent_entirely > 0.2, (
        f"only {silent_entirely:.0%} of texts speak to no instrument at all; the plan's "
        "headline finding (40% on gold_dev) no longer holds and the docs quoting it are stale"
    )


# ---------------------------------------------------------------------------
# (c) agreement with Phase 31, without an import between the modules
# ---------------------------------------------------------------------------


def test_neither_module_imports_the_other():
    """The OPEN-036 guard, asserted at the import graph.

    `src.evaluation.abstention` already reaches into `src.dashboard`. An import
    the other way closes the cycle that broke
    `test_explainability_imports_standalone_in_a_fresh_interpreter` in Phase 31.
    This test imports both; the modules import neither.
    """
    pairs = (
        (REPO_ROOT / "src" / "dashboard" / "coverage.py", "src.evaluation.abstention"),
        (REPO_ROOT / "src" / "evaluation" / "abstention.py", "src.dashboard.coverage"),
    )
    for path, forbidden in pairs:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module != forbidden, f"{path.name} imports {forbidden}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != forbidden, f"{path.name} imports {forbidden}"


#: The correspondence between this module's per-subscale states and Phase 31's
#: per-text causes. They are four and four, and they are NOT the same four
#: words: `abstention` names a whole text's outcome ("nothing was detected"),
#: this names one subscale's ("this one gave nothing"). Writing the map out is
#: the drift guard -- a fifth state on either side breaks the bijection below.
STATE_TO_CAUSE = {
    "silent": "no_detection",
    "inert": "all_inert",
    "refused": "refused",
    "evidenced": "moved",
}


def test_the_two_modules_describe_the_same_four_outcomes():
    """Drift guard. Two modules with four states each is two places to add a fifth."""
    from src.evaluation.abstention import CAUSES

    mine = {state.value for state in CoverageState}
    theirs = set(CAUSES)
    assert mine == set(STATE_TO_CAUSE), f"CoverageState gained or lost {mine ^ set(STATE_TO_CAUSE)}"
    assert theirs == set(STATE_TO_CAUSE.values()), f"CAUSES gained or lost {theirs}"
    assert len(set(STATE_TO_CAUSE.values())) == len(STATE_TO_CAUSE), "the map is not a bijection"


def test_per_construct_states_agree_with_the_phase_31_cause():
    """The semantic half of the agreement, on a basis the two modules share.

    `abstention.counterfactual_score` deliberately uses the FROZEN
    `CONSTRUCT_CUES`, while the live `LexiconBackend` uses that list widened
    with `DASHBOARD_EXTRA_CUES` (the demo-only widening `docs/dashboard.md`
    discloses). Comparing a `build_view` against an `Outcome` would therefore
    compare two detectors and fail for a reason that is not drift. So the
    states are derived here from the counterfactual's OWN decomposition, using
    `coverage.state_for` -- the shared rule -- and checked against the cause
    that decomposition produced.
    """
    from src.evaluation.abstention import counterfactual_score, evaluate
    from src.risk.fusion import Direction

    checked = 0
    for text in _corpus()[:60]:
        outcome = evaluate(text, "corpus")
        if not outcome.admitted:
            continue
        contributions = counterfactual_score(text).contributions
        states = [
            state_for(
                detected=c.probability > 0.0,
                inert=c.direction is Direction.POLAR and c.weight == 0.0,
            )
            for c in contributions
        ]
        evidenced = CoverageState.EVIDENCED in states
        if outcome.cause == "no_detection":
            assert set(states) == {CoverageState.SILENT}, text
        elif outcome.cause == "all_inert":
            assert CoverageState.INERT in states and not evidenced, text
        elif outcome.cause == "moved":
            assert evidenced, text
        checked += 1
    assert checked, "no corpus text was admitted; the agreement test checked nothing"


# ---------------------------------------------------------------------------
# (d) the panel cannot mislead
# ---------------------------------------------------------------------------


def test_the_panel_carries_the_three_fixed_caveats(panel):
    for caveat in COVERAGE_CAVEATS:
        assert caveat in panel, f"panel dropped the caveat: {caveat[:40]}"
    assert "subscales, not items" in panel.lower()
    assert "no evidence either way" in panel.lower()


def test_the_caveats_precede_the_first_table_row(panel):
    """A caveat below the number does not travel with a screenshot of it."""
    first_caveat = min(panel.index(c) for c in COVERAGE_CAVEATS)
    assert first_caveat < panel.index("<table"), "a caveat renders after the table opens"
    assert first_caveat < panel.index('<td class="name"')


def test_the_panel_carries_the_provenance_stamp(panel, ledger):
    assert ledger.stamp in panel
    assert PROVISIONAL_STAMP.split(" -- ")[0] in panel


def test_the_panel_never_renders_absence_language(panel):
    """R3. Silent means no evidence either way, in all three of its senses."""
    lowered = panel.lower()
    for phrase in ABSENCE_LANGUAGE:
        assert phrase not in lowered, f"the panel renders {phrase!r}"
    assert COVERAGE_SILENT_CAVEAT in panel


def test_the_panel_quotes_no_item_count_of_its_own(panel):
    """R2. The only item figure on the panel is CSAI-2's, inside the caveat that
    exists to say a count here is not a share of a questionnaire."""
    numbers = re.findall(r"\b(\d+) items?\b", panel)
    assert numbers == ["27"], f"an unexplained item count reached the panel: {numbers}"


def test_every_state_renders_three_channels(ledger):
    """Glyph, hue AND the literal word -- never hue alone.

    `charts.py`'s rule and its reason: these surfaces become paper figures, and
    hue alone fails in grayscale, in print, and for a CVD reader.
    """
    document = coverage_panel(ledger, mode="light")
    for state in {sub.state for sub in ledger.subscales}:
        assert STATE_GLYPHS[state] in document, f"{state} has no glyph"
        assert f".s-{state.value}{{color:" in document, f"{state} has no hue rule"
        assert f'class="g s-{state.value}"' in document, f"{state}'s glyph is unpainted"


def test_every_state_word_is_on_the_panel(ledger):
    document = coverage_panel(ledger, mode="light")
    for sub in ledger.subscales:
        assert sub.word in document, f"{sub.state} never appears as a word"
    for key, _gloss in COVERAGE_LEGEND:
        assert f"<b>{key}</b>" in document, f"the legend dropped {key}"


def test_the_panel_fetches_nothing(panel):
    """The defect `motion.py` records: a blocked CDN left the card empty while
    every unit test stayed green. There is nothing here to block."""
    for forbidden in ("<script", "<link", "@import", "http://", "https://", "url(", "<img"):
        assert forbidden not in panel, f"the panel reaches for {forbidden}"


def test_the_panel_renders_identically_with_the_webfont_blocked(panel):
    """It names no font file, so a blocked webfont costs nothing at all."""
    assert "fonts.googleapis" not in panel and "fonts.gstatic" not in panel
    assert "@font-face" not in panel


def test_both_modes_render_and_use_only_palette_colours(ledger):
    for mode in ("light", "dark"):
        document = coverage_panel(ledger, mode=mode)
        allowed = {value.lower() for value in theme.palette(mode).values()}
        used = {hexcode.lower() for hexcode in re.findall(r"#[0-9a-fA-F]{3,8}", document)}
        assert used <= allowed, f"{mode} paints with {used - allowed}, outside theme.palette"
        assert "<table" in document and ledger.summary in document


def test_the_two_modes_actually_differ(ledger):
    """A mode that filled in only the colours it wanted to change would leave
    the rest at light values -- the dark-on-dark failure `theme.py` records."""
    assert coverage_panel(ledger, mode="light") != coverage_panel(ledger, mode="dark")


def test_the_panel_height_is_a_positive_integer(ledger):
    assert isinstance(coverage_height(ledger), int)
    assert coverage_height(ledger) > 0


def test_the_summary_is_a_count_and_never_a_percentage(ledger):
    """A percentage of eight instruments reads as a completion rate."""
    assert f"{ledger.spoken_to} of {ledger.total}" in ledger.summary
    assert "%" not in ledger.summary


# ---------------------------------------------------------------------------
# (e) it changes nothing
# ---------------------------------------------------------------------------


def test_building_a_ledger_does_not_move_the_risk_index(view):
    """Bit-identical, before and after. The widget is a read, not a write."""
    before = view.risk.value
    before_display = view.risk.display
    before_bars = tuple((b.construct, b.probability, b.contribution) for b in view.bars)
    coverage_for(view)
    coverage_panel(coverage_for(view), mode="dark")
    coverage_widget(view)
    assert view.risk.value == before
    assert view.risk.display == before_display
    assert tuple((b.construct, b.probability, b.contribution) for b in view.bars) == before_bars


def test_the_tile_carries_the_views_stamp_and_its_own_denominator(view, ledger):
    tile = coverage_widget(view)
    assert tile.stamp == view.risk.stamp
    assert tile.value == f"{ledger.spoken_to} of {ledger.total}"
    assert "no evidence either way" in tile.secondary_caption
    assert tile.construct == "evidence_coverage"
