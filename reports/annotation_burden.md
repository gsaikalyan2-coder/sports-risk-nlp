# Annotation burden -- gold_dev

**ESTIMATE, NOT A MEASUREMENT.** UNMEASURED ASSUMPTION (OPEN-026). Numbers chosen to be plausible for a 9-token median utterance read in its parent-record context; no human has been timed. Replace with TimingModel.from_measurement() after the gold_dev calibration pass.

100 items x 1 annotator(s) x 10 constructs.

- **1.82 min/item**
- **3.03 h per annotator**
- **3.03 person-hours** for the batch
- recommended sittings per annotator: **2** (at 2.0 h each)

> The batch exceeds 2.0 h per annotator in one pass. Split it. OPEN-026: a rushed second half produces a worse dataset than a careful smaller one, and the damage does **not** show up in the kappa -- two tired annotators drift toward the same defaults and agree *more*.

## Marginal cost per construct

What *disappears from the batch* if the construct is dropped. The span pass and the context read are shared and do not disappear, so they are not charged here -- overstating what a drop saves is how a taxonomy gets trimmed for no gain.

| construct | marginal s/item | marginal h (batch, all annotators) | share |
|---|---|---|---|
| cognitive_anxiety | 6.0 | 0.17 | 5.5% |
| somatic_anxiety | 6.0 | 0.17 | 5.5% |
| self_confidence | 6.0 | 0.17 | 5.5% |
| motivation_orientation | 6.0 | 0.17 | 5.5% |
| perceived_stress | 6.0 | 0.17 | 5.5% |
| attentional_focus | 6.0 | 0.17 | 5.5% |
| burnout_signal | 6.0 | 0.17 | 5.5% |
| coping_style | 6.0 | 0.17 | 5.5% |
| resilience | 6.0 | 0.17 | 5.5% |
| appraisal_orientation | 6.0 | 0.17 | 5.5% |

Read this beside `reports/agreement_*.md`. A construct with poor kappa **and** high marginal cost is a drop candidate; the same poor kappa on a cheap construct is an argument for fixing the rubric, not for shrinking the taxonomy.

---

# Annotation burden -- gold_eval

**ESTIMATE, NOT A MEASUREMENT.** UNMEASURED ASSUMPTION (OPEN-026). Numbers chosen to be plausible for a 9-token median utterance read in its parent-record context; no human has been timed. Replace with TimingModel.from_measurement() after the gold_dev calibration pass.

400 items x 1 annotator(s) x 10 constructs.

- **1.82 min/item**
- **12.11 h per annotator**
- **12.11 person-hours** for the batch
- recommended sittings per annotator: **7** (at 2.0 h each)

> The batch exceeds 2.0 h per annotator in one pass. Split it. OPEN-026: a rushed second half produces a worse dataset than a careful smaller one, and the damage does **not** show up in the kappa -- two tired annotators drift toward the same defaults and agree *more*.

## Marginal cost per construct

What *disappears from the batch* if the construct is dropped. The span pass and the context read are shared and do not disappear, so they are not charged here -- overstating what a drop saves is how a taxonomy gets trimmed for no gain.

| construct | marginal s/item | marginal h (batch, all annotators) | share |
|---|---|---|---|
| cognitive_anxiety | 6.0 | 0.67 | 5.5% |
| somatic_anxiety | 6.0 | 0.67 | 5.5% |
| self_confidence | 6.0 | 0.67 | 5.5% |
| motivation_orientation | 6.0 | 0.67 | 5.5% |
| perceived_stress | 6.0 | 0.67 | 5.5% |
| attentional_focus | 6.0 | 0.67 | 5.5% |
| burnout_signal | 6.0 | 0.67 | 5.5% |
| coping_style | 6.0 | 0.67 | 5.5% |
| resilience | 6.0 | 0.67 | 5.5% |
| appraisal_orientation | 6.0 | 0.67 | 5.5% |

Read this beside `reports/agreement_*.md`. A construct with poor kappa **and** high marginal cost is a drop candidate; the same poor kappa on a cheap construct is an argument for fixing the rubric, not for shrinking the taxonomy.
