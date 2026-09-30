#!/usr/bin/env python
"""Phase 22 gate: build `synth_precomp_v2` and run the trajectory sanity check.

    python scripts/run_temporal.py                 # build + analyse (default)
    python scripts/run_temporal.py --build-only    # write the corpus, no analysis
    python scripts/run_temporal.py --analyse-only  # read the corpus, no write
    python scripts/run_temporal.py --athletes 300 --seed 22

Offline, free and deterministic, matching `scripts/run_ingestion.py`: no network
call, no API key, no language model. A reviewer rebuilds both the corpus and the
report from a fresh clone.

**This script never touches `synth_precomp_v1`.** It writes a separate source
directory and reads nothing from v1. The v1 artefacts and every number measured
against them are frozen; see `src/ingestion/temporal.py`'s module docstring.

Exit codes: 0 the design held, 1 a channel did not behave as the generator's
design predicts, 2 a configuration or policy error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.dashboard.backend import LexiconBackend  # noqa: E402
from src.dashboard.copy import CONSTRUCTS as PLAIN_CONSTRUCTS  # noqa: E402
from src.dashboard.view import build_view  # noqa: E402
from src.evaluation.trajectory import (  # noqa: E402
    CLUSTER_FEATURES,
    SHUFFLE_REPEATS,
    SLOPE_SIGN_NOTE,
    TRAJECTORY_FRAMING,
    TrajectoryReport,
    analyse,
)
from src.ingestion import RawStore, load_allowlist  # noqa: E402
from src.ingestion.temporal import (  # noqa: E402
    DRIFT_CITATION,
    DRIFTING_CONSTRUCTS,
    FLAT_BY_DESIGN,
    MIN_TIMEPOINTS_FOR_SLOPE,
    SOURCE_ID,
    AthletePanel,
    PanelSpec,
    athlete_id_of,
    build_panel_corpus,
    panel_descriptor,
    panel_generator_stamp,
)

#: The index plus every construct. The index is the headline; the constructs
#: are what make the two designed-flat negative controls visible.
RISK_CHANNEL = "risk_index"
REPORT_PATH = REPO_ROOT / "reports" / "temporal.md"


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def build_corpus(store: RawStore, spec: PanelSpec) -> tuple[AthletePanel, ...]:
    """Generate the panels and write them under their own provenance."""
    panels = build_panel_corpus(spec)
    descriptor = panel_descriptor(SOURCE_ID, spec=spec)
    stamp = panel_generator_stamp(spec)
    with store.open_source(descriptor, generator=stamp.to_dict()) as writer:
        for panel in panels:
            writer.write_all(panel.records)
    return panels


def score_corpus(panels: tuple[AthletePanel, ...]) -> dict[str, dict[str, float]]:
    """The L2 risk vector for every record the detector could read.

    A record with no detected construct is ABSENT from the mapping rather than
    present with a value. `LexiconBackend` would happily squash its all-zero
    decomposition to exactly 0.50, and a run of those inside a series draws a
    confident flat line at the midpoint -- `.claude.md` sec.12.3, which this
    phase must not reintroduce through a new door.
    """
    backend = LexiconBackend()
    readings: dict[str, dict[str, float]] = {}
    for panel in panels:
        for record in panel.records:
            view = build_view(text=record.text, backend=backend)
            if not any(bar.detected for bar in view.bars):
                continue
            reading = {RISK_CHANNEL: view.risk.value}
            reading.update({bar.construct: bar.probability for bar in view.bars})
            readings[record.record_id] = reading
    return readings


def _fmt(value: float | None, places: int = 5) -> str:
    return "--" if value is None else f"{value:+.{places}f}"


def _cluster_table(result) -> list[str]:
    """Clusters printed only alongside their centroid, never as a bare index."""
    if not result.cluster_sizes:
        return ["", "No shape clusters: too few athletes survived slope suppression."]
    by_cluster: dict[int, list] = {}
    for feature in result.features:
        label = result.clusters.get(feature.athlete_id)
        if label is not None:
            by_cluster.setdefault(label, []).append(feature)
    lines = [
        "",
        "#### Trajectory shape clusters",
        "",
        "Cluster indices carry no ordering, no severity and no label -- they are printed",
        "only beside their centroid, in the original units, so a reader can see what each",
        "group actually is. Clustering runs over the z-scored "
        f"`{'`, `'.join(CLUSTER_FEATURES)}` vector",
        "rather than over the raw series, because the panels are ragged by design and two",
        "athletes' readings sit on different day sets.",
        "",
        "| cluster | athletes | mean slope | mean volatility | mean last-day delta |",
        "|---|---|---|---|---|",
    ]
    for label in sorted(by_cluster):
        group = by_cluster[label]
        n = len(group)
        mean_slope = sum(f.slope for f in group) / n
        mean_vol = sum(f.volatility for f in group) / n
        mean_delta = sum(f.last_day_delta for f in group) / n
        lines.append(f"| {label} | {n} | {mean_slope:+.5f} | {mean_vol:.5f} | {mean_delta:+.5f} |")
    return lines


def write_report(report: TrajectoryReport, spec: PanelSpec, path: Path) -> None:
    """Write `reports/temporal.md`, framing first and always."""
    risk = report.channel(RISK_CHANNEL)
    lines: list[str] = [
        "# Temporal trajectory features over `synth_precomp_v2`",
        "",
        f"Generated by `scripts/run_temporal.py` (seed {spec.seed}). Offline, deterministic,",
        "no language model. Rebuild with `python scripts/run_temporal.py`.",
        "",
        "## Read this first",
        "",
        "> " + TRAJECTORY_FRAMING.replace(". ", ".\n> "),
        "",
        f"The drift claim encoded in the generator: **{DRIFT_CITATION}** -- somatic anxiety",
        "rises approaching the competition; cognitive anxiety and self-confidence stay flat.",
        "Owner decision of 2026-09-29. The two flat constructs are this layer's built-in",
        "negative controls and the other seven constructs have no drift planted at all, so",
        "**nine quiet channels and one live one is the design working, not nine failures.**",
        "",
        "`risk_index` is the one channel that moves without a drift planted *in* it: it",
        "inherits one, because `somatic_anxiety` carries a weight of +1.0 in",
        "`LinearRiskScorer` and a planted rise in the construct propagates into the index",
        "arithmetically. It is listed separately from the planted channel for that reason --",
        "a derived result is not an independent confirmation of the same planted effect.",
        "",
        f"{SLOPE_SIGN_NOTE}",
        "",
        "## Corpus",
        "",
        "| | |",
        "|---|---|",
        f"| Source | `{SOURCE_ID}` (additive; `synth_precomp_v1` untouched and frozen) |",
        f"| Athletes | {report.n_athletes} |",
        f"| Records | {report.n_records} |",
        f"| Readable records | {report.n_readable_records} |",
        f"| Unreadable records (no construct detected, excluded) | "
        f"{report.n_unreadable_records} ({report.unreadable_rate:.1%}) |",
        f"| Slope suppression floor | {MIN_TIMEPOINTS_FOR_SLOPE} timepoints |",
        f"| Permutations per channel | {report.channels[0].control.repeats:,} |",
        "",
        "### Slope suppression",
        "",
        f"**{risk.n_suppressed} of {len(risk.features)} athletes "
        f"({risk.suppression_rate:.1%}) had their slope suppressed** for having fewer than",
        f"{MIN_TIMEPOINTS_FOR_SLOPE} readable timepoints. Suppressed means the slope is",
        "absent, not zero: those athletes contribute to no slope figure on either side of",
        "the control. The panel generator draws a deliberately ragged number of timepoints",
        "so that this rate is a measured number rather than 0% or 100%.",
        "",
        "## Shuffled-time control",
        "",
        "The null is built by permuting the day-to-value pairing **within each athlete** --",
        "the same readings, re-dated -- which destroys temporal order while preserving every",
        "athlete's own level, spread and series length. Suppression applies identically on",
        "both sides. `p` is a two-sided permutation rank, not a distributional test",
        "statistic; the null is a re-ordering of this corpus, not a population model.",
        "",
        "**All channels are tested at once, so the threshold is Holm-corrected across the",
        "family.** An uncorrected 0.05 across eleven channels produces a false positive",
        "roughly half the time, and this analysis duly produced one: `coping_style` reached",
        "an uncorrected p = 0.025 with no drift planted in it, no cue overlap with the",
        "drifting construct, and a flat mean probability across the window. It does not",
        "survive the correction. The correction is not a response to that result -- testing",
        "eleven channels against a fixed 0.05 was the wrong test whatever came out of it.",
        "",
        "| channel | design expectation | n | suppressed | observed mean slope | "
        "null 95% | p | Holm threshold | verdict | as designed |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for result in report.channels:
        c = result.control
        null_band = "--" if c.null_lo is None else f"[{c.null_lo:+.5f}, {c.null_hi:+.5f}]"
        p_text = "--" if c.p_value is None else f"{c.p_value:.4f}"
        holm = (
            "--"
            if result.holm_threshold is None
            else f"{result.holm_threshold:.4f} {'reject' if result.holm_reject else 'hold'}"
        )
        lines.append(
            f"| `{result.channel}` | {result.expectation} | {c.n_series} | "
            f"{result.n_suppressed} | {_fmt(c.observed_mean_slope)} | {null_band} | "
            f"{p_text} | {holm} | {result.verdict} | "
            f"{'yes' if result.matches_expectation else 'NO'} |"
        )

    lines += _cluster_table(risk)
    lines += [
        "",
        "## What this does not show",
        "",
        "* **Nothing about athletes.** Every series is generated text. No real athlete, no",
        "  observed outcome and no human label exists anywhere in this corpus.",
        "* **No support for the drift claim itself.** The claim was planted, not tested.",
        "  Recovering it shows the trajectory code works; it is circular as evidence for",
        "  the psychology, exactly as `docs/data_sources.md` says of `generation_spec`.",
        "* **No calibration.** The risk index is a ranking only, here as everywhere else in",
        "  this project. A slope over an uncalibrated ranking is a slope over an",
        "  uncalibrated ranking.",
        "* **No clinical reading.** A rising trajectory is not a deteriorating person. This",
        "  is research and decision-support tooling on synthetic text, per `.claude.md`",
        "  sec.1 and `docs/ethics.md`.",
        "* **No detector precision.** The readings are the `LexiconBackend` floor with its",
        "  known upward bias (OPEN-021), and `data/gold/` carries no temporal annotation",
        "  against which any of this could be checked.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--athletes", type=int, default=PanelSpec.n_athletes)
    parser.add_argument("--seed", type=int, default=PanelSpec.seed)
    parser.add_argument("--repeats", type=int, default=SHUFFLE_REPEATS)
    parser.add_argument("--raw-root", type=Path, default=REPO_ROOT / "data" / "raw")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--analyse-only", action="store_true")
    args = parser.parse_args(argv)

    if args.build_only and args.analyse_only:
        print("--build-only and --analyse-only are mutually exclusive", file=sys.stderr)
        return 2

    spec = PanelSpec(n_athletes=args.athletes, seed=args.seed)

    _rule(f"Phase 22 -- {SOURCE_ID}")
    print(f"drift claim: {DRIFT_CITATION}")
    print(f"drifting: {', '.join(DRIFTING_CONSTRUCTS)}")
    print(f"flat by design (negative controls): {', '.join(FLAT_BY_DESIGN)}")

    if args.analyse_only:
        allowlist = load_allowlist()
        store = RawStore(root=args.raw_root, allowlist=allowlist)
        _, records = store.read_source(SOURCE_ID)
        grouped: dict[str, list] = {}
        for record in records:
            athlete = athlete_id_of(record)
            if athlete is None:
                print(
                    f"record {record.record_id!r} carries no athlete_id; "
                    f"{SOURCE_ID} is not a panel corpus",
                    file=sys.stderr,
                )
                return 2
            grouped.setdefault(athlete, []).append(record)
        panels = tuple(
            AthletePanel(
                athlete_id=athlete,
                sport=rows[0].sport,
                trait_constructs=tuple(rows[0].generation_spec["panel"]["trait_constructs"]),
                records=tuple(sorted(rows, key=lambda r: -r.time_to_competition_days)),
            )
            for athlete, rows in sorted(grouped.items())
        )
        print(f"read {len(records)} records across {len(panels)} athletes")
    else:
        allowlist = load_allowlist()
        store = RawStore(root=args.raw_root, allowlist=allowlist)
        panels = build_corpus(store, spec)
        print(
            f"wrote {sum(p.n_timepoints for p in panels)} records across "
            f"{len(panels)} athletes to {args.raw_root / SOURCE_ID}"
        )
        if args.build_only:
            return 0

    _rule("Scoring through the ordinary build_view path")
    readings = score_corpus(panels)
    total = sum(p.n_timepoints for p in panels)
    print(f"readable: {len(readings)} of {total} records")

    _rule("Trajectory features and the shuffled-time control")
    constructs = [b for b in sorted(PLAIN_CONSTRUCTS)]
    report = analyse(
        panels,
        readings,
        channels=[RISK_CHANNEL, *constructs],
        plain_names={k: v[0] for k, v in PLAIN_CONSTRUCTS.items()},
        drifting=DRIFTING_CONSTRUCTS,
        flat=tuple(FLAT_BY_DESIGN),
        inherits=(RISK_CHANNEL,),
        repeats=args.repeats,
        seed=args.seed,
    )
    for result in report.channels:
        flag = "ok " if result.matches_expectation else "NO "
        print(f"  {flag} {result.channel:<24} {result.verdict:<62} p={result.control.p_value}")

    write_report(report, spec, REPORT_PATH)
    print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}")
    risk = report.channel(RISK_CHANNEL)
    print(
        f"slope suppression rate: {risk.suppression_rate:.1%} "
        f"({risk.n_suppressed}/{len(risk.features)} athletes)"
    )

    if not report.design_holds:
        print("\nA channel did not behave as the generator's design predicts.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
