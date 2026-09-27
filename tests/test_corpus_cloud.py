"""Honesty tests for the corpus constellation (Phase 34).

The figure draws 4,000 records at once, which makes it the most quotable picture
this project produces and the easiest to quote wrongly. Three failures matter more
than the rest:

    (a) a record the detector said nothing about gets plotted at the midpoint. That
        would be nearly 1,500 invented readings in one image -- the `.claude.md`
        section 12.3 defect multiplied by the corpus size.
    (b) the artifact loses its stamp, and the figure becomes 4,000 numbers with no
        statement of what they are.
    (c) the four rows that legitimately sit on the midpoint go unexplained, and a
        reader takes the conservative default for a broken detector.

The loader is therefore a gate rather than a JSON read, and its refusals are
asserted here one by one against hand-built artifacts in `tmp_path`, because a
refusal nobody has triggered is a refusal nobody knows works.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.dashboard.bands import BANDS
from src.dashboard.charts import corpus_cloud_chart
from src.dashboard.copy import CLOUD_MIDPOINT_NOTE
from src.dashboard.corpus_cloud import (
    CLOUD_PATH,
    CloudLane,
    CorpusCloud,
    CorpusCloudError,
    CorpusCloudMissing,
    load_cloud,
)
from src.dashboard.view import ScoreSurface, assert_no_forbidden_language
from src.evaluation.harness import PROVISIONAL_STAMP
from src.models.dataset import CONSTRUCTS

pytestmark = pytest.mark.skipif(
    not CLOUD_PATH.exists(),
    reason="reports/corpus_cloud.json is not built; run scripts/build_corpus_cloud.py",
)


@pytest.fixture(scope="module")
def cloud() -> CorpusCloud:
    return load_cloud()


def _surface(value: float) -> ScoreSurface:
    return ScoreSurface(label="Median index, test", value=value, display=f"{value:.2f}")


def _artifact(**overrides) -> dict:
    """A minimal artifact that loads cleanly, for a test to break one field of."""
    payload = {
        "corpus": "test",
        "backend": "lexicon",
        "policy": "conservative default (neutral polarity)",
        "stamp": PROVISIONAL_STAMP,
        "provenance": "synthetic fixture",
        "scale_label": "test scale",
        "caveat": "test caveat",
        "n_records": 10,
        "n_scored": 6,
        "n_silent": 4,
        "n_unplanted": 1,
        "dots_per_lane": 80,
        "lanes": [
            {
                "construct": construct,
                "n_planted": 2,
                "n_scored": 1,
                "n_silent": 1,
                "median": 0.6,
                "dots": [0.6],
            }
            for construct in sorted(CONSTRUCTS)
        ],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, payload: dict) -> str:
    path = tmp_path / "corpus_cloud.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# (a) the committed artifact, as it stands
# ---------------------------------------------------------------------------


def test_the_committed_artifact_covers_every_construct(cloud):
    assert len(cloud.lanes) == len(CONSTRUCTS) == 10
    assert {lane.construct for lane in cloud.lanes} == set(CONSTRUCTS)


def test_the_totals_reconcile_with_the_lanes(cloud):
    assert cloud.n_scored + cloud.n_silent == cloud.n_records
    for lane in cloud.lanes:
        assert lane.n_scored + lane.n_silent == lane.n_planted
        assert len(lane.dots) <= lane.n_scored
        assert len(lane.dots) <= cloud.dots_per_lane


def test_every_dot_is_inside_the_range_a_squashed_index_can_occupy(cloud):
    for lane in cloud.lanes:
        for value in lane.dots:
            assert 0.0 <= value <= 1.0


def test_the_artifact_stores_no_record_text(cloud):
    """A committed report of 4,000 passages is a corpus; this one is numbers only."""
    raw = json.loads(CLOUD_PATH.read_text(encoding="utf-8"))
    assert "text" not in raw
    for lane in raw["lanes"]:
        assert set(lane) == {
            "construct",
            "n_planted",
            "n_scored",
            "n_silent",
            "median",
            "dots",
        }


def test_the_artifact_carries_no_timestamp(cloud):
    """A build date would make every rebuild a diff, which turns a gate into noise."""
    raw = json.loads(CLOUD_PATH.read_text(encoding="utf-8"))
    for key in raw:
        assert "time" not in key.lower()
        assert "date" not in key.lower()


def test_every_displayed_median_carries_the_artifact_stamp(cloud):
    for lane in cloud.lanes:
        if lane.median is None:
            continue
        assert lane.median.stamp == cloud.stamp
    for surface in cloud.surfaces:
        assert surface.stamp == cloud.stamp


# ---------------------------------------------------------------------------
# (b) the refusals
# ---------------------------------------------------------------------------


def test_a_missing_artifact_raises_with_the_rebuild_command(tmp_path):
    with pytest.raises(CorpusCloudMissing, match="build_corpus_cloud"):
        load_cloud(str(tmp_path / "nope.json"))


def test_an_artifact_with_no_stamp_is_refused(tmp_path):
    with pytest.raises(CorpusCloudError, match="PROVISIONAL"):
        load_cloud(_write(tmp_path, _artifact(stamp="")))


def test_totals_that_do_not_reconcile_are_refused(tmp_path):
    with pytest.raises(CorpusCloudError, match="records"):
        load_cloud(_write(tmp_path, _artifact(n_scored=5)))


def test_a_missing_lane_is_refused(tmp_path):
    payload = _artifact()
    payload["lanes"] = payload["lanes"][:-1]
    with pytest.raises(CorpusCloudError, match="no lane for"):
        load_cloud(_write(tmp_path, payload))


def test_a_lane_naming_an_unknown_construct_is_refused():
    with pytest.raises(CorpusCloudError, match="frozen taxonomy"):
        CloudLane(
            construct="vibes",
            plain_name="Vibes",
            n_planted=1,
            n_scored=1,
            n_silent=0,
            median=_surface(0.6),
            dots=(0.6,),
        )


def test_lane_counts_that_do_not_reconcile_are_refused():
    with pytest.raises(CorpusCloudError, match="reconcile"):
        CloudLane(
            construct="burnout_signal",
            plain_name="Running on empty",
            n_planted=5,
            n_scored=1,
            n_silent=1,
            median=_surface(0.6),
            dots=(0.6,),
        )


def test_a_lane_with_nothing_scored_may_not_carry_a_median():
    """The section 12.3 rule one level up: no detection anywhere, no number."""
    with pytest.raises(CorpusCloudError, match="0.50"):
        CloudLane(
            construct="burnout_signal",
            plain_name="Running on empty",
            n_planted=3,
            n_scored=0,
            n_silent=3,
            median=_surface(0.5),
            dots=(),
        )
    with pytest.raises(CorpusCloudError, match="0.50"):
        CloudLane(
            construct="burnout_signal",
            plain_name="Running on empty",
            n_planted=3,
            n_scored=3,
            n_silent=0,
            median=None,
            dots=(0.6, 0.7, 0.8),
        )


def test_more_dots_than_scored_records_is_refused():
    with pytest.raises(CorpusCloudError, match="invented"):
        CloudLane(
            construct="burnout_signal",
            plain_name="Running on empty",
            n_planted=2,
            n_scored=2,
            n_silent=0,
            median=_surface(0.6),
            dots=(0.6, 0.7, 0.8),
        )


def test_a_dot_outside_the_range_is_refused():
    with pytest.raises(CorpusCloudError, match="outside"):
        CloudLane(
            construct="burnout_signal",
            plain_name="Running on empty",
            n_planted=2,
            n_scored=2,
            n_silent=0,
            median=_surface(0.6),
            dots=(0.6, 1.4),
        )


def test_a_lane_with_nothing_scored_renders_without_a_median(cloud):
    """The empty-lane path is drawn, not crashed, and reports no middle."""
    empty = CloudLane(
        construct="burnout_signal",
        plain_name="Running on empty",
        n_planted=3,
        n_scored=0,
        n_silent=3,
        median=None,
        dots=(),
    )
    figure = corpus_cloud_chart(
        CorpusCloud(
            corpus=cloud.corpus,
            backend=cloud.backend,
            policy=cloud.policy,
            stamp=cloud.stamp,
            provenance=cloud.provenance,
            scale_label=cloud.scale_label,
            caveat=cloud.caveat,
            n_records=3,
            n_scored=0,
            n_silent=3,
            n_unplanted=0,
            dots_per_lane=80,
            lanes=(empty, *(lane for lane in cloud.lanes if lane.construct != "burnout_signal")),
        )
    )
    assert "0 plotted, 3 with nothing detected" in figure


# ---------------------------------------------------------------------------
# (c) what the figure says
# ---------------------------------------------------------------------------


def test_the_figure_says_the_scale_is_not_calibrated(cloud):
    figure = corpus_cloud_chart(cloud)
    assert "not calibrated" in figure
    assert "planted" in figure


def test_the_figure_explains_the_midpoint_pile_up(cloud):
    """Four rows sit on 0.50 by design. A figure that does not say so misleads."""
    figure = corpus_cloud_chart(cloud)
    assert "directionally unresolved" in figure
    assert "real reading, not a missing one" in figure
    # And the page's own wording makes the same point in the reader's register.
    assert "point either way" in CLOUD_MIDPOINT_NOTE


def test_the_figure_reports_the_absent_records(cloud):
    figure = corpus_cloud_chart(cloud)
    assert f"{cloud.n_silent} of {cloud.n_records}" in figure
    assert "absent rather than drawn at the midpoint" in figure


def test_the_figure_states_that_the_dots_are_a_sample(cloud):
    assert "stride sample" in corpus_cloud_chart(cloud)


def test_the_figure_carries_no_band_label(cloud):
    figure = corpus_cloud_chart(cloud)
    for band in BANDS:
        assert band.label not in figure


def test_the_figure_uses_no_forbidden_language(cloud):
    assert_no_forbidden_language(corpus_cloud_chart(cloud))


def test_the_figure_shows_only_medians_the_artifact_carries(cloud):
    figure = corpus_cloud_chart(cloud)
    for lane in cloud.lanes:
        if lane.median is None:
            continue
        assert lane.median.display in figure


def test_the_figure_is_deterministic(cloud):
    """Byte-stable, so a paper figure can be diffed between rebuilds."""
    assert corpus_cloud_chart(cloud) == corpus_cloud_chart(cloud)
