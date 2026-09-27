"""Build the committed corpus-cloud artifact for the constellation page.

Why an artifact rather than a live computation
---------------------------------------------
Scoring 4,000 records through `build_view` takes about three minutes: 45 ms each,
almost all of it building an `ExplanationCard` and merging span attributions. A
Streamlit page that did that on load would be a three-minute cold start on every
container restart, and a page that cached it would be a three-minute cold start
followed by a stale cache nobody could date. So the numbers are computed once,
offline, committed, and replayed -- exactly the argument
`src/dashboard/backend.py::ReplayBackend` already makes for the known examples.

`data/raw/` is gitignored (regenerable at seed 42), so the artifact is the only
part of this that a fresh clone has. That is intentional: a reader who has not
regenerated the corpus still gets the figure, and a reader who has can rebuild
the artifact and diff it.

What is deliberately NOT in the output
--------------------------------------
* **No record text.** The corpus is synthetic, but there is no reason for a
  committed report to carry 4,000 passages, and `docs/security.md` is easier to
  keep true when an artifact holds only numbers.
* **No timestamp.** A build date would make every rebuild a diff, which turns a
  gate into noise. The corpus seed is the provenance.
* **No index for a record the detector said nothing about.** This is the rule
  from `.claude.md` section 12.3 and it is why this script has the shape it does.
  A record with no cue match scores ten zeroes, sums to 0.0 and squashes to
  exactly 0.50; writing that down would put a spike of records at the midpoint of
  a figure about where records sit. Those records are counted and excluded, per
  lane and in total.

Run:  python scripts/build_corpus_cloud.py
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.dashboard.backend import LexiconBackend  # noqa: E402
from src.dashboard.view import build_view  # noqa: E402
from src.evaluation.harness import PROVISIONAL_STAMP  # noqa: E402
from src.models.dataset import CONSTRUCTS  # noqa: E402

RECORDS = REPO_ROOT / "data" / "raw" / "synth_precomp_v1" / "records.jsonl"
OUT = REPO_ROOT / "reports" / "corpus_cloud.json"

#: Dots per lane in the committed artifact.
#:
#: The lane medians and counts are computed over EVERY scored record; only the
#: plotted dots are sampled. Eighty is where a 400 px lane stops gaining
#: information -- past it the dots overplot into a solid bar and the file grows
#: for nothing. The sample is a fixed stride through corpus order, never a random
#: draw: a paper figure that moves between runs cannot be diffed.
DOTS_PER_LANE = 80

PROVENANCE = (
    "Risk index for every record of the synthetic corpus synth_precomp_v1, scored by "
    "the Phase 13 lexicon baseline through src/dashboard/view.py::build_view under the "
    "conservative default polarity policy. The lexicon is the honest floor, not the "
    "paper's model, and it is not independent of this corpus (OPEN-021): its cue list "
    "and the corpus template bank were both written from config/taxonomy.yaml. Lanes "
    "are the constructs the generator planted, so a lane says what a record was built "
    "to contain, not what any human judged it to contain. No record text is stored here."
)


def _stride(values: list[float], limit: int) -> list[float]:
    """Up to `limit` values, evenly spaced through the list, order preserved."""
    if len(values) <= limit:
        return list(values)
    step = len(values) / limit
    return [values[int(i * step)] for i in range(limit)]


def main() -> int:
    if not RECORDS.exists():
        print(
            f"{RECORDS} is missing. The corpus is gitignored and regenerable: run\n"
            "    python scripts/run_ingestion.py --seed 42\n"
            "and try again.",
            file=sys.stderr,
        )
        return 1

    backend = LexiconBackend()
    scored: dict[str, list[float]] = {construct: [] for construct in sorted(CONSTRUCTS)}
    planted_counts: dict[str, int] = {construct: 0 for construct in sorted(CONSTRUCTS)}
    silent_counts: dict[str, int] = {construct: 0 for construct in sorted(CONSTRUCTS)}
    n_records = n_scored = n_silent = n_unplanted = 0
    scale_label = caveat = ""

    with RECORDS.open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            n_records += 1
            spec = record.get("generation_spec") or {}
            planted = sorted({entry["construct"] for entry in spec.get("planted_constructs") or []})
            if not planted:
                # Records the generator planted nothing in. Counted rather than
                # dropped: they are a real part of the corpus, and a figure over
                # "every record" that silently omits some of them carries a total
                # nobody can reconcile.
                n_unplanted += 1

            view = build_view(text=record["text"], backend=backend)
            scale_label = scale_label or view.scale_label
            caveat = caveat or view.caveat
            detected = any(bar.detected for bar in view.bars)
            if detected:
                n_scored += 1
            else:
                n_silent += 1

            for construct in planted:
                planted_counts[construct] += 1
                if detected:
                    scored[construct].append(view.risk.value)
                else:
                    silent_counts[construct] += 1

            if n_records % 500 == 0:
                print(f"  {n_records} records scored", file=sys.stderr)

    payload = {
        "built_by": "scripts/build_corpus_cloud.py",
        "corpus": "synth_precomp_v1",
        "backend": "lexicon",
        "policy": "conservative default (neutral polarity)",
        "stamp": PROVISIONAL_STAMP,
        "provenance": PROVENANCE,
        "scale_label": scale_label,
        "caveat": caveat,
        "n_records": n_records,
        "n_scored": n_scored,
        "n_silent": n_silent,
        "n_unplanted": n_unplanted,
        "dots_per_lane": DOTS_PER_LANE,
        "lanes": [
            {
                "construct": construct,
                "n_planted": planted_counts[construct],
                "n_scored": len(values),
                "n_silent": silent_counts[construct],
                # Rounded to three places: finer than the figure can draw, coarse
                # enough that the file diffs cleanly.
                "median": round(statistics.median(values), 3) if values else None,
                "dots": [round(value, 3) for value in _stride(values, DOTS_PER_LANE)],
            }
            for construct, values in scored.items()
        ],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT.relative_to(REPO_ROOT)}: {n_scored} of {n_records} records scored, "
        f"{n_silent} with nothing detected, {n_unplanted} with nothing planted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
