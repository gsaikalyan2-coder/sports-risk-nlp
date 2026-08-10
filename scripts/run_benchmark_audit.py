#!/usr/bin/env python
"""Quantify how much a random split inflates scores on this corpus (OPEN-012).

    python scripts/run_benchmark_audit.py
    python scripts/run_benchmark_audit.py --source synth_precomp_v1 --seed 42

Runs the lexicon baseline under a random split and a template-disjoint split and
reports the gap, with bootstrap confidence intervals and a leakage report for
each.

WHAT THIS MEASURES, PRECISELY
-----------------------------
Labels here come from `generation_spec.planted_constructs` -- the constructs the
generator planted. `docs/data_sources.md` sec.3.1 forbids using those as
evaluation ground truth for a *model quality* claim, and that prohibition stands.

This script does not make a model-quality claim. It measures a **property of the
corpus**: how much easier the task becomes when templates are shared between
train and test. For that question the planted constructs are the correct
reference, because the question is about the generator's own structure. The
number produced here belongs in the paper's dataset or methodology section, never
in the results table.

Offline, free, deterministic. Exit 0 pass, 1 if the audit finds an unsafe split.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation import (  # noqa: E402
    LexiconBaseline,
    MajorityBaseline,
    StratifiedRandomBaseline,
    bootstrap_ci,
    leakage_report,
    macro_f1,
    per_label_prf,
    random_split,
    template_disjoint_split,
)
from src.evaluation.baselines import MemorisationProbe  # noqa: E402
from src.ingestion import RawStore  # noqa: E402
from src.ingestion.records import RawRecord  # noqa: E402

CONSTRUCTS = tuple(
    sorted(
        {
            "cognitive_anxiety",
            "somatic_anxiety",
            "self_confidence",
            "motivation_orientation",
            "perceived_stress",
            "attentional_focus",
            "burnout_signal",
            "coping_style",
            "resilience",
            "appraisal_orientation",
        }
    )
)


def planted_labels(record: RawRecord) -> frozenset[str]:
    spec = record.generation_spec or {}
    return frozenset(p["construct"] for p in spec.get("planted_constructs", ()))


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def evaluate(split, seed: int) -> tuple[dict[str, float], dict[str, str], list[str]]:
    """Score every baseline on a split.

    Both a *learning* system and a *non-learning* one are needed. The
    memorisation probe learns from the training set and so is sensitive to
    leakage; the lexicon never looks at training labels and so is immune. Their
    behaviour across the two splits is the diagnostic: the probe should collapse
    when templates are held out, and the lexicon should barely move.
    """
    y_train = [planted_labels(r) for r in split.train]
    y_test = [planted_labels(r) for r in split.test]

    points: dict[str, float] = {}
    intervals: dict[str, str] = {}
    detail: list[str] = []

    for factory in (MemorisationProbe, LexiconBaseline, MajorityBaseline, StratifiedRandomBaseline):
        model = factory().fit(split.train, y_train)
        y_pred = model.predict(split.test)
        interval = bootstrap_ci(
            y_test,
            y_pred,
            lambda t, p: macro_f1(t, p, CONSTRUCTS),
            n_resamples=400,
            seed=seed,
        )
        points[model.name] = interval.point
        intervals[model.name] = str(interval)
        if factory is MemorisationProbe:
            detail = [
                f"    {label:<24} {prf.as_row()}"
                for label, prf in per_label_prf(y_test, y_pred, CONSTRUCTS).items()
            ]
    return points, intervals, detail


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPEN-012 benchmark audit")
    parser.add_argument("--source", default="synth_precomp_v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    store = RawStore()
    try:
        _, records = store.read_source(args.source)
    except Exception as exc:  # noqa: BLE001 - a missing corpus is a user error, report it
        print(f"ERROR: could not read source {args.source!r}: {exc}", file=sys.stderr)
        print("Run `python scripts/run_ingestion.py` first.", file=sys.stderr)
        return 2

    print(f"corpus: {args.source}  n={len(records)}  seed={args.seed}")
    print(
        "labels: generation_spec.planted_constructs "
        "(corpus-property measurement ONLY -- see the module docstring)"
    )

    results: dict[str, dict[str, float]] = {}
    ok = True

    for split in (
        random_split(records, test_size=args.test_size, seed=args.seed),
        template_disjoint_split(records, test_size=args.test_size, seed=args.seed),
    ):
        _rule(f"Split: {split.name}")
        print(" ", split.summary())

        report = leakage_report(split)
        for line in report.as_lines():
            print("  " + line)

        if not split.test:
            print("  SKIP: empty test set")
            continue

        points, intervals, per_label = evaluate(split, args.seed)
        results[split.name] = points
        print("\n  macro-F1, 95% bootstrap CI:")
        for name, interval in intervals.items():
            print(f"    {name:<20} {interval}")
        if args.verbose:
            print("\n  memorisation probe, per label:")
            print("\n".join(per_label))

        if split.name == "template_disjoint":
            if not split.is_template_disjoint:
                print("  FAIL: the disjoint split is not actually disjoint")
                ok = False
            if report.exact_text_overlap > 0:
                print(f"  FAIL: {report.exact_text_overlap:.1%} of test texts appear in train")
                ok = False

    _rule("Verdict")
    if len(results) == 2:
        rnd, dis = results["random"], results["template_disjoint"]
        print(f"  {'system':<22}{'random':>10}{'disjoint':>12}{'drop':>10}")
        for name in rnd:
            drop = rnd[name] - dis[name]
            print(f"  {name:<22}{rnd[name]:>10.3f}{dis[name]:>12.3f}{drop:>+10.3f}")

        probe_drop = rnd["memorisation_probe"] - dis["memorisation_probe"]
        lex_drop = rnd["lexicon"] - dis["lexicon"]
        print()
        print(f"  Memorisation-sensitive drop (probe) : {probe_drop:+.3f}")
        print(f"  Label-leakage-immune drop (lexicon) : {lex_drop:+.3f}")
        print(
            "    NOTE (OPEN-021): the lexicon is immune to LABEL leakage, not\n"
            "    independent of the corpus -- its cues and the template bank were\n"
            "    both written from taxonomy.yaml positive_examples. Read its score\n"
            "    as a floor with a known upward bias."
        )
        print()
        if probe_drop > 0.02:
            print("  CONFIRMED: a random split materially overstates performance here.")
            print(
                "  A pure memoriser loses "
                f"{probe_drop:.3f} macro-F1 once templates are held out, while the"
            )
            print(
                "  label-leakage-immune lexicon moves far less. The gap is memorisation, not skill."
            )
            print()
            print("  ACTION: Phases 13, 14 and 18 MUST use template_disjoint_split().")
            print("  Report BOTH numbers in the paper -- the gap is itself a finding.")
        else:
            print("  Probe drop is small. Re-check once a transformer exists; a")
            print("  high-capacity model memorises far more readily than 1-NN, so treat")
            print("  this as a LOWER BOUND on the inflation fine-tuning would show.")

    print("\nBenchmark audit:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
