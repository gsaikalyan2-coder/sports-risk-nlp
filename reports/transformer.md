# Phase 14 -- Transformer results

> **PROVISIONAL -- planted-label measurement, NOT model accuracy**

This page reports how much of the `synth_precomp_v1` template grammar a
fine-tuned transformer recovers against `generation_spec.planted_constructs`.
It does **not** report accuracy, and none of these numbers may be described
as the model's ability to detect psychological constructs in athlete text.
`data/gold/` is empty (OPEN-025): no human-verified evaluation set exists,
so no accuracy claim is available to this project yet.

Belongs in the paper's dataset / methodology section. Never the results table.

- Generated: 2026-08-11
- Base model: `distilroberta-base`
- torch 2.13.0+cpu, transformers 5.15.0, Python 3.11.9, seed 42
- Configurations evaluated: 6

## Gate

**PASSED** -- transformer 0.588 vs lexicon 0.462 on the template-disjoint split (delta +0.126, paired bootstrap p=0.000).

### What that result means, and what it does not

The transformer recovers more of the planted template grammar than the lexicon baseline does, across held-out templates, and the gap survives a paired bootstrap. This is a **corpus property**: it says the near-synonym substitution layer produced realisations varied enough that a pretrained encoder generalises across them, where a bag-of-ngrams model could not. It is **not** evidence that the model detects psychological constructs in athlete text -- no athlete wrote this text and no human verified these labels (OPEN-025). The gate is satisfied for the purposes of PROJECT_PLAN.md Phase 14; the publication-readiness criterion in CLAUDE.md sec.9 is not, and cannot be, until a real gold set exists.

## Headline table

| configuration                                | disjoint macro-F1 [95% CI]   | random   |     gap |
|----------------------------------------------|------------------------------|----------|---------|
| distilroberta-base_lr1e-05_bs16_ep4_len128_c749741c | 0.504 [0.466, 0.537]         | n/a      |     n/a |
| distilroberta-base_lr2e-05_bs16_ep4_len128_716e3861 | 0.558 [0.525, 0.590]         | n/a      |     n/a |
| distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf | 0.588 [0.549, 0.624]         | 0.905    |  +0.317 |
| distilroberta-base_lr2e-05_bs8_ep4_len128_9dbf43fa | 0.546 [0.496, 0.586]         | n/a      |     n/a |
| distilroberta-base_lr3e-05_bs16_ep4_len128_b3ed1b20 | 0.582 [0.546, 0.615]         | n/a      |     n/a |
| distilroberta-base_lr5e-05_bs16_ep4_len128_1f51d54d | 0.500 [0.460, 0.537]         | n/a      |     n/a |

The `random` column is included **only** so the gap can be read. On the
random split 149 templates appear on both sides, and TF-IDF+LinearSVC
already scores 1.000 there (Phase 13). A high random-split number measures
template memorisation and must never be quoted alone -- that is OPEN-012.

## Against the Phase 13 bar (template-disjoint, planted labels)

| system | macro-F1 |
|---|---|
| lexicon | 0.462 |
| tfidf_logreg | 0.222 |
| memorisation_probe | 0.197 |
| tfidf_linearsvc | 0.181 |
| stratified_random | 0.104 |
| majority | 0.000 |
| **transformer (distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf)** | **0.588** |

## How much of this is the tuned thresholds?

The same fitted models, re-scored with every threshold fixed at 0.5 instead
of tuned on the validation slice. The per-construct thresholds are 10 free
parameters; this column says how much of the headline number they are
responsible for. A large `delta` means the result leans on tuning done over
a few hundred validation records rather than on the encoder.

| configuration | tuned | untuned (0.5) | delta |
|---|---|---|---|
| distilroberta-base_lr1e-05_bs16_ep4_len128_c749741c | 0.504 | 0.518 | -0.014 |
| distilroberta-base_lr2e-05_bs16_ep4_len128_716e3861 | 0.558 | 0.602 | -0.044 |
| distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf | 0.588 | 0.616 | -0.028 |
| distilroberta-base_lr2e-05_bs8_ep4_len128_9dbf43fa | 0.546 | 0.593 | -0.047 |
| distilroberta-base_lr3e-05_bs16_ep4_len128_b3ed1b20 | 0.582 | 0.639 | -0.058 |
| distilroberta-base_lr5e-05_bs16_ep4_len128_1f51d54d | 0.500 | 0.613 | -0.112 |

## Per-construct F1 (template-disjoint, best configuration)

| construct | precision | recall | F1 | support |
|---|---|---|---|---|
| appraisal_orientation | 0.320 | 1.000 | 0.484 | 39 |
| attentional_focus | 0.187 | 0.958 | 0.313 | 24 |
| burnout_signal | 0.433 | 0.470 | 0.451 | 83 |
| cognitive_anxiety | 1.000 | 0.227 | 0.370 | 22 |
| coping_style | 0.818 | 0.863 | 0.840 | 73 |
| motivation_orientation | 0.865 | 0.727 | 0.790 | 44 |
| perceived_stress | 0.571 | 1.000 | 0.727 | 44 |
| resilience | 0.382 | 0.464 | 0.419 | 28 |
| self_confidence | 0.977 | 0.832 | 0.898 | 101 |
| somatic_anxiety | 0.412 | 1.000 | 0.583 | 28 |

## Limitations that apply to every number above

1. **The labels were planted, not observed.** They record what the generator
   was told to write, not what a human judged the text to express.
2. **The text is synthetic.** No athlete wrote it. Domain shift from template
   English to real pre-competition speech is unmeasured and is expected to be
   large (OPEN-011).
3. **Thresholds were tuned on a validation slice of ~15% of training records.**
   For the rarest constructs that is a few hundred examples, which is thin.
4. **The sweep selected a configuration on this test split.** With a handful of
   configurations the selection bias is small but it is not zero, and the
   reported best is therefore mildly optimistic.

## How to make these numbers real

1. Recruit a second annotator and populate `data/gold/` (OPEN-025).
2. Acquire real pre-competition athlete text (OPEN-011) -- the project's
   highest live risk, because contribution #1 depends on it.
3. Re-run `python scripts/run_transformer.py --gold`. The harness changes an
   input path and nothing else; the numbers it then prints are accuracies
   and this warning can be deleted.
