"""Multi-label transformer fine-tuning -- Phase 14's system under test.

What this module is for, stated before anything else
----------------------------------------------------
`CLAUDE.md` sec.9 makes "transformer beats classical + lexicon baselines on
macro-F1" part of publication-readiness, and `PROJECT_PLAN.md` Phase 14 asks for
a fine-tuned DeBERTa/RoBERTa multi-label classifier. This module provides it.

It does **not** provide an accuracy, and the distinction is the whole reason the
module is shaped the way it is.

`data/gold/` is empty (OPEN-025: no second annotator), so there is no
human-verified evaluation set. The only labels that exist in usable form are
`generation_spec.planted_constructs` -- the constructs the generator was *told*
to plant into a template. Training and scoring against those answers exactly one
question:

    How much of this template grammar can a pretrained transformer recover,
    and how much of that recovery is memorisation rather than generalisation?

That is a **corpus property**. It belongs in the paper's dataset or methodology
section. It is not evidence that the model detects cognitive anxiety in athlete
speech, because no athlete wrote any of this text. `src/models/dataset.py`
enforces the label-source discipline; this module inherits it by construction
(it takes a `Dataset`, it never reads a label file itself) and restates it here
so that a reader who opens `transformer.py` first cannot miss it.

Why it is still worth doing now
-------------------------------
Phase 13 produced a specific, load-bearing pair of numbers on the planted
labels:

* TF-IDF + LinearSVC, **random** split: macro-F1 **1.000**
* TF-IDF + LinearSVC, **template-disjoint** split: macro-F1 **0.181**
* Lexicon floor, template-disjoint: macro-F1 **0.462**

The 1.000 -> 0.181 collapse is the evidence for OPEN-012, and it raises a
question a linear bag-of-ngrams model cannot answer: is the residual signal in
this corpus *only* surface lexical overlap, or is there paraphrase-level
structure that a pretrained contextual encoder can generalise across held-out
templates? A transformer scoring ~0.18 says the corpus offers nothing beyond
template identity. A transformer scoring well above 0.462 says the near-synonym
substitution layer produced genuinely varied realisations of each construct.

Either outcome is a publishable finding about synthetic-corpus design. Neither
is a model-quality claim. Phase 14 is therefore run as **measurement**, and the
gate result is recorded together with its reinterpretation.

The one number that would be actively misleading
------------------------------------------------
Macro-F1 on the **random** split. It will be high -- the linear model already
hits 1.000 there -- and it means the encoder memorised 149 templates that appear
on both sides of the split. It is computed and reported anyway, because the *gap*
between the two splits is the finding, and a gap needs both endpoints. It is
never reported alone, and `SplitScore.is_leaky` exists so a downstream consumer
must actively ignore the flag to misuse it.

Design decisions a reviewer would ask about
-------------------------------------------

**Threshold tuning happens on a validation slice carved out of train, never on
test.** A multi-label sigmoid head needs a decision threshold per construct, and
macro-F1 is highly sensitive to it -- moving a rare construct's threshold from
0.5 to 0.3 can shift macro-F1 by several points. Tuning those thresholds on the
test set would be a textbook optimistic bias, and it is an easy one to commit by
accident because the tuning code and the scoring code want the same array. So
the split is three-way: `fit()` carves `val_fraction` off the *training* records
(template-disjointly, when the caller supplies the parent split's template sets),
tunes thresholds and picks the best epoch there, and only then is `predict()`
allowed to see test text.

**Early stopping is on validation macro-F1, not validation loss.** BCE loss and
macro-F1 disagree on an imbalanced multi-label problem: loss is dominated by the
frequent constructs, and the checkpoint with the lowest loss is often not the
one with the best macro-F1. The primary metric in `config/settings.yaml` is
macro-F1, so that is what the model selection optimises.

**Class imbalance is handled by `pos_weight`, not by resampling.** Construct
support ranges from 446 (`motivation_orientation`) to 885 (`cognitive_anxiety`)
in `synth_precomp_v1`. Resampling a multi-label corpus is ill-defined -- an
example carries several labels at once, so oversampling for a rare construct
also oversamples whatever frequent construct rides along with it. A per-construct
`pos_weight` in `BCEWithLogitsLoss` reweights the loss without touching the data
distribution.

**Constructs with zero positive examples get a constant-zero head, and stay in
the macro denominator.** Same reasoning as `_ConstantZero` in `classical.py`:
dropping unattested constructs would raise macro-F1 by shrinking the denominator
from 10 to however many are attested, which is a real way papers overstate
results and it would happen silently. The planted source attests all 10, but the
silver ablation attests 6, and the two must be scored under identical rules or
the comparison is meaningless.

**Reproducibility is a stored fact.** Every fitted model persists a manifest
carrying the seed, the torch/transformers versions, the base checkpoint, the full
hyperparameter set, the tuned thresholds, and a SHA-256 fingerprint of the exact
training pairs -- reusing `classical.training_fingerprint` so a transformer run
and a baseline run over the same data produce the *same* fingerprint and can be
proven to have trained on the same thing.

Dependencies, and why they are imported lazily
----------------------------------------------
torch and transformers live in `requirements-ml.txt`, not `requirements-base.txt`.
`src/evaluation/` and the classical baselines must keep importing in the light
Docker image, and `src/models/__init__.py` imports this package. So torch is
imported inside the functions that need it, and a missing install raises
`MLDependencyMissing` with the exact command to fix it rather than a bare
`ModuleNotFoundError` three frames deep.

Network, and the offline guard
------------------------------
Fine-tuning needs pretrained weights, and pretrained weights come from the
Hugging Face hub. Everything else in this repository runs offline and free; this
step does not, and pretending otherwise would produce a confusing failure in a
sandbox or CI runner with no hub access. `resolve_base_model` therefore checks
for a usable local copy first and, on failure, raises `WeightsUnavailable` naming
the three ways out (pre-download, point at a local directory, or run on a host
with hub access). It never silently falls back to random initialisation --
a randomly-initialised "DeBERTa" that trains without complaint and scores 0.15 is
the single most expensive failure mode available here, because it looks exactly
like the honest finding that the corpus has no generalisable signal.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.evaluation.baselines import Baseline
from src.evaluation.metrics import macro_f1
from src.ingestion.records import RawRecord
from src.models.classical import training_fingerprint
from src.models.dataset import CONSTRUCTS, LabelSet

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "models"

#: Phase 14's primary checkpoint (`config/settings.yaml` -> model.base) and its
#: lighter fallback. DeBERTa-v3's disentangled attention is the stronger encoder;
#: roberta-base is the escape hatch for a CPU-only or memory-limited host, and
#: also for the case where DeBERTa-v3's sentencepiece tokenizer conversion is
#: awkward on a given transformers version.
DEFAULT_BASE_MODEL = "microsoft/deberta-v3-base"
FALLBACK_BASE_MODEL = "roberta-base"

#: Compute-constrained option, selected by the owner on 2026-08-11 after the
#: first real run measured ~19 minutes per epoch per split on CPU (which puts the
#: full 6-config sweep at ~18 hours). DistilRoBERTa is 6 layers against
#: RoBERTa's 12 and roughly halves that.
#:
#: The honest framing for the paper: this is a **compute-constrained study**, and
#: the encoder choice should be reported as such rather than presented as the
#: strongest available model. Since every number this project produces is a
#: corpus property rather than an accuracy (OPEN-025), spending 18 hours to
#: improve agreement with a template generator buys very little -- the trade is
#: defensible. It should stop being defensible the moment a real gold set exists.
FAST_BASE_MODEL = "distilroberta-base"


class MLDependencyMissing(RuntimeError):
    """torch / transformers are not installed.

    Distinct from a gate failure. A missing dependency is a configuration
    problem and the runner exits 2 for it, the same as it does for a missing
    gold set -- neither is a failed experiment.
    """


class WeightsUnavailable(RuntimeError):
    """Pretrained weights could not be obtained, and randomly-initialised weights
    are not an acceptable substitute.

    See the module docstring: a random-init run produces a plausible-looking low
    score that is indistinguishable, in the report, from the honest finding that
    the corpus lacks generalisable signal. Refusing is the only safe behaviour.
    """


# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HParams:
    """One point in the Phase 14 sweep space.

    Frozen and hashable so a sweep can key results by configuration and so a
    configuration cannot be mutated between "what we ran" and "what we logged" --
    the two must be the same object.

    Defaults are chosen for a CPU-feasible run over ~3,000 short records rather
    than for maximum score: `max_length=256` matches `config/settings.yaml`, and
    4 epochs over 2,591 training records is minutes on GPU and tolerable on CPU.
    """

    base_model: str = DEFAULT_BASE_MODEL
    learning_rate: float = 2e-5
    batch_size: int = 16
    epochs: int = 4
    #: 128, not the 256 in `config/settings.yaml`, and the change is measured
    #: rather than guessed. The longest record in `synth_precomp_v1` is ~125
    #: subword tokens and the median is ~50 (4,000 records, whitespace mean 37.8,
    #: p99 78). At 256 every batch was padded to roughly 5x the median real
    #: length, and on CPU that cost is paid in full on every forward and backward
    #: pass. 128 truncates nothing and halves the padded width; the dynamic
    #: trimming in `fit` then removes most of what remains.
    max_length: int = 128
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    #: Fraction of the *training* records held out for threshold tuning and
    #: epoch selection. Never drawn from test. See the module docstring.
    #:
    #: 0.25, raised from 0.15 after the first real run (2026-08-11). The carve is
    #: template-disjoint, so it discards straddling records as well as holding
    #: some out -- at 0.15 the realised slice was **207 records**, not the ~390
    #: the fraction implies. Per-construct thresholds were then tuned on as few
    #: as 10-25 positives, and the symptom was unmistakable in the results:
    #: `attentional_focus` P=0.141 R=1.000, `somatic_anxiety` P=0.329 R=0.929.
    #: Thresholds had been pushed down to catch every positive in a slice too
    #: small to show the cost. 0.25 buys a realised slice of roughly 350-400.
    val_fraction: float = 0.25
    #: Cap on the per-construct positive weight in the BCE loss. Uncapped
    #: `n_neg/n_pos` on a very rare construct produces a weight large enough to
    #: make the model predict it constantly, which raises that construct's recall
    #: to 1.0, craters its precision, and can *lower* macro-F1 while looking like
    #: imbalance handling.
    max_pos_weight: float = 10.0
    seed: int = 42

    def slug(self) -> str:
        """Short filesystem-safe identifier, stable across runs.

        Used for checkpoint directories and run-log filenames. Includes a hash
        of the full configuration, not just the fields in the readable prefix,
        so two configurations differing only in `weight_decay` cannot collide
        and silently overwrite each other's checkpoint.
        """
        readable = (
            f"{self.base_model.split('/')[-1]}"
            f"_lr{self.learning_rate:g}"
            f"_bs{self.batch_size}"
            f"_ep{self.epochs}"
            f"_len{self.max_length}"
        )
        digest = hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()
        return f"{readable}_{digest[:8]}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "base_model": self.base_model,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "max_length": self.max_length,
            "weight_decay": self.weight_decay,
            "warmup_ratio": self.warmup_ratio,
            "val_fraction": self.val_fraction,
            "max_pos_weight": self.max_pos_weight,
            "seed": self.seed,
        }


#: The Phase 14 sweep. Deliberately small: 6 configurations, not 60.
#:
#: A grid this size is defensible in a paper ("we swept learning rate over
#: {1e-5, 2e-5, 3e-5, 5e-5}, batch size over {8, 16}, and epochs over {4, 6}")
#: and finishes on a laptop.
#: A larger grid over a corpus whose labels are planted would be spending
#: compute to optimise a number the paper is not allowed to call accuracy --
#: and every configuration tried is another chance to pick the one that
#: happened to score well on this particular test split.
DEFAULT_SWEEP: tuple[HParams, ...] = (
    HParams(learning_rate=1e-5, batch_size=16),
    HParams(learning_rate=2e-5, batch_size=16),
    HParams(learning_rate=3e-5, batch_size=16),
    HParams(learning_rate=5e-5, batch_size=16),
    HParams(learning_rate=2e-5, batch_size=8),
    HParams(learning_rate=2e-5, batch_size=16, epochs=6),
)


# ---------------------------------------------------------------------------
# Dependency and weight resolution
# ---------------------------------------------------------------------------


def require_ml_stack() -> tuple[Any, Any]:
    """Import torch and transformers, or explain precisely how to install them.

    Returns the two modules so callers do not repeat the import. Kept as a
    function rather than a module-level import so `src.models` stays importable
    in the light image -- see the module docstring.
    """
    try:
        import torch
        import transformers
    except ModuleNotFoundError as exc:  # pragma: no cover - environment-dependent
        raise MLDependencyMissing(
            f"{exc.name} is not installed, so Phase 14 cannot run.\n\n"
            "  pip install -r requirements-ml.txt \\\n"
            "      --extra-index-url https://download.pytorch.org/whl/cpu\n\n"
            "The CPU wheel index matters: the default PyPI torch wheel for Linux "
            "is the CUDA build and pulls several GB of nvidia-* runtime libraries "
            "this project never uses. See the note at the top of "
            "requirements-ml.txt. The classical baselines "
            "(scripts/run_baselines.py) do not need this stack and still run."
        ) from exc
    return torch, transformers


def resolve_base_model(name: str, *, local_only: bool | None = None) -> str:
    """Confirm pretrained weights are reachable, and return the identifier to load.

    `name` may be a hub identifier (`microsoft/deberta-v3-base`) or a path to a
    directory already containing a checkpoint. A local directory is checked for
    a `config.json` and returned as-is; a hub identifier is probed by loading the
    config, which hits the local HF cache first and the network only if the
    cache misses.

    Scope note: this function checks that **weights** are obtainable. It does not
    check that a tokenizer can be built from them -- `AutoConfig` loads happily
    for `microsoft/deberta-v3-base` on a machine with no `sentencepiece`, which
    is how the first real Phase 14 run got past resolution and then failed
    (OPEN-029). That case is owned by `load_tokenizer`, which `fit()` calls
    before the weights are downloaded, so the failure still arrives early and
    with a named cause. Deliberately not duplicated here: two mechanisms
    diagnosing one condition drift apart, and the message that survives is
    whichever fires first.

    `local_only` defaults to the value of the `HF_HUB_OFFLINE` environment
    variable, so an offline CI runner behaves predictably without a flag.

    Raises `WeightsUnavailable` rather than falling back to random
    initialisation. See the module docstring for why that fallback would be the
    most expensive bug available here.
    """
    _, transformers = require_ml_stack()

    candidate = Path(name)
    if candidate.exists():
        if (candidate / "config.json").is_file():
            return str(candidate)
        raise WeightsUnavailable(
            f"{candidate} exists but contains no config.json, so it is not a "
            "usable checkpoint directory."
        )

    if local_only is None:
        local_only = os.environ.get("HF_HUB_OFFLINE", "").strip() not in ("", "0", "false")

    try:
        transformers.AutoConfig.from_pretrained(name, local_files_only=local_only)
    except Exception as exc:
        raise WeightsUnavailable(
            f"Could not obtain pretrained weights for {name!r}"
            f"{' (offline mode)' if local_only else ''}: {exc}\n\n"
            "Phase 14 fine-tunes a *pretrained* encoder. Randomly-initialised "
            "weights are refused rather than substituted, because a random-init "
            "run trains without error and produces a low score that is "
            "indistinguishable in the report from the honest finding that the "
            "corpus has no generalisable signal.\n\n"
            "Three ways forward:\n"
            "  1. On a host with hub access, pre-download once:\n"
            f'       python -c "from transformers import AutoModel, AutoTokenizer; \\\n'
            f"                   AutoModel.from_pretrained('{name}'); \\\n"
            f"                   AutoTokenizer.from_pretrained('{name}')\"\n"
            "     then re-run here with HF_HOME pointing at that cache.\n"
            "  2. Pass --base-model /path/to/local/checkpoint (a directory "
            "containing config.json).\n"
            f"  3. Try the lighter fallback: --base-model {FALLBACK_BASE_MODEL}."
        ) from exc
    return name


def load_tokenizer(resolved_base: str) -> Any:
    """Load the tokenizer, translating one specific unhelpful failure.

    DeBERTa-v3 ships its vocabulary as a SentencePiece model (`spm.model`), and
    transformers 5.x needs the `sentencepiece` package to convert it into a fast
    tokenizer. When that package is absent, transformers does **not** raise a
    clean missing-dependency error: it catches the `ImportError`, falls back to a
    TikToken extractor, and that extractor tries to parse the SentencePiece
    protobuf as a text BPE file. What surfaces is

        ValueError: Error parsing line b'\\x0e' in ...\\spm.model

    from inside `tiktoken/load.py`, roughly forty frames away from the actual
    cause, with the real `ImportError` buried as a `__cause__` several exceptions
    up. Encountered on the first real Phase 14 run, 2026-08-11 (OPEN-029), and
    predicted in that entry as the most likely first-run failure.

    `sentencepiece` is now pinned in `requirements-ml.txt`, so this should not
    recur on a correctly-provisioned environment. The translation stays because
    a pinned dependency and an installed one are different things -- an existing
    venv predating the pin will still hit it -- and because the raw error is
    close to un-Googleable.

    Deliberately narrow: the error is re-raised untouched unless the message
    carries both signatures. A broad `except Exception` here would attach a
    confident, wrong explanation to unrelated tokenizer failures, which is worse
    than no explanation at all.
    """
    _, transformers = require_ml_stack()
    try:
        return transformers.AutoTokenizer.from_pretrained(resolved_base)
    except Exception as exc:
        blob = f"{exc}".lower()
        chain: list[str] = []
        cursor: BaseException | None = exc
        while cursor is not None:
            chain.append(f"{cursor}".lower())
            cursor = cursor.__cause__ or cursor.__context__
        joined = " ".join(chain)
        looks_like_sentencepiece = "spm.model" in blob or "sentencepiece" in joined
        if not looks_like_sentencepiece:
            raise
        raise MLDependencyMissing(
            f"Could not build a tokenizer for {resolved_base!r}: the "
            "`sentencepiece` package is missing.\n\n"
            "  pip install sentencepiece\n\n"
            "DeBERTa-v3 stores its vocabulary as a SentencePiece model. Without "
            "this package, transformers 5.x falls back to a TikToken extractor "
            "that tries to read the SentencePiece protobuf as text, which fails "
            "with an unrelated-looking parse error deep inside tiktoken -- the "
            "traceback you would otherwise be reading.\n\n"
            "Alternative, if sentencepiece will not install on this machine:\n"
            f"  python scripts/run_transformer.py --base-model {FALLBACK_BASE_MODEL}\n"
            "roberta-base uses byte-level BPE and needs no SentencePiece. It is "
            "a slightly weaker encoder; record the substitution in the model "
            "card rather than leaving it implicit, since it changes what was run."
        ) from exc


def set_all_seeds(seed: int) -> None:
    """Seed Python, numpy and torch, and ask cuDNN for determinism.

    Called at the top of every `fit`. Bit-exact reproducibility across different
    hardware is not achievable for floating-point training and this does not
    claim it; what it buys is that two runs on the *same* machine with the same
    seed produce the same numbers, which is what the reproducibility gate
    actually checks.
    """
    torch, _ = require_ml_stack()
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ModuleNotFoundError:  # pragma: no cover
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():  # pragma: no cover - no GPU in CI
        torch.cuda.manual_seed_all(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


# ---------------------------------------------------------------------------
# Label encoding and threshold tuning (pure Python -- unit-testable without torch)
# ---------------------------------------------------------------------------


def _trim_batch(input_ids: Any, attention_mask: Any) -> tuple[Any, Any]:
    """Cut a padded batch down to its own longest real sequence.

    The dataset is padded once, to the longest record in the whole set. Within a
    batch of 16 drawn from a corpus whose median record is ~50 tokens and whose
    longest is ~125, most batches contain nothing near 125 -- so most of the
    attention computation is over padding that the mask will discard anyway.
    Trimming to `attention_mask.sum(1).max()` removes that work.

    This changes no result. Padding positions are masked out of attention and
    contribute nothing to the logits, so a trimmed batch and an untrimmed one
    produce the same output up to floating-point associativity. It is purely a
    cost reduction, and on CPU it is a large one.

    Guarded against an all-padding batch (`max() == 0`), which cannot occur with
    real text but would produce a zero-width tensor and a confusing error if it
    ever did.
    """
    longest = int(attention_mask.sum(dim=1).max())
    if longest <= 0:
        return input_ids, attention_mask
    return input_ids[:, :longest], attention_mask[:, :longest]


def encode_labels(labels: Sequence[LabelSet], constructs: Sequence[str]) -> list[list[float]]:
    """Label sets -> a multi-hot matrix, in the fixed `constructs` order.

    The order is the caller's `constructs` tuple and never a `set` iteration,
    because a column permutation between fit and predict would produce a model
    that confidently predicts the wrong construct while every shape check passes.
    """
    index = {name: i for i, name in enumerate(constructs)}
    matrix: list[list[float]] = []
    for label_set in labels:
        row = [0.0] * len(constructs)
        for label in label_set:
            position = index.get(label)
            if position is not None:
                row[position] = 1.0
        matrix.append(row)
    return matrix


def decode_predictions(
    probabilities: Sequence[Sequence[float]],
    thresholds: Sequence[float],
    constructs: Sequence[str],
) -> list[LabelSet]:
    """Sigmoid outputs + per-construct thresholds -> label sets.

    No "at least one label" rule. A record with no construct planted is a real
    and common case in this corpus (pure logistics talk), so the empty set is a
    legitimate prediction and forcing an argmax would manufacture false
    positives on exactly those records.
    """
    out: list[LabelSet] = []
    for row in probabilities:
        out.append(
            frozenset(
                name
                for name, prob, threshold in zip(constructs, row, thresholds, strict=True)
                if prob >= threshold
            )
        )
    return out


def positive_weights(
    encoded: Sequence[Sequence[float]],
    *,
    cap: float = 10.0,
) -> list[float]:
    """Per-construct `n_negative / n_positive`, clipped to `cap`.

    A construct with zero positives gets weight 1.0 -- the weight is irrelevant
    there because the column contributes no positive term to the loss, and
    dividing by zero to express that would be worse.
    """
    if not encoded:
        return []
    n_rows = len(encoded)
    weights: list[float] = []
    for column in range(len(encoded[0])):
        positives = sum(row[column] for row in encoded)
        if positives <= 0:
            weights.append(1.0)
            continue
        weights.append(min(cap, (n_rows - positives) / positives))
    return weights


def tune_thresholds(
    probabilities: Sequence[Sequence[float]],
    truth: Sequence[Sequence[float]],
    constructs: Sequence[str],
    *,
    grid: Sequence[float] = tuple(i / 100 for i in range(5, 100, 5)),
) -> list[float]:
    """Pick, per construct independently, the threshold maximising that
    construct's F1 on the validation slice.

    Per-construct rather than one global threshold: construct prevalence varies
    roughly 2x across the taxonomy, and a single threshold systematically
    under-predicts the rare ones, which macro-F1 punishes hardest.

    Independent per construct is an approximation -- macro-F1 is a sum of
    per-construct F1s, so maximising each term separately does maximise the sum,
    but only because the terms are genuinely independent given the probability
    matrix. That holds here; it would not if a constraint coupled the labels.

    Ties resolve to the threshold closest to 0.5. An arbitrary tie-break would
    make the tuned thresholds depend on grid iteration order, and thresholds are
    persisted in the manifest as a reproducibility claim.

    **This is fit on validation data and applied to test data.** A construct with
    no positives in the validation slice keeps 0.5, because there is no F1 to
    maximise and a tuned threshold would be fitting noise -- with a 15% val slice
    off ~2,600 records that is ~390 examples, which is thin for the rarest
    constructs and is a known limitation worth stating in the model card.
    """
    if not probabilities:
        return [0.5] * len(constructs)

    thresholds: list[float] = []
    for column in range(len(constructs)):
        gold = [row[column] for row in truth]
        if sum(gold) == 0:
            thresholds.append(0.5)
            continue
        scores = [row[column] for row in probabilities]
        best_threshold, best_f1 = 0.5, -1.0
        for threshold in grid:
            tp = fp = fn = 0
            for probability, actual in zip(scores, gold, strict=True):
                predicted = probability >= threshold
                if predicted and actual:
                    tp += 1
                elif predicted:
                    fp += 1
                elif actual:
                    fn += 1
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
            if f1 > best_f1 or (f1 == best_f1 and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
                best_threshold, best_f1 = threshold, f1
        thresholds.append(best_threshold)
    return thresholds


def carve_validation(
    records: Sequence[RawRecord],
    labels: Sequence[LabelSet],
    *,
    fraction: float,
    seed: int,
) -> tuple[list[int], list[int]]:
    """Index split of the training set into (train, validation).

    **Delegates to `src/evaluation/splits.py:template_disjoint_split`** rather
    than partitioning templates again here, and the delegation is the point. A
    record in this corpus typically uses *several* templates. The obvious
    implementation -- group records by their first template, ship whole groups
    to one side -- looks template-aware and is not: a record sent to validation
    on the strength of its first template drags its remaining templates along,
    and those templates are still in training. `tests/test_transformer.py`
    caught exactly that, with roughly half the template bank straddling the line.

    Getting this right means the same three-way logic `template_disjoint_split`
    already implements and already has tests for: a record goes to validation
    only if *every* template it uses is a validation template, to training only
    if every template is a training template, and straddlers are discarded.
    Two implementations of that rule is one implementation too many.

    Consequence worth naming: **straddling records are dropped from training**,
    not reassigned. On `synth_precomp_v1` the outer split already discards ~22%
    on the same principle, and paying it twice costs real training data. The
    alternative -- keeping straddlers in training -- would put validation
    templates in front of the model and calibrate the thresholds on phrasings it
    had memorised, which is the bias this whole function exists to prevent. The
    dropped count is recoverable from `n_train + n_val` against the input size
    and is recorded in the manifest.

    Records carrying no template (pure logistics talk) cannot leak and are split
    randomly by the underlying function.
    """
    n = len(records)
    if n == 0 or fraction <= 0:
        return list(range(n)), []

    from src.evaluation.splits import template_disjoint_split

    split = template_disjoint_split(records, test_size=fraction, seed=seed)
    position = {record.record_id: i for i, record in enumerate(records)}
    train_idx = sorted(position[r.record_id] for r in split.train)
    val_idx = sorted(position[r.record_id] for r in split.test)

    if not val_idx:
        # Degenerate corpus (too few templates to hold any out). Fall back to a
        # plain random slice so threshold tuning and epoch selection still have
        # something to run on, and accept that it may share templates -- an
        # honest small-sample compromise, not a silent one: `_n_val` in the
        # manifest lets a reader see how thin the slice was.
        rng = random.Random(seed)
        order = list(range(n))
        rng.shuffle(order)
        cut = max(1, int(n * (1.0 - fraction)))
        return sorted(order[:cut]), sorted(order[cut:])

    return train_idx, val_idx


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


@dataclass
class TransformerBaseline(Baseline):
    """Fine-tuned multi-label transformer, behind the Phase 13 `Baseline` interface.

    Deliberately the *same* interface as `TfidfLinearBaseline` -- `fit(records,
    labels)` / `predict(records) -> list[LabelSet]`. That is not incidental
    tidiness: it means the Phase 14 gate scores the transformer through the
    identical harness, splits, metrics and bootstrap that produced the Phase 13
    numbers, so a difference between the two rows of the results table is a
    difference in the model and not a difference in the evaluation code.
    """

    hparams: HParams = field(default_factory=HParams)
    name: str = "transformer"
    constructs: tuple[str, ...] = CONSTRUCTS
    #: Print per-epoch step counts, running loss and an ETA during `fit`.
    #: Default on. A CPU fine-tune of this corpus is tens of minutes per
    #: configuration, and the first real run printed nothing for the whole of it
    #: -- which is indistinguishable, from the outside, from a hang. Silence is
    #: not a neutral default when the alternative is the owner killing a healthy
    #: run because they cannot tell it is alive.
    progress: bool = True

    _model: Any = None
    _tokenizer: Any = None
    _device: str = "cpu"
    _thresholds: list[float] = field(default_factory=list)
    _degenerate: tuple[str, ...] = ()
    _fingerprint: str = ""
    _n_train: int = 0
    _n_val: int = 0
    _resolved_base: str = ""
    #: Per-epoch validation macro-F1. Persisted so the training curve can be
    #: inspected without re-running, and so "did it converge or did we stop it
    #: mid-climb" is answerable from the artifact.
    _val_curve: list[float] = field(default_factory=list)
    _best_epoch: int = 0

    # -- training -----------------------------------------------------------

    def fit(
        self,
        records: Sequence[RawRecord],
        labels: Sequence[LabelSet],
    ) -> TransformerBaseline:
        """Fine-tune on `(records, labels)`, selecting the epoch and thresholds
        on a validation slice carved from these same records.

        Test data is not visible here and must not be passed in. The runner
        enforces that by construction -- it hands `split.train` to this method
        and `split.test` to `predict` -- but the invariant is worth naming since
        violating it is invisible in the output.
        """
        torch, transformers = require_ml_stack()
        from torch.utils.data import DataLoader, TensorDataset

        set_all_seeds(self.hparams.seed)
        self._resolved_base = resolve_base_model(self.hparams.base_model)

        encoded = encode_labels(labels, self.constructs)
        self._degenerate = tuple(
            name for i, name in enumerate(self.constructs) if sum(row[i] for row in encoded) == 0
        )

        train_idx, val_idx = carve_validation(
            records,
            labels,
            fraction=self.hparams.val_fraction,
            seed=self.hparams.seed,
        )
        self._n_train, self._n_val = len(train_idx), len(val_idx)

        self._tokenizer = load_tokenizer(self._resolved_base)
        self._model = transformers.AutoModelForSequenceClassification.from_pretrained(
            self._resolved_base,
            num_labels=len(self.constructs),
            problem_type="multi_label_classification",
            # Without this, transformers fetched *both* pytorch_model.bin and
            # model.safetensors on the first real run -- 742 MB of download for a
            # 371 MB model. safetensors is also the safer format: loading a .bin
            # unpickles arbitrary Python objects.
            use_safetensors=True,
            # Always build a fresh 10-construct head, even when the checkpoint
            # already carries a classification head of a different width.
            #
            # `roberta-base` and `distilroberta-base` ship no head at all, so
            # this is a no-op for them -- which is why the real Phase 14 sweep
            # never hit it. Point `--base-model` at any already-fine-tuned
            # classifier (a sentiment model, or the tiny checkpoint the
            # integration test uses) and the head is sized for *its* labels, not
            # for ten sports-psychology constructs, and the load fails with
            # "You set `ignore_mismatched_sizes` to `False`".
            #
            # Reinitialising is unconditionally correct here: no pretrained head
            # could be meaningful over this label space. The encoder is what is
            # being transferred; the head is always new. transformers prints
            # exactly which tensors it reinitialised, so this hides nothing --
            # the MISSING/UNEXPECTED report in the run log is the audit trail.
            ignore_mismatched_sizes=True,
        )
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device)

        def batch_of(indices: Sequence[int]) -> Any:
            texts = [records[i].text for i in indices]
            targets = [encoded[i] for i in indices]
            tokens = self._tokenizer(
                texts,
                truncation=True,
                # Pad to the longest sequence in this set rather than to
                # `max_length`. Combined with `_trim_batch` in the training loop,
                # which cuts each batch to its own longest member, this is
                # dynamic padding: a batch of short records costs what short
                # records cost. `padding="max_length"` made every batch pay for
                # the full width when the median record is ~50 tokens -- pure
                # waste, paid on every step of every epoch of every
                # configuration, and on CPU that is the difference between an
                # afternoon and a day.
                padding=True,
                max_length=self.hparams.max_length,
                return_tensors="pt",
            )
            return TensorDataset(
                tokens["input_ids"],
                tokens["attention_mask"],
                torch.tensor(targets, dtype=torch.float),
            )

        train_loader = DataLoader(
            batch_of(train_idx),
            batch_size=self.hparams.batch_size,
            shuffle=True,
            generator=torch.Generator().manual_seed(self.hparams.seed),
        )

        pos_weight = torch.tensor(
            positive_weights([encoded[i] for i in train_idx], cap=self.hparams.max_pos_weight),
            dtype=torch.float,
            device=self._device,
        )
        loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        optimiser = torch.optim.AdamW(
            self._model.parameters(),
            lr=self.hparams.learning_rate,
            weight_decay=self.hparams.weight_decay,
        )
        total_steps = max(1, len(train_loader) * self.hparams.epochs)
        scheduler = transformers.get_linear_schedule_with_warmup(
            optimiser,
            num_warmup_steps=int(total_steps * self.hparams.warmup_ratio),
            num_training_steps=total_steps,
        )

        val_records = [records[i] for i in val_idx]
        val_truth = [encoded[i] for i in val_idx]
        val_label_sets = [labels[i] for i in val_idx]

        best_score = -1.0
        best_state: dict[str, Any] | None = None
        best_thresholds = [0.5] * len(self.constructs)
        self._val_curve = []

        n_steps = len(train_loader)
        for epoch in range(self.hparams.epochs):
            self._model.train()
            epoch_started = time.time()
            running_loss = 0.0
            for step_index, (input_ids, attention_mask, targets) in enumerate(train_loader, 1):
                input_ids, attention_mask = _trim_batch(input_ids, attention_mask)
                optimiser.zero_grad()
                logits = self._model(
                    input_ids=input_ids.to(self._device),
                    attention_mask=attention_mask.to(self._device),
                ).logits
                loss = loss_fn(logits, targets.to(self._device))
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._model.parameters(), 1.0)
                optimiser.step()
                scheduler.step()

                # `.detach()` before the scalar conversion. `float(tensor)` on a
                # tensor that still requires grad warns, and the warning is
                # earned: the naive version keeps a reference to the autograd
                # graph alive inside a running total, which is a slow leak across
                # thousands of steps.
                running_loss += loss.detach().item()
                if self.progress and (step_index % 25 == 0 or step_index == n_steps):
                    done = time.time() - epoch_started
                    eta = done / step_index * (n_steps - step_index)
                    print(
                        f"      epoch {epoch + 1}/{self.hparams.epochs}  "
                        f"step {step_index}/{n_steps}  "
                        f"loss {running_loss / step_index:.4f}  "
                        f"{done:.0f}s elapsed, ~{eta:.0f}s left",
                        flush=True,
                    )

            if not val_idx:
                # No validation slice (a degenerate tiny-corpus case). Keep the
                # last epoch and default thresholds, and record the absence
                # rather than fabricating a curve.
                self._val_curve.append(float("nan"))
                continue

            probabilities = self._probabilities(val_records)
            thresholds = tune_thresholds(probabilities, val_truth, self.constructs)
            predictions = decode_predictions(probabilities, thresholds, self.constructs)
            score = macro_f1(val_label_sets, predictions, self.constructs)
            self._val_curve.append(score)

            if score > best_score:
                best_score = score
                best_thresholds = thresholds
                self._best_epoch = epoch + 1
                # Detached CPU copy: keeping GPU tensors alive across epochs is
                # how a sweep runs out of memory on the fourth configuration.
                best_state = {
                    k: v.detach().cpu().clone() for k, v in self._model.state_dict().items()
                }

        if best_state is not None:
            self._model.load_state_dict(best_state)
            self._model.to(self._device)
        self._thresholds = best_thresholds
        self._fingerprint = training_fingerprint(records, labels)
        return self

    # -- inference ----------------------------------------------------------

    def _probabilities(self, records: Sequence[RawRecord]) -> list[list[float]]:
        """Sigmoid probabilities per construct. Batched, no gradients, eval mode."""
        torch, _ = require_ml_stack()
        if self._model is None:
            raise RuntimeError(f"{self.name}: fit() before predict()")

        self._model.eval()
        out: list[list[float]] = []
        batch = max(8, self.hparams.batch_size)
        with torch.no_grad():
            for start in range(0, len(records), batch):
                texts = [r.text for r in records[start : start + batch]]
                # `padding=True` pads only to the longest text in this batch, so
                # inference gets the same dynamic-padding saving as training.
                # Validation runs once per epoch, so this is not a rounding error.
                tokens = self._tokenizer(
                    texts,
                    truncation=True,
                    padding=True,
                    max_length=self.hparams.max_length,
                    return_tensors="pt",
                ).to(self._device)
                logits = self._model(**tokens).logits
                out.extend(torch.sigmoid(logits).cpu().tolist())
        return out

    def predict(self, records: Sequence[RawRecord]) -> list[LabelSet]:
        thresholds = self._thresholds or [0.5] * len(self.constructs)
        predictions = decode_predictions(self._probabilities(records), thresholds, self.constructs)
        if not self._degenerate:
            return predictions
        # A construct with no positive training examples cannot have been
        # learned. Suppressing it keeps the macro denominator at 10 while
        # ensuring its F1 is 0 for the honest reason (never predicted) rather
        # than an accidental one (predicted at random by an untrained head).
        degenerate = set(self._degenerate)
        return [frozenset(p - degenerate) for p in predictions]

    def predict_proba(self, records: Sequence[RawRecord]) -> list[list[float]]:
        """Raw per-construct probabilities.

        Phase 16 (risk fusion) and Phase 17 (calibration / ECE) both need these
        rather than thresholded label sets, and exposing them here avoids a
        later refactor that would change the fitted-model interface after the
        numbers were reported against it.
        """
        return self._probabilities(records)

    # -- persistence --------------------------------------------------------

    def manifest(self) -> dict[str, Any]:
        """Everything needed to reproduce or audit this fitted model.

        `training_fingerprint` is the shared one from `classical.py`, so a
        transformer run and a baseline run over the same data produce the same
        fingerprint and can be *proven* to have trained on the same pairs rather
        than assumed to have.
        """
        torch, transformers = require_ml_stack()
        return {
            "name": self.name,
            "base_model": self.hparams.base_model,
            "resolved_base_model": self._resolved_base,
            "hparams": self.hparams.as_dict(),
            "constructs": list(self.constructs),
            "thresholds": {
                name: threshold
                for name, threshold in zip(self.constructs, self._thresholds, strict=False)
            },
            "degenerate_constructs": list(self._degenerate),
            "n_train": self._n_train,
            "n_val": self._n_val,
            "best_epoch": self._best_epoch,
            "val_macro_f1_curve": self._val_curve,
            "training_fingerprint": self._fingerprint,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "device": self._device,
            "seed": self.hparams.seed,
            "label_semantics": (
                "Trained against generation_spec.planted_constructs on a "
                "synthetic corpus. Scores are a corpus property, NOT accuracy. "
                "data/gold/ is empty (OPEN-025)."
            ),
        }

    @classmethod
    def load(cls, directory: Path | str) -> TransformerBaseline:
        """Reload a fitted model from `save()`, thresholds and all.

        **Phase 17 depends on this.** Explainability (SHAP, attention rollout)
        and the Phase 19 dashboard both need the trained classifier back, and
        without a loader the only way to get it is to retrain -- five hours on
        CPU to reproduce a model that is already sitting on disk.

        Restores the tuned per-construct thresholds from the manifest rather
        than defaulting to 0.5. A model reloaded with default thresholds is a
        *different classifier* from the one that was evaluated, and it would
        silently produce explanations for predictions the reported numbers never
        described.

        Verifies the construct order matches the manifest. Label columns are
        positional, so a taxonomy edit between save and load would map every
        probability to the wrong construct while every shape check passed --
        precisely the failure `encode_labels` is written to prevent at fit time,
        and it deserves the same guard here.
        """
        torch, transformers = require_ml_stack()
        target = Path(directory)
        manifest_path = target / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(
                f"{manifest_path} not found. A checkpoint without its manifest has "
                "no thresholds, no seed and no training fingerprint, so it cannot "
                "be reloaded as the model that was evaluated."
            )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        constructs = tuple(manifest.get("constructs", ()))
        if constructs and constructs != CONSTRUCTS:
            raise ValueError(
                f"{target} was fitted against a different construct order.\n"
                f"  saved:   {constructs}\n"
                f"  current: {CONSTRUCTS}\n"
                "Label columns are positional, so loading this would map every "
                "probability to the wrong construct. Re-fit against the current "
                "taxonomy instead."
            )

        model = cls(hparams=HParams(**manifest["hparams"]), constructs=constructs or CONSTRUCTS)
        model._tokenizer = transformers.AutoTokenizer.from_pretrained(target)
        model._model = transformers.AutoModelForSequenceClassification.from_pretrained(target)
        model._device = "cuda" if torch.cuda.is_available() else "cpu"
        model._model.to(model._device)
        model._model.eval()

        thresholds = manifest.get("thresholds") or {}
        model._thresholds = [thresholds.get(name, 0.5) for name in model.constructs]
        model._degenerate = tuple(manifest.get("degenerate_constructs", ()))
        model._fingerprint = manifest.get("training_fingerprint", "")
        model._n_train = manifest.get("n_train", 0)
        model._n_val = manifest.get("n_val", 0)
        model._best_epoch = manifest.get("best_epoch", 0)
        model._val_curve = list(manifest.get("val_macro_f1_curve", ()))
        model._resolved_base = manifest.get("resolved_base_model", "")
        return model

    def save(self, directory: Path | None = None) -> Path:
        """Persist weights, tokenizer and manifest under `models/`."""
        target = directory or (MODELS_DIR / f"transformer_{self.hparams.slug()}")
        target.mkdir(parents=True, exist_ok=True)
        if self._model is None:
            raise RuntimeError(f"{self.name}: fit() before save()")
        self._model.save_pretrained(target)
        self._tokenizer.save_pretrained(target)
        (target / "manifest.json").write_text(
            json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return target
