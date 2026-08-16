# docs/findings.md — Phase 19: what the evidence supports

> **Read this first.** `data/gold/` is empty (OPEN-025) and no athlete wrote any
> text in this corpus (OPEN-011). Every score below is agreement with
> `generation_spec.planted_constructs` — labels this project's own generator
> planted in synthetic text. **No number in this document is an accuracy**, and
> nothing here is evidence that the model detects psychological constructs in
> real athlete language. What is measured throughout is how learnable the
> template grammar `synth_precomp_v1` is, and how the system behaves on it.

- Written: 2026-08-16, end of Phase 19
- Evidence base: `reports/results.{md,json}` (real checkpoint,
  `phase14_transformer_distilroberta-base_lr2e-05_bs16_ep6_len128_1a551fdf`),
  `reports/explain/explain.md`, `reports/baselines.md`, `reports/calibration.md`
- Claim ledger: `src/evaluation/ablations.py::CLAIMS` — 7 claims, all backed
- Python 3.11.9, seed 42, 1000 bootstrap resamples

---

## 0. The contribution statement

> We build a construct-grounded pipeline that detects ten validated
> sports-psychology constructs in pre-competition text and fuses them into an
> interpretable risk index with two-level explanations (span→construct,
> construct→risk). Because no public pre-competition athlete corpus exists, we
> build and release a synthetic construct-grounded corpus and evaluate on it
> honestly: we report a template-disjoint split alongside a random split and
> show that the random split overstates generalisation by **+0.234 macro-F1**,
> a result about evaluating synthetic corpora that transfers beyond this
> domain. Our explanations are **more faithful to the model than a random-span
> control by a +0.328 comprehensiveness margin**, validated by a pilot expert
> review. We report three negative results — weak supervision bought nothing,
> the risk index cannot be calibrated because no observed outcome exists, and
> four of ten constructs are inert in the fusion layer — as results rather than
> omissions.

Every clause of that paragraph maps to a row in `CLAIMS`. Nothing in the paper
may go beyond it without a new row being added **first**.

---

## 1. Headline finding 1 — the memorisation gap

**The strongest and most transferable thing this project measured.**

| system | random split | template-disjoint | gap |
|---|---|---|---|
| TF-IDF + LogReg | 0.999 [0.998, 1.000] | 0.222 [0.181, 0.258] | **+0.777** |
| transformer | 0.822 [0.805, 0.837] | 0.588 [0.546, 0.622] | **+0.234** |
| lexicon | 0.562 [0.535, 0.585] | 0.462 [0.431, 0.492] | +0.100 |

A linear model over TF-IDF scores **0.999 macro-F1 and 0.999 subset accuracy**
on a random split of this corpus, and **0.222** once the evaluation templates
are held out. It is not learning constructs; it is learning which template
generated which record. On a random split, near-identical realisations of the
same template appear in both train and test, so the task collapses to string
lookup.

The transformer's own gap is +0.234 — smaller, but the same effect. It is not
immune, only less exposed.

**Why this belongs in the paper as a result, not a methods footnote.** Synthetic
and template-augmented corpora are increasingly common in low-resource NLP, and
the default evaluation protocol for them is a random split. This measurement
says that protocol can inflate a headline number by up to 0.78 macro-F1 on a
corpus that looks perfectly reasonable. The lexicon's much smaller gap (+0.100)
is the control that makes the point: a model with no capacity to memorise
barely moves between splits, so the gap is a property of the *learner meeting
the corpus*, not of the split being harder.

**The honest caveat.** The gap magnitude is a property of `synth_precomp_v1`'s
duplication structure. Phase 9b cut utterance duplication from 87.4% to 37.6%
and the gap survived, which is evidence it is not a duplication artefact alone,
but we cannot claim a specific magnitude generalises to other synthetic corpora
— only that the failure mode does. Frame the contribution as *"measure both
splits and report the gap"*, not as *"expect +0.78"*.

Evidence: `comparisons.split_gap`, `scores.*` in `results.json`;
`reports/figures/phase18_memorisation_gap.svg`.

---

## 2. Headline finding 2 — two-level interpretability with a measured faithfulness margin

**The headline contribution, and the one that fills the gap the Phase 3 review
identified** (sports-XAI explanations are almost never validated).

### 2.1 Faithfulness — the explanation describes the model

| metric | attribution | random control | margin |
|---|---|---|---|
| comprehensiveness (higher better) | 0.500 | 0.172 | **+0.328** |
| sufficiency (lower better) | 0.535 | 0.705 | **+0.170** |

n = 211 scored explanations across 129 attributed records. **All ten constructs
beat their control individually**, margins from +0.239 (burnout_signal) to
+0.471 (somatic_anxiety).

The margin is the number, not the raw metric. Deleting any 20% of a sentence
degrades a prediction somewhat; the random control absorbs that, and only what
survives it is attributable to the explanation.

### 2.2 Method agreement — the explanation is a property of the model, not the explainer

Integrated Gradients vs SHAP Partition, on 72 comparable items: mean Spearman
**0.458**, mean top-5 Jaccard **0.384**.

**Report this as a mixed result, because it is one.** Jaccard is the relevant
figure — the top-5 words are all a human is ever shown — and 0.384 means the
two methods agree on roughly two of the five words they surface. That is above
chance and below comfortable. Two principled attribution methods disagreeing
about most of what they display is a limitation of attribution methods, and
naming it costs us nothing while quietly reporting only Spearman would be the
kind of thing a reviewer catches.

### 2.3 The unevidenced-driver count — the most self-critical number we have

**104 of 120 driver rows (86.7%) have no supporting span.** A driver is a
construct that moved the risk index; an unevidenced driver is one the model
asserted while no span in the text supports it.

This is counted rather than hidden, and it is the honest boundary of the
two-level claim: the **span→construct** level is well evidenced, the
**construct→risk** level frequently is not. The paper should state the
contribution as *"a two-level explanation architecture with a measured
faithfulness margin at the span level, and an instrumented count of where the
second level runs ahead of its evidence"* — which is a stronger and more
publishable claim than an unqualified "two-level explanations work".

### 2.4 Expert validation — pilot self-audit, and named as a limitation

**Decision recorded 2026-08-16 (owner):** ship the expert half as a **pilot
self-audit with sports-familiar student raters**, with external practitioner
validation named as a limitation. OPEN-004 does not close.

Wording that must be used verbatim wherever this appears, because the rater
population is fixed on the instrument itself (`reports/explain/rating_sheet.md`):

> Explanations were reviewed in a blinded pilot study by sports-familiar student
> raters. This is a **pilot expert review**, not practitioner validation: no
> coach or sport-psychology practitioner rated the explanations. Practitioner
> validation is the principal outstanding item for this contribution.

**Never** write "expert-validated", "practitioner-validated", or
"coach-validated" anywhere in the paper, abstract or figures. The instrument is
built and blinded (genuine spans, length-matched random spans as a floor,
mismatched span/construct pairs as an attention check), so it can be re-run the
day a practitioner is available and the claim upgraded — but the claim must
match the raters who actually rated.

Evidence: `explainability.faithfulness` in `results.json`;
`reports/explain/explain.md` §§1–4.

---

## 3. Headline finding 3 — negative results, reported as results

Three things did not work. All three are informative, and all three are the
kind of result that normally gets deleted.

### 3.1 Weak supervision bought nothing

Adding 3,625 silver-labelled rows to classical training moved macro-F1 from
0.222 to 0.255 — **delta +0.033 at p = 0.107**, no significant change in either
direction.

The reason is known by construction: every silver label is `rng.randrange`
output from the offline stub, because no live OpenRouter call has ever been made
(OPEN-008 → OPEN-028). The ablation is therefore *measured evidence* that
several thousand rows of PRNG-derived supervision are worth nothing, rather than
an assertion that they would be.

The transformer arm of this ablation was **refused, in writing**, not skipped:
~10 CPU-hours to measure the effect of adding uniform noise to a training set,
where the outcome is known by construction and the cheap classical arm
demonstrates it. `AblationStatus.REFUSED` is deliberately distinct from
`UNMEASURABLE` — refused means runnable and declined with a reason.

### 3.2 The risk index cannot be calibrated

`calibrate_risk_index` **refuses to run**. No observed pre-competition risk
outcome exists anywhere in this project, so there is nothing to calibrate
against. A proxy target derived from planted labels would measure whether the
model recovers this project's own generator — circular by construction.

The refusal is in the code, not just in prose. That is the point: the paper can
state that the risk layer is uncalibrated and *point at the guard that enforces
it*, which is a stronger reproducibility claim than a limitations paragraph.

### 3.3 Four of ten constructs are inert in the fusion layer

`appraisal_orientation`, `attentional_focus`, `coping_style` and
`motivation_orientation` **never moved the risk index** across all 443 scored
records. They are the polarity-bearing constructs, left inert by the
conservative `PolarityPolicy.NEUTRAL` default: without a resolved
facilitative/debilitative or challenge/threat direction, the layer declines to
assign a sign rather than guessing one.

**Consequence for the paper's wording, and it is binding.** The risk
decomposition may **not** be described as ten-construct without qualification.
Correct phrasing:

> The fusion layer decomposes risk over ten constructs, of which **six carry
> polarity under the default conservative policy**; the remaining four are
> detected and displayed but do not move the index unless an interpretation
> direction is resolved.

Note that inertness is a *policy* property, not a performance one — two of the
four inert constructs (`coping_style` F1 0.840, `motivation_orientation` 0.790)
are among the model's strongest. Do not conflate the two.

Evidence: `ablations.{silver_classical,silver_transformer,risk_fusion}` in
`results.json`.

---

## 4. Supporting findings (real, but not headline)

### 4.1 The transformer clears the honest floor

**0.588 [0.546, 0.622]** vs the lexicon's **0.462 [0.431, 0.492]**,
template-disjoint, **delta +0.126 at p = 0.000** under a paired bootstrap.

The bar is the lexicon, not the classical learners — both TF-IDF models score
*below* the lexicon on the honest split (0.222 and 0.181). A paper that
benchmarked only against TF-IDF would have reported a far more flattering and
far less honest gap. Note also OPEN-021: the lexicon is not fully independent
of the corpus (shared ancestry with the template bank via `taxonomy.yaml`
examples), so it is a *floor with a caveat*, and the caveat belongs in the text.

### 4.2 The fusion layer materially reorders records — a genuinely positive structural result

**`naive_rho` = 0.100.** This is the rank correlation between the
taxonomy-grounded risk index and a plain count of detected constructs.

The Phase 18 handover flagged the risk that this would come back near 1.0,
which would have meant the taxonomy weighting bought interpretability but not
discrimination. It did not. At 0.100 the directions and magnitudes in
`config/taxonomy.yaml` are doing substantial work — the index is not a
dressed-up construct counter.

**Two honest qualifications.** First, low correlation with a naive baseline is
not evidence of *correctness* — with no observed outcome, "different from a
count" and "better than a count" are different claims and we can only make the
first. Second, part of the divergence is mechanical: four constructs are inert
(§3.3), so the index is driven by six constructs while the naive count uses ten.
Report `naive_rho` with both qualifications attached or it will be misread.

Two further stability numbers support the layer being well-behaved:
perturbation rho **0.989** under ±0.05 probability noise (the ordering is not
knife-edge), and rho against alternative polarity policies of **0.839**
(PESSIMISTIC) / **0.855** (OPTIMISTIC) with mean index shifts of 0.152 / 0.174
(the conservative default is a real choice with real consequences, and it is
documented rather than defaulted into silently).

### 4.3 Per-construct behaviour splits into three regimes — and the split is diagnostic

The macro-F1 hides three distinct failure modes. This table is what a reviewer
will actually ask for.

| regime | constructs | signature |
|---|---|---|
| **competent** | self_confidence (0.898), coping_style (0.840), motivation_orientation (0.790) | P and R both high and balanced |
| **threshold-collapsed** | attentional_focus (P 0.187 / R 0.958), appraisal_orientation (P 0.320 / R 1.000), somatic_anxiety (P 0.412 / R 1.000), perceived_stress (P 0.571 / R 1.000) | near-perfect recall bought with mass over-prediction |
| **threshold-frozen** | cognitive_anxiety (P 1.000 / R 0.227) | perfect precision, predicts almost nothing |

The middle and right regimes are two ends of the same mechanism: Phase 14 tuned
a per-construct decision threshold, and for five of ten constructs that tuning
landed at a degenerate corner. `attentional_focus` contributes **100 false
positives and 1 false negative**; `cognitive_anxiety` contributes **0 false
positives and 17 false negatives**. Neither is a subtle error — both are a
threshold sitting at an extreme.

**This is a finding about threshold tuning under macro-F1, and it is worth a
paragraph.** Macro-F1 rewards a construct that is always predicted when its base
rate is high enough, so per-construct threshold search can walk itself into
degenerate corners while the aggregate number looks respectable at 0.588.

### 4.4 Errors concentrate on records that already carry a construct

| constructs on record | records with ≥1 error |
|---|---|
| 0 | **0 / 44 (0%)** |
| 1 | 217 / 318 (68%) |
| 2 | 70 / 75 (93%) |
| 3+ | 6 / 6 (100%) |

The model makes **no errors at all** on genuinely construct-free text, despite
several constructs having enormous false-positive counts. Those false positives
are *additional* constructs piled onto records that already carry one — not
hallucinations on neutral text. The dominant confusions are consistent with
this: `burnout_signal→somatic_anxiety` (×29) and
`burnout_signal→perceived_stress` (×20), i.e. within the affect-adjacent
cluster, exactly where the taxonomy's own construct boundaries are thinnest.

Two readings, and both should be in the paper: the model has learned "is this
text construct-bearing at all" well and "which construct, and how many" poorly;
and the confusion structure is a taxonomy signal, not only a model signal —
`burnout_signal`, `somatic_anxiety` and `perceived_stress` may be
under-separated in the annotation rubric, which is a Phase 12 question the
synthetic corpus cannot settle.

**Error analysis is structural throughout — no example sentences.**
`docs/ethics.md` binds this project to publish no verbatim corpus text, so
errors are characterised by construct, confusion pair and construct load rather
than by quoting records. This is a real cost to persuasiveness, paid on purpose,
and the paper should say so rather than let a reviewer wonder why there are no
examples.

---

## 5. What the evidence does not support

Every line here is a sentence someone will be tempted to write. None of them
may be written.

| tempting claim | why it is unavailable |
|---|---|
| "X% accuracy at detecting cognitive anxiety" | No human has verified a single label. There is no accuracy, only agreement with planted labels (OPEN-025). |
| "generalises to athlete language" | No athlete wrote any of this text (OPEN-011). |
| "expert-validated explanations" | Pilot student raters only (OPEN-004). Use the §2.4 wording. |
| "a calibrated risk index" | No observed outcome exists; the calibrator refuses to run. |
| "weak supervision degrades performance" | The measurement is +0.033 at p = 0.107 — **no significant change**. This exact overreach is OPEN-034. |
| "ten-construct risk decomposition" | Four constructs are inert under the default policy (§3.3). |
| "the transformer beats the classical baselines" | True but flattering; the honest floor is the lexicon (§4.1). |
| "inter-annotator agreement of κ = …" | No second annotator has rated anything (OPEN-025). |

---

## 6. The methodological thread the paper should pull

Three phases in a row found the same defect shape, and it is worth a paragraph
in the discussion because it is a transferable lesson about building evaluated
ML systems, not a project anecdote.

- **Phase 17** — an ethics guard passed its own test while remaining bypassable
  through a different field.
- **Phase 18 (OPEN-034)** — the claim gate certified `silver_is_noise` green
  while the ablation backing it measured +0.033 at p = 0.110, pointing the
  opposite way. The gate checked that evidence *existed*, not that it *supported
  the claim*.
- **Phase 9b** — the obvious fix for utterance duplication (expand the suffix
  bank 8 → 17) was implemented first and did nothing. Bank size was never the
  lever; sentence-hood was.

The common shape: **the check and the thing it protects were related by
assumption rather than by construction.** The fix in each case was to make the
relationship explicit and machine-checkable — a `predicate` over resolved
evidence, a guard on the actual field, a measurement before the plausible fix.

The corollary that goes in the paper: *a gate that only checks a result exists
is worse than no gate*, because it launders the claim — the next reader sees
"backed: yes" and never rereads the number.

Watch for the fourth instance in Phase 20, where "the dashboard card renders"
will be tempting to accept as "the dashboard card is honest".

---

## 7. Claim ledger status

All seven claims in `src/evaluation/ablations.py::CLAIMS` are backed by a logged
experiment on the real checkpoint, with `transformer_beats_lexicon` and
`silver_is_noise` additionally passing a predicate over their resolved evidence
rather than a presence check.

| claim | evidence key | backed |
|---|---|---|
| `transformer_beats_lexicon` | `comparisons.transformer_vs_lexicon` | yes (predicate) |
| `memorisation_gap` | `comparisons.split_gap` | yes |
| `per_construct_spread` | `scores` | yes |
| `silver_is_noise` | `ablations.silver_classical` | yes (predicate) |
| `fusion_is_structural` | `ablations.risk_fusion` | yes |
| `explanations_beat_random` | `explainability.faithfulness` | yes |
| `not_accuracy` | `provenance` | yes |

**Any headline sentence added to the paper that is not traceable to a row above
requires a new `Claim` — added to `CLAIMS` and passing the gate — before it is
written into the narrative.** That ordering is the whole point of the ledger.

---

## 8. Open items this document does not resolve

| id | item | effect on the paper |
|---|---|---|
| **OPEN-011** | no real athlete text | Contribution #1 must be stated as a *synthetic* construct-grounded corpus throughout. Highest live risk. |
| **OPEN-004** | no practitioner rater | §2.4 wording is mandatory; upgrade only if a practitioner rates before freeze. |
| **OPEN-025** | no second annotator, no gold | No accuracy and no κ anywhere in the paper. |
| OPEN-028 | silver is PRNG output | Now *measured* (§3.1) rather than asserted. |
| OPEN-021 | lexicon not corpus-independent | Caveat travels with the 0.462 floor wherever it is quoted. |
| OPEN-030/031/032, OPEN-005/006 | pre-submission items | Phase 22–25. |

**PROVISIONAL — planted-label corpus-property measurements, NOT accuracy.
`data/gold/` is empty (OPEN-025); no real athlete text exists (OPEN-011).**
