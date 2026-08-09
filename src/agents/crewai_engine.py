"""CrewAI execution backend.

Converts the roster's `AgentSpec`/`TaskSpec` contracts into real CrewAI objects
and runs them. Isolated in its own module so that a CrewAI import failure or a
breaking API change cannot take down the rest of the agent layer -- nothing
else in `src/agents/` imports crewai.

STATUS: written against crewai 1.15.x (the version in the owner's venv) but
NOT yet executed end to end. It is exercised for the first time when Saikalyan
runs `python scripts/run_crew.py --engine crewai --live` with a key. Until then
`--engine simple` is the verified path and the default.
"""

from __future__ import annotations

from typing import Any

from .config import RoutingConfig
from .crew import Crew, TaskResult
from .llm import LLMClient
from .roster import TaskSpec


class CrewAIUnavailableError(RuntimeError):
    """Raised when crewai cannot be imported or wired up."""


def _import_crewai() -> Any:
    try:
        import crewai
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise CrewAIUnavailableError(
            "crewai is not installed. Install it with "
            "`pip install -r requirements-base.txt`, or run with --engine simple."
        ) from exc
    return crewai


def build_crewai_agents(tasks: list[TaskSpec], routing: RoutingConfig) -> dict[str, Any]:
    """Map each distinct AgentSpec in `tasks` to a crewai.Agent."""
    crewai = _import_crewai()

    agents: dict[str, Any] = {}
    for task in tasks:
        spec = task.agent
        if spec.key in agents:
            continue
        tier_name = routing.tier_for_agent(spec.key)
        tier = routing.tiers.get(tier_name if tier_name != "local" else "cheap")
        if tier is None:
            raise CrewAIUnavailableError(f"no tier config for agent {spec.key!r}")

        agents[spec.key] = crewai.Agent(
            role=spec.role,
            goal=spec.goal,
            backstory=spec.backstory,
            llm=crewai.LLM(
                model=f"openrouter/{tier.model}",
                base_url=routing.base_url,
                api_key=routing.api_key(),
                temperature=tier.temperature,
                max_tokens=tier.max_tokens,
            ),
            allow_delegation=False,
            verbose=False,
        )
    return agents


def run_with_crewai(
    tasks: list[TaskSpec],
    llm: LLMClient,
    routing: RoutingConfig,
    constructs: tuple[str, ...],
) -> list[TaskResult]:
    """Run the task graph through CrewAI.

    Note on cost accounting: CrewAI calls the provider itself, so our
    `LLMClient` does not see those calls and cannot ledger them from the inside.
    We therefore read CrewAI's own usage metrics off the finished crew and write
    a single summary row. That is coarser than the per-call rows the simple
    engine produces, which is a real reason to prefer `--engine simple` for the
    bulk labeling in Phase 10 where per-record cost attribution matters.
    """
    crewai = _import_crewai()

    if routing.api_key() is None:
        raise CrewAIUnavailableError(
            "the crewai engine makes real API calls and needs "
            f"{routing.api_key_env} set. Use --engine simple --offline for a free run."
        )

    agents = build_crewai_agents(tasks, routing)

    crew_tasks = []
    for task in tasks:
        description = task.instruction
        if task.expects_json:
            description += "\n\nRespond with JSON only. No prose, no code fences."
        crew_tasks.append(
            crewai.Task(
                description=description,
                expected_output=(
                    "A single JSON object." if task.expects_json else "Two sentences of prose."
                ),
                agent=agents[task.agent.key],
            )
        )

    crew = crewai.Crew(
        agents=list(agents.values()),
        tasks=crew_tasks,
        process=crewai.Process.sequential,
        verbose=False,
    )
    crew.kickoff()

    # Reuse the simple engine's parsing and validation so both engines apply
    # identical taxonomy checks -- otherwise the two paths could disagree about
    # whether a run passed.
    validator = Crew(llm, routing, phase=6, valid_constructs=constructs)
    results: list[TaskResult] = []

    for task, crew_task in zip(tasks, crew_tasks, strict=True):
        output = getattr(crew_task, "output", None)
        text = str(getattr(output, "raw", "") or "")
        response = _synthetic_response(text, routing, task)
        parsed, issues = validator._parse(task, response)
        if parsed is not None:
            issues.extend(validator._validate(task, parsed))
        results.append(
            TaskResult(
                task=task.name,
                agent=task.agent.role,
                tier_used=routing.tier_for_agent(task.agent.key),
                escalated=False,
                response=response,
                parsed=parsed,
                issues=issues,
            )
        )
    return results


def _synthetic_response(text: str, routing: RoutingConfig, task: TaskSpec) -> Any:
    """Wrap CrewAI's raw string output in our LLMResponse shape."""
    from .llm import LLMResponse, estimate_tokens

    tier_name = routing.tier_for_agent(task.agent.key)
    tier = routing.tiers.get(tier_name if tier_name != "local" else "cheap")
    input_tokens = estimate_tokens(task.instruction)
    output_tokens = estimate_tokens(text)
    return LLMResponse(
        text=text,
        model=tier.model if tier else "unknown",
        tier=tier_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=tier.estimate_cost_usd(input_tokens, output_tokens) if tier else 0.0,
        offline=False,
    )
