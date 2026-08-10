"""The labelling loop: route, call, parse, escalate, fan out.

This module owns the control flow and nothing else. It builds no prompts,
validates no JSON, and writes no files -- those live in `prompt`, `parser` and
`store`. Keeping the loop thin is what makes the escalation policy readable,
and the escalation policy is the part a reviewer will ask about.

## The policy, in full

1. Every prompt starts on the tier `config/model_routing.yaml` assigns to the
   `labeling` agent, which is **cheap**.
2. A call is **escalated exactly once** when the cheap tier either produced
   output the parser refused, or produced a valid label set whose weakest
   confidence falls below `escalation.confidence_threshold` (0.65).
3. Escalation goes to **mid, and stops there**, even though
   `escalation.max_tier` permits premium. Premium is ~20x cheap per token and
   the config's own worked example puts a full premium pass at the entire
   monthly cap. Adjudicating a genuinely hard utterance is a job for a human at
   Phase 11, not for a more expensive model at Phase 10.
4. If the escalated answer is *still* unparseable, the utterance is left
   **unlabelled** and goes to the review queue. A gap is a known quantity; a
   guess is a corrupted row that nothing downstream can detect.
5. If the escalated answer parses but is still low-confidence, it is **kept**
   and flagged for review. Silver labels are training signal, not ground truth;
   discarding every uncertain one would bias the silver distribution toward
   easy utterances, which is the same selection error Phase 9 rejected when it
   refused to draw gold items by lexicon detectability.

## Why the confidence threshold is a starting value and is treated as one

0.65 was written into the config at Phase 6 with an explicit note that it is not
evidence-backed. Nothing here has changed that, and nothing here pretends
otherwise: the escalation rate is reported per run so the number can be
calibrated against the Phase 11 gold set rather than defended on vibes, and
Phase 18's ablation should report sensitivity to it.

## Determinism

The loop is deterministic given a fixed corpus and a fixed prompt version: units
are visited in corpus order, and both live tiers run at `temperature: 0.0`. The
offline stub is seeded from the prompt text, so an offline run is byte-stable
across machines. What is *not* deterministic is a live provider's output over
time -- a model updated behind a stable ID will answer differently next month.
That is a property of the provider, not of this code, and it is why the model ID
and prompt version are stamped onto every row.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agents.config import RoutingConfig
from src.agents.llm import LLMClient
from src.preprocessing.records import InterimRecord

from .dedup import DedupPlan, PromptUnit, build_plan
from .parser import LabelParseError, ParsedResponse, parse_response
from .prompt import SYSTEM_PROMPT_VERSION, cached_system_prompt
from .schema import SilverLabel, SilverSchemaError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = REPO_ROOT / "logs"

#: The Labeling Agent's escalation ceiling. Deliberately below
#: `escalation.max_tier` -- see the module docstring, point 3.
LABELING_MAX_TIER = "mid"

PHASE = 10


@dataclass(frozen=True)
class LabelFailure:
    """An utterance that could not be labelled, and why."""

    record_id: str
    parent_record_id: str
    text: str
    reason: str
    detail: str
    tier: str
    escalated: bool
    fanout: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "parent_record_id": self.parent_record_id,
            "text": self.text,
            "reason": self.reason,
            "detail": self.detail,
            "tier": self.tier,
            "escalated": self.escalated,
            "fanout": self.fanout,
        }


@dataclass
class LabelingRun:
    """Everything one labelling pass produced. The unit of reporting."""

    run_id: str
    mode: str
    prompt_version: str
    plan: DedupPlan
    labels: list[SilverLabel] = field(default_factory=list)
    failures: list[LabelFailure] = field(default_factory=list)
    calls_made: int = 0
    escalations: int = 0
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    started_on: str = ""
    finished_on: str = ""
    use_context: bool = True

    # -- derived ------------------------------------------------------------

    @property
    def abstentions(self) -> int:
        return sum(1 for label in self.labels if label.abstained)

    @property
    def abstention_rate(self) -> float:
        return self.abstentions / len(self.labels) if self.labels else 0.0

    @property
    def escalation_rate(self) -> float:
        return self.escalations / self.plan.calls if self.plan.calls else 0.0

    def construct_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label in self.labels:
            for item in label.present_labels:
                counts[item.construct] = counts.get(item.construct, 0) + 1
        return dict(sorted(counts.items()))

    def summary(self) -> str:
        return (
            f"run {self.run_id} [{self.mode}]: {len(self.labels)} label(s) from "
            f"{self.calls_made} call(s), {self.escalations} escalation(s), "
            f"{len(self.failures)} failure(s), ${self.cost_usd:.6f}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": PHASE,
            "mode": self.mode,
            "prompt_version": self.prompt_version,
            "use_context": self.use_context,
            "started_on": self.started_on,
            "finished_on": self.finished_on,
            "utterances": self.plan.total_records,
            "distinct_prompts": self.plan.calls,
            "copied_by_dedup": self.plan.copied,
            "dedup_saving_fraction": round(self.plan.saving_fraction, 4),
            "calls_made": self.calls_made,
            "escalations": self.escalations,
            "escalation_rate": round(self.escalation_rate, 4),
            "labels_written": len(self.labels),
            "failures": len(self.failures),
            "abstentions": self.abstentions,
            "abstention_rate": round(self.abstention_rate, 4),
            "construct_counts": self.construct_counts(),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }

    def write_log(self, log_dir: Path | None = None) -> Path:
        """Write the agent run log required of every agent (CLAUDE.md sec.4)."""
        directory = log_dir or DEFAULT_LOG_DIR
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"labeling_{self.run_id}.json"
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return path


def _new_run_id(now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(dt.UTC)
    return now.strftime("%Y%m%dT%H%M%SZ")


def _to_silver(
    record: InterimRecord,
    parsed: ParsedResponse,
    *,
    unit: PromptUnit,
    tier: str,
    model: str,
    offline: bool,
    escalated: bool,
    escalation_reason: str,
    run_id: str,
    use_context: bool,
    deduplicated: bool,
) -> SilverLabel:
    return SilverLabel(
        record_id=record.record_id,
        parent_record_id=record.parent_record_id,
        source_id=record.source_id,
        text=record.text,
        labels=parsed.labels,
        rationale=parsed.rationale,
        confidence=parsed.confidence,
        abstained=parsed.abstain,
        interpretation_modifier=parsed.interpretation_modifier,
        low_resilience_explicit=parsed.low_resilience_explicit,
        tier=tier,
        model=model,
        escalated=escalated,
        escalation_reason=escalation_reason,
        offline=offline,
        prompt_hash=unit.key,
        prompt_version=SYSTEM_PROMPT_VERSION,
        context_used=use_context,
        deduplicated=deduplicated,
        dedup_key=unit.key,
        run_id=run_id,
    )


def label_records(
    records: Sequence[InterimRecord],
    *,
    llm: LLMClient,
    routing: RoutingConfig,
    taxonomy: dict[str, Any],
    use_context: bool = True,
    limit: int | None = None,
    progress_every: int = 250,
    run_id: str | None = None,
    mode: str = "offline",
) -> LabelingRun:
    """Label a corpus and return everything the run produced.

    `limit` caps the number of **distinct prompts** sent, not the number of
    utterances. That is the number that costs money, so it is the number a
    pilot run wants to bound.
    """
    system = cached_system_prompt()
    plan = build_plan(records, system_prompt=system, use_context=use_context)
    constructs = taxonomy.get("constructs") or {}

    run = LabelingRun(
        run_id=run_id or _new_run_id(),
        mode=mode,
        prompt_version=SYSTEM_PROMPT_VERSION,
        plan=plan,
        use_context=use_context,
        started_on=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    )

    start_tier = routing.tier_for_agent("labeling")
    units = plan.units if limit is None else plan.units[:limit]

    for index, unit in enumerate(units, start=1):
        tier = start_tier
        escalated = False
        escalation_reason = ""
        parsed: ParsedResponse | None = None
        last_error: LabelParseError | None = None

        for attempt in range(2):  # at most one escalation; see policy point 2
            response = llm.complete(
                system=system,
                user=unit.user_prompt,
                tier=tier,
                agent="labeling",
                phase=PHASE,
                note=f"silver {unit.key[:12]} fanout={unit.fanout}",
                kind="silver",
            )
            run.calls_made += 1
            run.cost_usd += response.cost_usd
            run.input_tokens += response.input_tokens
            run.output_tokens += response.output_tokens
            model = response.model

            try:
                candidate = parse_response(
                    response.text, text=unit.representative.text, valid_constructs=constructs
                )
            except LabelParseError as exc:
                last_error = exc
                candidate = None

            if candidate is not None:
                parsed = candidate
                weakest = min([candidate.confidence] + [x.confidence for x in candidate.labels])
                needs_escalation = weakest < routing.confidence_threshold
                reason = f"confidence {weakest:.2f} < {routing.confidence_threshold:.2f}"
            else:
                needs_escalation = True
                reason = f"parse failed ({last_error.reason if last_error else 'unknown'})"

            if not needs_escalation or attempt == 1:
                break

            next_tier = routing.next_tier(tier)
            if next_tier is None or _tier_rank(next_tier) > _tier_rank(LABELING_MAX_TIER):
                break
            tier = next_tier
            escalated = True
            escalation_reason = reason
            run.escalations += 1

        if parsed is None:
            for member in unit.members:
                run.failures.append(
                    LabelFailure(
                        record_id=member.record_id,
                        parent_record_id=member.parent_record_id,
                        text=member.text,
                        reason=last_error.reason if last_error else "UNKNOWN",
                        detail=last_error.detail if last_error else "",
                        tier=tier,
                        escalated=escalated,
                        fanout=unit.fanout,
                    )
                )
        else:
            for position, member in enumerate(unit.members):
                try:
                    run.labels.append(
                        _to_silver(
                            member,
                            parsed,
                            unit=unit,
                            tier=tier,
                            model=model,
                            offline=response.offline,
                            escalated=escalated,
                            escalation_reason=escalation_reason,
                            run_id=run.run_id,
                            use_context=use_context,
                            deduplicated=position > 0,
                        )
                    )
                except SilverSchemaError as exc:
                    # Reachable only when fan-out lands a span on a member whose
                    # text differs -- which cannot happen while the key is a hash
                    # of the payload containing the text, but is caught rather
                    # than assumed away, because the day someone loosens the key
                    # is the day this becomes silent corruption.
                    run.failures.append(
                        LabelFailure(
                            record_id=member.record_id,
                            parent_record_id=member.parent_record_id,
                            text=member.text,
                            reason="FANOUT_SCHEMA_VIOLATION",
                            detail=str(exc),
                            tier=tier,
                            escalated=escalated,
                            fanout=unit.fanout,
                        )
                    )

        if progress_every and index % progress_every == 0:
            print(
                f"  {index}/{len(units)} prompts | {len(run.labels)} labels | "
                f"{run.escalations} escalations | ${run.cost_usd:.4f}"
            )

    run.finished_on = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    return run


def _tier_rank(tier: str) -> int:
    return {"cheap": 0, "mid": 1, "premium": 2}.get(tier, 99)


def project_cost(
    plan: DedupPlan,
    *,
    routing: RoutingConfig,
    system_prompt: str,
    sample_units: int = 200,
    assumed_output_tokens: int = 220,
    escalation_fraction: float = 0.25,
    cache_discount: float = 1.0,
) -> dict[str, float]:
    """Estimate what a live run of this plan would cost, before spending anything.

    Deliberately an over-estimate on every axis it controls: it charges every
    escalation at the mid tier, assumes an output length at the upper end of
    what the schema needs, and by default gives prompt caching **no** credit at
    all. A projection that came in under the real cost would be worse than
    useless -- its whole job is to let the owner refuse a run that is too
    expensive, and it can only do that by erring high.

    ## `cache_discount`, and a config figure this function falsified

    `config/model_routing.yaml` carries a worked budget estimate concluding
    "about $1.12 for a full labeling pass on the cheap tier", built on an
    assumption of "~400 input tokens (rubric is cached; only the utterance
    varies)".

    The rubric is not 400 tokens. The assembled system prompt for the ten locked
    constructs is **~3,950 tokens** -- ten definitions, forty examples, ten
    edge-case notes, the intensity anchors and the five discriminating
    questions. The config's estimate is low by roughly an order of magnitude on
    the input side, and it was written before the prompt existed, so this is the
    first opportunity anyone has had to check it.

    Caching does not make a cached prefix free either. Providers charge cache
    *reads* at a reduced rate, and the multiplier varies by provider and changes
    without notice -- the same drift OPEN-009 already tracks for prices. So the
    discount is an explicit parameter that defaults to 1.0 (no credit). Pass a
    measured multiplier once a pilot has produced one; do not guess one and
    quote the result.
    """
    from src.agents.llm import estimate_tokens

    sample = plan.units[:sample_units] or plan.units
    if not sample:
        return {"projected_usd": 0.0, "calls": 0, "mean_input_tokens": 0.0}

    system_tokens = estimate_tokens(system_prompt)
    mean_user = sum(estimate_tokens(u.user_prompt) for u in sample) / len(sample)
    # Only the system prefix is cacheable: it is byte-identical across calls,
    # which is the property `prompt.py` is written to preserve. The user prompt
    # varies by construction and is always charged in full.
    billable_input = system_tokens * cache_discount + mean_user

    cheap = routing.tiers["cheap"]
    mid = routing.tiers["mid"]

    base = plan.calls * cheap.estimate_cost_usd(int(billable_input), assumed_output_tokens)
    extra = (
        plan.calls
        * escalation_fraction
        * mid.estimate_cost_usd(int(billable_input), assumed_output_tokens)
    )
    return {
        "projected_usd": round(base + extra, 4),
        "cheap_only_usd": round(base, 4),
        "escalation_usd": round(extra, 4),
        "calls": float(plan.calls),
        "system_prompt_tokens": float(system_tokens),
        "mean_user_tokens": round(mean_user, 1),
        "mean_billable_input_tokens": round(billable_input, 1),
        "assumed_output_tokens": float(assumed_output_tokens),
        "assumed_escalation_fraction": escalation_fraction,
        "assumed_cache_discount": cache_discount,
    }
