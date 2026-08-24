## Reproduction check

**Gate:** PASS

> PROVISIONAL -- planted-label corpus-property measurement, NOT accuracy. data/gold/ is empty (OPEN-025); no real athlete text exists (OPEN-011).

Verified in `/home/claude/clone6` -- /home/claude/clone6 is a fresh tree: none of data/raw/synth_precomp_v1/records.jsonl, data/interim/synth_precomp_v1/utterances.jsonl, models is present, and every path a clone does carry is there.

Tiers attempted on this pass: **A_SEEDED, B_RESCORE**.

### Tier A -- seeded, minutes, base dependencies only

**`env`** -- Stand up the light environment from the lock, in a NEW directory, so the reproduction cannot read four months of accumulated artefacts.

```
git clone <repo-url> sports-risk-nlp-repro && cd sports-risk-nlp-repro && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-base.lock.txt
```

- **Reads:** requirements-base.lock.txt
- **Cannot reproduce:** Nothing numeric. This step installs no torch, so every tier-C artefact is out of its reach; it also cannot verify the ML layer's pins, which only the `env-ml` step exercises.
- **Ran on this pass:** no
- **Not runnable by the checker:** this command is the reader's own setup and cannot be executed from inside the tree it produces.

**`corpus`** -- Regenerate the synth_precomp_v1 corpus. A fresh clone has no data/, so this is where the text a reviewer scores actually comes from.

```
python scripts/run_ingestion.py --count 4000 --seed 42
```

- **Reads:** config, src/ingestion, scripts/run_ingestion.py
- **Cannot reproduce:** Any property of real athlete text. The corpus is 100% synthetic template grammar (OPEN-011); reproducing it proves the generator is deterministic and proves nothing about athletes.
- **Ran on this pass:** yes

**`preprocess`** -- Clean, segment and de-identify the generated corpus into the 9,302 utterances every downstream step consumes.

```
python scripts/run_preprocessing.py
```

- **Reads:** data/raw, config, src/preprocessing
- **Cannot reproduce:** The de-identification recall figure against real text. The fixture measures the failure modes we thought to write down on a generator that plants no identifiers, so 0% leak rate is an upper bound (Phase 8).
- **Ran on this pass:** yes

**`baselines`** -- Re-fit the lexicon and classical baselines and re-derive the honest floor the transformer is measured against.

```
python scripts/run_baselines.py --seed 42
```

- **Reads:** data/interim, config, src/models, src/evaluation
- **Cannot reproduce:** Independence of the lexicon floor from the corpus. OPEN-021: the lexicon shares ancestry with the template bank via taxonomy.yaml examples, so the 0.462 floor travels with that caveat wherever it is quoted.
- **Ran on this pass:** yes

| artefact | declared | outcome | expected | produced | delta |
|---|---|---|---|---|---|
| corpus_records | byte-identical | reproduced | sha256:fa09f5adeea7e4f3 | sha256:fa09f5adeea7e4f3 | -- |
| utterances | byte-identical | reproduced | sha256:87a796caf7d8ce11 | sha256:87a796caf7d8ce11 | -- |
| lexicon_template_disjoint_macro_f1 | byte-identical | reproduced | 0.4617285842599597 | 0.4617285842599597 | +0.0000 |
| tfidf_template_disjoint_macro_f1 | byte-identical | reproduced | 0.22208037080486936 | 0.22208037080486936 | +0.0000 |
| tfidf_random_macro_f1 | byte-identical | reproduced | 0.9994594594594595 | 0.9994594594594595 | +0.0000 |

### Tier B -- rescoring a committed cache, seconds, base dependencies only

**`rescore`** -- Re-score every system from the committed prediction caches and rebuild reports/results.json, including the paired bootstrap comparisons.

```
python scripts/run_evaluation.py --seed 42 --resamples 1000
```

- **Reads:** reports/predictions, data/interim, config, src/evaluation
- **Cannot reproduce:** The transformer itself. This step reads reports/predictions/, which IS committed, so it re-derives the SCORING of the transformer's predictions and never the predictions. A green tick here is not evidence that the checkpoint retrains to the same place -- that is step `retrain`, tier C.
- **Ran on this pass:** yes

| artefact | declared | outcome | expected | produced | delta |
|---|---|---|---|---|---|
| transformer_template_disjoint_macro_f1 | byte-identical | reproduced | 0.5877114720181955 | 0.5877114720181955 | +0.0000 |
| transformer_vs_lexicon_delta | byte-identical | reproduced | 0.1259828877582358 | 0.1259828877582358 | +0.0000 |
| memorisation_gap_transformer | byte-identical | reproduced | 0.23423985163237282 | 0.23423985163237282 | +0.0000 |
| transformer_random_macro_f1 | byte-identical | reproduced | 0.8219513236505683 | 0.8219513236505683 | +0.0000 |

### Tier C -- retraining, ~10 CPU-hours, full ML stack

**`env-ml`** -- Install the training layer. Separated from `env` so a reviewer reproducing tiers A and B never pays for a multi-gigabyte ML stack.

```
pip install -r requirements-ml.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

- **Reads:** requirements-base.lock.txt, requirements-ml.lock.txt
- **Cannot reproduce:** Bit-level equivalence of the numeric stack. A different CPU, BLAS build or torch build changes float results, which is exactly why tier C is measured against a tolerance and tiers A and B are not.
- **Ran on this pass:** no

**`retrain`** -- Actually re-derive the transformer predictions rather than reading the committed cache -- the only step that tests the headline model end to end.

```
python scripts/run_transformer.py --seed 42 && python scripts/run_evaluation.py --cache-predictions
```

- **Reads:** data/interim, config, src/models, reports/predictions
- **Cannot reproduce:** Anything gold-derived, and anything about real athletes. It also costs roughly ten CPU-hours, so most reviewers will not run it; that is why its artefact is reported SKIPPED rather than silently folded into tier B.
- **Ran on this pass:** no

| artefact | declared | outcome | expected | produced | delta |
|---|---|---|---|---|---|
| retrained_transformer_macro_f1 | within tolerance (+/-0.01 absolute macro-F1) | skipped -- runnable, not run on this pass | -- | -- | -- |

### Tier D -- cannot be run by anyone, including the author

**`gold`** -- Named so that the gold-derived figures are visible as an absence with a reason, rather than as rows a reader has to notice are missing.

```
# no command exists
```

- **Reads:** nothing in the repository
- **Cannot reproduce:** Everything it covers. data/gold/ is empty and no second annotator exists (OPEN-025), so no kappa and no human-agreement figure can be produced by anyone, the author included.
- **Ran on this pass:** no

| artefact | declared | outcome | expected | produced | delta |
|---|---|---|---|---|---|
| inter_annotator_kappa | not reproducible | blocked -- not runnable by anyone | -- | -- | -- |
| human_agreement_scores | not reproducible | blocked -- not runnable by anyone | -- | -- | -- |

### What this run does NOT reproduce

- **retrained_transformer_macro_f1** -- skipped -- runnable, not run on this pass. tier C -- retraining, ~10 CPU-hours, full ML stack; not selected on this pass
- **inter_annotator_kappa** -- blocked -- not runnable by anyone. OPEN-025: data/gold/ is empty because no second annotator was recruited, and src/models/dataset.py refuses --gold rather than falling back to silver. This is not a step a reviewer can run.
- **human_agreement_scores** -- blocked -- not runnable by anyone. OPEN-025 again, the same block as the kappa. Every figure in this repository is agreement with generator-planted labels on synthetic text, and no human-labelled comparison set exists to reproduce.
