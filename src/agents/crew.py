"""Orchestration: run a sequence of agent tasks and collect the results.

Two engines, same task graph:

* `simple`  - the built-in sequential orchestrator in this module. No external
              dependencies, fully deterministic, always available.
* `crewai`  - hands the same roster to CrewAI for execution.

Why both. The Phase 6 gate has to be re-runnable by a reviewer with no API key,
and it has to keep passing when CrewAI ships a breaking change (it went 0.x to
1.x during this project's lifetime). Pinning the *contract* in our own code and
treating CrewAI as one execution backend keeps the pipeline reproducible
without giving up the confirmed framework decision from CLAUDE.md sec.10.

The escalation logic lives here rather than in the LLM client on purpose:
"this answer was not confident enough, try a better model" is an orchestration
decision, and Phase 18 needs to ablate it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import RoutingConfig, construct_names, load_taxonomy
from .llm import LLMClient, LLMResponse
from .roster import ANNOTATION_QA, EVALUATION, LABELING, AgentSpec, TaskSpec

# A synthetic utterance. Written for this test, not taken from any real athlete.
# Ethics (CLAUDE.md sec.1): no real person's text appears in the repo, and
# nothing here is a claim about anybody's mental health.
SMOKE_UTTERANCE = (
    "I keep going over tomorrow's race in my head and I can't switch it off. "
    "My legs feel heavy and I'm not sure I've done enough."
)


@dataclass
class TaskResult:
    task: str
    agent: str
    tier_used: str
    escalated: bool
    response: LLMResponse
    parsed: dict[str, Any] | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass
class CrewRun:
    """Everything one orchestrated run produced."""

    engine: str
    mode: str
    results: list[TaskResult] = field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.response.cost_usd for r in self.results)

    @property
    def total_tokens(self) -> int:
        return sum(r.response.input_tokens + r.response.output_tokens for r in self.results)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    def summary_lines(self) -> list[str]:
        lines = [
            f"engine        : {self.engine}",
            f"mode          : {self.mode}",
            f"tasks         : {len(self.results)}",
            f"tokens        : {self.total_tokens}",
            f"estimated cost: ${self.total_cost_usd:.6f}",
        ]
        for r in self.results:
            flag = "ok" if r.ok else "ISSUES"
            esc = " (escalated)" if r.escalated else ""
            lines.append(f"  - {r.task:<22} {r.agent:<20} {r.tier_used:<8} {flag}{esc}")
            for issue in r.issues:
                lines.append(f"      ! {issue}")
        return lines


class Crew:
    """Runs TaskSpecs in order, with confidence-triggered tier escalation."""

    def __init__(
        self,
        llm: LLMClient,
        routing: RoutingConfig,
        *,
        phase: int = 6,
        valid_constructs: tuple[str, ...] = (),
    ):
        self.llm = llm
        self.routing = routing
        self.phase = phase
        self.valid_constructs = valid_constructs

    def run(self, tasks: list[TaskSpec]) -> list[TaskResult]:
        results: list[TaskResult] = []
        context: dict[str, Any] = {}

        for task in tasks:
            result = self._run_task(task, context)
            results.append(result)
            if result.parsed is not None:
                context[task.name] = result.parsed
        return results

    def _run_task(self, task: TaskSpec, context: dict[str, Any]) -> TaskResult:
        agent = task.agent
        tier = self.routing.tier_for_agent(agent.key)
        if tier == "local":
            tier = "cheap"

        prompt = self._build_prompt(task, context)
        response = self.llm.complete(
            system=agent.system_prompt(),
            user=prompt,
            tier=tier,
            agent=agent.key,
            phase=self.phase,
            note=task.name,
            kind=task.kind,
        )

        parsed, issues = self._parse(task, response)
        escalated = False

        # Escalate on low confidence, once, and only if a higher tier exists.
        confidence = (parsed or {}).get("confidence")
        if (
            isinstance(confidence, (int, float))  # noqa: UP038 - tuple form is faster
            and confidence < self.routing.confidence_threshold
            and self.routing.max_escalations_per_record > 0
        ):
            higher = self.routing.next_tier(tier)
            if higher:
                escalated = True
                response = self.llm.complete(
                    system=agent.system_prompt(),
                    user=prompt
                    + f"\n\nA cheaper model returned confidence {confidence}, below the "
                    f"{self.routing.confidence_threshold} threshold. Re-answer carefully.",
                    tier=higher,
                    agent=agent.key,
                    phase=self.phase,
                    note=f"{task.name} (escalated from {tier})",
                    kind=task.kind,
                )
                tier = higher
                parsed, issues = self._parse(task, response)

        if parsed is not None:
            issues.extend(self._validate(task, parsed))

        return TaskResult(
            task=task.name,
            agent=agent.role,
            tier_used=tier,
            escalated=escalated,
            response=response,
            parsed=parsed,
            issues=issues,
        )

    def _build_prompt(self, task: TaskSpec, context: dict[str, Any]) -> str:
        parts = [task.instruction]
        for key in task.context_keys:
            if key in context:
                parts.append(
                    f"\nOutput of the earlier '{key}' step:\n{json.dumps(context[key], indent=2)}"
                )
        if task.expects_json:
            parts.append("\nRespond with JSON only. No prose, no code fences.")
        return "\n".join(parts)

    def _parse(
        self, task: TaskSpec, response: LLMResponse
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if not task.expects_json:
            return None, []
        try:
            parsed = response.as_json()
        except (json.JSONDecodeError, ValueError) as exc:
            return None, [f"response was not valid JSON: {exc}"]
        if not isinstance(parsed, dict):
            return None, ["response JSON was not an object"]
        return parsed, []

    def _validate(self, task: TaskSpec, parsed: dict[str, Any]) -> list[str]:
        """Structural checks the pipeline can make without a human."""
        issues: list[str] = []

        construct = parsed.get("construct")
        if construct is not None and self.valid_constructs:
            if construct not in self.valid_constructs:
                # This is the guardrail behind CLAUDE.md sec.3: agents must
                # never invent constructs outside the locked taxonomy.
                issues.append(
                    f"construct {construct!r} is not in the locked taxonomy "
                    f"({len(self.valid_constructs)} valid constructs)"
                )

        intensity = parsed.get("intensity")
        if intensity is not None:
            if not isinstance(intensity, int) or not 0 <= intensity <= 3:
                issues.append(f"intensity {intensity!r} is outside the 0-3 scale")

        confidence = parsed.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, (int, float)) or not 0.0 <= confidence <= 1.0:  # noqa: UP038
                issues.append(f"confidence {confidence!r} is outside [0, 1]")

        return issues


def build_smoke_tasks(utterance: str = SMOKE_UTTERANCE) -> list[TaskSpec]:
    """The Phase 6 smoke-test task graph: label -> QA -> summarise.

    Trivial on purpose. The point is to prove the orchestration, routing,
    escalation, validation, and ledger wiring all work end to end -- not to
    produce a good label.
    """
    return [
        TaskSpec(
            name="propose_label",
            agent=LABELING,
            instruction=(
                "Propose the single most salient construct for the utterance below.\n\n"
                f'Utterance: "{utterance}"\n\n'
                "Return fields: construct, intensity (0-3), confidence (0-1), "
                "evidence_span, rationale."
            ),
            kind="label",
            expects_json=True,
        ),
        TaskSpec(
            name="qa_review",
            agent=ANNOTATION_QA,
            instruction=(
                "Validate the proposed label. Confirm the construct exists in the taxonomy, "
                "the intensity is in range, and the confidence is adequate.\n\n"
                "Return fields: verdict ('accept' or 'flag'), issues (list), rationale."
            ),
            kind="verdict",
            expects_json=True,
            context_keys=("propose_label",),
        ),
        TaskSpec(
            name="run_summary",
            agent=EVALUATION,
            instruction=(
                "In two sentences, summarise what this pipeline run produced and whether "
                "anything was flagged. Report only what the earlier steps show."
            ),
            kind="prose",
            expects_json=False,
            context_keys=("propose_label", "qa_review"),
        ),
    ]


def run_smoke_crew(
    llm: LLMClient,
    routing: RoutingConfig,
    *,
    engine: str = "simple",
    mode: str = "offline",
    utterance: str = SMOKE_UTTERANCE,
) -> CrewRun:
    """Execute the smoke crew on the chosen engine."""
    constructs = construct_names(load_taxonomy())
    tasks = build_smoke_tasks(utterance)

    if engine == "crewai":
        from .crewai_engine import run_with_crewai

        results = run_with_crewai(tasks, llm, routing, constructs)
    elif engine == "simple":
        crew = Crew(llm, routing, phase=6, valid_constructs=constructs)
        results = crew.run(tasks)
    else:
        raise ValueError(f"unknown engine {engine!r}; expected 'simple' or 'crewai'")

    return CrewRun(engine=engine, mode=mode, results=results)


def agent_for(key: str) -> AgentSpec:
    """Look up an agent contract by key."""
    from .roster import ROSTER

    if key not in ROSTER:
        raise KeyError(f"no agent {key!r}; known: {sorted(ROSTER)}")
    return ROSTER[key]
