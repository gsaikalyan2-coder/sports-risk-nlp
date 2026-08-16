#!/usr/bin/env python
"""Phase 17 gate -- span-level explanations, faithfulness, and the expert study pack.

    python scripts/run_explain.py                       # full run (IG everywhere, SHAP subsample)
    python scripts/run_explain.py --methods ig          # skip SHAP (no shap installed / faster)
    python scripts/run_explain.py --limit 40            # quick smoke run
    python scripts/run_explain.py --study-only          # regenerate the rating sheet, no attribution
    python scripts/run_explain.py --score-study reports/explain/ratings_A1.json ... # analyse returns
    python scripts/run_explain.py --gold                # refuses; data/gold/ is empty

WHAT THIS SCRIPT PRODUCES AND WHAT EACH ARTEFACT IS FOR
--------------------------------------------------------
  reports/explain/attributions.json   every span-level attribution, both methods
  reports/explain/faithfulness.json   comprehensiveness / sufficiency vs random control
  reports/explain/agreement.json      IG vs SHAP rank correlation and top-k overlap
  reports/explain/cards.md            two-level example cards (span -> construct -> risk)
  reports/explain/rating_sheet.md     the blinded instrument a rater fills in
  reports/explain/rating_sheet_KEY.json   the answer key -- DO NOT SEND THIS TO A RATER
  reports/explain/explain.md          the report the paper draws from

THE GATE
--------
`PROJECT_PLAN.md` Phase 17: explanations are span-level and construct-specific,
and expert agreement is reported.

This script can satisfy the first condition on its own. It **cannot** satisfy the
second, and it does not pretend to: no code can make a human rate anything. So
the gate is split, and the exit code reflects only the automatable half:

  * **Automatable** -- attributions carry character offsets and are per-construct
    (structural, asserted), and the attributions beat their random control on
    comprehensiveness and sufficiency (measured; if they do not, the
    explanations are not evidence of anything and the gate fails).
  * **Human** -- the rating sheet is generated and ready, but expert agreement is
    reported only after `--score-study` is run against returned ratings. Until
    then `explain.md` states plainly that the expert half of the gate is
    outstanding, rather than showing a blank table that reads as a pass.

Writing it any other way would let a green exit code stand in for a study that
never happened, which is the specific failure OPEN-007 exists to remind this
project about.

Exit codes: 0 gate passed, 1 gate failed, 2 config error.
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.splits import template_disjoint_split  # noqa: E402
from src.explainability.attribution import (  # noqa: E402
    AttributionUnavailable,
    IntegratedGradients,
    RecordExplanation,
    ShapPartition,
)
from src.explainability.cards import (  # noqa: E402
    CardSet,
    assert_publication_safe,
    build_card,
)
from src.explainability.faithfulness import (  # noqa: E402
    compare_methods,
    score_record,
    summarise,
)
from src.explainability.study import analyse, build_sheet  # noqa: E402
from src.models.dataset import CONSTRUCTS, load_planted  # noqa: E402
from src.risk.fusion import LinearRiskScorer  # noqa: E402

REPORT_DIR = REPO_ROOT / "reports" / "explain"
MODELS_DIR = REPO_ROOT / "models"

#: Default rater population. Deliberately a mouthful and deliberately not
#: "experts". OPEN-004 is open: A2 is a sports-familiar teammate, not a coach or
#: sport-psych practitioner. The claim in the paper must match the raters, and
#: fixing the wording here -- at the point the sheet is generated, before any
#: result is seen -- is what stops it drifting upward once the numbers look good.
DEFAULT_RATER_POPULATION = (
    "sports-familiar student raters (pilot expert-review; NOT coaches or "
    "sport-psychology practitioners -- see OPEN-004)"
)


def _newest_transformer() -> Path:
    """The Phase 14 checkpoint to explain.

    Prefers the configuration the Phase 14 report identifies as best
    (`lr2e-05_bs16_ep6`, macro-F1 0.588 template-disjoint). Explaining a
    different checkpoint from the one whose numbers are reported would produce
    an explanation of a model that appears nowhere in the paper, and nothing in
    the artefact would reveal the mismatch.
    """
    preferred = sorted(MODELS_DIR.glob("phase14_transformer_*_ep6_*"))
    candidates = preferred or sorted(MODELS_DIR.glob("phase14_transformer_*"))
    if not candidates:
        raise SystemExit(
            "2:no Phase 14 checkpoint found under models/. Run "
            "`python scripts/run_transformer.py --sweep` first, or pass "
            "--model-dir explicitly."
        )
    return candidates[-1]


def _load_model(directory: Path) -> Any:
    from src.models.transformer import TransformerBaseline

    return TransformerBaseline.load(directory)


def _taxonomy_definitions() -> dict[str, str]:
    import yaml

    path = REPO_ROOT / "config" / "taxonomy.yaml"
    taxonomy = yaml.safe_load(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, body in taxonomy["constructs"].items():
        definition = str(body.get("definition", "")).strip()
        # First sentence only. The full rubric entry runs to a paragraph, and a
        # rating sheet carrying ten paragraphs before the first item is a sheet
        # nobody reads. The full rubric lives in
        # docs/annotation_guidelines.md, which the protocol tells raters to
        # keep open beside the sheet.
        out[name] = definition.split(". ")[0].rstrip(".") + "."
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 17 explainability gate")
    parser.add_argument("--source", default="synth_precomp_v1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument(
        "--methods",
        default="ig,shap",
        help="comma-separated: ig, shap. SHAP runs on a subsample (--shap-limit).",
    )
    parser.add_argument("--limit", type=int, default=150, help="records to attribute")
    parser.add_argument("--shap-limit", type=int, default=40)
    parser.add_argument(
        "--predict-threshold",
        type=float,
        default=0.5,
        help="only attribute constructs the model scores above this",
    )
    parser.add_argument("--n-model-items", type=int, default=60)
    parser.add_argument("--rater-population", default=DEFAULT_RATER_POPULATION)
    parser.add_argument("--study-only", action="store_true")
    parser.add_argument(
        "--score-study",
        nargs="*",
        default=None,
        metavar="RATINGS.json",
        help="one JSON file per rater, mapping item_id -> yes|partly|no",
    )
    parser.add_argument("--gold", action="store_true")
    args = parser.parse_args(argv)

    if args.gold:
        print(
            "REFUSED: data/gold/ is empty (OPEN-025). Phase 17 explains a model "
            "trained against generator-planted labels on synthetic text. There is "
            "no human-verified label set to explain against, and pretending "
            "otherwise is the one error this repository refuses to make.",
            file=sys.stderr,
        )
        return 2

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- scoring returned ratings is a standalone mode ---------------------
    if args.score_study is not None:
        return _score_study(args)

    # ---- data --------------------------------------------------------------
    dataset = load_planted(args.source)
    split = template_disjoint_split(dataset.records, test_size=args.test_size, seed=args.seed)
    rng = random.Random(args.seed)
    pool = list(split.test)
    rng.shuffle(pool)
    records = pool[: args.limit]
    print(f"Explaining {len(records)} template-disjoint test records.")

    model_dir = Path(args.model_dir) if args.model_dir else _newest_transformer()
    print(f"Model: {model_dir.name}")
    baseline = _load_model(model_dir)

    def predict_fn(texts: list[str]) -> list[list[float]]:
        from src.ingestion.records import RawRecord

        stubs = [
            RawRecord(record_id=f"_p{i}", source_id=args.source, text=t, synthetic=True)
            for i, t in enumerate(texts)
        ]
        return baseline.predict_proba(stubs)

    methods = {m.strip() for m in args.methods.split(",") if m.strip()}

    ig = IntegratedGradients(
        model=baseline._model,
        tokenizer=baseline._tokenizer,
        device=baseline._device,
        max_length=baseline.hparams.max_length,
    )

    probabilities = baseline.predict_proba(records)

    # ---- attribution -------------------------------------------------------
    ig_explanations: list[RecordExplanation] = []
    shap_explanations: dict[str, RecordExplanation] = {}

    for index, record in enumerate(records):
        predicted = [
            name
            for name, p in zip(CONSTRUCTS, probabilities[index], strict=True)
            if p >= args.predict_threshold
        ]
        if not predicted:
            # Nothing was predicted, so there is no prediction to explain. Skipped
            # rather than attributed: an attribution map for a construct scored
            # 0.03 is an explanation of a non-event, it costs a full IG pass, and
            # it would pad the rating sheet with unratable items.
            continue
        if "ig" in methods:
            ig_explanations.append(
                ig.explain_record(record.record_id, record.text, CONSTRUCTS, only=predicted)
            )
        if index % 10 == 0:
            print(f"  {index}/{len(records)} attributed", flush=True)

    if "shap" in methods and ig_explanations:
        shap = ShapPartition(
            model=baseline._model,
            tokenizer=baseline._tokenizer,
            device=baseline._device,
            max_length=baseline.hparams.max_length,
        )
        subsample = ig_explanations[: args.shap_limit]
        print(f"SHAP Partition on {len(subsample)} records (subsample).")
        for number, explanation in enumerate(subsample):
            try:
                shap_explanations[explanation.record_id] = shap.explain_record(
                    explanation.record_id,
                    explanation.text,
                    CONSTRUCTS,
                    only=[e.construct for e in explanation.explanations],
                )
            except AttributionUnavailable as exc:
                print(f"SHAP unavailable, continuing with IG only: {exc}", file=sys.stderr)
                break
            if number % 5 == 0:
                print(f"  shap {number}/{len(subsample)}", flush=True)

    (REPORT_DIR / "attributions.json").write_text(
        json.dumps(
            {
                "integrated_gradients": [e.as_dict() for e in ig_explanations],
                "shap_partition": [e.as_dict() for e in shap_explanations.values()],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # ---- faithfulness ------------------------------------------------------
    faithfulness_scores = []
    for explanation in ig_explanations:
        for construct_explanation in explanation.explanations:
            score = score_record(
                record_id=explanation.record_id,
                text=explanation.text,
                construct=construct_explanation.construct,
                construct_index=CONSTRUCTS.index(construct_explanation.construct),
                method="integrated_gradients",
                tokens=construct_explanation.tokens,
                predict_fn=predict_fn,
                seed=args.seed,
            )
            if score is not None:
                faithfulness_scores.append(score)

    faithfulness = summarise(faithfulness_scores)
    (REPORT_DIR / "faithfulness.json").write_text(
        json.dumps(faithfulness, indent=2) + "\n", encoding="utf-8"
    )

    # ---- method agreement --------------------------------------------------
    agreements = []
    for explanation in ig_explanations:
        partner = shap_explanations.get(explanation.record_id)
        if partner is None:
            continue
        for construct_explanation in explanation.explanations:
            other = partner.for_construct(construct_explanation.construct)
            if other is None:
                continue
            agreements.append(
                compare_methods(
                    record_id=explanation.record_id,
                    text=explanation.text,
                    construct=construct_explanation.construct,
                    ig_tokens=construct_explanation.tokens,
                    shap_tokens=other.tokens,
                )
            )

    usable_rho = [a.spearman for a in agreements if a.spearman is not None]
    usable_jaccard = [a.top_k_jaccard for a in agreements if a.top_k_jaccard is not None]
    agreement_summary = {
        "n_compared": len(agreements),
        "n_with_defined_rho": len(usable_rho),
        "mean_spearman": (sum(usable_rho) / len(usable_rho)) if usable_rho else None,
        "mean_top5_jaccard": (sum(usable_jaccard) / len(usable_jaccard))
        if usable_jaccard
        else None,
        "per_item": [
            {
                "record_id": a.record_id,
                "construct": a.construct,
                "spearman": a.spearman,
                "top_k_jaccard": a.top_k_jaccard,
            }
            for a in agreements
        ],
    }
    (REPORT_DIR / "agreement.json").write_text(
        json.dumps(agreement_summary, indent=2) + "\n", encoding="utf-8"
    )

    # ---- cards -------------------------------------------------------------
    scorer = LinearRiskScorer()
    by_id = {r.record_id: r for r in records}
    cards = []
    for explanation in ig_explanations[:20]:
        record = by_id[explanation.record_id]
        index = records.index(record)
        risk = scorer.score(dict(zip(CONSTRUCTS, probabilities[index], strict=True)))
        cards.append(build_card(explanation=explanation, risk=risk, synthetic=record.synthetic))
    assert_publication_safe(cards)
    card_set = CardSet(tuple(cards))
    (REPORT_DIR / "cards.md").write_text(
        "# Phase 17 -- two-level explanation cards\n\n"
        "> Every card below is generated from **synthetic** text. Nothing here "
        "describes a real person.\n\n" + card_set.render(),
        encoding="utf-8",
    )

    # ---- study pack --------------------------------------------------------
    sheet = build_sheet(
        ig_explanations,
        rater_population=args.rater_population,
        construct_definitions=_taxonomy_definitions(),
        n_model_items=args.n_model_items,
        seed=args.seed,
    )
    sheet_path, key_path = sheet.write(REPORT_DIR)
    print(f"Rating sheet: {sheet_path}\nAnswer key (do NOT share): {key_path}")

    # ---- gate --------------------------------------------------------------
    structural = bool(ig_explanations) and all(
        token.is_real_span for e in ig_explanations for ce in e.explanations for token in ce.tokens
    )
    overall = faithfulness.get("overall") or {}
    beats_random = bool(overall.get("beats_random"))
    passed = structural and beats_random

    _write_report(
        args=args,
        model_dir=model_dir,
        n_records=len(records),
        n_explained=len(ig_explanations),
        faithfulness=faithfulness,
        agreement=agreement_summary,
        card_summary=card_set.summary(),
        sheet=sheet,
        structural=structural,
        beats_random=beats_random,
    )

    print(
        f"\nGate (automatable half): {'PASS' if passed else 'FAIL'}"
        f"  structural={structural} beats_random={beats_random}"
    )
    print(
        "Expert half of the gate is OUTSTANDING until ratings are returned and "
        "scored with --score-study."
    )
    return 0 if passed else 1


def _score_study(args: argparse.Namespace) -> int:
    """Analyse returned rating files against the stored answer key."""
    from src.explainability.study import RatingSheet, StudyItem

    key_path = REPORT_DIR / "rating_sheet_KEY.json"
    if not key_path.is_file():
        print(f"2:no answer key at {key_path}. Generate the sheet first.", file=sys.stderr)
        return 2
    key = json.loads(key_path.read_text(encoding="utf-8"))
    sheet = RatingSheet(
        items=tuple(
            StudyItem(
                item_id=i["item_id"],
                record_id=i["record_id"],
                construct=i["construct"],
                span_text=i["span_text"],
                context="",
                item_type=i["item_type"],
                span_start=i["span_start"],
                span_end=i["span_end"],
            )
            for i in key["items"]
        ),
        seed=key["seed"],
        rater_population=key["rater_population"],
    )

    ratings = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.score_study]
    lenient = analyse(sheet, ratings, approval=("yes", "partly"))
    strict = analyse(sheet, ratings, approval=("yes",))

    payload = {
        "lenient_yes_or_partly": lenient.as_dict(),
        "strict_yes_only": strict.as_dict(),
        "n_rating_files": len(ratings),
    }
    (REPORT_DIR / "study_result.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["lenient_yes_or_partly"], indent=2))
    if lenient.kappa is None and len(ratings) >= 2:
        print(
            "\nNOTE: kappa is undefined (a rater used a single category "
            "throughout). Report the raw agreement rate and say why.",
        )
    return 0 if lenient.passes_control else 1


def _write_report(**kwargs: Any) -> None:
    args = kwargs["args"]
    faithfulness = kwargs["faithfulness"]
    agreement = kwargs["agreement"]
    overall = faithfulness.get("overall") or {}

    def number(value: Any, digits: int = 3) -> str:
        return "n/a" if value is None else f"{value:.{digits}f}"

    lines = [
        "# Phase 17 -- Explainability & expert validation",
        "",
        "> **These are explanations of a model, not findings about athletes.**",
        "> The classifier was fine-tuned on synthetic text (`synth_precomp_v1`)",
        "> against generator-planted labels. `data/gold/` is empty (OPEN-025) and",
        "> no real athlete text exists in this corpus (OPEN-011). Nothing below is",
        "> an accuracy, and nothing below describes any real person.",
        "",
        f"- Generated: {datetime.now(UTC).date().isoformat()}",
        f"- Model: `{kwargs['model_dir'].name}`",
        f"- Python {platform.python_version()}, seed {args.seed}",
        f"- Records attributed: {kwargs['n_explained']} of {kwargs['n_records']} sampled "
        "(records where the model predicted no construct are skipped -- there is no "
        "prediction to explain)",
        "",
        "## Gate",
        "",
        f"- Span-level & construct-specific (structural): "
        f"**{'PASS' if kwargs['structural'] else 'FAIL'}**",
        f"- Attributions beat their random control (faithfulness): "
        f"**{'PASS' if kwargs['beats_random'] else 'FAIL'}**",
        "- Expert agreement reported: **OUTSTANDING** -- the rating sheet is",
        "  generated (`rating_sheet.md`); the number appears here once ratings are",
        "  returned and scored with `--score-study`.",
        "",
        "## 1. Faithfulness (does the explanation describe the model?)",
        "",
        "Comprehensiveness: delete the top-ranked words; the probability should",
        "**fall** (higher is better). Sufficiency: keep only the top-ranked words;",
        "the probability should **hold** (lower is better). Both are averaged over",
        "deletion fractions {1, 5, 10, 20, 50}%.",
        "",
        "**The margin over the random control is the number that matters.** Deleting",
        "any 20% of a sentence degrades a prediction somewhat, so a positive",
        "comprehensiveness on its own shows nothing.",
        "",
        "| metric | attribution | random control | margin |",
        "|---|---|---|---|",
        f"| comprehensiveness (higher better) | {number(overall.get('comprehensiveness'))} | "
        f"{number(overall.get('random_comprehensiveness'))} | "
        f"{number(overall.get('comprehensiveness_margin'))} |",
        f"| sufficiency (lower better) | {number(overall.get('sufficiency'))} | "
        f"{number(overall.get('random_sufficiency'))} | "
        f"{number(overall.get('sufficiency_margin'))} |",
        "",
        "### Per construct",
        "",
        "| construct | n | comprehensiveness margin | sufficiency margin | beats random |",
        "|---|---|---|---|---|",
    ]
    for name, block in sorted((faithfulness.get("constructs") or {}).items()):
        lines.append(
            f"| {name} | {block['n']} | {number(block['comprehensiveness_margin'])} | "
            f"{number(block['sufficiency_margin'])} | {'yes' if block['beats_random'] else 'NO'} |"
        )

    lines += [
        "",
        "## 2. Method agreement (IG vs SHAP Partition)",
        "",
        "Two methods derived from different principles. Agreement is evidence the",
        "explanation is a property of the model rather than of the explainer;",
        "disagreement is a reportable finding, not a bug.",
        "",
        f"- Items compared: **{agreement['n_compared']}** "
        f"(rho defined on {agreement['n_with_defined_rho']})",
        f"- Mean Spearman rho: **{number(agreement['mean_spearman'])}**",
        f"- Mean top-5 Jaccard: **{number(agreement['mean_top5_jaccard'])}**",
        "",
        "Spearman covers the whole token series and is dominated by the near-zero",
        "tail, where the methods have no reason to agree. Jaccard covers only the",
        "top-5 words -- the part a human is ever shown -- and is the more relevant",
        "of the two for this project.",
        "",
        "## 3. Two-level cards",
        "",
        f"- Cards rendered: **{kwargs['card_summary']['n']}** (`cards.md`)",
        f"- Driver rows with **no supporting span**: "
        f"{kwargs['card_summary']['n_unevidenced_driver_rows']} of "
        f"{kwargs['card_summary']['n_driver_rows']} "
        f"({kwargs['card_summary']['unevidenced_rate']:.1%})",
        "",
        "An unevidenced driver is a construct that moved the risk index while no",
        "span in the text supports it -- the model asserting something it cannot",
        "point at. It is counted rather than hidden.",
        "",
        "## 4. Expert validation study",
        "",
        f"- Rater population declared: **{kwargs['sheet'].rater_population}**",
        f"- Items on the sheet: **{len(kwargs['sheet'].items)}**",
        "- Item types are blinded: genuine model spans, length-matched **random**",
        "  spans (the floor), and **mismatched** span/construct pairs (the",
        "  attention check). The rater sees none of these labels.",
        "",
        "**Status: not yet run.** OPEN-004 is open -- no coach or sport-psychology",
        "practitioner has been recruited. The instrument is built and the rater",
        "population is fixed on the sheet itself, so whoever rates it, the claim in",
        "the paper matches the raters. If only students rate it, this is reported",
        "as a **pilot expert-review**, never as practitioner validation.",
        "",
        "## 5. Limitations",
        "",
        "1. **The model explains a template grammar.** Faithful attributions here",
        "   may be highlighting generator giveaways rather than psychological cues.",
        "   High faithfulness with low expert plausibility would be evidence of",
        "   exactly that, and it is the outcome to watch for.",
        "2. **IG attributions depend on the baseline.** A pad-token baseline is an",
        "   in-distribution 'empty' input, but a different baseline gives different",
        "   numbers. The completeness residual is reported per explanation.",
        "3. **Erasure metrics perturb syntax.** Deleting words makes text less",
        "   fluent, which moves predictions for reasons unrelated to the",
        "   explanation. The random control absorbs this, which is why the margin",
        "   and not the raw metric is reported.",
        "4. **SHAP Partition is Shapley under a hierarchy assumption**, not",
        "   unconditionally, and it ran on a subsample for cost.",
        "5. **No practitioner raters yet** (OPEN-004).",
        "",
    ]
    (REPORT_DIR / "explain.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
