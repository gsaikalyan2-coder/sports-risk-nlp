"""Tests for the Phase 9 profile and gold-set sampling plan.

The rule these tests are written to
------------------------------------
Every number that reaches `reports/eda.md` is a number a reviewer may check, so
each one is either computed by a function tested here or is a direct read of a
tested function's output. Tests that assert a *property* (a rate is in [0, 1],
a partition is disjoint) outnumber tests that assert a *value*, because a value
test on this corpus breaks on every regeneration and the temptation is then to
rewrite it to match rather than investigate -- the failure mode
`phase9_handover.md` §B5 warns about.

The exceptions are the fixed-corpus assertions at the end. Those pin the numbers
`reports/eda.md` quotes as headline findings, and they are *meant* to fail loudly
on regeneration, because the report is then stale. **They have already done their
job once:** resolving OPEN-016 and OPEN-017 regenerated the corpus at v1.3 with
4,000 records, all three failed, and the report and the assertions were updated
together in the same change -- which is the whole point of having them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation import figures
from src.evaluation.profile import (
    MIN_ANNOTATABLE_TOKENS,
    PLACEHOLDER_TOKEN_RE,
    describe,
    duplicate_profile,
    generator_metadata_profile,
    group_by_parent,
    histogram,
    junk_flags,
    junk_profile,
    load_interim,
    mattr,
    profile_corpus,
    time_band,
    tokenise,
    vocabulary,
)
from src.evaluation.sampling import (
    GOLD_TEMPLATE_HOLDOUT,
    MIN_POSITIVES_PER_CONSTRUCT,
    build_plan,
    construct_stratified_template_partition,
    draw_gold_sample,
    eligible_utterances,
    templates_by_construct,
    write_candidates,
)
from src.ingestion.substitution_verdicts import is_defective
from src.preprocessing.records import InterimRecord

SOURCE = "synth_precomp_v1"


def _record(record_id: str, text: str, **kwargs) -> InterimRecord:
    defaults = {
        "source_id": SOURCE,
        "parent_record_id": record_id.split("#")[0],
        "utterance_index": 0,
        "char_start": 0,
        "char_end": len(text),
        "sport": "tennis",
        "competition_level": "club",
        "region": "europe",
        "source_type": "synthetic",
        "time_to_competition_days": 1,
        "synthetic": True,
    }
    defaults.update(kwargs)
    return InterimRecord(record_id=record_id, text=text, **defaults)


@pytest.fixture(scope="module")
def corpus() -> list[InterimRecord]:
    return load_interim(SOURCE)


@pytest.fixture(scope="module")
def profile(corpus):
    return profile_corpus(corpus, SOURCE)


@pytest.fixture(scope="module")
def plan(corpus):
    return build_plan(corpus, SOURCE)


# ---------------------------------------------------------------------------
# Tokenisation and placeholders
# ---------------------------------------------------------------------------


def test_placeholders_are_single_tokens():
    tokens = tokenise("I spoke to [ATHLETE] about [EVENT_WINDOW] plans.")
    assert "[ATHLETE]" in tokens
    assert "[EVENT_WINDOW]" in tokens
    assert "athlete" not in tokens


def test_placeholders_can_be_excluded_not_lowercased():
    """Dropping is not the same as lowercasing, and the difference is a bug.

    Lowercasing `[COACH]` into `coach` would merge a privacy artefact with the
    real word and inflate that word's frequency. The parameter drops them.
    """
    tokens = tokenise("[COACH] said the coach was pleased.", keep_placeholders=False)
    assert tokens.count("coach") == 1


def test_placeholder_regex_does_not_match_ordinary_brackets():
    assert not PLACEHOLDER_TOKEN_RE.search("a [note] in brackets")
    assert PLACEHOLDER_TOKEN_RE.search("a [NOTE] in brackets")


# ---------------------------------------------------------------------------
# MATTR -- the measure the report leans on
# ---------------------------------------------------------------------------


def test_mattr_is_a_ratio():
    assert 0.0 <= mattr(["a"] * 200, window=50) <= 1.0
    assert 0.0 <= mattr([str(i) for i in range(200)], window=50) <= 1.0


def test_mattr_of_all_distinct_tokens_is_one():
    assert mattr([str(i) for i in range(500)], window=50) == pytest.approx(1.0)


def test_mattr_of_a_single_repeated_token_is_the_window_reciprocal():
    assert mattr(["x"] * 500, window=50) == pytest.approx(1 / 50)


def test_mattr_is_insensitive_to_length_where_raw_ttr_is_not():
    """The whole reason MATTR is the headline figure.

    Doubling a text by repeating it leaves lexical richness unchanged. Raw TTR
    halves; MATTR does not move. If this test ever fails, §2 of `reports/eda.md`
    is making a claim the code no longer supports.
    """
    short = [str(i % 40) for i in range(400)]
    long = short * 4
    ttr_short = len(set(short)) / len(short)
    ttr_long = len(set(long)) / len(long)
    assert ttr_long < ttr_short / 2 + 0.01
    assert mattr(long, window=50) == pytest.approx(mattr(short, window=50), abs=0.02)


def test_vocabulary_counts_types_and_tokens_consistently():
    stats = vocabulary(["the cat sat", "the cat sat on the mat"])
    assert stats.tokens == 9
    assert stats.types == 5
    assert stats.ttr == pytest.approx(5 / 9)


# ---------------------------------------------------------------------------
# Distributions
# ---------------------------------------------------------------------------


def test_describe_matches_hand_computed_summary():
    dist = describe([1.0, 2.0, 3.0, 4.0], "unit")
    assert dist.n == 4
    assert dist.mean == pytest.approx(2.5)
    assert dist.minimum == 1.0
    assert dist.maximum == 4.0
    assert dist.median == 2.0


def test_describe_ci_brackets_the_point_estimate():
    dist = describe([float(i) for i in range(200)], "unit")
    assert dist.mean_ci.low <= dist.mean <= dist.mean_ci.high


def test_describe_is_deterministic():
    values = [float(i % 17) for i in range(500)]
    assert describe(values, "u").mean_ci == describe(values, "u").mean_ci


def test_describe_handles_the_empty_case():
    dist = describe([], "u")
    assert dist.n == 0 and dist.mean == 0.0


def test_histogram_bins_cover_every_value():
    values = [float(i) for i in range(100)]
    assert sum(count for _, _, count in histogram(values, bins=10)) == 100


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------


def test_exact_duplicate_counts_include_the_first_occurrence():
    """`n - distinct` is the wrong count and this pins the right one."""
    result = duplicate_profile(["a b c", "a b c", "d e f"], "u")
    assert result.distinct == 2
    assert result.exact_duplicate_items == 2


def test_near_duplicates_are_a_superset_of_exact_duplicates():
    texts = ["the race is tomorrow", "the race is tomorrow", "entirely unrelated words here"]
    result = duplicate_profile(texts, "u")
    assert result.near_duplicate_items >= result.exact_duplicate_items


def test_near_duplicate_detection_finds_a_one_word_difference():
    texts = [
        "i am nervous about the race tomorrow morning again",
        "i am nervous about the race tomorrow morning too",
        "completely different sentence with no shared content",
    ]
    result = duplicate_profile(texts, "u", threshold=0.8)
    assert result.near_duplicate_items == 2


def test_duplicate_rates_are_probabilities(profile):
    for report in (profile.utterance_duplicates, profile.record_duplicates):
        assert 0.0 <= report.exact_duplicate_rate_ci.point <= 1.0
        assert report.exact_duplicate_rate_ci.low <= report.exact_duplicate_rate_ci.point
        assert report.exact_duplicate_rate_ci.point <= report.exact_duplicate_rate_ci.high


# ---------------------------------------------------------------------------
# Junk
# ---------------------------------------------------------------------------


def test_short_utterances_are_flagged():
    assert "too_short" in junk_flags("That's it.")
    assert "too_short" not in junk_flags("I am feeling reasonably calm about tomorrow.")


def test_min_annotatable_tokens_is_the_threshold_actually_used():
    text = " ".join(["word"] * (MIN_ANNOTATABLE_TOKENS - 1)) + "."
    assert "too_short" in junk_flags(text)
    text = " ".join(["word"] * MIN_ANNOTATABLE_TOKENS) + "."
    assert "too_short" not in junk_flags(text)


def test_truncated_ending_is_detected():
    assert "truncated_ending" in junk_flags("I keep thinking about how this might")
    assert "truncated_ending" not in junk_flags("I keep thinking about how this might go.")


def test_repeated_token_run_is_detected():
    assert "repeated_token_run" in junk_flags("no no no i cannot do this.")


def test_junk_profile_rate_matches_the_flag_count():
    texts = ["That's it.", "I am feeling reasonably calm about tomorrow."]
    report = junk_profile(texts)
    assert report.flagged == 1
    assert report.flagged_rate_ci.point == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# generation_spec must stay fenced off
# ---------------------------------------------------------------------------


def test_generator_metadata_carries_its_warning():
    assert "NOT LABELS" in generator_metadata_profile([]).warning


def test_corpus_profile_exposes_constructs_only_via_generator_metadata(profile):
    """No attribute on `CorpusProfile` offers construct prevalence directly.

    This is the structural half of the "generation_spec is not a label" rule:
    a caller who wants those counts has to go through a type whose name says
    what they are.
    """
    for attribute in vars(profile):
        assert "construct" not in attribute, attribute
    assert profile.generator_metadata.planted_construct_records


def test_generation_spec_is_identical_across_a_records_utterances(corpus):
    """The replication trap, asserted rather than assumed.

    If this ever fails, `planted_construct_utterances` starts meaning something
    different and §7.4 of `reports/eda.md` needs rewriting.
    """
    for pieces in group_by_parent(corpus).values():
        specs = {json.dumps(p.generation_spec, sort_keys=True) for p in pieces}
        assert len(specs) == 1


# ---------------------------------------------------------------------------
# Time bands
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, "day_of"),
        (1, "eve"),
        (2, "eve"),
        (3, "final_week"),
        (7, "final_week"),
        (14, "taper"),
        (30, "build"),
        (None, "unknown"),
    ],
)
def test_time_bands(days, expected):
    assert time_band(days) == expected


# ---------------------------------------------------------------------------
# The gold sampling plan
# ---------------------------------------------------------------------------


def test_every_construct_gets_a_held_out_template(corpus):
    """The defect that motivated this module, as a regression test.

    `template_disjoint_split` at 20% leaves `appraisal_orientation` with no
    test-side records at all. The construct-stratified partition must not.
    """
    partition = construct_stratified_template_partition(corpus)
    assert partition.constructs_without_holdout == []
    assert set(partition.per_construct_holdout) == set(templates_by_construct(corpus))
    assert all(v >= 1 for v in partition.per_construct_holdout.values())


def test_the_template_partition_is_disjoint(plan):
    assert plan.partition.is_disjoint
    assert not (plan.partition.gold_templates & plan.partition.train_templates)


def test_gold_eval_and_gold_dev_share_no_parent_record(plan):
    assert not (set(plan.gold_eval.parent_record_ids) & set(plan.gold_dev.parent_record_ids))


def test_gold_eval_uses_only_held_out_templates(corpus, plan):
    index = {r.record_id: r for r in corpus}
    for utterance_id in plan.gold_eval.utterance_ids:
        used = {
            planted["template_id"]
            for planted in (index[utterance_id].generation_spec or {}).get("planted_constructs", ())
            if "template_id" in planted
        }
        assert used and used <= plan.partition.gold_templates


def test_gold_dev_uses_only_training_templates(corpus, plan):
    index = {r.record_id: r for r in corpus}
    for utterance_id in plan.gold_dev.utterance_ids:
        used = {
            planted["template_id"]
            for planted in (index[utterance_id].generation_spec or {}).get("planted_constructs", ())
            if "template_id" in planted
        }
        assert used and used <= plan.partition.train_templates


def test_the_plan_reports_itself_leakage_safe(plan):
    assert plan.is_leakage_safe


def test_the_gold_sample_contains_no_duplicate_text(corpus, plan):
    """The 73.6% duplication finding, enforced where it matters.

    Two annotators agreeing on the same string 268 times is one agreement, and a
    kappa that counted it 268 times would be inflated invisibly.
    """
    index = {r.record_id: r for r in corpus}
    texts = [" ".join(tokenise(index[i].text)) for i in plan.gold_eval.utterance_ids]
    assert len(set(texts)) == len(texts)


def test_the_gold_sample_contains_no_sub_annotatable_utterance(corpus, plan):
    index = {r.record_id: r for r in corpus}
    for utterance_id in plan.gold_eval.utterance_ids:
        assert "too_short" not in junk_flags(index[utterance_id].text)


def test_the_draw_is_deterministic(corpus):
    assert build_plan(corpus, SOURCE).gold_eval.utterance_ids == (
        build_plan(corpus, SOURCE).gold_eval.utterance_ids
    )


def test_a_different_seed_draws_a_different_sample(corpus):
    assert (
        build_plan(corpus, SOURCE, seed=42).gold_eval.utterance_ids
        != build_plan(corpus, SOURCE, seed=7).gold_eval.utterance_ids
    )


def test_the_holdout_fraction_moves_the_pool_size(corpus):
    small = build_plan(corpus, SOURCE, holdout_fraction=0.2)
    large = build_plan(corpus, SOURCE, holdout_fraction=0.5)
    assert large.gold_eval.size > small.gold_eval.size


def test_under_powered_constructs_are_reported_not_hidden(plan):
    """The sample is returned *with* its shortfall, never silently."""
    for construct in plan.gold_eval.constructs_below_floor:
        assert plan.gold_eval.construct_coverage[construct] < MIN_POSITIVES_PER_CONSTRUCT


def test_eligibility_numbers_add_up(corpus, plan):
    report = plan.gold_eval.eligibility
    assert report is not None
    assert (
        report.eligible
        + report.excluded_junk
        + report.excluded_duplicate
        + report.excluded_no_template
        == report.considered
    )


def test_eligible_pool_excludes_straddling_records(corpus):
    partition = construct_stratified_template_partition(corpus)
    pool, _report = eligible_utterances(corpus, partition.gold_templates)
    assert pool
    assert all(r.generation_spec for r in pool)


def test_draw_respects_the_target_size():
    records = [
        _record(f"r{i:03d}#u0", f"a sentence number {i} about the race tomorrow.")
        for i in range(50)
    ]
    sample = draw_gold_sample(records, target=10, name="t")
    assert sample.size == 10


def test_draw_cannot_exceed_the_pool():
    records = [_record(f"r{i}#u0", f"sentence {i} about tomorrow's race.") for i in range(5)]
    assert draw_gold_sample(records, target=100, name="t").size == 5


# ---------------------------------------------------------------------------
# Candidate writing
# ---------------------------------------------------------------------------


def test_candidates_never_carry_generation_spec(tmp_path, corpus, plan):
    """The independence guarantee a kappa rests on.

    Showing an annotator which construct the generator planted is the most
    direct possible way to destroy it.
    """
    for path in write_candidates(plan, corpus, root=tmp_path):
        if path.suffix == ".jsonl":
            for line in path.read_text(encoding="utf-8").splitlines():
                assert "generation_spec" not in line


def test_candidates_keep_parentage_for_provenance(tmp_path, corpus, plan):
    path = tmp_path / "data/processed/gold_candidates/gold_eval.jsonl"
    write_candidates(plan, corpus, root=tmp_path)
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        assert payload["parent_record_id"]
        assert payload["deidentified"] is True


def test_candidates_are_not_written_into_a_gold_root(tmp_path, corpus, plan):
    written = write_candidates(plan, corpus, root=tmp_path)
    for path in written:
        parts = path.resolve().parts
        assert "gold" not in parts, path


def test_the_written_plan_round_trips(tmp_path, corpus, plan):
    write_candidates(plan, corpus, root=tmp_path)
    payload = json.loads(
        (tmp_path / "data/processed/gold_candidates/sampling_plan.json").read_text("utf-8")
    )
    assert payload["leakage_safe"] is True
    assert payload["parameters"]["GOLD_TEMPLATE_HOLDOUT"] == GOLD_TEMPLATE_HOLDOUT
    assert payload["partition"]["constructs_without_holdout"] == []


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def test_figures_are_valid_standalone_svg(tmp_path):
    svg = figures.bar_chart(["a", "b"], [1.0, 2.0], "title")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    path = figures.write(tmp_path / "f.svg", svg)
    assert path.read_text("utf-8") == svg


def test_figure_labels_are_escaped():
    assert "&lt;script&gt;" in figures.bar_chart(["<script>"], [1.0], "t")


def test_figures_are_byte_stable():
    assert figures.bar_chart(["a"], [1.0], "t") == figures.bar_chart(["a"], [1.0], "t")


def test_figures_import_without_matplotlib():
    """The light-image constraint, asserted rather than trusted.

    Checks for an *import*, not for the word: the module docstring explains at
    length why matplotlib is not used, and a test that banned the word would
    have punished the explanation.
    """
    source = Path("src/evaluation/figures.py").read_text("utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        assert not stripped.startswith(("import matplotlib", "from matplotlib")), line


# ---------------------------------------------------------------------------
# Fixed-corpus assertions. These SHOULD fail if the corpus is regenerated --
# that is the alarm that `reports/eda.md` has gone stale (see OPEN-017).
# ---------------------------------------------------------------------------


def test_reported_corpus_size(profile):
    assert (profile.n_records, profile.n_utterances) == (4000, 13651)


def test_reported_duplicate_rate(profile):
    assert profile.utterance_duplicates.distinct == 3131
    assert profile.utterance_duplicates.exact_duplicate_items == 11929


def test_reported_gold_sample_size(plan):
    assert plan.gold_eval.size == 400
    assert plan.gold_dev.size == 100
    assert plan.gold_eval.constructs_below_floor == []


def test_the_corpus_contains_no_ruled_defective_substitution(corpus):
    """OPEN-016, as a standing guarantee rather than a one-off measurement.

    At v1.2 this was 190/1,200 records. The v1.3 guard in `_vary` makes it
    structurally zero, and this asserts the structure rather than trusting it.
    """
    offenders = [r.record_id for r in corpus if is_defective(r.text)]
    assert not offenders, f"{len(offenders)} utterances carry a ruled-defective frame"
