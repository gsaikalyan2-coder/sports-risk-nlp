"""Phase 6 tests for the agent layer.

All offline: no network, no API key, no spend. That is the point -- these must
pass for a reviewer who has cloned the repo and has no OpenRouter account.

The ledger is redirected to a tmp_path in every test that writes, so running
pytest never touches the real logs/cost_ledger.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents import (
    ConfigError,
    CostLedger,
    OfflineLLM,
    build_llm,
    construct_names,
    load_routing,
    load_taxonomy,
    risk_direction,
)
from src.agents.config import BudgetConfig
from src.agents.crew import Crew, build_smoke_tasks, run_smoke_crew
from src.agents.ledger import BudgetExceededError, LedgerEntry
from src.agents.roster import ROSTER, TaskSpec


@pytest.fixture
def routing():
    return load_routing()


@pytest.fixture
def constructs():
    return construct_names(load_taxonomy())


@pytest.fixture
def tmp_ledger(tmp_path: Path, routing):
    budget = BudgetConfig(
        monthly_cap_usd=routing.budget.monthly_cap_usd,
        warn_at_fraction=routing.budget.warn_at_fraction,
        ledger_path=tmp_path / "cost_ledger.csv",
        enforce=True,
    )
    return CostLedger(budget)


# --- configuration -------------------------------------------------------


def test_routing_config_loads_and_validates(routing):
    assert routing.mode in ("offline", "live")
    assert set(routing.tiers) == {"cheap", "mid", "premium"}
    for tier in routing.tiers.values():
        assert tier.model, "every tier needs a model id"
        assert tier.price_per_1m_input_usd >= 0
        assert tier.price_per_1m_output_usd >= 0


def test_tiers_are_ordered_cheapest_first(routing):
    """A 'cheap' tier that costs more than 'premium' would silently invert
    the whole cost-aware routing argument in the paper."""
    cheap = routing.tiers["cheap"].price_per_1m_input_usd
    mid = routing.tiers["mid"].price_per_1m_input_usd
    premium = routing.tiers["premium"].price_per_1m_input_usd
    assert cheap <= mid <= premium


def test_escalation_walks_up_and_stops_at_ceiling(routing):
    assert routing.next_tier("cheap") == "mid"
    assert routing.next_tier("mid") == "premium"
    assert routing.next_tier("premium") is None


def test_agent_defaults_reference_real_agents(routing):
    """Every agent in model_routing.yaml that the code orchestrates must have
    a contract in the roster."""
    orchestrated = {"labeling", "annotation_qa", "evaluation", "harvester", "explainability"}
    for key in orchestrated:
        assert key in ROSTER, f"{key} routed but has no AgentSpec"
        assert key in routing.agent_defaults, f"{key} has no default tier"


def test_taxonomy_has_ten_locked_constructs(constructs):
    assert len(constructs) == 10
    assert "cognitive_anxiety" in constructs
    assert "appraisal_orientation" in constructs
    # interpretation_modifier is a modifier, not a construct
    assert "interpretation_modifier" not in constructs


def test_risk_direction_is_readable(constructs):
    assert risk_direction("cognitive_anxiety") in ("raises", "lowers", "neutral", "unknown")
    with pytest.raises(ConfigError):
        risk_direction("not_a_real_construct")


# --- ledger ---------------------------------------------------------------


def test_ledger_writes_header_and_rows(tmp_ledger):
    tmp_ledger.record(
        LedgerEntry(
            agent="labeling",
            phase=6,
            tier="cheap",
            model="test/model",
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.001,
            note="unit test",
        )
    )
    rows = tmp_ledger.rows()
    assert len(rows) == 1
    assert rows[0]["agent"] == "labeling"
    assert float(rows[0]["cost_usd"]) == pytest.approx(0.001)


def test_ledger_enforces_the_monthly_cap(tmp_path, routing):
    budget = BudgetConfig(
        monthly_cap_usd=0.01,
        warn_at_fraction=0.75,
        ledger_path=tmp_path / "ledger.csv",
        enforce=True,
    )
    ledger = CostLedger(budget)
    ledger.record(
        LedgerEntry("labeling", 6, "cheap", "m", 10, 10, 0.009, "under cap"),
    )
    with pytest.raises(BudgetExceededError):
        ledger.record(
            LedgerEntry("labeling", 6, "cheap", "m", 10, 10, 0.005, "over cap"),
        )


def test_cost_estimate_matches_hand_calculation(routing):
    tier = routing.tiers["cheap"]
    # 1M input + 1M output should equal the two headline prices summed.
    cost = tier.estimate_cost_usd(1_000_000, 1_000_000)
    expected = tier.price_per_1m_input_usd + tier.price_per_1m_output_usd
    assert cost == pytest.approx(expected)


# --- offline LLM ----------------------------------------------------------


def test_offline_llm_is_deterministic(routing, constructs, tmp_ledger):
    a = OfflineLLM(routing, tmp_ledger, constructs=constructs, seed=7)
    b = OfflineLLM(routing, tmp_ledger, constructs=constructs, seed=7)
    kw = dict(system="s", user="u", tier="cheap", agent="labeling", phase=6, kind="label")
    assert a.complete(**kw).text == b.complete(**kw).text


def test_offline_llm_seed_changes_output(routing, constructs, tmp_ledger):
    a = OfflineLLM(routing, tmp_ledger, constructs=constructs, seed=1)
    b = OfflineLLM(routing, tmp_ledger, constructs=constructs, seed=2)
    kw = dict(system="s", user="u", tier="cheap", agent="labeling", phase=6, kind="label")
    assert a.complete(**kw).text != b.complete(**kw).text


def test_offline_llm_costs_nothing(routing, constructs, tmp_ledger):
    llm = OfflineLLM(routing, tmp_ledger, constructs=constructs)
    r = llm.complete(system="s", user="u", tier="premium", agent="paper", phase=6, kind="prose")
    assert r.cost_usd == 0.0
    assert r.offline is True


def test_offline_label_uses_only_taxonomy_constructs(routing, constructs, tmp_ledger):
    """The stub must never invent a construct -- CLAUDE.md sec.3."""
    llm = OfflineLLM(routing, tmp_ledger, constructs=constructs, seed=3)
    for i in range(25):
        r = llm.complete(
            system="s", user=f"u{i}", tier="cheap", agent="labeling", phase=6, kind="label"
        )
        assert json.loads(r.text)["construct"] in constructs


def test_kind_dispatch_not_prompt_sniffing(routing, constructs, tmp_ledger):
    """Regression: a QA prompt containing the word 'proposed' once returned a
    label instead of a verdict. Dispatch is on `kind`, not prompt text."""
    llm = OfflineLLM(routing, tmp_ledger, constructs=constructs)
    verdict = llm.complete(
        system="s",
        user="Validate the proposed construct label for this utterance.",
        tier="cheap",
        agent="annotation_qa",
        phase=6,
        kind="verdict",
    )
    parsed = json.loads(verdict.text)
    assert "verdict" in parsed
    assert "construct" not in parsed


def test_build_llm_rejects_unknown_mode(routing):
    with pytest.raises(ValueError, match="offline"):
        build_llm(routing, mode="turbo")


# --- orchestration --------------------------------------------------------


def test_smoke_crew_runs_end_to_end(routing, constructs, tmp_ledger):
    llm = build_llm(routing, mode="offline", ledger=tmp_ledger, constructs=constructs, seed=42)
    run = run_smoke_crew(llm, routing, engine="simple", mode="offline")
    assert run.ok, [i for r in run.results for i in r.issues]
    assert len(run.results) == 3
    assert run.total_cost_usd == 0.0
    assert run.total_tokens > 0


def test_smoke_crew_writes_to_the_ledger(routing, constructs, tmp_ledger):
    llm = build_llm(routing, mode="offline", ledger=tmp_ledger, constructs=constructs, seed=42)
    run_smoke_crew(llm, routing, engine="simple", mode="offline")
    rows = tmp_ledger.rows()
    # 3 tasks, possibly 1 extra row if the label escalated
    assert 3 <= len(rows) <= 4
    assert {r["agent"] for r in rows} <= set(ROSTER)


def test_escalation_fires_below_the_confidence_threshold(routing, constructs, tmp_ledger):
    """At least one seed in a small sweep must escalate, otherwise the
    escalation path is untested in every offline run."""
    escalated_any = False
    for seed in range(1, 15):
        llm = build_llm(
            routing, mode="offline", ledger=tmp_ledger, constructs=constructs, seed=seed
        )
        run = run_smoke_crew(llm, routing, engine="simple", mode="offline")
        if any(r.escalated for r in run.results):
            escalated_any = True
            break
    assert escalated_any, "no seed triggered escalation; the routing path is untested"


def test_invalid_construct_is_flagged(routing, constructs, tmp_ledger):
    """The taxonomy guardrail must catch an invented construct."""

    class RogueLLM(OfflineLLM):
        def _synthesise(self, kind, rng):
            if kind == "label":
                return json.dumps({"construct": "vibes", "intensity": 1, "confidence": 0.9})
            return super()._synthesise(kind, rng)

    llm = RogueLLM(routing, tmp_ledger, constructs=constructs)
    crew = Crew(llm, routing, phase=6, valid_constructs=constructs)
    results = crew.run(build_smoke_tasks())
    label_result = results[0]
    assert not label_result.ok
    assert any("not in the locked taxonomy" in i for i in label_result.issues)


def test_out_of_range_intensity_is_flagged(routing, constructs, tmp_ledger):
    class RogueLLM(OfflineLLM):
        def _synthesise(self, kind, rng):
            if kind == "label":
                return json.dumps({"construct": constructs[0], "intensity": 9, "confidence": 0.9})
            return super()._synthesise(kind, rng)

    llm = RogueLLM(routing, tmp_ledger, constructs=constructs)
    crew = Crew(llm, routing, phase=6, valid_constructs=constructs)
    results = crew.run(build_smoke_tasks())
    assert any("outside the 0-3 scale" in i for i in results[0].issues)


def test_malformed_json_is_reported_not_raised(routing, constructs, tmp_ledger):
    class BrokenLLM(OfflineLLM):
        def _synthesise(self, kind, rng):
            return "this is not json at all"

    llm = BrokenLLM(routing, tmp_ledger, constructs=constructs)
    crew = Crew(llm, routing, phase=6, valid_constructs=constructs)
    results = crew.run(build_smoke_tasks())
    assert any("not valid JSON" in i for i in results[0].issues)


def test_json_in_code_fences_is_parsed(routing, constructs, tmp_ledger):
    """Models wrap JSON in ```json fences constantly; that must not fail a run."""

    class FencedLLM(OfflineLLM):
        def _synthesise(self, kind, rng):
            if kind == "label":
                body = json.dumps({"construct": constructs[0], "intensity": 1, "confidence": 0.9})
                return f"```json\n{body}\n```"
            return super()._synthesise(kind, rng)

    llm = FencedLLM(routing, tmp_ledger, constructs=constructs)
    crew = Crew(llm, routing, phase=6, valid_constructs=constructs)
    results = crew.run(build_smoke_tasks())
    assert results[0].ok
    assert results[0].parsed["construct"] == constructs[0]


def test_unknown_engine_raises(routing, constructs, tmp_ledger):
    llm = build_llm(routing, mode="offline", ledger=tmp_ledger, constructs=constructs)
    with pytest.raises(ValueError, match="unknown engine"):
        run_smoke_crew(llm, routing, engine="magic", mode="offline")


# --- ethics ---------------------------------------------------------------


def test_every_agent_carries_the_ethics_preamble():
    """The non-diagnosis framing must travel with every call, not sit in a doc."""
    for spec in ROSTER.values():
        prompt = spec.system_prompt()
        assert "label LANGUAGE, not people" in prompt
        assert "never invent constructs" in prompt
        assert "not clinical assessment" in prompt


def test_smoke_utterance_is_synthetic():
    from src.agents.crew import SMOKE_UTTERANCE

    assert isinstance(SMOKE_UTTERANCE, str) and SMOKE_UTTERANCE.strip()
    # No real athlete's name or handle should ever appear in the repo.
    assert "@" not in SMOKE_UTTERANCE


def test_taskspec_defaults_to_prose():
    t = TaskSpec(name="x", agent=ROSTER["evaluation"], instruction="do a thing")
    assert t.kind == "prose"
    assert t.expects_json is False
