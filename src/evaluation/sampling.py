"""The Phase 11 gold-set sampling plan, as executable code rather than prose.

What a gold set has to do here
-------------------------------
Contribution #1 is "a construct-grounded athlete-text corpus with span→construct
labels and reported inter-annotator agreement". Three things follow, and the
plan below is the smallest design that satisfies all three at once:

1. **It is the evaluation set.** Every number in the results table is measured
   against it, so it must not overlap the phrasings the model trained on.
2. **It carries a kappa.** Two independent annotators (`CLAUDE.md` §2 layer 4:
   Saikalyan plus at least one peer) must label the same items, so agreement is
   computable *per construct*, not just overall.
3. **It is small and human-produced**, so every item spent is expensive and
   nothing may be wasted on items an annotator cannot reasonably judge.

Why the obvious plan does not work, measured not assumed
---------------------------------------------------------
The obvious plan is "draw the gold set from the test side of
`template_disjoint_split`". Running it on this corpus gives 98 records / 228
utterances on the test side -- and **zero** records planting
`appraisal_orientation`. One of the ten locked constructs would have no gold
items at all, and a kappa for it would be undefined rather than low.

The cause is that `template_disjoint_split` shuffles all 85 templates as one
pool. With 7-12 templates per construct, a global 20% holdout can and does miss
a construct entirely. That function is not wrong -- it is the right tool for
comparing a leaky split against a clean one, which is what it was built for --
but it is the wrong tool for carving out an evaluation set that must cover
every label.

The fix: partition templates **per construct**
-----------------------------------------------
`construct_stratified_template_partition` holds out a fraction of each
construct's templates independently, with a floor of one. Disjointness is
preserved -- it is still a partition of the template set, so no template appears
on both sides and `Split.is_template_disjoint` still holds -- but coverage of
every construct is now guaranteed by construction rather than by luck.

Records are then assigned exactly as `template_disjoint_split` does it: a record
goes to the gold pool only if **every** template it uses is held out, to the
training pool only if none is, and is otherwise discarded. Discarding is not
waste-avoidance failure; a record straddling the partition leaks whichever side
it is put on.

Why the gold set is drawn per utterance but partitioned per record
--------------------------------------------------------------------
Labelling happens per utterance (Phase 8 built `InterimRecord` for exactly that
reason). Leakage happens per template, and templates attach to records. Mixing
the two units is the mistake that would quietly reintroduce the leakage: two
utterances of the same record share its templates, so drawing utterances
independently would put sibling utterances on both sides of the partition. Here
the partition is computed over records first and utterances are drawn only
within the resulting pools.

What this module does not do
-----------------------------
It **draws a sample and writes a plan**. It does not write labels, and it cannot
write into `data/gold/` -- that root is human-owned (`CLAUDE.md` §4) and the
store guards refuse it. The output is a candidate list under
`data/processed/gold_candidates/`, which annotators then label by hand.

Pure Python, deterministic under `seed`, offline.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from src.evaluation.profile import (
    MIN_ANNOTATABLE_TOKENS,
    junk_flags,
    time_band,
    tokenise,
)
from src.preprocessing.records import InterimRecord

# ---------------------------------------------------------------------------
# Plan parameters. Every one of these is a judgement; each is defended where it
# is defined so the paper's methods section can be written from this file.
# ---------------------------------------------------------------------------

#: Fraction of EACH construct's templates held out for the gold set.
#:
#: 0.35, not the 0.20 used by `template_disjoint_split`. Higher because the
#: constraint here is different: 0.20 of 8 templates is 1.6, and a construct
#: whose entire held-out evidence is one or two phrasings yields a kappa that
#: describes those phrasings rather than the construct. At 0.35 the thinnest
#: construct (`resilience`, 7 templates) holds out 2 and the typical one holds
#: out 3. That is still thin, and §"Known limits" in `reports/eda.md` says so
#: rather than letting the number pass as adequate.
GOLD_TEMPLATE_HOLDOUT = 0.35

#: Minimum positive gold utterances wanted per construct before a per-construct
#: kappa is worth reporting.
#:
#: 40 is a working floor, not a power calculation -- a genuine power analysis
#: for Cohen's kappa needs an assumed true kappa and an assumed base rate, and
#: this project has neither yet. At 40 items with a base rate near 0.5, the 95%
#: bootstrap interval on kappa is roughly +/-0.20 wide, which is enough to
#: separate "substantial" from "fair" and not enough to separate 0.70 from 0.75.
#: Phase 11 should report the interval, never the point estimate alone.
MIN_POSITIVES_PER_CONSTRUCT = 40

#: Target size of the primary gold evaluation set, in utterances.
TARGET_GOLD_EVAL = 400

#: Target size of the calibration set annotators use to argue about the rubric
#: before the real thing starts.
#:
#: Drawn from **training-side** templates on purpose. Calibration is where
#: guidelines get rewritten, and an item read during an argument about the
#: rubric is no longer an independent measurement of agreement. Spending
#: training-side items on it costs no evaluation power at all.
TARGET_GOLD_DEV = 100

#: Jaccard threshold above which two utterances are treated as the same item.
NEAR_DUPLICATE_THRESHOLD = 0.9


# ---------------------------------------------------------------------------
# Template partition
# ---------------------------------------------------------------------------


def templates_by_construct(records: Sequence[InterimRecord]) -> dict[str, set[str]]:
    """construct -> the template ids that realise it, from generator metadata.

    This is one of the few legitimate uses of `generation_spec`: it is being
    read as a description of the *generator*, which is what it is, to decide
    which generator outputs to show a human. It is not being read as a label,
    and nothing downstream of here treats it as one.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for planted in (record.generation_spec or {}).get("planted_constructs", ()):
            if planted.get("construct") and planted.get("template_id"):
                out[planted["construct"]].add(planted["template_id"])
    return {k: v for k, v in sorted(out.items())}


def templates_of(record: InterimRecord) -> frozenset[str]:
    """Template ids used by the utterance's parent record."""
    return frozenset(
        planted["template_id"]
        for planted in (record.generation_spec or {}).get("planted_constructs", ())
        if "template_id" in planted
    )


@dataclass(frozen=True)
class TemplatePartition:
    """A construct-stratified split of the template set."""

    gold_templates: frozenset[str]
    train_templates: frozenset[str]
    holdout_fraction: float
    seed: int
    per_construct_holdout: dict[str, int] = field(default_factory=dict)
    per_construct_total: dict[str, int] = field(default_factory=dict)

    @property
    def is_disjoint(self) -> bool:
        return not (self.gold_templates & self.train_templates)

    @property
    def constructs_without_holdout(self) -> list[str]:
        """Constructs with no held-out template. Must be empty."""
        return sorted(k for k, v in self.per_construct_holdout.items() if v == 0)


def construct_stratified_template_partition(
    records: Sequence[InterimRecord],
    *,
    holdout_fraction: float = GOLD_TEMPLATE_HOLDOUT,
    seed: int = 42,
) -> TemplatePartition:
    """Hold out a share of every construct's templates, with a floor of one.

    A template realising two constructs is held out if *either* construct's draw
    selects it. That biases the held-out set slightly towards multi-construct
    templates, which is the right direction: a multi-construct utterance is the
    harder annotation case and is exactly where inter-annotator agreement is
    informative rather than trivially high.
    """
    by_construct = templates_by_construct(records)
    rng = random.Random(seed)
    held: set[str] = set()
    for _construct, template_ids in sorted(by_construct.items()):
        ordered = sorted(template_ids)
        rng.shuffle(ordered)
        take = max(1, round(len(ordered) * holdout_fraction))
        held.update(ordered[:take])

    everything = {t for ids in by_construct.values() for t in ids}
    return TemplatePartition(
        gold_templates=frozenset(held),
        train_templates=frozenset(everything - held),
        holdout_fraction=holdout_fraction,
        seed=seed,
        per_construct_holdout={k: len(v & held) for k, v in by_construct.items()},
        per_construct_total={k: len(v) for k, v in by_construct.items()},
    )


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------

#: Junk checks that disqualify an utterance from the gold set.
#:
#: `too_short` only. The others (`unbalanced_brackets`, `repeated_token_run`,
#: `truncated_ending`, ...) are *reported* by the profile and would be excluded
#: too if they fired, but on this corpus they do not. Excluding on a check that
#: never fires is untested code in the sampling path, so the list names the one
#: that does and the rest are caught by the assertion in `eligible_utterances`.
DISQUALIFYING_JUNK: frozenset[str] = frozenset({"too_short"})


@dataclass(frozen=True)
class EligibilityReport:
    """Why each utterance was or was not available to be sampled."""

    considered: int
    eligible: int
    excluded_junk: int
    excluded_duplicate: int
    excluded_no_template: int
    junk_breakdown: dict[str, int] = field(default_factory=dict)


def eligible_utterances(
    records: Sequence[InterimRecord],
    allowed_templates: frozenset[str],
    *,
    require_template: bool = True,
) -> tuple[list[InterimRecord], EligibilityReport]:
    """Utterances a human could usefully be asked to label.

    Three exclusions, in order, each with a reason a reviewer can check:

    * **no template / straddling.** A record is eligible only if it uses at
      least one template and *every* template it uses is in `allowed_templates`.
      Template-free records (pure logistics talk) are excluded from the gold
      *evaluation* set entirely: they carry no construct by construction, so
      they contribute nothing to a per-construct kappa while consuming
      annotator time. They are the right source for the negative-item quota,
      which `draw_gold_sample` handles separately.
    * **junk.** `too_short` items -- under `MIN_ANNOTATABLE_TOKENS` words.
      Handing an annotator "That's it." and then reporting the resulting
      disagreement as unreliability would be measuring the sampling design, not
      the annotators.
    * **duplicates.** Exact and near-duplicate text is collapsed to its first
      occurrence. This one matters more than it sounds: 73.6% of utterances in
      this corpus are exact duplicates of another utterance (the discourse
      suffixes and neutral sentences are segmented into standalone utterances
      and repeat verbatim -- "It is what it is." appears 268 times). Sampling
      without collapsing them would fill the gold set with repeats, and worse,
      would **inflate kappa**: two annotators agreeing 268 times on the same
      string is one agreement counted 268 times.
    """
    junk_counter: Counter[str] = Counter()
    excluded_junk = excluded_dupe = excluded_template = 0
    seen_exact: set[str] = set()
    seen_token_sets: list[frozenset[str]] = []
    kept: list[InterimRecord] = []

    for record in sorted(records, key=lambda r: r.record_id):
        used = templates_of(record)
        if require_template and (not used or not used <= allowed_templates):
            excluded_template += 1
            continue
        if not require_template and used and not used <= allowed_templates:
            excluded_template += 1
            continue

        failures = junk_flags(record.text)
        for failure in failures:
            junk_counter[failure] += 1
        if DISQUALIFYING_JUNK.intersection(failures):
            excluded_junk += 1
            continue

        normalised = " ".join(tokenise(record.text))
        if normalised in seen_exact:
            excluded_dupe += 1
            continue
        tokens = frozenset(normalised.split())
        if any(
            len(tokens & other) / len(tokens | other) >= NEAR_DUPLICATE_THRESHOLD
            for other in seen_token_sets
            if tokens | other
        ):
            excluded_dupe += 1
            continue

        seen_exact.add(normalised)
        seen_token_sets.append(tokens)
        kept.append(record)

    return kept, EligibilityReport(
        considered=len(records),
        eligible=len(kept),
        excluded_junk=excluded_junk,
        excluded_duplicate=excluded_dupe,
        excluded_no_template=excluded_template,
        junk_breakdown=dict(sorted(junk_counter.items())),
    )


# ---------------------------------------------------------------------------
# The draw
# ---------------------------------------------------------------------------

#: Context strata the sample is balanced over, in priority order.
#:
#: Ordered, and the order is the design. A sample cannot be balanced over
#: everything at n=400: with 10 sports x 5 levels x 5 regions x 5 time bands
#: there are 1,250 cells and 400 items. So the draw balances *marginally* --
#: each field's distribution is matched one at a time -- rather than over the
#: joint, and it does construct coverage first because that is the quota a
#: missed cell makes a kappa undefined for. `time_band` is second because
#: contribution #3 is the time-aware design and a gold set with no `day_of`
#: items cannot support any claim about it.
CONTEXT_STRATA: tuple[str, ...] = ("time_band", "sport", "competition_level", "region")


@dataclass(frozen=True)
class GoldSample:
    """One drawn candidate set, with everything needed to justify it."""

    name: str
    utterance_ids: tuple[str, ...]
    parent_record_ids: tuple[str, ...]
    seed: int
    construct_coverage: dict[str, int] = field(default_factory=dict)
    stratum_coverage: dict[str, dict[str, int]] = field(default_factory=dict)
    eligibility: EligibilityReport | None = None

    @property
    def size(self) -> int:
        return len(self.utterance_ids)

    @property
    def constructs_below_floor(self) -> list[str]:
        """Constructs whose positive count misses `MIN_POSITIVES_PER_CONSTRUCT`.

        Reported, not raised. A draw that refused to return an under-powered
        sample would leave Phase 11 with nothing to annotate; a draw that
        returns one silently would let an under-powered kappa reach the paper.
        The middle course is to hand back the sample and the shortfall together.
        """
        return sorted(
            k for k, v in self.construct_coverage.items() if v < MIN_POSITIVES_PER_CONSTRUCT
        )


def _construct_of(record: InterimRecord) -> set[str]:
    return {
        planted["construct"]
        for planted in (record.generation_spec or {}).get("planted_constructs", ())
        if planted.get("construct")
    }


def draw_gold_sample(
    pool: Sequence[InterimRecord],
    *,
    target: int,
    name: str,
    seed: int = 42,
    eligibility: EligibilityReport | None = None,
) -> GoldSample:
    """Draw `target` utterances, construct quotas first, then context balance.

    Two passes, deliberately in this order:

    **Pass 1 -- construct quota.** Round-robin across constructs, taking the
    next unused utterance whose parent plants that construct, until each has
    `MIN_POSITIVES_PER_CONSTRUCT` items or its supply is exhausted. Round-robin
    rather than construct-by-construct so that a construct processed late is not
    left picking over what the earlier ones did not want -- the rarest construct
    would otherwise get the least context-diverse items.

    **Pass 2 -- context balance.** Fill the remainder by repeatedly taking the
    item that most improves the worst-served stratum cell, in `CONTEXT_STRATA`
    priority order. Greedy rather than optimal: the exact allocation is an
    integer program, the greedy version lands within a few items of it at this
    size, and an optimal allocation nobody can follow is worse for a methods
    section than a good one anybody can.

    Deterministic: the pool is sorted by id before anything is drawn, so the
    same corpus and seed give the same sample on any machine.
    """
    rng = random.Random(seed)
    items = sorted(pool, key=lambda r: r.record_id)
    rng.shuffle(items)

    by_construct: dict[str, list[InterimRecord]] = defaultdict(list)
    for record in items:
        for construct in _construct_of(record):
            by_construct[construct].append(record)

    chosen: dict[str, InterimRecord] = {}

    # Pass 1 -- construct quota, round robin.
    counts: Counter[str] = Counter()
    constructs = sorted(by_construct)
    cursors = dict.fromkeys(constructs, 0)
    progressing = True
    while progressing and len(chosen) < target:
        progressing = False
        for construct in constructs:
            if counts[construct] >= MIN_POSITIVES_PER_CONSTRUCT or len(chosen) >= target:
                continue
            supply = by_construct[construct]
            while cursors[construct] < len(supply):
                candidate = supply[cursors[construct]]
                cursors[construct] += 1
                if candidate.record_id in chosen:
                    continue
                chosen[candidate.record_id] = candidate
                for planted in _construct_of(candidate):
                    counts[planted] += 1
                progressing = True
                break

    # Pass 2 -- context balance, greedy on the highest-priority stratum first.
    def stratum_value(record: InterimRecord, field_name: str) -> str:
        if field_name == "time_band":
            return time_band(record.time_to_competition_days)
        return str(getattr(record, field_name))

    filled: dict[str, Counter[str]] = {
        field_name: Counter(stratum_value(r, field_name) for r in chosen.values())
        for field_name in CONTEXT_STRATA
    }
    remaining = [r for r in items if r.record_id not in chosen]
    while remaining and len(chosen) < target:
        best = min(
            remaining,
            key=lambda r: (
                tuple(filled[f][stratum_value(r, f)] for f in CONTEXT_STRATA) + (r.record_id,)
            ),
        )
        remaining.remove(best)
        chosen[best.record_id] = best
        for field_name in CONTEXT_STRATA:
            filled[field_name][stratum_value(best, field_name)] += 1
        for planted in _construct_of(best):
            counts[planted] += 1

    selected = sorted(chosen.values(), key=lambda r: r.record_id)
    return GoldSample(
        name=name,
        utterance_ids=tuple(r.record_id for r in selected),
        parent_record_ids=tuple(sorted({r.parent_record_id for r in selected})),
        seed=seed,
        construct_coverage=dict(sorted(counts.items())),
        stratum_coverage={
            field_name: dict(
                sorted(Counter(stratum_value(r, field_name) for r in selected).items())
            )
            for field_name in CONTEXT_STRATA
        },
        eligibility=eligibility,
    )


# ---------------------------------------------------------------------------
# The plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GoldSamplingPlan:
    """Everything Phase 11 needs, and the evidence that it is feasible."""

    source_id: str
    seed: int
    partition: TemplatePartition
    gold_eval: GoldSample
    gold_dev: GoldSample

    @property
    def is_leakage_safe(self) -> bool:
        """No template and no parent record is shared between eval and dev."""
        return (
            self.partition.is_disjoint
            and not (set(self.gold_eval.parent_record_ids) & set(self.gold_dev.parent_record_ids))
            and not self.partition.constructs_without_holdout
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "seed": self.seed,
            "leakage_safe": self.is_leakage_safe,
            "partition": {
                "holdout_fraction": self.partition.holdout_fraction,
                "gold_templates": sorted(self.partition.gold_templates),
                "train_templates": sorted(self.partition.train_templates),
                "per_construct_holdout": self.partition.per_construct_holdout,
                "per_construct_total": self.partition.per_construct_total,
                "disjoint": self.partition.is_disjoint,
                "constructs_without_holdout": self.partition.constructs_without_holdout,
            },
            "gold_eval": asdict(self.gold_eval),
            "gold_dev": asdict(self.gold_dev),
            "parameters": {
                "GOLD_TEMPLATE_HOLDOUT": GOLD_TEMPLATE_HOLDOUT,
                "MIN_POSITIVES_PER_CONSTRUCT": MIN_POSITIVES_PER_CONSTRUCT,
                "TARGET_GOLD_EVAL": TARGET_GOLD_EVAL,
                "TARGET_GOLD_DEV": TARGET_GOLD_DEV,
                "NEAR_DUPLICATE_THRESHOLD": NEAR_DUPLICATE_THRESHOLD,
                "MIN_ANNOTATABLE_TOKENS": MIN_ANNOTATABLE_TOKENS,
                "CONTEXT_STRATA": list(CONTEXT_STRATA),
            },
        }


def build_plan(
    records: Sequence[InterimRecord],
    source_id: str,
    *,
    seed: int = 42,
    holdout_fraction: float = GOLD_TEMPLATE_HOLDOUT,
    target_eval: int = TARGET_GOLD_EVAL,
    target_dev: int = TARGET_GOLD_DEV,
) -> GoldSamplingPlan:
    """The whole plan, end to end and reproducible from a fresh clone."""
    partition = construct_stratified_template_partition(
        records, holdout_fraction=holdout_fraction, seed=seed
    )

    eval_pool, eval_eligibility = eligible_utterances(records, partition.gold_templates)
    dev_pool, dev_eligibility = eligible_utterances(records, partition.train_templates)

    gold_eval = draw_gold_sample(
        eval_pool, target=target_eval, name="gold_eval", seed=seed, eligibility=eval_eligibility
    )
    gold_dev = draw_gold_sample(
        dev_pool, target=target_dev, name="gold_dev", seed=seed + 1, eligibility=dev_eligibility
    )
    return GoldSamplingPlan(
        source_id=source_id,
        seed=seed,
        partition=partition,
        gold_eval=gold_eval,
        gold_dev=gold_dev,
    )


#: Where candidate lists are written. NOT `data/gold/`: that root is human-owned
#: and no agent writes there (`CLAUDE.md` §4). What lands here is a list of
#: utterance ids to be labelled, which is a processing artefact; the labels
#: themselves are produced by hand and land in `data/gold/` by the annotators'
#: own action.
CANDIDATE_DIR = Path("data/processed/gold_candidates")


def write_candidates(
    plan: GoldSamplingPlan,
    records: Sequence[InterimRecord],
    *,
    root: Path | None = None,
) -> list[Path]:
    """Write the candidate utterances as JSONL, plus the plan as JSON.

    `generation_spec` is **stripped** from every written candidate. It would
    otherwise travel to the annotator's screen and tell them which construct the
    generator planted, which is the most direct way imaginable to destroy the
    independence a kappa depends on. The parent record id is kept so a candidate
    can still be traced back to its provenance.
    """
    directory = (root or Path.cwd()) / CANDIDATE_DIR
    if "gold" in directory.resolve().parts[:-1] and directory.resolve().name != "gold_candidates":
        raise ValueError(f"refusing to write inside a gold root: {directory}")
    directory.mkdir(parents=True, exist_ok=True)

    index = {r.record_id: r for r in records}
    written: list[Path] = []
    for sample in (plan.gold_eval, plan.gold_dev):
        path = directory / f"{sample.name}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for utterance_id in sample.utterance_ids:
                record = index[utterance_id]
                payload = record.to_dict()
                payload.pop("generation_spec", None)
                payload["annotation_batch"] = sample.name
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=False) + "\n")
        written.append(path)

    plan_path = directory / "sampling_plan.json"
    plan_path.write_text(
        json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    written.append(plan_path)
    return written
