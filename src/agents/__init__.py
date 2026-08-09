"""Agent layer: cost-aware, construct-grounded multi-agent orchestration.

Phase 6 deliverable. Public surface:

    from src.agents import load_routing, build_llm, run_smoke_crew

Submodules:
    config          load and validate config/model_routing.yaml + taxonomy
    ledger          append-only cost ledger with a hard monthly cap
    llm             OfflineLLM / OpenRouterLLM behind one interface
    roster          agent contracts (CLAUDE.md sec.4)
    crew            the built-in sequential orchestrator
    crewai_engine   optional CrewAI backend (live runs only)
"""

from __future__ import annotations

from .config import (
    ConfigError,
    RoutingConfig,
    TierConfig,
    construct_names,
    load_routing,
    load_settings,
    load_taxonomy,
    risk_direction,
)
from .crew import (
    SMOKE_UTTERANCE,
    Crew,
    CrewRun,
    TaskResult,
    build_smoke_tasks,
    run_smoke_crew,
)
from .ledger import BudgetExceededError, CostLedger, LedgerEntry
from .llm import LLMResponse, OfflineLLM, OpenRouterLLM, build_llm
from .roster import ROSTER, AgentSpec, TaskSpec

__all__ = [
    "ROSTER",
    "SMOKE_UTTERANCE",
    "AgentSpec",
    "BudgetExceededError",
    "ConfigError",
    "CostLedger",
    "Crew",
    "CrewRun",
    "LLMResponse",
    "LedgerEntry",
    "OfflineLLM",
    "OpenRouterLLM",
    "RoutingConfig",
    "TaskResult",
    "TaskSpec",
    "TierConfig",
    "build_llm",
    "build_smoke_tasks",
    "construct_names",
    "load_routing",
    "load_settings",
    "load_taxonomy",
    "risk_direction",
    "run_smoke_crew",
]
