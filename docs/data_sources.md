# Data Sources

**Phase 7, 2026-08-09.** Every source ingested into `data/raw/`, plus every candidate
that was surveyed and **rejected**, with the reason. The paper's dataset section is
built from this file.

Companion documents: `docs/ethics.md` §3 (policy), `config/data_sources_allowlist.yaml`
(machine-readable allow-list, enforced by `src/ingestion/allowlist.py`).

---

## 1. The survey result, and why it changed the plan

`CLAUDE.md` §10 Q3 confirmed **"existing public/licensed datasets first"** (allow-list
category A1) with a hybrid synthetic-plus-small-real-gold-set fallback, and explicitly
said to revisit that fallback at Phase 7. The survey was run on 2026-08-09.

**Finding: no public corpus of *pre-competition* athlete text exists.** Every athlete-speech
corpus located is **post-match**.

That is not a licensing inconvenience, it is a construct-validity problem. This project's
taxonomy is anticipatory: `appraisal_orientation` asks whether the athlete frames an
*upcoming* competition as challenge or threat, and `cognitive_anxiety` is worry about an
outcome that has not happened. Post-match speech expresses relief, disappointment, and
causal attribution instead — different constructs, elicited after the uncertainty has
resolved. Training on post-match text and reporting it as pre-competition risk profiling
would be a failure a reviewer would identify immediately.

This is exactly risk #1 in `PROJECT_PLAN.md` ("data scarcity/licensing — highest risk")
materialising. **Owner decision, 2026-08-09: synthetic-first (A2), pre-competition framing
retained, full taxonomy retained.** Recorded in `CLAUDE.md` §10.

---

## 2. Ingested sources

### 2.1 `synth_precomp_v1` — synthetic pre-competition athlete utterances

| Field | Value |
|---|---|
| Allow-list category | **A2_synthetic** |
| Records | **4,000** |
| Licence | Project-generated. No third-party licence applies; no human subject involved |
| Redistribution | **Permitted** — the only source in the corpus quotable verbatim in the paper |
| Generator | `construct-template-grammar@1.3`, seed `42` |
| Language | English |
| De-identified | `false` — Phase 8 sets this flag, not Phase 7 |
| Path | `data/raw/synth_precomp_v1/` (`provenance.json` + `records.jsonl`) |

**What it is.** A seeded template grammar over the ten locked constructs in
`config/taxonomy.yaml`, stratified across sport, competition level, region, register, and
time-to-competition. Rebuild it with:

```bash
python scripts/run_ingestion.py            # defaults: --count 4000 --seed 42
```

**Why a template grammar rather than an LLM.** Three reasons, all recorded in
`src/ingestion/synthetic.py`:

1. **Reproducibility.** `CLAUDE.md` §9 makes a reproducible artifact part of
   publication-readiness. Same seed → byte-identical corpus, no API key, no cost.
2. **OPEN-008.** There is no `OPENROUTER_API_KEY` in `.env`, so an LLM path could not have
   been executed or verified this session. Shipping an unrun generator would repeat the
   OPEN-007 mistake.
3. **Visible limitations.** A template grammar cannot pass itself off as naturalistic
   speech. The constraint is in the artefact rather than hidden behind fluent prose.

#### Corpus statistics (measured, generator v1.3, seed 42, n=4000)

| Metric | v1.0 (n=1.2k) | v1.1 (n=1.2k) | v1.2 (n=1.2k) | **v1.3 (n=4k, current)** |
|---|---|---|---|---|
| Records | 1,200 | 1,200 | 1,200 | **4,000** |
| Distinct texts | 976 (81.3%) | 1,161 (96.8%) | 1,158 (96.5%) | **3,797 (94.9%)** |
| Tokens | 30,367 | 40,251 | 40,634 | **134,787** |
| **Vocabulary (types)** | 444 | 635 | 636 | **625** |
| **MATTR-50** | — | 0.818 | 0.820 | **0.819** |
| Raw type–token ratio | 0.0146 | 0.0158 | 0.0157 | **0.0046** |
| Words per record | mean 25.3 | mean 33.5 | mean 33.9 | **mean 33.7** |
| Records with no construct planted | 106 (8.8%) | 92 (7.7%) | 85 (7.1%) | **300 (7.5%)** |
| **Records with a broken/degraded substitution** | — | not measured | 190 (15.8%) | **0 (0.0%)** |

> **Read the raw-TTR column as a warning, not a result.** It falls from 0.0157 to
> 0.0046 between v1.2 and v1.3 while MATTR-50 does not move at all (0.820 →
> 0.819) and the vocabulary barely changes. Nothing about the text got less
> diverse; the corpus got 3.3× longer and TTR's denominator grew with it. This is
> the length confound in one row, and it is why **MATTR-50 and `vocabulary_size`
> are the two figures this project quotes.**

> **v1.3 vocabulary is 11 types lower than v1.2, and that is the guard working.**
> OPEN-016 added a generation-time check that reverts a substitution which would
> produce a ruled-defective frame, so a word whose only frames in the bank were
> defective now never appears. The alternative — deleting the 34 implicated
> synonym-group members — was measured at **594** types. The guard keeps 31 more
> and removes nothing from the bank. Full table in
> `src/ingestion/substitution_verdicts.py`.

> **Three v1.1 figures were corrected at Phase 9.** The v1.1 column previously
> read 638 types, 1,163 distinct texts, 40,169 tokens and 106 construct-free
> records. Regenerating from the committed v1.1 generator
> (`git show 6f9561a:src/ingestion/synthetic.py`) at seed 42 gives **635**,
> **1,161**, **40,251** and **92**. The discrepancy is small and changes no
> conclusion, but the artefact claim in `CLAUDE.md` §9 is that a reviewer can
> reproduce these numbers exactly, so a figure that does not reproduce is a defect
> regardless of its size.

> **These are per-RECORD statistics** over `data/raw/`. The per-*utterance*
> profile of `data/interim/` is in `reports/eda.md`, and the two are not
> comparable — Phase 8 turned 4,000 records into 13,651 utterances, which changes
> every denominator. In particular the per-utterance corpus is **87.4% exact
> duplicates** (OPEN-018), a fact entirely invisible at record level, where the
> duplicate rate is 7.2%.

**Do not quote raw TTR as the diversity headline.** It is length-confounded: its
denominator grows without bound while its numerator saturates, so v1.1 raised the
vocabulary by 44% and moved raw TTR by 0.001. **MATTR-50** (mean TTR over sliding
50-token windows) holds the denominator fixed and is the comparable figure;
`vocabulary_size` is the other honest one. Both are computed by
`src/ingestion/synthetic.py`.

**What v1.1 changed.** A lexical-variation layer applies construct-preserving
near-synonym substitution and discourse framing *after* a template renders. It
raises the type count without altering template identity, so the
template-disjoint split in §2.2 still holds every paraphrase of a template out
together — a paraphrase of a seen template is still leakage, and treating it
otherwise would have manufactured the inflation this work exists to remove.

Synonym groups are restricted to members sharing a part of speech **and** an
argument structure. A first pass without that restriction generated
"fixating *about* the result", "I must *to* not mess this up", and "Sessions
*has* been at the usual times". Those groups were removed rather than
special-cased; the reasoning is recorded inline in `SYNONYM_GROUPS`.

**What v1.2 changed.** `("part", "portion", "corner", "piece")` deleted: every
occurrence of *part* in the bank sits inside the idiom *part of me*, and the
idiom does not survive substitution (OPEN-015). All four members share a part of
speech **and** an argument structure, so the review rule above could not have
caught it — **idiom membership is a third constraint**.

**What v1.3 changed, and it is the important one.** The v1.2 fix prompted an
exhaustive sweep (`src/ingestion/synonym_audit.py`): all 727 single-token
substitutions the generator can make, screened by six probes. It found that
OPEN-015 had **not** been isolated — **15.8% of v1.2 records** still contained a
substitution a human ruled broken or degraded, across 55 realised signatures
("*figure about*", "*insides is*", "*a approach*", "*on edge I'll*").

The remedy was **not** to shrink the bank. `_vary` now consults the ruled
verdicts at generation time and reverts any substitution that would produce a
defective frame (OPEN-016, option (c)). `think → figure` is broken in *"all I
figure about"* and fine in *"I figure I'm ready"*: the defect belongs to the
**frame**, not the word, and a context-blind bank can only accept or reject the
word. Measured both ways at n=4,000 — deleting the 34 implicated members costs
49 realised types, the guard costs 18, and both reach zero defects.

The standing guarantee is a build-time ratchet, not a one-off measurement: the
sweep is exhaustive over single substitutions, a test fails if any flagged
signature lacks a human verdict, and a second test asserts the corpus contains no
ruled-defective frame at all. **A new defect class still needs a human to notice
it once; it no longer needs a human to notice it repeatedly.**

#### Construct prevalence

> **GENERATOR METADATA, NOT LABELS.** This is what the generator *planted*, i.e.
> a description of the template bank. It is not corpus prevalence, it is not
> athlete language, and using it as evaluation ground truth would measure whether
> a model can recover this file's own template choices. Evaluation rests on the
> Phase 11 human gold set. Counts are **per record** (n=4,000); see OPEN-019 for
> why the per-utterance version of this table would be meaningless.

| Construct | Records | Prevalence |
|---|---|---|
| `cognitive_anxiety` | 934 | 23.4% |
| `coping_style` | 895 | 22.4% |
| `self_confidence` | 745 | 18.6% |
| `somatic_anxiety` | 689 | 17.2% |
| `appraisal_orientation` | 687 | 17.2% |
| `perceived_stress` | 671 | 16.8% |
| `attentional_focus` | 587 | 14.7% |
| `resilience` | 566 | 14.2% |
| `burnout_signal` | 540 | 13.5% |
| `motivation_orientation` | 431 | 10.8% |

Constructs per record: 0 → 300, 1 → 1,377, 2 → 1,601, 3 → 722. The interpretation
modifier is present on 385 records (209 debilitative, 176 facilitative).

#### Temporal and context coverage

The Phase 7 gate requires these present where the source allows, explicitly null otherwise.
This generator controls timing entirely, so anything below 100% would be a generator bug —
`scripts/run_ingestion.py` fails the gate if a synthetic source leaves timing null.

| Field | Coverage | Notes |
|---|---|---|
| `time_to_competition_days` | **100%** | 0–30 days, weighted to the final week |
| `sport` | **100%** | 10 sports, 108–143 records each |
| `competition_level` | **100%** | 5 levels, 228–254 each |
| `region` | **100%** | 5 regions, 224–269 each |
| `source_type` | **100%** | always `synthetic`; intended register in `generation_spec.rendered_as` |
| `training_load_hint` | **62.3%** | deliberately sparse — real sources rarely carry this |

Time-to-competition distribution (days before): 0→167, 1→229, 2→153, 3→169, 5→72, 7→86,
10→80, 14→86, 21→89, 30→69.

Register (in `generation_spec.rendered_as`): social 343, presser 300, journal 285,
interview 272.

---

## 3. Known bias and limitations of this corpus

Stated plainly. Each of these belongs in the paper's limitations section.

| Limitation | Substance |
|---|---|
| **It is synthetic** | No real athlete produced any of this text. It provides training volume and a working pipeline, not ecological validity. Any claim about real athlete language requires the real gold set, which does not yet exist. |
| **Vocabulary is tiny** | 444 word types across 30k tokens. A classifier trained on this alone will learn template surface forms, not construct semantics, and will not transfer. Held-out scores on this corpus are **not** evidence of generalisation. |
| **Balanced by construction, unlike reality** | Sport, region, and level are near-uniform because they are sampled uniformly. Real corpora are heavily skewed toward well-funded men's sports in a handful of countries (`docs/ethics.md` §6). This corpus therefore *understates* the sport/gender/language skew the paper must still discuss. |
| **No gender attribute** | Deliberately not generated. Assigning gender to fictional athletes and then reporting performance by it would fabricate a fairness result. Gender stratification requires real data. |
| **Monolingual** | English only. Cultural patterning of emotional expression (`docs/ethics.md` §6) is entirely unrepresented. |
| **No names, so de-identification is untested here** | The generator emits role references ("my coach") and never personal names, real or invented. Consequence: Phase 8's de-identifier has almost nothing to detect in this corpus, so its **recall cannot be validated against it**. That validation needs real text. |
| **Register is asserted, not observed** | A record labelled `journal` in `rendered_as` is not written in a demonstrably different register from one labelled `presser`. The field records intent, not a measured stylistic difference. |
| **Media-training artefact absent** | `docs/ethics.md` §6 names elite media training as a validity threat. Synthetic athletes have none, so the corpus is *cleaner* than reality in a way that flatters the model. |

### 3.1 Circularity risk — read before using `generation_spec`

Each record carries `generation_spec.planted_constructs`, naming the constructs the
generator planted.

**This is generation metadata. It is not a label, and it must never be used as evaluation
ground truth.** Doing so would measure whether a model can recover the template choices in
`src/ingestion/synthetic.py` — a circular result that says nothing about athlete language,
while producing impressively high F1. The warning travels inside every record
(`generation_spec.NOTE`) as well as here, and a test asserts it is present.

Legitimate uses: sanity-checking that Phase 10 silver labelling is not wildly
miscalibrated; stratified sampling; debugging; and measuring **corpus properties** such as
template leakage (§2.2), which is a question about the generator's structure rather than
about model quality. Evaluation rests on the Phase 11 human gold set alone.

---

## 2.2 Template leakage — measured, not assumed (OPEN-012)

A random train/test split on this corpus puts the **same template** on both sides. A model
can then score highly by recognising a string it has already seen labelled. That is not an
optimistic estimate of the right quantity; it is a precise estimate of the wrong one.

`src/evaluation/splits.py` provides `template_disjoint_split`, which partitions *templates*
first and assigns records second. A record enters the test set only if every template it
uses is a held-out template; records straddling the partition are discarded and counted.

`scripts/run_benchmark_audit.py` quantifies the effect. Measured on
`synth_precomp_v1`, seed 42, test_size 0.2:

| System | Random split | Template-disjoint | Drop |
|---|---|---|---|
| **Memorisation probe** (1-NN over training text) | 0.732 | **0.198** | **+0.534** |
| Lexicon (leakage-immune, ignores training labels) | 0.729 | 0.757 | −0.028 |
| Stratified random | 0.173 | 0.136 | +0.036 |
| Majority | 0.000 | 0.000 | 0.000 |

macro-F1, 95% bootstrap CIs in the script output.

| Leakage signal | Random | Template-disjoint |
|---|---|---|
| Templates on both sides | 85 | **0** |
| Test texts appearing verbatim in train | 3.8% | **0.0%** |
| 8-gram overlap | 60.3% | 11.8% |

**Reading it.** A pure memoriser loses **0.53 macro-F1** once templates are held out, while
a system that cannot memorise (the lexicon never looks at training labels) is unchanged
within noise. The gap is memorisation, not skill. A fine-tuned transformer has far more
capacity to memorise than 1-NN, so **0.53 is a lower bound** on the inflation Phase 14
would otherwise report.

**Binding consequences for later phases:**

1. Phases 13, 14 and 18 **must** use `template_disjoint_split`. Using `random_split` for a
   reported result is a methodological error, and the function's docstring says so.
2. Report **both** numbers in the paper. The gap is itself a contribution — evidence the
   failure mode was measured rather than assumed away, and reusable by anyone else building
   a template-seeded corpus.
3. Every headline number carries a **bootstrap CI** (`src/evaluation/metrics.py`). With a
   test set near 120 records the interval is wide, and hiding that would misrepresent it.
4. The Phase 14 gate "transformer > best baseline on macro-F1" is met only when
   `paired_bootstrap_p_value` says the gap survives resampling. 0.74 vs 0.73 is not a win.
5. The transformer must be compared against the **lexicon** baseline specifically. If a
   fine-tuned DeBERTa barely beats a keyword matcher on a disjoint split, it has learned the
   template bank rather than the constructs.

---

## 4. Candidates surveyed and REJECTED

Recorded because the paper must be able to say what was considered and why it was not
used, and because two of these become available if a licence conversation happens.

| Candidate | What it is | Rejected because |
|---|---|---|
| **Cornell Tennis Transcript and Commentary Dataset** ([page](https://www.cs.cornell.edu/~liye/tennis.html), [README](https://www.cs.cornell.edu/~liye/tennis_README.txt)) — Fu, Danescu-Niculescu-Mizil & Lee, 2016. 6,467 tennis singles **post-match** press conferences, 2007–2015, sourced from ASAP Sports | Freely downloadable | **No licence statement anywhere.** The project page and README carry a BibTeX citation request only. Fails A1's `explicit_licence_recorded_verbatim`, and triggers P7 (unverifiable provenance). Also post-match, so wrong side of the event. **Recoverable** with one written permission from the authors. |
| **iMiGUE-Speech** ([repo](https://github.com/CV-AC/imigue-speech)) — Kakouros, Kang & Chen, 2026. 359 **post-match** athlete interviews with Whisper ASR transcripts, speaker separation, word-level alignment | Gated | Requires a **signed licence agreement** with the University of Oulu, not obtained. Would satisfy A1 once signed. Also post-match. Base iMiGUE is identity-free, which would help Phase 8. |
| **ASAP Sports direct collection** (asapsports.com) — the underlying transcript archive, which does include pre-tournament press conferences | Not attempted | `terms.php` and `robots.txt` both returned empty content, so the terms of service **could not be verified**. Under the allow-list's fail-closed rule this is P4/P5 territory and ingestion must refuse. Needs a human to read the terms. |
| **YouTube captions via the Data API** (an `OPENROUTER`-independent route; `YOUTUBE_API_KEY` is present in `.env`) | Route closed | `captions.download` requires an OAuth token from the **channel that owns the video**; third-party requests return 403. Using any other extraction method would breach YouTube's terms → P4. |
| **Hugging Face Hub** | Nothing relevant | Searched athlete/sports/interview/press-conference/anxiety. Zero athlete-text datasets. The anxiety datasets found are clinical or general mental-health, which P6 excludes and which are not athlete speech. |

**Nothing from any rejected candidate is present in `data/raw/`.** The refusal path is
exercised on every run of `python scripts/run_ingestion.py --demo-refusal`, and refusals
are appended to `logs/ingestion_refusals.log`.

---

## 5. How enforcement works

`src/ingestion/` refuses rather than warns. There is no bypass flag, per the instruction in
`config/data_sources_allowlist.yaml` ("Never add a bypass flag to this checking path").

| Control | Where | Refusal code |
|---|---|---|
| Unlisted category | `allowlist.check_source` | `UNLISTED_SOURCE` |
| Category status not `permitted` | `allowlist.check_source` | `CATEGORY_NOT_PERMITTED` |
| Prohibition not declared against | `allowlist.check_source` | `MISSING_DECLARATION` |
| Prohibition declared but not cleared | `allowlist.check_source` | `PROHIBITED_MATCH` |
| Synthetic text filed under a real category | `allowlist.check_source` | `CATEGORY_MISMATCH` |
| Empty licence basis | `allowlist.check_source` | `MISSING_LICENCE_BASIS` |
| Missing required provenance field | `provenance.validate_provenance` | `MISSING_REQUIRED_PROVENANCE_FIELD` |
| Records with no `provenance.json` | `store.RawStore.iter_all` | `MISSING_PROVENANCE` |
| Write attempt into `data/gold/` | `store.RawStore._guard_root` | `GOLD_IS_HUMAN_OWNED` |

All seven prohibitions P1–P7 must be **explicitly declared against** by the caller. An
absent declaration is refused rather than defaulted to compliant — silence is not consent.
A parametrised test covers every declaration in both directions, and another test asserts
that no prohibition can be added to the YAML without a corresponding code guard.

---

## 6. What has to happen next

| Item | Phase | Tracked as |
|---|---|---|
| The corpus has no real athlete text. Contribution #1 needs some. | 8–11 | **OPEN-011** |
| Vocabulary of 444 types is too small to train a transformer that generalises. | 10 | **OPEN-012** |
| Phase 8 de-identification cannot be validated against a corpus with no identifiers. | 8 | **OPEN-013** |

---

## 7. Change log

| Date | Change |
|---|---|
| 2026-08-09 | Created at Phase 7. Survey recorded; four candidates rejected with reasons; `synth_precomp_v1` (1,200 records, A2) ingested. |
