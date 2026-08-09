"""Configuration loading for the agent layer.

Single place that reads `config/model_routing.yaml` and `config/settings.yaml`
so no other module has to know where those files live or how they are shaped.

Design note: every value the agents need is validated *here*, at load time, and
fails loudly. A typo in a tier name should stop the run immediately rather than
surface as a confusing `KeyError` three agents deep into an orchestration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTING_PATH = REPO_ROOT / "config" / "model_routing.yaml"
SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"
TAXONOMY_PATH = REPO_ROOT / "config" / "taxonomy.yaml"

VALID_TIERS = ("cheap", "mid", "premium")


class ConfigError(RuntimeError):
    """Raised when configuration is missing, malformed, or internally inconsistent."""


@dataclass(frozen=True)
class TierConfig:
    """One cost tier: which model to call and what it costs."""

    name: str
    model: str
    price_per_1m_input_usd: float
    price_per_1m_output_usd: float
    max_tokens: int
    temperature: float
    use_for: tuple[str, ...]

    def estimate_cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Estimated USD for a call of this size.

        Estimate, not billing truth -- see the provenance note in
        config/model_routing.yaml. Good enough to keep a running total against
        the monthly cap, not good enough to reconcile an invoice.
        """
        return (
            input_tokens * self.price_per_1m_input_usd
            + output_tokens * self.price_per_1m_output_usd
        ) / 1_000_000


@dataclass(frozen=True)
class BudgetConfig:
    monthly_cap_usd: float
    warn_at_fraction: float
    ledger_path: Path
    enforce: bool


@dataclass(frozen=True)
class RoutingConfig:
    """The whole routing policy, validated."""

    mode: str
    base_url: str
    api_key_env: str
    timeout_seconds: int
    max_retries: int
    budget: BudgetConfig
    tiers: dict[str, TierConfig]
    agent_defaults: dict[str, str]
    confidence_threshold: float
    max_tier: str
    max_escalations_per_record: int

    def tier_for_agent(self, agent_key: str) -> str:
        """Default tier for a named agent, falling back to the cheapest."""
        return self.agent_defaults.get(agent_key, "cheap")

    def next_tier(self, tier: str) -> str | None:
        """The next tier up, or None if already at the escalation ceiling."""
        order = list(VALID_TIERS)
        if tier not in order:
            raise ConfigError(f"unknown tier {tier!r}")
        ceiling = order.index(self.max_tier)
        current = order.index(tier)
        if current >= ceiling:
            return None
        return order[current + 1]

    def api_key(self) -> str | None:
        """The OpenRouter key from the environment, or None if unset."""
        key = os.environ.get(self.api_key_env, "").strip()
        return key or None


def _require(mapping: dict[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise ConfigError(f"missing required key {key!r} in {where}")
    return mapping[key]


def load_routing(path: Path | None = None) -> RoutingConfig:
    """Load and validate config/model_routing.yaml."""
    path = path or ROUTING_PATH
    if not path.exists():
        raise ConfigError(f"routing config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} did not parse to a mapping")

    mode = raw.get("mode", "offline")
    if mode not in ("offline", "live"):
        raise ConfigError(f"mode must be 'offline' or 'live', got {mode!r}")

    api = _require(raw, "api", str(path))
    budget_raw = _require(raw, "budget", str(path))
    budget = BudgetConfig(
        monthly_cap_usd=float(_require(budget_raw, "monthly_cap_usd", "budget")),
        warn_at_fraction=float(budget_raw.get("warn_at_fraction", 0.75)),
        ledger_path=REPO_ROOT / budget_raw.get("ledger_path", "logs/cost_ledger.csv"),
        enforce=bool(budget_raw.get("enforce", True)),
    )

    tiers_raw = _require(raw, "tiers", str(path))
    tiers: dict[str, TierConfig] = {}
    for name in VALID_TIERS:
        if name not in tiers_raw:
            raise ConfigError(f"tier {name!r} missing from {path}")
        t = tiers_raw[name]
        tiers[name] = TierConfig(
            name=name,
            model=str(_require(t, "model", f"tiers.{name}")),
            price_per_1m_input_usd=float(_require(t, "price_per_1m_input_usd", f"tiers.{name}")),
            price_per_1m_output_usd=float(_require(t, "price_per_1m_output_usd", f"tiers.{name}")),
            max_tokens=int(t.get("max_tokens", 1024)),
            temperature=float(t.get("temperature", 0.0)),
            use_for=tuple(t.get("use_for", ())),
        )

    esc = raw.get("escalation", {})
    max_tier = esc.get("max_tier", "premium")
    if max_tier not in VALID_TIERS:
        raise ConfigError(f"escalation.max_tier must be one of {VALID_TIERS}, got {max_tier!r}")

    agent_defaults = dict(raw.get("agent_defaults", {}))
    for agent, tier in agent_defaults.items():
        # 'local' means the agent runs on this machine and spends nothing.
        if tier not in VALID_TIERS and tier != "local":
            raise ConfigError(
                f"agent_defaults.{agent} = {tier!r} is not a valid tier "
                f"(expected one of {VALID_TIERS} or 'local')"
            )

    return RoutingConfig(
        mode=mode,
        base_url=str(api.get("base_url", "https://openrouter.ai/api/v1")),
        api_key_env=str(api.get("api_key_env", "OPENROUTER_API_KEY")),
        timeout_seconds=int(api.get("timeout_seconds", 120)),
        max_retries=int(api.get("max_retries", 3)),
        budget=budget,
        tiers=tiers,
        agent_defaults=agent_defaults,
        confidence_threshold=float(esc.get("confidence_threshold", 0.65)),
        max_tier=max_tier,
        max_escalations_per_record=int(esc.get("max_escalations_per_record", 1)),
    )


def load_settings(path: Path | None = None) -> dict[str, Any]:
    """Load config/settings.yaml (seed, paths, model defaults)."""
    path = path or SETTINGS_PATH
    if not path.exists():
        raise ConfigError(f"settings not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path} did not parse to a mapping")
    return data


def load_taxonomy(path: Path | None = None) -> dict[str, Any]:
    """Load config/taxonomy.yaml.

    The agent layer needs this to validate that a proposed construct label is
    actually in the frozen taxonomy. Agents must never invent constructs --
    CLAUDE.md sec.3.
    """
    path = path or TAXONOMY_PATH
    if not path.exists():
        raise ConfigError(f"taxonomy not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError(f"{path} did not parse to a mapping")
    return data


def construct_names(taxonomy: dict[str, Any] | None = None) -> tuple[str, ...]:
    """The valid construct keys, in file order.

    taxonomy.yaml is locked at v2 (Phase 4) with `constructs` as a mapping of
    construct_key -> record. Ten constructs plus a separate
    `interpretation_modifier`, which is a modifier rather than a construct and
    is deliberately not returned here.
    """
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    constructs = tax.get("constructs")
    if not isinstance(constructs, dict) or not constructs:
        raise ConfigError(
            "taxonomy.yaml has no readable 'constructs' mapping -- "
            "expected v2 schema with constructs: {name: {...}}"
        )
    return tuple(constructs.keys())


def risk_direction(construct: str, taxonomy: dict[str, Any] | None = None) -> str:
    """Whether a construct raises, lowers, or does not move the risk index.

    Consumed by the Phase 15 fusion step. Surfaced here so the agent layer can
    show a direction alongside a proposed label without re-parsing the file.
    """
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    record = tax.get("constructs", {}).get(construct)
    if record is None:
        raise ConfigError(f"{construct!r} is not in the taxonomy")
    return str(record.get("risk_direction", "unknown"))
