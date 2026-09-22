# Phase 32 — Evidence Coverage widget: implementation plan

> **Status:** plan only, no code written. Approved by the owner 2026-09-21/22.
> **Baseline:** `main` at `e1f9787` (PR #1 merged). Clean tree, 1095 tests passing.
> **Written for:** a session starting cold with no prior context. This file is
> self-contained — you do not need the conversation that produced it.

Supersedes `handover_phase_32_evidence_coverage.txt`, which was the design
handover. This file adds the concrete signatures, test names and acceptance
checks an implementing session needs. If the two ever disagree, **this file
wins** and the `.txt` should be deleted.

---

## 1. What you are building, in one paragraph

Every construct in this project is anchored to a validated sports-psychology
instrument (`instrument_anchor` in `config/taxonomy.yaml`). Ten constructs map to
eight instruments. This widget projects **one already-scored text** back onto
those instruments and reports, per subscale, whether the text gave any evidence
at all — and where it did not, says so plainly.

Its output *is* the limitation. There is no reading of "somatic anxiety: SILENT"
in which it becomes a finding about a person. That is the whole design.

**It computes no new number.** It is a projection of a `DashboardView` the
dashboard has already built.

---

## 2. Read these first

| File | Why |
|---|---|
| `reports/evidence_coverage_mockup.html` | **The approved visual contract.** Generated from real `build_view()` output, not drawn |
| `reports/abstention.md` | The measurement that motivates this feature |
| `CLAUDE.md` §11.3 | The shared architecture every dashboard feature copies |
| `CLAUDE.md` §12.3 | The 0.50 problem this feature exposes |
| `config/taxonomy.yaml` | `instrument_anchor` — the grounding |
| `config/brain_atlas.yaml` | The config convention `instruments.yaml` mirrors |
| `src/dashboard/widgets.py` | The `Widget` contract — already carries `inert` / `detected` |
| `docs/dashboard.md` | What the dashboard may never do |

---

## 3. Decisions already locked — do not re-open

| # | Decision | Date |
|---|---|---|
| Q1 | **Ship unflagged.** No `SRN_*` variable, no conditional page registration | 2026-09-22 |
| Q2 | The mockup is **committed and retained** as the design contract, not deleted when the panel lands | 2026-09-22 |
| Q3 | **Still open, non-blocking.** Grid tile + page, or page only? Recommendation: both, matching `atlas_widget`. Build the page first; add the tile in the same commit once confirmed | — |

**Why unflagged, stated so a future reader does not assume oversight:** pages 3–5
sit behind `SRN_COGNITIVE_LAYER` because they introduce *simulated signals* a
reader could mistake for measurements, and because a real physiological source
behind that seam is a different privacy class (`CLAUDE.md` §11.2). This widget
introduces no source, no signal, no sensor, no dependency and no new number.
There is nothing for a flag to protect.

Consequence accepted: every visitor sees "2 of 8" from first load. **Do not add a
flag later to hide it on a demo day.**

---

## 4. Why it is novel — and what is merely reused

**New.** Do claim these:

- **N1 — Instrument-space projection.** `instrument_anchor` has sat in
  `config/taxonomy.yaml` since Phase 4. Nothing in `src/` reads it today.
- **N2 — Negative-space reporting.** Every existing surface (bars, atlas, risk
  index, explanation cards) reports what was *found*. Nothing reports what the
  input could not speak to.
- **N3 — Coverage-conditioned index.** The risk index is rendered today with no
  statement of how much evidence it rests on. This pairs it with its evidential
  denominator.
- **N4 — Silent subscales as next questions.** Each unevidenced subscale renders
  as a topic the reader could ask about — turning a limitations display into
  something a coach can act on.

**Reused. Do NOT claim these as contributions:**

- The four-state ledger is `src/evaluation/abstention.py::CAUSES` (Phase 31).
  New here only in being surfaced *per input, on screen* rather than aggregated.
- `ConstructBar.inert` and `.detected` already exist and already carry the
  distinction. **No new detection logic is required or permitted.**
- `Widget`, `theme.palette`, the page-shell pattern, the stamp discipline.

**The argument for the paper:** a questionnaire is administered — every item gets
answered. Text is volunteered — the athlete says what they say. A text-derived
profile is therefore structurally incomparable to a questionnaire profile, and
text-based psychological inference work elides this universally.

> ⚠️ **Novelty is asserted, not verified.** No literature search has been run.
> Before any "first" or "no prior work" claim reaches `paper/`, search:
> selective prediction / abstention in ML; psychometric coverage and construct
> under-representation; construct validity of text-derived measures; missing-data
> reporting in psychological assessment. If prior work exists the feature still
> ships — the claim changes from "novel" to "first in this setting".

---

## 5. What the mockup already revealed

Real output, not projection:

| Case | Constructs detected | Instruments spoken to |
|---|---|---|
| Match-day scenario passage | 3 | **2 of 8** |
| Richest single corpus utterance | 2 | **2 of 8** |
| Sparse utterance | 1 | **1 of 8** |

A realistic passage speaks to a **quarter** of the instrument set.

A reviewer seeing "2 of 8" beside a confident risk index will ask why the index
is shown at all. The answer: the index is a ranking over what *was* detected, and
this widget is what makes that scope explicit rather than implied. **Do not
soften the panel to dodge the question.**

---

## 6. File manifest

| File | Action |
|---|---|
| `config/instruments.yaml` | **new** — instrument → subscale → construct, one citation per row |
| `src/dashboard/instruments.py` | **new** — loads, validates, freezes that file |
| `src/dashboard/coverage.py` | **new** — the ledger. Pure: no I/O, no Streamlit |
| `src/dashboard/coverage_panel.py` | **new** — renderer, theme-token driven, light + dark |
| `dashboard/pages/7_Evidence_coverage.py` | **new** — page shell, renderer only |
| `src/dashboard/widgets.py` | modified — `coverage_widget(view)` |
| `src/dashboard/copy.py` | modified — `COVERAGE_PLAIN`, `COVERAGE_CAVEATS` |
| `src/dashboard/__init__.py` | modified — export the new renderer |
| `tests/test_coverage.py` | **new** — the suite in §9 |
| `docs/dashboard.md` | modified — a section, as every feature gets |
| `docs/model_card.md` | modified — one paragraph, following the §11 pattern |

**A new renderer file, not `neurovis.py`.** That file is 1364 lines; adding to it
breaks the 800-line ceiling in the coding rules.

---

## 7. The one design decision that matters

```
bar.detected is False            -> SILENT
bar.detected and bar.inert       -> INERT
bar.detected and not bar.inert   -> EVIDENCED
no view built (gate refused)     -> REFUSED   (page shows refusal, no table)
```

Derive from `DashboardView.bars` **only**.

> 🚨 **Do NOT import `src.evaluation.abstention` from `src/dashboard/`.**
> The dependency direction inverts — `src.evaluation` already depends on
> `src.dashboard`. In Phase 31 an eager import in `src/evaluation/__init__.py`
> tripped the OPEN-036 cycle (`src.dashboard.__init__` → `copy` → `view` →
> `backend` → `src.explainability.attribution`, partially initialised) and broke
> the suite. The two modules agree on the four states *by construction*; §9 has
> the test that keeps them agreeing.

**Does not move the risk index.** Read-only projection. No context mapping, no
weights, no committed figure touched. Assert it.

---

## 8. Build order

Each step is independently provable. Do not start a step before its predecessor
passes.

### Step 1 — `config/instruments.yaml` + `src/dashboard/instruments.py`

The mapping, already confirmed against `config/taxonomy.yaml`:

| Instrument | Citation | Constructs |
|---|---|---|
| CSAI-2 | `Martens1990; Cox2003` | `cognitive_anxiety`, `somatic_anxiety`, `self_confidence` |
| Perceived Stress Scale | `Cohen1983` | `perceived_stress` |
| ABQ | `Raedeke2001` | `burnout_signal` |
| TAIS | `Nideffer1976` | `attentional_focus` |
| CD-RISC | `Connor2003` | `resilience` |
| Achievement-goal / SDT | `Elliot2001; Deci2000` | `motivation_orientation` |
| Challenge-threat | `JonesMeijen2009` | `appraisal_orientation` |
| Coping in sport | `Nicholls2007` | `coping_style` |

The loader **refuses**:

- a construct not present in `config/taxonomy.yaml`
- a row with an empty citation
- a citation key that does not resolve in `paper/refs.bib`
- any construct in `taxonomy.yaml` with no instrument row — no construct may be
  silently dropped
- any numeric field — this file carries no values

**Acceptance:** loader tests pass. No UI yet.

### Step 2 — `src/dashboard/coverage.py`

```python
class CoverageState(Enum):
    EVIDENCED = "evidenced"
    INERT = "inert"
    SILENT = "silent"
    REFUSED = "refused"

@dataclass(frozen=True)
class SubscaleCoverage:
    construct: str
    plain_name: str
    state: CoverageState
    prompt: str          # from taxonomy.yaml `definition` -- see R1

@dataclass(frozen=True)
class InstrumentCoverage:
    name: str
    citation: str
    subscales: tuple[SubscaleCoverage, ...]
    @property
    def evidenced_count(self) -> int: ...

@dataclass(frozen=True)
class CoverageLedger:
    instruments: tuple[InstrumentCoverage, ...]
    spoken_to: int
    total: int
    stamp: str
    def __post_init__(self) -> None:
        # raises without a PROVISIONAL stamp -- same shape as ScoreSurface
        # and BiosignalWindow

def coverage_for(view: DashboardView) -> CoverageLedger: ...
```

**Acceptance:** ledger tests pass. Still no UI.

### Step 3 — `src/dashboard/coverage_panel.py`

```python
def coverage_panel(ledger: CoverageLedger, *, mode: str) -> str: ...
def coverage_height(ledger: CoverageLedger) -> int: ...
```

One self-contained HTML document, mounted with `st.components.v1.html` — same
pattern as `motion_panel`. All colour from `theme.palette(mode)`. **Three
channels per state — glyph, hue *and* the literal word** — as `charts.py`
already requires. Never hue alone. Match the mockup.

**Acceptance:** render tests pass.

### Step 4 — page and tile

`dashboard/pages/7_Evidence_coverage.py` — imports only from `src.dashboard`,
constructs no view of its own, renders the stamp and caveats **before** any table
or expander.

`widgets.coverage_widget(view) -> Widget` — title "Evidence coverage", value
"2 of 8", caption "instruments this text speaks to".

**Acceptance:** `tests/test_dashboard_pages.py` shell rules pass on page 7.

### Step 5 — docs

`docs/dashboard.md` section; `docs/model_card.md` paragraph. Both must state that
**coverage is not correctness**.

---

## 9. Tests required

Write these **before** wiring the page on.

**Config / loader**
- every construct in `taxonomy.yaml` appears in exactly one instrument row
- a row with an empty citation raises
- a citation key absent from `paper/refs.bib` raises
- a construct absent from `taxonomy.yaml` raises

**Ledger**
- a `CoverageLedger` without a PROVISIONAL stamp raises
- all three live states are reachable over the real corpus
- state counts sum to the construct count — exhaustive, no gaps
- a bar with `detected=True, inert=True` yields `INERT`, never `EVIDENCED`
- `coverage_for()` introduces no number absent from the view: evidenced counts
  equal the count of non-inert detected bars, to the integer

**Agreement with Phase 31**
- for a sample of corpus texts, `coverage_for()`'s per-construct state matches
  `abstention.Outcome.cause` (`silent`↔`no_detection`, `inert`↔`all_inert`).
  *The test imports both; the modules do not import each other.*

**Honesty / render**
- panel contains "subscales, not items"
- panel contains "no evidence either way"
- panel contains the PROVISIONAL stamp
- panel contains **none** of: "no somatic anxiety", "free of", "does not have",
  "healthy", "at risk", "diagnos"
- caveats appear **before** the first table row in the page source
- every state renders three channels: glyph, hue **and** word
- renders identically with the webfont blocked
- light and dark both render; no colour outside `theme.palette(mode)`

**Non-interference**
- building a ledger does not alter `view.risk.index` — bit-identical
- the pre-existing suite stays green (1095 passed, 2 skipped at baseline)

**Page shell**
- `tests/test_dashboard_pages.py` rules apply to page 7 unchanged: imports only
  from `src.dashboard`; no `src.media` or `src.evaluation` import

---

## 10. Risks, each with its guard

| # | Risk | Guard |
|---|---|---|
| **R1** | **Copyright.** CSAI-2, ABQ, CD-RISC and TAIS are copyrighted instruments. Reproducing item text is a licensing violation and the most damaging mistake available in this phase | The N4 prompt is **not** an instrument item. Use the `definition` field already in `config/taxonomy.yaml`, authored by this project. A test asserts every prompt derives from `taxonomy.yaml` and that `instruments.yaml` carries no item-like free text |
| **R2** | Read as **item-level** coverage. CSAI-2 has 27 items; this project carries one construct per subscale | "subscales, not items" renders adjacent to every count, outside any expander. Test asserts presence, and that no item count is ever displayed |
| **R3** | **Silent read as absent.** Silent means: construct absent, athlete didn't mention it, *or* detector missed it. At a 20.2% silent rate the third is common | Copy fixed at "this text gives no evidence either way", screened at import by `copy.py::_screen()`. Test asserts the panel never renders "no X" / "free of" / "does not have" |
| **R4** | **Coverage mistaken for correctness.** Evidenced means a cue fired, not that it fired correctly. Precision needs the gold set (OPEN-025) | Caveat renders above the table, in the error style, outside any expander — so it survives a screenshot. Same rule as `CLAUDE.md` §13.2 |
| **R5** | **Drift from `abstention.py`** — two modules defining the same four states | The agreement test in §9. They must not import each other |
| **R6** | **The demo lexicon is unevaluated.** The live path runs the widened `DASHBOARD_EXTRA_CUES`, not the frozen list | Carry the disclosure `docs/dashboard.md` already makes. Never quote a coverage percentage in the paper without saying which cue list produced it |

---

## 11. Explicitly out of scope

- **Coverage aggregated across multiple texts** from one athlete over time
  ("across 5 texts, ABQ has never been evidenced"). This is the natural next
  phase and the temporal hook already in Future Work. Not this one.
- **Any attempt to *score* a subscale** rather than report its coverage state.
  The moment a subscale gets a number, this stops being a limitations display
  and becomes an unvalidated psychometric instrument.
- Reproducing, closely paraphrasing, or linking to instrument items (R1).
- **Any change to detection, fusion, weights or the cue lists.** The widget is a
  projection of an existing view and nothing else.

---

## 12. Definition of done

- [ ] Every construct in `taxonomy.yaml` maps to exactly one instrument, each
      with a citation resolving in `paper/refs.bib`
- [ ] The panel matches `reports/evidence_coverage_mockup.html` in both modes
- [ ] No number on the panel is absent from the `DashboardView` it was built from
- [ ] The risk index is bit-identical with and without the ledger
- [ ] All §9 tests pass, plus the pre-existing suite
- [ ] `docs/dashboard.md` and `docs/model_card.md` updated
- [ ] Conventional commit; pre-commit hooks green

> **Pre-commit gotcha, learned the hard way in Phase 31:** `detect-secrets` wants
> `# pragma: allowlist secret` **inline on the offending line**, not on a comment
> line above it. `ruff format` will also reformat your files during the hook run
> — re-run the affected tests afterwards before claiming a suite result.

---

## 13. Commands

```bash
# baseline check before starting
git status --porcelain            # expect empty
python -m pytest -q --no-header   # expect 1095 passed, 2 skipped

# during: run the focused suite
python -m pytest tests/test_coverage.py -q --no-header

# before commit: full suite (~5 min)
python -m pytest --no-header | tail -3
```

---

## 14. What this phase does not fix

`paper/` contains `refs.bib` and an empty `figures/`. **Phase 23 — the IEEE
draft — was due the first week of September 2026 and has not been started.**
`PROJECT_PLAN.md` gated Phase 26 on "starts only after Phase 23 ships"; phases 26
through 32 have all now run ahead of it.

Both headline contributions remain blocked on two human acts, neither of which
any amount of code performs:

- **A2 annotating 100 `gold_dev` items** (~3h, agreed 2026-08-12, not started)
- **2 sports-familiar raters**, ~45 min each (deadline set at 2026-09-28)

This widget is one paper section. It is not the paper.
