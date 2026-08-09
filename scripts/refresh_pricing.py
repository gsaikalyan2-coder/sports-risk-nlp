"""Check config/model_routing.yaml against OpenRouter's live catalogue.

    python scripts/refresh_pricing.py --check     # report drift, exit 1 if any
    python scripts/refresh_pricing.py --write     # rewrite prices in place

Why this exists. Model IDs and prices on OpenRouter change without notice, and
both failure modes are nasty:

* a retired model ID returns 404 and kills a labeling run partway through,
  leaving a half-written silver dataset;
* a price change silently invalidates every cost estimate in the ledger, and
  therefore the cost-aware-pipeline claim in the paper.

Neither is visible until it bites, so check before any large batch and before
quoting numbers in the write-up. Requires network access; nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import yaml  # noqa: E402

MODELS_URL = "https://openrouter.ai/api/v1/models"
ROUTING_PATH = REPO_ROOT / "config" / "model_routing.yaml"
TIERS = ("cheap", "mid", "premium")
# Prices are floats; compare with a tolerance rather than for exact equality.
PRICE_TOLERANCE_USD = 1e-6


def fetch_catalogue(url: str = MODELS_URL, timeout: int = 30) -> dict[str, dict[str, float]]:
    """Return {model_id: {"input": usd_per_1m, "output": usd_per_1m}}."""
    request = urllib.request.Request(url, headers={"User-Agent": "sports-risk-nlp/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))

    catalogue: dict[str, dict[str, float]] = {}
    for model in payload.get("data", []):
        pricing = model.get("pricing") or {}
        try:
            catalogue[model["id"]] = {
                "input": float(pricing.get("prompt", 0) or 0) * 1_000_000,
                "output": float(pricing.get("completion", 0) or 0) * 1_000_000,
            }
        except (TypeError, ValueError):
            continue
    return catalogue


def compare(routing: dict, catalogue: dict[str, dict[str, float]]) -> list[str]:
    """Return a list of human-readable drift messages. Empty means clean."""
    problems: list[str] = []
    tiers = routing.get("tiers", {})

    for tier_name in TIERS:
        tier = tiers.get(tier_name)
        if not tier:
            problems.append(f"{tier_name}: tier missing from config")
            continue

        model_id = tier.get("model")
        if model_id not in catalogue:
            problems.append(
                f"{tier_name}: model {model_id!r} is NOT in the live catalogue. "
                f"A run using this tier will fail with a 404."
            )
            continue

        live = catalogue[model_id]
        for field, live_key in (
            ("price_per_1m_input_usd", "input"),
            ("price_per_1m_output_usd", "output"),
        ):
            configured = float(tier.get(field, 0))
            actual = live[live_key]
            if abs(configured - actual) > PRICE_TOLERANCE_USD:
                pct = (actual - configured) / configured * 100 if configured else float("inf")
                problems.append(
                    f"{tier_name}.{field}: config ${configured:.4f} vs live "
                    f"${actual:.4f} ({pct:+.0f}%)"
                )
    return problems


def apply_prices(routing: dict, catalogue: dict[str, dict[str, float]]) -> int:
    """Overwrite configured prices with live ones. Returns the count changed."""
    changed = 0
    for tier_name in TIERS:
        tier = routing.get("tiers", {}).get(tier_name)
        if not tier or tier.get("model") not in catalogue:
            continue
        live = catalogue[tier["model"]]
        for field, live_key in (
            ("price_per_1m_input_usd", "input"),
            ("price_per_1m_output_usd", "output"),
        ):
            if abs(float(tier.get(field, 0)) - live[live_key]) > PRICE_TOLERANCE_USD:
                tier[field] = round(live[live_key], 6)
                changed += 1
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="report drift only (default)")
    action.add_argument("--write", action="store_true", help="rewrite prices in the config")
    args = parser.parse_args(argv)

    routing = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8"))

    try:
        catalogue = fetch_catalogue()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"FAIL  could not reach OpenRouter: {exc}")
        return 2

    print(f"live catalogue: {len(catalogue)} models")
    problems = compare(routing, catalogue)

    if not problems:
        print("PASS  every configured model exists and every price matches.")
        return 0

    print(f"\n{len(problems)} issue(s):")
    for problem in problems:
        print(f"  - {problem}")

    if args.write:
        changed = apply_prices(routing, catalogue)
        if changed:
            # NOTE: yaml.safe_dump discards the extensive comments in
            # model_routing.yaml. Review the diff before committing, and
            # restore any commentary you still want.
            ROUTING_PATH.write_text(
                yaml.safe_dump(routing, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
            print(f"\nWROTE {changed} price field(s) to {ROUTING_PATH.name}.")
            print("WARNING: comments in the YAML were dropped. Check `git diff`.")
        missing = [p for p in problems if "NOT in the live catalogue" in p]
        if missing:
            print("\nModel IDs cannot be fixed automatically -- choose replacements by hand.")
            return 1
        return 0

    print("\nRe-run with --write to update prices, or edit the config by hand.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
