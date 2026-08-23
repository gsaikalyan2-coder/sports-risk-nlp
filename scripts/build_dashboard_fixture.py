"""Build the dashboard's committed known-example fixture.

Why a fixture at all, rather than reading the reports directly
---------------------------------------------------------------
`reports/explain/cards.md` and `attributions.json` are regenerated every time
`scripts/run_explain.py` runs. A gate that compares the dashboard against a file
that moves with the dashboard's own inputs is not a gate -- it is the Phase 18
defect again, a check related to the thing it protects by assumption. So the
known examples are frozen into `tests/fixtures/dashboard_known_examples.json`,
committed, and the gate compares the dashboard's rendering of the *fixture* to
the committed `cards.md`. The two agree today; if either moves, the test says so.

How the probabilities are recovered, and why this is exact
-----------------------------------------------------------
`cards.md` prints probabilities rounded to two decimals, which is not enough to
reproduce a risk index. It also prints each construct's contribution to three
decimals, and `contribution = probability * weight` with the weight fixed by
`DEFAULT_MAGNITUDES`. Dividing recovers the probability at three-decimal
precision, which is finer than anything displayed. Polarity-bearing constructs
never appear in the drivers table -- they contribute exactly zero under the
default policy -- so their probabilities come from `attributions.json` where the
attribution run recorded them, and are zero otherwise.

The script then *verifies* the reconstruction by re-rendering the card and
comparing it to the committed markdown, and refuses to write a fixture that does
not reproduce byte for byte. A fixture builder that cannot demonstrate its own
output is correct would just be moving the problem.

Run:  python scripts/build_dashboard_fixture.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.harness import PROVISIONAL_STAMP  # noqa: E402
from src.explainability.attribution import (  # noqa: E402
    ConstructExplanation,
    RecordExplanation,
    TokenAttribution,
)
from src.explainability.cards import build_card, render_markdown  # noqa: E402
from src.models.dataset import CONSTRUCTS  # noqa: E402
from src.risk.fusion import LinearRiskScorer  # noqa: E402

CARDS_MD = REPO_ROOT / "reports" / "explain" / "cards.md"
ATTRIBUTIONS = REPO_ROOT / "reports" / "explain" / "attributions.json"
OUT = REPO_ROOT / "tests" / "fixtures" / "dashboard_known_examples.json"

#: Three records, chosen for what they teach rather than for looking good:
#:   002391  a low-risk record where every driver is unevidenced -- the honest
#:           failure mode, on screen by default rather than buried
#:   003481  the clearest positive case: one dominant construct with real spans
#:   001466  a middling record with two raising constructs and no spans at all
#: Between them a viewer sees the system working, the system asserting without
#: evidence, and the difference between the two.
WANTED = (
    "synth_precomp_v1-003481",
    "synth_precomp_v1-002391",
    "synth_precomp_v1-001466",
)

ROW = re.compile(
    r"^\|\s*(?P<construct>[a-z_]+)\s*\|\s*(?P<p>[\d.]+)\s*\|\s*(?P<direction>\w+)\s*\|"
    r"\s*(?P<contribution>[+-][\d.]+)\s*\|"
)


def parse_cards(text: str) -> dict[str, dict[str, float]]:
    """Recover per-construct contributions from the rendered card tables."""
    out: dict[str, dict[str, float]] = {}
    for block in text.split("\n### ")[1:]:
        record_id = block.split("`")[1]
        rows: dict[str, float] = {}
        for line in block.splitlines():
            match = ROW.match(line)
            if match:
                rows[match.group("construct")] = float(match.group("contribution"))
        out[record_id] = rows
    return out


def card_blocks(text: str) -> dict[str, str]:
    blocks = {}
    for block in text.split("\n### ")[1:]:
        record_id = block.split("`")[1]
        blocks[record_id] = ("### " + block).rstrip() + "\n"
    return blocks


def main() -> int:
    cards_md = CARDS_MD.read_text(encoding="utf-8")
    contributions = parse_cards(cards_md)
    blocks = card_blocks(cards_md)
    attributions = {
        record["record_id"]: record
        for record in json.loads(ATTRIBUTIONS.read_text(encoding="utf-8"))["integrated_gradients"]
    }

    scorer = LinearRiskScorer()
    examples = []
    for record_id in WANTED:
        source = attributions[record_id]
        probabilities = {c: 0.0 for c in CONSTRUCTS}

        # Polarity-bearing constructs: never in the drivers table, so taken from
        # the attribution run, which recorded them at full precision.
        for explanation in source["explanations"]:
            probabilities[explanation["construct"]] = float(explanation["probability"])

        # Everything that moved the index: recovered from contribution / weight.
        for construct, contribution in contributions[record_id].items():
            weight = scorer.magnitudes[construct]
            direction = scorer.directions[construct]
            signed = weight if direction.value == "raises" else -weight
            probabilities[construct] = round(contribution / signed, 6)

        examples.append(
            {
                "record_id": record_id,
                "text": source["text"],
                "method": source["method"],
                "provenance": source["provenance"],
                "synthetic": True,
                "probabilities": probabilities,
                "explanations": [
                    {
                        "construct": e["construct"],
                        "probability": e["probability"],
                        "method": source["method"],
                        "completeness_error": e.get("completeness_error"),
                        "tokens": e["tokens"],
                    }
                    for e in source["explanations"]
                ],
            }
        )

    # ---- verify before writing -------------------------------------------
    failures = []
    for example in examples:
        explanation = RecordExplanation(
            record_id=example["record_id"],
            text=example["text"],
            method=example["method"],
            provenance=example["provenance"],
            explanations=tuple(
                ConstructExplanation(
                    construct=e["construct"],
                    probability=e["probability"],
                    method=e["method"],
                    tokens=tuple(
                        TokenAttribution(
                            token=t["token"],
                            start=int(t["start"]),
                            end=int(t["end"]),
                            score=float(t["score"]),
                        )
                        for t in e["tokens"]
                    ),
                    completeness_error=e.get("completeness_error"),
                    source_text=example["text"],
                )
                for e in example["explanations"]
            ),
        )
        risk = scorer.score(example["probabilities"])
        card = build_card(explanation=explanation, risk=risk, synthetic=True)
        rendered = render_markdown(card).rstrip() + "\n"
        expected = blocks[example["record_id"]]
        if rendered != expected:
            failures.append((example["record_id"], expected, rendered))

    if failures:
        for record_id, expected, rendered in failures:
            print(f"--- {record_id}: reconstruction does NOT reproduce cards.md ---")
            for a, b in zip(expected.splitlines(), rendered.splitlines(), strict=False):
                if a != b:
                    print(f"  expected: {a}\n  actual:   {b}")
        print("\nRefusing to write a fixture that does not reproduce its source.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "reports/explain/cards.md",
                "built_by": "scripts/build_dashboard_fixture.py",
                "provenance": PROVISIONAL_STAMP,
                "note": (
                    "Frozen Phase 17 outputs on synthetic corpus records. Probabilities "
                    "recovered from each card's contribution/weight; polarity-bearing "
                    "constructs taken from reports/explain/attributions.json. Verified "
                    "to re-render reports/explain/cards.md byte for byte at build time."
                ),
                "examples": examples,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT.relative_to(REPO_ROOT)} with {len(examples)} verified examples.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
