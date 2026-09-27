# Test fixtures

Artefacts used by the test suite. **Not corpus.** Nothing here is ingested, none
of it appears in `data/`, and none of it may be used for training or evaluation.

## `deid_cases.jsonl` - the de-identification recall fixture (OPEN-013)

### Why it exists

`data/raw/synth_precomp_v1` deliberately contains **no personal names**
(`src/ingestion/synthetic.py`). Inventing names risks colliding with real people
and the corpus needs no identifiers.

The side effect is that Phase 8's `deidentify.py` would be run against text with
nothing to remove, pass its gate trivially, and tell us **nothing about its
recall**. "Spot-check shows no identifiers remain" is a true and worthless
statement when made about text that never had any.

This fixture supplies the identifiers so recall becomes measurable.

### What is in it

Each line is one case:

```json
{
  "case_id": "name_simple_01",
  "category": "person_name",
  "text": "Marcus Halloway said the coach was happy with the session.",
  "expected": "[ATHLETE] said the [COACH] was happy with the session.",
  "expected_placeholders": ["[ATHLETE]", "[COACH]"],
  "difficulty": "easy",
  "notes": "Canonical given-name + surname in subject position."
}
```

Categories match the removal table in `docs/ethics.md` §5.1: `person_name`,
`handle`, `contact`, `url`, `team_org`, `location`, `event`, `date`,
`quasi_identifier`, `health` (removed entirely, not placeholdered), and
`negative` (text that must be left **unchanged**).

### Every name in this file is invented

No real athlete, coach, team, or event is named. Names were constructed to be
implausible as real public figures while remaining realistic in form. If any
string here matches a real person by coincidence, that is unintended - report it
via the contact route in `docs/ethics.md` §7.1 and it will be replaced.

### The negatives matter as much as the positives

A de-identifier that replaces everything scores perfect recall and destroys the
corpus. `docs/ethics.md` §5.2 requires typed placeholders precisely because
blanking "destroys the linguistic structure the model needs". The `negative`
cases - ordinary words that look name-like, sport nouns, weekdays, capitalised
sentence openers - catch over-redaction, and Phase 8 must report **precision as
well as recall**.

### How Phase 8 should use it

1. Run `deidentify.py` over each `text`.
2. Compare against `expected`.
3. Report **recall** (identifiers removed / identifiers present), **precision**
   (correct removals / total removals), and **exact-match rate**.
4. Report per `difficulty` band. Aggregate numbers hide that the easy cases pass
   and the hard ones do not.
5. Re-measure against real text when OPEN-011 is resolved, and report both.

Do not tune the de-identifier until it overfits this file. It is a smoke test
with teeth, not a benchmark - roughly 40 cases cannot certify a PII pipeline, and
`docs/ethics.md` §5.3 already names residual re-identification risk as a stated
limitation.
