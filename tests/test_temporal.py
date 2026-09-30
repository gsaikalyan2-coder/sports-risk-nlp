"""Phase 22 -- the panel corpus, the planted drift, and the control that judges it.

The tests are grouped by the claim they defend rather than by module, because
the claims are what a reviewer will challenge:

1. The blocker that gated this phase is real and stays measured.
2. The drift is planted the way the owner decision says it is.
3. A series cannot hold a number it did not earn.
4. Suppression is symmetric, reported, and not a silent drop.
5. The control discriminates: planted drift survives it, noise does not.
6. Nothing on any surface claims more than this corpus can support.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.view import ForbiddenLanguage, assert_no_forbidden_language
from src.evaluation.trajectory import (
    SLOPE_SIGN_NOTE,
    TRAJECTORY_FRAMING,
    AthleteSeries,
    features_for,
    shuffled_control,
)
from src.ingestion.records import RawRecord
from src.ingestion.temporal import (
    DAY_LADDER,
    DRIFTING_CONSTRUCTS,
    FLAT_BY_DESIGN,
    MIN_TIMEPOINTS_FOR_SLOPE,
    SOURCE_ID,
    TIMING_BIAS,
    AthletePanel,
    PanelSpec,
    athlete_id_of,
    build_panel_corpus,
    drift_for,
    generate_panel,
    panel_descriptor,
    timepoint_index_of,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
V1_RECORDS = REPO_ROOT / "data" / "raw" / "synth_precomp_v1" / "records.jsonl"


# --------------------------------------------------------------------------
# 1. The blocker, kept measured
# --------------------------------------------------------------------------


@pytest.mark.skipif(not V1_RECORDS.exists(), reason="v1 corpus not built in this checkout")
def test_v1_still_carries_no_athlete_id():
    """The measurement that gated Phase 22, locked in as a regression.

    If this ever fails, someone has retrofitted an identity onto v1 -- which is
    the one thing `src/ingestion/temporal.py` refuses to do, because assigning
    i.i.d. draws to invented athletes manufactures panel structure that was
    never generated.
    """
    with V1_RECORDS.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = RawRecord.from_json_line(line)
            assert athlete_id_of(record) is None
            assert record.extra == {}


def test_this_module_never_imports_the_cue_biased_demo_generator():
    """The mistake this module made in its first draft, kept caught.

    `scenarios._realise_graded_at` prefers templates containing the lexicon's
    own cue phrases. In a demo that is legitimate; in a corpus it inflates the
    lexicon baseline by construction (OPEN-021), and the failure is silent.
    `tests/test_scenarios.py` guards the whole of `src/ingestion/`; this asserts
    it from this module's own side so the reason travels with the code that
    broke it.
    """
    import src.ingestion.temporal as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "from .scenarios import" not in source
    assert "import scenarios" not in source


def test_governed_constructs_cannot_also_be_an_athlete_trait():
    """The two sources of variation must stay separable."""
    from src.ingestion.temporal import generate_panel_record

    with pytest.raises(ValueError, match="planted twice"):
        generate_panel_record(
            athlete_id="A0000",
            sport="rowing",
            trait_constructs=("somatic_anxiety",),
            days_before=3,
            timepoint_index=0,
            seed=1,
        )


def test_athlete_id_accessor_is_honest_about_non_panel_records():
    plain = RawRecord(record_id="x-1", source_id="x", text="hello")
    assert athlete_id_of(plain) is None
    assert timepoint_index_of(plain) is None


# --------------------------------------------------------------------------
# 2. The drift is planted as the owner decision says
# --------------------------------------------------------------------------


def test_somatic_drift_is_monotone_towards_the_competition():
    """Both channels rise together as days -> 0. Neither may dip."""
    ladder = [drift_for("somatic_anxiety", d) for d in sorted(DAY_LADDER, reverse=True)]
    probs = [d.plant_probability for d in ladder]
    lows = [d.intensity_band[0] for d in ladder]
    highs = [d.intensity_band[1] for d in ladder]
    assert probs == sorted(probs), "plant probability must not dip approaching the event"
    assert lows == sorted(lows)
    assert highs == sorted(highs)
    assert probs[-1] > probs[0], "the whole point is that it rises"


def test_flat_constructs_do_not_consult_the_day():
    """The two negative controls, asserted rather than trusted."""
    for construct in FLAT_BY_DESIGN:
        bands = {drift_for(construct, day) for day in DAY_LADDER}
        assert len(bands) == 1, f"{construct} is flat by design and must not vary with the day"


def test_only_somatic_anxiety_drifts():
    assert DRIFTING_CONSTRUCTS == ("somatic_anxiety",)
    assert set(TIMING_BIAS) == {"somatic_anxiety"}
    assert "somatic_anxiety" not in FLAT_BY_DESIGN


def test_drift_for_refuses_post_competition_days():
    with pytest.raises(ValueError, match="days BEFORE"):
        drift_for("somatic_anxiety", -1)


def test_ungoverned_construct_has_no_drift():
    assert drift_for("resilience", 3) is None


def test_the_drift_actually_reaches_the_text():
    """Not a bookkeeping test: the cue words must appear more often near the event.

    A generator that records a planted construct in `generation_spec` but never
    renders it detectably is the failure mode `scenarios.py` already documents.
    """
    from src.evaluation.baselines import CONSTRUCT_CUES

    cues = CONSTRUCT_CUES["somatic_anxiety"]

    def hit_rate(day: int) -> float:
        from src.ingestion.temporal import generate_panel_record

        hits = 0
        for i in range(120):
            record = generate_panel_record(
                athlete_id=f"T{i:04d}",
                sport="athletics",
                trait_constructs=(),
                days_before=day,
                timepoint_index=0,
                seed=90_000 + i,
            )
            if any(cue in record.text.lower() for cue in cues):
                hits += 1
        return hits / 120

    far, near = hit_rate(30), hit_rate(0)
    assert near > far + 0.20, f"somatic cues must rise towards the event (far={far}, near={near})"


# --------------------------------------------------------------------------
# 3. Panels and series cannot hold what they did not earn
# --------------------------------------------------------------------------


def test_panels_are_ordered_distinct_and_identified():
    for panel in build_panel_corpus(PanelSpec(n_athletes=30)):
        assert panel.days == tuple(sorted(panel.days, reverse=True))
        assert len(set(panel.days)) == len(panel.days)
        for index, record in enumerate(panel.records):
            assert athlete_id_of(record) == panel.athlete_id
            assert timepoint_index_of(record) == index
            assert record.source_id == SOURCE_ID
            assert record.time_to_competition_days is not None


def test_panel_refuses_a_record_with_no_day_offset():
    record = RawRecord(record_id="p-1", source_id=SOURCE_ID, text="something", sport="rowing")
    with pytest.raises(ValueError, match="no day-offset"):
        AthletePanel(athlete_id="A0", sport="rowing", trait_constructs=(), records=(record,))


def test_panel_refuses_two_records_on_one_day():
    rows = tuple(
        RawRecord(
            record_id=f"p-{i}",
            source_id=SOURCE_ID,
            text="something",
            time_to_competition_days=3,
        )
        for i in range(2)
    )
    with pytest.raises(ValueError, match="same day-offset"):
        AthletePanel(athlete_id="A0", sport="rowing", trait_constructs=(), records=rows)


def test_series_refuses_a_value_without_a_day():
    with pytest.raises(ValueError, match="never imputed"):
        AthleteSeries(athlete_id="A0", channel="risk_index", days=(3, 1), values=(0.5,))


def test_generation_is_deterministic():
    first = generate_panel(athlete_index=7, spec=PanelSpec(n_athletes=30, seed=22))
    second = generate_panel(athlete_index=7, spec=PanelSpec(n_athletes=30, seed=22))
    assert [r.text for r in first.records] == [r.text for r in second.records]
    assert first.days == second.days


def test_a_different_seed_gives_a_different_corpus():
    a = generate_panel(athlete_index=7, spec=PanelSpec(n_athletes=30, seed=22))
    b = generate_panel(athlete_index=7, spec=PanelSpec(n_athletes=30, seed=23))
    assert [r.text for r in a.records] != [r.text for r in b.records]


# --------------------------------------------------------------------------
# 4. Suppression: reported, symmetric, never a silent drop
# --------------------------------------------------------------------------


def test_a_thin_series_has_no_slope_and_says_so():
    thin = AthleteSeries("A0", "risk_index", (10, 5, 0), (0.4, 0.5, 0.9))
    features = thin.n, features_for(thin)
    assert features[0] < MIN_TIMEPOINTS_FOR_SLOPE
    assert features[1].slope is None
    assert features[1].suppressed is True
    # The other features survive: they need two points, not four.
    assert features[1].volatility is not None
    assert features[1].last_day_delta is not None


def test_a_full_series_gets_a_slope():
    full = AthleteSeries("A0", "risk_index", (10, 5, 2, 0), (0.4, 0.5, 0.6, 0.7))
    assert features_for(full).suppressed is False
    assert features_for(full).slope is not None


def test_single_point_series_has_no_spread_to_report():
    lone = AthleteSeries("A0", "risk_index", (3,), (0.6,))
    f = features_for(lone)
    assert f.volatility is None and f.last_day_delta is None and f.slope is None


def test_the_spec_forces_the_suppression_rate_to_be_measurable():
    """Bands that do not straddle the floor make the rate 0% or 100%."""
    with pytest.raises(ValueError, match="straddle"):
        PanelSpec(long_series_points=(5, 6), short_series_points=(4, 4))


def test_suppression_is_applied_on_both_sides_of_the_control():
    thin = [AthleteSeries(f"S{i}", "c", (5, 0), (0.4, 0.6)) for i in range(10)]
    full = [AthleteSeries(f"F{i}", "c", (9, 5, 2, 0), (0.4, 0.5, 0.6, 0.7)) for i in range(10)]
    result = shuffled_control(thin + full, channel="c", repeats=200)
    assert result.n_series == 10
    assert result.n_suppressed == 10
    assert result.suppression_rate == pytest.approx(0.5)


def test_a_wholly_thin_channel_reports_nothing_rather_than_zero():
    thin = [AthleteSeries(f"S{i}", "c", (5, 0), (0.4, 0.6)) for i in range(10)]
    result = shuffled_control(thin, channel="c", repeats=200)
    assert result.observed_mean_slope is None
    assert result.p_value is None
    assert result.survives_control is False
    assert "nothing to test" in result.verdict


# --------------------------------------------------------------------------
# 5. The control discriminates
# --------------------------------------------------------------------------


def test_slope_sign_follows_the_stated_convention():
    """Rising towards the competition must read as a POSITIVE slope."""
    rising = AthleteSeries("A0", "c", (10, 5, 2, 0), (0.3, 0.4, 0.5, 0.6))
    falling = AthleteSeries("A1", "c", (10, 5, 2, 0), (0.6, 0.5, 0.4, 0.3))
    assert features_for(rising).slope > 0
    assert features_for(falling).slope < 0


def test_planted_drift_survives_the_control():
    series = [
        AthleteSeries(f"A{i}", "c", (10, 7, 3, 1, 0), (0.30, 0.38, 0.46, 0.54, 0.62))
        for i in range(40)
    ]
    result = shuffled_control(series, channel="c", repeats=1000)
    assert result.survives_control
    assert result.observed_mean_slope > result.null_hi


def test_a_flat_series_does_not_survive_the_control():
    series = [
        AthleteSeries(f"A{i}", "c", (10, 7, 3, 1, 0), (0.5, 0.5, 0.5, 0.5, 0.5)) for i in range(40)
    ]
    result = shuffled_control(series, channel="c", repeats=1000)
    assert not result.survives_control
    assert "no signal beyond the shuffle" in result.verdict


def test_the_control_is_reproducible_across_runs():
    series = [AthleteSeries(f"A{i}", "c", (10, 7, 3, 0), (0.3, 0.45, 0.5, 0.6)) for i in range(20)]
    first = shuffled_control(series, channel="c", repeats=500, seed=22)
    second = shuffled_control(series, channel="c", repeats=500, seed=22)
    assert first.null_mean == second.null_mean
    assert first.null_sd == second.null_sd
    assert first.p_value == second.p_value


def test_the_permutation_p_value_is_never_zero():
    series = [
        AthleteSeries(f"A{i}", "c", (10, 7, 3, 1, 0), (0.1, 0.3, 0.5, 0.7, 0.9)) for i in range(40)
    ]
    result = shuffled_control(series, channel="c", repeats=500)
    assert result.p_value > 0.0
    assert result.p_value == pytest.approx(1 / 501)


# --------------------------------------------------------------------------
# 6. Nothing claims more than the corpus supports
# --------------------------------------------------------------------------


def test_the_channel_family_is_holm_corrected():
    """Eleven simultaneous tests at a fixed 0.05 is the wrong test.

    Built from real `analyse` output rather than hand-made `ChannelResult`s, so
    the correction is exercised where it actually runs.
    """
    from src.evaluation.trajectory import FAMILY_ALPHA, analyse
    from src.ingestion.temporal import build_panel_corpus

    panels = build_panel_corpus(PanelSpec(n_athletes=40, seed=5))
    readings = {}
    for i, panel in enumerate(panels):
        for j, record in enumerate(panel.records):
            # A deterministic rising channel and a pure-noise channel.
            day = record.time_to_competition_days
            readings[record.record_id] = {
                "rising": 0.5 - 0.01 * day,
                "noise": ((i * 7 + j * 13) % 11) / 20.0,
            }
    report = analyse(
        panels, readings, channels=["rising", "noise"], drifting=("rising",), repeats=500
    )
    assert report.channel("rising").holm_reject is True
    assert report.channel("noise").holm_reject is False
    # Strictest threshold goes to the smallest p; the family size is the divisor.
    assert report.channel("rising").holm_threshold == pytest.approx(FAMILY_ALPHA / 2)
    assert report.design_holds


def test_holm_is_stricter_than_the_uncorrected_flag():
    """A channel may sit outside its own null and still not survive the family."""
    from src.evaluation.trajectory import ChannelResult, ControlResult

    borderline = ControlResult(
        channel="c",
        n_series=50,
        n_suppressed=0,
        observed_mean_slope=0.01,
        null_mean=0.0,
        null_sd=0.004,
        null_lo=-0.008,
        null_hi=0.008,
        p_value=0.025,
        repeats=2000,
    )
    assert borderline.survives_control is True  # uncorrected view
    channel = ChannelResult(
        channel="c",
        plain_name="c",
        features=(),
        control=borderline,
        flat_by_design=False,
        drifting_by_design=False,
        holm_reject=False,
        holm_threshold=0.005,
    )
    assert channel.signal is False
    assert "once the channel family is corrected" in channel.verdict
    assert channel.matches_expectation


def test_the_framing_leads_with_what_this_is_not():
    assert "Sanity check, not a finding" in TRAJECTORY_FRAMING
    assert "PLANTED" in TRAJECTORY_FRAMING
    assert "No real athlete" in TRAJECTORY_FRAMING


def test_the_sign_convention_is_stated_not_assumed():
    assert "-time_to_competition_days" in SLOPE_SIGN_NOTE
    assert "POSITIVE" in SLOPE_SIGN_NOTE


def test_module_surfaces_carry_no_forbidden_language():
    assert_no_forbidden_language(TRAJECTORY_FRAMING)
    assert_no_forbidden_language(SLOPE_SIGN_NOTE)
    assert_no_forbidden_language(panel_descriptor().notes)


def test_provenance_says_the_drift_was_planted():
    """A provenance record that understates what a generator did is the one
    document in the corpus that must not."""
    notes = panel_descriptor().notes
    assert "PLANTED" in notes
    assert "Martens1990" in notes
    assert "NOT evidence about athletes" in notes
    assert "synth_precomp_v1 is untouched" in notes


#: Surfaces a reader sees, checked as a group.
TEMPORAL_SURFACES = (TRAJECTORY_FRAMING, SLOPE_SIGN_NOTE)


@pytest.mark.parametrize("word", ["validated", "validation", "confirms that", "shows that"])
def test_no_validation_wording_on_any_temporal_surface(word):
    """This layer recovers a drift it planted. It confirms nothing about anyone."""
    for text in (*TEMPORAL_SURFACES, panel_descriptor().notes):
        assert word not in text.lower()


def _claimed_not_denied(text: str, word: str) -> list[str]:
    """Occurrences of `word` that are NOT inside an explicit denial.

    The same distinction `view.py::_accuracy_claims` already makes for
    'accuracy': the mistake is the claim, and the literal denial is the
    correction, so a blanket substring ban would forbid the sentence that
    does the work. Mentioning that this is not a clinical finding is the
    point; asserting that it is one is the defect.
    """
    low = text.lower()
    out = []
    start = 0
    while (i := low.find(word, start)) != -1:
        window = low[max(0, i - 40) : i]
        if not any(neg in window for neg in ("not ", "no ", "never ", "cannot ", "n't ")):
            out.append(low[max(0, i - 40) : i + 40])
        start = i + len(word)
    return out


@pytest.mark.parametrize("word", ["clinical", "diagnos"])
def test_clinical_wording_appears_only_as_a_denial(word):
    for text in (*TEMPORAL_SURFACES, panel_descriptor().notes):
        assert _claimed_not_denied(text, word) == []


def test_the_denial_guard_catches_a_real_claim():
    """Guard the guard: the helper must fail on an actual claim."""
    assert _claimed_not_denied("this is a clinical finding about the athlete", "clinical")
    assert _claimed_not_denied("it is not a clinical finding", "clinical") == []


REPORT = REPO_ROOT / "reports" / "temporal.md"


@pytest.mark.skipif(not REPORT.exists(), reason="run scripts/run_temporal.py first")
def test_the_report_leads_with_the_framing_and_claims_nothing_more():
    text = REPORT.read_text(encoding="utf-8")
    assert_no_forbidden_language(text)
    head = text[: text.index("## Corpus")]
    assert "Sanity check, not a finding" in head, "the framing must be above the first number"
    assert "What this does not show" in text
    for word in ("validated", "validation"):
        assert word not in text.lower()


def test_forbidden_language_guard_is_actually_live():
    """Guard the guard: a test that only ever passes proves nothing."""
    with pytest.raises(ForbiddenLanguage):
        assert_no_forbidden_language("slope detection accuracy was high")


@pytest.mark.skipif(not (REPO_ROOT / "data" / "raw" / SOURCE_ID).exists(), reason="not built")
def test_the_written_corpus_carries_identity_and_time_on_every_record():
    path = REPO_ROOT / "data" / "raw" / SOURCE_ID / "records.jsonl"
    seen: set[tuple[str, int]] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            athlete = row["extra"]["athlete_id"]
            day = row["time_to_competition_days"]
            assert athlete and isinstance(day, int)
            assert (athlete, day) not in seen, "one athlete may not speak twice on one day"
            seen.add((athlete, day))
