"""Assemble `(text, label-set)` pairs for the Phase 13 baselines.

This module exists to make one question impossible to answer by accident:
**which labels are we scoring against, and what does a score against them
mean?** Phase 13 has three candidate label sources, they mean three completely
different things, and only one of them is currently usable. Rather than let a
call site pick with a string argument and a shrug, each source is a named
function with its own docstring and its own refusal behaviour.

The three sources
----------------

**`planted`** -- `generation_spec.planted_constructs`, the constructs the
generator was told to plant. `docs/data_sources.md` sec.3.1 forbids using these
as evaluation ground truth for a *model quality* claim, and that prohibition
stands unweakened. What they support is a **corpus-property measurement**: how
learnable is this template grammar, and how much of that learnability is
memorisation. `scripts/run_benchmark_audit.py` established the precedent and the
framing; this module reuses both. A number produced from this source belongs in
the paper's dataset or methodology section and never in the results table.

**`silver`** -- `data/processed/silver/`. Unusable, and the reason is worse than
"machine-proposed". No live OpenRouter call has ever been made (OPEN-008), so
every one of the 9,302 silver labels came from `OfflineLLM._synthesise_silver`,
which picks a construct with `rng.randrange(...)` seeded from a SHA-256 of the
prompt. It is a pseudo-random number generator keyed on text. Measured:

* exactly **one** label per non-abstained utterance, so the data is not
  multi-label at all;
* **6 of 10** constructs appear, at ~1,030 each -- `motivation_orientation`,
  `attentional_focus`, `coping_style` and `appraisal_orientation` have zero
  support, because the stub is deliberately given only the graded construct
  names (`scripts/run_labeling.py`);
* the silver construct falls inside its parent's planted set 20.2% of the time,
  against 16.7% for a uniform pick over six.

A classifier trained on this can only memorise, because the label *is* a hash of
the text. On a template-disjoint split it scores near zero, and that is the
correct answer rather than a bug. `load_silver` therefore returns the data but
requires the caller to pass `acknowledge_no_signal=True`, so the fact cannot be
skipped by a future session that only reads the function signature.

**`gold`** -- `data/gold/`. Empty. OPEN-025: there is no second annotator, so no
human-labelled evaluation set exists. `load_gold` **refuses with a clear
message** rather than silently falling back to silver, which is the failure this
whole module is shaped to prevent. When gold arrives, the gate changes an input
path and nothing else.

Why the unit is the raw record, not the utterance
-------------------------------------------------
`generation_spec.planted_constructs` records a construct and a `template_id` per
**record**. It does not say which utterance realises which construct. So planted
labels are record-level by construction, and asking for utterance-level planted
labels would mean inventing an alignment the generator never wrote down.

That is also convenient: `src/evaluation/splits.py` operates on `RawRecord`, so
the record-level path reuses the existing template-disjoint split with no
adapter. The utterance-level path (`load_silver`, and `load_gold` when it
exists) wraps each utterance in a `RawRecord` carrying its **parent's**
`generation_spec`, purely so `templates_of` can see the templates the utterance
descends from. That wrapper is a split-time device; the labels still come from
the label file, never from the spec it is carrying.

Deduplication, and why it happens before fitting
------------------------------------------------
4,000 records cover 3,888 distinct texts. Fitting on the raw 4,000 lets a
repeated string vote once per copy, which turns a portion of the score into a
popularity contest over the generator's sampling. `deduplicate` collapses each
distinct text to one example.

Texts whose copies disagree about their label set are **dropped entirely**, not
resolved by majority vote. A text mapping to two different label sets is
unlearnable by any function of the text, so keeping one arbitrary copy would
inject noise while looking like data. On `synth_precomp_v1` at generator v1.4
the count is zero, which is worth asserting rather than assuming -- a future
corpus revision that introduces ambiguity should show up as a number in the
report, not as a quiet accuracy drop.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.records import RawRecord
from src.ingestion.store import RawStore

#: The 10 constructs of `config/taxonomy.yaml` v2. Restated as a module constant
#: for the same reason `src/labeling/schema.py` restates `MODIFIER_CONSTRUCTS`:
#: a typo should be an import error, not a silently short label list that makes
#: macro-F1 look better by averaging over fewer constructs.
CONSTRUCTS: tuple[str, ...] = (
    "appraisal_orientation",
    "attentional_focus",
    "burnout_signal",
    "cognitive_anxiety",
    "coping_style",
    "motivation_orientation",
    "perceived_stress",
    "resilience",
    "self_confidence",
    "somatic_anxiety",
)

LabelSet = frozenset[str]

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLD_ROOT = REPO_ROOT / "data" / "gold"


class NoEvaluableLabels(RuntimeError):
    """Raised when a label source is requested that does not yet exist.

    A distinct exception type rather than a bare `RuntimeError` so the gate can
    catch exactly this and exit 2 (config error) rather than 1 (gate failure).
    "The gold set does not exist yet" is not a failed experiment.
    """


@dataclass(frozen=True)
class Dataset:
    """Aligned records and labels, plus the evidence needed to read a score.

    `records` and `labels` are positionally aligned and the same length; that is
    checked on construction rather than trusted, because a silent misalignment
    produces a plausible-looking macro-F1 computed against shuffled truth.
    """

    name: str
    label_source: str
    records: tuple[RawRecord, ...]
    labels: tuple[LabelSet, ...]
    unit: str = "record"

    #: Set by `deduplicate`. Kept on the dataset rather than returned alongside
    #: it so the numbers travel with the data into the report.
    n_before_dedup: int = 0
    n_duplicate_texts_collapsed: int = 0
    n_ambiguous_texts_dropped: int = 0

    #: True when a score against these labels measures agreement with a
    #: pseudo-random generator rather than with any judgement. The report and
    #: the JSON both key their warning banner off this flag.
    has_signal: bool = True

    def __post_init__(self) -> None:
        if len(self.records) != len(self.labels):
            raise ValueError(
                f"dataset {self.name!r}: {len(self.records)} records but "
                f"{len(self.labels)} label sets; these must be positionally aligned"
            )

    def __len__(self) -> int:
        return len(self.records)

    @property
    def label_support(self) -> dict[str, int]:
        """How many examples carry each construct. Zeroes are the interesting part."""
        counts = dict.fromkeys(CONSTRUCTS, 0)
        for label_set in self.labels:
            for label in label_set:
                if label in counts:
                    counts[label] += 1
        return counts

    @property
    def constructs_without_support(self) -> tuple[str, ...]:
        """Constructs no example carries.

        Per-label F1 for these is 0 by definition and they drag macro-F1 down by
        a fixed amount regardless of the model. A macro-F1 averaged over 10
        constructs when only 6 are attested is capped at 0.6 before any
        modelling happens, which is a fact about the label source and not about
        the classifier.
        """
        return tuple(name for name, n in self.label_support.items() if n == 0)

    def summary(self) -> str:
        return (
            f"{self.name}: n={len(self)} unit={self.unit} source={self.label_source} "
            f"deduped {self.n_before_dedup}->{len(self)} "
            f"(collapsed={self.n_duplicate_texts_collapsed}, "
            f"ambiguous_dropped={self.n_ambiguous_texts_dropped}) "
            f"unattested_constructs={len(self.constructs_without_support)}"
        )


def planted_labels(record: RawRecord) -> LabelSet:
    """The constructs the generator planted in a record.

    NOT ground truth for a model-quality claim. See the module docstring and
    `docs/data_sources.md` sec.3.1.
    """
    spec = record.generation_spec or {}
    return frozenset(
        planted["construct"]
        for planted in spec.get("planted_constructs", ())
        if "construct" in planted
    )


def deduplicate(
    records: Sequence[RawRecord],
    labels: Sequence[LabelSet],
) -> tuple[tuple[RawRecord, ...], tuple[LabelSet, ...], int, int]:
    """Collapse each distinct text to one example; drop texts with conflicting labels.

    Returns `(records, labels, n_collapsed, n_ambiguous_dropped)`.

    Order is by `record_id` within each text group and the first member is kept,
    so the output is deterministic across runs and platforms. An implementation
    that iterated a `set` here would produce a different training set on a
    different machine and quietly break the reproducibility gate.
    """
    if len(records) != len(labels):
        raise ValueError(f"length mismatch: {len(records)} records vs {len(labels)} labels")

    groups: dict[str, list[tuple[RawRecord, LabelSet]]] = defaultdict(list)
    for record, label_set in zip(records, labels, strict=True):
        groups[record.text].append((record, label_set))

    kept_records: list[RawRecord] = []
    kept_labels: list[LabelSet] = []
    collapsed = 0
    ambiguous = 0

    for text in sorted(groups):
        members = sorted(groups[text], key=lambda pair: pair[0].record_id)
        distinct = {label_set for _, label_set in members}
        if len(distinct) > 1:
            # Unlearnable by any function of the text. Dropping the whole group
            # is the only choice that does not silently pick a winner.
            ambiguous += 1
            continue
        collapsed += len(members) - 1
        record, label_set = members[0]
        kept_records.append(record)
        kept_labels.append(label_set)

    return tuple(kept_records), tuple(kept_labels), collapsed, ambiguous


def load_planted(
    source_id: str = "synth_precomp_v1",
    *,
    store: RawStore | None = None,
    dedup: bool = True,
) -> Dataset:
    """Record-level dataset labelled with `generation_spec.planted_constructs`.

    **Corpus-property measurement only.** A macro-F1 from this dataset answers
    "how learnable is this template grammar", not "how well does the model
    detect psychological constructs in athlete text". The gate prints that
    sentence next to every number it produces from this source.
    """
    store = store if store is not None else RawStore()
    _, records = store.read_source(source_id)
    labels = [planted_labels(r) for r in records]

    n_before = len(records)
    if dedup:
        kept, kept_labels, collapsed, ambiguous = deduplicate(records, labels)
    else:
        kept, kept_labels, collapsed, ambiguous = tuple(records), tuple(labels), 0, 0

    return Dataset(
        name=source_id,
        label_source="planted",
        records=kept,
        labels=kept_labels,
        unit="record",
        n_before_dedup=n_before,
        n_duplicate_texts_collapsed=collapsed,
        n_ambiguous_texts_dropped=ambiguous,
        has_signal=True,
    )


def load_silver(
    source_id: str = "synth_precomp_v1",
    *,
    acknowledge_no_signal: bool = False,
    dedup: bool = True,
) -> Dataset:
    """Utterance-level dataset from `data/processed/silver/`. **Contains no signal.**

    Requires `acknowledge_no_signal=True`. The keyword is not bureaucracy: the
    labels are PRNG output keyed on the prompt text (see the module docstring),
    so a caller who has not read that cannot correctly interpret anything this
    returns, and a default-permitted call would let a future session produce a
    number that looks like a result.

    Kept callable at all because it is the ablation that demonstrates the
    problem: running the same harness over this source and showing macro-F1
    collapse to near zero on a template-disjoint split is the evidence for
    OPEN-028, and evidence is better than an assertion.
    """
    if not acknowledge_no_signal:
        raise NoEvaluableLabels(
            "data/processed/silver/ contains PRNG output, not labels. No live "
            "OpenRouter call has been made (OPEN-008), so every silver label came "
            "from OfflineLLM._synthesise_silver, which picks a construct from a "
            "hash of the prompt. It is single-label, covers 6 of 10 constructs, "
            "and agrees with the planted set at chance. Pass "
            "acknowledge_no_signal=True to load it as an ablation, or use "
            "load_planted() for the corpus-property measurement."
        )

    # Imported here rather than at module scope: the silver path is an ablation,
    # and the planted path -- which is what the gate actually runs -- should not
    # pay to import the labelling stack or fail if it is mid-refactor.
    from src.labeling.store import SilverStore

    _, silver = SilverStore().read_source(source_id)

    parent_specs: dict[str, dict] = {}
    raw_store = RawStore()
    _, raw_records = raw_store.read_source(source_id)
    for record in raw_records:
        parent_specs[record.record_id] = record.generation_spec or {}

    records: list[RawRecord] = []
    labels: list[LabelSet] = []
    for label in silver:
        # The parent's generation_spec rides along ONLY so templates_of() can
        # partition the split. The label below comes from the silver file.
        records.append(
            RawRecord(
                record_id=label.record_id,
                source_id=label.source_id,
                text=label.text,
                synthetic=True,
                generation_spec=parent_specs.get(label.parent_record_id),
            )
        )
        labels.append(frozenset(cl.construct for cl in label.labels if cl.is_present))

    n_before = len(records)
    if dedup:
        kept, kept_labels, collapsed, ambiguous = deduplicate(records, labels)
    else:
        kept, kept_labels, collapsed, ambiguous = tuple(records), tuple(labels), 0, 0

    return Dataset(
        name=source_id,
        label_source="silver",
        records=kept,
        labels=kept_labels,
        unit="utterance",
        n_before_dedup=n_before,
        n_duplicate_texts_collapsed=collapsed,
        n_ambiguous_texts_dropped=ambiguous,
        has_signal=False,
    )


def load_gold(source_id: str = "synth_precomp_v1", *, gold_root: Path | None = None) -> Dataset:
    """Human-verified labels from `data/gold/`. **Refuses while the directory is empty.**

    This function is the whole point of the module's shape. When a second
    annotator exists and `data/gold/` is populated (OPEN-025), the gate switches
    to `--gold`, this returns real labels, and every number the harness produces
    stops being provisional. Until then it raises, loudly, rather than falling
    back to silver -- which is the exact substitution that would put a
    PRNG-agreement score into the paper under the word "accuracy".
    """
    root = gold_root if gold_root is not None else GOLD_ROOT
    populated = sorted(p for p in root.glob("**/*.jsonl")) if root.exists() else []
    if not populated:
        raise NoEvaluableLabels(
            f"{root} contains no gold labels, so there is no human-verified "
            "evaluation set and no accuracy claim can be made. This is OPEN-025: "
            "gold verification needs a second annotator and does not have one. "
            "Refusing rather than falling back to silver -- silver is PRNG output "
            "(OPEN-028) and a fallback here would silently relabel a "
            "chance-agreement score as accuracy. Use --planted for the "
            "corpus-property measurement in the meantime."
        )
    raise NoEvaluableLabels(
        f"{root} contains {len(populated)} label file(s) but no reader is "
        "implemented yet. Phase 13 built the harness against an empty gold "
        "directory; wire src/annotation/store.py in here when the first gold "
        "batch lands, and re-run the gate with --gold."
    )
