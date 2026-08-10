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
        #: Running month-to-date total, as (month_prefix, usd). See
        #: `spend_this_month` for why this cache exists.
        self._cached_month: tuple[str, float] | None = None
        self._header_ready = False
        self._ensure_header()

    def _ensure_header(self) -> None:
        """Create the ledger file with a header if it is missing. Runs once.

        `record()` used to call this on every append, which is three filesystem
        syscalls (`mkdir`, `exists`, `stat`) per LLM call. On the owner's setup
        those cost ~13 ms each, so a 9,260-prompt Phase 10 pass spent about
        three minutes doing nothing but re-asking whether a file it had just
        written to still existed -- 95% of the run's wall time, measured with
        cProfile. Once per instance is sufficient: nothing in this process
        deletes the ledger mid-run, and if something outside it did, silently
        recreating the file would be the wrong response anyway.
        """
        if self._header_ready:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as fh:
                csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS).writeheader()
        self._header_ready = True

    # -- reading -----------------------------------------------------------

    def rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def spend_this_month(self, now: dt.datetime | None = None) -> float:
        """Total USD recorded in the current calendar month (UTC).

        Cached after the first read and maintained incrementally by `record()`.

        The cache is a Phase 10 fix for a Phase 6 defect that only volume could
        expose. Every `record()` calls this to decide whether to print the
        budget warning, and every `check_affordable()` calls it too. Reading and
        parsing the whole CSV each time makes a run of N calls cost O(N^2) row
        parses: fine for the Phase 6 smoke crew's handful of calls, and roughly
        43 million parses for a 9,260-prompt labelling pass, which does not
        finish in any reasonable time. The behaviour is unchanged; only the
        number of times the file is read is.

        `refresh()` drops the cache for the case this misses -- another process
        appending to the same ledger concurrently. Nothing in the project does
        that today, and a stale cache would under-report spend, so the escape
        hatch is explicit rather than implied.
        """
        now = now or dt.datetime.now(dt.UTC)
        prefix = now.strftime("%Y-%m")
        if self._cached_month is not None and self._cached_month[0] == prefix:
            return self._cached_month[1]
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
        self._cached_month = (prefix, total)
        return total

    def refresh(self) -> None:
        """Drop the month-total cache, forcing the next read to hit disk."""
        self._cached_month = None

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
            # Maintained under the same lock as the append, so the cache and the
            # file cannot disagree about how many rows exist.
            prefix = entry.timestamp[:7]
            if self._cached_month is not None and self._cached_month[0] == prefix:
                self._cached_month = (prefix, self._cached_month[1] + float(entry.cost_usd))
            else:
                self._cached_month = None

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
