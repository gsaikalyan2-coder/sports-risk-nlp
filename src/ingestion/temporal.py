"""Phase 22 -- `synth_precomp_v2`: a panel corpus with a deliberately planted drift.

Why this module exists, and why it is not an edit to `synthetic.py`
-------------------------------------------------------------------
The L3 temporal layer was gated on one question: does a `synth_precomp_v1`
record carry an `athlete_id` and a day-offset? Measured on 2026-09-29 against
all 4,000 records: **the day-offset exists and the identity does not.**
`_draw_stratum` draws sport, level, region, source_type,
`time_to_competition_days` and load hint independently per record; `RawRecord`
carries no subject field; `extra` is `{}` in every record; and no
`athlete_id` / `subject_id` / `speaker_id` appears anywhere in `data/` or
`src/`. Every v1 record is an i.i.d. draw, so v1 contains no panels and
nothing in it can be grouped into a within-athlete series.

Retrofitting an identity onto v1 was considered and refused. Assigning 4,000
independent draws to invented athletes manufactures panel structure that was
never generated, and a slope fitted across records whose sport, level and
region all change between "timepoints" is `.claude.md` sec.12.3 by a fifth
door: arithmetically correct and a lie. **`synth_precomp_v1` is frozen. This
module adds a separate corpus and touches neither the v1 artefacts nor the
generator that produced them.**

The second blocker, and the claim that resolves it
---------------------------------------------------
Identity alone is not enough. Phase 36 (sec.19.3) already measured the other
half: `generate_scenario_record` uses `timing` for exactly two things -- the
record id and `time_to_competition_days` -- so text is byte-identical across
all three timings, spread `0.0000`. A panel built on that generator would have
an identity axis and no drift, and its slope would be fitted over noise. The
shuffled-time control would correctly find nothing, which is not a finding but
a tautology: it would be testing whether noise has a slope.

So this module plants a drift, and the drift is a **psychological claim
encoded into a generator**, which under `.claude.md` sec.8 rule 2 is an owner
decision. Recorded as taken on **2026-09-29**:

    Approaching a competition, SOMATIC anxiety rises -- sharply in the final
    24-48h. COGNITIVE anxiety stays comparatively flat across the
    pre-competition window. SELF-CONFIDENCE stays flat.

This is multidimensional anxiety theory's time-to-event prediction
[Martens1990], in the CSAI-2 tradition [Cox2003]. Both keys resolve in
`paper/refs.bib`, and both are already the `instrument_anchor` that
`config/taxonomy.yaml` gives `cognitive_anxiety` and `somatic_anxiety`
generally -- so this table is grounded in the same instruments those
constructs already cite -- the same grounding convention Phase 30 (sec.15.3)
established for its own bias table, rather than a mapping invented for this
feature. The convention is reused; the module is not (see below).

**What this makes the temporal results, and what it does not.** Every
trajectory number downstream is a check that the analysis recovers a drift
this file planted on purpose. It is a sanity check on instrumentation. It is
not evidence about athletes, not a clinical finding, and not a validation of
anything: no real athlete, no observed outcome and no human label is involved
at any point. `src/evaluation/trajectory.py` restates this at the top of every
artefact it writes.

The two negative controls are designed in, not discovered
----------------------------------------------------------
`cognitive_anxiety` and `self_confidence` are planted with a band that does
not depend on the day, by the claim above. Their slopes SHOULD come back
indistinguishable from the shuffled control. Eight of the ten constructs have
no drift planted at all and the same holds for them. A reader meeting nine
nulls and one signal is looking at the design working, not at nine failures,
and `FLAT_BY_DESIGN` names the two explicitly so that claim is auditable in
code rather than asserted in prose.

Where `athlete_id` lives, and why it is not a new `RawRecord` field
--------------------------------------------------------------------
In `record.extra["athlete_id"]`, read back through `athlete_id_of`. Adding a
field to the shared `RawRecord` dataclass would change `to_dict()` -- and
therefore the serialised key set -- for every record in the project including
the v1 artefacts pinned by SHA-256 in `src/reproducibility/manifest.py`
(`corpus_records` `fa09f5ad...`, `utterances` `87a796ca...`). `extra` is the
schema's documented slot for exactly this, so the panel corpus costs no hash
and no schema change.

Why this does NOT build on `scenarios.py`
------------------------------------------
`scenarios.py` looks like the natural base -- it already has a construct-bias
table and a `_Directive` shape this ladder mirrors. It is the wrong base, and
`tests/test_scenarios.py::test_no_corpus_writing_module_imports_scenarios`
exists to stop exactly this mistake, which the first draft of this module made.

`scenarios._realise_graded_at` biases template selection towards realisations
that contain one of `src.evaluation.baselines.CONSTRUCT_CUES`' phrases, so the
Match-day demo shows contributions instead of ten empty bars. That is
legitimate for a demo and fatal for a corpus: text chosen BECAUSE the lexicon
detects it inflates the lexicon's own score. That is **OPEN-021** ("the lexicon
baseline is not independent of the corpus") made strictly worse, by
construction rather than by shared ancestry, and the failure is silent -- a
corpus built that way produces a better lexicon number and no error anywhere.

So this module imports nothing from `scenarios.py`. Every realisation goes
through `synthetic._realise` or through `_realise_graded_unbiased` below, both
of which pick a template with a flat `rng.randrange` over the bank and consult
no cue list. The cost is real and is the honest price: a planted construct is
detected less often, so more timepoints are unreadable and more slopes are
suppressed. Those rates are reported rather than engineered away.

Reuse, not modification
------------------------
`synthetic.py` and `scenarios.py` both have zero diff from this phase.
This module imports their realisation banks and framing helpers unchanged, the
same discipline `scenarios.py` itself records in its module docstring. Nothing
here reshuffles an RNG stream any existing seeded artefact depends on.
"""

from __future__ import annotations

import datetime as _dt
import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .allowlist import SourceDescriptor
from .provenance import GeneratorStamp
from .records import RawRecord
from .synthetic import (
    GENERATOR_NAME,
    GENERATOR_VERSION,
    GRADED_REALISATIONS,
    INTERPRETATION_REALISATIONS,
    NEUTRAL_SENTENCES,
    SPORTS,
    _contradicts,
    _draw_constructs,
    _fill,
    _frame,
    _realise,
    _vary,
)

__all__ = [
    "DAY_LADDER",
    "DRIFT_CITATION",
    "FLAT_BY_DESIGN",
    "MIN_TIMEPOINTS_FOR_SLOPE",
    "SOURCE_ID",
    "panel_descriptor",
    "panel_generator_stamp",
    "TIMING_BIAS",
    "AthletePanel",
    "PanelSpec",
    "athlete_id_of",
    "build_panel_corpus",
    "drift_for",
    "generate_panel",
    "timepoint_index_of",
]

#: The corpus this module writes. Additive: `synth_precomp_v1` is untouched.
SOURCE_ID = "synth_precomp_v2"

#: The citation carried by every drifting row, and reproduced in the report.
DRIFT_CITATION = "CSAI-2 multidimensional anxiety theory [Martens1990; Cox2003]"

#: Days before the competition, far to near. The same ladder `synthetic.py`
#: draws from, so v2's time axis is comparable to v1's metadata rather than a
#: second, differently-spaced one.
DAY_LADDER: tuple[int, ...] = (30, 21, 14, 10, 7, 5, 3, 2, 1, 0)

#: Below this many timepoints a slope is suppressed rather than reported.
#: An OLS slope over three points is dominated by whichever point is furthest
#: from the others; over two it is a straight line through both and carries no
#: information about shape at all. `src/evaluation/trajectory.py` enforces
#: this and reports the suppression rate rather than quietly dropping rows.
MIN_TIMEPOINTS_FOR_SLOPE = 4


@dataclass(frozen=True)
class _Drift:
    """How strongly a construct is planted at one distance from the event."""

    plant_probability: float
    intensity_band: tuple[int, int]

    def __post_init__(self) -> None:
        if not 0.0 <= self.plant_probability <= 1.0:
            raise ValueError(f"plant_probability {self.plant_probability!r} is not a probability")
        lo, hi = self.intensity_band
        if not (1 <= lo <= hi <= 3):
            raise ValueError(
                f"intensity_band {self.intensity_band!r} is outside the realisation "
                "bank's 1-3 range. Intensity 0 means 'absent', which is expressed by "
                "plant_probability, not by a band the bank has no templates for."
            )


#: **The drift, encoded.** Keyed by an inclusive upper bound on
#: `time_to_competition_days`, nearest the event first; `drift_for` walks it.
#:
#: Only `somatic_anxiety` appears, because only `somatic_anxiety` is claimed to
#: move (see the module docstring). Both of its channels rise together as the
#: event approaches -- the construct is planted more often AND at a higher
#: intensity -- because that is what "rises sharply in the final 24-48h"
#: describes: more athletes reporting it, and those reporting it reporting it
#: more strongly. Splitting the rise across both channels rather than loading
#: it all into intensity also keeps any single timepoint from being a
#: giveaway.
#:
#: Grounding: CSAI-2 multidimensional anxiety theory [Martens1990; Cox2003] --
#: the same `instrument_anchor` `config/taxonomy.yaml` already gives
#: `somatic_anxiety`.
TIMING_BIAS: dict[str, tuple[tuple[int, _Drift], ...]] = {
    "somatic_anxiety": (
        (0, _Drift(plant_probability=0.95, intensity_band=(3, 3))),
        (1, _Drift(plant_probability=0.90, intensity_band=(2, 3))),
        (2, _Drift(plant_probability=0.80, intensity_band=(2, 3))),
        (3, _Drift(plant_probability=0.65, intensity_band=(2, 2))),
        (5, _Drift(plant_probability=0.50, intensity_band=(1, 2))),
        (7, _Drift(plant_probability=0.45, intensity_band=(1, 2))),
        (999, _Drift(plant_probability=0.25, intensity_band=(1, 1))),
    ),
}

#: Planted at a band that does NOT consult the day, by the same claim that
#: makes `somatic_anxiety` rise. These are the layer's built-in negative
#: controls: their slopes should be indistinguishable from the shuffled-time
#: control, and a report that shows them moving has found a bug in the
#: analysis rather than a result.
FLAT_BY_DESIGN: dict[str, _Drift] = {
    # CSAI-2 cognitive-anxiety subscale [Martens1990; Cox2003]
    "cognitive_anxiety": _Drift(plant_probability=0.55, intensity_band=(1, 3)),
    # CSAI-2 self-confidence subscale [Martens1990; Cox2003]
    "self_confidence": _Drift(plant_probability=0.55, intensity_band=(1, 3)),
}

#: The constructs this module governs directly. Anything else a record carries
#: arrives from the athlete's fixed trait construct set, drawn once per athlete.
DRIFTING_CONSTRUCTS: tuple[str, ...] = tuple(TIMING_BIAS)
CONTROLLED_CONSTRUCTS: tuple[str, ...] = (*DRIFTING_CONSTRUCTS, *FLAT_BY_DESIGN)


def drift_for(construct: str, days_before: int) -> _Drift | None:
    """The drift governing `construct` at `days_before`, or `None` if ungoverned.

    Flat constructs return their single day-independent `_Drift`, which is the
    point: the function has the same shape for both, so a caller cannot
    accidentally treat "flat" as "absent".
    """
    if days_before < 0:
        raise ValueError(
            f"days_before must be >= 0 (days BEFORE the competition), got {days_before}. "
            "This project is pre-competition throughout; see RawRecord.__post_init__."
        )
    if construct in FLAT_BY_DESIGN:
        return FLAT_BY_DESIGN[construct]
    ladder = TIMING_BIAS.get(construct)
    if ladder is None:
        return None
    for upper, drift in ladder:
        if days_before <= upper:
            return drift
    raise AssertionError(f"{construct!r} ladder has no catch-all bound")  # pragma: no cover


@dataclass(frozen=True)
class PanelSpec:
    """The shape of a panel corpus, with its arguments checked.

    Defaults are the owner-confirmed ones of 2026-09-29: 300 athletes, a
    deliberately ragged number of timepoints so that the
    `MIN_TIMEPOINTS_FOR_SLOPE` suppression rule suppresses something real and
    its rate is a measured number rather than 0% or 100%.
    """

    n_athletes: int = 300
    seed: int = 22
    long_series_share: float = 0.70
    long_series_points: tuple[int, int] = (4, 6)
    short_series_points: tuple[int, int] = (2, 3)

    def __post_init__(self) -> None:
        if self.n_athletes < 1:
            raise ValueError("a panel corpus needs at least one athlete")
        if not 0.0 <= self.long_series_share <= 1.0:
            raise ValueError("long_series_share is a proportion")
        for name, band in (
            ("long_series_points", self.long_series_points),
            ("short_series_points", self.short_series_points),
        ):
            lo, hi = band
            if not (1 <= lo <= hi <= len(DAY_LADDER)):
                raise ValueError(f"{name}={band!r} is outside 1..{len(DAY_LADDER)}")
        short_max, long_min = self.short_series_points[1], self.long_series_points[0]
        if short_max < MIN_TIMEPOINTS_FOR_SLOPE <= long_min:
            return
        raise ValueError(
            "the two bands must straddle MIN_TIMEPOINTS_FOR_SLOPE "
            f"({MIN_TIMEPOINTS_FOR_SLOPE}); otherwise the suppression rate is 0% or 100% "
            "and measures nothing."
        )


@dataclass(frozen=True)
class AthletePanel:
    """One synthetic athlete: a fixed trait, and a series of records over time."""

    athlete_id: str
    sport: str
    trait_constructs: tuple[str, ...]
    records: tuple[RawRecord, ...]

    def __post_init__(self) -> None:
        if not self.records:
            raise ValueError(f"panel {self.athlete_id!r} has no records")
        days = [r.time_to_competition_days for r in self.records]
        if any(d is None for d in days):
            raise ValueError(
                f"panel {self.athlete_id!r} has a record with no day-offset. A panel "
                "record without a time index is the exact gap that blocked this phase "
                "on synth_precomp_v1; it may not be reintroduced here."
            )
        if len(set(days)) != len(days):
            raise ValueError(
                f"panel {self.athlete_id!r} has two records at the same day-offset. "
                "One athlete speaking twice on one day is a repeated measure this "
                "generator does not model, and it would put two points on one x."
            )
        if list(days) != sorted(days, reverse=True):
            raise ValueError(f"panel {self.athlete_id!r} is not ordered far-to-near")

    @property
    def n_timepoints(self) -> int:
        return len(self.records)

    @property
    def days(self) -> tuple[int, ...]:
        return tuple(int(r.time_to_competition_days) for r in self.records)


def athlete_id_of(record: RawRecord) -> str | None:
    """The athlete this record belongs to, or `None` for a non-panel record.

    Returns `None` for every `synth_precomp_v1` record, which is the honest
    answer: v1 has no identity axis and this accessor must not invent one.
    """
    return record.extra.get("athlete_id") if record.extra else None


def timepoint_index_of(record: RawRecord) -> int | None:
    """Position in its athlete's series, far-to-near, or `None` if not a panel."""
    return record.extra.get("timepoint_index") if record.extra else None


def _realise_graded_unbiased(
    construct: str, rng: random.Random, sport: str, band: tuple[int, int]
) -> tuple[str, dict[str, Any]]:
    """A graded realisation at a chosen intensity band, with NO cue preference.

    The band is this module's drift mechanism, so intensity has to be
    controllable -- which is why `synthetic._realise` (whose intensity is drawn
    from fixed weights) cannot be used directly for the governed constructs.
    Everything else matches it exactly: a flat `rng.randrange` over the bank,
    and the same `template_id` shape that `src/evaluation/splits.py` groups on
    to build a leakage-free split.

    What it deliberately does NOT do is consult `CONSTRUCT_CUES`. See the
    module docstring: preferring templates the lexicon can detect would inflate
    the lexicon's own score on a corpus this project also evaluates against.
    """
    lo, hi = band
    intensity = rng.randint(lo, hi)
    bank = GRADED_REALISATIONS[construct][intensity]
    index = rng.randrange(len(bank))
    spec = {
        "construct": construct,
        "intensity": intensity,
        "template_id": f"{construct}:i{intensity}:{index}",
    }
    return _fill(bank[index], sport), spec


def _plant(
    construct: str,
    drift: _Drift,
    rng: random.Random,
    sport: str,
    planted: list[dict[str, Any]],
    sentences: list[str],
) -> None:
    """Realise one governed construct, if the draw says so. Graded constructs only."""
    if rng.random() >= drift.plant_probability:
        return
    sentence, spec = _realise_graded_unbiased(construct, rng, sport, drift.intensity_band)
    spec["governed_by"] = "TIMING_BIAS" if construct in TIMING_BIAS else "FLAT_BY_DESIGN"
    spec["anchor"] = DRIFT_CITATION
    sentences.append(_vary(_frame(sentence, rng), rng))
    planted.append(spec)


def generate_panel_record(
    *,
    athlete_id: str,
    sport: str,
    trait_constructs: Sequence[str],
    days_before: int,
    timepoint_index: int,
    seed: int,
) -> RawRecord:
    """One record for one athlete at one distance from the competition.

    Deterministic in `seed`: the same arguments produce byte-identical text,
    the guarantee `synthetic.generate_records` and
    `scenarios.generate_scenario_record` both already make.

    Two sources of variation, deliberately separated:

    * **Between athletes** -- `trait_constructs`, drawn once per athlete and
      unchanged across the series. This is the athlete's trait.
    * **Within an athlete** -- `TIMING_BIAS` and `FLAT_BY_DESIGN`, redrawn at
      every timepoint. This is the only thing that moves along the series, and
      it is what a trajectory feature is being asked to recover.

    The two cannot overlap: `generate_panel` filters the governed constructs out
    of the trait draw and this function refuses a trait set containing one, so a
    construct is never planted by both mechanisms in the same record.
    """
    if sport not in SPORTS:
        raise ValueError(f"unknown sport {sport!r}")
    if any(c in CONTROLLED_CONSTRUCTS for c in trait_constructs):
        raise ValueError(
            "a trait construct may not be one this module governs over time "
            f"({CONTROLLED_CONSTRUCTS}); the drift would be planted twice and the "
            "within-athlete and between-athlete sources of variation would mix."
        )
    rng = random.Random(seed)

    sentences: list[str] = []
    planted: list[dict[str, Any]] = []

    if rng.random() < 0.35:
        sentences.append(_vary(_fill(rng.choice(NEUTRAL_SENTENCES), sport), rng))

    # --- within-athlete: the governed constructs, redrawn every timepoint ---
    for construct in CONTROLLED_CONSTRUCTS:
        drift = drift_for(construct, days_before)
        assert drift is not None  # CONTROLLED_CONSTRUCTS are governed by construction
        _plant(construct, drift, rng, sport, planted, sentences)

    # --- between-athlete: the athlete's fixed trait constructs ---
    # Realised through `synthetic._realise`, the ordinary corpus path: its
    # intensity is drawn from fixed weights and its template from a flat
    # randrange, so nothing here is selected for detectability.
    for construct in trait_constructs:
        sentence, spec = _realise(construct, rng, sport)
        if _contradicts(spec, planted):
            continue
        spec["governed_by"] = "ATHLETE_TRAIT"
        sentences.append(_vary(_frame(sentence, rng), rng))
        planted.append(spec)

    # Same interpretation-modifier mechanism as both existing generators, so a
    # v2 record reads like a v1 record rather than like a third dialect.
    anxiety = [
        p
        for p in planted
        if p["construct"] in ("cognitive_anxiety", "somatic_anxiety") and p.get("intensity", 0) >= 2
    ]
    interpretation: str | None = None
    if anxiety and rng.random() < 0.45:
        appraisal = next(
            (p.get("label") for p in planted if p["construct"] == "appraisal_orientation"), None
        )
        if appraisal == "challenge":
            interpretation = "facilitative"
        elif appraisal == "threat":
            interpretation = "debilitative"
        else:
            interpretation = rng.choice(("facilitative", "debilitative"))
        sentences.append(
            _vary(_fill(rng.choice(INTERPRETATION_REALISATIONS[interpretation]), sport), rng)
        )

    if not sentences:
        sentences.append(_vary(_fill(rng.choice(NEUTRAL_SENTENCES), sport), rng))

    return RawRecord(
        record_id=f"{SOURCE_ID}-{athlete_id}-d{days_before:02d}",
        source_id=SOURCE_ID,
        text=" ".join(sentences),
        time_to_competition_days=days_before,
        sport=sport,
        competition_level=None,
        region=None,
        source_type="synthetic",
        language="en",
        training_load_hint=None,
        synthetic=True,
        deidentified=False,
        generation_spec={
            "planted_constructs": planted,
            "interpretation_modifier": interpretation,
            "panel": {
                "athlete_id": athlete_id,
                "days_before": days_before,
                "timepoint_index": timepoint_index,
                "trait_constructs": list(trait_constructs),
            },
            "drift_claim": DRIFT_CITATION,
            "generator": f"{GENERATOR_NAME}@{GENERATOR_VERSION}+panel",
            "seed": seed,
            "NOTE": (
                "Generation metadata, NOT a label. Never use as evaluation ground truth "
                "-- see docs/data_sources.md. The temporal drift in this corpus was "
                "PLANTED by src/ingestion/temporal.py; recovering it measures this "
                "project's instrumentation, not athletes."
            ),
        },
        # Not a new RawRecord field: see the module docstring. `extra` is the
        # schema's documented slot, and using it costs no reproducibility hash.
        extra={"athlete_id": athlete_id, "timepoint_index": timepoint_index},
    )


def _draw_days(rng: random.Random, n_points: int) -> tuple[int, ...]:
    """`n_points` distinct days from the ladder, ordered far-to-near.

    Sampled without replacement so no athlete has two records on one day, and
    the day-0 end is favoured slightly so that series tend to run towards the
    competition rather than stopping a fortnight out -- which is where the
    planted drift lives and therefore where a trajectory feature has anything
    to recover.
    """
    weights = [1.0 + (len(DAY_LADDER) - i) * 0.12 for i in range(len(DAY_LADDER))]
    pool = list(DAY_LADDER)
    chosen: list[int] = []
    for _ in range(n_points):
        total = sum(weights)
        pick = rng.random() * total
        running = 0.0
        for i, w in enumerate(weights):
            running += w
            if pick <= running:
                chosen.append(pool[i])
                weights[i] = 0.0
                break
        else:  # pragma: no cover - float guard
            i = next(j for j, w in enumerate(weights) if w > 0.0)
            chosen.append(pool[i])
            weights[i] = 0.0
    return tuple(sorted(chosen, reverse=True))


def generate_panel(
    *, athlete_index: int, spec: PanelSpec, sports: Sequence[str] = SPORTS
) -> AthletePanel:
    """One athlete's whole series, deterministic in `spec.seed` and the index."""
    rng = random.Random(spec.seed * 100_003 + athlete_index)
    athlete_id = f"A{athlete_index:04d}"
    sport = rng.choice(list(sports))
    # Drawn ONCE per athlete and reused at every timepoint: this is the
    # athlete's stable trait, and it is the only between-athlete variation.
    # Constructs this module governs over time are excluded, so the two
    # sources of variation stay separable.
    trait_constructs = tuple(c for c in _draw_constructs(rng) if c not in CONTROLLED_CONSTRUCTS)

    lo, hi = (
        spec.long_series_points
        if rng.random() < spec.long_series_share
        else spec.short_series_points
    )
    n_points = rng.randint(lo, hi)
    days = _draw_days(rng, n_points)

    records = tuple(
        generate_panel_record(
            athlete_id=athlete_id,
            sport=sport,
            trait_constructs=trait_constructs,
            days_before=day,
            timepoint_index=index,
            seed=spec.seed * 1_000_003 + athlete_index * 101 + day,
        )
        for index, day in enumerate(days)
    )
    return AthletePanel(
        athlete_id=athlete_id, sport=sport, trait_constructs=trait_constructs, records=records
    )


def build_panel_corpus(spec: PanelSpec | None = None) -> tuple[AthletePanel, ...]:
    """The whole `synth_precomp_v2` corpus as panels, deterministic in `spec`."""
    spec = spec or PanelSpec()
    return tuple(generate_panel(athlete_index=i, spec=spec) for i in range(spec.n_athletes))


def panel_generator_stamp(spec: PanelSpec, *, generated_on: str | None = None) -> GeneratorStamp:
    """The generator stamp written into `synth_precomp_v2`'s provenance."""
    return GeneratorStamp(
        name=f"{GENERATOR_NAME}+panel",
        version=f"{GENERATOR_VERSION}+t1",
        kind="template-grammar",
        seed=spec.seed,
        generated_on=generated_on or _dt.date.today().isoformat(),
        prompts_location=(
            "src/ingestion/temporal.py (version-controlled TIMING_BIAS ladder over the "
            "src/ingestion/synthetic.py template bank, which is imported unchanged)"
        ),
        notes=(
            "Deterministic seeded template grammar, no language model and no network "
            "call. Adds a WITHIN-ATHLETE temporal drift on top of the v1 generator: "
            f"somatic anxiety rises approaching the competition ({DRIFT_CITATION}) while "
            "cognitive anxiety and self-confidence are planted at a day-independent band "
            "and serve as designed-flat negative controls. The drift is a generator "
            "design choice taken by the owner on 2026-09-29, NOT a measurement; see this "
            "module's docstring and reports/temporal.md."
        ),
        extra={
            "drifting_constructs": list(DRIFTING_CONSTRUCTS),
            "flat_by_design": list(FLAT_BY_DESIGN),
            "drift_anchor": DRIFT_CITATION,
            "panel": {
                "n_athletes": spec.n_athletes,
                "day_ladder": list(DAY_LADDER),
                "long_series_share": spec.long_series_share,
                "long_series_points": list(spec.long_series_points),
                "short_series_points": list(spec.short_series_points),
                "min_timepoints_for_slope": MIN_TIMEPOINTS_FOR_SLOPE,
            },
            "v1_relationship": (
                "additive; synth_precomp_v1 is frozen and byte-unmodified by this corpus"
            ),
        },
    )


def panel_descriptor(
    source_id: str = SOURCE_ID, *, spec: PanelSpec | None = None
) -> SourceDescriptor:
    """The allow-list descriptor for the panel corpus.

    Deliberately NOT `synthetic.synthetic_descriptor` with a different id. That
    descriptor's `url_or_citation` names `src/ingestion/synthetic.py` and says
    nothing about a planted temporal drift, and a provenance record that
    understates what a generator did is the one document in the corpus that
    must not. This one names the drift, the claim behind it, the citation and
    the date the owner took the decision, so a reader who opens
    `provenance.json` alone learns that the time structure in this corpus was
    designed rather than observed.
    """
    spec = spec or PanelSpec()
    return SourceDescriptor(
        source_id=source_id,
        source_name=(
            "Synthetic pre-competition athlete panels with a planted temporal drift "
            f"(template grammar v{GENERATOR_VERSION}, panel extension v1)"
        ),
        allowlist_category="A2_synthetic",
        url_or_citation=(
            "Generated for this project by src/ingestion/temporal.py "
            f"({GENERATOR_NAME}@{GENERATOR_VERSION}+panel, seed={spec.seed}). Not derived "
            "from any external corpus. Additive to synth_precomp_v1, which is frozen and "
            "unmodified."
        ),
        licence_or_consent_basis=(
            "Project-generated synthetic text. No third-party licence applies and no "
            "human subject is involved: no real person's words are reproduced, "
            "paraphrased, or used as a generation input. Released under the "
            "repository licence alongside the code that produces it."
        ),
        permitted_uses=(
            "Research use, training, evaluation, redistribution, and publication of "
            "verbatim examples. Because no real athlete is involved, this is the only "
            "category in the corpus from which examples may be quoted verbatim in the "
            "paper or dashboard (docs/ethics.md sec.3.3 condition 2)."
        ),
        redistribution_permitted=True,
        synthetic=True,
        subject_is_adult=True,  # No human subject exists; the athlete voice is fictional.
        language="en",
        notes=(
            "PANEL CORPUS WITH A PLANTED DRIFT. Each athlete_id carries a series of "
            "records at different time_to_competition_days. The within-athlete temporal "
            "structure was PLANTED by src/ingestion/temporal.py under an owner decision "
            "of 2026-09-29: somatic anxiety rises approaching the event while cognitive "
            f"anxiety and self-confidence stay flat, per {DRIFT_CITATION}. Any trajectory "
            "recovered from this corpus is a sanity check on this project's own "
            "instrumentation, NOT evidence about athletes and NOT support for the "
            "psychological claim itself. athlete_id and timepoint_index live in "
            "record.extra. Template selection is UNBIASED with respect to "
            "src.evaluation.baselines.CONSTRUCT_CUES: no realisation is chosen because "
            "the lexicon can detect it, so this corpus does not inflate the lexicon "
            "baseline (OPEN-021). synth_precomp_v1 is untouched by this corpus."
        ),
        sport=None,  # Varies per record; recorded at record level.
        competition_level=None,
        region=None,
        source_type="synthetic",
        time_to_competition_days=None,
        declares={
            "not_scraped_personal_social_media": True,
            "no_minors": True,
            "not_private_communication": True,
            "licence_and_tos_permit_this_use": True,
            "not_behind_auth_or_paywall": True,
            "not_health_injury_or_treatment_content": True,
            "provenance_is_complete": True,
        },
    )
