# Implementation Report: Richer, Honest Facial-Cue Display

## Summary
Surfaced `hsemotion-onnx`'s eight expression-category scores (already computed,
previously discarded) as zero-weighted supporting detail alongside the two
weighted cues, on both pages that show a facial-cue reading. Reformatted every
facial-cue tile as a plain-English percentage instead of a raw `0.00` float.
Confirmed empirically that the eight scores are a genuine softmax distribution,
so the percentage framing is accurate rather than assumed.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium | Medium — matched |
| Confidence | 8/10 | Held — the one open question (softmax check) resolved cleanly, no other surprises |
| Files Changed | 7 | 6 (test_dashboard_pages.py needed no edit — verified only, per plan) |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Extend the feature name set | Done | `FACE_EXPRESSION_FEATURES` (8 names) added to `src/media/nonverbal.py`, unioned into `FEATURES` |
| 2 | Surface the 8-way scores | Done | Empirically confirmed scores sum to ~1.0 (0.99999996 in one sample run) before writing the copy that describes them as such |
| 3 | New unit tests | Done | 4 new tests, all passing, no stack-dependent test newly skipped |
| 4 | Copy — plain English | Done | `FACE_EXPRESSION_HEADLINE` / `FACE_EXPRESSION_PLAIN` added to `src/dashboard/copy.py` |
| 5 | Render — combined path (page 2) | Done | Percentage formatting + row-wrapped grid (5 per row) |
| 6 | Render — face-only path (page 2) | Done | Added unfiltered supporting-detail row before the existing `st.stop()` |
| 7 | Render — match-day page (page 6) | Done | Deviated from the plan's literal duplication instruction — see below |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis (ruff) | Pass | Zero errors on all 6 touched files |
| Unit Tests | Pass | `tests/test_facecues.py`: 26/26 (22 pre-existing + 4 new) |
| Full Test Suite | Pass | All tests green, 2 pre-existing skips unchanged (ML-stack-conditional, unrelated) |
| Build | N/A | Python/Streamlit project, no build step |
| Integration | Pass (partial) | Live model smoke-tested directly (see Deviations); full Streamlit UI not opened in-browser this session |
| Edge Cases | Pass | Degraded (8-only) row, key-drift, `FACE_WEIGHTS` disjointness all covered by new tests |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `src/media/nonverbal.py` | UPDATED | +17/-1 |
| `src/media/facecues.py` | UPDATED | +36/-2 |
| `src/dashboard/copy.py` | UPDATED | +11 |
| `dashboard/pages/2_Score_my_own_text.py` | UPDATED | +46/-12 |
| `dashboard/pages/6_Match_day_profile.py` | UPDATED | +57/-15 |
| `tests/test_facecues.py` | UPDATED | +46/-1 |

## Deviations from Plan

1. **Page 6's face-only block was not a clean mirror of page 2's original —
   it needed the same restructuring page 2 got, not a copy-paste.** The plan's
   Mandatory Reading table described page 6's face-only branch as rendering
   "2 weighted tiles only," matching page 2's *pre-change* shape. On inspection
   it was actually already iterating over every `face_features` entry
   unfiltered (not just the 2 weighted ones) but with no `is-inert` styling or
   "shown, weighted as zero" label — a pre-existing inconsistency the plan
   didn't anticipate. **WHY changed**: bringing it up to Task 6's standard
   (hero row = weighted only, percentage-formatted; separate supporting row =
   unweighted, labeled correctly) required different code than a literal
   mirror, not just the same code pasted in. **Impact**: same end state the
   plan wanted, reached by a different diff shape in that one block.
2. **The combined-path block on page 6 was closer to Task 5's target state
   than expected.** It already distinguished weighted vs. unweighted tiles
   with `is-inert` and correct labeling — only percentage formatting and
   row-wrapping were actually needed there, not the fuller rework Task 5
   specified for page 2. **WHY changed**: less code needed than planned, same
   outcome. **Impact**: none — smaller diff, same behavior.
3. **Verified the softmax assumption with a live model call before writing
   code**, rather than writing the code first and checking after (plan's Task
   2 GOTCHA suggested "verify empirically, once"). Ran `HSEmotionRecognizer`
   against a synthetic array and confirmed the 8 scores sum to 0.9999999572 —
   close enough to treat as a probability distribution. This was a smoke test
   against random noise (no real face features), not a real photograph — it
   confirms the *shape* of the model's output, not anything about accuracy on
   real faces, which this project makes no claim about anyway (`docs/ethics.md`
   §14.3).

## Issues Encountered

- The IDE's static analyzer flagged `Cannot find module src.media.nonverbal`
  in `tests/test_facecues.py` after adding the import. This is a pre-existing
  environment/tooling quirk (the analyzer's inferred import root does not match
  pytest's actual resolution, which uses `pyproject.toml`'s config) — every
  other import in that file uses the identical `from src....` form and the
  analyzer does not flag those, so this is very likely an IDE-side caching
  issue rather than a real problem. Confirmed harmless by running the actual
  test suite (pytest, not the IDE), which passed. Worth a restart of the
  language server if it persists, not a code fix.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_facecues.py` | 4 new (`test_a_full_row_carries_all_eight_expression_scores`, `test_a_degraded_eight_only_row_still_carries_the_breakdown`, `test_the_expression_keys_never_drift_from_the_declared_name_set`, `test_expression_scores_are_never_a_face_weights_key`) | `_features_from_scores`'s new expression-breakdown output, in both the full-row and degraded-row paths, plus the load-bearing invariant that `FACE_EXPRESSION_FEATURES` and `FACE_WEIGHTS` stay disjoint |

## Not Done In This Session

- **Manual browser validation** (`streamlit run dashboard/app.py`, visually
  confirming the 10-13 tile grid renders legibly and reads well) was not run
  interactively this session, given the session's cost budget. Everything the
  automated tests can check (honesty invariants, forbidden-vocabulary screen,
  stamp ordering, the risk-index-isolation property) passed. The plan's manual
  checklist is still worth running once before treating this as fully done —
  in particular, whether 5-per-row is actually the right wrap width, which is
  a visual judgment call no test can make.
- `CLAUDE.md` §13.2/§13.3 one-line addendum (plan's Completion Checklist item)
  was not added — this report substitutes for it for now; fold into `CLAUDE.md`
  when convenient.

## Next Steps
- [ ] Run `streamlit run dashboard/app.py` once, visually confirm the tile grid on both pages
- [ ] `/code-review` before committing
- [ ] `/prp-commit` — nothing has been committed yet; this branch (`feat/richer-honest-facial-cue-display`) has only the working-tree changes described above
- [ ] `/prp-pr` if you want a PR, or a direct commit to `main` matching this project's usual practice
