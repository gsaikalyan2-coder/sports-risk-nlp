# Artifact — Pre-Competition Psychological Risk Profiling of Athletes

Research artifact accompanying the paper. Construct-grounded NLP that detects
validated sports-psychology constructs in pre-competition athlete text and fuses
them into an interpretable risk index with two-level explanations
(span→construct, construct→risk).

> **PROVISIONAL — planted-label corpus-property measurement, NOT accuracy.**
> `data/gold/` is empty (OPEN-025); no real athlete text exists (OPEN-011).
> Every figure in this artifact measures agreement with generator-planted labels
> on **synthetic** text. Nothing here is a measurement of a person.

---

## What this artifact contains

* A **synthetic** construct-grounded corpus (`synth_precomp_v1`, 4,000 records →
  9,302 utterances), regenerated deterministically from source at seed 42 — the
  corpus text is not shipped, the generator is.
* A ten-construct multi-label taxonomy grounded in the CSAI-2 / SDT / ABQ
  traditions (`config/taxonomy.yaml`, `docs/annotation_guidelines.md`).
* Lexicon and classical baselines, a fine-tuned distilroberta classifier, and a
  deterministic construct→risk fusion layer with per-construct contributions.
* Span-level attributions with a measured faithfulness margin over a random-span
  control.
* A Streamlit dashboard, an evaluation harness with a claim ledger, a security
  audit, and a reproduction checker.

## What it does not contain, and cannot

* **Real athlete text.** No public pre-competition corpus exists that is both
  licensed and on the right side of the event; four candidates were surveyed and
  all four rejected (`docs/data_sources.md` §4). The corpus is 100% synthetic.
  Contribution #1 is a **synthetic** construct-grounded corpus, and is described
  that way throughout.
* **A gold standard.** No second annotator was recruited, so `data/gold/` is
  empty, there is no inter-annotator agreement figure, and every number here
  stays agreement with generator-planted labels rather than a measurement of
  correctness. `src/models/dataset.py` refuses
  `--gold` rather than falling back to silver labels.
* **Practitioner validation of the explanations.** The explanation study shipped
  as a blinded pilot self-audit with sports-familiar student raters.
  Practitioner validation is a named limitation, not a pending task.
* **Any clinical claim.** Research and decision-support only. No mental-health
  inference about any real, named individual. See `docs/ethics.md`.

---

## Reproducing it

Minutes, no GPU, no API key, no account of any kind.

```bash
git clone <repo-url> sports-risk-nlp-repro && cd sports-risk-nlp-repro
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-base.lock.txt

python scripts/run_ingestion.py --count 4000 --seed 42
python scripts/run_preprocessing.py
python scripts/run_baselines.py --seed 42
python scripts/run_evaluation.py --seed 42 --resamples 1000
```

Then let the checker grade it:

```bash
python scripts/run_reproduction.py --verify --root . --tiers A,B
```

**Clone into a new directory.** The checker inspects the tree first and exits 2
rather than measuring if it finds generated artefacts already present — a
reproduction verified where it could not have failed is not evidence. This also
means `docker compose run app` will not do: every service bind-mounts the host
working tree.

Retraining the transformer is a separate, ~10 CPU-hour step:

```bash
pip install -r requirements-ml.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
python scripts/run_transformer.py --seed 42
python scripts/run_evaluation.py --cache-predictions
```

The `--extra-index-url` is required, not advisory: `torch==2.13.0+cpu` is a PEP
440 local version that exists on no default index.

### What reproduces, and how exactly

`reports/predictions/` is committed, so the cheap path re-derives the
transformer's **scores** without torch, weights or corpus — and does not
re-derive the transformer. Full per-artefact strengths, the ±0.010 retrain
tolerance and how it was fixed before any run, and the complete list of what
cannot be reproduced by anyone: **[`docs/reproducibility.md`](docs/reproducibility.md)**.

Verified 2026-08-24 from a genuine fresh clone on a different operating system:
every headline number returned at full float precision.

---

## The headline numbers

Template-disjoint split, planted labels, synthetic text. Each figure is
agreement with the generator's own planted labels, never a measurement of
correctness — see the stamp above.

| result | figure |
|---|---|
| transformer macro-F1 | **0.588** [0.546, 0.622] |
| lexicon floor | 0.462 [0.431, 0.492] |
| delta, paired bootstrap | **+0.126**, p = 0.000 |
| memorisation gap, TF-IDF | random 0.999 → disjoint 0.222 (**+0.777**) |
| memorisation gap, transformer | +0.234 |
| memorisation gap, lexicon control | +0.100 |
| explanation comprehensiveness over random-span control | **+0.328** |

Three negative results are reported as results: silver supervision bought
nothing (+0.033, p = 0.107); the risk index cannot be calibrated because no
observed outcome exists; and **four of the ten constructs are inert** in the
fusion layer under the conservative default polarity policy, so the risk
decomposition is not ten-construct without qualification. 104 of 120 driver rows
(86.7%) have no supporting span — published rather than hidden.

The lexicon floor is not independent of the corpus (OPEN-021); that caveat
travels with the 0.462 wherever it is quoted.

---

## Layout

| path | what |
|---|---|
| `config/` | taxonomy, model routing, data-source allow-list |
| `src/` | ingestion, preprocessing, taxonomy, labeling, models, risk, explainability, evaluation, dashboard, security, reproducibility |
| `scripts/` | one runner per phase gate |
| `reports/` | metrics, figures, explanation cards, security audit, reproduction record |
| `docs/` | ethics, findings, model card, reproducibility, security, annotation guidelines |
| `dashboard/` | Streamlit demo |
| `tests/` | pytest; the suite runs with no ML stack installed |

## Ethics

Synthetic, de-identified text only. Research and decision-support, never
diagnosis. Risk labels can stigmatise, and the framing, misuse risks and bias
limitations are set out in `docs/ethics.md`. Every score surface carries a
provenance stamp enforced in code rather than trusted to the report author.

## Licence and contact

See `LICENSE`. The contact route is below and in `docs/consent_form.md`.

## Contact — withdrawal, correction, incident reports

**`sk8069@srmist.edu.in`** (SRMIST institutional address)
Supervisor / secondary contact: **Dr. Shankar Ram**, SRMIST
Subject-line prefix: `[SPORTS-RISK-NLP]` · Acknowledgement target: **7 days**

`docs/ethics.md` §7.1 requires this route to appear on every reader-facing
surface. It is the mechanism behind §7's withdrawal and correction rights: if it
is not reachable from the document a reader actually has, those rights are
decorative. Note that the released corpus is 100% synthetic (OPEN-011), so no
real person's text is presently subject to withdrawal — the route exists so that
it already works on the day that stops being true.
