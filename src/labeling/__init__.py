"""Cost-aware weak labelling (Phase 10).

Produces **silver** labels: construct labels proposed by a cheap LLM, each with
a rationale, a confidence, and spans copied verbatim from the utterance. Silver
is training signal, not ground truth. Human gold labels are Phase 11, live in
`data/gold/`, and are written by people.

    from src.labeling import label_records, SilverStore, run_qa

Submodules, in pipeline order:

    prompt      the cached rubric prompt, built from taxonomy + guidelines
    dedup       group utterances by prompt payload; pay once per distinct prompt
    runner      route -> call -> parse -> escalate once -> fan out
    parser      strict validation; refuses malformed output rather than coercing
    schema      SilverLabel / ConstructLabel, with the invariants enforced
    store       the only write path into data/processed/silver/
    qa          the Annotation-QA pass -> logs/review_queue.jsonl
    ancestry    OPEN-021 probe: is the labeller independent of the corpus?
"""

from __future__ import annotations

from .ancestry import (
    ConstructAncestry,
    example_overlap,
    format_report,
    overlap_report,
)
from .dedup import DedupPlan, PromptUnit, build_plan, parent_context
from .parser import LabelParseError, ParsedResponse, parse_response
from .prompt import (
    PLACEHOLDER_GLOSSARY,
    SYSTEM_PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt,
    cached_system_prompt,
    prompt_hash,
)
from .qa import ReviewItem, build_queue, queue_summary, review_reasons, run_qa, write_queue
from .runner import (
    LABELING_MAX_TIER,
    LabelFailure,
    LabelingRun,
    label_records,
    project_cost,
)
from .schema import (
    FORBIDDEN_FIELDS,
    MODIFIER_CONSTRUCTS,
    MODIFIER_VALUES,
    ConstructLabel,
    SilverLabel,
    SilverSchemaError,
)
from .store import SilverStore, SilverWriter, silver_provenance

__all__ = [
    "FORBIDDEN_FIELDS",
    "LABELING_MAX_TIER",
    "MODIFIER_CONSTRUCTS",
    "MODIFIER_VALUES",
    "PLACEHOLDER_GLOSSARY",
    "SYSTEM_PROMPT_VERSION",
    "ConstructAncestry",
    "ConstructLabel",
    "DedupPlan",
    "LabelFailure",
    "LabelParseError",
    "LabelingRun",
    "ParsedResponse",
    "PromptUnit",
    "ReviewItem",
    "SilverLabel",
    "SilverSchemaError",
    "SilverStore",
    "SilverWriter",
    "build_plan",
    "build_queue",
    "build_system_prompt",
    "build_user_prompt",
    "cached_system_prompt",
    "example_overlap",
    "format_report",
    "label_records",
    "overlap_report",
    "parent_context",
    "parse_response",
    "project_cost",
    "prompt_hash",
    "queue_summary",
    "review_reasons",
    "run_qa",
    "silver_provenance",
    "write_queue",
]
