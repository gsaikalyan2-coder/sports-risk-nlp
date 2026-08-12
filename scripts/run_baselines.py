#!/usr/bin/env python
"""Phase 13 gate -- establish the bar the Phase 14 transformer must beat.

    python scripts/run_baselines.py
    python scripts/run_baselines.py --seed 42 --test-size 0.2
    python scripts/run_baselines.py --silver     # ablation: demonstrates OPEN-028
    python scripts/run_baselines.py --gold       # refuses; data/gold/ is empty

Trains six systems -- majority, stratified-random, lexicon, memorisation probe,
TF-IDF+LogReg and TF-IDF+LinearSVC -- on a template-disjoint split, scores them
with bootstrap confidence intervals, and writes `reports/baselines.md` and
`reports/baselines.json`.

WHAT THESE NUMBERS ARE, PRECISELY
---------------------------------
`data/gold/` is empty (OPEN-025: no second annotator), so there is no
human-verified evaluation set and **this script cannot produce an accuracy**.
What it produces is a **corpus-property measurement** against
`generation_spec.planted_constructs`, under exactly the framing
`scripts/run_benchmark_audit.py` established: it answers "how learnable is this
template grammar, and how much of that learnability is memorisation", not "how
well does a model detect psychological constructs in athlete text".

Every number is stamped `PROVISIONAL -- planted-label measurement` in the report
text and in the JSON. The stamp is not decoration. A provisional number that does
not announce itself becomes a cited number, and this project has eight weeks
between here and a paper that a reviewer will read.

The word "accuracy" does not appear next to any figure this script emits.

WHY NOT SILVER
--------------
The obvious alternative reference is `data/processed/silver/`. It is worse than
provisional, it is empty of signal: no live OpenRouter call has ever been made
(OPEN-008), so all 9,302 silver labels are PRNG output keyed on the prompt hash
(OPEN-028). `--silver` runs the same harness over it anyway, because
demonstrating the collapse is better evidence than asserting it.

Offline, free, deterministic. Exit 0 pass, 1 gate failure, 2 config error.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import date
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import sklearn  # noqa: E402

from src.evaluation import (  # noqa: E402
    LexiconBaseline,
    MajorityBaseline,
    MemorisationProbe,
    StratifiedRandomBaseline,
    bootstrap_ci,
    leakage_report,
    macro_f1,
    micro_f1,
    per_label_prf,
    random_split,
    subset_accuracy,
    template_disjoint_split,
)
from src.models.classical import LinearSVCBaseline, LogisticRegressionBaseline  # noqa: E402
from src.models.dataset import (  # noqa: E402
    CONSTRUCTS,
    Dataset,
    NoEvaluableLabels,
    load_gold,
    load_planted,
    load_silver,
)

REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR = REPO_ROOT / "models"

#: Stamped onto every emitted figure. Changing this string is a decision about
#: what the project claims, so it lives in one place.
PROVISIONAL_STAMP = "PROVISIONAL -- planted-label measurement, NOT model accuracy"

SILVER_STAMP = "INVALID -- silver labels are PRNG output (OPEN-028). Ablation only."

#: Order of the results table: trivial floors, then the leakage instrument, then
#: the real baselines. Reading top to bottom should tell the story.
SYSTEMS = (
    MajorityBaseline,
    StratifiedRandomBaseline,
    MemorisationProbe,
    LexiconBaseline,
    LogisticRegressionBaseline,
    LinearSVCBaseline,
)


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def _labels_for(split_side: tuple, index: dict[str, frozenset[str]]) -> list[frozenset[str]]:
    """Look labels up by record ID rather than by position.

    The splits shuffle, so a positional zip against the original label list
    would silently pair each record with someone else's labels and produce a
    plausible macro-F1 computed against noise. Looking up by ID makes that
    class of bug impossible rather than unlikely.
    """
    return [index[record.record_id] for record in split_side]


def evaluate_split(
    split: Any,
    dataset: Dataset,
    *,
    seed: int,
    n_resamples: int,
    save_models: bool,
) -> dict[str, Any]:
    """Fit and score every system on one split."""
    index = {r.record_id: ls for r, ls in zip(dataset.records, dataset.labels, strict=True)}
    y_train = _labels_for(split.train, index)
    y_test = _labels_for(split.test, index)

    report = leakage_report(split)
    out: dict[str, Any] = {
        "split": split.name,
        "n_train": len(split.train),
        "n_test": len(split.test),
        "n_discarded": len(split.discarded),
        "shared_templates": len(split.shared_templates),
        "is_template_disjoint": split.is_template_disjoint,
        "leakage": {
            "exact_text_overlap": report.exact_text_overlap,
            "ngram_overlap": {str(k): v for k, v in report.ngram_overlap.items()},
        },
        "systems": {},
    }

    for factory in SYSTEMS:
        # Only some baselines take a seed -- `MajorityBaseline` and
        # `LexiconBaseline` are deterministic and have no such field. Branching
        # on the dataclass fields rather than on a hand-maintained list of class
        # names means adding a baseline cannot silently drop its seed.
        seeded = "seed" in getattr(factory, "__dataclass_fields__", {})
        model = factory(seed=seed) if seeded else factory()
        model.fit(split.train, y_train)
        y_pred = model.predict(split.test)

        macro = bootstrap_ci(
            y_test,
            y_pred,
            lambda t, p: macro_f1(t, p, CONSTRUCTS),
            n_resamples=n_resamples,
            seed=seed,
        )
        micro = bootstrap_ci(
            y_test,
            y_pred,
            lambda t, p: micro_f1(t, p, CONSTRUCTS),
            n_resamples=n_resamples,
            seed=seed,
        )
        per_label = per_label_prf(y_test, y_pred, CONSTRUCTS)

        entry: dict[str, Any] = {
            "macro_f1": {"point": macro.point, "low": macro.low, "high": macro.high},
            "micro_f1": {"point": micro.point, "low": micro.low, "high": micro.high},
            "subset_accuracy": subset_accuracy(y_test, y_pred),
            "per_construct": {
                label: {
                    "precision": prf.precision,
                    "recall": prf.recall,
                    "f1": prf.f1,
                    "support": prf.support,
                }
                for label, prf in per_label.items()
            },
            "status": PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP,
        }
        if hasattr(model, "manifest"):
            entry["manifest"] = model.manifest()
            if save_models and split.name == "template_disjoint":
                target = MODELS_DIR / f"phase13_{model.name}_{split.name}"
                model.save(target)
                entry["saved_to"] = str(target.relative_to(REPO_ROOT))

        out["systems"][model.name] = entry

    return out


def _table(results: dict[str, Any]) -> list[str]:
    """Headline table: macro-F1 with CI under each split, plus the gap."""
    disjoint = results["template_disjoint"]["systems"]
    rnd = results["random"]["systems"]
    lines = [
        f"| {'system':<22} | {'disjoint macro-F1 [95% CI]':<28} "
        f"| {'random macro-F1':<16} | {'gap':>7} |",
        f"|{'-' * 24}|{'-' * 30}|{'-' * 18}|{'-' * 9}|",
    ]
    for name in disjoint:
        d = disjoint[name]["macro_f1"]
        r = rnd[name]["macro_f1"]
        ci = f"{d['point']:.3f} [{d['low']:.3f}, {d['high']:.3f}]"
        lines.append(
            f"| {name:<22} | {ci:<28} | {r['point']:<16.3f} | {r['point'] - d['point']:>+7.3f} |"
        )
    return lines


def write_reports(results: dict[str, Any], dataset: Dataset, args: Any) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP

    payload = {
        "phase": 13,
        "generated_on": date.today().isoformat(),
        "status": stamp,
        "label_source": dataset.label_source,
        "unit": dataset.unit,
        "is_accuracy": False,
        "what_this_measures": (
            "Learnability of the synth_precomp_v1 template grammar against the "
            "constructs the generator planted, and how much of it is memorisation. "
            "NOT detection of psychological constructs in athlete text. No "
            "human-verified evaluation set exists (OPEN-025)."
        ),
        "environment": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "seed": args.seed,
            "test_size": args.test_size,
            "bootstrap_resamples": args.resamples,
        },
        "dataset": {
            "name": dataset.name,
            "n": len(dataset),
            "n_before_dedup": dataset.n_before_dedup,
            "duplicate_texts_collapsed": dataset.n_duplicate_texts_collapsed,
            "ambiguous_texts_dropped": dataset.n_ambiguous_texts_dropped,
            "label_support": dataset.label_support,
            "constructs_without_support": list(dataset.constructs_without_support),
        },
        "splits": results,
    }
    (REPORTS_DIR / "baselines.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    disjoint = results["template_disjoint"]["systems"]
    best = max(disjoint, key=lambda k: disjoint[k]["macro_f1"]["point"])

    md: list[str] = [
        "# Phase 13 -- Baseline results",
        "",
        f"> **{stamp}**",
        "",
        "These figures measure how learnable the `synth_precomp_v1` template grammar",
        "is against `generation_spec.planted_constructs`. They do **not** measure how",
        "well a model detects psychological constructs in athlete text, and none of",
        "them is an accuracy. `data/gold/` is empty (OPEN-025), so no human-verified",
        "evaluation set exists and no accuracy claim is available to this project yet.",
        "",
        "Belongs in the paper's dataset / methodology section. Never the results table.",
        "",
        f"- Generated: {payload['generated_on']}",
        f"- Label source: `{dataset.label_source}` (unit: {dataset.unit})",
        f"- Python {platform.python_version()}, scikit-learn {sklearn.__version__}, "
        f"seed {args.seed}",
        f"- Dataset: {len(dataset)} examples "
        f"(deduplicated from {dataset.n_before_dedup}; "
        f"{dataset.n_duplicate_texts_collapsed} duplicate texts collapsed, "
        f"{dataset.n_ambiguous_texts_dropped} ambiguous dropped)",
        "",
        "## Headline: template-disjoint split",
        "",
        "The template-disjoint split is the honest one. The random split is shown only",
        "as a contrast; the gap between them is the memorisation story and is itself a",
        "paper result (OPEN-012).",
        "",
    ]
    md.extend(_table(results))
    md.extend(
        [
            "",
            f"Best system on the honest split: **{best}** at "
            f"{disjoint[best]['macro_f1']['point']:.3f} macro-F1.",
            "",
            "## Split diagnostics",
            "",
        ]
    )
    for split_name, block in results.items():
        md.extend(
            [
                f"### {split_name}",
                "",
                f"- train / test / discarded: {block['n_train']} / {block['n_test']} "
                f"/ {block['n_discarded']}",
                f"- templates on both sides: {block['shared_templates']}",
                f"- exact test texts seen in train: {block['leakage']['exact_text_overlap']:.1%}",
                "- n-gram overlap: "
                + ", ".join(
                    f"{n}-gram {v:.1%}"
                    for n, v in sorted(block["leakage"]["ngram_overlap"].items())
                ),
                "",
            ]
        )

    md.extend(["## Per-construct F1 (template-disjoint)", ""])
    header = "| construct | " + " | ".join(disjoint) + " | support |"
    md.append(header)
    md.append("|" + "---|" * (len(disjoint) + 2))
    for construct in CONSTRUCTS:
        cells = [f"{disjoint[s]['per_construct'][construct]['f1']:.3f}" for s in disjoint]
        support = next(iter(disjoint.values()))["per_construct"][construct]["support"]
        md.append(f"| {construct} | " + " | ".join(cells) + f" | {support} |")

    md.extend(
        [
            "",
            "## How to make these numbers real",
            "",
            "1. Recruit a second annotator and populate `data/gold/` (OPEN-025).",
            "2. Re-run `python scripts/run_baselines.py --gold`. The harness changes an",
            "   input path and nothing else; the numbers it then prints are accuracies",
            "   and this warning can be deleted.",
            "",
            "Until then `--gold` refuses rather than falling back to silver, because",
            "silver is PRNG output (OPEN-028) and a silent fallback would relabel a",
            "chance-agreement score as accuracy.",
            "",
        ]
    )
    (REPORTS_DIR / "baselines.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 13 baselines")
    parser.add_argument("--source", default="synth_precomp_v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--resamples", type=int, default=400)
    parser.add_argument(
        "--gold",
        action="store_true",
        help="evaluate against data/gold/ (refuses while it is empty)",
    )
    parser.add_argument(
        "--silver",
        action="store_true",
        help="ablation: run against the PRNG silver labels to demonstrate OPEN-028",
    )
    parser.add_argument("--no-save", action="store_true", help="do not persist fitted models")
    args = parser.parse_args(argv)

    if args.gold and args.silver:
        print("ERROR: --gold and --silver are mutually exclusive", file=sys.stderr)
        return 2

    try:
        if args.gold:
            dataset = load_gold(args.source)
        elif args.silver:
            dataset = load_silver(args.source, acknowledge_no_signal=True)
        else:
            dataset = load_planted(args.source)
    except NoEvaluableLabels as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - a missing corpus is a user error, report it
        print(f"ERROR: could not build the dataset: {exc}", file=sys.stderr)
        print("Run `python scripts/run_ingestion.py` first.", file=sys.stderr)
        return 2

    print(f"Phase 13 baselines  seed={args.seed}  sklearn={sklearn.__version__}")
    print(" ", dataset.summary())
    if dataset.has_signal:
        print(f"  STATUS: {PROVISIONAL_STAMP}")
    else:
        _rule("NO SIGNAL")
        print("  These labels are PRNG output keyed on the prompt hash (OPEN-028).")
        print("  Exactly one label per non-abstained utterance; 6 of 10 constructs")
        print("  attested; agreement with the planted set is at chance. Any number")
        print("  below measures the stub's entropy. Ablation only.")

    if dataset.constructs_without_support:
        print(
            f"  WARNING: {len(dataset.constructs_without_support)} construct(s) have zero "
            f"support: {', '.join(dataset.constructs_without_support)}"
        )
        print("  Macro-F1 over 10 constructs is capped below 1.0 by that alone.")

    results: dict[str, Any] = {}
    ok = True

    for split in (
        template_disjoint_split(dataset.records, test_size=args.test_size, seed=args.seed),
        random_split(dataset.records, test_size=args.test_size, seed=args.seed),
    ):
        _rule(f"Split: {split.name}")
        print(" ", split.summary())
        if not split.test:
            print("  FAIL: empty test set")
            return 2

        block = evaluate_split(
            split,
            dataset,
            seed=args.seed,
            n_resamples=args.resamples,
            save_models=not args.no_save and dataset.has_signal,
        )
        results[split.name] = block

        print("\n  macro-F1, 95% bootstrap CI:")
        for name, entry in block["systems"].items():
            m = entry["macro_f1"]
            print(f"    {name:<22} {m['point']:.3f} [{m['low']:.3f}, {m['high']:.3f}]")

        if split.name == "template_disjoint":
            if not split.is_template_disjoint:
                print("  FAIL: the disjoint split is not actually disjoint")
                ok = False
            if block["leakage"]["exact_text_overlap"] > 0:
                print(
                    f"  FAIL: {block['leakage']['exact_text_overlap']:.1%} of test texts "
                    "appear in train"
                )
                ok = False

    write_reports(results, dataset, args)

    _rule("Verdict")
    for line in _table(results):
        print("  " + line)
    print()
    print(
        f"  Reports: {(REPORTS_DIR / 'baselines.md').relative_to(REPO_ROOT)}, "
        f"{(REPORTS_DIR / 'baselines.json').relative_to(REPO_ROOT)}"
    )
    print(f"  STATUS: {PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP}")

    print("\nPhase 13 gate:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
