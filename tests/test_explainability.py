"""Phase 17 tests.

None of these need torch. `src/explainability/attribution.py` imports the ML
stack lazily and the data model is pure Python, so every invariant that matters
here -- offset handling, span merging, faithfulness arithmetic, blinding,
kappa -- is testable against hand-built attributions and a stub scorer.

That is deliberate and it is the reason the module is shaped this way. A test
suite that needed a 300 MB checkpoint and five minutes of CPU would be run once
and then skipped, and the invariants below are exactly the ones that break
silently.
"""

from __future__ import annotations

import pytest

from src.explainability.attribution import (
    ConstructExplanation,
    RecordExplanation,
    SpanAttribution,
    TokenAttribution,
    merge_into_spans,
    word_spans,
)
from src.explainability.cards import (
    PublicationUnsafe,
    assert_publication_safe,
    build_card,
    highlight,
    render_markdown,
)
from src.explainability.faithfulness import (
    align_to_words,
    compare_methods,
    score_record,
    spearman,
    summarise,
    top_k_jaccard,
)
from src.explainability.study import ITEM_TYPES, analyse, build_sheet, cohens_kappa
from src.models.dataset import CONSTRUCTS
from src.risk.fusion import LinearRiskScorer

TEXT = "my hands wont stop shaking before the race"


def tokens_for(text: str, scores: dict[str, float]) -> tuple[TokenAttribution, ...]:
    out = []
    cursor = 0
    for word in text.split():
        start = text.index(word, cursor)
        out.append(
            TokenAttribution(
                token=word, start=start, end=start + len(word), score=scores.get(word, 0.0)
            )
        )
        cursor = start + len(word)
    return tuple(out)


# ---------------------------------------------------------------------------
# Spans and offsets -- the "span-level" half of the Phase 17 gate
# ---------------------------------------------------------------------------


def test_subword_tokens_merge_into_one_word():
    """`shak` + `ing` is one span, and its score is the sum of the pieces."""
    toks = (
        TokenAttribution("shak", 19, 23, 0.6),
        TokenAttribution("ing", 23, 26, 0.4),
    )
    spans = merge_into_spans(toks, source_text=TEXT)
    assert len(spans) == 1
    assert spans[0].text == "shaking"
    assert spans[0].score == pytest.approx(1.0)


def test_spans_of_opposite_sign_are_not_merged():
    """Merging them would cancel two strong opposing effects into a small
    number, reporting 'nothing happened here' for the most active region."""
    toks = (
        TokenAttribution("good", 0, 4, 1.0),
        TokenAttribution("bad", 5, 8, -1.0),
    )
    assert len(merge_into_spans(toks, source_text="good bad")) == 2


def test_special_tokens_are_dropped_not_placed_at_zero():
    """CLS/SEP have offset (0,0). Keeping them would put a phantom span at
    character 0 of every record, and it would frequently rank first."""
    toks = (
        TokenAttribution("<s>", 0, 0, 5.0),
        TokenAttribution("my", 0, 2, 0.1),
    )
    spans = merge_into_spans(toks, source_text=TEXT)
    assert len(spans) == 1
    assert spans[0].text == "my"


def test_span_text_is_a_real_substring_of_the_record():
    """Regression: without `source_text`, spans were rebuilt by concatenating
    token strings and lost the whitespace -- producing `shakingbefore`, which
    would go straight onto a rating sheet."""
    explanation = ConstructExplanation(
        construct="somatic_anxiety",
        probability=0.8,
        method="integrated_gradients",
        tokens=tokens_for(TEXT, {"shaking": 0.9, "hands": 0.8}),
        source_text=TEXT,
    )
    for span in explanation.top_spans():
        assert span.text == TEXT[span.start : span.end]
        assert span.text in TEXT


# ---------------------------------------------------------------------------
# Faithfulness arithmetic
# ---------------------------------------------------------------------------


def test_align_to_words_sums_subwords_and_keeps_length():
    scores = align_to_words(
        TEXT,
        (
            TokenAttribution("shak", 19, 23, 0.6),
            TokenAttribution("ing", 23, 26, 0.4),
        ),
    )
    assert len(scores) == len(word_spans(TEXT))
    assert scores[4] == pytest.approx(1.0)


def test_a_correct_explanation_beats_its_random_control():
    """The end-to-end sanity check for the whole faithfulness story.

    The stub model's probability depends only on two 'signal' words. An
    attribution that points at exactly those words must beat a random control
    on both metrics; if this ever fails, the metric is wired backwards.
    """
    signal = {"hands", "shaking"}

    def predict(texts):
        return [[len(set(t.lower().split()) & signal) / len(signal)] for t in texts]

    score = score_record(
        record_id="r1",
        text=TEXT,
        construct="somatic_anxiety",
        construct_index=0,
        method="ig",
        tokens=tokens_for(TEXT, {"hands": 0.9, "shaking": 0.9}),
        predict_fn=predict,
    )
    assert score is not None
    assert score.comprehensiveness_margin > 0
    assert score.sufficiency_margin > 0
    assert summarise([score])["overall"]["beats_random"] is True


def test_a_misleading_explanation_does_not_beat_random():
    """The negative control on the metric itself. An attribution pointing at
    words the model provably ignores must not look faithful."""
    signal = {"hands", "shaking"}

    def predict(texts):
        return [[len(set(t.lower().split()) & signal) / len(signal)] for t in texts]

    score = score_record(
        record_id="r1",
        text=TEXT,
        construct="somatic_anxiety",
        construct_index=0,
        method="ig",
        tokens=tokens_for(TEXT, {"the": 0.9, "before": 0.9, "race": 0.8}),
        predict_fn=predict,
    )
    assert score is not None
    assert score.comprehensiveness_margin <= 0


def test_spearman_and_jaccard_edges():
    assert spearman([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)
    assert spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    # A constant series has no ordering: None, not 0.0. Reporting 0.0 would say
    # "the methods disagree" for what is "there was nothing to agree about".
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert top_k_jaccard([3, 2, 1], [3, 2, 1], k=2) == pytest.approx(1.0)


def test_compare_methods_aligns_before_correlating():
    """IG is subword and SHAP is word-level; a correct comparison aligns both
    onto words first. Identical evidence expressed at different granularities
    must correlate at 1.0."""
    ig = (
        TokenAttribution("shak", 19, 23, 0.5),
        TokenAttribution("ing", 23, 26, 0.5),
        TokenAttribution("the", 34, 37, -0.2),
    )
    shap = (
        TokenAttribution("shaking", 19, 26, 1.0),
        TokenAttribution("the", 34, 37, -0.2),
    )
    result = compare_methods(
        record_id="r1", text=TEXT, construct="somatic_anxiety", ig_tokens=ig, shap_tokens=shap
    )
    assert result.spearman == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def _explanation(record_id: str = "r1") -> RecordExplanation:
    return RecordExplanation(
        record_id=record_id,
        text=TEXT,
        method="integrated_gradients",
        explanations=tuple(
            ConstructExplanation(
                construct=c,
                probability=0.7,
                method="integrated_gradients",
                tokens=tokens_for(TEXT, {"shaking": 0.9}),
                source_text=TEXT,
            )
            for c in CONSTRUCTS[:3]
        ),
    )


def test_card_joins_on_construct_name_not_position():
    """`RiskScore.contributions` is sorted by name; `RecordExplanation` is in
    taxonomy order. Zipping would pair each construct's risk with another
    construct's spans, and every field would still be populated."""
    risk = LinearRiskScorer().score(dict.fromkeys(CONSTRUCTS, 0.7))
    card = build_card(explanation=_explanation(), risk=risk, synthetic=True)
    for row in card.evidence:
        if row.spans:
            assert row.contribution.construct in {e.construct for e in _explanation().explanations}
    named = {r.contribution.construct for r in card.evidence if r.spans}
    assert named == set(CONSTRUCTS[:3])


def test_card_requires_provenance():
    risk = LinearRiskScorer().score(dict.fromkeys(CONSTRUCTS, 0.5))
    explanation = RecordExplanation(
        record_id="r1", text=TEXT, method="ig", explanations=(), provenance="   "
    )
    with pytest.raises(ValueError):
        build_card(explanation=explanation, risk=risk, synthetic=True)


def test_non_synthetic_text_cannot_be_published_verbatim():
    """Today a no-op -- every record is synthetic. It stops being a no-op in the
    week real A3 donated text first lands, which is the week the mistake is
    most likely."""
    risk = LinearRiskScorer().score(dict.fromkeys(CONSTRUCTS, 0.5))
    card = build_card(explanation=_explanation(), risk=risk, synthetic=False)
    with pytest.raises(PublicationUnsafe):
        assert_publication_safe([card])


def test_redacted_render_omits_the_record_text():
    risk = LinearRiskScorer().score(dict.fromkeys(CONSTRUCTS, 0.7))
    card = build_card(explanation=_explanation(), risk=risk, synthetic=True)
    # "wont stop" is unattributed filler: it appears in the full render (which
    # prints the record with the spans marked up) and must not appear in the
    # redacted one (which prints spans only). Checking a fragment rather than
    # the whole string because `highlight` inserts `**` markers, so the record
    # is no longer a contiguous substring of its own rendering.
    assert "wont stop" not in render_markdown(card, redact=True)
    assert "wont stop" in render_markdown(card, redact=False)


def test_zero_scored_tokens_do_not_weld_a_record_into_one_span():
    """Regression, and the bug was sharper than it looked.

    Zero is non-negative, so under the same-sign rule alone a zero-scored token
    sat between two positive ones and joined them. A record whose attributions
    were mostly zero therefore merged into a single span covering the entire
    text -- which highlights everything (so explains nothing) and silently
    defeated the redaction guard, because 'show only the spans' then showed the
    whole record.
    """
    toks = tokens_for(TEXT, {"hands": 0.8, "race": 0.5})
    spans = merge_into_spans(toks, source_text=TEXT)
    assert {s.text for s in spans} == {"hands", "race"}
    assert all(s.end - s.start < len(TEXT) for s in spans)


def test_redaction_suppresses_spans_that_cover_the_whole_record():
    """The second half of the same defect: even with genuinely non-zero scores,
    a diffuse attribution can span the record. Redaction must not leak it."""
    explanation = RecordExplanation(
        record_id="r1",
        text=TEXT,
        method="integrated_gradients",
        explanations=(
            # A non-polar construct. Polar constructs (appraisal_orientation,
            # attentional_focus, ...) contribute exactly 0 without a resolved
            # sub-label, so they are not `drivers` and never reach the evidence
            # table -- which would make this test pass vacuously.
            ConstructExplanation(
                construct="cognitive_anxiety",
                probability=0.9,
                method="integrated_gradients",
                tokens=tokens_for(TEXT, dict.fromkeys(TEXT.split(), 0.4)),
                source_text=TEXT,
            ),
        ),
    )
    risk = LinearRiskScorer().score(dict.fromkeys(CONSTRUCTS, 0.7))
    card = build_card(explanation=explanation, risk=risk, synthetic=True)
    rendered = render_markdown(card, redact=True)
    assert TEXT not in rendered
    assert "suppressed" in rendered


def test_highlight_merges_overlaps_instead_of_nesting():
    spans = [
        SpanAttribution("my hands", 0, 8, 1.0, 2),
        SpanAttribution("hands wont", 3, 13, 1.0, 2),
    ]
    assert highlight(TEXT, spans).count("**") == 2


# ---------------------------------------------------------------------------
# Expert study
# ---------------------------------------------------------------------------


def _sheet(n: int = 12):
    explanations = [
        RecordExplanation(
            record_id=f"r{i}",
            text=TEXT,
            method="integrated_gradients",
            explanations=tuple(
                ConstructExplanation(
                    construct=c,
                    probability=0.7,
                    method="integrated_gradients",
                    tokens=tokens_for(TEXT, {"shaking": 0.9, "hands": 0.5}),
                    source_text=TEXT,
                )
                for c in CONSTRUCTS[:4]
            ),
        )
        for i in range(8)
    ]
    return build_sheet(
        explanations,
        rater_population="test raters",
        construct_definitions={c: "..." for c in CONSTRUCTS[:4]},
        n_model_items=n,
        seed=7,
    )


def test_the_sheet_never_leaks_the_item_type():
    """The blinding. If a rater can see which items are controls, the control
    margin measures nothing."""
    rendered = _sheet().render()
    for item_type in ITEM_TYPES:
        assert item_type not in rendered
    assert "item_type" not in rendered


def test_the_key_carries_all_three_item_types():
    key = _sheet().answer_key()
    assert set(key["counts_by_type"]) == set(ITEM_TYPES)
    assert all(count > 0 for count in key["counts_by_type"].values())


def test_a_discriminating_rater_passes_control_and_attention_checks():
    sheet = _sheet()
    ratings = [
        {
            i.item_id: {"model": "yes", "random_span": "no", "mismatched": "no"}[i.item_type]
            for i in sheet.items
        }
    ]
    result = analyse(sheet, ratings)
    assert result.passes_control is True
    assert result.passes_attention_check is True
    assert result.control_margin == pytest.approx(1.0)


def test_an_indiscriminate_rater_fails_the_control():
    """A rater who approves everything produces a 100% approval rate. Without
    the control that reads as a triumph."""
    sheet = _sheet()
    ratings = [{i.item_id: "yes" for i in sheet.items}]
    result = analyse(sheet, ratings)
    assert result.approval_by_type["model"] == pytest.approx(1.0)
    assert result.passes_control is False
    assert result.passes_attention_check is False


def test_kappa_matches_a_hand_computed_value():
    a = ["yes", "yes", "no", "partly", "no"]
    b = ["yes", "no", "no", "partly", "no"]
    # observed = 4/5 = 0.8
    # expected = (2/5)(1/5) + (1/5)(1/5) + (2/5)(3/5) = 0.08 + 0.04 + 0.24 = 0.36
    # kappa = (0.8 - 0.36) / (1 - 0.36) = 0.6875
    assert cohens_kappa(a, b) == pytest.approx(0.6875)


def test_kappa_is_none_when_undefined_rather_than_zero():
    """Both raters used one category throughout: expected agreement is 1.0.
    Reporting 0.0 would say 'no agreement beyond chance' about raters who
    agreed on every single item."""
    assert cohens_kappa(["yes"] * 6, ["yes"] * 6) is None


def test_control_spans_are_length_matched_to_the_model_spans():
    """Otherwise the control differs in content *and* length, and lower rater
    approval could be explained by either."""
    sheet = _sheet()
    model_lengths = {len(i.span_text.split()) for i in sheet.items if i.item_type == "model"}
    control_lengths = {
        len(i.span_text.split()) for i in sheet.items if i.item_type == "random_span"
    }
    assert control_lengths <= model_lengths
