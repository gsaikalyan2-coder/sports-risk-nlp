# Plan: Richer, Honest Facial-Cue Display

## Summary
Phase 28's facial-cue reader (`src/media/facecues.py`) already runs a real, published,
trained model (`hsemotion-onnx`) and discards seven-eighths of what it computes: only
`negative_valence` and `arousal` reach the screen, as bare `0.00`-`1.00` floats in a
generic tile. This plan surfaces the model's own eight expression-category scores
(Anger, Contempt, Disgust, Fear, Happiness, Neutral, Sadness, Surprise) as zero-weighted
supporting detail, and reformats all ten numbers as plain-English percentages — without
ever presenting a single "detected emotion," a ranked winner, or language implying the
system knows how the person feels. The two weighted cues, their weights, and the
mandatory limitation text are unchanged.

## User Story
As a reader who uploaded a photograph under consent,
I want to see what the model actually computed, not just the two numbers it happens to weight,
So that the reading feels like transparent evidence rather than an opaque score, without the page overclaiming what a face can tell it.

## Problem → Solution
Current: two floats (`negative_valence 0.62`, `arousal 0.41`) in identical tiles to every
other context feature, no visibility into the model's native 8-way output, no plain-English
framing. → Desired: the same two weighted cues, described in plain English, plus an
explicitly zero-weighted "what the model's eight categories scored" panel, both carrying
the existing `FACE_CUES_LIMITATION` and both screened by the same honesty tests that
already gate this page.

## Metadata
- **Complexity**: Medium (follows an established pattern end-to-end; touches a fixed-name
  validation list, one model-output function, two near-duplicate page files)
- **Source PRD**: N/A
- **PRD Phase**: N/A
- **Estimated Files**: 7

---

## UX Design

### Before
```
+-------------------------------------------------+
| WHAT THE FACE IN THE PICTURE LOOKS LIKE          |
| (mandatory limitation text, unchanged)           |
|                                                   |
| negative valence      arousal                    |
| 0.62                  0.41                       |
| weight +0.20          weight +0.10               |
+-------------------------------------------------+
```

### After
```
+-------------------------------------------------+
| WHAT THE FACE IN THE PICTURE LOOKS LIKE          |
| (mandatory limitation text, unchanged)           |
|                                                   |
| Negative-looking       Activated-looking         |
| 62% (moved the score)  41% (moved the score)     |
| weight +0.20            weight +0.10             |
|                                                   |
| -- What the model's own eight categories scored, |
|    shown as context only -- none of this moved   |
|    the number above. --------------------------- |
| Anger 4%  Contempt 2%  Disgust 1%  Fear 6%        |
| Happiness 9%  Neutral 58%  Sadness 12%  Surprise 8%|
| (alphabetical order, not ranked by score -- no    |
|  "primary emotion" is named anywhere on this page)|
+-------------------------------------------------+
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Page 2, "non-verbal reading" section (both channels) | 2-5 generic tiles from `media_context`, raw floats | Same tiles, percentage-formatted, plus 8 new alphabetical tiles explicitly marked zero-weight | `len(media_context)` grows from 2-5 to 10-13; needs a wrapped grid, not one `st.columns()` row |
| Page 2, face-only branch | 2 weighted tiles only | 2 weighted tiles (percentage-formatted) + new "supporting detail" row of 8 | Currently filters `if k in media_weights`; the filter stays for the hero row, a second unfiltered row is added |
| Page 6 (match-day), face-only branch | Same 2-tile pattern, duplicated from page 2 | Same change, duplicated again | `src/dashboard/matchday.py` docstring states the duplication is deliberate (page-import rule); mirror, do not refactor |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/media/nonverbal.py` | 86-128 | `FEATURES` is a closed name set; `NonVerbalReading.__post_init__` raises on any feature name outside it. This is the load-bearing gotcha for the whole plan. |
| P0 | `src/media/facecues.py` | 334-380 | `FaceCueReader.read()` and `_features_from_scores()` — where the 8-way row is currently computed and thrown away. |
| P0 | `tests/test_facecues.py` | 150-186 | Exact unit-test pattern for `_features_from_scores`; new tests must match this shape (`pytest.approx`, row-construction style). |
| P1 | `dashboard/pages/2_Score_my_own_text.py` | 144-186, 260-370 | Both rendering branches (face-only, combined) that must change together. |
| P1 | `dashboard/pages/6_Match_day_profile.py` | 118-155 | The duplicate face-only rendering for the match-day page. |
| P1 | `src/dashboard/copy.py` | 326-375 | Every `FACE_*` string. New copy must sit beside these, same voice (plain, hedged, no adjectives implying certainty). |
| P2 | `src/dashboard/matchday.py` | 144-157 | `_read_face()` — confirms `face_features` already passes through whatever `reading.features` contains; likely needs **no** change. |
| P2 | `docs/ethics.md` | §14.3, §14.5 | The limitation text this plan must not weaken, and the "measured error rate" honesty bar already set for Phase 28. |

## External Documentation

No external research needed — `hsemotion-onnx`'s output shape is already documented in
`src/media/facecues.py`'s own docstring and exercised by the existing test suite. One thing
to verify empirically rather than assume (see GOTCHA in Task 2): whether `predict_emotions(...,
logits=False)` returns the 8 expression scores as a softmax distribution (sums to ~1) or
independent per-class probabilities. The current code never needed to know; this plan's
copy ("out of the model's eight categories") is only accurate if it's the former.

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: src/media/nonverbal.py:86,93,95
SIMULATED_FEATURES: tuple[str, ...] = ("expressivity", "vocal_strain", "steadiness")
FACE_FEATURES: tuple[str, ...] = ("negative_valence", "arousal")
FEATURES: tuple[str, ...] = SIMULATED_FEATURES + FACE_FEATURES
```
New tuple follows the same shape: `FACE_EXPRESSION_FEATURES`, unioned into `FEATURES`.

### VALIDATION_GOTCHA
```python
# SOURCE: src/media/nonverbal.py:118-124
unknown = set(self.features) - set(FEATURES)
if unknown:
    raise ValueError(
        f"NonVerbalReading({self.source!r}) emitted unknown features "
        f"{sorted(unknown)}. The name set is fixed so that a feature and its "
        "weight cannot drift apart; add to FEATURES deliberately."
    )
```
Any new key returned by `_features_from_scores` that is not added to `FEATURES` first will
raise at construction, not at render time — the failure is loud and early, which is correct;
do not work around it.

### PURE_FUNCTION_TEST_STYLE
```python
# SOURCE: tests/test_facecues.py:150-165
def test_arousal_is_rescaled_into_the_unit_interval() -> None:
    row = [0.0] * len(EXPRESSIONS) + [0.0, 1.0]
    assert _features_from_scores(row)["arousal"] == pytest.approx(1.0)
```
No model, no image, no Streamlit — a plain list in, a dict out. New tests for the 8-way
scores follow the same shape.

### GENERIC_TILE_LOOP (already handles an arbitrary-length context dict)
```python
# SOURCE: dashboard/pages/2_Score_my_own_text.py:334-349
for column, (name, value) in zip(
    st.columns(len(media_context)), sorted(media_context.items()), strict=False
):
    with column:
        st.markdown(
            f'<div class="widget{"" if name in media_weights else " is-inert"}">'
            f'<span class="wl">{name.replace("_", " ")}</span>'
            f'<span class="wv" style="font-size:32px">{value:.2f}</span>'
            f'<span class="wu">'
            f"{'moved the score' if name in media_weights else 'shown, weighted as zero'}"
            f"</span></div>",
            unsafe_allow_html=True,
        )
```
This already renders correctly for a 10-13 item dict content-wise; it needs a row-wrap
(5 per row, matching the construct-tile loop at line 313) rather than one `st.columns(N)`
call, or ten columns render illegibly narrow.

### COPY_VOICE
```python
# SOURCE: src/dashboard/copy.py:341-348
FACE_CUES_LIMITATION = (
    "An expression is not a feeling. Research does not support reading a person's "
    "state of mind reliably from their face, ..."
)
```
Every new string: hedged, plain, no adjective stronger than the evidence, never a verb like
"detects" or "reveals" applied to a person.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/media/nonverbal.py` | UPDATE | Add `FACE_EXPRESSION_FEATURES` (8 names), extend `FEATURES` |
| `src/media/facecues.py` | UPDATE | `_features_from_scores` returns the 8 extra keys when the full row is present; `EXPRESSIONS` order must match the new tuple's order exactly |
| `src/dashboard/copy.py` | UPDATE | New `FACE_EXPRESSION_HEADLINE` / `FACE_EXPRESSION_PLAIN` copy; a small percentage-formatting helper if one doesn't already exist (check `src/dashboard/bands.py` / `charts.py` first — do not write a second one) |
| `dashboard/pages/2_Score_my_own_text.py` | UPDATE | Percentage formatting on the two weighted tiles; row-wrapped grid for the "non-verbal reading" section; add the unfiltered supporting-detail row to the face-only branch |
| `dashboard/pages/6_Match_day_profile.py` | UPDATE | Mirror the same two changes in its own (deliberately duplicated) rendering code |
| `tests/test_facecues.py` | UPDATE | New unit tests for the 8-way keys: bounded, present only with a full row, absent (degraded) with an 8-only row |
| `tests/test_dashboard_pages.py` | VERIFY ONLY | Its existing forbidden-vocabulary screen and stamp-ordering checks should catch a copy mistake; run it, do not assume it needs edits |

## NOT Building

- Any ranking, "top emotion," or single winning category. All 8 render in the same fixed
  alphabetical order every time, exactly as the existing non-verbal section already sorts
  alphabetically (`sorted(media_context.items())`) rather than by value.
- Any change to `FACE_WEIGHTS`. The 8 new features are never keys in it; they stay at the
  same zero-weight, "shown, weighted as zero" status the simulated reader's 3 features
  already have.
- Any change to `FACE_CUES_LIMITATION`, `FACE_ONLY_STAMP`, or the consent gate in
  `FaceCueReader.__init__`. Nothing about this plan touches who may be read or under what
  precondition.
- A new chart/SVG component. The existing `.widget` tile grid is reused; introducing
  `charts.py`-style bars for this one panel would be a second visual language for one
  section, not a genuine improvement.
- Any equivalent change to `src/media/pressroom.py` or the match-day text/score path.
  That stays exactly as gated in `CLAUDE.md` §14 / `docs/ethics.md` §15 — see the companion
  Phase 29 decision-writeup plan.

---

## Step-by-Step Tasks

### Task 1: Extend the feature name set
- **ACTION**: Add `FACE_EXPRESSION_FEATURES` to `src/media/nonverbal.py`, union it into `FEATURES`.
- **IMPLEMENT**:
  ```python
  #: The model's own eight expression-category scores, carried for transparency.
  #: Never a key in FACE_WEIGHTS -- see facecues.py's docstring on why a discrete
  #: category is not a defensible thing to weight, even though a bounded
  #: valence/arousal pair is.
  FACE_EXPRESSION_FEATURES: tuple[str, ...] = (
      "expr_anger", "expr_contempt", "expr_disgust", "expr_fear",
      "expr_happiness", "expr_neutral", "expr_sadness", "expr_surprise",
  )
  FEATURES: tuple[str, ...] = SIMULATED_FEATURES + FACE_FEATURES + FACE_EXPRESSION_FEATURES
  ```
- **MIRROR**: `SIMULATED_FEATURES` / `FACE_FEATURES` naming and placement (nonverbal.py:86-95).
- **IMPORTS**: none new.
- **GOTCHA**: order here is arbitrary (name set, not positional), but `facecues.py`'s
  `EXPRESSIONS` tuple order (Anger, Contempt, Disgust, Fear, Happiness, Neutral, Sadness,
  Surprise) is positional against the model's actual output — the new
  `FACE_EXPRESSION_FEATURES` names must be zipped against `EXPRESSIONS` in that same order
  in Task 2, not re-sorted.
- **VALIDATE**: `python -c "from src.media.nonverbal import FEATURES; print(len(FEATURES))"` → 13.

### Task 2: Surface the 8-way scores from the model output
- **ACTION**: Extend `_features_from_scores()` in `src/media/facecues.py`.
- **IMPLEMENT**: when the full row (`>= len(EXPRESSIONS) + 2`) is present, also emit the 8
  expression keys, each `_unit(score)` (existing helper), zipped against `EXPRESSIONS` in
  its declared order against the new `FACE_EXPRESSION_FEATURES` tuple. In the degraded
  8-only path, still emit them (this is the *one* case where they're the only signal
  present, so hiding them there would be a step backward for exactly the situation this
  plan is meant to help with).
- **MIRROR**: the existing two-branch structure at `facecues.py:365-380`; do not change the
  branch conditions, only what each branch returns.
- **IMPORTS**: `from src.media.nonverbal import FACE_EXPRESSION_FEATURES` (new).
- **GOTCHA**: verify empirically, once, with `needs_stack` installed locally, whether the 8
  raw scores already sum to ~1.0 (softmax) or need their own normalization. If they don't
  sum to ~1, do not silently divide by their sum before display — that would be inventing a
  distribution the model didn't produce. Show the raw per-class scores and say so ("the
  model's own per-category score," not "probability out of 100%") if they're not a proper
  distribution.
- **VALIDATE**: `pytest tests/test_facecues.py -k features_from_scores -v`

### Task 3: New unit tests for the extension
- **ACTION**: Add to `tests/test_facecues.py`, immediately after the existing
  `_features_from_scores` tests (around line 180).
- **IMPLEMENT**: three tests — (a) full row produces all 8 expression keys, each
  bounded 0-1; (b) 8-only (degraded) row still produces all 8 keys; (c) the returned dict's
  8 expression keys are a subset of `FACE_EXPRESSION_FEATURES` exactly (no drift, no typo).
- **MIRROR**: `test_every_feature_is_bounded_whatever_the_engine_returns` (facecues.py test
  file, ~line 168) for the bounded-value assertion style.
- **IMPORTS**: `from src.media.nonverbal import FACE_EXPRESSION_FEATURES`.
- **GOTCHA**: none beyond Task 2's.
- **VALIDATE**: `pytest tests/test_facecues.py -v` — all green, none newly skipped.

### Task 4: Copy — plain English, no overclaim
- **ACTION**: Add to `src/dashboard/copy.py`, beside the existing `FACE_*` block (after line 374).
- **IMPLEMENT**:
  ```python
  FACE_EXPRESSION_HEADLINE = "What the model's eight categories scored"

  FACE_EXPRESSION_PLAIN = (
      "These eight numbers are the same model's own per-category scores for this "
      "photo, shown so the two weighted numbers above are not the only thing "
      "visible. None of the eight moved the score -- only negative-looking and "
      "activated-looking do, at the weights stated above. They are listed in a "
      "fixed order, not ranked by score, and no single category is named as "
      "the photo's 'emotion' anywhere on this page."
  )
  ```
- **MIRROR**: the hedged, plain voice of `FACE_CUES_LIMITATION` and `FACE_CUES_NOT_MEASURED`.
- **IMPORTS**: none.
- **GOTCHA**: this file is screened at import for forbidden vocabulary (`CLAUDE.md` §12.6 /
  the `_screen()` walk referenced in `docs/dashboard.md`) — run the dashboard test suite
  after adding this, don't assume it passes.
- **VALIDATE**: `pytest tests/test_dashboard_pages.py tests/test_dashboard_panels.py -q`

### Task 5: Render — combined path (page 2, both channels)
- **ACTION**: Update the "non-verbal reading" section, `dashboard/pages/2_Score_my_own_text.py:334-350`.
- **IMPLEMENT**: (a) format `value` as `f"{value*100:.0f}%"` instead of `f"{value:.2f}"` for
  every tile in this loop; (b) wrap into rows of 5 (`for row_start in range(0, len(items), 5)`),
  mirroring the construct-tile loop at line 313, instead of one `st.columns(len(media_context))`
  call; (c) insert `st.markdown(theme.claude_lede(plain.FACE_EXPRESSION_PLAIN), ...)` once,
  above the grid, only when any `expr_*` key is present in `media_context`.
- **MIRROR**: the row-wrapping pattern already used for the ten construct tiles (lines 312-322).
- **IMPORTS**: none new (`plain`, `theme` already imported on this page).
- **GOTCHA**: `media_weights` still only contains the 2 original keys — the `is-inert` /
  "shown, weighted as zero" styling already applies correctly to the 8 new tiles with no
  further change, because that branch is keyed on membership in `media_weights`, not on a
  hardcoded count.
- **VALIDATE**: `streamlit run dashboard/app.py`, upload a real photo with consent ticked,
  visually confirm 10-13 tiles render legibly in rows, weighted ones say "moved the score,"
  the rest say "shown, weighted as zero."

### Task 6: Render — face-only path (page 2)
- **ACTION**: Update `dashboard/pages/2_Score_my_own_text.py:158-178`.
- **IMPLEMENT**: after the existing weighted-only hero grid (unchanged), add a second,
  unfiltered "supporting detail" section using the same row-wrapped loop as Task 5, driven
  by `media_context` filtered to `k not in media_weights` this time (the complement of the
  hero grid), with the `FACE_EXPRESSION_HEADLINE` / `FACE_EXPRESSION_PLAIN` copy above it.
- **MIRROR**: Task 5's loop, and the existing hero-grid formatting for percentage display.
- **IMPORTS**: none new.
- **GOTCHA**: this branch `st.stop()`s at the end (line 186) — the new section must be
  inserted **before** that `st.stop()`, not after, or it never renders.
- **VALIDATE**: upload a photo with no text and consent ticked; confirm both the hero figure
  and the new supporting-detail row appear before the page halts.

### Task 7: Render — match-day page (page 6), same two changes
- **ACTION**: Repeat Task 5 and Task 6's changes in `dashboard/pages/6_Match_day_profile.py`,
  in its own face-only and combined rendering blocks (lines ~118-155 and the later combined
  section).
- **IMPLEMENT**: identical logic; this file does not import from page 2, per
  `src/dashboard/matchday.py`'s own docstring rationale for the duplication (page-import
  boundary rule enforced by `tests/test_dashboard_pages.py`).
- **MIRROR**: Tasks 5 and 6, verbatim in shape.
- **IMPORTS**: none new.
- **GOTCHA**: do **not** try to deduplicate this into a shared page-level helper module under
  `dashboard/` — that would violate the "a page imports only from `src.dashboard`" rule this
  project enforces structurally, and `src.dashboard` cannot import Streamlit rendering code
  without becoming untestable outside a running app.
- **VALIDATE**: `streamlit run dashboard/app.py`, repeat the manual checks from Tasks 5-6 on
  the "Match-day profile" page specifically (photo only, no link, consent ticked).

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| Full row → 8 expression keys | 10-element row (8 expr + valence + arousal) | dict has all 8 `expr_*` keys, each in [0,1] | no |
| Degraded 8-only row → still 8 keys | 8-element row | dict has all 8 `expr_*` keys | yes — this is the path where they matter most |
| Keys never drift | any valid row | `set(result) - set(FACE_EXPRESSION_FEATURES) == set()` minus the 2 original keys | yes — catches a typo before `NonVerbalReading` would catch it at construction |

### Edge Cases Checklist
- [x] Empty input — already covered by `test_an_unreadable_engine_row_produces_no_number`
- [x] Degraded (8-only) engine row — Task 3
- [ ] A row that is exactly 9 long (neither branch) — confirm existing `raise FaceCueUnavailable` still fires; add a regression test if not already covered
- [x] Maximum size input — n/a, row length is fixed by the model
- [ ] Scores that don't sum to 1 — see Task 2 GOTCHA; write a test once the empirical answer is known

---

## Validation Commands

### Static Analysis
```bash
.venv\Scripts\python.exe -m ruff check src/media/nonverbal.py src/media/facecues.py src/dashboard/copy.py dashboard/pages/2_Score_my_own_text.py dashboard/pages/6_Match_day_profile.py
```
EXPECT: Zero errors.

### Unit Tests
```bash
.venv\Scripts\python.exe -m pytest tests/test_facecues.py -v
```
EXPECT: All pass, same skip count as before for stack-dependent tests only.

### Full Test Suite
```bash
.venv\Scripts\python.exe -m pytest -q
```
EXPECT: No regressions; same pass/skip counts as the pre-change baseline plus the new tests.

### Manual Validation
```powershell
$env:SRN_MATCHDAY_REAL_ATHLETES = $null   # confirm still unset -- unrelated to this plan
.venv\Scripts\streamlit.exe run dashboard\app.py
```
- [ ] "Score my own text" page, upload a real photo + consent ticked, no text: hero figure +
      2 weighted tiles + new 8-tile supporting-detail row all render before the page halts.
- [ ] Same page, photo + typed text: combined score renders, "non-verbal reading" section
      shows all 10-13 tiles in wrapped rows, percentages not raw floats.
- [ ] "Match-day profile" page, photo only (no link): same two checks as above.
- [ ] `FACE_CUES_LIMITATION` text is visible, above the score, outside any expander, on
      every path that shows a face-derived number — unchanged from before this plan.
- [ ] No text anywhere on the page names a single "detected emotion" or ranks the 8
      categories by value.

---

## Acceptance Criteria
- [ ] All 7 tasks completed
- [ ] All validation commands pass
- [ ] Tests written and passing
- [ ] No lint errors
- [ ] Matches UX design above
- [ ] `FACE_CUES_LIMITATION`, `FACE_WEIGHTS`, and the consent gate are byte-identical to before this plan

## Completion Checklist
- [ ] Code follows discovered patterns (row-wrapped tile grid, alphabetical-not-ranked ordering)
- [ ] Error handling matches codebase style (unreadable engine row still raises `FaceCueUnavailable`)
- [ ] Tests follow test patterns (`pytest.approx`, no-stack-required unit tests)
- [ ] No hardcoded values beyond the fixed `EXPRESSIONS` / `FACE_EXPRESSION_FEATURES` name lists
- [ ] Documentation updated: `CLAUDE.md` §13.2/§13.3 gets a one-line addendum noting the
      expression breakdown is now shown as supporting detail (no new phase number needed —
      this is a refinement of Phase 28, not a new phase)
- [ ] No unnecessary scope additions (no new chart library, no change to weights, no touch to Phase 29)
- [ ] Self-contained — no questions needed during implementation, except the empirical
      softmax-vs-not check flagged in Task 2

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 8 raw scores don't sum to 1, copy implies a probability distribution | Medium | Medium — inaccurate framing, not a safety issue | Task 2's empirical check before writing final copy |
| A 10-13 tile grid still looks cramped even row-wrapped | Medium | Low — cosmetic | Manual validation step catches it; fall back to 2 rows of up to 6 if 5-per-row looks bad |
| Someone later adds a 9th `FACE_WEIGHTS` key by copying this pattern without reading the GOTCHA | Low | High — would silently let an expression category move the score | The "NOT Building" section and the `FEATURES`-vs-`FACE_WEIGHTS` distinction are stated explicitly twice (here and in nonverbal.py's own comment) |

## Notes
This plan deliberately does not touch anything about *whether* a face is read (consent gate)
or *how much* it weighs (declared weights). It only makes visible what the model was already
computing and discarding. If, after seeing the richer display, you still want something that
reads as more confident than this — a single "the athlete looks anxious" sentence, say — that
is a different, larger conversation about what this project is willing to claim, not a
follow-up to this plan.
