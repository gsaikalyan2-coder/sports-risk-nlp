"""Phase 31 runner -- a thin shell over `src/evaluation/abstention.py`.

    python scripts/run_abstention_report.py
    python scripts/run_abstention_report.py --out reports/abstention.md

Everything worth testing lives in `src/evaluation/abstention.py`. This file owns
the two things a test must never do: read the corpus off disk and write a report
to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.evaluation.abstention import (  # noqa: E402
    build_report,
    load_corpus,
    render_markdown,
)
from src.evaluation.harness import PROVISIONAL_STAMP  # noqa: E402

CORPUS = REPO / "data" / "processed" / "gold_candidates"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPO / "reports" / "abstention.md")
    parser.add_argument("--json", type=Path, default=REPO / "reports" / "abstention.json")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    args = parser.parse_args(argv)

    corpus = load_corpus(args.corpus)
    if not corpus:
        print(f"No corpus found under {args.corpus}. Nothing to measure.", file=sys.stderr)
        return 1

    report = build_report(corpus, PROVISIONAL_STAMP)
    markdown = render_markdown(report, generated=date.today().isoformat())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    args.json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    corpus_result = report.corpus
    print(f"corpus n={corpus_result.n}")
    print(f"  false refusals    {corpus_result.refused} ({corpus_result.refusal_rate * 100:.1f}%)")
    print(
        f"  ungated midpoint  {corpus_result.ungated_midpoint} "
        f"({corpus_result.ungated_midpoint_rate * 100:.1f}%)  <- the finding"
    )
    print(f"junk refused        {report.refused_junk}/{report.junk_n}")
    print(f"wrote {args.out.relative_to(REPO)} and {args.json.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
