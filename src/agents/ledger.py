"""Cost ledger: every LLM call this project makes gets one row.

This is the artifact the Phase 6 gate asks for, and it is also the evidence
behind the "cost-aware pipeline" methods contribution in the paper. If a call
is not in the ledger, for our purposes it did not happen.

Budget enforcement is deliberately a *hard stop*. When the running month's
spend would exceed the cap, `record()` raises rather than trimming the batch
quietly. A job that dies with a clear message is recoverable; a labeling run
that silently processed 6,000 of 10,000 utterances is a corrupted dataset that
may not be noticed until the results look strange weeks later.
"""

from __future__ import annotations

import csv
import datetime as dt
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .config import BudgetConfig

LEDGER_COLUMNS = [
    "timestamp",
    "agent",
    "phase",
    "tier",
    "model",
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "note",
]

# Serialises appends. CrewAI can run agents concurrently, and two threads
# interleaving inside a single csv.writer call produces a torn row.
_WRITE_LOCK = threading.Lock()


class BudgetExceededError(RuntimeError):
    """Raised when a call would push the month's spend past the configured cap."""


@dataclass
class LedgerEntry:
    agent: str
    phase: int
    tier: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    note: str = ""
    timestamp: str = field(
        default_factory=lambda: dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    )

    def as_row(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "agent": self.agent,
            "phase": self.phase,
            "tier": self.tier,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": f"{self.cost_usd:.6f}",
            "note": self.note,
        }


class CostLedger:
    """Append-only CSV of LLM spend, with a monthly cap."""

    def __init__(self, budget: BudgetConfig):
        self.budget = budget
        self.path = Path(budget.ledger_path)
        self._ensure_header()

    def _ensure_header(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS).writeheader()

    # -- reading -----------------------------------------------------------

    def rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def spend_this_month(self, now: dt.datetime | None = None) -> float:
        """Total USD recorded in the current calendar month (UTC)."""
        now = now or dt.datetime.now(dt.UTC)
        prefix = now.strftime("%Y-%m")
        total = 0.0
        for row in self.rows():
            if not row.get("timestamp", "").startswith(prefix):
                continue
            try:
                total += float(row.get("cost_usd") or 0.0)
            except ValueError:
                # A malformed row should not silently zero out the running
                # total and hand back an under-estimate of spend.
                continue
        return total

    # -- writing -----------------------------------------------------------

    def check_affordable(self, cost_usd: float) -> None:
        """Raise if this cost would breach the cap. No-op when enforce is off."""
        if not self.budget.enforce or cost_usd <= 0:
            return
        current = self.spend_this_month()
        if current + cost_usd > self.budget.monthly_cap_usd:
            raise BudgetExceededError(
                f"call would cost ${cost_usd:.4f}; month-to-date spend is "
                f"${current:.4f} against a ${self.budget.monthly_cap_usd:.2f} cap. "
                f"Raise budget.monthly_cap_usd in config/model_routing.yaml, or "
                f"switch to offline mode, or wait for the next month."
            )

    def record(self, entry: LedgerEntry, *, enforce: bool = True) -> None:
        """Append one row, after an optional affordability check."""
        if enforce:
            self.check_affordable(entry.cost_usd)
        with _WRITE_LOCK:
            self._ensure_header()
            with self.path.open("a", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS).writerow(entry.as_row())

        if self.budget.enforce:
            spent = self.spend_this_month()
            threshold = self.budget.monthly_cap_usd * self.budget.warn_at_fraction
            if spent >= threshold:
                pct = 100 * spent / self.budget.monthly_cap_usd
                print(
                    f"  [budget] WARNING: ${spent:.4f} of "
                    f"${self.budget.monthly_cap_usd:.2f} used this month ({pct:.0f}%)"
                )

    # -- reporting ---------------------------------------------------------

    def summary(self) -> str:
        rows = self.rows()
        spent = self.spend_this_month()
        return (
            f"ledger: {len(rows)} call(s) recorded at {_display_path(self.path)}; "
            f"${spent:.6f} spent this month of ${self.budget.monthly_cap_usd:.2f} cap"
        )


def _display_path(path: Path) -> str:
    """Repo-relative path when possible, so logs do not leak absolute paths."""
    try:
        return str(path.relative_to(Path(os.getcwd())))
    except ValueError:
        return str(path)
