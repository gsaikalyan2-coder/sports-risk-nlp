# Handover — end of Phase 18 → start of Phase 19

Self-contained. A new session should be able to continue from this file alone,
after reading `CLAUDE.md` (which overrides defaults).

---

## Part A — Project summary

**Project.** Pre-Competition Psychological Risk Profiling of Athletes. NLP ×
sports psychology: detect 10 validated constructs (CSAI-2 / SDT / ABQ tradition)
in athlete text and fuse them into an interpretable risk index. Target: IEEE
conference paper. Owner: Saikalyan, sophomore, SRMIST.

**Timeline.** ~3 weeks to code freeze. Paper draft due first week of September
2026. Today is 2026-08-13.

**Phase just completed: Phase 18 — evaluation harness and ablations.**
Phases 1–15 and 17 complete. Phase 16 (DataRobot AutoML) skipped by decision.

### THE CONSTRAINT THAT GOVERNS EVERYTHING — carry this forward verbatim

`data/gold/` is empty. **No number in this repository is an accuracy.** Every
result is a corpus property of a synthetic template grammar (`synth_precomp_v1`,
4,000 generated records, labels planted by the generator). Never report a figure
as accuracy. Never write to `data/gold/`. Never weaken the `--gold` refusal in
`src/models/dataset.py`.

Phase 17's corollary still holds: **an attribution is a claim about the model,
not about athlete psychology.**

Phase 18 adds a third: **a gate that certifies a claim is only as good as what it
actually checks.** See OPEN-034 below — this session's gate went green over a
claim its own evidence contradicted.

---

## Part B — What was done this session

### B0. Phase 17 intake — OPEN-033 closed

The owner ran `scripts/run_explain.py` on 2026-08-12. All artefacts exist and are
consistent: 129 of 150 sampled records attributed, **comprehensiveness margin
+0.328** over the random control, sufficiency margin +0.170, and all ten
constructs beat their control individually. The predicted `inputs_embeds`
friction did not materialise. **OPEN-033 is closed.**

The expert-agreement half of Phase 17 remains OUTSTANDING. That is OPEN-004, not
OPEN-033: a run that produces artefacts is not a study that produced ratings.

### B1. Approach decisions (owner-confirmed before any code)

| Question | Decision |
|---|---|
| ± silver ablation | **Cheap classical arm + documented refusal of the transformer arm.** OPEN-028 makes the transformer arm ten CPU-hours to measure the effect of adding noise. |
| ± risk fusion ablation | **Structural sensitivity analysis.** No observed risk outcome exists; a proxy target from planted labels would be circular. |
| Compute architecture | **Cache predictions once, pure Python downstream.** |

### B2. Files created

| File | What it is |
|---|---|
| `src/evaluation/harness.py` | `PredictionSet` (the cache), scoring with bootstrap CIs, paired `compare_systems`, structural `error_profile`. Pure Python. |
| `src/evaluation/ablations.py` | `Ablation` + `AblationStatus`, the silver refusal, `risk_sensitivity`, `CLAIMS` and `ClaimLedger` (the gate). Pure Python. |
| `scripts/run_evaluation.py` | Two-mode runner: `--cache-predictions` (needs torch) then the pure-Python scoring/ablation/report pass. |
| `tests/test_evaluation_harness.py` | **37 tests, all passing, none requiring torch.** |

Modified: `src/evaluation/__init__.py` (exports), `docs/open_issues.md`,
`PROJECT_PLAN.md` (status board rewritten; the Phase 9 board retained below it).

### B3. The architecture decision worth carrying forward

**Predicting and scoring are separate programs.** The model runs once into
`reports/predictions/*.json`; everything after that is arithmetic over the cache.
Consequences, all of which paid for themselves this session: ablations rerun in
seconds rather than hours, the entire test suite runs with no ML stack, and two
runs of the same number cannot differ because the model was reloaded in between.

This is the third phase built this way (`src/risk/` at 15, `src/explainability/`
minus `attribution.py` at 17). It is now the project's default shape and Phase 19
and 20 should follow it.

### B4. The defect this session found, and it is the important part

**The claim gate passed while certifying a claim its own evidence refuted.**

The Phase 18 gate is *"every claim the paper will make is backed by a logged
experiment"*. It was implemented as: enumerate the claims, look up each one's
evidence key in `results.json`, fail if missing or empty. First real run: seven
claims, all green.

One of them was wrong. `silver_is_noise` read *"training on it degrades rather
than improves a model"*. The ablation had just measured **delta = +0.033 at
p = 0.110** — no significant change, point estimate pointing the *opposite* way.
The gate saw a populated key and stopped looking.

**A gate that only checks that a result exists is worse than no gate**, because
it launders the claim: the next reader sees "backed: yes" and never rereads the
number.

It is the Phase 17 defect in new clothes — there, an ethics guard passed its own
test while being bypassable through a different field. Same shape both times:
*the check and the thing it protects were related by assumption, not by
construction.* Expect a third instance; look for it in Phase 20's dashboard,
where "the card renders" will be tempting to accept as "the card is honest".

Fixed by giving `Claim` an optional `predicate` over the resolved evidence, and
by **rewording the claim to match the measurement**. The distinction is written
into the gate's own failure message: rewording a claim to fit the experiment is
legitimate; loosening a predicate to fit a claim is not.

### B5. What was and was not executed

**Executed here:** the entire step-2 pipeline end-to-end against a scratch cache
in `/tmp` — scoring, all three ablations, the claim ledger, four SVG figures,
`results.md` and `results.json`. 37 new tests plus `test_explainability.py` and
`test_evaluation.py` (90 passing together).

**A meaningful cross-check fell out of it.** The classical rows produced by the
new harness reproduce the published Phase 13 numbers *exactly* — lexicon 0.462,
TF-IDF+LogReg 0.222 template-disjoint, 0.999 on the random split. The new harness
and the Phase 13 harness agree to three decimals on the same data.

**Not executed:** `--cache-predictions` against the real checkpoint. The sandbox
has no torch and runs Python 3.10, not 3.11. Logged as **OPEN-035**, not glossed.
The untested surface is ~40 lines calling only APIs Phases 14 and 17 already
exercised (`TransformerBaseline.load`, `predict_proba`, `predict`, `manifest`).

*(One pre-existing test fails in the 3.10 sandbox only:
`tests/test_risk.py::test_the_gate_refuses_gold_while_the_directory_is_empty`,
because `scripts/run_risk.py` imports `datetime.UTC`, which is 3.11+. Not a
Phase 18 change; it passes on the owner's 3.11.)*

---

## Part C — Phase 19 handoff

### C0. Do this first — run the phase

```
python scripts/run_evaluation.py --cache-predictions    # step 1, needs torch, ~5-15 min CPU
python scripts/run_evaluation.py                        # step 2, seconds
python -m pytest tests/test_evaluation_harness.py -q    # expect 37 passed
```

Then read `reports/results.md` and check four things:

1. **`transformer_beats_lexicon` is backed.** Phase 14 measured 0.588 vs 0.462 at
   p = 0.000, so it should be. If it is not, that is a finding about the harness
   or the checkpoint — investigate, do not relax the predicate.
2. **The per-construct table.** A single macro-F1 hides a model that is competent
   on some constructs and blind on others. The spread is what Phase 19's
   narrative is actually about.
3. **`zeroed_constructs` in the risk sensitivity block.** On the scratch run,
   **4 of 10 constructs never moved the risk index** — the polarity-bearing ones,
   left inert by the conservative `PolarityPolicy.NEUTRAL` default. If that holds
   on the real probabilities, the paper cannot describe the decomposition as
   ten-construct without qualification.
4. **`naive_rho` in the same block.** It is the rank correlation between the risk
   index and a plain count of detected constructs. Near 1.0 would mean the
   taxonomy weighting buys interpretability but not discrimination — reportable
   either way, and dishonest to omit.

Then record the outcome in `docs/open_issues.md` under OPEN-035.

### C1. Open items, in priority order

- **OPEN-004 — no practitioner rater.** Longest lead time, now 4 phases overdue.
  The instrument exists; only recruitment remains. Contact SRMIST sports-dept
  coaches and sport-psych staff. Pair with the A3 recruitment — same population,
  one conversation, and it also moves OPEN-011.
- **OPEN-011 — still no real athlete text.** The project's live highest risk;
  contribution #1 needs it.
- **OPEN-035 (new)** — closes on the first successful `run_evaluation.py` pair.
- OPEN-025 — A2 recruited, kappa computable but not yet performed.
- OPEN-028 — now has *measured* evidence rather than an assertion.
- OPEN-030 / 031 / 032, OPEN-005 / 006 — before submission.

**OPEN-034 is closed** and is recorded for its lesson, not as outstanding work.

### C2. Working rules — unchanged

- Teach while doing; the owner is a sophomore. Concise in chat, depth in files.
- Small verifiable steps; end non-trivial work with a verification step.
- `pytest` excludes `-m slow` by default. Run those with `pytest -m slow`.
- Python 3.11.
  `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu`
- Do **not** retrain — `TransformerBaseline.load(path)` restores the model with
  its tuned thresholds, and `run_evaluation.py --cache-predictions` uses `load`
  precisely so the paper's model cannot silently change.
- Ethics binding: no claim about any identifiable person; **no verbatim corpus
  text** in the paper / dashboard / figures; no individual-level output. The
  Phase 18 error analysis is structural for this reason.
- **Produce a handover file at the end of every phase. Do not start the next
  phase until the owner confirms receipt.**

### C3. Ready for Phase 19 (results aggregation & narrative)

Phase 19 decides the story the data tells and writes `docs/findings.md`. It needs
no new machinery — everything it consumes now exists:

- `reports/results.json` — every score, comparison and ablation, machine-readable.
- `src/evaluation/ablations.py::CLAIMS` — **start here.** It is already the list
  of claims the project believes it has earned, each with a pointer to its
  evidence. `docs/findings.md` should be the prose form of that ledger, and any
  headline finding that is not in `CLAIMS` needs a row added *before* it is
  written into the narrative.
- `reports/explain/explain.md` — the faithfulness numbers.
- `reports/figures/phase18_*.svg` — four paper figures already rendered.

**Three candidate headline findings, in the order the evidence supports them:**

1. **The memorisation gap.** A linear model over TF-IDF scores 0.999–1.000 on a
   random split and 0.222 template-disjoint. That is a result about evaluating
   synthetic corpora, not a diagnostic, and it is the most transferable thing
   this project has measured.
2. **Two-level interpretability with a measured faithfulness margin** (+0.328
   over a random control), which is the headline contribution — but it is
   *pilot* expert-review until OPEN-004 moves, and the wording must match the
   raters.
3. **Negative results, reported as results:** silver supervision bought nothing;
   the risk index cannot be calibrated because no outcome exists; four constructs
   are inert in the fusion layer.

**Do not start Phase 20 (dashboard) before Phase 19.** The Phase 17 cards are the
dashboard's rendering layer; do not reimplement them there, or the paper figure
and the dashboard will drift apart.

---

**Phase 18 is complete pending the owner's run on the real checkpoint.
Do not start Phase 19 until receipt of this file is confirmed.**
