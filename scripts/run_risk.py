#!/usr/bin/env python
"""Phase 15 gate -- calibrate construct probabilities and fuse them into a risk index.

    python scripts/run_risk.py                    # full run, TF-IDF probability source
    python scripts/run_risk.py --source-model transformer   # once Phase 14 has run
    python scripts/run_risk.py --sensitivity      # weight + polarity-policy ablation
    python scripts/run_risk.py --gold             # refuses; data/gold/ is empty

WHY THIS PHASE DOES NOT WAIT FOR PHASE 14
-----------------------------------------
`PROJECT_PLAN.md` Phase 15's gate is three conditions:

  1. calibration error (ECE) is **reported**;
  2. the risk decomposition is **human-readable**;
  3. the interface **accepts optional context features** without breaking the
     text-only path.

None of the three depends on how well the Phase 14 transformer scores. The risk
layer consumes a probability mapping from *any* source, so it is built and gated
against the Phase 13 TF-IDF logistic model today, and the source is swapped with
`--source-model transformer` when Phase 14 has actually run (OPEN-029). That
decoupling is deliberate: Phase 14 is blocked on a dependency install and a
weights download, and there is no reason for a blocked phase to block an
unblocked one.

WHAT IS AND IS NOT BEING CALIBRATED
-----------------------------------
**Calibrated here:** the per-construct probabilities, against the planted
construct labels. Real, runnable, and inheriting the standard caveat -- the
target is a template generator's intent, so the ECE is a corpus property.

**Not calibrated, and refused rather than faked:** the fused risk index. That
needs an observed risk outcome per record and none exists -- no administered
CSAI-2, no clinician rating, no linked competition outcome.
`src/risk/calibration.py:calibrate_risk_index` raises with the reasoning
attached. The tempting substitute ("risk = 1 if any risk-raising construct was
planted") would calibrate the fusion against a restatement of its own inputs and
produce a good ECE that means nothing.

So the risk index this script emits is a **ranking**, not a probability, and
every artifact it writes says so. `RiskScore.is_calibrated` stays False.

Exit codes: 0 gate passed, 1 gate failed, 2 config error.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation import template_disjoint_split  # noqa: E402
from src.models.dataset import (  # noqa: E402
    CONSTRUCTS,
    NoEvaluableLabels,
    load_gold,
    load_planted,
)
from src.models.transformer import carve_validation  # noqa: E402
from src.risk import (  # noqa: E402
    LinearRiskScorer,
    PolarityPolicy,
    RiskCalibrationUnavailable,
    apply_temperature,
    calibrate_risk_index,
    fit_temperature,
    reliability_table,
)

REPORTS_DIR = REPO_ROOT / "reports"

PROVISIONAL_STAMP = "PROVISIONAL -- planted-label measurement, NOT model accuracy"

#: The risk index is a ranking until an outcome exists to calibrate it against.
#: Stamped onto every emitted artifact.
RANKING_STAMP = (
    "RANKING ONLY -- the fused risk index is not calibrated and is not a probability. "
    "No risk outcome exists to calibrate it against."
)


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def probability_source(
    name: str,
    records: Any,
    labels: list[frozenset[str]],
) -> tuple[Any, str]:
    """Fit the model that supplies construct probabilities.

    Takes `records` and `labels` directly rather than a `Split`, so the caller
    controls exactly what the model sees. That matters here: the model must be
    fitted on the *reduced* training set with the validation slice held out, or
    the temperatures would be fitted on data the probability source had already
    memorised and the calibration would be meaningless.

    Two sources, and the note in each branch is the load-bearing part:

    * `tfidf_logreg` -- available today. Genuine `predict_proba`. Scores 0.222
      macro-F1 on the template-disjoint split, so its probabilities are weakly
      informative at best; the risk index built on them ranks accordingly. It is
      here to exercise and gate the *plumbing*, not to produce a result.
    * `transformer` -- the intended source, once OPEN-029 is closed.
    """
    if name == "transformer":
        from src.models.transformer import TransformerBaseline

        model = TransformerBaseline()
        model.fit(records, labels)
        return model, "Phase 14 fine-tuned transformer"

    from src.models.classical import LogisticRegressionBaseline

    model = LogisticRegressionBaseline()
    model.fit(records, labels)
    return model, "Phase 13 TF-IDF + logistic regression (interim source; macro-F1 0.222)"


def probabilities_for(model: Any, records: Any) -> list[dict[str, float]]:
    """Normalise the two sources' outputs to one shape.

    `TransformerBaseline.predict_proba` returns a list of lists in construct
    order; the classical one returns a list of dicts. Converting here rather
    than at each call site means the risk layer never has to know which model it
    is talking to -- which is the property that lets the source be swapped with a
    flag.
    """
    raw = model.predict_proba(records)
    if raw and isinstance(raw[0], dict):
        return raw
    return [dict(zip(CONSTRUCTS, row, strict=True)) for row in raw]


def calibrate_constructs(
    val_probs: list[dict[str, float]],
    val_truth: list[frozenset[str]],
    test_probs: list[dict[str, float]],
    test_truth: list[frozenset[str]],
) -> dict[str, Any]:
    """Fit one temperature per construct on validation, evaluate ECE on test.

    Per construct, not one global temperature. The constructs differ in
    prevalence and in how confidently the model predicts them, so a single
    temperature would over-correct some columns while under-correcting others,
    and the pooled ECE would improve while individual constructs got worse.

    **The two splits are separate arguments and are never combined.** Fitting on
    `test_probs` would drive ECE toward zero and mean nothing; the function
    signature makes that mistake require a deliberate edit rather than a slip.
    """
    out: dict[str, Any] = {"per_construct": {}, "pooled": {}}

    pooled_before: list[float] = []
    pooled_after: list[float] = []
    pooled_outcomes: list[int] = []

    for construct in CONSTRUCTS:
        v_p = [row.get(construct, 0.0) for row in val_probs]
        v_o = [1 if construct in labels else 0 for labels in val_truth]
        t_p = [row.get(construct, 0.0) for row in test_probs]
        t_o = [1 if construct in labels else 0 for labels in test_truth]

        temperature = fit_temperature(v_p, v_o)
        t_scaled = apply_temperature(t_p, temperature)

        before = reliability_table(t_p, t_o, label=f"{construct} (raw)")
        after = reliability_table(t_scaled, t_o, label=f"{construct} (scaled)")

        pooled_before.extend(t_p)
        pooled_after.extend(t_scaled)
        pooled_outcomes.extend(t_o)

        out["per_construct"][construct] = {
            "temperature": temperature,
            "temperature_at_search_bound": temperature <= 0.06 or temperature >= 9.9,
            "support_val": sum(v_o),
            "support_test": sum(t_o),
            "ece_raw": before.ece,
            "ece_scaled": after.ece,
            "mce_raw": before.mce,
            "mce_scaled": after.mce,
            "improved": after.ece < before.ece,
        }

    pooled_raw = reliability_table(pooled_before, pooled_outcomes, label="pooled (raw)")
    pooled_scaled = reliability_table(pooled_after, pooled_outcomes, label="pooled (scaled)")
    out["pooled"] = {
        "ece_raw": pooled_raw.ece,
        "ece_scaled": pooled_scaled.ece,
        "mce_raw": pooled_raw.mce,
        "mce_scaled": pooled_scaled.mce,
        "n": pooled_raw.n,
        "bins_raw": [
            {
                "lower": b.lower,
                "upper": b.upper,
                "count": b.count,
                "confidence": b.mean_confidence,
                "observed": b.observed_frequency,
            }
            for b in pooled_raw.bins
        ],
        "bins_scaled": [
            {
                "lower": b.lower,
                "upper": b.upper,
                "count": b.count,
                "confidence": b.mean_confidence,
                "observed": b.observed_frequency,
            }
            for b in pooled_scaled.bins
        ],
    }
    return out


def sensitivity_analysis(
    test_probs: list[dict[str, float]],
    scorer: LinearRiskScorer,
) -> dict[str, Any]:
    """How much does the risk index depend on choices nobody could fit?

    Two knobs, both set by judgement rather than by data:

    * the **magnitudes** (which constructs weigh more), and
    * the **polarity policy** (what to do with a directionally unresolved
      construct).

    A conclusion that survives only at one setting is a conclusion about the
    setting. Reporting rank correlation across settings is the cheapest honest
    way to say how much of the index is structure and how much is the author's
    thumb. Spearman is computed inline -- ten lines of arithmetic against a
    scipy dependency the light image does not carry.
    """

    def ranks(values: list[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2 + 1
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out

    def spearman(a: list[float], b: list[float]) -> float:
        ra, rb = ranks(a), ranks(b)
        n = len(a)
        if n < 2:
            return 1.0
        mean_a, mean_b = sum(ra) / n, sum(rb) / n
        num = sum((x - mean_a) * (y - mean_b) for x, y in zip(ra, rb, strict=True))
        den_a = sum((x - mean_a) ** 2 for x in ra) ** 0.5
        den_b = sum((y - mean_b) ** 2 for y in rb) ** 0.5
        return num / (den_a * den_b) if den_a and den_b else 1.0

    baseline = [s.index for s in scorer.score_many(test_probs)]
    variants: dict[str, list[float]] = {}

    for policy in (PolarityPolicy.PESSIMISTIC, PolarityPolicy.OPTIMISTIC):
        variant = LinearRiskScorer(
            directions=scorer.directions,
            magnitudes=dict(scorer.magnitudes),
            polarity_policy=policy,
        )
        variants[f"polarity_{policy.value}"] = [s.index for s in variant.score_many(test_probs)]

    flat = LinearRiskScorer(
        directions=scorer.directions,
        magnitudes=dict.fromkeys(scorer.magnitudes, 1.0),
        polarity_policy=scorer.polarity_policy,
    )
    variants["uniform_magnitudes"] = [s.index for s in flat.score_many(test_probs)]

    return {
        "baseline_mean_index": sum(baseline) / len(baseline) if baseline else 0.0,
        "variants": {
            name: {
                "spearman_vs_baseline": spearman(baseline, values),
                "mean_index": sum(values) / len(values) if values else 0.0,
                "mean_absolute_shift": (
                    sum(abs(x - y) for x, y in zip(baseline, values, strict=True)) / len(baseline)
                    if baseline
                    else 0.0
                ),
            }
            for name, values in variants.items()
        },
    }


def check_context_interface(scorer: LinearRiskScorer, row: dict[str, float]) -> dict[str, Any]:
    """Gate condition 3: context features are accepted and the text-only path is unchanged.

    Two assertions, and the second is the one that matters. It is not enough that
    passing context *works*; passing context to a **text-only** scorer must leave
    the number **bit-identical**, or the primary reported model would drift the
    moment someone started experimenting with context.
    """
    text_only = scorer.score(row)
    ignored = scorer.score(row, context={"hours_to_competition": 3.0, "training_load": 0.8})

    contextual = LinearRiskScorer(
        directions=scorer.directions,
        magnitudes=dict(scorer.magnitudes),
        polarity_policy=scorer.polarity_policy,
        context_weights={"hours_to_competition": -0.05, "training_load": 0.4},
    )
    with_context = contextual.score(
        row, context={"hours_to_competition": 3.0, "training_load": 0.8}
    )

    return {
        "text_only_index": text_only.index,
        "text_only_unchanged_when_context_passed": ignored.index == text_only.index,
        "contextual_index": with_context.index,
        "context_features_used": list(with_context.context_used),
        "context_changed_the_score": with_context.index != text_only.index,
    }


def write_reports(payload: dict[str, Any], examples: list[str]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "calibration.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    pooled = payload["calibration"]["pooled"]
    per_construct = payload["calibration"]["per_construct"]
    gate = payload["gate"]

    md: list[str] = [
        "# Phase 15 -- Risk scoring and calibration",
        "",
        f"> **{payload['status']}**",
        ">",
        f"> **{RANKING_STAMP}**",
        "",
        "This page reports two different things and the difference is the point.",
        "",
        "1. **Per-construct calibration** -- real, computed below. The construct",
        "   probabilities are calibrated against the planted construct labels, so the",
        "   ECE is a corpus property (OPEN-025), not a statement about athletes.",
        "2. **Risk-index calibration** -- *not computed, because it cannot be.* It needs",
        "   an observed risk outcome per record and none exists: no administered CSAI-2,",
        "   no clinician rating, no linked competition outcome. `calibrate_risk_index`",
        "   raises rather than substituting a proxy, because the obvious proxy",
        '   ("risk = 1 if any risk-raising construct was planted") is a restatement of',
        "   the fusion's own inputs and would produce a good ECE that means nothing.",
        "",
        f"- Generated: {payload['generated_on']}",
        f"- Probability source: {payload['environment']['probability_source']}",
        f"- Python {payload['environment']['python']}, seed {payload['environment']['seed']}",
        f"- Split: template-disjoint, {payload['environment']['n_train']} train / "
        f"{payload['environment']['n_val']} val / {payload['environment']['n_test']} test",
        "",
        "## Gate",
        "",
        f"**{'PASSED' if gate['passed'] else 'FAILED'}**",
        "",
        "| condition | result |",
        "|---|---|",
        f"| ECE reported | {'yes' if gate['ece_reported'] else 'NO'} "
        f"(pooled raw {pooled['ece_raw']:.4f} -> scaled {pooled['ece_scaled']:.4f}) |",
        f"| decomposition human-readable | {'yes' if gate['decomposition_readable'] else 'NO'} |",
        f"| context interface non-breaking | {'yes' if gate['context_interface_ok'] else 'NO'} |",
        "",
        "## Calibration by construct",
        "",
        "Temperature is fitted on the **validation** slice and evaluated on **test**.",
        "T > 1 softens over-confident probabilities, T < 1 sharpens under-confident ones.",
        "",
        "| construct | T | ECE raw | ECE scaled | improved | test support |",
        "|---|---|---|---|---|---|",
    ]
    for construct in CONSTRUCTS:
        row = per_construct[construct]
        flag = " ⚠" if row["temperature_at_search_bound"] else ""
        md.append(
            f"| {construct} | {row['temperature']:.2f}{flag} | {row['ece_raw']:.4f} "
            f"| {row['ece_scaled']:.4f} | {'yes' if row['improved'] else 'no'} "
            f"| {row['support_test']} |"
        )

    md.extend(
        [
            "",
            "⚠ = the temperature search hit its bound; read that row as "
            '"outside the searched range" rather than as a fit.',
            "",
            f"**Pooled:** ECE {pooled['ece_raw']:.4f} -> {pooled['ece_scaled']:.4f}, "
            f"MCE {pooled['mce_raw']:.4f} -> {pooled['mce_scaled']:.4f}, n={pooled['n']}.",
            "",
            "## Reliability (pooled, after scaling)",
            "",
            "| bin | n | mean confidence | observed frequency | gap |",
            "|---|---|---|---|---|",
        ]
    )
    for b in pooled["bins_scaled"]:
        if b["count"] == 0:
            continue
        md.append(
            f"| [{b['lower']:.1f}, {b['upper']:.1f}) | {b['count']} "
            f"| {b['confidence']:.3f} | {b['observed']:.3f} "
            f"| {b['confidence'] - b['observed']:+.3f} |"
        )

    md.extend(["", "## Worked examples (gate condition 2)", ""])
    for example in examples:
        md.extend(["```", example, "```", ""])

    if "sensitivity" in payload:
        md.extend(
            [
                "## Sensitivity to unfittable choices",
                "",
                "The magnitudes and the polarity policy are set by judgement, not fitted --",
                "there is no risk target to fit them against. This table says how much the",
                "index depends on them. A conclusion that survives only at one setting is a",
                "conclusion about the setting.",
                "",
                "| variant | Spearman vs default | mean index | mean absolute shift |",
                "|---|---|---|---|",
            ]
        )
        for name, block in sorted(payload["sensitivity"]["variants"].items()):
            md.append(
                f"| {name} | {block['spearman_vs_baseline']:.3f} "
                f"| {block['mean_index']:.3f} | {block['mean_absolute_shift']:.3f} |"
            )
        md.append("")

    md.extend(
        [
            "## Limitations",
            "",
            "1. **The risk index is a ranking, not a probability.** Nothing here licenses",
            '   reading 0.7 as "70% of such athletes".',
            "2. **The probability source is weak.** The interim TF-IDF model scores 0.222",
            "   macro-F1 template-disjoint; calibrating a weakly-informative probability",
            "   makes it honest, not accurate.",
            "3. **The calibration target is planted labels** on synthetic text (OPEN-025,",
            "   OPEN-011).",
            "4. **The fusion is declared, not learned** -- signs come from",
            "   `config/taxonomy.yaml`'s `risk_direction`, magnitudes are coarse tiers.",
            "5. **Polarity-bearing constructs contribute nothing by default**, because the",
            "   presence classifier emits no sub-label. See the sensitivity table for how",
            "   much that matters.",
            "",
            "## What would make the risk index calibratable",
            "",
            "Administered CSAI-2 scores alongside pre-competition text, or outcome-linked",
            'data. That is the "Outcome-linkage validation" expansion in `CLAUDE.md`',
            "sec.10, and it is the single acquisition that would turn the risk index from a",
            "ranking into a measurement.",
            "",
        ]
    )
    (REPORTS_DIR / "calibration.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 15 risk scoring gate")
    parser.add_argument("--source", default="synth_precomp_v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument(
        "--source-model",
        default="tfidf_logreg",
        choices=("tfidf_logreg", "transformer"),
        help="where construct probabilities come from (default: the Phase 13 model)",
    )
    parser.add_argument("--sensitivity", action="store_true", help="run the weight ablation")
    parser.add_argument("--gold", action="store_true", help="refuses while data/gold/ is empty")
    args = parser.parse_args(argv)

    try:
        dataset = load_gold(args.source) if args.gold else load_planted(args.source)
    except NoEvaluableLabels as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - a missing corpus is a user error
        print(f"ERROR: could not build the dataset: {exc}", file=sys.stderr)
        return 2

    print(f"Phase 15 risk scoring  seed={args.seed}  source={args.source_model}")
    print(" ", dataset.summary())
    print(f"  STATUS: {PROVISIONAL_STAMP}")
    print(f"  {RANKING_STAMP}")

    index = {r.record_id: ls for r, ls in zip(dataset.records, dataset.labels, strict=True)}
    split = template_disjoint_split(dataset.records, test_size=args.test_size, seed=args.seed)
    if not split.test:
        print("  FAIL: empty test set", file=sys.stderr)
        return 2

    # Validation is carved from TRAIN and is used only to fit temperatures.
    train_idx, val_idx = carve_validation(
        split.train,
        [index[r.record_id] for r in split.train],
        fraction=args.val_fraction,
        seed=args.seed,
    )
    fit_records = [split.train[i] for i in train_idx]
    val_records = [split.train[i] for i in val_idx]
    y_fit = [index[r.record_id] for r in fit_records]
    y_val = [index[r.record_id] for r in val_records]
    y_test = [index[r.record_id] for r in split.test]

    _rule("Split")
    print(" ", split.summary())
    print(f"  fit={len(fit_records)} val={len(val_records)} test={len(split.test)}")

    # Fitted on the REDUCED training set. The validation slice is held out from
    # the probability source as well as from the temperature fit -- otherwise the
    # temperatures would be fitted on predictions the model had memorised, and a
    # memorised prediction is confidently correct, which makes a miscalibrated
    # model look calibrated.
    try:
        model, source_description = probability_source(args.source_model, fit_records, y_fit)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: could not fit the probability source: {exc}", file=sys.stderr)
        return 2

    val_probs = probabilities_for(model, val_records)
    test_probs = probabilities_for(model, split.test)

    _rule("Calibration (fitted on val, evaluated on test)")
    calibration = calibrate_constructs(val_probs, y_val, test_probs, y_test)
    pooled = calibration["pooled"]
    print(f"  pooled ECE {pooled['ece_raw']:.4f} -> {pooled['ece_scaled']:.4f}")
    print(f"  pooled MCE {pooled['mce_raw']:.4f} -> {pooled['mce_scaled']:.4f}")
    improved = sum(1 for v in calibration["per_construct"].values() if v["improved"])
    print(f"  constructs improved by scaling: {improved}/{len(CONSTRUCTS)}")

    _rule("Risk index -- refusal check")
    try:
        calibrate_risk_index()
        print("  ERROR: calibrate_risk_index did not refuse", file=sys.stderr)
        return 2
    except RiskCalibrationUnavailable:
        print("  calibrate_risk_index() correctly refuses: no risk outcome exists.")

    scorer = LinearRiskScorer()

    _rule("Worked examples (gate condition 2: readable decomposition)")
    # Highest, median and lowest scoring test records -- the ends and the middle,
    # so the report shows what a low score looks like as well as a high one.
    scored = sorted(
        zip(split.test, scorer.score_many(test_probs), strict=True),
        key=lambda pair: pair[1].index,
    )
    picks = [scored[-1], scored[len(scored) // 2], scored[0]]
    examples: list[str] = []
    for record, risk in picks:
        text = record.text if len(record.text) <= 220 else record.text[:217] + "..."
        block = f'"{text}"\n\n{risk.explain()}'
        examples.append(block)
        print()
        print("  " + block.replace("\n", "\n  "))

    readable = all(
        risk.explain().splitlines() and "Risk index" in risk.explain() for _, risk in picks
    )

    _rule("Context interface (gate condition 3)")
    context_check = check_context_interface(scorer, test_probs[0])
    for key, value in context_check.items():
        print(f"  {key}: {value}")
    context_ok = bool(
        context_check["text_only_unchanged_when_context_passed"]
        and context_check["context_changed_the_score"]
        and context_check["context_features_used"]
    )

    payload: dict[str, Any] = {
        "phase": 15,
        "generated_on": datetime.now(UTC).date().isoformat(),
        "status": PROVISIONAL_STAMP,
        "risk_index_status": RANKING_STAMP,
        "is_accuracy": False,
        "risk_index_is_calibrated": False,
        "environment": {
            "python": platform.python_version(),
            "seed": args.seed,
            "probability_source": source_description,
            "n_train": len(fit_records),
            "n_val": len(val_records),
            "n_test": len(split.test),
        },
        "scorer": scorer.manifest(),
        "calibration": calibration,
        "context_interface": context_check,
    }

    if args.sensitivity:
        _rule("Sensitivity to unfittable choices")
        payload["sensitivity"] = sensitivity_analysis(test_probs, scorer)
        for name, block in sorted(payload["sensitivity"]["variants"].items()):
            print(
                f"  {name:<26} spearman={block['spearman_vs_baseline']:.3f} "
                f"mean_shift={block['mean_absolute_shift']:.3f}"
            )

    gate = {
        "ece_reported": True,
        "decomposition_readable": readable,
        "context_interface_ok": context_ok,
        "risk_index_calibration_correctly_refused": True,
        "passed": bool(readable and context_ok),
        "note": (
            "The gate asks for ECE to be REPORTED, not to be low. A high ECE that is "
            "measured and stated is a result; a low one obtained by fitting the "
            "calibrator on the evaluation data is a fabrication."
        ),
    }
    payload["gate"] = gate
    write_reports(payload, examples)

    _rule("Gate")
    for key in ("ece_reported", "decomposition_readable", "context_interface_ok"):
        print(f"  {key:<32} {'PASS' if gate[key] else 'FAIL'}")
    print(f"  {'result':<32} {'PASS' if gate['passed'] else 'FAIL'}")
    print("\n  Wrote reports/calibration.json, reports/calibration.md")

    return 0 if gate["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
