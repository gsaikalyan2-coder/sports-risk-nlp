"""Phase 22 -- tests for the declared reproduction path.

No torch, no network, no clone. Everything here is arithmetic over dataclasses,
which is the whole reason `src/reproducibility/` was written as a package rather
than as logic inside `scripts/run_reproduction.py`.

The tests worth reading first are the ones that assert something is
**unconstructable**: a tolerance on a byte-identical artefact, a pip command
missing its extra index, a step with no coverage sentence. Those are the
by-construction teeth, and a test that only checks the happy path would not
notice if one of them were removed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.view import ForbiddenLanguage
from src.evaluation.ablations import CLAIMS, ClaimLedger
from src.reproducibility import (
    HEADLINE,
    PLAN,
    RETRAIN_TOLERANCE_MACRO_F1,
    Artefact,
    ArtefactResult,
    ContaminatedTree,
    Match,
    MissingExtraIndex,
    Outcome,
    ReproductionPlan,
    Step,
    StepResult,
    Tier,
    VerificationReport,
    assert_absentees_are_gitignored,
    assert_fresh,
    inspect_tree,
    render_markdown,
)
from src.reproducibility.environment import (
    IGNORE_PROBES,
    MUST_BE_ABSENT_IN_FRESH_CLONE,
    PRESENT_IN_FRESH_CLONE,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

GOOD_SENTENCE = "a sentence long enough to be a real coverage statement about scope"


def a_step(**kwargs) -> Step:
    base = dict(
        id="s",
        tier=Tier.A_SEEDED,
        command="python scripts/run_ingestion.py --seed 42",
        purpose=GOOD_SENTENCE,
        cannot_reproduce=GOOD_SENTENCE,
    )
    base.update(kwargs)
    return Step(**base)  # type: ignore[arg-type]


def fresh_tree(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    for rel in PRESENT_IN_FRESH_CLONE:
        target = root / rel
        if rel.endswith(".json"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / ".gitkeep").write_text("", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------
# Artefact -- the three-way strength invariant
# ---------------------------------------------------------------------------


def test_within_tolerance_requires_a_positive_number():
    with pytest.raises(ValueError, match="not a gate"):
        Artefact(name="x", locator="reports/x.json", match=Match.WITHIN_TOLERANCE)
    with pytest.raises(ValueError, match="not a gate"):
        Artefact(
            name="x",
            locator="reports/x.json",
            match=Match.WITHIN_TOLERANCE,
            tolerance=0.0,
            units="macro-F1",
        )


def test_within_tolerance_requires_units():
    with pytest.raises(ValueError, match="units"):
        Artefact(name="x", locator="reports/x.json", match=Match.WITHIN_TOLERANCE, tolerance=0.01)


def test_byte_identical_may_not_carry_a_tolerance():
    """The contradiction that would otherwise sit in a table looking like rigour."""
    with pytest.raises(ValueError, match="understates"):
        Artefact(name="x", locator="reports/x.json", match=Match.BYTE_IDENTICAL, tolerance=0.01)


def test_unreproducible_artefact_must_say_why():
    with pytest.raises(ValueError, match="no explanation"):
        Artefact(name="x", locator="reports/iaa.md", match=Match.NOT_REPRODUCIBLE)


def test_agrees_is_exact_for_byte_identical_and_banded_for_tolerance():
    exact = Artefact(name="e", locator="p", match=Match.BYTE_IDENTICAL)
    assert exact.agrees(0.5877114720181955, 0.5877114720181955)
    assert not exact.agrees(0.5877114720181956, 0.5877114720181955)

    banded = Artefact(
        name="b", locator="p", match=Match.WITHIN_TOLERANCE, tolerance=0.010, units="macro-F1"
    )
    assert banded.agrees(0.5877 + 0.0099, 0.5877)
    assert not banded.agrees(0.5877 + 0.0101, 0.5877)


def test_comparing_an_unreproducible_artefact_raises():
    """Producing a value for a blocked artefact asserts the opposite of the plan."""
    blocked = Artefact(
        name="kappa", locator="reports/iaa.md", match=Match.NOT_REPRODUCIBLE, why_not=GOOD_SENTENCE
    )
    with pytest.raises(ValueError, match="declared unreproducible"):
        blocked.agrees(0.7, 0.7)


# ---------------------------------------------------------------------------
# Step -- coverage sentence and the extra-index tooth
# ---------------------------------------------------------------------------


def test_step_without_a_coverage_sentence_is_unconstructable():
    with pytest.raises(ValueError, match="cannot_reproduce"):
        a_step(cannot_reproduce="")
    with pytest.raises(ValueError, match="cannot_reproduce"):
        a_step(cannot_reproduce="n/a")


def test_pip_install_of_a_local_version_lock_demands_the_extra_index():
    """A command that only works for a reader who remembers a flag is not a path."""
    with pytest.raises(MissingExtraIndex, match="extra-index-url"):
        a_step(command="pip install -r requirements-ml.lock.txt")
    with pytest.raises(MissingExtraIndex):
        a_step(command="pip install -r requirements.lock.txt")


def test_the_extra_index_tooth_does_not_fire_on_the_base_lock():
    """It must distinguish, or it is a detector that fires on everything."""
    step = a_step(command="pip install -r requirements-base.lock.txt")
    assert "extra-index-url" not in step.command


def test_the_extra_index_tooth_is_satisfied_by_the_real_flag():
    step = a_step(
        command=(
            "pip install -r requirements-ml.lock.txt "
            "--extra-index-url https://download.pytorch.org/whl/cpu"
        )
    )
    assert "--extra-index-url" in step.command


def test_forbidden_language_is_refused_at_step_construction():
    with pytest.raises(ForbiddenLanguage):
        a_step(purpose="measure detection accuracy on the held-out split, carefully")


# ---------------------------------------------------------------------------
# The real plan
# ---------------------------------------------------------------------------


def test_every_declared_step_carries_a_coverage_sentence():
    for step in PLAN.steps:
        assert len(step.cannot_reproduce.strip()) >= 20, step.id


def test_the_plan_declares_something_it_cannot_reproduce():
    """A reproduction path claiming to reproduce everything is claiming too much."""
    blocked = [a for a in PLAN.artefacts if a.match is Match.NOT_REPRODUCIBLE]
    assert blocked, "OPEN-025 means at least the gold-derived figures are unreproducible"
    assert all("OPEN-025" in a.why_not or "gold" in a.why_not.lower() for a in blocked)


def test_only_the_retrain_artefact_uses_a_tolerance():
    """Everything seeded is exact; the tolerance is reserved for the one retrain."""
    banded = [a for a in PLAN.artefacts if a.match is Match.WITHIN_TOLERANCE]
    assert [a.name for a in banded] == ["retrained_transformer_macro_f1"]
    assert banded[0].tolerance == RETRAIN_TOLERANCE_MACRO_F1


def test_the_tolerance_is_smaller_than_the_effect_it_must_not_hide():
    """A tolerance wider than the headline delta would launder a real regression."""
    delta = HEADLINE["transformer_vs_lexicon_delta"]
    assert RETRAIN_TOLERANCE_MACRO_F1 < delta / 10
    # ...and it must also be smaller than the reported bootstrap half-width, or
    # it would fail runs that only moved by measurement noise.
    half_width = (0.6222430542818375 - 0.546256792412586) / 2
    assert RETRAIN_TOLERANCE_MACRO_F1 < half_width


def test_the_rescore_step_admits_it_reads_the_committed_cache():
    """The trap this plan exists to expose, asserted rather than described."""
    step = PLAN.step("rescore")
    assert "reports/predictions" in step.reads
    assert "committed" in step.cannot_reproduce


def test_tier_c_is_separate_from_tier_b():
    """Retraining must not be foldable into the cheap rescore's green tick."""
    assert PLAN.step("rescore").tier is Tier.B_RESCORE
    assert PLAN.step("retrain").tier is Tier.C_RETRAIN


def test_plan_hash_changes_when_a_tolerance_changes():
    """The mechanism behind 'a tolerance picked after the delta is not a gate'."""
    before = PLAN.declaration_sha256()
    widened = ReproductionPlan(
        steps=tuple(
            Step(
                id=s.id,
                tier=s.tier,
                command=s.command,
                purpose=s.purpose,
                cannot_reproduce=s.cannot_reproduce,
                reads=s.reads,
                produces=tuple(
                    Artefact(
                        name=a.name,
                        locator=a.locator,
                        match=a.match,
                        tolerance=(0.25 if a.match is Match.WITHIN_TOLERANCE else None),
                        units=a.units,
                        why_not=a.why_not,
                    )
                    for a in s.produces
                ),
            )
            for s in PLAN.steps
        )
    )
    assert widened.declaration_sha256() != before


def test_duplicate_artefact_names_are_refused():
    art = Artefact(name="dup", locator="p", match=Match.BYTE_IDENTICAL)
    with pytest.raises(ValueError, match="produced by two steps"):
        ReproductionPlan(
            steps=(a_step(id="one", produces=(art,)), a_step(id="two", produces=(art,)))
        )


# ---------------------------------------------------------------------------
# environment -- the fresh-clone tooth
# ---------------------------------------------------------------------------


def test_a_fresh_clone_is_usable(tmp_path):
    root = fresh_tree(tmp_path)
    check = inspect_tree(root)
    assert check.is_fresh and check.is_usable
    assert assert_fresh(root) is not None


def test_a_working_tree_with_data_is_refused(tmp_path):
    root = fresh_tree(tmp_path)
    target = root / MUST_BE_ABSENT_IN_FRESH_CLONE[0]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"id": 1}\n', encoding="utf-8")
    with pytest.raises(ContaminatedTree, match="NOT a fresh clone"):
        assert_fresh(root)


def test_a_clone_with_committed_interim_manifests_is_still_fresh(tmp_path):
    """The failure this list already had once, kept fixed by a test.

    `.gitignore` un-ignores `data/interim/*/provenance.json`, so a genuine clone
    arrives with a populated `data/interim/synth_precomp_v1/`. An earlier version
    of MUST_BE_ABSENT_IN_FRESH_CLONE named that directory and would have rejected
    every honest reproduction -- found by running the runner against a mock
    clone, not by any assertion in this file.
    """
    root = fresh_tree(tmp_path)
    interim = root / "data" / "interim" / "synth_precomp_v1"
    interim.mkdir(parents=True, exist_ok=True)
    (interim / "provenance.json").write_text("{}", encoding="utf-8")
    (interim / "preprocessing.json").write_text("{}", encoding="utf-8")
    assert inspect_tree(root).is_fresh


def test_a_clone_with_generated_utterances_is_not_fresh(tmp_path):
    root = fresh_tree(tmp_path)
    interim = root / "data" / "interim" / "synth_precomp_v1"
    interim.mkdir(parents=True, exist_ok=True)
    (interim / "utterances.jsonl").write_text('{"id": 1}\n', encoding="utf-8")
    assert not inspect_tree(root).is_fresh


def test_a_models_directory_holding_only_gitkeep_is_still_fresh(tmp_path):
    """What a genuine clone has. Calling this contamination fails every honest run."""
    root = fresh_tree(tmp_path)
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "models" / ".gitkeep").write_text("", encoding="utf-8")
    assert inspect_tree(root).is_fresh


def test_a_models_directory_holding_a_checkpoint_is_not_fresh(tmp_path):
    root = fresh_tree(tmp_path)
    (root / "models" / "phase14").mkdir(parents=True, exist_ok=True)
    (root / "models" / "phase14" / "model.safetensors").write_text("x", encoding="utf-8")
    assert not inspect_tree(root).is_fresh


def test_a_directory_missing_the_committed_cache_is_not_a_clone_either(tmp_path):
    root = fresh_tree(tmp_path)
    (root / "reports" / "predictions" / ".gitkeep").unlink()
    (root / "reports" / "predictions").rmdir()
    check = inspect_tree(root)
    assert check.is_fresh and not check.is_usable


def test_absentee_list_must_stay_gitignored():
    assert_absentees_are_gitignored(IGNORE_PROBES.values())  # all ignored: fine
    with pytest.raises(ContaminatedTree, match="no longer"):
        assert_absentees_are_gitignored([])


def test_every_absentee_has_an_ignore_probe():
    """The two lists cannot drift: an absentee with no probe would be unchecked."""
    assert set(IGNORE_PROBES) == set(MUST_BE_ABSENT_IN_FRESH_CLONE)


def test_the_probes_target_files_not_bare_directories():
    """`models/*` ignores the CONTENTS of models/, never `models` itself.

    Probing the bare directory is what the first version of this check did, and
    it failed on a correctly-configured clone -- the detector-fires-on-
    everything failure mode. Each probe must therefore name something inside.
    """
    for absentee, probe in IGNORE_PROBES.items():
        if absentee == "models":
            assert probe.startswith("models/") and probe != "models"
        else:
            assert probe == absentee


# ---------------------------------------------------------------------------
# verify -- the gate
# ---------------------------------------------------------------------------


def _report(tmp_path, **kwargs) -> VerificationReport:
    return VerificationReport(
        plan=PLAN,
        tree=inspect_tree(fresh_tree(tmp_path)),
        declared_sha256=kwargs.pop("declared_sha256", PLAN.declaration_sha256()),
        attempted_tiers=kwargs.pop("attempted_tiers", (Tier.A_SEEDED,)),
    )


def _reproduce_tier(report: VerificationReport, tier: Tier) -> None:
    """Mark every artefact of `tier` as genuinely reproduced."""
    kept = [s for s in report.steps if s.step_id not in {st.id for st in PLAN.by_tier(tier)}]
    report.steps[:] = kept
    for step in PLAN.by_tier(tier):
        report.add(
            StepResult(
                step_id=step.id,
                ran=True,
                artefacts=tuple(
                    ArtefactResult(
                        artefact=a, outcome=Outcome.REPRODUCED, expected=1.0, produced=1.0
                    )
                    for a in step.produces
                ),
            )
        )


def _full_coverage(report: VerificationReport) -> None:
    """Give every declared artefact a verdict, so only the tooth under test bites."""
    for step in PLAN.steps:
        report.add(
            StepResult(
                step_id=step.id,
                ran=False,
                artefacts=tuple(
                    ArtefactResult(
                        artefact=a,
                        outcome=(
                            Outcome.BLOCKED
                            if a.match is Match.NOT_REPRODUCIBLE
                            else Outcome.SKIPPED
                        ),
                        note="not run on this pass",
                    )
                    for a in step.produces
                ),
            )
        )


def test_gate_passes_when_the_attempted_tier_reproduces(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    passed, reasons = report.gate()
    assert passed, reasons


def test_gate_fails_when_nothing_runnable_was_attempted(tmp_path):
    """A correctly-filled-in form is not evidence.

    Found at Phase 22 by rendering the report and reading it: with no tiers
    selected, every artefact is honestly SKIPPED, every other check is satisfied
    and the gate went green having reproduced nothing.
    """
    report = _report(tmp_path, attempted_tiers=())
    _full_coverage(report)
    passed, reasons = report.gate()
    assert not passed
    assert any("reproduced nothing" in r for r in reasons)


def test_gate_fails_when_an_attempted_tier_skips_one_of_its_artefacts(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)  # everything SKIPPED, tier A attempted
    passed, reasons = report.gate()
    assert not passed
    assert any("belongs to an attempted tier but is reported skipped" in r for r in reasons)


def test_gate_fails_when_a_declared_artefact_is_never_mentioned(tmp_path):
    """Silence about a declared artefact is how a path claims more than it delivers."""
    report = _report(tmp_path)
    passed, reasons = report.gate()
    assert not passed
    assert any("carries no verdict" in r for r in reasons)


def test_gate_fails_in_a_contaminated_tree(tmp_path):
    root = fresh_tree(tmp_path)
    (root / "models" / "ckpt").mkdir(parents=True, exist_ok=True)
    (root / "models" / "ckpt" / "w.bin").write_text("x", encoding="utf-8")
    report = VerificationReport(
        plan=PLAN,
        tree=inspect_tree(root),
        declared_sha256=PLAN.declaration_sha256(),
        attempted_tiers=(Tier.A_SEEDED,),
    )
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    passed, reasons = report.gate()
    assert not passed
    assert any("fresh clone" in r for r in reasons)


def test_gate_fails_when_the_plan_changed_after_declaration(tmp_path):
    report = _report(tmp_path, declared_sha256="0" * 64)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    passed, reasons = report.gate()
    assert not passed
    assert any("fitted to that run" in r for r in reasons)


def test_gate_fails_on_a_deviation(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    artefact = PLAN.artefact("transformer_template_disjoint_macro_f1")
    report.steps[0] = StepResult(
        step_id=PLAN.steps[0].id,
        ran=True,
        artefacts=(
            ArtefactResult(
                artefact=artefact,
                outcome=Outcome.DEVIATED,
                expected=0.5877114720181955,
                produced=0.41,
            ),
        ),
    )
    # the artefact now has two verdicts; the deviating one must still fail the gate
    passed, reasons = report.gate()
    assert not passed
    assert any("outside the declared" in r for r in reasons)


def test_gate_fails_on_an_undeclared_read(tmp_path):
    """The hidden-input tooth: the corpus has to come from somewhere."""
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    report.add(
        StepResult(
            step_id="rescore",
            ran=True,
            observed_reads=("models/phase14_transformer",),
        )
    )
    passed, reasons = report.gate()
    assert not passed
    assert any("hidden input" in r for r in reasons)


def test_declared_reads_are_accepted(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    report.add(
        StepResult(
            step_id="rescore",
            ran=True,
            observed_reads=("reports/predictions/template_disjoint__transformer.json",),
        )
    )
    passed, reasons = report.gate()
    assert passed, reasons


def test_a_verdict_with_no_comparison_behind_it_is_unconstructable():
    artefact = PLAN.artefact("transformer_template_disjoint_macro_f1")
    with pytest.raises(ValueError, match="OPEN-034"):
        ArtefactResult(artefact=artefact, outcome=Outcome.REPRODUCED)


def test_blocked_verdict_must_match_a_blocked_declaration():
    artefact = PLAN.artefact("transformer_template_disjoint_macro_f1")
    with pytest.raises(ValueError, match="One of the two is wrong"):
        ArtefactResult(artefact=artefact, outcome=Outcome.BLOCKED)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def test_rendered_report_always_carries_the_coverage_section(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    rendered = render_markdown(report)
    assert "What this run does NOT reproduce" in rendered
    assert "inter_annotator_kappa" in rendered
    assert "OPEN-025" in rendered


def test_rendered_report_carries_the_provisional_stamp(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    assert "PROVISIONAL" in render_markdown(report)


def test_rendered_report_passes_the_forbidden_vocabulary_screen(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    render_markdown(report)  # raises ForbiddenLanguage if it does not


def test_report_serialises_and_never_claims_to_be_accuracy(tmp_path):
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    payload = json.loads(json.dumps(report.as_dict()))
    assert payload["is_accuracy"] is False
    assert payload["gate"] == "PASS"


# ---------------------------------------------------------------------------
# the claim ledger -- Phase 19's corollary, enforced
# ---------------------------------------------------------------------------


def test_the_tolerance_claim_exists_in_the_ledger():
    assert any(c.id == "reproduction_tolerance" for c in CLAIMS)


def test_the_tolerance_claim_is_unbacked_when_the_plan_drifts():
    claim = next(c for c in CLAIMS if c.id == "reproduction_tolerance")
    good = {
        "reproduction": {
            "declaration": {
                "retrain_tolerance_macro_f1": RETRAIN_TOLERANCE_MACRO_F1,
                "declared_sha256": "abc",
                "plan_sha256": "abc",
            }
        }
    }
    drifted = {
        "reproduction": {
            "declaration": {
                "retrain_tolerance_macro_f1": RETRAIN_TOLERANCE_MACRO_F1,
                "declared_sha256": "abc",
                "plan_sha256": "def",
            }
        }
    }
    ledger = ClaimLedger(claims=(claim,))
    assert ledger.unbacked(good) == ()
    assert ledger.unbacked(drifted) == (claim,)


# ---------------------------------------------------------------------------
# Cross-platform byte identity (found by running, 2026-08-24)
# ---------------------------------------------------------------------------

PIPELINE_WRITERS = (
    "src/ingestion/store.py",
    "src/preprocessing/store.py",
    "src/labeling/store.py",
    "src/evaluation/sampling.py",
)


def test_every_pipeline_writer_pins_the_newline():
    """A byte-identity claim that holds only on one OS is not a claim.

    Phase 22 verified the corpus in a real fresh clone on Linux and found the
    owner's `records.jsonl` matched byte-for-byte while `utterances.jsonl` did
    not -- identical content, 9,302 bytes apart, because Python translates "\\n"
    to "\\r\\n" on Windows and the two files had been generated two days apart on
    two different platforms. The stores' code was identical; only the machine
    differed, and nothing recorded which.

    A source-level check rather than a functional one, deliberately: on Linux the
    functional version passes whether or not the fix is present, so it would
    assert nothing about the platform where the defect lives.
    """
    repo_root = Path(__file__).resolve().parents[1]
    for rel in PIPELINE_WRITERS:
        source = (repo_root / rel).read_text(encoding="utf-8")
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if '.open("w"' in stripped or 'open("w"' in stripped:
                assert 'newline="\\n"' in stripped, f"{rel}: {stripped}"


def test_gate_fails_when_a_step_exits_nonzero(tmp_path):
    """A step producing no artefact still has to succeed.

    Found on the first real run against a genuine fresh clone: `env` exited
    non-zero (its command clones the repository, which cannot be done from
    inside the clone), produced no artefacts, and the gate passed on the
    strength of the later steps. Third instance this phase of the check and the
    property being related by assumption.
    """
    report = _report(tmp_path)
    _full_coverage(report)
    _reproduce_tier(report, Tier.A_SEEDED)
    report.add(StepResult(step_id="rescore", ran=True, exit_code=127))
    passed, reasons = report.gate()
    assert not passed
    assert any("exited 127" in r for r in reasons)


def test_the_clone_step_is_declared_unrunnable_by_the_checker():
    """You cannot `git clone` the repository from inside the clone."""
    assert PLAN.step("env").runnable is False
    assert all(s.runnable for s in PLAN.steps if s.id != "env")


def test_the_declaration_hash_covers_every_field_of_a_step():
    """A field left out of `as_dict` is a field the hash cannot protect.

    `runnable` was added to `Step` and not to `as_dict`, so flipping it changed
    the plan's behaviour and not its fingerprint -- a declaration hash with a
    blind spot. Compared against the dataclass's own field list so a future
    field cannot be forgotten the same way.
    """
    import dataclasses

    serialised = set(PLAN.as_dict()["steps"][0])
    declared = {f.name for f in dataclasses.fields(PLAN.steps[0])}
    assert declared - serialised == set(), f"unhashed step fields: {declared - serialised}"


def test_every_file_artefact_has_a_recorded_digest():
    """Otherwise the runner can only existence-check it and call that reproduced."""
    from src.reproducibility import FILE_DIGESTS

    file_artefacts = {
        a.name for a in PLAN.artefacts if ":" not in a.locator and a.locator.endswith(".jsonl")
    }
    assert file_artefacts <= set(FILE_DIGESTS), file_artefacts - set(FILE_DIGESTS)


def test_numeric_artefacts_point_at_a_value_not_a_file():
    """A locator naming only a file can be existence-checked and nothing more.

    Three baseline artefacts shipped for one round pointing at
    `reports/baselines.json` with no key, so the runner compared "the file
    exists" and rendered it as "byte-identical / reproduced" -- the same
    overstatement `FILE_DIGESTS` was added to fix, in a second place. Every
    artefact carrying a recorded headline value must address a value.
    """
    for artefact in PLAN.artefacts:
        if artefact.name in HEADLINE:
            assert ":" in artefact.locator, artefact.name
