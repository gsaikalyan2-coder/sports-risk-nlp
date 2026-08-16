# Phase 18 -- Evaluation harness, ablations, and results

> **No number in this file is an accuracy.** `data/gold/` is empty (OPEN-025),
> so every score is agreement with `generation_spec.planted_constructs` --
> labels this project's generator planted in synthetic text (OPEN-011). What is
> measured is how learnable the template grammar `synth_precomp_v1` is. Nothing
> here describes any real person, and nothing here is evidence that the model
> detects psychological constructs in athlete language.

- Generated: 2026-08-16
- Python 3.11.9, seed 42, 1000 bootstrap resamples
- Checkpoint: `phase14_transformer_distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf`

## Gate

The Phase 18 gate is *"every claim the paper will make is backed by a logged
experiment"*. That is only checkable if the claims are enumerated somewhere a
program can read, so they are: `src/evaluation/ablations.py::CLAIMS`. Each row
below names a claim and the key in `results.json` that backs it.

| claim | evidence key | backed |
|---|---|---|
| `transformer_beats_lexicon` | `comparisons.transformer_vs_lexicon` | yes |
| `memorisation_gap` | `comparisons.split_gap` | yes |
| `per_construct_spread` | `scores` | yes |
| `silver_is_noise` | `ablations.silver_classical` | yes |
| `fusion_is_structural` | `ablations.risk_fusion` | yes |
| `explanations_beat_random` | `explainability.faithfulness` | yes |
| `not_accuracy` | `provenance` | yes |

## 1. Results by system

macro-F1 with a 95% bootstrap interval. **A point estimate without an interval
is not a result** -- at this test-set size the interval is wide enough that
several of these systems do not separate.

| split | system | n | macro-F1 [95% CI] | micro-F1 | subset acc. | constructs at F1=0 |
|---|---|---|---|---|---|---|
| random | lexicon | 778 | 0.562 [0.535, 0.585] | 0.587 | 0.253 | 0 |
| random | majority | 778 | 0.000 [0.000, 0.000] | 0.000 | 0.057 | 10 (appraisal_orientation, attentional_focus, burnout_signal, cognitive_anxiety, coping_style, motivation_orientation, perceived_stress, resilience, self_confidence, somatic_anxiety) |
| random | tfidf_logreg | 778 | 0.999 [0.998, 1.000] | 1.000 | 0.999 | 0 |
| random | transformer | 778 | 0.822 [0.805, 0.837] | 0.827 | 0.566 | 0 |
| template_disjoint | lexicon | 443 | 0.462 [0.431, 0.492] | 0.533 | 0.352 | 2 (cognitive_anxiety, resilience) |
| template_disjoint | majority | 443 | 0.000 [0.000, 0.000] | 0.000 | 0.099 | 10 (appraisal_orientation, attentional_focus, burnout_signal, cognitive_anxiety, coping_style, motivation_orientation, perceived_stress, resilience, self_confidence, somatic_anxiety) |
| template_disjoint | tfidf_logreg | 443 | 0.222 [0.181, 0.258] | 0.228 | 0.167 | 1 (resilience) |
| template_disjoint | transformer | 443 | 0.588 [0.546, 0.622] | 0.614 | 0.339 | 0 |

### Per-construct, transformer, template-disjoint split

The spread is the interesting part. A single macro-F1 averages over a model
that is competent on some constructs and blind on others, and the ten rows
below are what a reviewer will actually ask for.

| construct | P | R | F1 | support |
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

## 2. Comparisons

| comparison | delta | p | verdict |
|---|---|---|---|
| transformer_vs_lexicon (transformer vs lexicon) | +0.126 | 0.000 | A beats B |
| split_gap (transformer (random split) vs transformer (template-disjoint)) | +0.234 | nan | memorisation gap (not a paired test -- different test sets) |

## 3. Ablations

### silver_classical -- MEASURED

*Does adding silver-labelled data help a classical model?*

3625 silver rows added to training only; any row realising a held-out template was dropped, so the template-disjoint split is preserved. macro-F1 0.222 -> 0.255 (delta +0.033, p=0.107): no significant change in either direction. That is the measured evidence for OPEN-028: several thousand additional training rows bought nothing, because their labels are `rng.randrange` output keyed on a prompt hash.

### silver_transformer -- REFUSED

*Does adding the silver-labelled utterances to transformer training help?*

OPEN-028: every silver label is `rng.randrange` output from the offline stub (OPEN-008, no live OpenRouter call has ever been made). The experiment would measure the effect of adding uniform noise to the training set, which is known by construction, at a cost of roughly ten CPU-hours across the two arms. The cheap classical arm (`silver_classical`) demonstrates the collapse instead. This ablation becomes worth running the day a real labelling run exists; until then its result would be a fact about `random`, not about weak supervision.

### risk_fusion -- MEASURED

*What does the construct->risk fusion layer contribute?*

Reframed as a structural sensitivity analysis. No observed risk outcome exists, so an accuracy-style +/- fusion comparison is impossible and a proxy target derived from planted labels would be circular (Phase 15). rho=0.100 against a plain count of detected constructs -- the taxonomy directions and magnitudes materially change the ordering.

#### Risk-layer sensitivity, in numbers

- Records scored: **443**
- Constructs that never moved the index: **4** of 10 (appraisal_orientation, attentional_focus, coping_style, motivation_orientation) -- these are polarity-bearing constructs left inert by the conservative `PolarityPolicy.NEUTRAL` default. The risk decomposition is therefore narrower than the taxonomy suggests.
- Rank correlation with a plain count of detected constructs: **0.100**
- Rank correlation under +/-0.05 probability noise: **0.989**
- Rank correlation with the NEUTRAL polarity default: PESSIMISTIC 0.839, OPTIMISTIC 0.855
- Mean index shift under an alternative polarity policy: PESSIMISTIC 0.152, OPTIMISTIC 0.174

## 4. Error analysis

**Structural only, with no example sentences.** `docs/ethics.md` binds this
project to publish no verbatim corpus text, so errors are characterised by
construct, by confusion pair and by how many constructs a record carries --
not by quoting records. That is a real cost to persuasiveness, paid on
purpose.

| construct | false positives | false negatives |
|---|---|---|
| appraisal_orientation | 83 | 0 |
| attentional_focus | 100 | 1 |
| burnout_signal | 51 | 44 |
| cognitive_anxiety | 0 | 17 |
| coping_style | 14 | 10 |
| motivation_orientation | 5 | 12 |
| perceived_stress | 33 | 0 |
| resilience | 21 | 15 |
| self_confidence | 2 | 17 |
| somatic_anxiety | 40 | 0 |

Most frequent construct swaps (missed X, invented Y on the same record):

- `burnout_signal->somatic_anxiety` x29
- `burnout_signal->perceived_stress` x20
- `coping_style->attentional_focus` x10
- `motivation_orientation->appraisal_orientation` x10
- `burnout_signal->appraisal_orientation` x9
- `self_confidence->burnout_signal` x8
- `resilience->burnout_signal` x7
- `cognitive_anxiety->burnout_signal` x7

Error rate by how many constructs a record carries:

- 0 constructs: 0/44 records have at least one error
- 1 construct: 217/318 records have at least one error
- 2 constructs: 70/75 records have at least one error
- 3+ constructs: 6/6 records have at least one error

## 5. Figures

- `reports\figures\phase18_macro_f1_by_system.svg`
- `reports\figures\phase18_per_construct_f1.svg`
- `reports\figures\phase18_memorisation_gap.svg`
- `reports\figures\phase18_risk_contribution_share.svg`

## 6. What this phase does not establish

- **Not accuracy.** No human has verified a single label in this evaluation set.
- **Not generalisation to athlete language.** No athlete wrote any of this text.
- **Not a validated risk index.** No observed risk outcome exists, so the fusion
  layer is characterised structurally and never scored for correctness.
- **Not a weak-supervision result.** The silver ablation measures the effect of
  adding PRNG output, because that is what the silver set currently is (OPEN-028).

**PROVISIONAL -- planted-label corpus-property measurement, NOT accuracy. data/gold/ is empty (OPEN-025); no real athlete text exists (OPEN-011).**
