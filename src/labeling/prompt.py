"""Prompt construction for the Labeling Agent.

Two prompts per call, and the split is the whole cost strategy:

* the **system prompt** is the rubric. It is long (~2,000 tokens), identical for
  every one of the ~9,000 calls, and built once per process from
  `config/taxonomy.yaml` plus the rules in `docs/annotation_guidelines.md`.
* the **user prompt** is the utterance and its context. It is short and varies
  per call.

`prompt_caching: true` in `config/model_routing.yaml` only pays off if the
cached prefix is **byte-identical** across calls. That is a real constraint on
how this module is written, not an aspiration:

* the system prompt is assembled deterministically -- constructs in
  `taxonomy.yaml` file order, no dict iteration whose order could drift, no
  timestamps, no run ids, no record-specific text anywhere in it;
* it is memoised on the taxonomy path, so a run builds it once;
* `SYSTEM_PROMPT_VERSION` is bumped by hand when the rubric changes, and a test
  asserts the prompt contains every construct and every placeholder. Edit the
  prompt and forget the version, and the cache silently stops hitting while
  everything still appears to work -- only the bill changes.

**Why the taxonomy is inlined rather than summarised.** The rubric is the only
thing standing between a cheap model and generic sentiment analysis. The
discriminating questions from `docs/annotation_guidelines.md` sec.4 are the
highest-value tokens in the whole prompt: they are exactly the five confusions
that cause most human disagreement, so they are exactly what a model with no
sports-psychology training will get wrong.

**Why the placeholder glossary is not optional.** De-identification leaves
`[ATHLETE]`, `[COACH]`, `[EVENT_WINDOW]` and eleven others in the text. A model
told nothing about them will either treat them as noise or, worse, read
`[EVENT_WINDOW]` as a literal phrase and hallucinate a temporal claim from it.
They are meaningful tokens and the model is told so explicitly.

**Why the parent record is shown but not labelled.** Median utterance length is
17 tokens. `appraisal_orientation` is a stance toward an event and frequently
cannot be judged from one clause. The parent record is supplied as context and
the target utterance is fenced inside it, with an instruction to label only the
target. See `docs/labeling.md` sec.3 for what this costs -- it is the reason
deduplication saves ~1%, not ~31%.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.agents.config import load_taxonomy
from src.agents.roster import ETHICS_PREAMBLE
from src.preprocessing.deidentify import PLACEHOLDERS

#: Bump by hand whenever the assembled system prompt changes meaning. Written
#: into every silver record so a mixed-version silver set is detectable after
#: the fact rather than being an untraceable inconsistency.
SYSTEM_PROMPT_VERSION = "silver-v1"

#: Plain-English gloss for each de-identification placeholder. Written out
#: rather than generated so that a placeholder added to `deidentify.py` without
#: a gloss fails a test instead of quietly reaching the model unexplained.
PLACEHOLDER_GLOSSARY: dict[str, str] = {
    "[ATHLETE]": "the athlete speaking, or another athlete; a redacted personal name",
    "[COACH]": "a coach; a redacted personal name",
    "[TEAMMATE]": "a teammate; a redacted personal name",
    "[OPPONENT]": "a rival or opponent; a redacted personal name",
    "[PERSON]": "some other person; a redacted personal name",
    "[HANDLE]": "a redacted social-media handle",
    "[CONTACT]": "a redacted email address or phone number",
    "[URL]": "a redacted web link",
    "[TEAM]": "a redacted team or club name",
    "[ORG]": "a redacted organisation, federation or sponsor name",
    "[LOCATION]": "a redacted place name",
    "[EVENT]": "a redacted competition or event name",
    "[EVENT_WINDOW]": "a redacted date, time or date range for the competition",
    "[ID]": "a redacted identifier such as a bib or licence number",
}

#: The exact JSON the model must return. Shown as a schema plus one filled
#: example: schemas alone produce well-typed nonsense, examples alone produce
#: copies of the example. Both together is what the parser can actually rely on.
RESPONSE_SCHEMA = """\
{
  "abstain": <true if NO construct is expressed at all, else false>,
  "rationale": "<one or two sentences, describing the LANGUAGE, never the person>",
  "confidence": <0.0-1.0, your confidence in this whole judgement>,
  "interpretation_modifier": "facilitative" | "debilitative" | "unclear" | null,
  "low_resilience_explicit": <true only if the text explicitly states fragility>,
  "labels": [
    {
      "construct": "<one of the ten construct keys below>",
      "value": "present" | "<one of that construct's categorical labels>",
      "intensity": <0-3>,
      "evidence_spans": ["<EXACT substring copied from the TARGET utterance>"],
      "confidence": <0.0-1.0 for this construct specifically>
    }
  ]
}"""

RESPONSE_EXAMPLE = """\
Target utterance:
  "I keep thinking about the ways this could go wrong - my hands won't stop shaking."

{
  "abstain": false,
  "rationale": "Forward-looking outcome worry plus reported bodily arousal; both stated \
without hedging.",
  "confidence": 0.82,
  "interpretation_modifier": "unclear",
  "low_resilience_explicit": false,
  "labels": [
    {
      "construct": "cognitive_anxiety",
      "value": "present",
      "intensity": 2,
      "evidence_spans": ["I keep thinking about the ways this could go wrong"],
      "confidence": 0.85
    },
    {
      "construct": "somatic_anxiety",
      "value": "present",
      "intensity": 2,
      "evidence_spans": ["my hands won't stop shaking"],
      "confidence": 0.8
    }
  ]
}"""

#: Lifted from `docs/annotation_guidelines.md` sec.4. These five pairs cause
#: most inter-annotator disagreement, so they are the highest-value tokens in
#: the prompt. Kept as a literal rather than parsed out of the markdown: a
#: prompt that silently changes when someone reflows a table is a prompt whose
#: cache key changes for no reason.
DISCRIMINATING_QUESTIONS = """\
1. cognitive_anxiety vs perceived_stress
   Worried about the OUTCOME, or overwhelmed by the DEMAND? Outcome worry is
   cognitive_anxiety; demand-exceeds-resources is perceived_stress. Both can be true.
2. cognitive_anxiety vs appraisal_orientation = threat
   Worry, or a positioning of SELF against the demand? "I'm scared I'll mess up" is
   anxiety; "this field is beyond me" is threat appraisal. They often co-occur.
3. self_confidence vs resilience
   Expected success, or recovery if it goes wrong? No adversity frame means it is
   not resilience.
4. somatic_anxiety vs burnout_signal
   Acute arousal before THIS competition, or depletion built up over time? Plain
   training fatigue is neither.
5. coping_style = avoidance vs attentional_focus = distracted
   Is a STRATEGY described, or is attention simply going somewhere unhelpful?
   Naming an emotion is neither."""


def _construct_block(name: str, record: dict[str, Any]) -> str:
    """One construct's entry in the rubric, in a stable field order."""
    lines = [f"### {name}"]
    label_type = str(record.get("label_type", "graded"))
    if label_type == "categorical":
        labels = record.get("labels") or []
        lines.append(f"type: categorical -- value must be one of: {', '.join(labels)}")
    else:
        lines.append('type: graded -- value is "present" or "absent"; intensity 0-3')
    definition = " ".join(str(record.get("definition", "")).split())
    lines.append(f"definition: {definition}")
    for example in record.get("positive_examples") or []:
        lines.append(f"  + {example}")
    for example in record.get("negative_examples") or []:
        lines.append(f"  - {example}")
    edge = " ".join(str(record.get("edge_cases", "")).split())
    if edge:
        lines.append(f"edge cases: {edge}")
    return "\n".join(lines)


def build_system_prompt(taxonomy: dict[str, Any] | None = None) -> str:
    """Assemble the full rubric prompt. Deterministic and cacheable."""
    tax = taxonomy if taxonomy is not None else load_taxonomy()
    constructs = tax.get("constructs") or {}

    glossary = "\n".join(
        f"  {token} = {PLACEHOLDER_GLOSSARY[token]}"
        for token in PLACEHOLDERS
        if token in PLACEHOLDER_GLOSSARY
    )
    blocks = "\n\n".join(_construct_block(name, rec) for name, rec in constructs.items())

    return f"""\
{ETHICS_PREAMBLE}
Role: Labeling Agent
Goal: label ONE athlete utterance against a fixed sports-psychology taxonomy,
citing the exact span that justifies every label.

You are NOT doing sentiment analysis. Positive/negative is irrelevant here. You
are detecting specific, defined constructs, and only those.

## Output format

Return ONE JSON object and nothing else. No prose before or after, no code fence.

{RESPONSE_SCHEMA}

Worked example of a correct response:

{RESPONSE_EXAMPLE}

## Hard rules

- `evidence_spans` must be EXACT substrings copied character-for-character from
  the TARGET utterance. Do not paraphrase, do not fix punctuation, do not quote
  from the surrounding context. A span that is not a literal substring makes the
  whole response invalid and it will be discarded.
- Only list a construct in `labels` if you are asserting something about it.
  Constructs you do not list are treated as absent. Do not list all ten.
- WHEN IN DOUBT, DO NOT LABEL. A missed label costs a little recall. An invented
  label teaches the model to read distress into ordinary language, which is the
  one artefact this project must not produce. Apply this most strictly to
  `burnout_signal`, the most clinically loaded construct here.
- Abstaining is a correct, expected answer. Many utterances are logistics,
  scheduling or small talk and express NO construct. For those, return
  `"abstain": true` with an empty `labels` array. A labeller that never abstains
  is broken, not thorough.
- `mixed` means both poles are genuinely present, each with its own span. It does
  NOT mean "I could not decide". If you cannot decide, the answer is `none`.
- Never write clinical language ("depressed", "disorder", "burnt out as a person")
  in the rationale. Describe the language.

## Intensity anchors (0-3)

0 = not expressed, or merely neutral/factual. THIS IS THE DEFAULT.
1 = mild: expressed once, hedged, in passing, or immediately qualified away.
2 = moderate: expressed clearly without hedging, or expressed more than once.
3 = strong: intensifiers, absolutes, repetition, or functional impact
    ("can't", "every night", "completely", "it wrecks me").

Hedges ("a bit", "kind of", "I guess") pull intensity DOWN one level.
Intensifiers ("really", "completely", "can't stop") pull it UP one level.
Take the STRONGEST evidence present; do not average.

## interpretation_modifier

Applies only to cognitive_anxiety and somatic_anxiety, and only when that
construct's intensity is >= 1. `facilitative` = the athlete reads the arousal as
helpful; `debilitative` = as harmful; `unclear` = reported without evaluation,
which is the default. Set it to null when neither anxiety construct is present.

## low_resilience_explicit

Text expressing the OPPOSITE of resilience ("one mistake and I'm done") is not a
negative score. It is resilience intensity 0 PLUS `low_resilience_explicit: true`.

## Redaction placeholders

The text has been de-identified. Bracketed tokens are redactions, not words the
athlete said. Read them as the thing they stand for and never treat them as
evidence of a construct on their own:

{glossary}

## Discriminating questions -- run these before assigning

{DISCRIMINATING_QUESTIONS}

## The taxonomy

{blocks}
"""


@lru_cache(maxsize=4)
def cached_system_prompt(taxonomy_path: str | None = None) -> str:
    """Memoised system prompt, keyed on the taxonomy path.

    A run builds this once. Rebuilding it per call would be correct and
    wasteful; worse, any accidental nondeterminism in assembly would then show
    up as a cache miss on every single call, which is invisible except on the
    invoice.
    """
    tax = load_taxonomy(Path(taxonomy_path) if taxonomy_path else None)
    return build_system_prompt(tax)


def build_user_prompt(
    *,
    text: str,
    context: str | None = None,
    time_to_competition_days: int | None = None,
) -> str:
    """The per-call payload: the target utterance, optionally inside its record.

    The target is fenced with explicit markers rather than merely mentioned. An
    instruction to "label the last sentence" is a request the model can
    misresolve; a delimiter is not.

    `time_to_competition_days` is included because the taxonomy is
    *pre-competition* by construction -- `cognitive_anxiety` here means
    anticipatory worry, and a model with no idea when the event is has to infer
    that from the text.
    """
    parts: list[str] = []
    if time_to_competition_days is not None:
        parts.append(
            f"Context: this text was produced {time_to_competition_days} day(s) "
            "before the competition."
        )
    if context and context.strip() and context.strip() != text.strip():
        parts.append(
            "Full record this utterance came from (for context ONLY -- do not label it):\n"
            f"{context.strip()}"
        )
    parts.append(f"TARGET UTTERANCE (label exactly this):\n<<<{text}>>>")
    parts.append("Return the JSON object now.")
    return "\n\n".join(parts)


def prompt_hash(system: str, user: str) -> str:
    """Stable identity of one prompt payload.

    This is the deduplication key and the cache key at once, and that identity
    is the point: at `temperature: 0.0` two calls with the same payload are the
    same call, so paying for both is paying twice for one answer. Hashing the
    payload rather than the utterance text is what makes the claim true even
    though the payload also contains the parent record.
    """
    digest = hashlib.sha256()
    digest.update(SYSTEM_PROMPT_VERSION.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(system.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(user.encode("utf-8"))
    return digest.hexdigest()
