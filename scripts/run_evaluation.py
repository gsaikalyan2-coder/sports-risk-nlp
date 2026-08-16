#!/usr/bin/env python
"""Phase 18 gate -- the evaluation harness, the ablations, and the paper's numbers.

    # step 1, needs the ML stack, run once (~5-15 min CPU)
    python scripts/run_evaluation.py --cache-predictions

    # step 2, pure Python, seconds, rerun as often as you like
    python scripts/run_evaluation.py

    python scripts/run_evaluation.py --no-silver    # skip the classical +/- silver arm
    python scripts/run_evaluation.py --resamples 200 --seed 42

Writes `reports/results.md`, `reports/results.json`, and the Phase 18 figures
under `reports/figures/`.

WHY TWO STEPS
-------------
Predicting is expensive and needs torch; scoring is arithmetic. Splitting them
means the ablations rerun in seconds instead of hours, the test suite needs no ML
stack, and two runs of the same number cannot differ because the model was
reloaded in between. See `src/evaluation/harness.py`'s module docstring.

Step 2 refuses to invent its inputs. If the cache is missing it exits 2 with the
command to produce it, rather than falling back to a subset of systems and
emitting a results table that silently has no transformer row in it.

WHAT THESE NUMBERS ARE
----------------------
`data/gold/` is empty (OPEN-025). Nothing here is an accuracy. Every score is
agreement with `generation_spec.planted_constructs` on synthetic text
(`synth_precomp_v1`, OPEN-011), so it measures how learnable this project's own
template grammar is. The stamp is enforced by `harness.assert_not_accuracy`
rather than trusted to the report author.

Exit 0 pass, 1 gate failure, 2 config error.
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

from src.evaluation.ablations import (  # noqa: E402
    Ablation,
    AblationStatus,
    ClaimLedger,
    fusion_ablation,
    refuse_transformer_silver_ablation,
    risk_sensitivity,
)
from src.evaluation.baselines import LexiconBaseline, MajorityBaseline  # noqa: E402
from src.evaluation.figures import bar_chart, grouped_bar_chart, write  # noqa: E402
from src.evaluation.harness import (  # noqa: E402
    PROVISIONAL_STAMP,
    PredictionSet,
    assert_not_accuracy,
    compare_systems,
    error_profile,
    load_cache,
    score_predictions,
)
from src.evaluation.splits import (  # noqa: E402
    random_split,
    template_disjoint_split,
    templates_of,
)
from src.models.dataset import CONSTRUCTS, load_planted  # noqa: E402

REPORTS_DIR = REPO_ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
CACHE_DIR = REPORTS_DIR / "predictions"

#: The checkpoint Phase 14 selected. Named rather than globbed: globbing the
#: models directory would silently pick a different configuration if the sweep is
#: ever re-run, and the results table would change with no visible cause.
DEFAULT_CHECKPOINT = "phase14_transformer_distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf"


def _display(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise (--out-dir may sit outside)."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _rho(value: float | None) -> str:
    """Rank correlations at 3 dp. `None` means undefined, not zero, and says so."""
    return "undefined" if value is None else f"{value:.3f}"


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * max(12, len(title))}")


# ---------------------------------------------------------------------------
# Step 1 -- cache predictions (the only part that needs torch)
# ---------------------------------------------------------------------------


def cache_predictions(args: argparse.Namespace) -> int:
    """Run every system once per split and write `reports/predictions/`."""
    from src.models.classical import LogisticRegressionBaseline
    from src.models.transformer import MLDependencyMissing, TransformerBaseline

    dataset = load_planted()
    by_id = {r.record_id: label for r, label in zip(dataset.records, dataset.labels, strict=True)}
    checkpoint = REPO_ROOT / "models" / args.checkpoint
    if not checkpoint.exists():
        print(f"FAIL: checkpoint not found: {checkpoint}")
        print("      Phase 14 must have been run, and --checkpoint must name its best run.")
        return 2

    try:
        transformer = TransformerBaseline.load(checkpoint)
    except MLDependencyMissing as exc:
        print(f"FAIL: the ML stack is not installed ({exc}).")
        print(
            "      pip install -r requirements-ml.txt "
            "--extra-index-url https://download.pytorch.org/whl/cpu"
        )
        return 2

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for split in (
        template_disjoint_split(dataset.records, test_size=args.test_size, seed=args.seed),
        random_split(dataset.records, test_size=args.test_size, seed=args.seed),
    ):
        _rule(f"Caching predictions: {split.name}")
        print(" ", split.summary())
        test = split.test
        record_ids = tuple(r.record_id for r in test)
        y_true = tuple(by_id[r.record_id] for r in test)
        train_labels = [by_id[r.record_id] for r in split.train]

        # The transformer is NOT refitted here -- `load` restores it with its
        # tuned thresholds. Refitting would silently change the model the paper
        # reports (handover C2: "do not retrain").
        probs = transformer.predict_proba(test)
        preds = transformer.predict(test)
        systems: list[PredictionSet] = [
            PredictionSet(
                system="transformer",
                split=split.name,
                label_source=dataset.label_source,
                constructs=tuple(transformer.constructs),
                record_ids=record_ids,
                y_true=y_true,
                y_pred=tuple(preds),
                y_prob=tuple(tuple(float(v) for v in row) for row in probs),
                thresholds=transformer.manifest()["thresholds"],
            )
        ]

        for name, model in (
            ("lexicon", LexiconBaseline()),
            ("majority", MajorityBaseline()),
            ("tfidf_logreg", LogisticRegressionBaseline()),
        ):
            model.fit(split.train, train_labels)
            systems.append(
                PredictionSet(
                    system=name,
                    split=split.name,
                    label_source=dataset.label_source,
                    constructs=CONSTRUCTS,
                    record_ids=record_ids,
                    y_true=y_true,
                    y_pred=tuple(model.predict(test)),
                )
            )

        for ps in systems:
            path = ps.save(CACHE_DIR)
            written.append(path)
            print(f"  wrote {path.relative_to(REPO_ROOT)}  (n={len(ps)})")

    _rule("Done")
    print(f"  {len(written)} prediction sets cached under {CACHE_DIR.relative_to(REPO_ROOT)}")
    print("  Now run:  python scripts/run_evaluation.py")
    return 0


# ---------------------------------------------------------------------------
# Step 2 -- the classical +/- silver ablation (cheap, no torch)
# ---------------------------------------------------------------------------


def silver_ablation(args: argparse.Namespace) -> Ablation:
    """Train the classical model with and without silver, and score both.

    Runs on the classical side because it is seconds rather than ten CPU-hours,
    and because the point is to *demonstrate* OPEN-028 rather than to tune
    anything. The transformer arm is refused in writing; see
    `refuse_transformer_silver_ablation`.
    """
    from src.models.classical import LogisticRegressionBaseline
    from src.models.dataset import load_silver

    dataset = load_planted()
    by_id = {r.record_id: label for r, label in zip(dataset.records, dataset.labels, strict=True)}
    split = template_disjoint_split(dataset.records, test_size=args.test_size, seed=args.seed)
    test, record_ids = split.test, tuple(r.record_id for r in split.test)
    y_true = tuple(by_id[r.record_id] for r in test)

    train_records = list(split.train)
    train_labels = [by_id[r.record_id] for r in split.train]

    try:
        # The keyword is the point: this label source has no signal and the
        # loader refuses to hand it over to a caller who has not said so.
        silver = load_silver(acknowledge_no_signal=True)
    except Exception as exc:  # noqa: BLE001 -- reported, not swallowed
        return Ablation(
            id="silver_classical",
            question="Does adding silver-labelled data help a classical model?",
            status=AblationStatus.UNMEASURABLE,
            rationale=f"`load_silver` failed: {exc}",
        )

    # Silver is utterance-level and the split is record-level, so a silver row
    # cannot be excluded by record id -- `load_silver` keys rows on the utterance
    # id and does not carry the parent id forward. It does carry the parent's
    # `generation_spec`, explicitly so that `templates_of` works, so the guard is
    # by *template*: any silver row realising a held-out template is dropped.
    #
    # That is the stronger guard anyway. Excluding by id would still let a silver
    # utterance from a training record that shares a template with the test side
    # into training, and on a template-disjoint split that is exactly the leak the
    # split exists to prevent. A leak here would surface as silver "helping".
    test_templates = split.test_templates
    added_records, added_labels = [], []
    for record, label in zip(silver.records, silver.labels, strict=True):
        if templates_of(record) & test_templates:
            continue
        added_records.append(record)
        added_labels.append(label)

    sets: dict[str, PredictionSet] = {}
    for name, records, labels in (
        ("without_silver", train_records, train_labels),
        ("with_silver", train_records + added_records, train_labels + added_labels),
    ):
        model = LogisticRegressionBaseline()
        model.fit(records, labels)
        sets[name] = PredictionSet(
            system=name,
            split=split.name,
            label_source=dataset.label_source,
            constructs=CONSTRUCTS,
            record_ids=record_ids,
            y_true=y_true,
            y_pred=tuple(model.predict(test)),
        )

    comparison = compare_systems(
        sets["with_silver"],
        sets["without_silver"],
        n_resamples=args.resamples,
        seed=args.seed,
    )
    if comparison.significant:
        direction = (
            "a significant IMPROVEMENT, which would need explaining"
            if comparison.delta > 0
            else "a significant DEGRADATION"
        )
    else:
        direction = "no significant change in either direction"
    return Ablation(
        id="silver_classical",
        question="Does adding silver-labelled data help a classical model?",
        status=AblationStatus.MEASURED,
        rationale=(
            f"{len(added_records)} silver rows added to training only; any row realising a "
            f"held-out template was dropped, so the template-disjoint split is preserved. "
            f"macro-F1 {comparison.score_b:.3f} -> {comparison.score_a:.3f} "
            f"(delta {comparison.delta:+.3f}, p={comparison.p_value:.3f}): {direction}. "
            "That is the measured evidence for OPEN-028: several thousand additional "
            "training rows bought nothing, because their labels are `rng.randrange` "
            "output keyed on a prompt hash."
        ),
        comparison=comparison,
        detail={"n_silver_rows_added": len(added_records), "blocked_by": ["OPEN-028"]},
    )


# ---------------------------------------------------------------------------
# Step 2 -- reporting
# ---------------------------------------------------------------------------


def build_figures(scores: dict[str, Any], payload: dict[str, Any]) -> list[Path]:
    """Paper figures. SVG, hand-written, no matplotlib (see `figures.py`)."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    disjoint = [v for v in scores.values() if v["split"] == "template_disjoint"]
    if disjoint:
        written.append(
            write(
                FIGURES_DIR / "phase18_macro_f1_by_system.svg",
                bar_chart(
                    [v["system"] for v in disjoint],
                    [v["macro_f1"]["point"] for v in disjoint],
                    "macro-F1, template-disjoint (planted labels, NOT accuracy)",
                    value_format="{:.3f}",
                ),
            )
        )

    transformer = scores.get("template_disjoint::transformer")
    if transformer:
        per = transformer["per_construct"]
        written.append(
            write(
                FIGURES_DIR / "phase18_per_construct_f1.svg",
                bar_chart(
                    list(per),
                    [v["f1"] for v in per.values()],
                    "Transformer per-construct F1 (planted labels, NOT accuracy)",
                    value_format="{:.3f}",
                ),
            )
        )

    paired = [v["system"] for v in disjoint if f"random::{v['system']}" in scores]
    if paired:
        written.append(
            write(
                FIGURES_DIR / "phase18_memorisation_gap.svg",
                grouped_bar_chart(
                    paired,
                    [
                        (
                            "template-disjoint",
                            [
                                scores[f"template_disjoint::{s}"]["macro_f1"]["point"]
                                for s in paired
                            ],
                        ),
                        (
                            "random (leaky)",
                            [scores[f"random::{s}"]["macro_f1"]["point"] for s in paired],
                        ),
                    ],
                    "Memorisation gap: random split vs template-disjoint",
                ),
            )
        )

    share = (
        payload.get("ablations", {})
        .get("risk_fusion", {})
        .get("detail", {})
        .get("contribution_share")
    )
    if share:
        written.append(
            write(
                FIGURES_DIR / "phase18_risk_contribution_share.svg",
                bar_chart(
                    list(share),
                    list(share.values()),
                    "Share of absolute movement in the risk index",
                    value_format="{:.3f}",
                ),
            )
        )
    return written


def write_reports(payload: dict[str, Any], figures: list[Path]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "results.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")

    scores = payload["scores"]
    lines: list[str] = [
        "# Phase 18 -- Evaluation harness, ablations, and results",
        "",
        "> **No number in this file is an accuracy.** `data/gold/` is empty (OPEN-025),",
        "> so every score is agreement with `generation_spec.planted_constructs` --",
        "> labels this project's generator planted in synthetic text (OPEN-011). What is",
        "> measured is how learnable the template grammar `synth_precomp_v1` is. Nothing",
        "> here describes any real person, and nothing here is evidence that the model",
        "> detects psychological constructs in athlete language.",
        "",
        f"- Generated: {payload['generated_on']}",
        f"- Python {payload['environment']['python']}, seed {payload['environment']['seed']},"
        f" {payload['environment']['bootstrap_resamples']} bootstrap resamples",
        f"- Checkpoint: `{payload['environment']['checkpoint']}`",
        "",
        "## Gate",
        "",
        'The Phase 18 gate is *"every claim the paper will make is backed by a logged',
        'experiment"*. That is only checkable if the claims are enumerated somewhere a',
        "program can read, so they are: `src/evaluation/ablations.py::CLAIMS`. Each row",
        "below names a claim and the key in `results.json` that backs it.",
        "",
        "| claim | evidence key | backed |",
        "|---|---|---|",
    ]
    for claim_id, backed in payload["claim_audit"].items():
        key = next(c.evidence_key for c in ClaimLedger().claims if c.id == claim_id)
        lines.append(f"| `{claim_id}` | `{key}` | {'yes' if backed else '**NO**'} |")

    lines += [
        "",
        "## 1. Results by system",
        "",
        "macro-F1 with a 95% bootstrap interval. **A point estimate without an interval",
        "is not a result** -- at this test-set size the interval is wide enough that",
        "several of these systems do not separate.",
        "",
        "| split | system | n | macro-F1 [95% CI] | micro-F1 | subset acc. | constructs at F1=0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry in scores.values():
        m, mi = entry["macro_f1"], entry["micro_f1"]
        zeros = entry["constructs_at_zero"]
        lines.append(
            f"| {entry['split']} | {entry['system']} | {entry['n']} | "
            f"{m['point']:.3f} [{m['low']:.3f}, {m['high']:.3f}] | {mi['point']:.3f} | "
            f"{entry['subset_accuracy']:.3f} | {len(zeros)}"
            + (f" ({', '.join(zeros)})" if zeros else "")
            + " |"
        )

    transformer = scores.get("template_disjoint::transformer")
    if transformer:
        lines += [
            "",
            "### Per-construct, transformer, template-disjoint split",
            "",
            "The spread is the interesting part. A single macro-F1 averages over a model",
            "that is competent on some constructs and blind on others, and the ten rows",
            "below are what a reviewer will actually ask for.",
            "",
            "| construct | P | R | F1 | support |",
            "|---|---|---|---|---|",
        ]
        for name, prf in transformer["per_construct"].items():
            lines.append(
                f"| {name} | {prf['precision']:.3f} | {prf['recall']:.3f} | "
                f"{prf['f1']:.3f} | {prf['support']} |"
            )

    lines += [
        "",
        "## 2. Comparisons",
        "",
        "| comparison | delta | p | verdict |",
        "|---|---|---|---|",
    ]
    for name, comp in payload["comparisons"].items():
        lines.append(
            f"| {name} ({comp['system_a']} vs {comp['system_b']}) | {comp['delta']:+.3f} | "
            f"{comp['p_value']:.3f} | {comp['verdict']} |"
        )

    lines += ["", "## 3. Ablations", ""]
    for ablation in payload["ablations"].values():
        lines += [
            f"### {ablation['id']} -- {ablation['status'].upper()}",
            "",
            f"*{ablation['question']}*",
            "",
            ablation["rationale"],
            "",
        ]

    fusion = payload["ablations"].get("risk_fusion", {}).get("detail", {})
    if fusion:
        lines += [
            "#### Risk-layer sensitivity, in numbers",
            "",
            f"- Records scored: **{fusion['n']}**",
            f"- Constructs that never moved the index: **{len(fusion['zeroed_constructs'])}** of 10"
            + (
                f" ({', '.join(fusion['zeroed_constructs'])}) -- these are polarity-bearing "
                "constructs left inert by the conservative `PolarityPolicy.NEUTRAL` default. "
                "The risk decomposition is therefore narrower than the taxonomy suggests."
                if fusion["zeroed_constructs"]
                else ""
            ),
            f"- Rank correlation with a plain count of detected constructs: "
            f"**{_rho(fusion['naive_rho_vs_construct_count'])}**",
            f"- Rank correlation under +/-{fusion['perturbation_epsilon']} probability noise: "
            f"**{_rho(fusion['perturbation_rho'])}**",
            "- Rank correlation with the NEUTRAL polarity default: "
            + ", ".join(f"{k} {_rho(v)}" for k, v in fusion["polarity_rho"].items()),
            "- Mean index shift under an alternative polarity policy: "
            + ", ".join(f"{k} {v:.3f}" for k, v in fusion["polarity_mean_shift"].items()),
            "",
        ]

    errors = payload.get("error_profile")
    if errors:
        lines += [
            "## 4. Error analysis",
            "",
            "**Structural only, with no example sentences.** `docs/ethics.md` binds this",
            "project to publish no verbatim corpus text, so errors are characterised by",
            "construct, by confusion pair and by how many constructs a record carries --",
            "not by quoting records. That is a real cost to persuasiveness, paid on",
            "purpose.",
            "",
            "| construct | false positives | false negatives |",
            "|---|---|---|",
        ]
        for construct in sorted(set(errors["false_positives"]) | set(errors["false_negatives"])):
            lines.append(
                f"| {construct} | {errors['false_positives'].get(construct, 0)} | "
                f"{errors['false_negatives'].get(construct, 0)} |"
            )
        top = list(errors["confusions"].items())[:8]
        if top:
            lines += [
                "",
                "Most frequent construct swaps (missed X, invented Y on the same record):",
                "",
            ]
            lines += [f"- `{pair}` x{n}" for pair, n in top]
        lines += ["", "Error rate by how many constructs a record carries:", ""]
        lines += [
            f"- {band}: {v['n_with_error']}/{v['n']} records have at least one error"
            for band, v in errors["by_load_band"].items()
        ]

    lines += [
        "",
        "## 5. Figures",
        "",
    ]
    lines += [f"- `{_display(p)}`" for p in figures]
    lines += [
        "",
        "## 6. What this phase does not establish",
        "",
        "- **Not accuracy.** No human has verified a single label in this evaluation set.",
        "- **Not generalisation to athlete language.** No athlete wrote any of this text.",
        "- **Not a validated risk index.** No observed risk outcome exists, so the fusion",
        "  layer is characterised structurally and never scored for correctness.",
        "- **Not a weak-supervision result.** The silver ablation measures the effect of",
        "  adding PRNG output, because that is what the silver set currently is (OPEN-028).",
        "",
        f"**{PROVISIONAL_STAMP}**",
        "",
    ]
    (REPORTS_DIR / "results.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------


def main() -> int:
    global REPORTS_DIR, FIGURES_DIR  # noqa: PLW0603 -- CLI redirection, set once below

    parser = argparse.ArgumentParser(description="Phase 18 evaluation harness and ablations")
    parser.add_argument("--cache-predictions", action="store_true", help="step 1; needs torch")
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--resamples", type=int, default=1000)
    parser.add_argument(
        "--no-silver", action="store_true", help="skip the classical +/- silver arm"
    )
    # Redirect inputs/outputs. Present so the runner can be exercised end to end
    # against a scratch cache without overwriting `reports/`, which is what a
    # smoke run on a machine that cannot load the real checkpoint needs to do.
    # Defaults are the real paths; nothing changes for a normal run.
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--out-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    if args.cache_predictions:
        return cache_predictions(args)

    REPORTS_DIR = args.out_dir
    FIGURES_DIR = args.out_dir / "figures"

    _rule("Phase 18 -- evaluation")
    cache = load_cache(args.cache_dir)
    if not cache:
        print(f"FAIL: no cached predictions under {args.cache_dir}.")
        print("      Run:  python scripts/run_evaluation.py --cache-predictions")
        print("      (needs the ML stack; ~5-15 min CPU. This script will not")
        print("       silently score a subset of the systems instead.)")
        return 2

    assert_not_accuracy(list(cache.values()))

    scores: dict[str, Any] = {}
    for (split, system), ps in sorted(cache.items()):
        entry = score_predictions(ps, n_resamples=args.resamples, seed=args.seed)
        scores[f"{split}::{system}"] = entry.as_dict()
        print(f"  {split:<18} {system:<14} macro-F1 {entry.macro_f1}")

    comparisons: dict[str, Any] = {}
    disjoint_t = cache.get(("template_disjoint", "transformer"))
    disjoint_l = cache.get(("template_disjoint", "lexicon"))
    if disjoint_t and disjoint_l:
        comparisons["transformer_vs_lexicon"] = compare_systems(
            disjoint_t, disjoint_l, n_resamples=args.resamples, seed=args.seed
        ).as_dict()
    if disjoint_t and ("random", "transformer") in cache:
        # Not a paired test -- different test sets by construction. Recorded as a
        # gap between two scores, which is what the memorisation claim needs.
        rand = scores["random::transformer"]["macro_f1"]["point"]
        dis = scores["template_disjoint::transformer"]["macro_f1"]["point"]
        comparisons["split_gap"] = {
            "system_a": "transformer (random split)",
            "system_b": "transformer (template-disjoint)",
            "split": "cross-split",
            "metric": "macro_f1",
            "score_a": rand,
            "score_b": dis,
            "delta": rand - dis,
            "p_value": float("nan"),
            "verdict": "memorisation gap (not a paired test -- different test sets)",
        }

    _rule("Ablations")
    ablations: dict[str, Any] = {}
    if not args.no_silver:
        silver = silver_ablation(args)
        ablations[silver.id] = silver.as_dict()
        print(f"  silver_classical: {silver.status.value}")
    refused = refuse_transformer_silver_ablation()
    ablations[refused.id] = refused.as_dict()
    print(f"  silver_transformer: {refused.status.value} (by design)")

    if disjoint_t and disjoint_t.y_prob is not None:
        rows = [disjoint_t.probabilities_for(i) for i in range(len(disjoint_t))]
        fusion = fusion_ablation(risk_sensitivity(rows, seed=args.seed))
        ablations[fusion.id] = fusion.as_dict()
        print(f"  risk_fusion: {fusion.status.value}")

    errors = error_profile(disjoint_t).as_dict() if disjoint_t else None

    # An input, not an output: always read from the real reports tree even when
    # --out-dir redirects where this run writes.
    explain_path = REPO_ROOT / "reports" / "explain" / "faithfulness.json"
    explainability: dict[str, Any] = {}
    if explain_path.exists():
        explainability["faithfulness"] = json.loads(explain_path.read_text(encoding="utf-8"))[
            "overall"
        ]

    payload: dict[str, Any] = {
        "phase": 18,
        "generated_on": date.today().isoformat(),
        "environment": {
            "python": platform.python_version(),
            "seed": args.seed,
            "test_size": args.test_size,
            "bootstrap_resamples": args.resamples,
            "checkpoint": args.checkpoint,
        },
        "provenance": PROVISIONAL_STAMP,
        "is_accuracy": False,
        "scores": scores,
        "comparisons": comparisons,
        "ablations": ablations,
        "error_profile": errors,
        "explainability": explainability,
    }

    ledger = ClaimLedger()
    payload["claim_audit"] = ledger.audit(payload)
    unbacked = ledger.unbacked(payload)

    figures = build_figures(scores, payload)
    write_reports(payload, figures)

    _rule("Gate")
    for claim in ledger.claims:
        mark = "ok " if payload["claim_audit"][claim.id] else "NO "
        print(f"  [{mark}] {claim.id}")
    if unbacked:
        print("\n  FAIL: the following claims are not supported by a logged experiment")
        print("        (the evidence is missing, empty, or says something else):")
        for claim in unbacked:
            print(f"    - {claim.id}: {claim.text}")
        print(
            "\n  Three honest ways out: run the missing experiment, reword the claim to "
            "match\n  what was measured, or delete it from CLAIMS. Loosening the predicate "
            "is not\n  one of them."
        )
    print(
        f"\n  Reports: {_display(REPORTS_DIR / 'results.md')}, "
        f"{_display(REPORTS_DIR / 'results.json')}"
    )
    print(f"  STATUS: {PROVISIONAL_STAMP}")
    print("\nPhase 18 gate:", "PASSED" if not unbacked else "FAILED")
    return 0 if not unbacked else 1


if __name__ == "__main__":
    raise SystemExit(main())
