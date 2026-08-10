# Preprocessing & De-identification (Phase 8)

**Version:** 1.0 — Phase 8, 2026-08-09
**Implements:** `docs/ethics.md` §5 (de-identification policy), `PROJECT_PLAN.md` Phase 8
**Code:** `src/preprocessing/`, gate at `scripts/run_preprocessing.py`
**Companion:** `docs/data_sources.md` (what the corpus contains), `docs/open_issues.md`

This file is written to be cited in the paper's Method and Ethics sections. Where a number
appears here it was produced by running the code, not estimated.

---

## 1. What Phase 8 does

`data/raw/` → **normalise → segment → language filter → de-identify** → `data/interim/`

| Step | Module | Output |
|---|---|---|
| Normalisation | `normalize.py` | Unicode NFKC, typography folded, controls and zero-width stripped. Casing untouched. |
| Segmentation | `segment.py` | Utterances with exact `(char_start, char_end)` offsets into the normalised parent. |
| Language filter | `language.py` | Coarse offline English filter. Conservative about exclusion. |
| De-identification | `deidentify.py` | Typed placeholders per `docs/ethics.md` §5.1; health detail removed entirely. |
| Storage | `store.py`, `records.py` | `data/interim/<source>/utterances.jsonl` + `provenance.json` + `preprocessing.json`. |

### Why this order

**Normalise first**, because every later step matches on surface form. A de-identifier looking
for `@handle` misses the fullwidth `＠handle`; a segmenter looking for `. ` misses a
non-breaking space. Normalisation is a *safety* step here, not a cosmetic one — each
unnormalised variant is a hole in the redaction.

**Segment before de-identify.** Redaction changes length (`Marcus Halloway` → `[ATHLETE]`), so
offsets computed afterwards point into a string that no longer matches the raw record. Cutting
first gives every utterance an exact, checkable span into its parent — which is what span-level
explanation needs at Phase 16.

**Consequence, stated rather than buried:** `char_start`/`char_end` index the **normalised
parent text in `data/raw/`**, not the de-identified text stored in `data/interim/`. It is on
the schema, in the manifest, and here.

---

## 2. The de-identification specification

Implemented exactly as `docs/ethics.md` §5.1 wrote it at Phase 5. The spec was not redesigned.

| Category | Action | Placeholder |
|---|---|---|
| Person names | typed replacement | `[ATHLETE]` `[COACH]` `[TEAMMATE]` `[OPPONENT]` `[PERSON]` |
| Handles, emails, phones, URLs | replacement | `[HANDLE]` `[CONTACT]` `[URL]` |
| Teams, clubs, schools, sponsors | replacement | `[TEAM]` `[ORG]` |
| Venues, cities, countries | replacement | `[LOCATION]` |
| Named competitions and editions | replacement | `[EVENT]` |
| Exact dates | replacement by relative window | `[EVENT_WINDOW]` |
| Jersey numbers, rankings, placings, uniqueness claims | replacement | `[ID]` |
| Health, injury, treatment detail | **removed entirely** | none |

### Three properties, and how each is enforced

**Typed, not blanked.** `[COACH]` and `[OPPONENT]` are different tokens because they carry
different meaning. "I'm worried about what `[COACH]` thinks" and "…what `[OPPONENT]` does"
express different constructs; a de-identifier that renders both as `[REDACTED]` deletes the
distinction the classifier exists to learn.

**Irreversible.** No mapping table, no salt, no reversible hash, and no parameter that could
produce one (`docs/ethics.md` §5.2). What `deidentify_with_report` returns is text and counts.
A test asserts the report contains no original strings and exposes no inverse.

**`deidentified: true` is earned, not set.** Phase 7 hardcoded the flag `False` everywhere on
the grounds that writing `true` would put a claim in the artefact that no code had earned.
Phase 8 flips it in exactly one function, `store.interim_provenance`, called only after the
de-identifier has run over every record. `InterimRecord.__post_init__` raises if the flag is
`False`, so an un-de-identified record is not a mistake you must remember not to make — it is
an object that cannot exist.

**`data/raw/` still says `deidentified: false`, and that is correct.** The raw text has not
been de-identified and never will be; rewriting the flag would misdescribe a file that still
contains the original strings.

---

## 3. How the de-identifier is measured, and why the obvious gate is worthless

`PROJECT_PLAN.md` sets the Phase 8 gate as "spot-check sample shows no direct identifiers
remain". Run against `data/raw/synth_precomp_v1`, that gate is **vacuous**: the generator plants
no personal names, so the de-identifier removes nothing, the spot-check finds nothing, and the
gate passes having measured zero. That is **OPEN-013**.

So Phase 8 runs two gates and labels which is which.

### 3.1 The real gate — `tests/fixtures/deid_cases.jsonl`

34 cases seeded with names, handles, teams, venues, events, dates, quasi-identifiers, health
detail, and **8 negatives that must come back unchanged**.

**Measured 2026-08-09:**

| Metric | Value |
|---|---|
| Precision | **100.0%** |
| Recall | **100.0%** |
| F1 | 100.0% |
| Exact match | **100.0%** (34/34) |
| **Leak rate** | **0.0%** |
| Negatives preserved | **8/8** |

By difficulty band:

| Band | n | Precision | Recall | Exact | Leak |
|---|---|---|---|---|---|
| easy | 10 | 100.0% | 100.0% | 100.0% | 0.0% |
| medium | 11 | 100.0% | 100.0% | 100.0% | 0.0% |
| hard | 13 | 100.0% | 100.0% | 100.0% | 0.0% |

The bands are reported separately even when they agree, because an aggregate hides the usual
pattern — easy cases pass and hard ones do not — and a reader cannot tell that pattern is
absent unless the breakdown is shown.

**A clean sweep of 34 cases is a weak claim, and §3.5 is the part of this section that
matters.** The cascade handles the failure modes this project thought to write down. It says
nothing about the ones we did not think of, and nothing at all about real athlete text.

### 3.2 The metric that actually matters

**Recall** above is placeholder-level agreement with the fixture's expected output. That is the
convenient metric. **Leak rate** is the one that is a privacy claim: the share of cases where a
string the fixture removed is still present in the output. The two come apart in both
directions — a case can mistype a coach as `[PERSON]` and leak nothing, and a case can match
the expected placeholder count while leaking, if the wrong span was replaced.

**Precision is reported because a de-identifier that blanks everything scores perfect recall
and destroys the corpus.** The 8 negative cases are the control, and all 8 survive intact.

### 3.3 One fixture case was corrected — role nouns are not names

As delivered at Phase 7, `name_01` expected:

> `Marcus Halloway said the coach was happy with the session.`
> → `[ATHLETE] said the [COACH] was happy with the session.`

It required the **bare role noun** *the coach* to be replaced. That could not be satisfied
alongside `negative_04` in the same file:

> `The Final is on Sunday and my Coach has the schedule.` → **unchanged**

whose own note reads *"'my Coach' is a role, not an identity"*. And §2 above — the removal
table copied from `docs/ethics.md` §5.1 — lists person **names** for replacement, not role
nouns. So `name_01` was the case that disagreed with the policy, not `negative_04`.

**Resolution:** `name_01`'s expected output was amended to
`[ATHLETE] said the coach was happy with the session.` The name goes; the role stays. The
correction and its reasoning are recorded in the case's own `notes` field, so the fixture
explains itself to the next reader.

**The implementation was not changed to chase the fixture.** The order of operations matters
here: the contradiction was found by running the de-identifier, reported before any file was
touched, and the fixture was corrected only once the policy had been checked and the owner
had decided. A gate rewritten to fit its implementation stops being evidence — and this
fixture is the only real measurement the de-identifier has.

Why this matters beyond one case: `[COACH]` exists to replace *a coach's name*, not the word
"coach". Collapsing the role noun into the placeholder would lose the distinction between
"what my coach thinks" and "what my opponent does" — two different constructs — which is the
same reason §2 requires typed placeholders rather than blanks.

### 3.4 The held-out probe

`tests/fixtures/README.md` warns: *"Do not tune the de-identifier until it overfits this file."*
A perfect score on the only set you developed against is not evidence of much. So
`scripts/run_preprocessing.py` also carries a 10-case **generalisation probe** using different
names, sports, and sentence shapes, never consulted while writing the rules.

**Result: 10/10 exact.** It is reported and never gated — a probe that gates becomes a second
fixture the next person tunes against, and then there is no held-out set left. 10 cases is a
smoke test; the honest reading is that the cascade is not obviously fixture-specific, not that
it is validated.

### 3.5 What this does not measure

Neither number says anything about **real athlete text**, because there is none (OPEN-011).
Every case in both sets was written by this project. When real text arrives, both must be
re-measured against it and both numbers reported. The paper must present the fixture score as
an **upper bound**, not as de-identification performance.

---

## 4. Corpus run — `synth_precomp_v1`

| Metric | Value |
|---|---|
| Raw records in | **1,200** |
| Utterances out | **4,110** |
| Records changed by normalisation | 0 |
| Records dropped | **0** |
| Health clauses removed | 0 |
| Placeholders written | **0** |
| Utterances flagged for manual audit | 0 |

Rebuild: `python scripts/run_preprocessing.py`

**Zero placeholders is the expected result and it measures nothing.** The A2 generator plants no
personal names by design (`docs/data_sources.md` §3). Reporting this line as evidence of
de-identification performance would be exactly the vacuous claim §3 exists to avoid.

### 4.1 A bug this run found

The first run dropped **2 records as Portuguese**:

> *"Slept a little lighter than usual last night."*

The English stopword profile had 20 entries and the Portuguese profile 21; the sentence shared
exactly one token with either list — `a`, a Portuguese article — and Portuguese won on a single
match. Two perfectly good English records were deleted from the corpus.

Two fixes, both structural rather than a threshold tweak:

1. **Profiles are now comparable in size** (~45 entries each). A language filter whose profiles
   differ in size is really a profile-size filter.
2. **Exclusion carries the burden of proof.** `should_exclude` drops a record only when another
   language clears an absolute score (0.20) *and* beats English by a margin (0.10). Mislabelling
   a language is a metadata error; excluding a record deletes it, and deletion is not
   recoverable by a later analyst noticing the mistake.

Both are covered by regression tests, including the exact sentence above.

**Why this mattered more than two records.** The dropped text was short, terse, and
sleep-related — which is to say it was `somatic_anxiety` and `burnout_signal` evidence. A filter
biased against short sparse text is biased against precisely the utterances this project is
trying to detect.

---

## 5. Known limitations *(paper-citable)*

These belong in the Limitations section. `docs/ethics.md` §5.3 already names residual
re-identification risk; this is the specific version of that claim for this implementation.

1. **This is a rule cascade, not NER.** Chosen so the pipeline runs offline and deterministically
   from a fresh clone with no model download and no API key (OPEN-008). The cost is real: it
   misses nicknames it has no cue for, names colliding with ordinary words, and any language the
   lexicons do not cover.

2. **Lexicon-bound health detection.** Medication detection is a ~22-name list. An unlisted drug
   name is a known miss. The primary control is not this module — it is the allow-list's **P6**,
   which makes health-subject text ineligible for the corpus at all. This is a second line of
   defence and should be described as one.

3. **The safety list is a judgement, not a dictionary.** `lexicons.COMMON_WORDS` decides which
   capitalised words are ordinary language. A word on it can never be redacted as a name, so a
   real surname that is also a common word survives. The trade-off is documented at the top of
   `lexicons.py` and the list is deliberately small.

4. **Person-role typing is heuristic.** `[ATHLETE]` for a full name before a speech verb,
   `[TEAMMATE]` for "X and I", `[OPPONENT]` after "against". These are press-report and
   conversational conventions, not grammar. Mistyping does not leak an identifier — it produces
   the wrong placeholder — but it does inject a systematic error into the linguistic context the
   classifier reads.

5. **Sentence-initial single words are not redacted without a cue.** This is what keeps "Mark my
   words" intact, and it is also how a real name opening a sentence with no other cue survives.
   A deliberate precision/recall trade, and a stated one.

6. **English only.** Every lexicon and every cue is English.

7. **34 + 10 cases cannot certify a PII pipeline.** They are smoke tests with teeth.

---

## 6. Manual audit

`docs/ethics.md` §5.2 requires a manual audit of a stratified sample every phase that touches
data — automated de-identification misses nicknames, in-group references, and unusual spellings.

`scripts/run_preprocessing.py` writes **`reports/deid_audit_sample.md`**, stratified by
sport × time-to-competition band, drawing **flagged records first**. `DeidReport.residual_flags`
lists what the cascade could not resolve — a surviving unresolved capitalised token, a long
digit run — so the human reads the cases the machine was unsure about rather than the ones it
already handled.

The sample is written with `auditor verdict: (unreviewed)` against each entry. **It is not
reviewed yet.** For `synth_precomp_v1` the audit is close to a formality — zero flags, zero
placeholders, no names in the source — and it becomes load-bearing the moment real text arrives.

---

## 7. Binding on later phases

1. **Phase 10 labels `data/interim/`, never `data/raw/`.** Raw text is not de-identified.
2. **`char_start`/`char_end` index the normalised parent**, not the stored utterance text. Span
   attribution at Phase 16 must resolve through `parent_record_id`.
3. **Placeholders are tokens with meaning.** Annotators need a rule for them
   (`docs/annotation_guidelines.md`), and the tokeniser must not split `[EVENT_WINDOW]` into
   fragments — check this when the model is wired up at Phase 13.
4. **`generation_spec` is still not a label.** It looks more like one on an interim record than
   on a raw one, which makes the warning more necessary, not less.

   **And it is replicated, not distributed** (measured at Phase 9, **OPEN-019**). Every
   utterance cut from a record carries the parent's spec byte-identically — including the
   utterances that realise none of the planted constructs, such as the neutral logistics
   sentence and the discourse suffix. A record averaging 3.45 utterances and planting 2
   constructs therefore reports both constructs on all 3.45 of them. **Any per-utterance
   count derived from this field is a per-record count multiplied by ~3.45.** Use
   `planted_construct_records`, never the per-utterance figure. Asserted by
   `tests/test_profile.py::test_generation_spec_is_identical_across_a_records_utterances`,
   so if this ever stops being true the test says so.
5. **Re-measure de-identification against real text** when OPEN-011 resolves, and report both
   numbers.
