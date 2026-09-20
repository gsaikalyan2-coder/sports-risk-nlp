"""Match-day scenario generation: determinism and construct-set variation.

Offline, no network, no ML backend -- these tests exercise the template
grammar and the bias table only, matching the contract `test_ingestion.py`
uses for `synthetic.generate_records`.
"""

from __future__ import annotations

import pytest

from src.ingestion.scenarios import (
    LIFE_CONTEXT_LABELS,
    LIFE_CONTEXTS,
    SPORTS,
    TIMING_LABELS,
    TIMINGS,
    MatchDayScenario,
    generate_scenario_record,
)


def _constructs(record) -> set[str]:
    return {p["construct"] for p in record.generation_spec["planted_constructs"]}


def test_invalid_sport_rejected() -> None:
    with pytest.raises(ValueError, match="unknown sport"):
        MatchDayScenario(sport="chess", timing="week_before", life_context="none")


def test_invalid_timing_rejected() -> None:
    with pytest.raises(ValueError, match="unknown timing"):
        MatchDayScenario(sport="tennis", timing="after", life_context="none")


def test_invalid_life_context_rejected() -> None:
    with pytest.raises(ValueError, match="unknown life_context"):
        MatchDayScenario(sport="tennis", timing="week_before", life_context="heartbreak")


def test_every_declared_option_is_a_valid_scenario() -> None:
    """The dropdowns' own option lists must never construct an invalid scenario."""
    for sport in SPORTS:
        for timing in TIMINGS:
            for life_context in LIFE_CONTEXTS:
                MatchDayScenario(sport=sport, timing=timing, life_context=life_context)


def test_labels_cover_every_option() -> None:
    assert set(TIMING_LABELS) == set(TIMINGS)
    assert set(LIFE_CONTEXT_LABELS) == set(LIFE_CONTEXTS)


def test_same_scenario_same_seed_is_deterministic() -> None:
    scenario = MatchDayScenario(sport="tennis", timing="morning_of", life_context="injury_comeback")
    first = generate_scenario_record(scenario, seed=7)
    second = generate_scenario_record(scenario, seed=7)
    assert first.text == second.text
    assert first.generation_spec == second.generation_spec


def test_same_scenario_different_seed_usually_varies_text() -> None:
    scenario = MatchDayScenario(sport="tennis", timing="morning_of", life_context="strong_season")
    texts = {generate_scenario_record(scenario, seed=s).text for s in range(10)}
    assert len(texts) > 1


@pytest.mark.parametrize(
    "life_context",
    [lc for lc in LIFE_CONTEXTS if lc != "none"],
)
def test_biased_life_context_plants_its_declared_constructs(life_context: str) -> None:
    """Every non-`none` life_context always plants its full declared construct set."""
    from src.ingestion.scenarios import SCENARIO_BIAS

    expected = {d.construct for d in SCENARIO_BIAS[life_context]}
    scenario = MatchDayScenario(sport="athletics", timing="week_before", life_context=life_context)
    for seed in range(5):
        record = generate_scenario_record(scenario, seed=seed)
        assert expected.issubset(_constructs(record))


def test_different_life_context_gives_different_construct_set_most_of_the_time() -> None:
    """The statistical check the plan asks for: vary life_context, hold sport/timing fixed."""
    non_none = [lc for lc in LIFE_CONTEXTS if lc != "none"]
    differing = 0
    total = 0
    for seed in range(30):
        for i, life_a in enumerate(non_none):
            for life_b in non_none[i + 1 :]:
                a = MatchDayScenario(sport="football", timing="week_before", life_context=life_a)
                b = MatchDayScenario(sport="football", timing="week_before", life_context=life_b)
                record_a = generate_scenario_record(a, seed=seed)
                record_b = generate_scenario_record(b, seed=seed)
                total += 1
                if _constructs(record_a) != _constructs(record_b):
                    differing += 1
    assert total > 0
    assert differing / total >= 0.9


def test_none_life_context_falls_back_to_unbiased_draw() -> None:
    """`none` must not appear in the bias table as a set of forced constructs."""
    from src.ingestion.scenarios import SCENARIO_BIAS

    assert SCENARIO_BIAS["none"] == ()


def test_generated_record_is_a_valid_raw_record() -> None:
    scenario = MatchDayScenario(
        sport="swimming", timing="immediately_before", life_context="personal_disruption"
    )
    record = generate_scenario_record(scenario, seed=1)
    assert record.synthetic is True
    assert record.sport == "swimming"
    assert record.time_to_competition_days == 0
    assert record.text.strip()
