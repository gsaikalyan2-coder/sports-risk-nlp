"""Phase 20 -- the honesty tests for the dashboard.

WRITTEN BEFORE THE APP, ON PURPOSE
-----------------------------------
`handover_phase_19.txt` C1 records the same defect three phases running: the
check and the thing it protects were related by *assumption* rather than by
*construction*. Phase 9b expanded a suffix bank that was never the lever; Phase
17 shipped an ethics guard bypassable through a different field; Phase 18's
claim gate certified a claim its own evidence contradicted. Each was a check
that could pass while the property it named was false.

The Phase 18 handover predicted the fourth instance would appear here as
**"the card renders" being accepted as "the card is honest"**. The gate in
`PROJECT_PLAN.md` -- "app runs in Docker and reproduces a known example" --
is exactly that gate: it checks rendering and reproducibility and says nothing
about what is rendered.

So this module is written first, and each test below is paired with a
*constructional* mechanism in `src/dashboard/` rather than a convention:

    (c) assert_publication_safe    -> called inside DashboardView.__post_init__,
                                      so an unsafe view cannot be constructed at
                                      all. The test proves there is no second
                                      constructor.
    (d) PROVISIONAL_STAMP          -> a mandatory field on ScoreSurface that
                                      raises when absent. A number with no stamp
                                      is unconstructable, not merely untested.
    (e) inert constructs           -> read off the live scorer's own
                                      `Direction.POLAR` + zero weight, never a
                                      hardcoded name list, so a policy change
                                      moves the marking with it.
    (f) forbidden vocabulary       -> screened over the *rendered* surface and
                                      the Streamlit source, not over a template.

A test that could be satisfied by editing a string constant is not one of these.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from src.dashboard.backend import LexiconBackend, ReplayBackend
from src.dashboard.charts import (
    INERT_HATCH_ID,
    construct_contribution_chart,
    construct_probability_chart,
    risk_meter,
)
from src.dashboard.view import (
    FORBIDDEN_SUBSTRINGS,
    DashboardView,
    ScoreSurface,
    assert_no_forbidden_language,
    build_view,
)
from src.evaluation.harness import PROVISIONAL_STAMP
from src.explainability.cards import PublicationUnsafe
from src.risk.fusion import Direction, LinearRiskScorer, PolarityPolicy

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "dashboard" / "app.py"
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"

#: The four constructs `docs/findings.md` sec.3.3 records as inert under the
#: conservative default policy. Restated here as an *expectation of the test*,
#: never as an input to the code under test -- the code derives its own list, and
#: this constant exists so the test fails loudly if the two ever diverge.
EXPECTED_INERT = frozenset(
    {
        "appraisal_orientation",
        "attentional_focus",
        "coping_style",
        "motivation_orientation",
    }
)

LIVE_TEXT = "My hands will not stop shaking and I keep replaying the start in my head."


@pytest.fixture(scope="module")
def replay_views() -> tuple[DashboardView, ...]:
    backend = ReplayBackend.from_fixture(FIXTURE_PATH)
    return tuple(build_view(example_id=e, backend=backend) for e in backend.example_ids)


@pytest.fixture(scope="module")
def live_view() -> DashboardView:
    return build_view(text=LIVE_TEXT, backend=LexiconBackend())


# ---------------------------------------------------------------------------
# (c) assert_publication_safe is unavoidable
# ---------------------------------------------------------------------------


def test_no_view_can_be_built_without_the_publication_guard(replay_views):
    """Every constructed view has been through `assert_publication_safe`.

    Asserted by observation rather than by trust: the guard records itself on the
    view. A view that skipped it carries `publication_checked=False`, which no
    code path can produce, because the flag is set by the guard call itself.
    """
    assert replay_views
    for view in replay_views:
        assert view.publication_checked is True
        assert view.exportable is True


def test_a_non_synthetic_card_cannot_be_exported(live_view):
    """User-pasted text is the user's own -- shown back, never exported.

    `assert_publication_safe` refuses a non-synthetic card. The live path does
    not suppress that refusal; it catches it, marks the view non-exportable, and
    surfaces the reason. Attempting to export anyway re-raises.
    """
    assert live_view.publication_checked is True
    assert live_view.exportable is False
    with pytest.raises(PublicationUnsafe):
        live_view.export_markdown()
    assert any("not stored" in n.lower() for n in live_view.notices)


def test_build_view_is_the_only_public_constructor():
    """No code path can reach a `DashboardView` around the guard.

    The guard lives in `__post_init__`, so even a direct construction is checked.
    This test defends the weaker property that matters for review: the Streamlit
    shell does not construct one itself, and so cannot pass hand-made arguments
    that dodge the fixture-shaped inputs the tests exercise.
    """
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "DashboardView" not in called
    assert "ExplanationCard" not in called
    assert "CardSet" not in called
    assert "build_card" not in called


def test_the_streamlit_shell_holds_no_business_logic():
    """`dashboard/app.py` is a renderer. Logic lives in tested pure Python.

    Enforced structurally: the shell defines no function that computes a score,
    and every name it imports from `src.` comes from the dashboard package's
    public surface. `notebooks/01_eda.ipynb` is the precedent -- a thin viewer
    over tested functions.
    """
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src."):
            assert node.module.startswith("src.dashboard"), (
                f"{APP_PATH.name} imports {node.module}; the shell may only reach the "
                "project through src.dashboard, or business logic will migrate into "
                "the file the Streamlit runtime executes."
            )


def test_the_stamp_is_rendered_outside_any_collapsed_container():
    """A stamp inside a collapsed expander is in the DOM and not on the screen.

    Found during review of this phase's own code: the provenance stamp was only
    inside `st.expander(...)`, which Streamlit renders collapsed. Every
    screenshot -- and every screenshot that becomes a paper figure -- would have
    carried a number with no visible provenance while a DOM-level test passed.
    The same defect shape the phase was warned about, one level down.

    So the stamp must appear before the first `st.expander` call in the shell.
    """
    EXEMPT_BECAUSE = (
        "Owner instruction, 2026-09-14, given after the consequence was put in "
        "writing: the stamp is no longer rendered above the fold on page 1. "
        "Phase 26 gate #3 therefore does not hold for that page, and a "
        "screenshot of the risk index taken from it travels without the sentence "
        "saying the number is agreement with planted labels and is not accuracy. "
        "tests/test_dashboard_pages.py carries the matching exemption. This "
        "assertion is narrowed rather than deleted so the rule still fails if "
        "the stamp leaves the page altogether, and so restoring it is one line."
    )
    source = APP_PATH.read_text(encoding="utf-8")
    assert "view.risk.stamp" in source, EXEMPT_BECAUSE
    assert "st.expander" in source


# ---------------------------------------------------------------------------
# (d) the PROVISIONAL stamp is on every page that shows a number
# ---------------------------------------------------------------------------


def test_a_score_surface_without_the_stamp_cannot_be_constructed():
    ScoreSurface(label="risk index", value=0.5, display="0.50")  # default stamp
    with pytest.raises(ValueError):
        ScoreSurface(label="risk index", value=0.5, display="0.50", stamp="")
    with pytest.raises(ValueError):
        ScoreSurface(label="risk index", value=0.5, display="0.50", stamp="looks fine to me")


def test_every_number_on_every_view_carries_the_stamp(replay_views, live_view):
    for view in (*replay_views, live_view):
        assert view.surfaces, "a view that shows no number is not a dashboard"
        for surface in view.surfaces:
            assert PROVISIONAL_STAMP.split(" -- ")[0] in surface.stamp
        # And the stamp reaches the rendered page, not just the data model.
        assert PROVISIONAL_STAMP.split(" -- ")[0] in view.render_text()


def test_the_risk_number_is_never_presented_as_calibrated(replay_views):
    for view in replay_views:
        assert view.risk.value == pytest.approx(view.card.risk.index)
        assert "not calibrated" in view.render_text().lower()
        assert "ranking only" in view.render_text().lower()


# ---------------------------------------------------------------------------
# (e) the four inert constructs render as visibly non-contributing
# ---------------------------------------------------------------------------


def test_the_inert_set_is_derived_from_the_scorer_not_hardcoded():
    """Inertness is a property of the policy, so it is read from the policy.

    Under `NEUTRAL` a POLAR construct gets weight 0.0 and cannot move the index.
    Under `PESSIMISTIC` the same construct gets a non-zero weight and *does*
    move it. If the marking were a name list, the second case would be silently
    mislabelled -- the picture would assert something the numbers do not, which
    is the exact failure C2.5 forbids.
    """
    neutral = LinearRiskScorer()
    inert = {
        c.construct
        for c in neutral.score({k: 0.9 for k in neutral.magnitudes}).contributions
        if c.direction is Direction.POLAR and c.weight == 0.0
    }
    assert inert == EXPECTED_INERT

    pessimistic = LinearRiskScorer(polarity_policy=PolarityPolicy.PESSIMISTIC)
    still_inert = {
        c.construct
        for c in pessimistic.score({k: 0.9 for k in pessimistic.magnitudes}).contributions
        if c.direction is Direction.POLAR and c.weight == 0.0
    }
    assert still_inert == set(), "under PESSIMISTIC nothing is inert; the marking must follow"


def test_all_ten_constructs_are_drawn_and_the_inert_four_are_marked(replay_views):
    for view in replay_views:
        assert len(view.bars) == 10, "ten bars, or the taxonomy is being quietly truncated"
        marked = {b.construct for b in view.bars if b.inert}
        assert marked == EXPECTED_INERT
        for bar in view.bars:
            if bar.inert:
                assert bar.contribution == 0.0
                assert "does not move" in bar.note
            else:
                assert "does not move" not in bar.note


def test_the_inert_marking_survives_grayscale_and_colourblind_rendering(replay_views):
    """Marking by colour alone would vanish in the paper's grayscale figure.

    Three redundant channels are required and checked: a hatch pattern fill, a
    dashed outline, and a literal text label on the row. `PROJECT_PLAN.md` Phase
    24's gate is "figures legible in grayscale"; a marking that fails it here
    fails it there too, and there it would be found after the figure is drawn.
    """
    svg = construct_contribution_chart(replay_views[0].bars)
    hatch = re.search(rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"', svg)
    assert hatch, "no hatch pattern defined; the marking would be colour-only"
    assert f"url(#{hatch.group(1)})" in svg, "the pattern is defined but never referenced"
    assert "stroke-dasharray" in svg
    for construct in EXPECTED_INERT:
        assert f"{construct.replace('_', ' ')} (inert)" in svg
    # Once per row label plus once per in-plot annotation: the word itself is the
    # third channel, and it is the one that survives a stylesheet being stripped.
    assert svg.count("inert") >= 2 * len(EXPECTED_INERT)


def test_two_charts_on_one_page_do_not_share_a_pattern_id(replay_views):
    """Found by looking at a screenshot, then pinned here.

    SVG ids share one namespace per document and Streamlit keeps every tab's DOM
    mounted, so two charts both defining `inert-hatch` left one of them with an
    empty marker -- while these tests, rendering each chart alone, stayed green.
    The unit tests could not see it; only the rendered page could. That is the
    argument for the verification step, not an argument against the tests.
    """
    a = construct_contribution_chart(replay_views[0].bars)
    b = construct_contribution_chart(replay_views[1].bars)
    c = construct_probability_chart(replay_views[0].bars)
    ids = [re.search(rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"', s).group(1) for s in (a, b, c)]
    assert len(set(ids)) == 3, f"pattern ids collide across charts on one page: {ids}"
    # Deterministic: the same data must produce the same id, or screenshots churn.
    assert (
        re.search(
            rf'id="({INERT_HATCH_ID}-[0-9a-f]+)"',
            construct_contribution_chart(replay_views[0].bars),
        ).group(1)
        == ids[0]
    )


def test_the_view_states_the_six_of_ten_qualification_in_words(replay_views):
    """C2.5: the decomposition is not "ten-construct" without qualification."""
    for view in replay_views:
        text = view.render_text().lower()
        assert "six" in text and "ten" in text
        assert not re.search(r"ten[- ]construct risk (decomposition|index)", text)


# ---------------------------------------------------------------------------
# (f) forbidden vocabulary never reaches the rendered surface
# ---------------------------------------------------------------------------


def test_the_forbidden_list_is_the_one_the_findings_document_fixes():
    assert set(FORBIDDEN_SUBSTRINGS) >= {
        "expert-validated",
        "practitioner-validated",
        "coach-validated",
        "accuracy",
    }


def test_forbidden_language_is_rejected_at_construction():
    for bad in FORBIDDEN_SUBSTRINGS:
        with pytest.raises(ValueError):
            assert_no_forbidden_language(f"a sentence containing {bad} in it")
        with pytest.raises(ValueError):
            assert_no_forbidden_language(f"A Sentence Containing {bad.upper()} In It")
    with pytest.raises(ValueError):
        ScoreSurface(label="detection accuracy", value=0.5, display="0.50")


def test_the_only_permitted_use_of_accuracy_is_the_stamps_own_denial():
    """The one narrow exception, pinned so it cannot widen unnoticed.

    `PROVISIONAL_STAMP` reads "... NOT accuracy", so a flat ban makes the
    mandated stamp unshippable. The exception is the literal denial and nothing
    else -- in particular a claim wearing a negation elsewhere in the sentence
    must still fail, or the exception becomes the hole.
    """
    assert_no_forbidden_language(PROVISIONAL_STAMP)
    assert_no_forbidden_language("this figure is not accuracy")
    for smuggled in (
        "there is no reason to doubt the accuracy",
        "not a bad accuracy",
        "accuracy not reported here",
        "we do not overstate the accuracy",
    ):
        with pytest.raises(ValueError):
            assert_no_forbidden_language(smuggled)


def test_no_rendered_surface_contains_a_forbidden_string(replay_views, live_view):
    """Screened over what a reader sees, not over a template.

    "accuracy" is checked through `assert_no_forbidden_language` rather than by
    substring, because the required provenance stamp legitimately contains the
    denial; every other term is banned outright with no exception.
    """
    surfaces = [v.render_text() for v in (*replay_views, live_view)]
    surfaces.append(APP_PATH.read_text(encoding="utf-8"))
    surfaces.append(construct_contribution_chart(replay_views[0].bars))
    surfaces.append(construct_probability_chart(replay_views[0].bars))
    surfaces.append(risk_meter(replay_views[0].risk))
    for surface in surfaces:
        low = surface.lower()
        for term in FORBIDDEN_SUBSTRINGS:
            if term == "accuracy":
                continue
            assert term not in low, f"forbidden term {term!r} reached a rendered surface"
        assert_no_forbidden_language(surface)


def test_the_expert_study_is_described_only_in_the_mandated_wording(replay_views):
    """`docs/findings.md` sec.2.4 fixes this wording verbatim. OPEN-004 was
    closed by decision, not by recruitment, and closing a tracking item does not
    upgrade a claim."""
    for view in replay_views:
        text = view.render_text()
        if "pilot" in text.lower():
            assert "pilot expert review" in text
            assert "not practitioner validation" in text


def test_no_diagnosis_framing_anywhere(replay_views, live_view):
    banned = ("diagnos", "clinical assessment", "mental health status", "disorder")
    for view in (*replay_views, live_view):
        low = view.render_text().lower()
        for term in banned:
            # "not a clinical instrument" is required; a diagnosis *claim* is not.
            assert term not in low.replace("not a clinical instrument", "")


# ---------------------------------------------------------------------------
# The gate as originally written: reproduces a known example
# ---------------------------------------------------------------------------


def test_the_known_example_reproduces_the_phase_17_card_byte_identically(replay_views):
    """The demo and the paper figure are the same artefact or one of them is wrong.

    C2.6 forbids re-deriving the highlighting. This test is what makes that
    binding: the fixture's rendered card must match the corresponding block of
    `reports/explain/cards.md` character for character. If the dashboard ever
    grows its own renderer, this fails.
    """
    cards_md = (REPO_ROOT / "reports" / "explain" / "cards.md").read_text(encoding="utf-8")
    blocks = {}
    for block in cards_md.split("\n### ")[1:]:
        record_id = block.split("`")[1]
        blocks[record_id] = ("### " + block).rstrip() + "\n"

    for view in replay_views:
        expected = blocks[view.card.record_id]
        actual = view.export_markdown().rstrip() + "\n"
        assert actual == expected, (
            f"{view.card.record_id}: the dashboard's card no longer matches "
            "reports/explain/cards.md. The demo and the paper figure have drifted."
        )


def test_the_fixture_is_committed_and_self_describing():
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["source"].endswith("cards.md")
    assert PROVISIONAL_STAMP.split(" -- ")[0] in payload["provenance"]
    assert len(payload["examples"]) >= 3
    for example in payload["examples"]:
        assert example["synthetic"] is True
        assert len(example["probabilities"]) == 10


# ---------------------------------------------------------------------------
# Architecture: no ML stack, nothing persisted
# ---------------------------------------------------------------------------


def test_the_dashboard_package_imports_without_torch(monkeypatch):
    """C4: the test suite runs with no ML stack installed. Held since Phase 15."""
    import sys

    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


def test_pasted_text_is_never_written_to_disk(tmp_path, monkeypatch):
    """The user's own words are shown back and then forgotten.

    Enforced by watching the filesystem rather than by reading the code: any
    write performed while a live view is built fails the test, whichever module
    performed it.
    """
    written: list[str] = []
    real_open = open

    def watched_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")):
            written.append(str(file))
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", watched_open)
    original = Path.write_text
    monkeypatch.setattr(
        Path,
        "write_text",
        lambda self, *a, **k: written.append(str(self)) or original(self, *a, **k),
    )

    view = build_view(text=LIVE_TEXT, backend=LexiconBackend())
    _ = view.render_text()
    assert written == [], f"the live path wrote to {written}"


# --------------------------------------------------------------------------
# Phase 22 regression: the shell must be importable the way Streamlit runs it.
#
# `streamlit run dashboard/app.py` executes the file with the file's OWN
# directory on sys.path and the repository root nowhere on it. Every test above
# imports `src.` under pytest, which inserts the root itself because
# tests/__init__.py exists -- so the suite and the Streamlit runtime disagreed
# about what "importable" means, and `from src.dashboard import ...` raised
# ModuleNotFoundError in every container while 23 dashboard tests passed.
#
# Asserting that a bootstrap line EXISTS would be a Phase 18 no-gate: it checks
# the remedy is present, not that the property holds. This reproduces the
# runtime's sys.path instead, executes the app's real prologue in a subprocess
# with a cleaned environment, and requires the src import to succeed from it.
# --------------------------------------------------------------------------


def _app_prologue() -> str:
    """The app's source up to (but excluding) its first `src.` import."""
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src."):
            return "\n".join(source.splitlines()[: node.lineno - 1])
    raise AssertionError("app.py no longer imports anything from src.")


def test_app_reaches_src_the_way_streamlit_runs_it(tmp_path):
    """Reproduce the Streamlit runtime's sys.path and require the import to work."""
    import os
    import subprocess
    import sys

    pytest.importorskip("streamlit")

    root = str(APP_PATH.parent.parent)
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import os, sys\n"
        # Streamlit PREPENDS the script's directory and leaves the rest of
        # sys.path (stdlib, site-packages) alone. What it does not do is put the
        # repository root there -- so drop the root and the implicit cwd entry,
        # which is exactly the shape a container sees.
        f"root = {root!r}\n"
        "sys.path[:] = [p for p in sys.path if p not in ('', root, os.getcwd())]\n"
        f"sys.path.insert(0, {str(APP_PATH.parent)!r})\n"
        "assert root not in sys.path, 'probe failed to remove the repo root'\n"
        # exec needs the app's own __file__: the bootstrap derives the repo
        # root from it, and probe.py's __file__ would silently point elsewhere.
        f"g = {{'__file__': {str(APP_PATH)!r}, '__name__': '__main__'}}\n"
        f"exec(compile({_app_prologue()!r}, {str(APP_PATH)!r}, 'exec'), g)\n"
        "import src.dashboard\n"
        "print('OK')\n",
        encoding="utf-8",
    )

    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = ""  # a container that forgot the env var must still work
    result = subprocess.run(
        [sys.executable, str(probe)],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),  # never the repo: cwd must not be what rescues it
        env=env,
    )
    assert result.returncode == 0, (
        "dashboard/app.py cannot reach src/ with only its own directory "
        f"prepended to sys.path -- this is what every container shows:\n{result.stderr}"
    )
    assert "OK" in result.stdout


def test_the_images_put_the_repo_root_on_the_import_path():
    """Belt and braces to the bootstrap above, and the fix for the container.

    The bootstrap makes app.py self-sufficient; this keeps `docker compose run`
    working for every OTHER entry point (scripts/, python -m), which have the
    same sys.path shape and no bootstrap of their own.
    """
    dockerfile = (APP_PATH.parent.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "PYTHONPATH=/app" in dockerfile, (
        "the light image no longer puts /app on the import path; "
        "`from src...` will fail for every entry point that is not app.py"
    )
