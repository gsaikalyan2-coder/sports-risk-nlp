"""Phase 6 gate: run one orchestrated multi-agent task end to end.

    python scripts/run_crew.py                      # offline, free, deterministic
    python scripts/run_crew.py --live               # real OpenRouter calls
    python scripts/run_crew.py --engine crewai --live
    python scripts/run_crew.py --show-ledger

Offline is the default and costs nothing. Live mode needs OPENROUTER_API_KEY in
.env and will spend real money -- it prints an estimate and the running monthly
total before it starts.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load .env before anything reads OPENROUTER_API_KEY. Docker Compose injects
# these via env_file, but a bare `python scripts/run_crew.py` on the host would
# otherwise see no key and report live mode as unconfigured even though .env
# has one. Existing environment variables win, so an explicitly exported key
# still overrides the file.
try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover - python-dotenv is a declared dependency
    pass

from src.agents import (  # noqa: E402  (path bootstrap must run first)
    ConfigError,
    CostLedger,
    build_llm,
    construct_names,
    load_routing,
    load_taxonomy,
    run_smoke_crew,
)
from src.agents.ledger import BudgetExceededError  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Phase 6 smoke-test crew.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        dest="mode",
        action="store_const",
        const="offline",
        help="deterministic stub LLM; no network, no spend (default)",
    )
    mode.add_argument(
        "--live",
        dest="mode",
        action="store_const",
        const="live",
        help="real OpenRouter calls; requires OPENROUTER_API_KEY",
    )
    parser.add_argument(
        "--engine",
        choices=("simple", "crewai"),
        default="simple",
        help="orchestration backend (default: simple)",
    )
    parser.add_argument("--seed", type=int, default=42, help="offline determinism seed")
    parser.add_argument(
        "--utterance",
        default=None,
        help="override the synthetic test utterance",
    )
    parser.add_argument(
        "--show-ledger",
        action="store_true",
        help="print the cost ledger and exit",
    )
    parser.set_defaults(mode=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        routing = load_routing()
    except ConfigError as exc:
        print(f"FAIL  configuration error: {exc}")
        return 2

    ledger = CostLedger(routing.budget)

    if args.show_ledger:
        rows = ledger.rows()
        print(f"=== cost ledger ({len(rows)} row(s)) ===")
        for row in rows[-25:]:
            print(
                f"  {row['timestamp']}  {row['agent']:<16} {row['tier']:<8} "
                f"{row['model']:<34} ${row['cost_usd']}  {row['note']}"
            )
        print(ledger.summary())
        return 0

    mode = args.mode or routing.mode

    print("=== sports-risk-nlp :: Phase 6 smoke crew ===")
    print(f"engine : {args.engine}")
    print(f"mode   : {mode}")

    if mode == "live":
        if routing.api_key() is None:
            print(
                f"\nFAIL  live mode needs {routing.api_key_env} in .env.\n"
                f"      Copy .env.example to .env and add your OpenRouter key,\n"
                f"      or drop --live to run the free offline path."
            )
            return 2
        spent = ledger.spend_this_month()
        print(f"budget : ${spent:.4f} spent of ${routing.budget.monthly_cap_usd:.2f} this month")
        print("         live mode makes real API calls and will cost money.")

    try:
        constructs = construct_names(load_taxonomy())
    except ConfigError as exc:
        print(f"FAIL  taxonomy error: {exc}")
        return 2
    print(f"taxonomy: {len(constructs)} constructs loaded")

    try:
        llm = build_llm(routing, mode=mode, ledger=ledger, constructs=constructs, seed=args.seed)
    except RuntimeError as exc:
        print(f"FAIL  {exc}")
        return 2

    print("\n--- running ---")
    try:
        run = run_smoke_crew(
            llm,
            routing,
            engine=args.engine,
            mode=mode,
            **({"utterance": args.utterance} if args.utterance else {}),
        )
    except BudgetExceededError as exc:
        print(f"FAIL  budget cap reached: {exc}")
        return 3
    except Exception as exc:  # noqa: BLE001 - the runner is the top-level boundary
        print(f"FAIL  crew run raised {type(exc).__name__}: {exc}")
        return 1

    print("\n--- result ---")
    for line in run.summary_lines():
        print(line)

    print()
    print(ledger.summary())

    if not run.ok:
        print("\nPhase 6 gate: FAILED - one or more tasks reported issues.")
        return 1

    print("\nPhase 6 gate: PASSED - orchestrated run completed and logged to the ledger.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
