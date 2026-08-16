# Phase 17 -- Explainability & expert validation

> **These are explanations of a model, not findings about athletes.**
> The classifier was fine-tuned on synthetic text (`synth_precomp_v1`)
> against generator-planted labels. `data/gold/` is empty (OPEN-025) and
> no real athlete text exists in this corpus (OPEN-011). Nothing below is
> an accuracy, and nothing below describes any real person.

- Generated: 2026-08-12
- Model: `phase14_transformer_distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf`
- Python 3.11.9, seed 42
- Records attributed: 129 of 150 sampled (records where the model predicted no construct are skipped -- there is no prediction to explain)

## Gate

- Span-level & construct-specific (structural): **PASS**
- Attributions beat their random control (faithfulness): **PASS**
- Expert agreement reported: **OUTSTANDING** -- the rating sheet is
  generated (`rating_sheet.md`); the number appears here once ratings are
  returned and scored with `--score-study`.

## 1. Faithfulness (does the explanation describe the model?)

Comprehensiveness: delete the top-ranked words; the probability should
**fall** (higher is better). Sufficiency: keep only the top-ranked words;
the probability should **hold** (lower is better). Both are averaged over
deletion fractions {1, 5, 10, 20, 50}%.

**The margin over the random control is the number that matters.** Deleting
any 20% of a sentence degrades a prediction somewhat, so a positive
comprehensiveness on its own shows nothing.

| metric | attribution | random control | margin |
|---|---|---|---|
| comprehensiveness (higher better) | 0.500 | 0.172 | 0.328 |
| sufficiency (lower better) | 0.535 | 0.705 | 0.170 |

### Per construct

| construct | n | comprehensiveness margin | sufficiency margin | beats random |
|---|---|---|---|---|
| appraisal_orientation | 32 | 0.274 | 0.137 | yes |
| attentional_focus | 29 | 0.264 | 0.119 | yes |
| burnout_signal | 11 | 0.239 | 0.157 | yes |
| cognitive_anxiety | 9 | 0.371 | 0.133 | yes |
| coping_style | 16 | 0.291 | 0.140 | yes |
| motivation_orientation | 26 | 0.244 | 0.118 | yes |
| perceived_stress | 28 | 0.402 | 0.168 | yes |
| resilience | 9 | 0.363 | 0.183 | yes |
| self_confidence | 30 | 0.383 | 0.193 | yes |
| somatic_anxiety | 21 | 0.471 | 0.366 | yes |

## 2. Method agreement (IG vs SHAP Partition)

Two methods derived from different principles. Agreement is evidence the
explanation is a property of the model rather than of the explainer;
disagreement is a reportable finding, not a bug.

- Items compared: **72** (rho defined on 72)
- Mean Spearman rho: **0.458**
- Mean top-5 Jaccard: **0.384**

Spearman covers the whole token series and is dominated by the near-zero
tail, where the methods have no reason to agree. Jaccard covers only the
top-5 words -- the part a human is ever shown -- and is the more relevant
of the two for this project.

## 3. Two-level cards

- Cards rendered: **20** (`cards.md`)
- Driver rows with **no supporting span**: 104 of 120 (86.7%)

An unevidenced driver is a construct that moved the risk index while no
span in the text supports it -- the model asserting something it cannot
point at. It is counted rather than hidden.

## 4. Expert validation study

- Rater population declared: **sports-familiar student raters (pilot expert-review; NOT coaches or sport-psychology practitioners -- see OPEN-004)**
- Items on the sheet: **84**
- Item types are blinded: genuine model spans, length-matched **random**
  spans (the floor), and **mismatched** span/construct pairs (the
  attention check). The rater sees none of these labels.

**Status: not yet run.** OPEN-004 is open -- no coach or sport-psychology
practitioner has been recruited. The instrument is built and the rater
population is fixed on the sheet itself, so whoever rates it, the claim in
the paper matches the raters. If only students rate it, this is reported
as a **pilot expert-review**, never as practitioner validation.

## 5. Limitations

1. **The model explains a template grammar.** Faithful attributions here
   may be highlighting generator giveaways rather than psychological cues.
   High faithfulness with low expert plausibility would be evidence of
   exactly that, and it is the outcome to watch for.
2. **IG attributions depend on the baseline.** A pad-token baseline is an
   in-distribution 'empty' input, but a different baseline gives different
   numbers. The completeness residual is reported per explanation.
3. **Erasure metrics perturb syntax.** Deleting words makes text less
   fluent, which moves predictions for reasons unrelated to the
   explanation. The random control absorbs this, which is why the margin
   and not the raw metric is reported.
4. **SHAP Partition is Shapley under a hierarchy assumption**, not
   unconditionally, and it ran on a subsample for cost.
5. **No practitioner raters yet** (OPEN-004).
