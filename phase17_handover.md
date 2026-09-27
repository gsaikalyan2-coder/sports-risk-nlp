# Handover - end of Phase 17 → start of Phase 18

Self-contained. A new session should be able to continue from this file alone,
after reading `CLAUDE.md` (which overrides defaults).

---

## Part A - Project summary

**Project.** Pre-Competition Psychological Risk Profiling of Athletes. NLP ×
sports psychology: detect 10 validated constructs (CSAI-2 / SDT / ABQ tradition)
in athlete text and fuse them into an interpretable risk index. Target: IEEE
conference paper. Owner: Saikalyan, sophomore, SRMIST.

**Timeline.** ~3 weeks to code freeze. Paper draft due first week of September
2026. Today is 2026-08-12.

**Phase just completed: Phase 17 - explainability + expert validation.**
Phases 1–15 complete. Phase 16 (DataRobot AutoML) skipped - no account, and
uploading athlete text to a third-party cloud breaks the "reviewer reproduces
with no account" property established in Phase 6.

### THE CONSTRAINT THAT GOVERNS EVERYTHING - carry this forward verbatim

`data/gold/` is empty. **No number in this repository is an accuracy.** Every
result is a corpus property of a synthetic template grammar (`synth_precomp_v1`,
4,000 generated records, labels planted by the generator). Never report a figure
as accuracy. Never write to `data/gold/`. Never weaken the `--gold` refusal in
`src/models/dataset.py`.

Phase 17 adds a corollary that Phase 18 must not lose: **an attribution is a
claim about the model, not about athlete psychology.** A faithful explanation of
this model may be faithfully describing template giveaways.

---

## Part B - What was done this session

### B1. Approach decisions (owner-confirmed before any code)

| Question | Decision |
|---|---|
| Attribution method | **Integrated Gradients + SHAP Partition, cross-checked.** Attention rollout deliberately NOT used as a headline method - attention weights are not explanations and a reviewer will say so. |
| Expert study given OPEN-004 | **Build the instrument now, run as a pilot with sports-familiar raters, keep recruiting.** Rater population is fixed on the sheet at generation time so the claim matches the raters. |
| Faithfulness metrics | **Yes** - comprehensiveness / sufficiency vs a random control, reported alongside expert agreement. |

### B2. Files created

| File | What it is |
|---|---|
| `src/explainability/attribution.py` | IG (embedding path-integral, midpoint rule, pad baseline, completeness residual reported) + SHAP Partition. Character-offset spans throughout. |
| `src/explainability/faithfulness.py` | Comprehensiveness / sufficiency AOPC vs random control; Spearman + top-k Jaccard for IG-vs-SHAP agreement. **Pure Python** - model enters via a `predict_fn` callable. |
| `src/explainability/cards.py` | Two-level cards: span→construct joined to `src/risk/fusion.py`'s construct→risk contributions. Ethics guards enforced in code. |
| `src/explainability/study.py` | Blinded rating sheet + answer key; approval rates, control margin, Cohen's kappa. |
| `src/explainability/__init__.py` | Package exports. |
| `scripts/run_explain.py` | Phase 17 runner and gate. Also `--score-study` mode. |
| `tests/test_explainability.py` | 23 tests, **all passing**, none requiring torch. |
| `docs/expert_validation_protocol.md` | Full protocol with reporting thresholds fixed in advance. |

Modified: `docs/open_issues.md` (OPEN-004 updated).

### B3. Architecture decision worth carrying forward

**Only `attribution.py` touches torch, and it does so lazily.** Everything else
is pure Python, mirroring how `src/risk/` was built in Phase 15. Consequences:
the light Docker image still works, and the entire test suite runs with no ML
stack - which is why the invariants below are actually tested rather than
nominally tested.

### B4. Two real defects found by testing, both fixed

1. **Span text was reconstructed from token strings**, losing whitespace and
   producing spans like `shakingbefore`. Those go straight onto rating sheets and
   into paper figures, where a mangled phrase reads as a defect in the model.
   Fixed by carrying `source_text` on `ConstructExplanation` so a span is always
   a genuine substring. Regression test asserts `span.text == text[start:end]`.

2. **Zero-scored tokens welded whole records into one span.** Zero is
   non-negative, so under the same-sign merge rule a zero-scored token sat
   between two positive ones and joined them - a record with mostly-zero
   attributions merged into a *single span covering the entire text*. That
   highlights everything (so explains nothing) **and silently defeated the
   redaction guard**, because "show only the spans" then showed the whole
   record. Fixed at the root (zero-scored tokens break spans) and defensively
   (`covers_whole_record` suppresses spans in redacted renders). Two regression
   tests.

The second one is the more instructive: an ethics guard was passing its own test
while being fully bypassable through a different field.

### B5. Ethics enforced mechanically, not documented

- `ExplanationCard` cannot be constructed without provenance.
- `render_markdown(redact=True)` withholds the record and suppresses spans that
  would reproduce it.
- `assert_publication_safe` refuses cards whose record is not `synthetic`. Today
  a no-op - every record is synthetic. It stops being a no-op the week real A3
  donated text arrives, which is the week the mistake is most likely.

### B6. Gate status

`PROJECT_PLAN.md` Phase 17: *explanations are span-level and construct-specific;
expert agreement reported.* Deliberately split, because no code can make a human
rate anything:

| Half | Status |
|---|---|
| Span-level & construct-specific (structural) | **Implemented and tested.** Awaiting the owner's run for the measured artefacts. |
| Attributions beat their random control | **Measured by the runner.** Not yet run on the real model. |
| Expert agreement reported | **OUTSTANDING.** Instrument built; needs raters. |

`explain.md` states the expert half is outstanding rather than showing a blank
table that reads as a pass. A green exit code must never stand in for a study
that never happened - the OPEN-007 lesson.

### B7. What was NOT run, and why

**`scripts/run_explain.py` has not been executed against the real checkpoint.**
This session's sandbox has no torch: `download.pytorch.org` is blocked by the
proxy and only ~3 GB of disk is free, so the CUDA wheel from PyPI will not fit.

This is the same class of risk as OPEN-007 (code written, never executed) and it
is logged as **OPEN-033** below rather than glossed. Mitigation: everything that
could be verified without torch was verified, against hand-built attributions and
a stub scorer - including the faithfulness arithmetic (a known-correct
explanation beats its control; a known-misleading one does not), the blinding,
and the kappa against a hand-computed value.

Expected first-run friction is in `IntegratedGradients.attribute`, which is the
only genuinely new torch code: `inputs_embeds` + `attention_mask` forward passes
and `torch.autograd.grad` against a 6-layer distilroberta.

---

## Part C - Phase 18 handoff

### C0. Do this first - run the phase (~30–60 min CPU)

```
python scripts/run_explain.py --limit 40 --shap-limit 8     # smoke run
python scripts/run_explain.py                               # full run
python -m pytest tests/test_explainability.py -q            # expect 23 passed
```

Then read `reports/explain/explain.md` and check three things:

1. **Comprehensiveness margin > 0.** If it is not, the explanations are not
   evidence of anything and that is the finding - do not tune until it is.
2. **Completeness residuals in `attributions.json` are small** relative to the
   logits. If large, raise `IntegratedGradients.n_steps` from 32.
3. **`unevidenced_rate` in the card summary.** Constructs moving the risk index
   with no supporting span are the model asserting what it cannot point at.

Then send `reports/explain/rating_sheet.md` to two raters -
**not** `rating_sheet_KEY.json`.

### C1. Open items, in priority order

- **OPEN-004 - no practitioner rater.** Longest lead time, 3 phases overdue.
  Instrument now exists; only recruitment remains. Contact SRMIST sports-dept
  coaches and sport-psych staff. Pair with the A3 recruitment - same population,
  one conversation, and it also moves OPEN-011.
- **OPEN-011 - still no real athlete text.** The project's live highest risk;
  contribution #1 needs it. A1 exhausted, A5 blocked by Reddit 403 (OPEN-031),
  A3 consented donation live but nothing collected.
- **OPEN-033 (new) - `run_explain.py` never executed.** Closes on the first
  successful run; record the outcome in `docs/open_issues.md`.
- OPEN-025 - A2 recruited, kappa computable but not yet performed.
- OPEN-030 / 031 / 032, OPEN-005 / 006 - before submission.

### C2. Working rules - unchanged

- Teach while doing; the owner is a sophomore. Concise in chat, depth in files.
- Small verifiable steps; end non-trivial work with a verification step.
- `pytest` excludes `-m slow` by default. Run those with `pytest -m slow`.
- Python 3.11.
  `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu`
- No HF token needed. Full transformer sweep ~5h CPU; do **not** retrain -
  `TransformerBaseline.load(path)` restores the model with its tuned thresholds.
- Ethics binding: no claim about any identifiable person; no verbatim corpus text
  in the paper / dashboard / figures; no individual-level output.
- **Produce a handover file at the end of every phase. Do not start the next
  phase until the owner confirms receipt.**

### C3. Ready for Phase 18

- `TransformerBaseline.load(path)` - model + tuned thresholds, construct-order
  guarded.
- `predict_proba()` - per-construct probabilities.
- `src/risk/fusion.py` - per-construct contributions to the risk index.
- `src/explainability/` - attribution, faithfulness, cards, study. The cards are
  the Phase 19 dashboard's rendering layer; do not reimplement them there, or the
  paper figure and the dashboard will drift apart.

### C4. Phase 14 numbers, for reference

- distilroberta-base lr2e-5 bs16 ep6 → macro-F1 **0.588** [0.549, 0.624]
  template-disjoint
- vs lexicon bar 0.462: **+0.126**, paired bootstrap **p=0.000** → gate PASS
- random split 0.905 → **memorisation gap +0.317**
- Phase 15: per-construct ECE computed; risk-index calibration deliberately NOT
  computed - no observed risk outcome exists and `calibrate_risk_index` raises
  rather than substituting a proxy.

---

**Phase 17 is complete pending the owner's run and the rater recruitment.
Do not start Phase 18 until receipt of this file is confirmed.**
