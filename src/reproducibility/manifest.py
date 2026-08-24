"""The actual declared reproduction path for this repository.

Read `PLAN` as a contract with a reviewer: these commands, in this order, in a
tree with these contents, produce these artefacts at these strengths -- and
these other artefacts are not produced at all, for stated reasons.

The tolerances here are the Phase 22 gate's numbers, and they are declared in
source **before** any re-run, hashed by `ReproductionPlan.declaration_sha256`,
and bound into every verification. Phase 19's corollary is the reason: a
tolerance is a claim, and a claim edited after the delta is known is not a gate.
The Claim row backing them is `reproduction_tolerance` in
`src/evaluation/ablations.py::CLAIMS`.

Why two strengths and not one
-----------------------------
Applying one word to every artefact would understate what this repository can
promise and overstate it in the same table. The corpus at seed 42 and the
classical baselines are deterministic -- Phase 13 asserts them at full float
precision, not `approx` -- so anything less than byte-identical for those is a
weaker claim than the code already makes. The transformer retrain is a different
animal: a distilroberta fine-tune on a different CPU, BLAS build and torch build
will not land on the same float, and demanding it would produce a gate that
fails for reasons unrelated to the claim.

So: **byte-identical for everything seeded, +/-0.010 absolute macro-F1 for the
one artefact that is genuinely re-trained.** 0.010 is a quarter of the +/-0.038
bootstrap half-width already reported on the 0.588 point estimate, and an
order below the +0.126 delta over the lexicon floor that the headline claim
rests on -- so a run that drifts far enough to matter cannot pass, and a run
that drifts less than the measurement noise cannot fail.

The trap this plan is built around
----------------------------------
`reports/predictions/` is COMMITTED. A fresh clone therefore reproduces every
headline number in `reports/results.json` in seconds, with no torch, no
`models/` and no corpus -- because the transformer's contribution is read off a
JSON file that came with the clone. That is a real and useful property, and
reporting it as "the transformer result reproduced" would be a lie of emphasis.
Tier B says what it is; tier C is the step that actually re-derives it, and it
is separated out precisely so it cannot be quietly absorbed into a green tick.
"""

from __future__ import annotations

from src.reproducibility.plan import (
    CPU_WHEEL_INDEX,
    Artefact,
    Match,
    ReproductionPlan,
    Step,
    Tier,
)

#: Absolute macro-F1 tolerance for the one genuinely-retrained artefact.
#: Declared 2026-08-24, before any re-run. See the module docstring for the
#: derivation; do not edit without re-declaring, which the plan hash enforces.
RETRAIN_TOLERANCE_MACRO_F1 = 0.010

#: Point estimates from the real 2026-08-16 checkpoint, as recorded in
#: `reports/results.json`. These are the "headline numbers" the plan's gate
#: refers to. Every one of them is a planted-label corpus-property measurement.
HEADLINE: dict[str, float] = {
    "transformer_template_disjoint_macro_f1": 0.5877114720181955,
    "lexicon_template_disjoint_macro_f1": 0.4617285842599597,
    "transformer_vs_lexicon_delta": 0.1259828877582358,
    "tfidf_template_disjoint_macro_f1": 0.22208037080486936,
    "tfidf_random_macro_f1": 0.9994594594594595,
    "transformer_random_macro_f1": 0.8219513236505683,
    "memorisation_gap_transformer": 0.23423985163237282,
}


#: SHA-256 of file artefacts, measured 2026-08-24 in a genuine fresh clone
#: (Linux, Python 3.11, base lock) after the newline fix described in
#: `src/preprocessing/store.py`.
#:
#: Recording digests rather than checking existence is the difference between
#: "the step wrote something" and "the step wrote the same thing". The first
#: version of this plan checked existence and rendered the result as
#: "byte-identical / reproduced", which overstates by exactly the amount that
#: matters.
#:
#: `records.jsonl` already matched the owner's Windows tree byte-for-byte before
#: the fix. `utterances.jsonl` did not, and the 9,302-byte difference was
#: entirely CRLF: the owner's copy was generated on Windows two days after the
#: corpus was generated in the container, and nothing recorded that. The digest
#: below is the post-fix, platform-independent one, so the owner's existing file
#: will match only after regenerating.
FILE_DIGESTS: dict[str, str] = {
    "corpus_records": "fa09f5adeea7e4f3d2c68ca7ff2537a4f9f34b5bfaa6cd91d834823216731d3a",
    "utterances": "87a796caf7d8ce110624aa3f77b92049d4a80be73b7390b10d852cb183436171",
}


PLAN = ReproductionPlan(
    steps=(
        Step(
            id="env",
            tier=Tier.A_SEEDED,
            command=(
                "git clone <repo-url> sports-risk-nlp-repro && cd sports-risk-nlp-repro && "
                "python -m venv .venv && . .venv/bin/activate && "
                "pip install -r requirements-base.lock.txt"
            ),
            purpose=(
                "Stand up the light environment from the lock, in a NEW directory, so the "
                "reproduction cannot read four months of accumulated artefacts."
            ),
            cannot_reproduce=(
                "Nothing numeric. This step installs no torch, so every tier-C artefact is "
                "out of its reach; it also cannot verify the ML layer's pins, which only "
                "the `env-ml` step exercises."
            ),
            reads=("requirements-base.lock.txt",),
            # The checker cannot run this: it clones the repository, and the
            # checker only exists once the clone does. Declared so a reader
            # follows it by hand rather than the runner silently failing it.
            runnable=False,
        ),
        Step(
            id="corpus",
            tier=Tier.A_SEEDED,
            command="python scripts/run_ingestion.py --count 4000 --seed 42",
            purpose=(
                "Regenerate the synth_precomp_v1 corpus. A fresh clone has no data/, so "
                "this is where the text a reviewer scores actually comes from."
            ),
            cannot_reproduce=(
                "Any property of real athlete text. The corpus is 100% synthetic template "
                "grammar (OPEN-011); reproducing it proves the generator is deterministic "
                "and proves nothing about athletes."
            ),
            reads=("config", "src/ingestion", "scripts/run_ingestion.py"),
            produces=(
                Artefact(
                    name="corpus_records",
                    locator="data/raw/synth_precomp_v1/records.jsonl",
                    match=Match.BYTE_IDENTICAL,
                ),
            ),
        ),
        Step(
            id="preprocess",
            tier=Tier.A_SEEDED,
            command="python scripts/run_preprocessing.py",
            purpose=(
                "Clean, segment and de-identify the generated corpus into the 9,302 "
                "utterances every downstream step consumes."
            ),
            cannot_reproduce=(
                "The de-identification recall figure against real text. The fixture measures "
                "the failure modes we thought to write down on a generator that plants no "
                "identifiers, so 0% leak rate is an upper bound (Phase 8)."
            ),
            reads=("data/raw", "config", "src/preprocessing"),
            produces=(
                Artefact(
                    name="utterances",
                    locator="data/interim/synth_precomp_v1/utterances.jsonl",
                    match=Match.BYTE_IDENTICAL,
                ),
            ),
        ),
        Step(
            id="baselines",
            tier=Tier.A_SEEDED,
            command="python scripts/run_baselines.py --seed 42",
            purpose=(
                "Re-fit the lexicon and classical baselines and re-derive the honest floor "
                "the transformer is measured against."
            ),
            cannot_reproduce=(
                "Independence of the lexicon floor from the corpus. OPEN-021: the lexicon "
                "shares ancestry with the template bank via taxonomy.yaml examples, so the "
                "0.462 floor travels with that caveat wherever it is quoted."
            ),
            reads=("data/interim", "config", "src/models", "src/evaluation"),
            produces=(
                Artefact(
                    name="lexicon_template_disjoint_macro_f1",
                    locator="reports/baselines.json:splits.template_disjoint.systems.lexicon.macro_f1.point",
                    match=Match.BYTE_IDENTICAL,
                ),
                Artefact(
                    name="tfidf_template_disjoint_macro_f1",
                    locator="reports/baselines.json:splits.template_disjoint.systems.tfidf_logreg.macro_f1.point",
                    match=Match.BYTE_IDENTICAL,
                ),
                Artefact(
                    name="tfidf_random_macro_f1",
                    locator="reports/baselines.json:splits.random.systems.tfidf_logreg.macro_f1.point",
                    match=Match.BYTE_IDENTICAL,
                ),
            ),
        ),
        Step(
            id="rescore",
            tier=Tier.B_RESCORE,
            command="python scripts/run_evaluation.py --seed 42 --resamples 1000",
            purpose=(
                "Re-score every system from the committed prediction caches and rebuild "
                "reports/results.json, including the paired bootstrap comparisons."
            ),
            cannot_reproduce=(
                "The transformer itself. This step reads reports/predictions/, which IS "
                "committed, so it re-derives the SCORING of the transformer's predictions "
                "and never the predictions. A green tick here is not evidence that the "
                "checkpoint retrains to the same place -- that is step `retrain`, tier C."
            ),
            reads=("reports/predictions", "data/interim", "config", "src/evaluation"),
            produces=(
                Artefact(
                    name="transformer_template_disjoint_macro_f1",
                    locator="reports/results.json:scores.template_disjoint::transformer.macro_f1.point",
                    match=Match.BYTE_IDENTICAL,
                ),
                Artefact(
                    name="transformer_vs_lexicon_delta",
                    locator="reports/results.json:comparisons.transformer_vs_lexicon.delta",
                    match=Match.BYTE_IDENTICAL,
                ),
                Artefact(
                    name="memorisation_gap_transformer",
                    locator="reports/results.json:comparisons.split_gap.delta",
                    match=Match.BYTE_IDENTICAL,
                ),
                Artefact(
                    name="transformer_random_macro_f1",
                    locator="reports/results.json:scores.random::transformer.macro_f1.point",
                    match=Match.BYTE_IDENTICAL,
                ),
            ),
        ),
        Step(
            id="env-ml",
            tier=Tier.C_RETRAIN,
            command=(
                f"pip install -r requirements-ml.lock.txt --extra-index-url {CPU_WHEEL_INDEX}"
            ),
            purpose=(
                "Install the training layer. Separated from `env` so a reviewer reproducing "
                "tiers A and B never pays for a multi-gigabyte ML stack."
            ),
            cannot_reproduce=(
                "Bit-level equivalence of the numeric stack. A different CPU, BLAS build or "
                "torch build changes float results, which is exactly why tier C is measured "
                "against a tolerance and tiers A and B are not."
            ),
            reads=("requirements-base.lock.txt", "requirements-ml.lock.txt"),
        ),
        Step(
            id="retrain",
            tier=Tier.C_RETRAIN,
            command=(
                "python scripts/run_transformer.py --seed 42 && "
                "python scripts/run_evaluation.py --cache-predictions"
            ),
            purpose=(
                "Actually re-derive the transformer predictions rather than reading the "
                "committed cache -- the only step that tests the headline model end to end."
            ),
            cannot_reproduce=(
                "Anything gold-derived, and anything about real athletes. It also costs "
                "roughly ten CPU-hours, so most reviewers will not run it; that is why its "
                "artefact is reported SKIPPED rather than silently folded into tier B."
            ),
            reads=("data/interim", "config", "src/models", "reports/predictions"),
            produces=(
                Artefact(
                    name="retrained_transformer_macro_f1",
                    locator="reports/results.json:scores.template_disjoint::transformer.macro_f1.point",
                    match=Match.WITHIN_TOLERANCE,
                    tolerance=RETRAIN_TOLERANCE_MACRO_F1,
                    units="absolute macro-F1",
                ),
            ),
        ),
        Step(
            id="gold",
            tier=Tier.D_BLOCKED,
            command="# no command exists",
            purpose=(
                "Named so that the gold-derived figures are visible as an absence with a "
                "reason, rather than as rows a reader has to notice are missing."
            ),
            cannot_reproduce=(
                "Everything it covers. data/gold/ is empty and no second annotator exists "
                "(OPEN-025), so no kappa and no human-agreement figure can be produced by "
                "anyone, the author included."
            ),
            reads=(),
            produces=(
                Artefact(
                    name="inter_annotator_kappa",
                    locator="reports/iaa.md",
                    match=Match.NOT_REPRODUCIBLE,
                    why_not=(
                        "OPEN-025: data/gold/ is empty because no second annotator was "
                        "recruited, and src/models/dataset.py refuses --gold rather than "
                        "falling back to silver. This is not a step a reviewer can run."
                    ),
                ),
                Artefact(
                    name="human_agreement_scores",
                    locator="reports/results.json:human_agreement",
                    match=Match.NOT_REPRODUCIBLE,
                    why_not=(
                        "OPEN-025 again, the same block as the kappa. Every figure in "
                        "this repository is "
                        "agreement with generator-planted labels on synthetic text, and no "
                        "human-labelled comparison set exists to reproduce."
                    ),
                ),
            ),
        ),
    )
)
