# Phase 13 -- Baseline results

> **PROVISIONAL -- planted-label measurement, NOT model accuracy**

These figures measure how learnable the `synth_precomp_v1` template grammar
is against `generation_spec.planted_constructs`. They do **not** measure how
well a model detects psychological constructs in athlete text, and none of
them is an accuracy. `data/gold/` is empty (OPEN-025), so no human-verified
evaluation set exists and no accuracy claim is available to this project yet.

Belongs in the paper's dataset / methodology section. Never the results table.

- Generated: 2026-08-11
- Label source: `planted` (unit: record)
- Python 3.10.12, scikit-learn 1.7.2, seed 42
- Dataset: 3888 examples (deduplicated from 4000; 112 duplicate texts collapsed, 0 ambiguous dropped)

## Headline: template-disjoint split

The template-disjoint split is the honest one. The random split is shown only
as a contrast; the gap between them is the memorisation story and is itself a
paper result (OPEN-012).

| system                 | disjoint macro-F1 [95% CI]   | random macro-F1  |     gap |
|------------------------|------------------------------|------------------|---------|
| majority               | 0.000 [0.000, 0.000]         | 0.000            |  +0.000 |
| stratified_random      | 0.104 [0.082, 0.126]         | 0.175            |  +0.071 |
| memorisation_probe     | 0.197 [0.162, 0.228]         | 0.720            |  +0.523 |
| lexicon                | 0.462 [0.432, 0.494]         | 0.562            |  +0.100 |
| tfidf_logreg           | 0.222 [0.181, 0.259]         | 0.999            |  +0.777 |
| tfidf_linearsvc        | 0.181 [0.150, 0.212]         | 1.000            |  +0.819 |

Best system on the honest split: **lexicon** at 0.462 macro-F1.

## Split diagnostics

### template_disjoint

- train / test / discarded: 2591 / 443 / 854
- templates on both sides: 0
- exact test texts seen in train: 0.0%
- n-gram overlap: 4-gram 40.0%, 6-gram 25.1%, 8-gram 13.9%

### random

- train / test / discarded: 3110 / 778 / 0
- templates on both sides: 149
- exact test texts seen in train: 0.0%
- n-gram overlap: 4-gram 94.6%, 6-gram 84.7%, 8-gram 71.2%

## Per-construct F1 (template-disjoint)

| construct | majority | stratified_random | memorisation_probe | lexicon | tfidf_logreg | tfidf_linearsvc | support |
|---|---|---|---|---|---|---|---|
| appraisal_orientation | 0.000 | 0.073 | 0.303 | 0.656 | 0.645 | 0.471 | 39 |
| attentional_focus | 0.000 | 0.095 | 0.055 | 0.068 | 0.048 | 0.049 | 24 |
| burnout_signal | 0.000 | 0.189 | 0.142 | 0.533 | 0.047 | 0.000 | 83 |
| cognitive_anxiety | 0.000 | 0.062 | 0.240 | 0.000 | 0.138 | 0.000 | 22 |
| coping_style | 0.000 | 0.115 | 0.146 | 0.731 | 0.176 | 0.194 | 73 |
| motivation_orientation | 0.000 | 0.093 | 0.253 | 0.571 | 0.615 | 0.625 | 44 |
| perceived_stress | 0.000 | 0.144 | 0.327 | 0.542 | 0.259 | 0.268 | 44 |
| resilience | 0.000 | 0.049 | 0.000 | 0.000 | 0.000 | 0.000 | 28 |
| self_confidence | 0.000 | 0.126 | 0.289 | 0.534 | 0.100 | 0.139 | 101 |
| somatic_anxiety | 0.000 | 0.093 | 0.219 | 0.982 | 0.194 | 0.069 | 28 |

## How to make these numbers real

1. Recruit a second annotator and populate `data/gold/` (OPEN-025).
2. Re-run `python scripts/run_baselines.py --gold`. The harness changes an
   input path and nothing else; the numbers it then prints are accuracies
   and this warning can be deleted.

Until then `--gold` refuses rather than falling back to silver, because
silver is PRNG output (OPEN-028) and a silent fallback would relabel a
chance-agreement score as accuracy.
