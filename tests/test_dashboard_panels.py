"""Phase 22b -- honesty tests for the panels, copy and charts added after Phase 20.

WHY A SECOND FILE
-----------------
`tests/test_dashboard.py` is the Phase 20 gate and is left untouched; these are
the properties the readability and visualisation work introduced, and they are
the ones nothing was checking. The defect this file exists to prevent is the one
the phase already produced once and only a screenshot caught: the animated panel
built its DOM inside an ES module, the module failed to load with the CDN
unreachable, and the card rendered empty while all 25 tests above stayed green.
"It renders in my browser" is not "it renders".

Each test below is paired with a mechanism, in the same style as the file it
sits beside:

    (a) copy.py's import-time screen  -> reflective over the module namespace, so
                                         a caption added later is screened
                                         without anyone remembering to.
    (b) motion_panel                  -> asserted to introduce no number the view
                                         does not already carry, and to render
                                         its rows without the module script.
    (c) the polarity switch           -> asserted to move the marking, the
                                         arithmetic AND the words together, and
                                         to withhold the committed card.
    (d) the three new charts          -> asserted to carry their own provenance
                                         and to survive grayscale.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.dashboard import plain
from src.dashboard.backend import LexiconBackend, ReplayBackend
from src.dashboard.benchmarks import (
    PER_CONSTRUCT_CAPTION,
    load_benchmarks,
    load_per_construct,
)
from src.dashboard.charts import (
    benchmark_chart,
    evidence_coverage_chart,
    per_construct_chart,
    risk_waterfall,
)
from src.dashboard.motion import motion_panel, panel_height, spans_panel
from src.dashboard.view import (
    DEFAULT_POLICY_LABEL,
    POLICY_LABELS,
    ForbiddenLanguage,
    assert_no_forbidden_language,
    build_view,
    scorer_for,
)
from src.risk.fusion import PolarityPolicy

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "dashboard" / "app.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"

#: A text whose cues land on the four two-sided constructs, so the polarity
#: policy actually has something to act on. A text that detects none of them
#: would let every policy agree and the test would prove nothing.
POLAR_TEXT = (
    "All I'm thinking about is the crowd and I keep checking my phone. I want to "
    "take it on and test myself, but I'd rather not talk about it."
)


@pytest.fixture(scope="module")
def view():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return build_view(example_id=backend.example_ids[0], backend=backend)


# ---------------------------------------------------------------------------
# (a) the plain-English copy is screened, not trusted
# ---------------------------------------------------------------------------


def test_every_string_in_the_copy_module_passes_the_forbidden_screen():
    """The screen runs at import; this asserts it covers the whole namespace.

    Re-run here over the same reflective walk, so a future refactor that turns
    `_screen()` into a hand-written list of names fails immediately -- that list
    is exactly the thing that goes stale.
    """
    published = [
        value
        for name, value in vars(plain).items()
        if not name.startswith("_") and isinstance(value, (str, tuple, dict))
    ]
    assert len(published) >= 15, "the copy module published almost nothing; wrong module?"
    for value in published:
        for chunk in plain._strings(value):
            assert_no_forbidden_language(chunk)


def test_the_copy_screen_actually_rejects_something():
    """A screen that passes everything is not a screen."""
    with pytest.raises(ForbiddenLanguage):
        assert_no_forbidden_language("our coach-validated detector")


def test_every_construct_has_a_plain_english_name_and_a_direction(view):
    """No construct may reach a reader as a bare identifier.

    Derived from the live view's own bars rather than from a list, so adding an
    eleventh construct to the taxonomy fails here instead of silently rendering
    `new_construct` to a coach.
    """
    for bar in view.bars:
        assert bar.construct in plain.CONSTRUCTS, (
            f"{bar.construct} has no plain-English entry in copy.CONSTRUCTS"
        )
        name, meaning, direction = plain.CONSTRUCTS[bar.construct]
        assert name and meaning
        assert direction in plain.DIRECTION_PLAIN
        assert (direction == "inert") == bar.inert, (
            f"{bar.construct}: the copy and the scorer disagree about inertness"
        )


def test_the_glossary_covers_the_jargon_the_page_still_shows(view):
    terms = " ".join(term.lower() for term, _ in plain.GLOSSARY)
    for required in ("construct", "risk index", "inert", "span", "macro-f1"):
        assert required in terms


# ---------------------------------------------------------------------------
# (b) the animated panel renders, and invents nothing
# ---------------------------------------------------------------------------


def test_the_panel_introduces_no_number_the_view_does_not_carry(view):
    """The panel is a second rendering of one set of facts, never a second computation.

    Checked against the payload it embeds rather than against the rendered
    markup, because the payload is what the script draws from.
    """
    payload = json.loads(re.search(r"const data = (\{.*?\});\n", motion_panel(view), re.S).group(1))
    assert payload["risk"] == pytest.approx(view.risk.value, abs=5e-4)
    assert payload["unevidenced"] == view.unevidenced_driver_count
    assert len(payload["rows"]) == len(view.bars)
    by_key = {r["key"]: r for r in payload["rows"]}
    for bar in view.bars:
        row = by_key[bar.construct]
        assert row["contribution"] == pytest.approx(bar.contribution, abs=5e-4)
        assert row["probability"] == pytest.approx(bar.probability, abs=5e-4)
        assert row["inert"] is bar.inert


def test_the_panel_renders_without_the_animation_module(view):
    """The defect a screenshot caught, pinned.

    The rows must be built by a classic `<script>` with no imports, so a blocked
    CDN costs the motion and nothing else. Asserted structurally: the element the
    rows are written into is populated by a script that appears *before* the
    first `type="module"` tag and contains no `import`.
    """
    html = motion_panel(view)
    module_at = html.index('<script type="module">')
    classic = html[:module_at]
    assert "import " not in classic, "the fallback script imports; a blocked CDN empties the panel"
    assert 'getElementById("rows")' in classic
    assert 'getElementById("big")' in classic
    assert "scaleX(${data.risk})" in classic, "the meter's final state is never painted"


def test_the_panel_marks_every_inert_construct_in_words(view):
    html = motion_panel(view)
    inert = [b for b in view.bars if b.inert]
    assert inert
    assert html.count("inert") >= len(inert), "inertness is carried by styling alone"
    for bar in inert:
        name, _, _ = plain.CONSTRUCTS[bar.construct]
        assert name in html


def test_the_panel_honours_reduced_motion_and_sizes_its_iframe(view):
    html = motion_panel(view)
    assert "prefers-reduced-motion" in html
    # An iframe does not grow to its content: too short and the last row is
    # invisible while every test here still passes.
    assert panel_height(view) > 60 * len(view.bars)


def test_the_evidence_panel_says_so_when_nothing_supports_a_driver(view):
    html = spans_panel(view)
    assert view.unevidenced_driver_count
    assert "no words in the text back this up" in html


# ---------------------------------------------------------------------------
# (c) the polarity switch moves the marking, the arithmetic and the words together
# ---------------------------------------------------------------------------


def test_the_default_policy_is_the_one_the_paper_reports():
    assert scorer_for(DEFAULT_POLICY_LABEL).polarity_policy is PolarityPolicy.NEUTRAL


def test_an_unoffered_policy_cannot_reach_the_arithmetic():
    with pytest.raises(ValueError):
        scorer_for("pessimistic")  # the enum value, not an offered label
    with pytest.raises(ValueError):
        scorer_for("")


def test_switching_policy_moves_the_index_the_marking_and_the_words():
    """C2.5, one level up: the picture, the number and the prose move together.

    Under the default the four two-sided constructs are inert and contribute
    nothing; under the other two they carry a sign and the index moves a long
    way on identical text. If any one of the three stopped following the policy,
    the page would assert something the numbers do not.
    """
    backend = LexiconBackend()
    seen = {}
    for label, policy in POLICY_LABELS.items():
        view = build_view(text=POLAR_TEXT, backend=backend, scorer=scorer_for(label))
        inert = {b.construct for b in view.bars if b.inert}
        seen[policy] = (view.risk.value, inert, view.render_text())
        assert view.policy_note in view.render_text()

    neutral_index, neutral_inert, neutral_text = seen[PolarityPolicy.NEUTRAL]
    pess_index, pess_inert, pess_text = seen[PolarityPolicy.PESSIMISTIC]
    opt_index, opt_inert, _ = seen[PolarityPolicy.OPTIMISTIC]

    assert len(neutral_inert) == 4, "the default must leave the two-sided four inert"
    assert pess_inert == set() and opt_inert == set(), "the marking did not follow the policy"
    assert pess_index > neutral_index > opt_index, (
        "the same text must rank differently once the policy resolves the four"
    )
    assert "conservative" in neutral_text.lower()
    assert "not a result" in pess_text.lower(), (
        "a non-default policy must say in words that it produces no reported number"
    )


def test_a_non_default_policy_is_flagged_and_withholds_the_committed_card():
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    label = next(k for k, v in POLICY_LABELS.items() if v is PolarityPolicy.PESSIMISTIC)
    view = build_view(example_id=backend.example_ids[0], backend=backend, scorer=scorer_for(label))
    assert view.is_default_policy is False
    source = APP_PATH.read_text(encoding="utf-8")
    assert "is_default_policy" in source, (
        "the shell renders the committed paper card without checking the policy"
    )


# ---------------------------------------------------------------------------
# (d) the three new charts
# ---------------------------------------------------------------------------


def test_the_waterfall_ends_on_the_index_the_view_reports(view):
    svg = risk_waterfall(view.bars, raw_score=view.raw_score, index=view.risk.value)
    assert f"index {view.risk.value:.2f}" in svg
    assert f"{view.raw_score:+.3f}" in svg
    # Inert constructs add exactly zero and are excluded from the steps; the
    # count must still be stated, or the chart quietly drops four rows.
    n_inert = sum(1 for b in view.bars if b.inert)
    assert f"{n_inert} inert constructs are not drawn" in svg
    for bar in view.bars:
        if bar.inert:
            assert bar.construct.replace("_", " ") not in svg


def test_the_coverage_chart_compares_this_text_to_the_corpus(view):
    svg = evidence_coverage_chart(
        evidenced=view.evidenced_driver_count,
        unevidenced=view.unevidenced_driver_count,
    )
    assert "104 of 120" in svg, "the corpus-wide comparison is the point of this chart"
    total = view.evidenced_driver_count + view.unevidenced_driver_count
    assert f"{view.unevidenced_driver_count} of {total}" in svg
    assert "pattern" in svg and "stroke-dasharray" in svg, "hatched share is colour-only"


def test_the_benchmark_chart_is_read_from_the_artefact_not_typed_in():
    """The figures must come from the file the claim gate reads.

    Asserted by reading the artefact independently here: if someone hardcodes a
    caption, the two diverge and this fails.
    """
    data = json.loads((REPO_ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
    benchmarks = load_benchmarks()
    svg = benchmark_chart(benchmarks)
    for key, row in zip(
        ("template_disjoint::lexicon", "template_disjoint::transformer", "random::transformer"),
        benchmarks.rows,
        strict=True,
    ):
        assert row.point == pytest.approx(data["scores"][key]["macro_f1"]["point"])
        assert f"{row.point:.3f}" in svg
    assert "memorisation" in svg, "the seen-patterns bar is not marked as inflated"


def test_the_per_construct_chart_names_the_constructs_the_model_does_not_win():
    """A negative result must be in words, not left to a two-pixel difference."""
    rows = load_per_construct()
    assert len(rows) == 10
    assert [r.f1 for r in rows] == sorted(r.f1 for r in rows), "weakest-first ordering lost"
    svg = per_construct_chart(rows, caption=PER_CONSTRUCT_CAPTION)
    losers = [r for r in rows if not r.beats_floor]
    assert losers, "no construct loses to the floor; check the artefact, not the chart"
    assert svg.count("no better than the floor") == len(losers)
    for row in rows:
        assert row.construct.replace("_", " ") in svg


def test_no_new_surface_contains_a_forbidden_string(view):
    """The Phase 20 screen, extended over everything this phase added."""
    surfaces = [
        motion_panel(view),
        spans_panel(view),
        risk_waterfall(view.bars, raw_score=view.raw_score, index=view.risk.value),
        evidence_coverage_chart(evidenced=1, unevidenced=5),
        benchmark_chart(load_benchmarks()),
        per_construct_chart(load_per_construct(), caption=PER_CONSTRUCT_CAPTION),
        APP_PATH.read_text(encoding="utf-8"),
    ]
    for surface in surfaces:
        assert_no_forbidden_language(surface)
