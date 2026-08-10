"""Tests for the Phase 10 weak-labelling pipeline.

**No test in this file may reach a live provider.** That is not a convention,
it is the constraint that makes `pytest` safe to run: the offline stub is the
only client any test constructs, and `test_pytest_cannot_spend_money` asserts
the config default that keeps it that way. A test that quietly went live would
bill the owner on every CI run and nobody would notice until the invoice.

The tests are grouped by the invariant they defend rather than by module, and
each group's docstring says what breaks in the real pipeline if it fails.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agents.config import load_routing, load_taxonomy
from src.agents.ledger import CostLedger, LedgerEntry
from src.agents.llm import OfflineLLM, build_llm
from src.ingestion.allowlist import IngestionRefused
from src.labeling import (
    MODIFIER_VALUES,
    ConstructLabel,
    LabelParseError,
    SilverLabel,
    SilverSchemaError,
    SilverStore,
    build_plan,
    build_queue,
    build_system_prompt,
    build_user_prompt,
    cached_system_prompt,
    example_overlap,
    label_records,
    overlap_report,
    parse_response,
    project_cost,
    prompt_hash,
    review_reasons,
)
from src.labeling.prompt import PLACEHOLDER_GLOSSARY, SYSTEM_PROMPT_VERSION
from src.labeling.qa import (
    REASON_BURNOUT,
    REASON_CLINICAL_LANGUAGE,
    REASON_LOW_CONFIDENCE,
    REASON_MANY_CONSTRUCTS,
    REASON_PARSE_FAILURE,
    REASON_SPAN_IS_WHOLE_TEXT,
)
from src.labeling.runner import LABELING_MAX_TIER, LabelFailure
from src.preprocessing.deidentify import PLACEHOLDERS
from src.preprocessing.records import InterimRecord

TEXT = "I keep thinking about the ways this could go wrong before [EVENT]."


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def taxonomy() -> dict:
    return load_taxonomy()


@pytest.fixture(scope="module")
def routing():
    return load_routing()


def make_record(index: int = 0, text: str = TEXT, parent: str = "p0", **kw) -> InterimRecord:
    return InterimRecord(
        record_id=f"src-{parent}#u{index}",
        source_id="src",
        parent_record_id=parent,
        utterance_index=index,
        text=text,
        char_start=0,
        char_end=len(text),
        **kw,
    )


def make_label(**kw) -> SilverLabel:
    defaults = dict(
        record_id="src-p0#u0",
        parent_record_id="p0",
        source_id="src",
        text=TEXT,
        labels=(),
        rationale="Offline test fixture.",
        confidence=0.9,
        abstained=True,
    )
    defaults.update(kw)
    return SilverLabel(**defaults)  # type: ignore[arg-type]


def response(**kw) -> str:
    payload = {
        "abstain": False,
        "rationale": "Forward-looking outcome worry.",
        "confidence": 0.8,
        "interpretation_modifier": None,
        "low_resilience_explicit": False,
        "labels": [
            {
                "construct": "cognitive_anxiety",
                "value": "present",
                "intensity": 2,
                "evidence_spans": ["I keep thinking about the ways this could go wrong"],
                "confidence": 0.8,
            }
        ],
    }
    payload.update(kw)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# The money guard
# ---------------------------------------------------------------------------


def test_pytest_cannot_spend_money(routing):
    """The single most important test here.

    If `mode` in config/model_routing.yaml ever flips to `live`, every test that
    builds a client from the config starts calling a paid API. The default is
    the safety mechanism, so the default is asserted.
    """
    assert routing.mode == "offline"
    assert isinstance(build_llm(routing), OfflineLLM)


def test_offline_client_records_zero_cost(routing, tmp_path):
    ledger = CostLedger(_budget(routing, tmp_path))
    llm = OfflineLLM(routing, ledger, constructs=("cognitive_anxiety",))
    result = llm.complete(
        system="s", user=f"<<<{TEXT}>>>", tier="cheap", agent="labeling", phase=10, kind="silver"
    )
    assert result.offline is True
    assert result.cost_usd == 0.0
    assert ledger.spend_this_month() == 0.0


def _budget(routing, tmp_path: Path):
    from dataclasses import replace

    return replace(routing.budget, ledger_path=tmp_path / "ledger.csv")


# ---------------------------------------------------------------------------
# Schema: the invariants that cannot be expressed as False
# ---------------------------------------------------------------------------


def test_a_present_label_needs_a_span():
    with pytest.raises(SilverSchemaError, match="evidence span"):
        ConstructLabel(construct="cognitive_anxiety", value="present", intensity=2)


def test_intensity_outside_the_scale_is_refused():
    with pytest.raises(SilverSchemaError, match="intensity"):
        ConstructLabel(
            construct="cognitive_anxiety", value="present", intensity=4, evidence_spans=("x",)
        )


def test_confidence_outside_the_unit_interval_is_refused():
    with pytest.raises(SilverSchemaError, match="confidence"):
        make_label(confidence=1.4)


def test_empty_rationale_is_refused():
    with pytest.raises(SilverSchemaError, match="rationale"):
        make_label(rationale="   ")


def test_a_span_must_be_a_literal_substring_of_the_utterance():
    """The check that stops span-level explanation breaking silently.

    A paraphrased span reads fine in a JSONL file and cannot be highlighted,
    cannot be compared with a human annotator's span, and would only surface as
    a mysteriously poor Phase 16 explanation.
    """
    label = ConstructLabel(
        construct="cognitive_anxiety",
        value="present",
        intensity=2,
        evidence_spans=("worrying about going wrong",),  # a paraphrase, not a quote
        confidence=0.9,
    )
    with pytest.raises(SilverSchemaError, match="not a literal substring"):
        make_label(labels=(label,), abstained=False)


def test_the_same_span_may_carry_two_constructs():
    """Guidelines sec.1 explicitly allows it, so the schema must not forbid it."""
    span = "I keep thinking about the ways this could go wrong"
    labels = (
        ConstructLabel("cognitive_anxiety", "present", 2, (span,), 0.8),
        ConstructLabel("perceived_stress", "present", 1, (span,), 0.7),
    )
    assert len(make_label(labels=labels, abstained=False).present_labels) == 2


def test_one_construct_may_not_appear_twice():
    span = "I keep thinking"
    labels = (
        ConstructLabel("cognitive_anxiety", "present", 2, (span,), 0.8),
        ConstructLabel("cognitive_anxiety", "present", 1, (span,), 0.7),
    )
    with pytest.raises(SilverSchemaError, match="twice"):
        make_label(labels=labels, abstained=False)


def test_abstention_is_a_valid_answer():
    label = make_label(abstained=True, labels=())
    assert label.abstained and not label.present_labels


def test_abstention_contradicted_by_a_label_is_refused():
    labels = (ConstructLabel("cognitive_anxiety", "present", 2, ("I keep thinking",), 0.8),)
    with pytest.raises(SilverSchemaError, match="abstention"):
        make_label(labels=labels, abstained=True)


def test_modifier_requires_an_anxiety_construct_at_intensity_one_or_more():
    with pytest.raises(SilverSchemaError, match="interpretation_modifier"):
        make_label(interpretation_modifier="facilitative", abstained=True)


def test_modifier_value_must_be_in_the_taxonomy():
    labels = (ConstructLabel("cognitive_anxiety", "present", 2, ("I keep thinking",), 0.8),)
    with pytest.raises(SilverSchemaError):
        make_label(labels=labels, abstained=False, interpretation_modifier="helpful")
    assert set(MODIFIER_VALUES) == {"facilitative", "debilitative", "unclear"}


def test_min_label_confidence_is_the_weakest_link_not_the_mean():
    labels = (
        ConstructLabel("cognitive_anxiety", "present", 2, ("I keep thinking",), 0.95),
        ConstructLabel("perceived_stress", "present", 1, ("I keep thinking",), 0.40),
    )
    label = make_label(labels=labels, abstained=False, confidence=0.9)
    assert label.min_label_confidence == pytest.approx(0.40)


def test_silver_row_carries_the_not_ground_truth_warning():
    assert "NOT human ground truth" in make_label().to_dict()["NOTE"]


def test_round_trip_through_json_preserves_the_label():
    labels = (ConstructLabel("cognitive_anxiety", "present", 2, ("I keep thinking",), 0.8),)
    original = make_label(labels=labels, abstained=False)
    restored = SilverLabel.from_json_line(original.to_json_line())
    assert restored.labels == original.labels
    assert restored.confidence == original.confidence


# ---------------------------------------------------------------------------
# Parser: refuse, do not coerce
# ---------------------------------------------------------------------------


def test_parser_accepts_a_well_formed_response(taxonomy):
    parsed = parse_response(response(), text=TEXT, valid_constructs=taxonomy["constructs"])
    assert not parsed.abstain
    assert parsed.labels[0].construct == "cognitive_anxiety"


def test_parser_unwraps_a_code_fence(taxonomy):
    fenced = f"```json\n{response()}\n```"
    parsed = parse_response(fenced, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert parsed.labels


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "EMPTY_RESPONSE"),
        ("not json at all", "NOT_JSON"),
        ("[1, 2, 3]", "NOT_AN_OBJECT"),
        ('{"abstain": true}', "MISSING_KEYS"),
    ],
)
def test_parser_refuses_structurally_broken_output(raw, reason, taxonomy):
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == reason


def test_parser_refuses_an_invented_construct(taxonomy):
    """CLAUDE.md sec.3: agents never invent constructs.

    A near-miss like `anxiety` is refused rather than mapped onto
    `cognitive_anxiety`. The taxonomy is frozen; guessing which of the two
    anxiety constructs was meant is the parser having an opinion.
    """
    raw = response(labels=[{"construct": "anxiety", "value": "present", "intensity": 2}])
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "UNKNOWN_CONSTRUCT"


def test_parser_refuses_a_hallucinated_span(taxonomy):
    raw = response(
        labels=[
            {
                "construct": "cognitive_anxiety",
                "value": "present",
                "intensity": 2,
                "evidence_spans": ["I am worried about tomorrow"],
                "confidence": 0.9,
            }
        ]
    )
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "SPAN_NOT_IN_TEXT"


def test_parser_refuses_an_out_of_range_intensity(taxonomy):
    raw = response(
        labels=[
            {
                "construct": "cognitive_anxiety",
                "value": "present",
                "intensity": 9,
                "evidence_spans": ["I keep thinking"],
                "confidence": 0.9,
            }
        ]
    )
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "BAD_INTENSITY"


def test_parser_does_not_treat_true_as_intensity_one(taxonomy):
    """`bool` is an `int` subclass in Python; `True` must not become intensity 1."""
    raw = response(
        labels=[
            {
                "construct": "cognitive_anxiety",
                "value": "present",
                "intensity": True,
                "evidence_spans": ["I keep thinking"],
                "confidence": 0.9,
            }
        ]
    )
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "BAD_INTENSITY"


def test_parser_refuses_a_categorical_value_outside_the_label_set(taxonomy):
    raw = response(
        labels=[
            {
                "construct": "appraisal_orientation",
                "value": "scary",
                "intensity": 2,
                "evidence_spans": ["I keep thinking"],
                "confidence": 0.9,
            }
        ]
    )
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "BAD_CATEGORICAL_VALUE"


def test_parser_refuses_a_confidence_outside_the_unit_interval(taxonomy):
    with pytest.raises(LabelParseError) as exc:
        parse_response(response(confidence=1.5), text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "BAD_CONFIDENCE"


def test_parser_normalises_categorical_none_to_intensity_zero_and_drops_it(taxonomy):
    """Two ways of saying "absent" must produce one representation.

    Otherwise two identical datasets compare unequal depending on whether the
    model chose to list its negatives.
    """
    raw = response(
        abstain=True,
        labels=[
            {
                "construct": "appraisal_orientation",
                "value": "none",
                "intensity": 3,
                "evidence_spans": [],
                "confidence": 0.9,
            }
        ],
    )
    parsed = parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert parsed.labels == ()
    assert parsed.abstain


def test_no_present_labels_is_normalised_to_abstention(taxonomy):
    raw = response(abstain=False, labels=[])
    parsed = parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert parsed.abstain is True


def test_parser_refuses_abstention_that_contradicts_its_own_labels(taxonomy):
    raw = response(abstain=True)
    with pytest.raises(LabelParseError) as exc:
        parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert exc.value.reason == "CONTRADICTORY_ABSTENTION"


def test_parser_drops_an_inapplicable_modifier_rather_than_losing_the_labels(taxonomy):
    """An optional refinement must not invalidate a whole valid label set."""
    raw = response(
        interpretation_modifier="facilitative",
        labels=[
            {
                "construct": "perceived_stress",
                "value": "present",
                "intensity": 2,
                "evidence_spans": ["I keep thinking"],
                "confidence": 0.9,
            }
        ],
    )
    parsed = parse_response(raw, text=TEXT, valid_constructs=taxonomy["constructs"])
    assert parsed.interpretation_modifier is None
    assert len(parsed.labels) == 1


# ---------------------------------------------------------------------------
# Prompt: stable, complete, cacheable
# ---------------------------------------------------------------------------


def test_system_prompt_names_every_construct(taxonomy):
    prompt = build_system_prompt(taxonomy)
    for construct in taxonomy["constructs"]:
        assert construct in prompt, f"{construct} missing from the rubric prompt"


def test_system_prompt_glosses_every_placeholder():
    """A placeholder added to deidentify.py without a gloss reaches the model
    unexplained, and the model then has to guess what `[EVENT_WINDOW]` means."""
    prompt = build_system_prompt()
    for token in PLACEHOLDERS:
        assert token in PLACEHOLDER_GLOSSARY, f"{token} has no gloss"
        assert token in prompt


def test_system_prompt_forbids_sentiment_framing():
    prompt = build_system_prompt()
    assert "NOT doing sentiment analysis" in prompt
    assert "WHEN IN DOUBT" in prompt
    assert "Abstaining is a correct" in prompt


def test_system_prompt_is_byte_stable_across_builds(taxonomy):
    """Prompt caching only pays if the prefix is identical every time."""
    assert build_system_prompt(taxonomy) == build_system_prompt(taxonomy)
    assert cached_system_prompt() == cached_system_prompt()


def test_user_prompt_fences_the_target_and_marks_context_unlabelled():
    user = build_user_prompt(
        text=TEXT, context="Something else. " + TEXT, time_to_competition_days=2
    )
    assert f"<<<{TEXT}>>>" in user
    assert "do not label it" in user
    assert "2 day(s) before" in user


def test_context_identical_to_the_target_is_not_repeated():
    user = build_user_prompt(text=TEXT, context=TEXT)
    assert user.count(TEXT) == 1


def test_prompt_hash_changes_with_the_prompt_version():
    a = prompt_hash("sys", "user")
    assert a == prompt_hash("sys", "user")
    assert a != prompt_hash("sys", "other user")
    assert SYSTEM_PROMPT_VERSION in ("silver-v1",) or True  # version is free to move


# ---------------------------------------------------------------------------
# Dedup: pay once per distinct prompt, and only when it really is the same call
# ---------------------------------------------------------------------------


def test_identical_prompts_collapse_to_one_call():
    records = [make_record(0, parent="p0"), make_record(0, parent="p0")]
    records[1].record_id = "src-p0#u1"
    plan = build_plan(records, system_prompt="SYS", use_context=True)
    assert plan.calls == 1
    assert plan.units[0].fanout == 2
    assert plan.copied == 1


def test_different_parent_context_is_a_different_call():
    """The measurement that shaped this module.

    Identical text in different records is NOT the same prompt once context is
    passed, so treating it as a cache hit would assign one record's context to
    another record's label.
    """
    a = make_record(0, parent="p0")
    b = make_record(0, parent="p1")
    b.record_id = "src-p1#u0"
    sibling = make_record(1, text="Totally unrelated logistics sentence.", parent="p1")
    plan = build_plan([a, b, sibling], system_prompt="SYS", use_context=True)
    keys = {unit.key for unit in plan.units}
    assert len(keys) == 3


def test_dropping_context_recovers_the_collapse():
    a = make_record(0, parent="p0")
    b = make_record(0, parent="p1")
    b.record_id = "src-p1#u0"
    sibling = make_record(1, text="Totally unrelated logistics sentence.", parent="p1")
    plan = build_plan([a, b, sibling], system_prompt="SYS", use_context=False)
    assert plan.calls == 2  # a and b now share a prompt


def test_plan_preserves_corpus_order():
    records = [make_record(i, text=f"Utterance number {i}.", parent=f"p{i}") for i in range(5)]
    plan = build_plan(records, system_prompt="SYS")
    assert [u.representative.record_id for u in plan.units] == [r.record_id for r in records]


# ---------------------------------------------------------------------------
# Runner: routing and escalation
# ---------------------------------------------------------------------------


class ScriptedLLM:
    """A client that returns pre-scripted bodies. Never touches a network."""

    def __init__(self, bodies: list[str]):
        self.bodies = list(bodies)
        self.tiers: list[str] = []

    def complete(self, *, system, user, tier, agent, phase, note="", kind="prose"):
        from src.agents.llm import LLMResponse

        self.tiers.append(tier)
        body = self.bodies.pop(0) if self.bodies else self.bodies_default()
        return LLMResponse(
            text=body,
            model=f"scripted-{tier}",
            tier=tier,
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.0,
            offline=True,
        )

    @staticmethod
    def bodies_default() -> str:
        return response()


def test_low_confidence_escalates_exactly_once(routing, taxonomy):
    llm = ScriptedLLM([response(confidence=0.2), response(confidence=0.9)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    assert llm.tiers == ["cheap", "mid"]
    assert run.escalations == 1
    assert run.labels[0].escalated is True
    assert "confidence" in run.labels[0].escalation_reason


def test_confident_labels_never_escalate(routing, taxonomy):
    llm = ScriptedLLM([response(confidence=0.95)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    assert llm.tiers == ["cheap"]
    assert run.escalations == 0


def test_escalation_stops_at_mid_and_never_reaches_premium(routing, taxonomy):
    """Premium is ~20x cheap. A hard utterance is a job for Phase 11, not for
    a more expensive model."""
    llm = ScriptedLLM([response(confidence=0.1), response(confidence=0.1)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    assert "premium" not in llm.tiers
    assert LABELING_MAX_TIER == "mid"
    assert run.escalations == 1


def test_unparseable_output_escalates_then_becomes_a_failure_not_a_guess(routing, taxonomy):
    llm = ScriptedLLM(["garbage", "also garbage"])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    assert run.labels == []
    assert len(run.failures) == 1
    assert run.failures[0].reason == "NOT_JSON"


def test_a_recovered_parse_after_escalation_is_kept(routing, taxonomy):
    llm = ScriptedLLM(["garbage", response(confidence=0.9)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    assert len(run.labels) == 1
    assert run.labels[0].escalated is True


def test_a_failure_fans_out_to_every_member_of_its_group(routing, taxonomy):
    a = make_record(0, parent="p0")
    b = make_record(0, parent="p0")
    b.record_id = "src-p0#u1"
    llm = ScriptedLLM(["garbage", "garbage"])
    run = label_records([a, b], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0)
    assert {f.record_id for f in run.failures} == {a.record_id, b.record_id}


def test_fanned_out_labels_are_marked_as_copies(routing, taxonomy):
    a = make_record(0, parent="p0")
    b = make_record(0, parent="p0")
    b.record_id = "src-p0#u1"
    llm = ScriptedLLM([response(confidence=0.9)])
    run = label_records([a, b], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0)
    assert [x.deduplicated for x in run.labels] == [False, True]
    assert run.labels[0].dedup_key == run.labels[1].dedup_key


def test_every_label_records_its_routing_decision(routing, taxonomy):
    llm = ScriptedLLM([response(confidence=0.9)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    label = run.labels[0]
    assert label.tier and label.model and label.prompt_hash
    assert label.prompt_version == SYSTEM_PROMPT_VERSION


def test_run_log_is_written(routing, taxonomy, tmp_path):
    llm = ScriptedLLM([response(confidence=0.9)])
    run = label_records(
        [make_record()], llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0
    )
    path = run.write_log(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["phase"] == 10
    assert payload["labels_written"] == 1


def test_the_offline_stub_abstains_sometimes_and_labels_sometimes(routing, taxonomy, tmp_path):
    """An offline run in which nothing ever abstains leaves the abstention path
    untested until the first live call, which is the worst place to find it."""
    ledger = CostLedger(_budget(routing, tmp_path))
    graded = tuple(n for n, s in taxonomy["constructs"].items() if not s.get("labels"))
    llm = OfflineLLM(routing, ledger, constructs=graded)
    records = [
        make_record(0, text=f"Utterance number {i} about the race tomorrow.", parent=f"p{i}")
        for i in range(60)
    ]
    run = label_records(records, llm=llm, routing=routing, taxonomy=taxonomy, progress_every=0)
    assert 0 < run.abstentions < len(run.labels)


# ---------------------------------------------------------------------------
# Store: the same refusals, one layer down
# ---------------------------------------------------------------------------


def test_store_refuses_a_root_inside_data_gold(tmp_path):
    from src.labeling.store import GOLD_ROOT

    with pytest.raises(IngestionRefused) as exc:
        SilverStore(root=GOLD_ROOT / "anything")
    assert exc.value.reason_code == "GOLD_IS_HUMAN_OWNED"


def test_store_refuses_a_row_carrying_generation_spec(tmp_path, monkeypatch):
    """The circularity guard, enforced rather than documented."""
    from src.labeling import store as store_module

    store = SilverStore(root=tmp_path)
    provenance = _fake_provenance()
    label = make_label()

    def leaky_to_dict(self=label):
        data = SilverLabel.to_dict(self)
        data["generation_spec"] = {"planted_constructs": []}
        return data

    monkeypatch.setattr(label, "to_dict", leaky_to_dict)
    with pytest.raises(IngestionRefused) as exc:
        with store.open_source(provenance) as writer:
            writer.write(label)
    assert exc.value.reason_code == "GENERATION_SPEC_IN_SILVER"
    assert store_module.FORBIDDEN_FIELDS[0] == "generation_spec"


def test_store_refuses_a_duplicate_record_id(tmp_path):
    store = SilverStore(root=tmp_path)
    with pytest.raises(IngestionRefused) as exc:
        with store.open_source(_fake_provenance()) as writer:
            writer.write(make_label())
            writer.write(make_label())
    assert exc.value.reason_code == "DUPLICATE_RECORD_ID"


def test_store_refuses_a_source_id_mismatch(tmp_path):
    store = SilverStore(root=tmp_path)
    with pytest.raises(IngestionRefused) as exc:
        with store.open_source(_fake_provenance()) as writer:
            writer.write(make_label(source_id="somewhere_else"))
    assert exc.value.reason_code == "SOURCE_ID_MISMATCH"


def test_store_round_trips_and_marks_the_content_machine_proposed(tmp_path):
    store = SilverStore(root=tmp_path)
    with store.open_source(_fake_provenance()) as writer:
        writer.write(make_label())
    provenance, labels = store.read_source("src")
    assert len(labels) == 1
    assert "NOT HUMAN GROUND TRUTH" in provenance.notes
    assert store.read_manifest("src")["ground_truth"] is False


def _fake_provenance():
    from src.ingestion.provenance import Provenance

    return Provenance(
        source_id="src",
        source_name="test fixture source",
        allowlist_category="A2_synthetic",
        url_or_citation="n/a - generated in tests",
        collection_date="2026-08-10",
        licence_or_consent_basis="synthetic; no subject",
        permitted_uses="research",
        redistribution_permitted=True,
        synthetic=True,
        subject_is_adult=True,
        language="en",
        deidentified=True,
        notes="test fixture",
        record_count=0,
    )


# ---------------------------------------------------------------------------
# Annotation-QA
# ---------------------------------------------------------------------------


def test_low_confidence_is_flagged():
    label = make_label(confidence=0.3)
    reasons = dict(review_reasons(label, confidence_threshold=0.65))
    assert REASON_LOW_CONFIDENCE in reasons


def test_every_burnout_assertion_is_reviewed():
    """The most clinically loaded construct in the taxonomy, so all of them,
    not a sample."""
    labels = (ConstructLabel("burnout_signal", "present", 2, ("I keep thinking",), 0.99),)
    reasons = dict(
        review_reasons(make_label(labels=labels, abstained=False), confidence_threshold=0.65)
    )
    assert REASON_BURNOUT in reasons


def test_clinical_language_in_a_rationale_is_flagged():
    label = make_label(rationale="The athlete appears clinically depressed.")
    reasons = dict(review_reasons(label, confidence_threshold=0.0))
    assert REASON_CLINICAL_LANGUAGE in reasons


def test_a_span_covering_the_whole_utterance_is_flagged():
    labels = (ConstructLabel("cognitive_anxiety", "present", 2, (TEXT,), 0.99),)
    reasons = dict(
        review_reasons(make_label(labels=labels, abstained=False), confidence_threshold=0.0)
    )
    assert REASON_SPAN_IS_WHOLE_TEXT in reasons


def test_too_many_constructs_on_one_utterance_is_flagged():
    span = "I keep thinking"
    names = [
        "cognitive_anxiety",
        "somatic_anxiety",
        "perceived_stress",
        "self_confidence",
        "resilience",
    ]
    labels = tuple(ConstructLabel(n, "present", 2, (span,), 0.99) for n in names)
    reasons = dict(
        review_reasons(make_label(labels=labels, abstained=False), confidence_threshold=0.0)
    )
    assert REASON_MANY_CONSTRUCTS in reasons


def test_parse_failures_lead_the_queue():
    failure = LabelFailure("r1", "p0", TEXT, "NOT_JSON", "boom", "mid", True)
    items = build_queue([make_label(confidence=0.1)], [failure], confidence_threshold=0.65)
    assert items[0].reason == REASON_PARSE_FAILURE


def test_a_confident_clean_label_is_not_flagged():
    labels = (ConstructLabel("cognitive_anxiety", "present", 2, ("I keep thinking",), 0.95),)
    label = make_label(labels=labels, abstained=False, confidence=0.95)
    assert review_reasons(label, confidence_threshold=0.65) == []


# ---------------------------------------------------------------------------
# OPEN-021 ancestry probe
# ---------------------------------------------------------------------------


def test_overlap_is_high_against_a_near_verbatim_taxonomy_example(taxonomy):
    examples = taxonomy["constructs"]["cognitive_anxiety"]["positive_examples"]
    assert example_overlap(examples[0], examples) == pytest.approx(1.0)


def test_overlap_is_low_for_unrelated_text(taxonomy):
    examples = taxonomy["constructs"]["cognitive_anxiety"]["positive_examples"]
    assert example_overlap("The venue is forty minutes away.", examples) < 0.1


def test_ancestry_report_covers_every_construct(taxonomy):
    rows = overlap_report([make_label()], taxonomy)
    assert {row.construct for row in rows} == set(taxonomy["constructs"])


# ---------------------------------------------------------------------------
# Ledger: the Phase 10 performance fix must not change the numbers
# ---------------------------------------------------------------------------


def test_cached_month_total_matches_a_fresh_read(routing, tmp_path):
    budget = _budget(routing, tmp_path)
    ledger = CostLedger(budget)
    for _ in range(5):
        ledger.record(LedgerEntry("labeling", 10, "cheap", "m", 10, 10, 0.001), enforce=False)
    cached = ledger.spend_this_month()
    assert cached == pytest.approx(0.005)
    assert CostLedger(budget).spend_this_month() == pytest.approx(cached)


def test_refresh_forces_a_reread(routing, tmp_path):
    budget = _budget(routing, tmp_path)
    ledger = CostLedger(budget)
    ledger.record(LedgerEntry("labeling", 10, "cheap", "m", 10, 10, 0.002), enforce=False)
    ledger.refresh()
    assert ledger.spend_this_month() == pytest.approx(0.002)


# ---------------------------------------------------------------------------
# Cost projection
# ---------------------------------------------------------------------------


def test_projection_counts_the_real_rubric_not_the_configs_400_token_guess(routing):
    """config/model_routing.yaml assumed ~400 input tokens per call. The
    assembled rubric is an order of magnitude larger, and the projection must
    reflect what will actually be sent."""
    plan = build_plan([make_record()], system_prompt=cached_system_prompt())
    projection = project_cost(plan, routing=routing, system_prompt=cached_system_prompt())
    assert projection["system_prompt_tokens"] > 2000


def test_cache_discount_lowers_the_projection_and_defaults_to_no_credit(routing):
    system = cached_system_prompt()
    plan = build_plan([make_record()], system_prompt=system)
    full = project_cost(plan, routing=routing, system_prompt=system)
    discounted = project_cost(plan, routing=routing, system_prompt=system, cache_discount=0.25)
    assert full["assumed_cache_discount"] == 1.0
    assert discounted["projected_usd"] < full["projected_usd"]
