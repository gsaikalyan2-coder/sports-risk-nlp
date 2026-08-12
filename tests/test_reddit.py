"""Tests for the category A5 harvester.

Offline, deterministic, no network, no credentials, no spend -- the whole
filtering path is pure functions over dicts, which is why it was built that way.
OPEN-027 is the precedent: a parser that had never met its real input was broken
in three ways, one of which silently discarded evidence. Here the *network* edge
is one thin function and everything that makes a governance decision sits above
it, where it can be tested without a client.

The tests that carry the most weight are the ones asserting the C1 guarantee is
**structural**. `docs/ethics.md` §3.5 permits topic-scoped collection and
prohibits account-centred collection absolutely, and the module's defence is
that no author parameter exists anywhere. A test that merely checked "we do not
pass an author" would pass just as happily after someone added the parameter
back, so these tests inspect the signatures themselves.

The exclusion tests deliberately assert **over-inclusive** behaviour -- that an
adult writing about their child is dropped, that a passing mention of physio is
dropped. Those are false positives and they are the intended direction of error
(module docstring). A future session tempted to "fix" the recall loss should
have to delete an explicit test that says the loss is deliberate.
"""

from __future__ import annotations

import inspect

import pytest

from src.ingestion.reddit import (
    ALLOWED_POST_FIELDS,
    PERMITTED_COMMUNITIES,
    HarvestQuery,
    HarvestStats,
    a5_descriptor,
    days_to_competition,
    fetch_listing,
    fetch_listing_public,
    harvest,
    is_health_content,
    is_pre_competition,
    mentions_minor,
    minimise,
)

PRE_RACE = (
    "First marathon tomorrow and I cannot switch my brain off. I keep running "
    "through everything that could go wrong on the start line, whether I went "
    "out too hard in training, whether the taper was enough. Trying to remind "
    "myself I have done the work and just need to trust it on the day."
)


def _post(text: str, post_id: str = "abc123", **extra):
    return {"id": post_id, "subreddit": "running", "title": "", "selftext": text, **extra}


# ---------------------------------------------------------------------------
# C1 -- the structural guarantee
# ---------------------------------------------------------------------------


def test_harvest_query_has_no_author_field():
    """C1. A caller must not be able to *express* an account-centred request."""
    fields = set(HarvestQuery.__dataclass_fields__)
    assert not {"author", "user", "username", "redditor", "author_id"} & fields
    assert fields == {"subreddit", "query", "limit"}


@pytest.mark.parametrize("function", [harvest, fetch_listing, fetch_listing_public])
def test_no_entry_point_accepts_an_author(function):
    """C1, enforced against the signatures rather than against behaviour.

    Checking "we didn't pass an author" would still pass if the parameter were
    reinstated. Checking that the parameter does not exist fails the moment it
    comes back.
    """
    parameters = set(inspect.signature(function).parameters)
    assert not {"author", "user", "username", "redditor", "author_id"} & parameters


def test_a_community_outside_the_permitted_list_is_refused(tmp_path):
    with pytest.raises(ValueError, match="PERMITTED_COMMUNITIES"):
        HarvestQuery(subreddit="AskReddit")


def test_harvest_refuses_an_unpermitted_community_and_logs_it(tmp_path):
    log = tmp_path / "refusals.log"
    records = list(harvest([_post(PRE_RACE)], source_id="s", subreddit="AskReddit", log_path=log))
    assert records == []
    assert "A5_COMMUNITY_NOT_PERMITTED" in log.read_text(encoding="utf-8")


def test_no_permitted_community_is_youth_scoped():
    """P2 stands under A5. The strongest minor protection is not collecting from
    a youth community at all, rather than filtering ages afterwards."""
    for community in PERMITTED_COMMUNITIES:
        lowered = community.lower()
        assert not any(marker in lowered for marker in ("school", "teen", "youth", "junior", "kid"))


# ---------------------------------------------------------------------------
# C11 -- data minimisation
# ---------------------------------------------------------------------------


def test_minimise_drops_author_and_every_unlisted_field():
    post = {
        "id": "x",
        "subreddit": "running",
        "title": "t",
        "selftext": "s",
        "created_utc": 1,
        "over_18": False,
        "author": "some_user",
        "author_fullname": "t2_abc",
        "link_karma": 900,
        "awards": [],
        "crosspost_parent": "t3_z",
    }
    kept = minimise(post)
    assert set(kept) <= ALLOWED_POST_FIELDS
    assert "author" not in kept
    assert not any("author" in k or "karma" in k for k in kept)


def test_minimise_is_a_whitelist_so_new_api_fields_are_excluded_by_default():
    kept = minimise({"id": "x", "some_field_reddit_adds_in_2027": "surprise"})
    assert "some_field_reddit_adds_in_2027" not in kept


def test_harvested_records_carry_no_author_information():
    records = list(
        harvest([_post(PRE_RACE, author="runner_99")], source_id="s", subreddit="running")
    )
    assert len(records) == 1
    assert "runner_99" not in records[0].text
    assert "runner_99" not in records[0].record_id


def test_record_id_does_not_expose_the_post_id():
    """C10. The post id is a direct handle back to the account, so records carry
    a digest and the mapping stays in provenance."""
    records = list(
        harvest([_post(PRE_RACE, post_id="t3_secret")], source_id="s", subreddit="running")
    )
    assert "t3_secret" not in records[0].record_id


# ---------------------------------------------------------------------------
# C3 / P2 -- minors, over-inclusive by design
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I'm 16 and my first big meet is tomorrow, so nervous about the start line",
        "high school regionals this weekend and I can't stop thinking about it",
        "16f, first race tomorrow, terrified about going out too fast",
        "my u18 team races next week and I'm anxious about it",
    ],
)
def test_minor_signals_are_caught(text):
    assert mentions_minor(text) is not None


def test_an_adult_writing_about_a_child_is_also_dropped():
    """A deliberate false positive. Documented in the module docstring: the
    asymmetry between the two errors is not close, so the threshold is not
    balanced."""
    assert mentions_minor("my kid's high school meet is tomorrow, I'm more nervous than her")


def test_numbers_that_are_not_ages_do_not_trigger_the_age_filter():
    assert mentions_minor("I'm 5 minutes off my PB and the race is tomorrow") is None
    assert mentions_minor("I am 34 and racing this weekend") is None


# ---------------------------------------------------------------------------
# C4 / P6 -- health content
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "my anxiety disorder always flares before a race",
        "coming back from a stress fracture, race is tomorrow",
        "physio cleared me last week, racing this weekend",
        "started an SSRI last month and race day is tomorrow",
        "recovering from an eating disorder, first race tomorrow",
    ],
)
def test_health_content_is_excluded(text):
    assert is_health_content(text) is not None


def test_ordinary_pre_race_nerves_are_not_health_content():
    """The boundary A5 depends on. Nerves are the target construct; a disclosed
    clinical condition is special-category data."""
    assert is_health_content(PRE_RACE) is None
    assert is_health_content("so nervous about tomorrow, stomach is in knots") is None


# ---------------------------------------------------------------------------
# Scope -- anticipatory, not a race report
# ---------------------------------------------------------------------------


def test_anticipatory_posts_are_in_scope():
    assert is_pre_competition(PRE_RACE)


def test_race_reports_are_out_of_scope():
    """The exact failure that disqualified all four Phase 7 candidates."""
    assert not is_pre_competition("Race report: finished in 3:12, went out too hard")
    assert not is_pre_competition(
        "Yesterday's race was rough, I crossed the line and immediately felt sick"
    )


def test_a_race_report_that_mentions_tomorrow_is_still_out_of_scope():
    assert not is_pre_competition(
        "Race report: I PR'd. Already thinking about tomorrow's recovery run."
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("race is tomorrow", 1),
        ("night before my first marathon", 1),
        ("racing this weekend", 3),
        ("meet is next week", 7),
        ("10 days out from the race", 10),
        ("sometime later in the season", None),
    ],
)
def test_days_to_competition(text, expected):
    assert days_to_competition(text) == expected


def test_days_to_competition_returns_none_rather_than_guessing():
    """The value feeds Phase 15's risk fusion as a context feature. An invented
    number would be indistinguishable there from a measured one."""
    assert days_to_competition("I have a race coming up at some point") is None


# ---------------------------------------------------------------------------
# Harvest behaviour
# ---------------------------------------------------------------------------


def test_a_clean_pre_race_post_is_kept_with_the_right_metadata():
    stats = HarvestStats()
    records = list(
        harvest([_post(PRE_RACE)], source_id="reddit_v1", subreddit="running", stats=stats)
    )
    assert len(records) == 1
    record = records[0]
    assert record.synthetic is False
    assert record.deidentified is False, "C5: only the Phase 8 pass may flip this"
    assert record.source_type == "social"
    assert record.sport == "running"
    assert record.time_to_competition_days == 1
    assert stats.kept == 1 and stats.seen == 1


def test_every_drop_is_logged_with_the_cue_that_matched(tmp_path):
    """A refusal log that only says 'health content' cannot be audited for false
    positives, so the matching cue is recorded."""
    log = tmp_path / "refusals.log"
    list(
        harvest(
            [_post("Coming back from a stress fracture, my race is tomorrow and I'm nervous " * 3)],
            source_id="s",
            subreddit="running",
            log_path=log,
        )
    )
    contents = log.read_text(encoding="utf-8")
    assert "A5_HEALTH_CONTENT" in contents
    # The logged cue is whichever matched first in HEALTH_CUES -- 'fracture'
    # precedes 'stress fracture'. Which one it names does not matter; that it
    # names one at all is the point, since a bare "health content" verdict
    # cannot be audited for false positives.
    assert "fracture" in contents


def test_nsfw_and_too_short_posts_are_dropped():
    stats = HarvestStats()
    posts = [
        _post(PRE_RACE, post_id="a", over_18=True),
        _post("race tomorrow, nervous", post_id="b"),
        _post(PRE_RACE, post_id="c"),
    ]
    records = list(harvest(posts, source_id="s", subreddit="running", stats=stats))
    assert len(records) == 1
    assert stats.dropped.get("A5_NSFW") == 1
    assert stats.dropped.get("A5_TOO_SHORT") == 1


def test_a_post_without_an_id_is_refused_for_incomplete_provenance():
    stats = HarvestStats()
    records = list(
        harvest([{"selftext": PRE_RACE, "id": ""}], source_id="s", subreddit="running", stats=stats)
    )
    assert records == []
    assert stats.dropped.get("A5_NO_POST_ID") == 1


def test_harvest_has_no_bypass_parameter():
    """The allow-list's enforcement contract: never add a bypass flag to this
    checking path."""
    parameters = set(inspect.signature(harvest).parameters)
    assert not {"force", "strict", "skip_checks", "allow_all", "unsafe"} & parameters


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_the_a5_descriptor_makes_every_required_declaration():
    from src.ingestion.allowlist import REQUIRED_DECLARATIONS

    descriptor = a5_descriptor("reddit_running_v1", "running")
    assert set(descriptor.declares) == set(REQUIRED_DECLARATIONS)
    assert all(descriptor.declares.values())


def test_the_a5_descriptor_passes_the_allowlist_check():
    from src.ingestion.allowlist import check_source, load_allowlist

    category = check_source(a5_descriptor("reddit_running_v1", "running"), load_allowlist())
    assert category.is_permitted


def test_the_descriptor_records_that_authors_did_not_consent():
    """§3.5.2 is the paragraph a reviewer will look for. The provenance file
    should not imply a consent basis the project does not have."""
    basis = a5_descriptor("reddit_running_v1", "running").licence_or_consent_basis.lower()
    assert "not consented" in basis
    assert "§3.5.2" in basis or "3.5.2" in basis


def test_competition_level_is_left_null_rather_than_guessed():
    """A forum post does not state its author's competition level, and
    COMPETITION_LEVELS has no 'amateur' tier. Mapping the population onto 'club'
    because it is the lowest available option would put an invented value into a
    Phase 15 context feature, where it would be indistinguishable from an
    observed one.
    """
    records = list(harvest([_post(PRE_RACE)], source_id="s", subreddit="running"))
    assert records[0].competition_level is None
    assert a5_descriptor("reddit_running_v1", "running").competition_level is None


def test_the_descriptor_forbids_redistribution():
    assert a5_descriptor("reddit_running_v1", "running").redistribution_permitted is False
