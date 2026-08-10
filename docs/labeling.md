# Weak / LLM Labelling (Phase 10)

**Governs:** `src/labeling/`, `scripts/run_labeling.py`, `data/processed/silver/`
**Status:** built and gated offline on 2026-08-10. **The live path has not been executed.**
**Reads:** `config/taxonomy.yaml` v2, `docs/annotation_guidelines.md` v1.0,
`config/model_routing.yaml` v2.

> **What is in `data/processed/silver/` is not ground truth.** It is a cheap model's
> proposal, with a rationale and a confidence attached. Human gold labels are Phase 11,
> live in `data/gold/`, and are written by people. Every silver row carries a `NOTE`
> field saying so, because JSONL files get copied out of their directories.

---

## 1. What this phase produces

For each of the 9,302 de-identified utterances in `data/interim/`, one silver record
containing:

| Field | Meaning |
|---|---|
| `labels[]` | zero or more `{construct, value, intensity 0-3, evidence_spans[], confidence}` |
| `abstained` | true when no construct is expressed — a first-class answer, not a failure |
| `rationale` | one or two sentences describing the *language*, never the person |
| `confidence` | the model's confidence in the whole judgement |
| `interpretation_modifier` | facilitative / debilitative / unclear, only where the rubric allows |
| `low_resilience_explicit` | the guidelines sec.2d flag |
| `tier`, `model`, `escalated`, `escalation_reason` | the routing decision that produced it |
| `prompt_hash`, `prompt_version`, `context_used` | what was actually sent |
| `deduplicated`, `dedup_key` | whether this row was paid for or copied |

Plus `logs/review_queue.jsonl` (the Annotation-QA output), `logs/labeling_<run>.json`
(the agent run log), a row per call in `logs/cost_ledger.csv`, and
`reports/labeling_run.json`.

---

## 2. Prompt design

Two prompts. The **system prompt** is the rubric: the ethics preamble from
`src/agents/roster.py`, the output schema, one worked example, the hard rules, the
intensity anchors, the placeholder glossary, the five discriminating questions from
`docs/annotation_guidelines.md` sec.4, and all ten constructs with their definitions,
positive and negative examples, and edge cases. The **user prompt** is the target
utterance, fenced in `<<<...>>>`, optionally preceded by its parent record and the days
to competition.

Four design choices worth defending:

1. **The rubric is inlined, not summarised.** It is the only thing standing between a
   cheap model and generic sentiment analysis. The discriminating questions are the
   highest-value tokens in it, because they are precisely the five confusions that cause
   most *human* disagreement.
2. **The system prompt is byte-stable across calls.** Constructs are emitted in
   `taxonomy.yaml` file order, nothing record-specific appears in it, and it is memoised
   per process. `prompt_caching: true` only pays if the prefix is identical, and a prompt
   that drifts silently stops hitting the cache while everything still appears to work —
   only the bill changes. `SYSTEM_PROMPT_VERSION` is stamped onto every row so a
   mixed-version silver set is detectable after the fact.
3. **Placeholders are glossed.** `[ATHLETE]`, `[EVENT_WINDOW]` and twelve others are
   de-identification artefacts. A model told nothing about them will read
   `[EVENT_WINDOW]` as a literal phrase. A test asserts every placeholder in
   `deidentify.PLACEHOLDERS` has a gloss.
4. **Abstention is instructed explicitly and repeatedly.** 8.6% of records plant no
   construct at all and many utterances inside construct-bearing records realise nothing.
   The prompt says a labeller that never abstains is broken, not thorough.

---

## 3. Deduplication — the measured finding that changed the design

`phase10_handover.md` and `reports/eda.md` both put the saving at ~31%: 9,302 utterances
over 6,444 distinct texts. **That figure is correct and it does not survive the
requirement to pass the parent record as context.**

Recomputed on the actual corpus (generator v1.4, seed 42):

| Dedup key | Distinct prompts | Saving |
|---|---|---|
| utterance text alone | 6,444 | 30.7% |
| (utterance, parent record) | 9,185 | 1.3% |
| **(utterance, parent record, days-to-competition) — used** | **9,260** | **0.5%** |

636 utterance texts appear in more than one distinct parent record, and they are the
frequent ones: `"Results from the heats should be up by lunchtime."` occurs 109 times
across 109 different records. Nearly the whole of the 31% came from exactly the strings
whose context differs.

**The key is a hash of the exact bytes sent to the model**, so "same key implies same
answer" is true by construction at `temperature: 0.0`, rather than resting on an argument
about which parts of the prompt matter.

**The saving was given up deliberately.** The cheap-tier pass costs single-digit dollars
either way, so the difference is well under a dollar. Buying context for the constructs
that need it — `appraisal_orientation` is a stance toward an event, and a 17-token clause
frequently does not carry one — is worth that. `--no-context` keeps the abandoned option
measurable as an ablation rather than merely asserted.

*This is the third time a number carried forward from a superseded corpus version has
failed to reproduce (see also `reports/eda.md` §5b and the Phase 9 v1.1 corrections).
Recompute, do not carry forward.*

---

## 4. Routing and escalation

| Step | Policy |
|---|---|
| Start | `cheap` — `agent_defaults.labeling` in `config/model_routing.yaml` |
| Escalate when | the parser refused the output, **or** the weakest confidence < 0.65 |
| Escalate to | `mid`, **once**, and never to `premium` |
| Still unparseable | leave the utterance **unlabelled**, send it to the review queue |
| Still low-confidence | **keep** the label and flag it |

**Why the ceiling is mid, not the config's `premium`.** Premium is ~20x cheap per token.
Adjudicating a genuinely hard utterance is a job for a human at Phase 11, not for a more
expensive model at Phase 10.

**Why a failure is a gap rather than a guess.** An unlabelled utterance is a known
quantity that the review queue surfaces. A coerced one is a corrupted row that nothing
downstream can detect and that Phase 14 would attribute to the labeller.

**Why low-confidence labels are kept.** Discarding every uncertain label would bias the
silver distribution toward easy utterances — the same selection error Phase 9 rejected
when it refused to draw gold items by lexicon detectability.

**0.65 is a starting value and is treated as one.** It was written into the config at
Phase 6 with an explicit note that it is not evidence-backed, and nothing here has changed
that. The escalation rate is reported per run so it can be calibrated against the Phase 11
gold set, and Phase 18's ablation should report sensitivity to it.

---

## 5. Cost — and a config figure this phase falsified

`config/model_routing.yaml` carries a worked estimate concluding **"about $1.12 for a full
labeling pass on the cheap tier"**, built on "~400 input tokens (rubric is cached; only the
utterance varies)".

**The rubric is 3,946 estimated tokens, not 400.** Ten definitions, forty examples, ten
edge-case notes, the anchors and the discriminating questions. The config's estimate is low
by roughly an order of magnitude on the input side. It was written at Phase 6, before the
prompt existed, so this is the first opportunity anyone has had to check it.

Measured projection for the full corpus (`scripts/run_labeling.py --project-only`):

| | USD |
|---|---|
| cheap tier, 9,260 calls | 4.99 |
| + escalations at 25% on mid | 12.47 |
| **projected total, no cache credit** | **17.46** |
| monthly cap (enforced) | 20.00 |

**This is close enough to the cap to be an owner decision, not an implementation detail.**
The projection deliberately errs high on every axis it controls: every escalation is
charged at mid, output length is set at the upper end, and prompt caching is given **no**
credit at all (`--cache-discount 1.0`, the default). Cache-read rates vary by provider and
drift without notice — the same problem OPEN-009 already tracks for prices — so the
discount is a declared parameter rather than a guess baked into a number.

Four levers, in the order they should be considered:

1. **Measure the real cache-read rate with a bounded pilot** (`--live --limit 50`). If the
   cached prefix bills at 0.25x, the projection falls to roughly $5.
2. **Measure the real escalation rate.** 25% is assumed. The offline stub's 39% is an
   artefact of its uniform(0.45, 0.95) confidence and says nothing about a real model.
3. **Shorten the rubric.** Dropping negative examples and edge cases would cut it by
   perhaps a third — at the cost of the discriminating detail that stops this being
   sentiment analysis. Not recommended.
4. **Raise the cap.** Only as an explicit owner decision, never to make a run finish.

**Do not raise `monthly_cap_usd` to get past a `BudgetExceededError`.** The ledger stops
the run rather than silently truncating, and a half-written silver dataset with a confident
manifest is worse than a job that died loudly.

---

## 6. The circularity trap, and how it is closed structurally

Every interim record carries `generation_spec`: the constructs the generator planted. It is
**not a label**. This is the first phase that writes something which genuinely is one, into
a directory sitting beside those records.

**Silver is never evaluated against `generation_spec`.** Doing so would measure whether an
LLM can reverse-engineer this project's own template bank. Silver is evaluated against the
Phase 11 human gold set and nothing else.

Three structural guards rather than three warnings:

* `SilverLabel.to_dict()` emits no generator metadata, and `SilverWriter.write()` refuses
  any row containing `generation_spec` or `planted_constructs` with reason code
  `GENERATION_SPEC_IN_SILVER`.
* The Annotation-QA queue is blind to what was planted. Every flag is derived from the
  label or the text. "The model missed a planted construct" would be the circularity trap
  wearing a QA badge — a human working that queue would learn to reproduce the generator.
* Also note **OPEN-019**: Phase 8 replicates the parent's spec onto every utterance
  verbatim, so any per-utterance count derived from it is a per-record count × ~2.3.

`data/processed/gold_candidates/` was labelled along with the rest of the corpus, because
it is drawn from the same `data/interim/`. **That overlap is a comparison, never a kappa.**
Agreement is between two humans (Phase 11). Silver-vs-human is a measurement of the
labeller, reported as such.

---

## 7. OPEN-021 one level up: is the labeller independent of the corpus?

Phase 9b established that `LexiconBaseline` was never corpus-independent — its cues and the
template bank were both written from `taxonomy.yaml`'s `positive_examples`, and its
macro-F1 fell 0.780 → 0.461 once the templates stopped reusing those phrasings.

**The silver labeller has the identical shape**: it is handed `positive_examples` in its
prompt and labels a corpus generated from them.

`src/labeling/ancestry.py` buckets utterances by lexical overlap (content-token Jaccard,
max over the construct's examples, threshold 0.30) and reports the labeller's assert rate
and mean confidence in each bucket. A large gap bounds how much apparent competence is
recognition rather than comprehension; a small gap is weak evidence against, not proof.

**The check that could not be built.** The comparison that exposed the lexicon — Phase
7-era templates against Phase 9b-era ones — **is not recoverable from the corpus**.
`template_id` is `construct:label:index` with index 0–4 across all 150 templates, because
Phase 9b restructured the bank rather than appending to it, and no field records when a
template was written. Lexical overlap is the available substitute, not the preferred
instrument. Raised as **OPEN-022**.

The offline table is noise by construction — the stub picks constructs at random. The probe
is only interpretable on a live run, and its result belongs in the paper's limitations
either way.

---

## 8. What the offline gate does and does not prove

`scripts/run_labeling.py` defaults to offline, and that is a safety property: spending
money requires typing `--live`, and `--live` additionally requires `--pricing-checked`
because a retired model ID returns 404 and kills a batch partway through (OPEN-009).

The offline run **proves the plumbing** — dedup, routing, escalation, parsing, span
validation, fan-out, storage, the QA queue, the ledger — end to end, for free, from a fresh
clone, which is the property a reviewer needs.

It **proves nothing about label quality.** The stub's content is meaningless by
construction; its 33% abstention rate and 39% escalation rate are artefacts of its own
random number generator. Do not quote them as findings.

**Determinism.** Two consecutive offline runs produce a byte-identical
`logs/review_queue.jsonl` and a `silver.jsonl` that is byte-identical once `run_id` and
`labeled_on` are stripped — verified. Those two fields are per-run by design, so any
determinism check must strip them.

---

## 9. Honest limitations

1. **The live path has never been executed.** OPEN-008 is closed only in the sense that a
   key now exists; `phase8_handover.md` records OPEN-007 as exactly the mistake of shipping
   an unexecuted path, and this is currently the same mistake with a different module. The
   first live pilot is the owner's next action.
2. **The corpus is 100% synthetic (OPEN-011).** Silver labels over synthetic text are
   labels over this project's own grammar. Contribution #1 claims an athlete-text corpus.
3. **Label quality is unmeasured and unmeasurable until Phase 11.** Nothing in this phase
   reports accuracy, and no floor in the gate is a quality floor.
4. **The abstention floor is a liveness check, not a calibration.** It asserts that
   abstention happens and is not the only answer. What the *right* abstention rate is can
   only be answered by human gold.
5. **The escalation threshold is uncalibrated.** See sec.4.
6. **The cost projection rests on three declared assumptions** — output length, escalation
   fraction, cache discount — none of them measured. It is an upper bound, not a forecast.
7. **Prompt caching is configured but unverified.** `prompt_caching: true` is a config flag;
   whether the provider actually caches a 3,946-token prefix, and at what rate, is unknown
   until a live run reports it.
