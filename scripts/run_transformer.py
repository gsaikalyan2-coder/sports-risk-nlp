#!/usr/bin/env python
"""Phase 14 gate -- fine-tune the transformer and test it against the Phase 13 bar.

    python scripts/run_transformer.py                 # single default config, both splits
    python scripts/run_transformer.py --sweep         # the 6-point hyperparameter sweep
    python scripts/run_transformer.py --base-model roberta-base
    python scripts/run_transformer.py --dry-run       # plan only; no torch, no weights
    python scripts/run_transformer.py --gold          # refuses; data/gold/ is empty

WHAT THE GATE ACTUALLY TESTS
----------------------------
`PROJECT_PLAN.md` Phase 14 states the gate as "transformer > best baseline
(macro-F1)". This script evaluates exactly that, on the **template-disjoint**
split, with a paired bootstrap significance test rather than a bare comparison of
point estimates -- 0.47 vs 0.46 is not a win unless the gap survives resampling,
and `src/evaluation/metrics.py:paired_bootstrap_p_value` was written for this
gate specifically.

The Phase 13 bar, template-disjoint, planted labels:

    lexicon           0.462   <- the bar the gate is set against (OPEN-021 floor)
    tfidf_logreg      0.222
    tfidf_linearsvc   0.181
    memorisation      0.197
    stratified_random 0.104
    majority          0.000

WHAT PASSING WOULD AND WOULD NOT MEAN
-------------------------------------
Passing means a pretrained encoder recovers more of the planted template grammar
than a hand-written cue lexicon does, across held-out templates. That is a
statement about `synth_precomp_v1`. It is **not** evidence that the model detects
psychological constructs in athlete text, because no athlete wrote any of this
text and no human verified any of these labels (`data/gold/` is empty, OPEN-025).

So the gate result and its reinterpretation are recorded together, in the same
sentence, everywhere they appear -- console, JSON, Markdown and model card. A
gate result that travels without its caveat becomes a claim.

Failing is equally informative and is not treated as an error to be tuned away.
A transformer that cannot beat a cue lexicon on held-out templates says the
corpus's construct signal is essentially the cue words themselves, with no
paraphrase-level structure to generalise over. That is a finding about synthetic
corpus design, it is publishable, and engineering it away by sweeping harder
would be the dishonest move.

Exit codes: 0 gate passed, 1 gate failed (a real result, recorded), 2 config
error (missing dependency, unreachable weights, refused label source).
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation import (  # noqa: E402
    bootstrap_ci,
    leakage_report,
    macro_f1,
    micro_f1,
    paired_bootstrap_p_value,
    per_label_prf,
    random_split,
    subset_accuracy,
    template_disjoint_split,
)
from src.models.dataset import (  # noqa: E402
    CONSTRUCTS,
    Dataset,
    NoEvaluableLabels,
    load_gold,
    load_planted,
    load_silver,
)
from src.models.transformer import (  # noqa: E402
    DEFAULT_SWEEP,
    FAST_BASE_MODEL,
    HParams,
    MLDependencyMissing,
    TransformerBaseline,
    WeightsUnavailable,
)

REPORTS_DIR = REPO_ROOT / "reports"
MODELS_DIR = REPO_ROOT / "models"
LOGS_DIR = REPO_ROOT / "logs"
BASELINES_JSON = REPORTS_DIR / "baselines.json"

PROVISIONAL_STAMP = "PROVISIONAL -- planted-label measurement, NOT model accuracy"
SILVER_STAMP = "INVALID -- silver labels are PRNG output (OPEN-028). Ablation only."

#: The gate's reference system. The lexicon rather than the best TF-IDF model,
#: and that choice is deliberate: on the template-disjoint split the lexicon
#: (0.462) is more than double the best TF-IDF model (0.222), so "beat the best
#: baseline" and "beat the lexicon" are the same requirement, and naming the
#: lexicon makes the bar legible without a lookup. `--reference` overrides it.
GATE_REFERENCE = "lexicon"

#: Significance level for the paired bootstrap. A gate that fires on an
#: insignificant gap is a gate that will eventually pass by luck.
GATE_ALPHA = 0.05


def _rule(title: str) -> None:
    print(f"\n{title}\n{'=' * len(title)}")


def _labels_for(side: tuple, index: dict[str, frozenset[str]]) -> list[frozenset[str]]:
    """Look labels up by record ID, never by position.

    Same reasoning as `scripts/run_baselines.py`: the splits shuffle, so a
    positional zip would pair each record with someone else's labels and produce
    a plausible macro-F1 computed against noise.
    """
    return [index[record.record_id] for record in side]


def load_baseline_bar() -> dict[str, Any]:
    """Read the Phase 13 numbers this gate is measured against.

    Read from `reports/baselines.json` rather than hardcoded, so the bar cannot
    drift out of date relative to the artifact that produced it. If Phase 13 is
    re-run with a different seed, the gate automatically compares against the
    new numbers instead of against a stale comment.
    """
    if not BASELINES_JSON.is_file():
        raise FileNotFoundError(
            f"{BASELINES_JSON} not found. The Phase 14 gate is defined relative to "
            "the Phase 13 bar. Run `python scripts/run_baselines.py` first."
        )
    return json.loads(BASELINES_JSON.read_text(encoding="utf-8"))


def baseline_predictions(
    split: Any,
    y_train: list[frozenset[str]],
    reference: str,
) -> list[frozenset[str]]:
    """Refit the reference baseline on this split, for the paired test.

    The paired bootstrap needs both systems' predictions on the *same* test
    records. `reports/baselines.json` stores scores, not predictions, so the
    reference is refit here. It is cheap (the lexicon is rule-based; the TF-IDF
    models fit in seconds) and it guarantees the pairing is real rather than
    reconstructed from summary statistics.
    """
    from src.evaluation import (
        LexiconBaseline,
        MajorityBaseline,
        MemorisationProbe,
        StratifiedRandomBaseline,
    )
    from src.models.classical import LinearSVCBaseline, LogisticRegressionBaseline

    registry = {
        "lexicon": LexiconBaseline,
        "majority": MajorityBaseline,
        "memorisation_probe": MemorisationProbe,
        "stratified_random": StratifiedRandomBaseline,
        "tfidf_logreg": LogisticRegressionBaseline,
        "tfidf_linearsvc": LinearSVCBaseline,
    }
    if reference not in registry:
        raise KeyError(f"unknown reference system {reference!r}; choose from {sorted(registry)}")
    factory = registry[reference]
    model = factory() if "seed" not in getattr(factory, "__dataclass_fields__", {}) else factory()
    model.fit(split.train, y_train)
    return model.predict(split.test)


def score_system(
    y_true: list[frozenset[str]],
    y_pred: list[frozenset[str]],
    *,
    seed: int,
    n_resamples: int,
) -> dict[str, Any]:
    """Macro/micro F1 with bootstrap CIs, plus per-construct breakdown.

    Identical metric code to Phase 13 -- imported from the same module, not
    reimplemented -- so a difference between the transformer row and a baseline
    row is a difference in the model and not in the measurement.
    """
    macro = bootstrap_ci(
        y_true, y_pred, lambda t, p: macro_f1(t, p, CONSTRUCTS), n_resamples=n_resamples, seed=seed
    )
    micro = bootstrap_ci(
        y_true, y_pred, lambda t, p: micro_f1(t, p, CONSTRUCTS), n_resamples=n_resamples, seed=seed
    )
    return {
        "macro_f1": {"point": macro.point, "low": macro.low, "high": macro.high},
        "micro_f1": {"point": micro.point, "low": micro.low, "high": micro.high},
        "subset_accuracy": subset_accuracy(y_true, y_pred),
        "per_construct": {
            label: {
                "precision": prf.precision,
                "recall": prf.recall,
                "f1": prf.f1,
                "support": prf.support,
            }
            for label, prf in per_label_prf(y_true, y_pred, CONSTRUCTS).items()
        },
    }


def run_configuration(
    hparams: HParams,
    split: Any,
    dataset: Dataset,
    *,
    args: Any,
) -> dict[str, Any]:
    """Fit one configuration on one split and score it. Returns a result block."""
    index = {r.record_id: ls for r, ls in zip(dataset.records, dataset.labels, strict=True)}
    y_train = _labels_for(split.train, index)
    y_test = _labels_for(split.test, index)

    started = time.time()
    model = TransformerBaseline(hparams=hparams)
    model.fit(split.train, y_train)
    y_pred = model.predict(split.test)
    elapsed = time.time() - started

    block = score_system(y_test, y_pred, seed=args.seed, n_resamples=args.resamples)

    # Robustness check: the same model, scored with no threshold tuning at all.
    #
    # Per-construct thresholds are 10 free parameters fitted on a validation
    # slice, and a reviewer is entitled to ask how much of the headline number
    # they are responsible for. Scoring the identical probabilities at a flat 0.5
    # answers that for free -- no retraining, one decode. A large gap between the
    # two means the result leans on the tuning and the tuning leans on a slice of
    # a few hundred records; a small gap means the model, not the thresholds, is
    # doing the work.
    #
    # Added after the first real run, where thresholds tuned on 207 records drove
    # `attentional_focus` to P=0.141 R=1.000. That is the failure this column
    # makes visible instead of leaving for a reviewer to find.
    from src.models.transformer import decode_predictions

    y_untuned = decode_predictions(
        model.predict_proba(split.test), [0.5] * len(CONSTRUCTS), CONSTRUCTS
    )
    untuned = score_system(y_test, y_untuned, seed=args.seed, n_resamples=args.resamples)
    block["untuned_threshold_0.5"] = {
        "macro_f1": untuned["macro_f1"],
        "micro_f1": untuned["micro_f1"],
        "per_construct": untuned["per_construct"],
        "delta_from_tuned": block["macro_f1"]["point"] - untuned["macro_f1"]["point"],
        "note": (
            "Same fitted model, thresholds fixed at 0.5 instead of tuned. "
            "Quantifies how much of the tuned macro-F1 is attributable to the "
            "10 tuned threshold parameters rather than to the encoder."
        ),
    }

    block["hparams"] = hparams.as_dict()
    block["slug"] = hparams.slug()
    block["train_seconds"] = round(elapsed, 1)
    block["manifest"] = model.manifest()
    block["status"] = PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP

    # The paired comparison, on this split, against the reference baseline.
    y_ref = baseline_predictions(split, y_train, args.reference)
    ref_macro = macro_f1(y_test, y_ref, CONSTRUCTS)
    block["reference"] = {
        "name": args.reference,
        "macro_f1": ref_macro,
        "delta": block["macro_f1"]["point"] - ref_macro,
        "paired_bootstrap_p": paired_bootstrap_p_value(
            y_test,
            y_pred,
            y_ref,
            lambda t, p: macro_f1(t, p, CONSTRUCTS),
            n_resamples=args.resamples,
            seed=args.seed,
        ),
    }

    if args.save and split.name == "template_disjoint" and dataset.has_signal:
        target = MODELS_DIR / f"phase14_transformer_{hparams.slug()}"
        model.save(target)
        block["saved_to"] = str(target.relative_to(REPO_ROOT))

    write_run_log(block, split_name=split.name, args=args)
    return block


def write_run_log(block: dict[str, Any], *, split_name: str, args: Any) -> None:
    """One JSON file per fitted configuration, plus a cost-ledger line.

    `CLAUDE.md` sec.4 requires every agent to log what it did and what it cost.
    A local fine-tune costs no API money, and the ledger records it at 0.00
    anyway with the wall-clock time in the note -- an empty row for a run that
    consumed an hour of compute would misrepresent the project's real costs, and
    "free" is a claim worth being able to substantiate.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = LOGS_DIR / f"transformer_{split_name}_{block['slug']}_{stamp}.json"
    path.write_text(json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ledger = LOGS_DIR / "cost_ledger.csv"
    is_new = not ledger.exists()
    with ledger.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if is_new:
            writer.writerow(
                [
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
            )
        writer.writerow(
            [
                datetime.now(UTC).isoformat(timespec="seconds"),
                "modeling",
                14,
                "local",
                block["hparams"]["base_model"],
                0,
                0,
                "0.000000",
                f"finetune {split_name} {block['slug']} "
                f"macroF1={block['macro_f1']['point']:.4f} "
                f"{block['train_seconds']}s [local, no API cost]",
            ]
        )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def write_reports(payload: dict[str, Any]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "transformer.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    disjoint = payload["splits"].get("template_disjoint", {})
    rnd = payload["splits"].get("random", {})
    best = payload.get("best", {})
    gate = payload.get("gate", {})

    md: list[str] = [
        "# Phase 14 -- Transformer results",
        "",
        f"> **{payload['status']}**",
        "",
        "This page reports how much of the `synth_precomp_v1` template grammar a",
        "fine-tuned transformer recovers against `generation_spec.planted_constructs`.",
        "It does **not** report accuracy, and none of these numbers may be described",
        "as the model's ability to detect psychological constructs in athlete text.",
        "`data/gold/` is empty (OPEN-025): no human-verified evaluation set exists,",
        "so no accuracy claim is available to this project yet.",
        "",
        "Belongs in the paper's dataset / methodology section. Never the results table.",
        "",
        f"- Generated: {payload['generated_on']}",
        f"- Base model: `{payload['environment']['base_model']}`",
        f"- torch {payload['environment'].get('torch', 'n/a')}, "
        f"transformers {payload['environment'].get('transformers', 'n/a')}, "
        f"Python {payload['environment']['python']}, seed {payload['environment']['seed']}",
        f"- Configurations evaluated: {payload['environment']['n_configurations']}",
        "",
        "## Gate",
        "",
        f"**{'PASSED' if gate.get('passed') else 'FAILED'}** -- "
        f"transformer {gate.get('transformer_macro_f1', float('nan')):.3f} vs "
        f"{gate.get('reference')} {gate.get('reference_macro_f1', float('nan')):.3f} "
        f"on the template-disjoint split "
        f"(delta {gate.get('delta', float('nan')):+.3f}, "
        f"paired bootstrap p={gate.get('paired_bootstrap_p', float('nan')):.3f}).",
        "",
        "### What that result means, and what it does not",
        "",
        gate.get("interpretation", ""),
        "",
        "## Headline table",
        "",
    ]

    md.extend(
        [
            f"| {'configuration':<44} | {'disjoint macro-F1 [95% CI]':<28} "
            f"| {'random':<8} | {'gap':>7} |",
            f"|{'-' * 46}|{'-' * 30}|{'-' * 10}|{'-' * 9}|",
        ]
    )
    for slug, block in sorted(disjoint.items()):
        d = block["macro_f1"]
        ci = f"{d['point']:.3f} [{d['low']:.3f}, {d['high']:.3f}]"
        r = rnd.get(slug, {}).get("macro_f1", {}).get("point")
        gap = f"{r - d['point']:+.3f}" if r is not None else "n/a"
        r_txt = f"{r:.3f}" if r is not None else "n/a"
        md.append(f"| {slug:<44} | {ci:<28} | {r_txt:<8} | {gap:>7} |")

    md.extend(
        [
            "",
            "The `random` column is included **only** so the gap can be read. On the",
            "random split 149 templates appear on both sides, and TF-IDF+LinearSVC",
            "already scores 1.000 there (Phase 13). A high random-split number measures",
            "template memorisation and must never be quoted alone -- that is OPEN-012.",
            "",
            "## Against the Phase 13 bar (template-disjoint, planted labels)",
            "",
            "| system | macro-F1 |",
            "|---|---|",
        ]
    )
    for name, score in sorted(payload["phase13_bar"].items(), key=lambda kv: kv[1], reverse=True):
        md.append(f"| {name} | {score:.3f} |")
    if best:
        md.append(
            f"| **transformer ({best.get('slug', '?')})** | **{best.get('macro_f1', 0):.3f}** |"
        )

    md.extend(
        [
            "",
            "## How much of this is the tuned thresholds?",
            "",
            "The same fitted models, re-scored with every threshold fixed at 0.5 instead",
            "of tuned on the validation slice. The per-construct thresholds are 10 free",
            "parameters; this column says how much of the headline number they are",
            "responsible for. A large `delta` means the result leans on tuning done over",
            "a few hundred validation records rather than on the encoder.",
            "",
            "| configuration | tuned | untuned (0.5) | delta |",
            "|---|---|---|---|",
        ]
    )
    for slug, block in sorted(disjoint.items()):
        untuned = block.get("untuned_threshold_0.5")
        if untuned is None:
            continue
        md.append(
            f"| {slug} | {block['macro_f1']['point']:.3f} "
            f"| {untuned['macro_f1']['point']:.3f} "
            f"| {untuned['delta_from_tuned']:+.3f} |"
        )

    md.extend(
        [
            "",
            "## Per-construct F1 (template-disjoint, best configuration)",
            "",
            "| construct | precision | recall | F1 | support |",
            "|---|---|---|---|---|",
        ]
    )
    best_block = disjoint.get(best.get("slug", ""), {})
    for construct in CONSTRUCTS:
        cell = best_block.get("per_construct", {}).get(construct)
        if cell is None:
            md.append(f"| {construct} | - | - | - | - |")
        else:
            md.append(
                f"| {construct} | {cell['precision']:.3f} | {cell['recall']:.3f} "
                f"| {cell['f1']:.3f} | {cell['support']} |"
            )

    md.extend(
        [
            "",
            "## Limitations that apply to every number above",
            "",
            "1. **The labels were planted, not observed.** They record what the generator",
            "   was told to write, not what a human judged the text to express.",
            "2. **The text is synthetic.** No athlete wrote it. Domain shift from template",
            "   English to real pre-competition speech is unmeasured and is expected to be",
            "   large (OPEN-011).",
            "3. **Thresholds were tuned on a validation slice of ~15% of training records.**",
            "   For the rarest constructs that is a few hundred examples, which is thin.",
            "4. **The sweep selected a configuration on this test split.** With a handful of",
            "   configurations the selection bias is small but it is not zero, and the",
            "   reported best is therefore mildly optimistic.",
            "",
            "## How to make these numbers real",
            "",
            "1. Recruit a second annotator and populate `data/gold/` (OPEN-025).",
            "2. Acquire real pre-competition athlete text (OPEN-011) -- the project's",
            "   highest live risk, because contribution #1 depends on it.",
            "3. Re-run `python scripts/run_transformer.py --gold`. The harness changes an",
            "   input path and nothing else; the numbers it then prints are accuracies",
            "   and this warning can be deleted.",
            "",
        ]
    )
    (REPORTS_DIR / "transformer.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def gate_interpretation(passed: bool, significant: bool, reference: str) -> str:
    """The sentence that travels with the gate result everywhere it appears."""
    if passed:
        return (
            f"The transformer recovers more of the planted template grammar than the "
            f"{reference} baseline does, across held-out templates, and the gap survives "
            f"a paired bootstrap. This is a **corpus property**: it says the near-synonym "
            f"substitution layer produced realisations varied enough that a pretrained "
            f"encoder generalises across them, where a bag-of-ngrams model could not. It "
            f"is **not** evidence that the model detects psychological constructs in "
            f"athlete text -- no athlete wrote this text and no human verified these "
            f"labels (OPEN-025). The gate is satisfied for the purposes of "
            f"PROJECT_PLAN.md Phase 14; the publication-readiness criterion in CLAUDE.md "
            f"sec.9 is not, and cannot be, until a real gold set exists."
        )
    if not significant:
        return (
            f"The transformer's point estimate differs from the {reference} baseline but "
            f"the gap does not survive a paired bootstrap, so the two systems are not "
            f"distinguishable on this test set. Reporting the point difference as a win "
            f"would be reporting noise. Treat this as 'no measurable difference' rather "
            f"than as a narrow pass or a narrow failure."
        )
    return (
        f"The transformer does **not** beat the {reference} baseline on held-out "
        f"templates. Read literally, this says the construct signal in "
        f"`synth_precomp_v1` is essentially the cue words themselves, with little "
        f"paraphrase-level structure for a contextual encoder to generalise over -- the "
        f"generator varies slot fillers and near-synonyms but not the underlying "
        f"construction. That is a finding about synthetic-corpus design and it is worth "
        f"reporting as one. Do not sweep harder to make this number go up: the quantity "
        f"being optimised is agreement with a template generator, not construct "
        f"detection, so a higher number here would not be a better model."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 14 transformer gate")
    parser.add_argument("--source", default="synth_precomp_v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--resamples", type=int, default=400)
    parser.add_argument("--base-model", default=None, help="hub id or local checkpoint directory")
    parser.add_argument(
        "--fast",
        action="store_true",
        help=(
            f"use {FAST_BASE_MODEL} (6 layers, ~2x faster than roberta-base). "
            "Compute-constrained choice, owner-selected 2026-08-11. Report it as "
            "such in the paper -- it is not the strongest available encoder."
        ),
    )
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--max-length", type=int, default=None)
    parser.add_argument("--sweep", action="store_true", help="run the 6-point sweep")
    parser.add_argument(
        "--all-splits",
        action="store_true",
        help=(
            "run every configuration on the random split too (~3x the wall-clock). "
            "By default the random split runs for the best configuration only, "
            "because the memorisation gap is a corpus property and needs one clean "
            "pair of numbers, not six."
        ),
    )
    parser.add_argument(
        "--reference",
        default=GATE_REFERENCE,
        help="baseline the gate is measured against (default: lexicon, the Phase 13 bar)",
    )
    parser.add_argument("--no-save", dest="save", action="store_false", default=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and the bar, touch no weights, import no torch",
    )
    parser.add_argument("--gold", action="store_true", help="refuses while data/gold/ is empty")
    parser.add_argument("--silver", action="store_true", help="ablation against PRNG labels")
    args = parser.parse_args(argv)

    if args.gold and args.silver:
        print("ERROR: --gold and --silver are mutually exclusive", file=sys.stderr)
        return 2

    # -- label source (same discipline as Phase 13; --gold still refuses) ----
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
    except Exception as exc:  # noqa: BLE001 - a missing corpus is a user error
        print(f"ERROR: could not build the dataset: {exc}", file=sys.stderr)
        print("Run `python scripts/run_ingestion.py` first.", file=sys.stderr)
        return 2

    try:
        bar_payload = load_baseline_bar()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    bar = {
        name: block["macro_f1"]["point"]
        for name, block in bar_payload["splits"]["template_disjoint"]["systems"].items()
    }

    # -- build the configuration list ---------------------------------------
    if args.fast and args.base_model:
        print("ERROR: --fast and --base-model are mutually exclusive", file=sys.stderr)
        return 2
    if args.fast:
        args.base_model = FAST_BASE_MODEL

    overrides = {
        key: value
        for key, value in (
            ("base_model", args.base_model),
            ("epochs", args.epochs),
            ("batch_size", args.batch_size),
            ("learning_rate", args.learning_rate),
            ("max_length", args.max_length),
            ("seed", args.seed),
        )
        if value is not None
    }
    if args.sweep:
        requested = [HParams(**{**config.as_dict(), **overrides}) for config in DEFAULT_SWEEP]
        # An override can collapse two sweep points into one. `--epochs 2` maps
        # both the 4-epoch lr2e-5 config and the 6-epoch one onto the same
        # configuration, and since results are keyed by slug the second would
        # silently overwrite the first -- reporting "6 configurations" over 5
        # rows, with an hour of compute spent recomputing a number already held.
        # Collapse explicitly and say so.
        configurations = tuple(dict.fromkeys(requested))
        collapsed = len(requested) - len(configurations)
        if collapsed:
            # Built outside the f-string: nesting same-type quotes inside an
            # f-string expression is a syntax error before Python 3.12, and this
            # project targets 3.11.
            shown = ", ".join(
                "--" + key.replace("_", "-") + f" {value}"
                for key, value in overrides.items()
                if key != "seed"
            )
            print(
                f"  NOTE: {collapsed} sweep configuration(s) became duplicates under your "
                f"overrides ({shown}) and were dropped. "
                f"Running {len(configurations)}, not {len(DEFAULT_SWEEP)}."
            )
    else:
        configurations = (HParams(**{**HParams().as_dict(), **overrides}),)

    print(f"Phase 14 transformer gate  seed={args.seed}  configurations={len(configurations)}")
    print(" ", dataset.summary())
    print(f"  STATUS: {PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP}")
    print(
        f"  Bar ({args.reference}, template-disjoint): {bar.get(args.reference, float('nan')):.3f}"
    )

    splits = {
        "template_disjoint": template_disjoint_split(
            dataset.records, test_size=args.test_size, seed=args.seed
        ),
        "random": random_split(dataset.records, test_size=args.test_size, seed=args.seed),
    }

    if args.dry_run:
        _rule("Dry run -- plan only")
        for split in splits.values():
            print(" ", split.summary())
            report = leakage_report(split)
            print("   ", "; ".join(report.as_lines()[2:]))
        print("\n  Configurations:")
        for config in configurations:
            print(f"    {config.slug()}")
        print("\n  Phase 13 bar (template-disjoint):")
        for name, score in sorted(bar.items(), key=lambda kv: kv[1], reverse=True):
            print(f"    {name:<20} {score:.3f}")
        print("\n  No weights touched, no torch imported. Drop --dry-run to train.")
        return 0

    # -- train ---------------------------------------------------------------
    results: dict[str, dict[str, Any]] = {"template_disjoint": {}, "random": {}}
    environment: dict[str, Any] = {
        "python": platform.python_version(),
        "seed": args.seed,
        "test_size": args.test_size,
        "bootstrap_resamples": args.resamples,
        "base_model": configurations[0].base_model,
        "n_configurations": len(configurations),
    }

    try:
        from src.models.transformer import require_ml_stack

        torch, transformers = require_ml_stack()
        environment["torch"] = torch.__version__
        environment["transformers"] = transformers.__version__
    except MLDependencyMissing as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2

    # Sweep the honest split; run the foil once.
    #
    # Measured on the owner's CPU 2026-08-11: one epoch of roberta-base at
    # batch 16 / length 128 is ~9.2 s/step -- 19 minutes on the template-disjoint
    # split (127 steps) and ~30 on the random one (195 steps). Sweeping all six
    # configurations across both splits is roughly **21 hours**, which against a
    # three-week deadline is not a defensible way to spend the machine.
    #
    # The random split exists only to quantify the memorisation gap (OPEN-012).
    # That gap is a property of the corpus, not of the learning rate, so it needs
    # *one* clean pair of numbers -- not six. Running it for the best
    # configuration only preserves the entire finding at about a third of the
    # cost. `--all-splits` restores the exhaustive version for anyone who wants
    # to check that the gap is stable across hyperparameters.
    plan: list[tuple[str, Any, tuple[HParams, ...]]] = [
        ("template_disjoint", splits["template_disjoint"], configurations)
    ]

    for split_name, split, split_configs in plan:
        _rule(f"Split: {split_name}")
        print(" ", split.summary())
        if not split.test:
            print("  FAIL: empty test set", file=sys.stderr)
            return 2
        for config in split_configs:
            print(f"  training {config.slug()} ...", flush=True)
            try:
                block = run_configuration(config, split, dataset, args=args)
            except (WeightsUnavailable, MLDependencyMissing) as exc:
                # Both are configuration problems, not failed experiments, so
                # they exit 2 rather than 1. MLDependencyMissing can surface
                # here and not only at the import check above: the tokenizer
                # conversion needs `sentencepiece`, and that is discovered when
                # the tokenizer loads, several minutes into a run.
                print(f"\nERROR: {exc}", file=sys.stderr)
                return 2
            results[split_name][config.slug()] = block
            print(
                f"    macro-F1 {block['macro_f1']['point']:.3f} "
                f"[{block['macro_f1']['low']:.3f}, {block['macro_f1']['high']:.3f}]  "
                f"({block['train_seconds']}s, best epoch "
                f"{block['manifest']['best_epoch']})"
            )

    # -- the foil: random split, best configuration only ---------------------
    disjoint = results["template_disjoint"]
    best_slug = max(disjoint, key=lambda k: disjoint[k]["macro_f1"]["point"])
    best_config = next(c for c in configurations if c.slug() == best_slug)

    random_configs = configurations if args.all_splits else (best_config,)
    _rule("Split: random  (the foil -- measures memorisation, never quoted alone)")
    print(" ", splits["random"].summary())
    for config in random_configs:
        print(f"  training {config.slug()} ...", flush=True)
        try:
            block = run_configuration(config, splits["random"], dataset, args=args)
        except (WeightsUnavailable, MLDependencyMissing) as exc:
            print(f"\nERROR: {exc}", file=sys.stderr)
            return 2
        results["random"][config.slug()] = block
        print(
            f"    macro-F1 {block['macro_f1']['point']:.3f} "
            f"[{block['macro_f1']['low']:.3f}, {block['macro_f1']['high']:.3f}]  "
            f"({block['train_seconds']}s)"
        )

    gap = (
        results["random"][best_slug]["macro_f1"]["point"] - disjoint[best_slug]["macro_f1"]["point"]
    )
    print(f"\n  MEMORISATION GAP (random - disjoint, best config): {gap:+.3f}")
    print("  Phase 13 reference: TF-IDF+LinearSVC gapped +0.819 (1.000 vs 0.181).")

    # -- gate ----------------------------------------------------------------
    best_block = disjoint[best_slug]
    reference_score = best_block["reference"]["macro_f1"]
    delta = best_block["reference"]["delta"]
    p_value = best_block["reference"]["paired_bootstrap_p"]
    significant = p_value < GATE_ALPHA
    passed = bool(delta > 0 and significant)

    gate = {
        "passed": passed,
        "reference": args.reference,
        "reference_macro_f1": reference_score,
        "transformer_macro_f1": best_block["macro_f1"]["point"],
        "delta": delta,
        "paired_bootstrap_p": p_value,
        "alpha": GATE_ALPHA,
        "significant": significant,
        "split": "template_disjoint",
        "best_configuration": best_slug,
        "interpretation": gate_interpretation(passed, significant, args.reference),
        "is_accuracy": False,
    }

    payload = {
        "phase": 14,
        "generated_on": datetime.now(UTC).date().isoformat(),
        "status": PROVISIONAL_STAMP if dataset.has_signal else SILVER_STAMP,
        "label_source": dataset.label_source,
        "unit": dataset.unit,
        "is_accuracy": False,
        "what_this_measures": (
            "How much of the synth_precomp_v1 template grammar a fine-tuned "
            "transformer recovers against the constructs the generator planted, and "
            "how much of that recovery is memorisation. NOT detection of "
            "psychological constructs in athlete text. No human-verified evaluation "
            "set exists (OPEN-025)."
        ),
        "environment": environment,
        "dataset": {
            "name": dataset.name,
            "n": len(dataset),
            "label_support": dataset.label_support,
            "constructs_without_support": list(dataset.constructs_without_support),
        },
        "phase13_bar": bar,
        "splits": results,
        "best": {"slug": best_slug, "macro_f1": best_block["macro_f1"]["point"]},
        "gate": gate,
    }
    write_reports(payload)

    _rule("Gate")
    print(f"  best configuration : {best_slug}")
    print(f"  transformer        : {best_block['macro_f1']['point']:.3f} (template-disjoint)")
    print(f"  {args.reference:<19}: {reference_score:.3f}")
    print(f"  delta              : {delta:+.3f}  (paired bootstrap p={p_value:.3f})")
    print(f"  result             : {'PASS' if passed else 'FAIL'}")
    print()
    print("  " + gate["interpretation"].replace(". ", ".\n  "))
    print("\n  Wrote reports/transformer.json, reports/transformer.md")
    print(f"  Run logs: logs/transformer_*_{best_slug}_*.json  (cost ledger updated)")
    print(
        "\n  NEXT: fill in section 5 of docs/model_card.md from reports/transformer.json.\n"
        "  It is deliberately left empty until a real run exists -- a placeholder\n"
        "  number in a model card is the kind of thing that gets quoted."
    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
