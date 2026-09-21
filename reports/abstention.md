# Abstention-aware evaluation -- what the system does with what it cannot score

> **No number in this file is an accuracy.** Every figure is behaviour of
> the gates and the fusion layer over synthetic text (OPEN-011) with an
> empty `data/gold/` (OPEN-025). Nothing here describes any real person.

- Generated: 2026-09-21
- Provenance: PROVISIONAL -- planted-label corpus-property measurement, NOT accuracy. data/gold/ is empty (OPEN-025); no real athlete text exists (OPEN-011).
- Detector: `CONSTRUCT_CUES` (the evaluated cue list, **not** the widened
  dashboard one -- see `docs/dashboard.md`)
- Pure Python, no checkpoint, no network. Reproduce with
  `python scripts/run_abstention_report.py`.

## 1. What this measures, and why it did not exist before

Every macro-F1 in `reports/results.md` is computed over inputs assumed to
be scorable. `CLAUDE.md` sec.12.3 argues in prose that unscorable input
produces an index of exactly 0.50 -- a score of 50 out of 100 with a band
and ten tiles beneath it -- and three gates were built on that argument.
This page is the first measurement of them.

The question asked of every input is not only *was it refused* but **what
would it have scored had it not been**. A refusal rate alone says a gate is
opinionated. The counterfactual says what the opinion was worth.

## 2. The cost of the gates (false refusals)

The corpus is text the system *should* score. Refusals here are pure cost.

| set | n | refused | refusal rate | flagged off-register |
|---|---|---|---|---|
| `gold_dev` + `gold_eval` | 500 | 1 | **0.2%** | 78 (15.6%) |

The gates cost 0.2% of legitimate text. That is the
honest price, and it is small.

## 3. The finding: the gates close the narrowest of three routes

An index of exactly 0.50 is reached three ways, and only the first is a
gate's business. Separating them is what this report adds, because the
three have different fixes and the prose in `CLAUDE.md` sec.12.3 describes
only one.

| route | what happened | does a gate stop it |
|---|---|---|
| `refused` | input was not language; never reaches the scorer | **yes** |
| `no_detection` | good text, detector fired on nothing | no |
| `all_inert` | good text, constructs detected, all directionally unresolved so all weighted 0 | no |

Over the corpus:

| route | n | share of corpus |
|---|---|---|
| `refused` | 1 | 0.2% |
| `no_detection` | 293 | 58.6% |
| `all_inert` | 62 | 12.4% |
| `moved` | 144 | 28.8% |

**355 of 500 corpus texts (71.0%) are admitted, scored, and handed
back exactly 0.50 anyway.** No gate in the system addresses either route.
The refusal gate prevented 1 of them.

The `all_inert` row is the sharper half: 62 texts
light up construct bars on the dashboard and still produce the midpoint,
because the conservative default polarity policy weights a directionally
unresolved construct at zero. A reader sees evidence and a neutral score at
the same time, which is the most misreadable state the interface has.

**This contradicts the comfortable version of the argument.** The gates were
built to stop a vacuous 0.50 and they do -- for the input class that makes up
0.2% of corpus traffic. The class that makes up
71.0% is untouched by them.

## 4. True refusals, by junk class

**Authored by this project, and weak in a stated way**: these are shapes the
project imagined a paste box or a camera catching, not a sample of user
submissions. Sanity check, never a field estimate.

| class | n | refused | rate | refusal reasons | at midpoint |
|---|---|---|---|---|---|
| `empty_extraction` | 3 | 3 | 100.0% | `empty`x3 | 3 |
| `keyboard_mash` | 4 | 4 | 100.0% | `not_english`x1, `not_words`x2, `too_short`x1 | 4 |
| `symbols_and_digits` | 3 | 3 | 100.0% | `not_letters`x3 | 3 |
| `too_short` | 4 | 4 | 100.0% | `too_short`x4 | 4 |
| `off_register` | 7 | 0 | 0.0% | -- | 7 |

Non-language junk is refused 14 of 14 (100.0%). Counting `off_register`, which is deliberately not refused, the figure over all 21 authored items is 14.

`off_register` is the control and it is **not** refused, by design: under
`CLAUDE.md` sec.12.2 the register test decorates and never gates. Those
texts are real English about the wrong subject, so `admit` passes them,
`judge` flags them, and they are scored. Every one lands on the midpoint --
which is the `no_detection` route again, arriving from a different door.

## 5. What this does not establish

1. **The positives are synthetic** (OPEN-011). The false-refusal rate is
   measured against the register this project's own generator writes.
2. **The junk is authored** by this project (sec.4 above).
3. **The counterfactual uses the lexicon**, not the transformer. The 0.50
   result is a property of the fusion layer given all-zero probabilities; a
   transformer emits small non-zero probabilities on junk and would cluster
   *near* the midpoint rather than on it. That is a weaker statement and it
   is not the one made here.
4. **No claim is made that refusing was correct** in any individual case
   beyond the authored classes. There is no human judgement of refusals,
   because that needs the annotators OPEN-025 is waiting on.
