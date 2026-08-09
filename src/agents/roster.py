"""The agent roster: one contract per specialist agent.

Mirrors the table in CLAUDE.md sec.4. Each agent declares a narrow contract --
role, goal, what it may read, what it may write, and its default cost tier --
so that orchestration code never has to hardcode who does what.

Keeping this as data rather than as classes matters for two reasons. It is the
thing the paper's methods section describes, so it should be readable by a
non-programmer. And it lets the same definitions drive both the built-in
orchestrator and a CrewAI crew without duplicating the descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Shared preamble prepended to every agent's system prompt. The ethics framing
# is not decoration: these agents touch athlete language, and the framing has to
# travel with every single call, not just live in a document nobody reads.
# CLAUDE.md sec.1, docs/ethics.md, docs/annotation_guidelines.md sec.0.
ETHICS_PREAMBLE = """\
You are part of a research pipeline that detects sports-psychology constructs in
athlete text. Three rules constrain everything you do:

1. You label LANGUAGE, not people. You never diagnose, and you never make a
   claim about any real named individual's mental health.
2. You never invent constructs. Only the constructs defined in
   config/taxonomy.yaml exist. If nothing fits, say so.
3. This is research and decision support, not clinical assessment. Where you are
   uncertain, report uncertainty rather than resolving it with a guess.
"""


@dataclass(frozen=True)
class AgentSpec:
    """One agent's contract."""

    key: str
    role: str
    goal: str
    backstory: str
    default_tier: str
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    phases: tuple[int, ...] = ()

    def system_prompt(self) -> str:
        return f"{ETHICS_PREAMBLE}\nRole: {self.role}\nGoal: {self.goal}\n\n{self.backstory}"


LABELING = AgentSpec(
    key="labeling",
    role="Labeling Agent",
    goal=(
        "Propose a construct label, an intensity on the 0-3 scale, and a calibrated "
        "confidence for a single athlete utterance, citing the span that justifies it."
    ),
    backstory=(
        "You apply docs/annotation_guidelines.md mechanically. Intensity is graded on "
        "linguistic evidence -- hedges pull down, intensifiers pull up -- not on your "
        "estimate of the athlete's true internal state. When in doubt, label 0."
    ),
    default_tier="cheap",
    reads=("data/interim/",),
    writes=("data/processed/silver/",),
    phases=(10,),
)

ANNOTATION_QA = AgentSpec(
    key="annotation_qa",
    role="Annotation-QA Agent",
    goal=(
        "Check a proposed label for validity: the construct must exist in the taxonomy, "
        "the intensity must be within scale, and low-confidence proposals must be flagged "
        "for escalation or human review."
    ),
    backstory=(
        "You are a gatekeeper, not a second labeler. You do not re-label; you decide "
        "whether a proposal is well-formed and confident enough to keep."
    ),
    default_tier="cheap",
    reads=("data/processed/silver/",),
    writes=("logs/review_queue.jsonl",),
    phases=(11,),
)

EVALUATION = AgentSpec(
    key="evaluation",
    role="Evaluation Agent",
    goal="Summarise a pipeline run: what was produced, what was flagged, and what it cost.",
    backstory=(
        "You report, you do not interpret. Numbers and flags, with no claims the run "
        "does not support."
    ),
    default_tier="cheap",
    reads=("models/", "data/gold/"),
    writes=("reports/",),
    phases=(18,),
)

HARVESTER = AgentSpec(
    key="harvester",
    role="Harvester Agent",
    goal="Ingest source text, record provenance and licence, and de-identify before storage.",
    backstory=(
        "You never write a record without provenance. Any text touching data/raw/ passes "
        "through de-identification first, and every source is checked against the Phase 5 "
        "allow-list in config/data_sources_allowlist.yaml."
    ),
    default_tier="cheap",
    reads=("config/data_sources_allowlist.yaml",),
    writes=("data/raw/", "data/interim/"),
    phases=(7, 8),
)

EXPLAINABILITY = AgentSpec(
    key="explainability",
    role="Explainability Agent",
    goal="Attribute a risk score to text spans and constructs, and write example cards.",
    backstory=(
        "Explanations are the headline contribution of this project and will be shown to "
        "coaches. An explanation that is confidently wrong is worse than none."
    ),
    default_tier="mid",
    reads=("models/",),
    writes=("reports/explain/",),
    phases=(16, 17),
)

#: Registry of every agent, keyed as in config/model_routing.yaml agent_defaults.
ROSTER: dict[str, AgentSpec] = {
    spec.key: spec for spec in (LABELING, ANNOTATION_QA, EVALUATION, HARVESTER, EXPLAINABILITY)
}


@dataclass
class TaskSpec:
    """One unit of work assigned to one agent.

    `kind` declares the SHAPE of the expected answer ("label", "verdict",
    "prose"). It is passed to the LLM layer explicitly rather than inferred
    from the prompt text. That distinction caused a real bug: the offline stub
    originally sniffed the prompt for the word "propose", which also matches
    "the proposed label" in the QA instruction, so the QA step silently
    returned a label proposal instead of a verdict. Guessing intent from
    substrings is fragile; declaring it is not.
    """

    name: str
    agent: AgentSpec
    instruction: str
    kind: str = "prose"
    expects_json: bool = False
    context_keys: tuple[str, ...] = field(default_factory=tuple)
