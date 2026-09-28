# Annotation Tooling (Phase 11)

**Governs:** `src/annotation/`, `scripts/run_annotation.py`, `config/annotators.yaml`,
`data/gold/`
**Tool:** [Potato](https://github.com/davidjurgens/potato) - "the portable annotation tool",
pinned at **2.7.1**
**Status:** built and verified 2026-08-10. **Updated 2026-09-28: `gold_dev` is annotated by A1
alone (96/100 valid spans). A2 agreed on 2026-08-12 but never annotated anything, and the owner
decided to close OPEN-025 by dropping the inter-annotator-agreement claim rather than wait
further. As a direct consequence, `src/annotation/agreement.py` was deleted (backup under
`annotation/gold_dev/_backup_2026-09-28/removed_20260928/`), and `--agreement` no longer exists
on `scripts/run_annotation.py`. Sections 7 and 10.2 below describe that deleted system and are
kept for the historical record of what it computed and why, not as current behaviour.** See
`CLAUDE.md` sec.20-21 for the full reasoning.

---

## 1. Why a tool at all

The rubric asks for span-anchored, multi-label, graded annotation: ten constructs, each with
an intensity 0–3, each non-zero label carrying at least one span, plus a modifier, two flags
and a note. Over 400 items, twice.

In a spreadsheet or raw JSONL that means a person hand-typing character offsets several
thousand times. Offsets typed by hand are wrong often enough to be the dominant error source,
and a wrong offset is invisible: it looks like a valid label and silently misattributes the
construct to the wrong words. Since span-level explanation is contribution #2, that failure
would corrupt the thing the paper is about.

Potato removes the class of error entirely - the annotator drags over text and the tool
records the offsets.

## 2. Why Potato, and why not the other repo

Two candidates were considered.

**Potato** (`davidjurgens/potato`) - a Flask + YAML annotation server from the Jurgens lab.
Config-driven, multi-annotator with a closed user list, and it ships the exact schemes this
rubric needs: `span` with labelled highlights, `radio`, `multiselect`, `text`, and
`pure_display` for read-only context. Adopted.

**`sciknoworg/ALD-E-ImageMiner`** - **rejected, and the reason is worth recording.** It is
not a general annotation tool. It is a domain-specific *dataset* project for annotating
**figures and images** from atomic-layer-deposition and etching papers - chart-type
classification, data extraction from plots, and multimodal QA with Qwen2.5-VL. Our task is
span-level construct labelling over English text. The two share the word "annotation" and
nothing else.

One thing *was* taken from it: its **pilot-annotation-task → full-annotation-task** phasing,
which is exactly this project's `gold_dev` → `gold_eval` calibration order, and its
`onboarding/` directory convention. Structure, not code.

## 3. Integration: generated, not vendored

`src/annotation/potato_project.py` **emits** a Potato project; Potato itself is installed
separately with `pip install potato-annotation==2.7.1`. Three consequences, all deliberate:

- **The taxonomy stays the single source of truth.** A hand-written UI config is a second
  copy of `config/taxonomy.yaml` that drifts, and a gold set annotated against a stale rubric
  is worse than no gold set. A test asserts every construct in the taxonomy reaches the
  screen.
- **The Docker image is unchanged.** Potato pulls Flask and its tree; the Phase 2 layering
  decision keeps the light image light, and annotation happens on a laptop, not in a
  container.
- **Reproducibility is by pin, not by copy.** The version is pinned here and in the generated
  README. A reviewer reproducing the artifact regenerates the project and installs the same
  Potato version.

## 4. The layout, and the two decisions inside it

| Scheme | Type | Carries |
|---|---|---|
| `context` | `pure_display` | the **parent record**, target sentence `<mark>`ed |
| `evidence` | `span` | construct identity, one label per graded construct and one per categorical pole |
| `intensity_<construct>` ×10 | `radio` | 0–3 |
| `interpretation_modifier` | `radio` | facilitative / debilitative / unclear |
| `flags` | `multiselect` | `low_resilience_explicit`, `uncertain` |
| `note` | `text` | free text, no clinical language |

**Spans carry construct identity; radios carry intensity.** Potato spans hold no magnitude,
so the two halves of a label need two mechanisms. Categorical constructs use
`construct:pole` span labels, which is what makes each pole span-anchored - guidelines sec.2b
requires a span for *each* pole when `mixed` is used, and that is unrepresentable with one
label per construct. `mixed` is therefore **derived** from two poles being marked, not
offered as a button: a button can be pressed without evidencing either side.

**Context is displayed, not annotated.** The target utterance is Potato's `text`, so span
offsets land on the utterance and stay comparable with `InterimRecord.char_start/char_end`,
with `SilverLabel.evidence_spans`, and with whatever Phase 16 highlights. See §5.

## 5. The defect this phase opened with

`docs/annotation_guidelines.md` sec.3 step 1: *"Read the whole record once before marking
anything. Context changes labels."*

`gold_eval.jsonl` carried `parent_record_id` but **not the parent text**. An annotator opening
it could not follow step 1. Measured:

| Batch | Items | Gain multi-utterance context | Mean parent tokens | Mean target tokens |
|---|---|---|---|---|
| `gold_dev` | 100 | 84 (84.0%) | 43.2 | 18.5 |
| `gold_eval` | 400 | 301 (75.3%) | 35.1 | 17.7 |

Three quarters of the evaluation set gained roughly twice as much text to judge from.

It matters twice. **Agreement:** `appraisal_orientation` is a stance toward an event and a
17-token clause frequently does not carry one; two annotators guessing from a fragment
disagree, and the kappa then measures the fragment. **Fairness:** the Phase 10 labeller *was*
given the parent record (`docs/labeling.md` sec.3 - it is why deduplication saved 0.5% instead
of 31%). Humans annotating without it would make the Phase 14 comparison a measurement of
context asymmetry. The annotation view now shows **the same context the model saw**, and a
test asserts the reconstruction is the same one.

## 6. `data/gold/` is human-owned - how that survives a module that writes to it

Three stores refuse `data/gold/` outright. `src/annotation/store.py` writes there, which looks
like the rule being relaxed at the first inconvenience. It is not.

`CLAUDE.md` sec.4 means the *content* originates from a person's judgement, not that no code
may ever write the bytes - read literally, gold could never exist. Four locks enforce the
purpose:

1. **`GoldLabel` has no machine author.** `author_kind` accepts only `human`.
2. **The annotator must be on the roster** in `config/annotators.yaml`.
3. **Writing requires an `Annotator` object**, and `scripts/run_annotation.py` only obtains one
   from a mandatory `--annotator` argument - a human types their own id every time.
4. **Silver cannot become gold.** `SilverLabel` is a different type with a `confidence` and no
   `annotator_id`, and `ingest_potato` is the only producer of `GoldLabel`s.

**What this does not protect against, stated plainly:** someone can hand-write fabricated
annotations under their own roster id. No schema stops research fraud. The locks stop the
realistic failure - a future session deciding silver labels are "good enough" to seed gold.

## 7. Agreement: four numbers, never one (REMOVED 2026-09-28, kept for the record)

**This section describes `src/annotation/agreement.py`, which no longer exists.** Kept as-is
below because it explains a real design, in case a future annotator makes IAA measurable again
and this needs rebuilding from the backup. See the file header above and `CLAUDE.md` sec.20-21.

| Statistic | Question |
|---|---|
| Cohen's kappa, per construct | do they agree on *whether* it is expressed, above chance? |
| Quadratic-weighted kappa | do they agree on *how strongly*, treating 0-vs-3 as worse than 2-vs-3? |
| Percent agreement | the raw number, always beside kappa |
| Span F1 (token overlap) | given they agreed on the construct, did they find the same evidence? |

**Per-construct, never a single headline.** `config/taxonomy.yaml` freezes the construct set at
Phase 12 *"after checking annotation burden and inter-annotator agreement. Any construct with
poor agreement is a candidate to drop."* That check is impossible against an average - a macro
kappa of 0.6 hides `burnout_signal` at 0.2, and `burnout_signal` is the most clinically loaded
label in the taxonomy.

**The kappa paradox is reported, not hidden.** Several constructs are rare, and Cohen's kappa
collapses when one category dominates: annotators can agree on 97% of items and score near
zero. Every row therefore carries prevalence, raw agreement and counts, and the
`interpretation` column says plainly when a low kappa is a prevalence artefact. That
distinction decides whether a construct is dropped at Phase 12, so it is not left to the
reader.

**Undefined is not zero.** A construct neither annotator ever marked reports UNDEFINED, not
0.0. Span F1 uses token overlap rather than exact match, because two careful people routinely
differ on whether to include a leading "I keep", and scoring that as total disagreement would
say nothing useful.

**No human-vs-silver agreement is computed here.** That is a measurement of the model and
belongs to Phase 14 under a name that says so.

## 8. Workflow

```bash
# 1. build the calibration project
python scripts/run_annotation.py --build --batch gold_dev

# 2. both annotators label ALL of gold_dev, independently
pip install potato-annotation==2.7.1
cd annotation/gold_dev && potato start config.yaml

# 3. ingest each pass (each person runs this with their OWN id)
python scripts/run_annotation.py --ingest --batch gold_dev --annotator A1

# 4. only now: the evaluation set
python scripts/run_annotation.py --build --batch gold_eval
```

**(2026-09-28) There used to be a step 4 here** - `--agreement --batch gold_dev`, comparing two
passes before opening `gold_eval`. It was single-annotator by decision and removed along with
`src/annotation/agreement.py`; see the file header above.

**The order is load-bearing.** `gold_dev` is drawn from *training-side* templates precisely so
that burning it on rubric arguments costs zero evaluation power. An item read during an
argument about the rubric is no longer an independent measurement.

**Do not discuss specific records until both passes are done** (guidelines sec.7). It inflates
agreement, it cannot be undone, and it makes the headline statistic worthless.

## 9. Verification performed

- Both generated projects pass **Potato 2.7.1's own validator**, `python -m
  potato.validate_cli <config> --strict`: *"OK - no issues found."* That check caught a real
  defect: an `html_layout` key carried over from an older Potato API, pointing at a template
  this project does not ship. It was deleted rather than justified.
- 48 tests in `tests/test_annotation.py`, all offline.
- One test asserts the shipped roster has exactly one annotator - if it starts failing,
  someone has been recruited.
- **13 tests in `tests/test_potato_output.py` run against output written by Potato 2.7.1's
  own serialiser** (recorded under `tests/fixtures/potato/`), including a check that the raw
  `user_state.json` and the JSONL export produce identical payloads, and an end-to-end run
  from two real passes to a kappa. See §8b for what that check found.

## 8b. What running against real Potato output found (OPEN-027)

The ingest path had been written against an *assumed* Potato interface and never executed
against the real one. It did not work. Three mismatches - the output lives in
`annotation_output/<user_id>/user_state.json` rather than any `.jsonl`; the item key is
`instance_id`; and **Potato spans carry `start`/`end` offsets and no surface text at all.**

The third was the dangerous one. `_collect_spans` silently skipped spans with no surface
text, so against real output every span would have vanished and the item would then have been
counted as "not yet annotated" - evidence lost without an error. `src/annotation/
potato_output.py` is the fix, and it makes the situation better than it was assumed to be:
because the surface text is now produced by slicing the utterance with Potato's own offsets,
**a gold evidence span cannot be a paraphrase.** The invariant `SilverLabel` enforces with a
check, gold gets by construction.

This is the second time in this project that "written carefully, never run" turned out to mean
"broken" (the first was the Phase 6 cost ledger, OPEN-024). OPEN-007 and OPEN-008 are the two
remaining unexecuted paths and should be assumed broken until executed.

## 10. Honest limitations

1. **No annotation exists.** The tooling is verified; the gold set is empty.
2. **There is no second annotator, by decision.** A2 agreed (2026-08-12) but never annotated;
   the owner chose to proceed on A1's single pass and drop the IAA claim rather than keep
   waiting (2026-09-28). Contribution #1 as originally framed ("with inter-annotator agreement
   reported") does not exist, and is named as a limitation in the paper rather than omitted.
   `src/annotation/agreement.py` was deleted as a result; see `CLAUDE.md` sec.20-21.
3. **Burden is unmeasured.** Ten intensity questions plus a span pass, per item, per
   annotator, over 400 items. `CLAUDE.md` sec.3 schedules exactly this check before the
   taxonomy freezes at Phase 12 - **time the `gold_dev` pass** and use the number. The
   generator supports a `constructs` filter so the set can be trimmed on evidence.
4. **Span F1 uses token overlap**, which is lenient. It rewards finding the same evidence, not
   the same boundaries, and the paper should say so.
5. **Potato's output format is version-coupled, and this is now a demonstrated risk rather
   than a theoretical one.** The parser was written against an interface Potato 2.7.1 does not
   have (§8b). `potato_output.py` handles both artifacts 2.7.1 writes and is defensive about
   shape, but it is not guaranteed against a future release. The pin in `POTATO_VERSION` is
   the mitigation, and **`tests/fixtures/potato/` must be regenerated if that pin is raised** -
   the recorded artifacts are the only thing that would catch the same class of change again.
6. **The recorded fixtures are a rehearsal, not data.** The judgements in them were produced
   by a script to exercise the parser; they carry no psychological meaning and must never be
   read as annotations.
6. **The corpus is still 100% synthetic (OPEN-011).** A real inter-annotator agreement figure
   over text no athlete ever said is a real number about an unreal corpus, and the paper must
   frame it that way.
