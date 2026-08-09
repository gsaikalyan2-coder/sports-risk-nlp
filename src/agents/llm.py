"""LLM access with cost-tier routing.

Two implementations behind one interface:

* `OfflineLLM`   - deterministic, no network, no spend. Used by tests, CI, and
                   the default container smoke run.
* `OpenRouterLLM` - real calls to OpenRouter via the OpenAI-compatible client.

Why an offline implementation exists at all: the Phase 6 gate has to be
re-runnable by anyone reviewing the artifact, including a conference reviewer
with no API key and no intention of spending money to check our work. Making
the *default* path free and deterministic is what makes that possible. It also
means a stray `pytest` can never bill the owner.

The offline responses are seeded from the prompt text, so the same prompt
always yields the same answer. That is what makes an offline run a usable
regression test rather than theatre.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Protocol

from .config import RoutingConfig, TierConfig
from .ledger import CostLedger, LedgerEntry


@dataclass(frozen=True)
class LLMResponse:
    """One completion, plus what it cost."""

    text: str
    model: str
    tier: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    offline: bool

    def as_json(self) -> dict[str, Any]:
        """Parse the response body as JSON, tolerating fenced code blocks.

        Models wrap JSON in ```json fences often enough that stripping them
        here saves the same defensive code in every caller.
        """
        body = self.text.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.DOTALL)
        if fence:
            body = fence.group(1)
        return json.loads(body)


class LLMClient(Protocol):
    """What the agent layer needs from a model. Deliberately small.

    `kind` declares the expected answer shape ("label", "verdict", "prose").
    Live backends ignore it; the offline stub uses it to return a correctly
    shaped synthetic answer without guessing from the prompt text.
    """

    def complete(
        self,
        *,
        system: str,
        user: str,
        tier: str,
        agent: str,
        phase: int,
        note: str = "",
        kind: str = "prose",
    ) -> LLMResponse: ...


def estimate_tokens(text: str) -> int:
    """Rough token count: ~4 characters per token for English prose.

    Used only for offline cost estimates and pre-flight budget checks. Live
    calls overwrite these with the provider's reported usage, which is
    authoritative.
    """
    return max(1, len(text) // 4)


class _BaseLLM:
    """Shared plumbing: tier lookup and ledger writing."""

    def __init__(self, routing: RoutingConfig, ledger: CostLedger | None = None):
        self.routing = routing
        self.ledger = ledger or CostLedger(routing.budget)

    def _tier(self, tier: str) -> TierConfig:
        if tier not in self.routing.tiers:
            raise ValueError(f"unknown tier {tier!r}; expected one of {list(self.routing.tiers)}")
        return self.routing.tiers[tier]

    def _log(
        self,
        *,
        agent: str,
        phase: int,
        tier: TierConfig,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        note: str,
        enforce: bool,
    ) -> None:
        self.ledger.record(
            LedgerEntry(
                agent=agent,
                phase=phase,
                tier=tier.name,
                model=tier.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                note=note,
            ),
            enforce=enforce,
        )


class OfflineLLM(_BaseLLM):
    """Deterministic stub. No network, no spend, reproducible.

    Responses are generated from a hash of the prompt, so they are stable
    across runs and machines. Where the caller asks for a construct label, the
    stub returns a well-formed record drawn from the real taxonomy -- the
    shape is correct even though the content is synthetic.
    """

    def __init__(
        self,
        routing: RoutingConfig,
        ledger: CostLedger | None = None,
        constructs: tuple[str, ...] = (),
        seed: int = 42,
    ):
        super().__init__(routing, ledger)
        self.constructs = constructs
        self.seed = seed

    def _rng(self, prompt: str) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}:{prompt}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    def complete(
        self,
        *,
        system: str,
        user: str,
        tier: str,
        agent: str,
        phase: int,
        note: str = "",
        kind: str = "prose",
    ) -> LLMResponse:
        tier_cfg = self._tier(tier)
        rng = self._rng(system + user)
        text = self._synthesise(kind, rng)

        input_tokens = estimate_tokens(system) + estimate_tokens(user)
        output_tokens = estimate_tokens(text)

        # Cost is recorded as 0.00 because nothing was spent. The token counts
        # are still real, so an offline run tells you what a live run WOULD
        # have cost -- useful for budgeting a Phase 10 batch before committing.
        self._log(
            agent=agent,
            phase=phase,
            tier=tier_cfg,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=0.0,
            note=(note + " [offline]").strip(),
            enforce=False,
        )
        return LLMResponse(
            text=text,
            model=f"{tier_cfg.model} (offline stub)",
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            offline=True,
        )

    def _synthesise(self, kind: str, rng: random.Random) -> str:
        """Produce a well-formed synthetic response of the declared shape.

        Dispatches on the caller's declared `kind`, never on prompt text --
        see the note in roster.TaskSpec for the bug that motivated this.
        """
        if kind == "label":
            pool = self.constructs or ("cognitive_anxiety",)
            construct = pool[rng.randrange(len(pool))]
            # Deliberately spans both sides of the 0.65 escalation threshold so
            # an offline run exercises the escalation path some of the time.
            confidence = round(rng.uniform(0.45, 0.95), 2)
            return json.dumps(
                {
                    "construct": construct,
                    "intensity": rng.randrange(0, 4),
                    "confidence": confidence,
                    "evidence_span": "offline stub - no span extracted",
                    "rationale": "Deterministic offline response; not a real model judgement.",
                },
                indent=2,
            )

        if kind == "verdict":
            return json.dumps(
                {
                    "verdict": "accept",
                    "issues": [],
                    "rationale": "Offline stub validation; shape checked, content not judged.",
                },
                indent=2,
            )

        return (
            "OFFLINE STUB RESPONSE. This text is generated locally with a fixed seed "
            "and contains no model output. Run with --live to call OpenRouter."
        )


class OpenRouterLLM(_BaseLLM):
    """Real OpenRouter calls through the OpenAI-compatible client."""

    def __init__(self, routing: RoutingConfig, ledger: CostLedger | None = None):
        super().__init__(routing, ledger)
        api_key = routing.api_key()
        if not api_key:
            raise RuntimeError(
                f"live mode needs {routing.api_key_env} set. Add it to .env "
                f"(see .env.example) or run with --offline."
            )
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise RuntimeError(
                "the 'openai' package is required for live mode; "
                "pip install -r requirements-base.txt"
            ) from exc

        self._client = OpenAI(
            base_url=routing.base_url,
            api_key=api_key,
            timeout=routing.timeout_seconds,
            max_retries=routing.max_retries,
        )

    def complete(
        self,
        *,
        system: str,
        user: str,
        tier: str,
        agent: str,
        phase: int,
        note: str = "",
        kind: str = "prose",  # noqa: ARG002 - part of the shared protocol
    ) -> LLMResponse:
        tier_cfg = self._tier(tier)

        # Pre-flight budget check on an ESTIMATE, before the call is made.
        # Checking after the fact would mean the money is already spent.
        projected = tier_cfg.estimate_cost_usd(
            estimate_tokens(system) + estimate_tokens(user), tier_cfg.max_tokens
        )
        self.ledger.check_affordable(projected)

        started = time.monotonic()
        completion = self._client.chat.completions.create(
            model=tier_cfg.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=tier_cfg.max_tokens,
            temperature=tier_cfg.temperature,
            extra_headers=_referer_headers(),
        )
        elapsed = time.monotonic() - started

        text = (completion.choices[0].message.content or "").strip()
        usage = getattr(completion, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) or estimate_tokens(system + user)
        output_tokens = getattr(usage, "completion_tokens", None) or estimate_tokens(text)
        cost = tier_cfg.estimate_cost_usd(input_tokens, output_tokens)

        self._log(
            agent=agent,
            phase=phase,
            tier=tier_cfg,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            note=(note + f" [live {elapsed:.1f}s]").strip(),
            enforce=False,  # already checked pre-flight; do not reject a paid call
        )
        return LLMResponse(
            text=text,
            model=tier_cfg.model,
            tier=tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            offline=False,
        )


def _referer_headers() -> dict[str, str]:
    """OpenRouter attribution headers. Optional, but good citizenship."""
    return {
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "https://github.com/sports-risk-nlp"),
        "X-Title": "sports-risk-nlp",
    }


def build_llm(
    routing: RoutingConfig,
    *,
    mode: str | None = None,
    ledger: CostLedger | None = None,
    constructs: tuple[str, ...] = (),
    seed: int = 42,
) -> LLMClient:
    """Construct the right client for the effective mode.

    `mode` overrides `config/model_routing.yaml` when the CLI passes
    --live / --offline.
    """
    effective = (mode or routing.mode).lower()
    if effective == "live":
        return OpenRouterLLM(routing, ledger)
    if effective == "offline":
        return OfflineLLM(routing, ledger, constructs=constructs, seed=seed)
    raise ValueError(f"mode must be 'offline' or 'live', got {effective!r}")
