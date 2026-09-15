"""The register test: does the recovered text read as athlete self-report?

This file is the measurement. The gate in `src/media/relevance.py` is allowed to
exist only because the numbers below exist, and they are computed here rather
than quoted from a docstring so that a change to the weights moves the number or
fails the build.

Method, stated because it is the part that can be got wrong invisibly
----------------------------------------------------------------------
* **Positives** are the project's own pre-competition corpus:
  `data/processed/gold_candidates/gold_dev.jsonl` (100 utterances) for choosing
  the weights, and `gold_eval.jsonl` (400) which was not looked at until the
  weights were fixed. Reporting on the split the threshold was tuned on would be
  a fit presented as a finding.
* **Negatives** are `NEGATIVES` below: twenty off-topic texts written by this
  project. This is the weak half of the evaluation and it is weak in a specific
  way -- they are texts the author imagined, so they test the gate against
  plausible off-topic writing, not against whatever a user uploads. The
  false-positive figure is a sanity check and is described that way everywhere it
  appears.
* Both halves inherit OPEN-011: the positives are synthetic, so what is being
  measured is agreement with a register this project's generator invented.

The thresholds asserted are floors, not the observed values, so an improvement
does not fail the suite and a regression does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.media.relevance import (
    ON_TOPIC_THRESHOLD,
    STATE_WORDS,
    RelevanceVerdict,
    judge,
)

CORPUS = Path(__file__).resolve().parents[1] / "data" / "processed" / "gold_candidates"

#: Off-topic text, authored for this test. See the module docstring on what this
#: does and does not establish. Chosen to cover the shapes a camera actually
#: catches by accident: signage, packaging, instructions, reportage, admin.
NEGATIVES: tuple[str, ...] = (
    "P 24 HOURS PAY AND DISPLAY TICKETS MUST BE CLEARLY SHOWN ON THE DASHBOARD",
    "Preheat the oven to 180 degrees and grease a 20cm round tin with butter.",
    "Add the flour, sugar and eggs to a large bowl and whisk until smooth.",
    "The council has approved the new bypass after a consultation lasting eight months.",
    "Shares in the company fell four per cent following the announcement on Tuesday.",
    "This product contains milk, soya and wheat. Store in a cool dry place.",
    "Terms and conditions apply. Offer valid until the end of the month.",
    "Please queue here. Staff will call the next customer when a till is free.",
    "The train to platform 4 is delayed by approximately fifteen minutes.",
    "Install the package with pip and then run the command from the project root.",
    "Return the value of the function as a list of integers sorted in ascending order.",
    "Heavy rain is expected across the region tonight with gusts of up to 50 mph.",
    "FIRE EXIT KEEP CLEAR AT ALL TIMES",
    "Happy birthday! Hope you have a lovely day and see you at the weekend.",
    "The museum is open from ten until five and entry is free for children.",
    "Wash at 30 degrees. Do not tumble dry. Iron on a low heat only.",
    "Our offices will be closed on Monday and will reopen on Tuesday morning.",
    "The lease shall commence on the date of signature and continue for twelve months.",
    "Chapter four discusses the origins of the printing press in northern Europe.",
    "Table 3 reports the mean and standard deviation for each of the four groups.",
)

#: Floors. The observed figures at the time of writing are 0.82 (dev) and 0.85
#: (eval); the floors sit below them so that an improvement passes.
MIN_RECALL_DEV = 0.78
MIN_RECALL_EVAL = 0.80
MAX_FALSE_POSITIVE_RATE = 0.10


def _texts(split: str) -> tuple[str, ...]:
    path = CORPUS / f"{split}.jsonl"
    if not path.exists():  # pragma: no cover - corpus not present in a thin checkout
        pytest.skip(f"{path} is not present; the register test needs the corpus.")
    with path.open(encoding="utf-8") as handle:
        return tuple(json.loads(line)["text"] for line in handle if line.strip())


def _recall(texts: tuple[str, ...]) -> float:
    return sum(1 for text in texts if judge(text).on_topic) / len(texts)


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def test_recall_on_the_split_the_weights_were_chosen_on() -> None:
    recall = _recall(_texts("gold_dev"))
    assert recall >= MIN_RECALL_DEV, f"dev recall fell to {recall:.3f}"


def test_recall_on_the_held_out_split() -> None:
    """The one that means something.

    `gold_eval` was not consulted while the weights were being chosen. Recall
    here at or above the dev figure is what says the gate found a register
    rather than memorising a hundred sentences.
    """
    recall = _recall(_texts("gold_eval"))
    assert recall >= MIN_RECALL_EVAL, f"held-out recall fell to {recall:.3f}"


def test_held_out_recall_does_not_collapse_against_dev() -> None:
    """A large dev-to-eval drop is the signature of a fitted threshold."""
    dev, evaluation = _recall(_texts("gold_dev")), _recall(_texts("gold_eval"))
    assert evaluation >= dev - 0.10, (
        f"dev {dev:.3f} but held-out {evaluation:.3f}: the threshold is fitted to dev."
    )


def test_authored_negatives_are_mostly_refused() -> None:
    rate = sum(1 for text in NEGATIVES if judge(text).on_topic) / len(NEGATIVES)
    assert rate <= MAX_FALSE_POSITIVE_RATE, f"false-positive rate rose to {rate:.3f}"


def test_the_known_false_positive_is_named_rather_than_hidden() -> None:
    """One negative passes, and it is worth knowing which.

    "Our offices will be closed on Monday" carries a first-person plural and a
    weekday, which is most of what the gate looks for. It is a real weakness of a
    first-person-dominated register test and it is recorded here rather than
    patched with a special case, because a special case would make the next one
    invisible.
    """
    office = "Our offices will be closed on Monday and will reopen on Tuesday morning."
    assert judge(office).on_topic, (
        "This has been the known false positive since the gate was written. If it "
        "now passes, say so in docs/findings.md rather than deleting this test."
    )


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I am worried about tomorrow and I could not sleep last night.",
        "Honestly there is more noise around me than I would choose right now.",
        "I know what I have to do and I have done the work, so I am ready.",
    ],
)
def test_athlete_self_report_is_on_topic(text: str) -> None:
    verdict = judge(text)
    assert verdict.on_topic
    assert verdict.score >= ON_TOPIC_THRESHOLD
    assert verdict.detail == "", "an on-topic verdict has nothing to explain"


@pytest.mark.parametrize(
    "text",
    ["P 24 HOURS PAY AND DISPLAY", "FIRE EXIT KEEP CLEAR AT ALL TIMES"],
)
def test_signage_is_caught_by_shape_not_by_vocabulary(text: str) -> None:
    """Capitals and digits, no word list. A sign this page has never seen still fails."""
    verdict = judge(text)
    assert not verdict.on_topic
    assert verdict.detail.strip()


def test_a_verdict_always_explains_a_refusal() -> None:
    for text in NEGATIVES:
        verdict = judge(text)
        if not verdict.on_topic:
            assert verdict.detail.strip(), f"no explanation for {text[:40]!r}"


def test_empty_text_is_not_on_topic_and_says_so() -> None:
    verdict = judge("!!!")
    assert isinstance(verdict, RelevanceVerdict)
    assert not verdict.on_topic
    assert verdict.detail.strip()


def test_verdict_is_advisory_and_carries_its_own_evidence() -> None:
    """The page needs the components, not just the boolean, to explain itself."""
    verdict = judge("I am nervous about the final tomorrow and I did not sleep.")
    assert verdict.first_person > 0
    assert verdict.sport_hits > 0
    assert verdict.state_hits > 0
    assert 0.0 <= verdict.score <= 1.0


# ---------------------------------------------------------------------------
# The declared limitation
# ---------------------------------------------------------------------------


def test_state_words_overlap_the_construct_vocabulary_is_declared() -> None:
    """Limitation 3 in the module docstring, asserted so it cannot quietly stop being true.

    Relevance and detected signal are not independent: some words that make a
    text look on-topic also raise construct probabilities. The overlap is real
    and is declared in the docstring and the paper rather than engineered away,
    because a register test that cannot see the thing the register is about would
    not be a register test.
    """
    from src.evaluation.baselines import CONSTRUCT_CUES

    cues = {cue.lower() for cues in CONSTRUCT_CUES.values() for cue in cues}
    shared = {word for word in STATE_WORDS if any(word in cue.split() for cue in cues)}
    assert shared, (
        "The overlap with the construct lexicon has disappeared. That is not "
        "automatically good: check whether the register test can still see "
        "self-state language at all, and update the docstring either way."
    )
