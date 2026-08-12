# Phase 15 -- Risk scoring and calibration

> **PROVISIONAL -- planted-label measurement, NOT model accuracy**
>
> **RANKING ONLY -- the fused risk index is not calibrated and is not a probability. No risk outcome exists to calibrate it against.**

This page reports two different things and the difference is the point.

1. **Per-construct calibration** -- real, computed below. The construct
   probabilities are calibrated against the planted construct labels, so the
   ECE is a corpus property (OPEN-025), not a statement about athletes.
2. **Risk-index calibration** -- *not computed, because it cannot be.* It needs
   an observed risk outcome per record and none exists: no administered CSAI-2,
   no clinician rating, no linked competition outcome. `calibrate_risk_index`
   raises rather than substituting a proxy, because the obvious proxy
   ("risk = 1 if any risk-raising construct was planted") is a restatement of
   the fusion's own inputs and would produce a good ECE that means nothing.

- Generated: 2026-08-11
- Probability source: Phase 13 TF-IDF + logistic regression (interim source; macro-F1 0.222)
- Python 3.10.12, seed 42
- Split: template-disjoint, 1828 train / 286 val / 443 test

## Gate

**PASSED**

| condition | result |
|---|---|
| ECE reported | yes (pooled raw 0.0505 -> scaled 0.0219) |
| decomposition human-readable | yes |
| context interface non-breaking | yes |

## Calibration by construct

Temperature is fitted on the **validation** slice and evaluated on **test**.
T > 1 softens over-confident probabilities, T < 1 sharpens under-confident ones.

| construct | T | ECE raw | ECE scaled | improved | test support |
|---|---|---|---|---|---|
| appraisal_orientation | 0.52 | 0.1149 | 0.0243 | yes | 39 |
| attentional_focus | 0.73 | 0.1301 | 0.0929 | yes | 24 |
| burnout_signal | 0.87 | 0.0815 | 0.0705 | yes | 83 |
| cognitive_anxiety | 0.26 | 0.1576 | 0.0639 | yes | 22 |
| coping_style | 0.76 | 0.0536 | 0.0761 | no | 73 |
| motivation_orientation | 0.80 | 0.0913 | 0.0544 | yes | 44 |
| perceived_stress | 0.68 | 0.1069 | 0.0713 | yes | 44 |
| resilience | 1.44 | 0.0203 | 0.0891 | no | 28 |
| self_confidence | 0.35 | 0.0849 | 0.2011 | no | 101 |
| somatic_anxiety | 0.92 | 0.0787 | 0.0621 | yes | 28 |

⚠ = the temperature search hit its bound; read that row as "outside the searched range" rather than as a fit.

**Pooled:** ECE 0.0505 -> 0.0219, MCE 0.2627 -> 0.4159, n=4430.

## Reliability (pooled, after scaling)

| bin | n | mean confidence | observed frequency | gap |
|---|---|---|---|---|
| [0.0, 0.1) | 2820 | 0.036 | 0.049 | -0.014 |
| [0.1, 0.2) | 924 | 0.140 | 0.123 | +0.017 |
| [0.2, 0.3) | 301 | 0.244 | 0.272 | -0.028 |
| [0.3, 0.4) | 155 | 0.342 | 0.329 | +0.012 |
| [0.4, 0.5) | 89 | 0.448 | 0.427 | +0.021 |
| [0.5, 0.6) | 57 | 0.543 | 0.386 | +0.157 |
| [0.6, 0.7) | 39 | 0.654 | 0.333 | +0.320 |
| [0.7, 0.8) | 24 | 0.740 | 0.625 | +0.115 |
| [0.8, 0.9) | 14 | 0.844 | 0.429 | +0.416 |
| [0.9, 1.0) | 7 | 0.935 | 0.857 | +0.078 |

## Worked examples (gate condition 2)

```
"Put it this way, the thought of coming up short has been sitting with me all fortnight — for what it's worth. I would rather turn up nervous than turn up numb."

Risk index 0.85  (RANKING ONLY -- not calibrated)
  Research artifact. Constructs inferred from text by a classifier trained on synthetic data against planted labels; no human-verified labels exist (OPEN-025) and no real athlete text has been used (OPEN-011). Not a clinical instrument and not a judgement about any real person.
  - cognitive_anxiety: detected (p=0.44), raised the score by 0.65
  - perceived_stress: detected (p=0.59), raised the score by 0.59
  - somatic_anxiety: detected (p=0.28), raised the score by 0.28
  - burnout_signal: detected (p=0.16), raised the score by 0.25
  (4 construct(s) detected but directionally unresolved, so excluded: appraisal_orientation, attentional_focus, coping_style, motivation_orientation)
```

```
"The start is scheduled for the evening session. Honestly, this is a demand I have the tools for and I aim it — that's just where I am."

Risk index 0.64  (RANKING ONLY -- not calibrated)
  Research artifact. Constructs inferred from text by a classifier trained on synthetic data against planted labels; no human-verified labels exist (OPEN-025) and no real athlete text has been used (OPEN-011). Not a clinical instrument and not a judgement about any real person.
  - perceived_stress: detected (p=0.25), raised the score by 0.25
  - burnout_signal: detected (p=0.15), raised the score by 0.22
  - cognitive_anxiety: detected (p=0.13), raised the score by 0.19
  - self_confidence: detected (p=0.10), lowered the score by 0.10
  (4 construct(s) detected but directionally unresolved, so excluded: appraisal_orientation, attentional_focus, coping_style, motivation_orientation)
```

```
"If I'm honest, I expect to win this and I have expected it for weeks — that's about the size of it."

Risk index 0.41  (RANKING ONLY -- not calibrated)
  Research artifact. Constructs inferred from text by a classifier trained on synthetic data against planted labels; no human-verified labels exist (OPEN-025) and no real athlete text has been used (OPEN-011). Not a clinical instrument and not a judgement about any real person.
  - self_confidence: detected (p=0.73), lowered the score by 0.73
  - burnout_signal: detected (p=0.13), raised the score by 0.19
  - perceived_stress: detected (p=0.14), raised the score by 0.14
  - resilience: detected (p=0.12), lowered the score by 0.12
  (4 construct(s) detected but directionally unresolved, so excluded: appraisal_orientation, attentional_focus, coping_style, motivation_orientation)
```

## Sensitivity to unfittable choices

The magnitudes and the polarity policy are set by judgement, not fitted --
there is no risk target to fit them against. This table says how much the
index depends on them. A conclusion that survives only at one setting is a
conclusion about the setting.

| variant | Spearman vs default | mean index | mean absolute shift |
|---|---|---|---|
| polarity_optimistic | 0.664 | 0.482 | 0.157 |
| polarity_pessimistic | 0.830 | 0.767 | 0.127 |
| uniform_magnitudes | 0.979 | 0.600 | 0.040 |

## Limitations

1. **The risk index is a ranking, not a probability.** Nothing here licenses
   reading 0.7 as "70% of such athletes".
2. **The probability source is weak.** The interim TF-IDF model scores 0.222
   macro-F1 template-disjoint; calibrating a weakly-informative probability
   makes it honest, not accurate.
3. **The calibration target is planted labels** on synthetic text (OPEN-025,
   OPEN-011).
4. **The fusion is declared, not learned** -- signs come from
   `config/taxonomy.yaml`'s `risk_direction`, magnitudes are coarse tiers.
5. **Polarity-bearing constructs contribute nothing by default**, because the
   presence classifier emits no sub-label. See the sensitivity table for how
   much that matters.

## What would make the risk index calibratable

Administered CSAI-2 scores alongside pre-competition text, or outcome-linked
data. That is the "Outcome-linkage validation" expansion in `CLAUDE.md`
sec.10, and it is the single acquisition that would turn the risk index from a
ranking into a measurement.
