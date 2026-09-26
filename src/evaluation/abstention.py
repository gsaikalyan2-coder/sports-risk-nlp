"""Abstention-aware evaluation: what the system does with what it cannot score.

Why this module exists
-----------------------
Every macro-F1 in `reports/` is computed over inputs that were assumed to be
scorable. That assumption is the one `CLAUDE.md` sec.12.3 identifies as this
project's most dangerous defect, and it is argued there in prose:

    `LexiconBackend` will score anything. Hand it keyboard mash, or an empty
    string from a missing OCR engine, or a car-park sign: nothing matches, all
    ten probabilities are 0.0, the weighted sum is 0.0, and the logistic squash
    returns an index of **exactly 0.50** -- a psychological score of 50 out of
    100, with a band, a stamp and ten tiles beneath it.

Three gates were built because of that argument. None of them has ever been
measured. This module measures them, and in particular it computes the number
the prose asserts: **the index each refused input would have received had the
gate not been there.** A refusal rate on its own says a gate is opinionated; the
counterfactual says what the opinion was worth.

What is measured, and what each half is worth
----------------------------------------------
* **False refusals** -- the corpus (`gold_dev` + `gold_eval`, n=500) run through
  the gates. These are texts the system *should* score. Refusals here are pure
  cost, and the rate is the honest price of the gate.
* **True refusals** -- authored junk, by class. This is the weaker half and it
  is weak in the same specific way `src/media/relevance.py` declares for its own
  negatives: the classes below are shapes this project imagined a camera or a
  paste box catching, not a sample of what users actually submit. Treat the
  per-class rates as a sanity check, never as an estimate of field behaviour.
* **The counterfactual index** -- for every input, the risk index the ordinary
  text path would have produced with the gate bypassed. Reported for refused
  inputs, where it is the measurement of the defect, and for the corpus, where
  it is the control that shows the midpoint is specific to unscorable input.

Inherited limitations, all of which belong in the paper
--------------------------------------------------------
1. **The positives are synthetic** (OPEN-011), so the false-refusal rate is
   measured against the register this project's own generator writes.
2. **The junk is authored by this project**, as above.
3. **The counterfactual uses `LexiconBaseline`'s cue list**, not the
   transformer. The 0.50 argument is a property of the fusion layer given
   all-zero probabilities, and any detector that fires on nothing reaches it;
   the lexicon is used because it is the deterministic one and needs no
   checkpoint. A transformer emits small non-zero probabilities on junk, so its
   counterfactual would cluster *near* the midpoint rather than on it. That is a
   different and weaker statement, and it is not the one made here.

All pure Python. No network, no ML stack, no checkpoint, no cost.

Deliberately **not** re-exported from `src/evaluation/__init__.py`
--------------------------------------------------------------------
Import it as `from src.evaluation.abstention import ...`, never via the package.
This module reaches into `src.dashboard` and `src.media` for the gates, and an
eager re-export puts that whole graph behind `import src.evaluation`, which
trips the OPEN-036 import cycle: `src.dashboard.__init__` -> `copy` -> `view` ->
`backend` -> `src.explainability.attribution`, partially initialised. It was
added, it broke
`tests/test_evaluation_harness.py::test_explainability_imports_standalone_in_a_fresh_interpreter`,
and it was removed rather than worked around -- the convenience bought nothing
that a direct import does not already give.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from src.dashboard.backend import DASHBOARD_EXTRA_CUES
from src.dashboard.gibberish import admit
from src.evaluation.baselines import CONSTRUCT_CUES
from src.media.relevance import judge
from src.risk.fusion import LinearRiskScorer

#: The index the fusion layer returns when every construct probability is 0.0,
#: for any temperature. Named because a bare 0.5 in a comparison reads as a
#: threshold, and this is not a threshold -- it is the specific wrong answer
#: this whole layer exists to prevent.
MIDPOINT = 0.5

#: Floating-point slack when asking "did this land exactly on the midpoint".
MIDPOINT_TOLERANCE = 1e-9

#: Authored junk, by the shape that produces it. See limitation 2 above: these
#: are shapes this project imagined, not a sample of user submissions.
#:
#: `off_register` is deliberately included although the gates do **not** refuse
#: it. Under `CLAUDE.md` sec.12.2 the register test decorates rather than gates,
#: so this class is the control showing the two gates answer different
#: questions: `admit` asks "is this language", `judge` asks "is this the right
#: language". A report omitting it would imply a refusal the system does not
#: make.
JUNK_CLASSES: Mapping[str, tuple[str, ...]] = {
    "empty_extraction": (
        "",
        "   ",
        "\n\n\t  \n",
    ),
    "keyboard_mash": (
        "asdfghjkl qwertyuiop zxcvbnm asdfgh",
        "kkkkkkkk jjjjjjjj hhhhhhhh gggggggg",
        "xzqwv brtkn plmfd zxcvb qwrtp",
        "aaaaaaaaaaaa bbbbbbbbbbbb cccccccccccc",
    ),
    "symbols_and_digits": (
        "### 42 >>> 1,200.00 // 99% @@@ *** +++",
        "01/02/2026 14:30 -- 18:45 (+05:30) [ref 88213]",
        "<<< ---- ==== ++++ ~~~~ |||| ____ >>>>",
    ),
    "too_short": (
        "ok",
        "I am fine",
        "yes",
        "not sure",
    ),
    "off_register": (
        "P 24 HOURS PAY AND DISPLAY TICKETS MUST BE CLEARLY SHOWN ON THE DASHBOARD",
        "Preheat the oven to 180 degrees and grease a 20cm round tin with butter.",
        "The council has approved the new bypass after a consultation lasting eight months.",
        "Shares in the company fell four per cent following the announcement on Tuesday.",
        "Install the package with pip and then run the command from the project root.",
        "Wash at 30 degrees. Do not tumble dry. Iron on a low heat only.",
        "Table 3 reports the mean and standard deviation for each of the four groups.",
    ),
}


#: The three ways a text arrives at the midpoint, and the one way it does not.
#: Separated because they have different fixes and only the first is a gate's
#: business -- see `AbstentionReport` and the report's section 3.
CAUSES: tuple[str, ...] = ("refused", "no_detection", "all_inert", "moved")


def counterfactual_score(text: str, scorer: LinearRiskScorer | None = None):
    """The `RiskScore` `text` would receive with every gate bypassed.

    Deliberately reimplements the cue match rather than importing
    `LexiconBackend`: that class carries `DASHBOARD_EXTRA_CUES`, the demo-only
    widening documented in `docs/dashboard.md`, and a measurement must use the
    evaluated cue list. `CONSTRUCT_CUES` is the frozen one.
    """
    scorer = scorer or LinearRiskScorer()
    lowered = text.lower()
    probabilities = {
        construct: 1.0 if any(cue in lowered for cue in cues) else 0.0
        for construct, cues in CONSTRUCT_CUES.items()
    }
    return scorer.score(probabilities)


def counterfactual_index(text: str, scorer: LinearRiskScorer | None = None) -> float:
    """The bare index, for callers that do not need the decomposition."""
    return counterfactual_score(text, scorer).index


@dataclass(frozen=True)
class Outcome:
    """One text's journey through the gates, and what it would have scored."""

    klass: str
    admitted: bool
    refusal_reason: str
    on_topic: bool
    index: float
    detected: int

    @property
    def at_midpoint(self) -> bool:
        return abs(self.index - MIDPOINT) <= MIDPOINT_TOLERANCE

    @property
    def cause(self) -> str:
        """Why this text ended where it did.

        The ordering matters and is not arbitrary. `refused` wins over the rest
        because a refused text never reaches the scorer in the real system, so
        its index is counterfactual in a second sense: it is what *would* have
        happened, not a defect the user can see. The other two are live defects
        on text the system accepted and scored.
        """
        if not self.admitted:
            return "refused"
        if not self.at_midpoint:
            return "moved"
        return "no_detection" if self.detected == 0 else "all_inert"


def evaluate(text: str, klass: str, scorer: LinearRiskScorer | None = None) -> Outcome:
    """Run one text through both gates and the bypassed scorer."""
    admission = admit(text)
    verdict = judge(text)
    score = counterfactual_score(text, scorer)
    return Outcome(
        klass=klass,
        admitted=admission.admitted,
        refusal_reason="" if admission.admitted else admission.reason,
        on_topic=verdict.on_topic,
        index=score.index,
        detected=sum(1 for c in score.contributions if c.probability > 0.0),
    )


@dataclass(frozen=True)
class ClassResult:
    """The gates' behaviour over one class of input."""

    name: str
    n: int
    refused: int
    off_register: int
    at_midpoint: int
    reasons: tuple[tuple[str, int], ...]
    causes: tuple[tuple[str, int], ...]

    @property
    def refusal_rate(self) -> float:
        return self.refused / self.n if self.n else 0.0

    @property
    def off_register_rate(self) -> float:
        return self.off_register / self.n if self.n else 0.0

    @property
    def midpoint_rate(self) -> float:
        """Share whose bypassed index is exactly the midpoint."""
        return self.at_midpoint / self.n if self.n else 0.0

    def cause(self, name: str) -> int:
        return dict(self.causes).get(name, 0)

    @property
    def ungated_midpoint(self) -> int:
        """Midpoint scores the gates do **not** prevent.

        The headline of this whole module. A text here was admitted, scored, and
        handed back the midpoint anyway -- either because the detector fired on
        nothing or because everything it fired on was directionally inert. No
        gate in the system addresses either route.
        """
        return self.cause("no_detection") + self.cause("all_inert")

    @property
    def ungated_midpoint_rate(self) -> float:
        return self.ungated_midpoint / self.n if self.n else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n": self.n,
            "refused": self.refused,
            "refusal_rate": round(self.refusal_rate, 4),
            "off_register": self.off_register,
            "off_register_rate": round(self.off_register_rate, 4),
            "at_midpoint": self.at_midpoint,
            "midpoint_rate": round(self.midpoint_rate, 4),
            "ungated_midpoint": self.ungated_midpoint,
            "ungated_midpoint_rate": round(self.ungated_midpoint_rate, 4),
            "reasons": dict(self.reasons),
            "causes": dict(self.causes),
        }


def summarise(outcomes: Sequence[Outcome], name: str) -> ClassResult:
    """Fold one class's outcomes into a row."""
    reasons = Counter(o.refusal_reason for o in outcomes if not o.admitted)
    causes = Counter(o.cause for o in outcomes)
    return ClassResult(
        name=name,
        n=len(outcomes),
        refused=sum(1 for o in outcomes if not o.admitted),
        off_register=sum(1 for o in outcomes if not o.on_topic),
        at_midpoint=sum(1 for o in outcomes if o.at_midpoint),
        reasons=tuple(sorted(reasons.items())),
        causes=tuple((c, causes.get(c, 0)) for c in CAUSES),
    )


#: The two cue lists that exist, and what each one is for. The frozen list is
#: the instrument every committed figure was measured with; the widened one is
#: what a visitor to the deployed page is actually scored by
#: (`docs/dashboard.md`). Named together here because the silence rate below is
#: the one number that differs between them by a factor of three, and a quote of
#: it without its list is the mis-citation this section exists to prevent.
CUE_LISTS: tuple[tuple[str, str, Mapping[str, tuple[str, ...]]], ...] = (
    (
        "CONSTRUCT_CUES",
        "frozen; the list every committed figure was measured with",
        CONSTRUCT_CUES,
    ),
    (
        "CONSTRUCT_CUES + DASHBOARD_EXTRA_CUES",
        "widened; demo only, no measured score of its own",
        {
            construct: CONSTRUCT_CUES.get(construct, ()) + DASHBOARD_EXTRA_CUES.get(construct, ())
            for construct in set(CONSTRUCT_CUES) | set(DASHBOARD_EXTRA_CUES)
        },
    ),
)


@dataclass(frozen=True)
class SilenceResult:
    """How often one cue list fires on nothing at all.

    **This is coverage, not correctness**, and the distinction is the whole
    reason the widened list may appear in a measurement at all. Firing more
    often is not firing more correctly: every extra match could be wrong and
    nothing here shows otherwise, because precision needs the gold set OPEN-025
    is waiting on. `test_the_evaluated_cue_list_is_pinned` and
    `test_counterfactual_uses_the_evaluated_cue_list_not_the_dashboard_one` keep
    the widened list out of every *scored* number in this module; it is admitted
    to this one because a silence count is a property of the list itself.
    """

    name: str
    description: str
    n: int
    silent: int

    @property
    def rate(self) -> float:
        return self.silent / self.n if self.n else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "n": self.n,
            "silent": self.silent,
            "rate": round(self.rate, 4),
        }


def is_silent(text: str, cues: Mapping[str, tuple[str, ...]]) -> bool:
    """Whether `cues` matches nothing in `text` -- the `no_detection` route's cause."""
    lowered = text.lower()
    return not any(any(cue in lowered for cue in group) for group in cues.values())


def silence_rates(corpus: Sequence[str]) -> tuple[SilenceResult, ...]:
    """The silence rate of each cue list over the same corpus.

    Counts the *detector's* silence, so it includes the text the admission gate
    refuses -- which is why the frozen list's figure here is one text higher
    than section 3's `no_detection` count, where `refused` wins the cause
    ordering. The two are both right and they answer different questions: this
    one is a property of the cue list, that one is a property of the pipeline.
    """
    return tuple(
        SilenceResult(
            name=name,
            description=description,
            n=len(corpus),
            silent=sum(1 for text in corpus if is_silent(text, cues)),
        )
        for name, description, cues in CUE_LISTS
    )


def load_corpus(directory: Path) -> tuple[str, ...]:
    """The project's own pre-competition text, both gold-candidate splits."""
    texts: list[str] = []
    for split in ("gold_dev", "gold_eval"):
        path = directory / f"{split}.jsonl"
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            texts.extend(json.loads(line)["text"] for line in handle if line.strip())
    return tuple(texts)


@dataclass(frozen=True)
class AbstentionReport:
    """The whole picture: the cost of the gates and the defect they prevent."""

    corpus: ClassResult
    junk: tuple[ClassResult, ...]
    silence: tuple[SilenceResult, ...]
    provenance: str

    @property
    def junk_n(self) -> int:
        return sum(c.n for c in self.junk)

    @property
    def refused_junk(self) -> int:
        return sum(c.refused for c in self.junk)

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance": self.provenance,
            "corpus": self.corpus.to_dict(),
            "junk": [c.to_dict() for c in self.junk],
            "silence": [s.to_dict() for s in self.silence],
        }


def build_report(corpus: Sequence[str], provenance: str) -> AbstentionReport:
    """Run the corpus and every junk class through the gates."""
    scorer = LinearRiskScorer()
    corpus_outcomes = [evaluate(text, "corpus", scorer) for text in corpus]
    junk = tuple(
        summarise([evaluate(text, name, scorer) for text in texts], name)
        for name, texts in JUNK_CLASSES.items()
    )
    return AbstentionReport(
        corpus=summarise(corpus_outcomes, "corpus"),
        junk=junk,
        silence=silence_rates(corpus),
        provenance=provenance,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(report: AbstentionReport, *, generated: str) -> str:
    """The report page. Every number comes from `report`; none is written here."""
    corpus, junk = report.corpus, report.junk
    lines = [
        "# Abstention-aware evaluation -- what the system does with what it cannot score",
        "",
        "> **No number in this file is an accuracy.** Every figure is behaviour of",
        "> the gates and the fusion layer over synthetic text (OPEN-011) with an",
        "> empty `data/gold/` (OPEN-025). Nothing here describes any real person.",
        "",
        f"- Generated: {generated}",
        f"- Provenance: {report.provenance}",
        "- Detector: `CONSTRUCT_CUES` (the evaluated cue list, **not** the widened",
        "  dashboard one -- see `docs/dashboard.md`). Section 4 is the one place",
        "  the widened list is measured, and it measures coverage, never accuracy.",
        "- Pure Python, no checkpoint, no network. Reproduce with",
        "  `python scripts/run_abstention_report.py`.",
        "",
        "## 1. What this measures, and why it did not exist before",
        "",
        "Every macro-F1 in `reports/results.md` is computed over inputs assumed to",
        "be scorable. `CLAUDE.md` sec.12.3 argues in prose that unscorable input",
        "produces an index of exactly 0.50 -- a score of 50 out of 100 with a band",
        "and ten tiles beneath it -- and three gates were built on that argument.",
        "This page is the first measurement of them.",
        "",
        "The question asked of every input is not only *was it refused* but **what",
        "would it have scored had it not been**. A refusal rate alone says a gate is",
        "opinionated. The counterfactual says what the opinion was worth.",
        "",
        "## 2. The cost of the gates (false refusals)",
        "",
        "The corpus is text the system *should* score. Refusals here are pure cost.",
        "",
        "| set | n | refused | refusal rate | flagged off-register |",
        "|---|---|---|---|---|",
        f"| `gold_dev` + `gold_eval` | {corpus.n} | {corpus.refused} | "
        f"**{_pct(corpus.refusal_rate)}** | {corpus.off_register} "
        f"({_pct(corpus.off_register_rate)}) |",
        "",
        f"The gates cost {_pct(corpus.refusal_rate)} of legitimate text. That is the",
        "honest price, and it is small.",
        "",
        "## 3. The finding: the gates close the narrowest of three routes",
        "",
        "An index of exactly 0.50 is reached three ways, and only the first is a",
        "gate's business. Separating them is what this report adds, because the",
        "three have different fixes and the prose in `CLAUDE.md` sec.12.3 describes",
        "only one.",
        "",
        "| route | what happened | does a gate stop it |",
        "|---|---|---|",
        "| `refused` | input was not language; never reaches the scorer | **yes** |",
        "| `no_detection` | good text, detector fired on nothing | no |",
        "| `all_inert` | good text, constructs detected, all directionally "
        "unresolved so all weighted 0 | no |",
        "",
        "Over the corpus:",
        "",
        "| route | n | share of corpus |",
        "|---|---|---|",
    ]
    for cause in CAUSES:
        count = corpus.cause(cause)
        lines.append(f"| `{cause}` | {count} | {_pct(count / corpus.n)} |")
    lines += [
        "",
        f"**{corpus.ungated_midpoint} of {corpus.n} corpus texts "
        f"({_pct(corpus.ungated_midpoint_rate)}) are admitted, scored, and handed",
        "back exactly 0.50 anyway.** No gate in the system addresses either route.",
        f"The refusal gate prevented {corpus.refused} of them.",
        "",
        f"The `all_inert` row is the sharper half: {corpus.cause('all_inert')} texts",
        "light up construct bars on the dashboard and still produce the midpoint,",
        "because the conservative default polarity policy weights a directionally",
        "unresolved construct at zero. A reader sees evidence and a neutral score at",
        "the same time, which is the most misreadable state the interface has.",
        "",
        "**This contradicts the comfortable version of the argument.** The gates were",
        "built to stop a vacuous 0.50 and they do -- for the input class that makes up",
        f"{_pct(corpus.refusal_rate)} of corpus traffic. The class that makes up",
        f"{_pct(corpus.ungated_midpoint_rate)} is untouched by them.",
        "",
        "## 4. Which cue list is in force, and what silence costs each one",
        "",
        "The `no_detection` route above is a property of the detector, and this",
        "project runs two of them: the frozen `CONSTRUCT_CUES` that every",
        "committed figure was measured with, and the same list widened by",
        "`DASHBOARD_EXTRA_CUES` for the deployed page only (`docs/dashboard.md`).",
        "A silence rate quoted without naming its list is the most misleading",
        "number this report can produce, because the two differ by a factor of",
        "three. Both are therefore measured here, over the same corpus.",
        "",
        "| cue list | what it is | n | silent | silence rate |",
        "|---|---|---|---|---|",
    ]
    for silence in report.silence:
        lines.append(
            f"| `{silence.name}` | {silence.description} | {silence.n} | "
            f"{silence.silent} | **{_pct(silence.rate)}** |"
        )
    lines += [
        "",
        "**This is coverage, not correctness.** Firing more often is not firing",
        "more correctly: every extra match the widened list makes could be wrong",
        "and nothing here shows otherwise, because precision needs the gold set",
        "OPEN-025 is waiting on. The widened list still has no measured score, it",
        "is in no committed figure, and no macro-F1 anywhere derives from it.",
        "",
        "These counts are the *detector's* silence, so they include text the",
        "admission gate refused; section 3's `no_detection` count excludes it,",
        "because `refused` wins the cause ordering there. That is the whole of",
        f"the difference between the two frozen-list figures "
        f"({report.silence[0].silent} here, {corpus.cause('no_detection')} there).",
        "",
        "## 5. True refusals, by junk class",
        "",
        "**Authored by this project, and weak in a stated way**: these are shapes the",
        "project imagined a paste box or a camera catching, not a sample of user",
        "submissions. Sanity check, never a field estimate.",
        "",
        "| class | n | refused | rate | refusal reasons | at midpoint |",
        "|---|---|---|---|---|---|",
    ]
    for result in junk:
        reasons = ", ".join(f"`{k}`x{v}" for k, v in result.reasons) or "--"
        lines.append(
            f"| `{result.name}` | {result.n} | {result.refused} | "
            f"{_pct(result.refusal_rate)} | {reasons} | {result.at_midpoint} |"
        )
    non_language = [r for r in junk if r.name != "off_register"]
    nl_n = sum(r.n for r in non_language)
    nl_refused = sum(r.refused for r in non_language)
    lines += [
        "",
        f"Non-language junk is refused {nl_refused} of {nl_n} "
        f"({_pct(nl_refused / nl_n if nl_n else 0.0)}). Counting `off_register`, "
        f"which is deliberately not refused, the figure over all "
        f"{report.junk_n} authored items is {report.refused_junk}.",
        "",
        "`off_register` is the control and it is **not** refused, by design: under",
        "`CLAUDE.md` sec.12.2 the register test decorates and never gates. Those",
        "texts are real English about the wrong subject, so `admit` passes them,",
        "`judge` flags them, and they are scored. Every one lands on the midpoint --",
        "which is the `no_detection` route again, arriving from a different door.",
        "",
        "## 6. What this does not establish",
        "",
        "1. **The positives are synthetic** (OPEN-011). The false-refusal rate is",
        "   measured against the register this project's own generator writes.",
        "2. **The junk is authored** by this project (sec.5 above).",
        "3. **The counterfactual uses the lexicon**, not the transformer. The 0.50",
        "   result is a property of the fusion layer given all-zero probabilities; a",
        "   transformer emits small non-zero probabilities on junk and would cluster",
        "   *near* the midpoint rather than on it. That is a weaker statement and it",
        "   is not the one made here.",
        "4. **No claim is made that refusing was correct** in any individual case",
        "   beyond the authored classes. There is no human judgement of refusals,",
        "   because that needs the annotators OPEN-025 is waiting on.",
        "",
    ]
    return "\n".join(lines)
