# docs/dashboard.md — Phase 20: the demo, and what it is allowed to say

> **PROVISIONAL — planted-label corpus-property measurement, NOT accuracy.**
> `data/gold/` is empty (OPEN-025); no real athlete text exists (OPEN-011).
> Nothing the dashboard displays is evidence that the model detects
> psychological constructs in real athlete language.

## Running it

```powershell
# Local
streamlit run dashboard/app.py

# Docker (light image — no torch; the `dashboard` service already existed
# from Phase 2 and needed no change, because streamlit is in requirements-base.txt)
docker compose build app
docker compose up dashboard      # http://localhost:8501
```

Regenerating the committed artefacts:

```powershell
python scripts/build_dashboard_fixture.py   # refuses to write unless it reproduces cards.md
python scripts/build_dashboard_figure.py    # writes reports/figures/phase20_explanation_card.svg
pytest tests/test_dashboard.py -q
```

## The two tabs, and why they differ

| tab | backend | what the bars mean | exportable |
|---|---|---|---|
| **Known examples** | `ReplayBackend` — a committed fixture derived from `reports/explain/cards.md` | `P(construct present)` from the Phase 14 checkpoint, cached | yes |
| **Score your own text** | `LexiconBackend` — the Phase 13 lexicon baseline, pure Python | cue match: 1 matched / 0 not. **Not a probability** | no |

**The live tab is not the paper's model.** The `dashboard` compose service runs
the light image, which has no torch by design. Loading the checkpoint would mean
the multi-GB train image and a Docker gate that no longer runs in the image the
rest of the project uses — and C2.7 binds: the paper's model must not silently
change, and the surest guarantee is that the demo does not hold it. The lexicon
scores macro-F1 **0.462** template-disjoint (the honest floor the transformer's
0.588 is measured against) and carries a known upward bias (OPEN-021). The app
says so on screen, every time.

**The lexicon emits presence, not probability, and that is left visible.**
`LexiconBaseline.predict` returns a set of matched constructs. Rather than invent
a magnitude from cue-hit counts — an arbitrary formula that would look exactly
like a model score on a bar chart — the live path reports 1.0/0.0 and labels the
axis accordingly. The bars look blocky. A made-up magnitude on a screening tool
is the kind of number that gets quoted back without its formula.

### The live detector is wider than the evaluated one (added 2026-09-21)

`LexiconBackend` scores pasted text with `CONSTRUCT_CUES` **widened by
`DASHBOARD_EXTRA_CUES`** (`src/dashboard/backend.py`). `LexiconBaseline` in
`src/evaluation/baselines.py`, whose macro-F1 **0.462** is the number quoted
above and committed in `reports/`, uses `CONSTRUCT_CUES` alone and is
untouched by that widening.

So the two differ, deliberately: the evaluated baseline is a narrow, frozen
instrument, and re-fitting it would invalidate every committed figure measured
against it. The demo's job is different — a visitor pasting their own sentence
should see the constructs a human reader would see, not a blank chart because
they wrote "nervous" where the frozen cue list expects "on edge".

**What this costs, stated plainly: a reviewer who opens the deployed app is not
running the system whose 0.462 this document reports, and the widened list has
no measured score of its own.** It is not evaluated, it is not in the paper, and
no figure anywhere derives from it.

**Its *coverage* is measured; its *correctness* is not, and the two are not the
same thing.** `reports/abstention.md` reports how often each list fires at all:
the frozen list is silent on **58.8%** of the corpus, the widened list on
**20.2%** (Phase 31, 2026-09-21). Silence matters, because a silent detector
hands back an index of exactly 0.50 with a band underneath it. But firing more
often is not the same as firing correctly -- every one of those extra matches
could be wrong and nothing here shows otherwise, because measuring precision
needs the gold set OPEN-025 is waiting on. Coverage is the honest claim;
precision is not available. The extra cues are drawn from the same
`config/taxonomy.yaml`-anchored realisation vocabulary as the generator's own
banks, so nothing in them is invented outside the instruments, but provenance is
not measurement and this paragraph is not a number.

The paper must describe the demo as the widened lexicon, never as the baseline.

## Architecture

Predicting and rendering are separate programs, as in `src/risk/` (15),
`src/explainability/` (17) and `src/evaluation/` (18).

```
src/dashboard/backend.py   probabilities from somewhere. No torch.
src/dashboard/view.py      the honesty layer. Every guard lives here.
src/dashboard/charts.py    SVG marks, grayscale- and CVD-safe.
dashboard/app.py           Streamlit shell. ~110 lines, zero business logic.
```

`tests/test_dashboard.py` enforces the split structurally: `app.py` may import
from `src.dashboard` and nowhere else under `src.`, and may not construct a
`DashboardView`, `ExplanationCard` or `CardSet` itself. The whole suite runs with
no ML stack installed, in about 1.5 seconds.

## The strengthened gate

`PROJECT_PLAN.md` gates Phase 20 on "app runs in Docker and reproduces a known
example". That checks *rendering* and *reproducibility* and says nothing about
whether what is rendered is claim-safe — which is the fourth instance of the
defect `docs/findings.md` §6 traces through Phases 9b, 17 and 18. Four honesty
checks were therefore written **before** the app:

| | property | how it is enforced |
|---|---|---|
| c | `assert_publication_safe` on every card path | called in `DashboardView.__post_init__`; an unchecked view is unconstructable |
| d | PROVISIONAL stamp on every page showing a number | mandatory validated field on `ScoreSurface`; rendered **above the fold**, not inside a collapsed expander |
| e | the four inert constructs render as non-contributing | derived from `Direction.POLAR` + zero weight on the live scorer, never a name list |
| f | forbidden vocabulary never reaches a surface | screened at construction *and* over the fully rendered page and `app.py` source |

Plus the original: the fixture's rendered card must equal its block of
`reports/explain/cards.md` **character for character**. That is what makes C2.6
binding rather than aspirational — if the dashboard ever grows its own
highlighting, the demo and the paper figure drift and this test says so.

### The one deliberate exception, and why it is narrow

`PROVISIONAL_STAMP` reads "… corpus-property measurement, **NOT accuracy**". A
flat ban on the substring makes the mandated stamp unshippable, so the two rules
contradicted each other on the guard's first run. The resolution allows the
literal denial `not accuracy` and nothing else — matched literally rather than by
detecting negation in general, because a cleverer rule would let "no reason to
doubt the accuracy" through, which is a claim wearing a negation.
`test_the_only_permitted_use_of_accuracy_is_the_stamps_own_denial` pins four such
smuggling attempts.

## Chart choices

Both obvious defaults were wrong.

**A radial gauge is the wrong mark for the risk index.** A dial's arc is read as
a proportion of a whole; the index is an uncalibrated ranking score. The
speedometer form also carries a strong "measurement of a thing" connotation,
which for a number that is explicitly not a measurement of a person is the
connotation to avoid. A **linear meter** reads as a position, not a verdict. The
track carries no low/moderate/high bands: banding an uncalibrated score invents
thresholds nothing in this project supports.

**A ten-hue categorical chart is the wrong mark for the decomposition.** The
constructs are rows of one comparison, not series, so the encoding is position
down a shared axis — a **diverging bar chart**, left of the rule lowers risk and
right raises it.

**Sign is position, not colour**, so it survives grayscale, print, any colour
vision, and a stripped stylesheet. **The four inert constructs are marked three
times over**: hatch fill, dashed outline, and the literal word `inert` in the row
label. `reports/dashboard/03_figure_grayscale_proof.png` is the desaturated proof
against Phase 24's "figures legible in grayscale" gate.

## Two defects found by looking, not by asserting

Both passed every unit test and were caught in the verification step.

1. **Duplicate SVG `id`s.** Both charts defined `inert-hatch`; SVG ids share one
   namespace per document and Streamlit keeps every tab's DOM mounted, so one
   chart's hatch silently rendered empty. Pattern ids are now derived
   deterministically from the chart's own data.
2. **A stamp inside a collapsed expander.** Present in the DOM, absent from the
   screen — and from every screenshot that becomes a paper figure. The stamp is
   now rendered above the fold, and a test asserts it appears before the first
   `st.expander` call.

Both are the same shape as the defect this phase was warned about, one level
down: a check that passes while the property it names is false. The unit tests
could not see either of them; only the rendered page could. That is an argument
for the verification step, not against the tests.

## What the dashboard may never do

1. Display, log, cache or ship verbatim corpus text outside the synthetic A2
   source. User-pasted text is the user's own: shown back, never persisted.
2. Label any number "accuracy", "confidence in the athlete", or anything implying
   a measurement of a person.
3. Use diagnosis framing. The risk index is not a clinical instrument.
4. Write "expert-validated", "practitioner-validated" or "coach-validated". If the
   pilot study is referenced, the `docs/findings.md` §2.4 wording is used verbatim.
5. Call the decomposition ten-construct without the §3.3 qualification.
6. Re-derive the Phase 17 highlighting, retrain, or re-tune thresholds.
