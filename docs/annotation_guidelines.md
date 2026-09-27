# Annotation Guidelines

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Version:** 1.0 - locked at Phase 4, 2026-08-08
**Governs:** `config/taxonomy.yaml` v2
**Audience:** human annotators (Phase 11) and the Labeling Agent (Phase 10)

If this document and `config/taxonomy.yaml` ever disagree, **`taxonomy.yaml` wins** and this
file must be corrected. Do not annotate from memory - keep this open.

---

## 0. Read this first: what you are and are not doing

You are labelling **language**, not people.

A label means *"this span of text expresses this construct."* It does **not** mean the person
who wrote it has that psychological state, and it certainly does not mean they have a
disorder. You are not diagnosing anyone. You are not a clinician here, and even if you are a
clinician elsewhere, that is not the role in this task.

Three rules follow from this and they are not negotiable:

1. **Label the text in front of you.** Do not use outside knowledge about the athlete, the
   result of the competition, or anything you have read about them elsewhere.
2. **Never write a clinical term into a note** ("depressed", "has an anxiety disorder",
   "clearly burnt out as a person"). Describe the language instead.
3. **If a record contains identifying information that survived de-identification, stop and
   flag it** rather than annotating it. Report it to the project owner.

The output of this project is a research and decision-support tool. Mislabelled data becomes
a mislabelled risk score, and a mislabelled risk score attached to a real athlete can do real
harm. That is why the "when in doubt, label 0" rule below exists.

---

## 1. The unit of annotation

- A **record** is one utterance or short passage of pre-competition athlete text (an
  interview answer, a press-conference turn, a social post, a journal entry).
- Within a record you mark **spans**. A span is a contiguous stretch of text that carries the
  evidence for a construct.
- Every construct label must be **anchored to at least one span**. A label with no span is
  invalid. This is what makes the model's span-level explanations verifiable later - it is a
  core contribution of the paper, so it is not optional bookkeeping.

### Span-selection rules

| Situation | Rule |
|---|---|
| How much text to select | The **minimal span that a reader could not remove without losing the evidence**. Usually a clause; sometimes a sentence. |
| Trailing punctuation | Exclude it. |
| Discourse filler ("um", "you know", "I mean") | Exclude unless it carries the evidence. |
| Evidence split across two clauses | Select **one span per clause**, both attached to the same construct label. Do not select the connecting text between them. |
| Evidence spans a whole sentence and cannot be shortened | Select the sentence. |
| Pronoun resolves to earlier text | Select the clause containing the pronoun, not the antecedent. |

### Overlapping and multi-label spans

- **Spans may overlap.** This is expected and correct.
- **One span may carry several constructs.** "This field is way above me and I'm dreading it"
  is `appraisal_orientation = threat` *and* `cognitive_anxiety`. Label both.
- Do **not** artificially split a span to force a one-label-per-span structure.
- Do **not** duplicate a construct on the same record twice for the same evidence. If a record
  expresses one construct across three separate spans, that is **one construct label with
  three spans**, at the intensity of the strongest evidence.

---

## 2. The label model

Two label types. `taxonomy.yaml` states which type each construct uses.

### 2a. Graded constructs

`cognitive_anxiety`, `somatic_anxiety`, `self_confidence`, `perceived_stress`,
`burnout_signal`, `resilience`.

Record **intensity 0–3**. Presence is implied: intensity ≥ 1 means present.

| Intensity | Name | Anchor - what it takes to earn this level |
|---|---|---|
| **0** | None | The construct is not expressed. Also the value for a merely neutral or factual statement. **This is the default.** |
| **1** | Mild | Expressed once, hedged, in passing, or immediately qualified away. Reads as an ordinary, in-range reaction. *"A few nerves, but nothing unusual."* |
| **2** | Moderate | Expressed clearly and without hedging, or expressed more than once across the record. Reads as something the athlete is actually contending with. *"I'm nervous about this one. I keep coming back to it."* |
| **3** | Strong | Expressed with intensifiers, absolutes, repetition, escalation, or functional impact ("can't", "always", "completely", "every night", "it wrecks me"). Reads as dominating the record. *"I'm terrified. I haven't slept in three nights and I can't stop thinking about it."* |

**Calibration tips**

- Intensity is about the **language**, not your estimate of the person's true state.
- Hedges ("a bit", "kind of", "maybe", "I guess") pull intensity **down** one level.
- Intensifiers ("really", "completely", "can't stop", "every") pull intensity **up** one level.
- Repetition across the record pulls **up**; a single mention pulls **down**.
- Do not average across a record - take the **strongest** evidence present.
- Sarcasm and joking: label the literal content at **reduced** intensity (usually 1), and add
  a note. Do not label 0 just because it was framed as a joke.

### 2b. Categorical constructs

`motivation_orientation`, `attentional_focus`, `coping_style`, `appraisal_orientation`.

Pick **one** label from the construct's `labels` list, then record intensity **for that label**
using the same 0–3 anchors above.

- `none` is the default and always takes intensity 0.
- `mixed` is for genuine co-presence of *both* poles in the same record, each independently
  supported by a span. `mixed` is **not** a synonym for "I couldn't decide" - if you cannot
  decide, the answer is `none`.
- When you use `mixed`, you must mark a span for **each** pole.

### 2c. The interpretation modifier

Applies only to `cognitive_anxiety` and `somatic_anxiety`, and only when that construct's
intensity is ≥ 1.

| Label | When to use |
|---|---|
| `facilitative` | The athlete evaluates the arousal as **helpful** - sharpening, energising, a sign of readiness. |
| `debilitative` | The athlete evaluates the arousal as **harmful** - undermining, derailing, something to be rid of. |
| `unclear` | **Default.** The arousal is reported without evaluation. |

This distinction matters more than it looks. Two athletes can report identical anxiety
intensity and carry very different risk depending on whether they read those nerves as fuel or
as a problem. Do not collapse it into intensity - record it separately.

### 2d. Low-resilience flag

`resilience` is scored 0–3 for *expressed* resilience. Text expressing the **opposite**
("one mistake and I'm done") is not negative resilience - it is `resilience = 0` **plus** the
boolean note `low_resilience_explicit: true`. Explicit fragility is different from silence, and
the risk model in Phase 15 needs to tell them apart.

---

## 3. Decision procedure

Run this in order for every record.

1. **Read the whole record once** before marking anything. Context changes labels.
2. **Ask: is this about the upcoming competition, or about the athlete's readiness for it?**
   If neither, most constructs are 0.
3. **Mark spans first, assign labels second.** Find the evidence, then name it. Doing it the
   other way round is how annotators talk themselves into labels.
4. **For each construct, ask the discriminating question** (Section 4) before assigning.
5. **Assign intensity** using the anchors in 2a.
6. **Apply the interpretation modifier** if an anxiety construct is ≥ 1.
7. **Re-read your labels against the spans.** If a span does not obviously support its label to
   a stranger, delete the label.
8. **When in doubt, label 0.** See Section 6.

---

## 4. Discriminating questions (the confusable pairs)

These five confusions cause most disagreement between annotators. Learn them.

**`cognitive_anxiety` vs. `perceived_stress`**
→ *Is the athlete worried about the OUTCOME, or overwhelmed by the DEMAND?*
Outcome worry = cognitive_anxiety. Demand-exceeds-resources = perceived_stress. Both can be
true at once; label both when both have spans.

**`cognitive_anxiety` vs. `appraisal_orientation = threat`**
→ *Is this worry, or is this a positioning of self against the demand?*
"I'm scared I'll mess up" = anxiety. "This field is beyond me" = threat appraisal. They very
often co-occur - that is fine, label both.

**`self_confidence` vs. `resilience`**
→ *Expected success, or recovery if it goes wrong?*
"I'll win" = confidence. "If it goes wrong I'll come back" = resilience. No adversity frame
means it is not resilience.

**`somatic_anxiety` vs. `burnout_signal`**
→ *Acute arousal before this competition, or depletion built up over time?*
Shaking hands the night before = somatic_anxiety. "Drained, and I don't care anymore" =
burnout_signal. Plain training fatigue is neither.

**`coping_style = avoidance` vs. `attentional_focus = distracted`**
→ *Is a STRATEGY being described, or is attention simply going somewhere unhelpful?*
"I try not to think about it" = avoidance coping (a strategy). "I keep watching the other
lane" = distracted (no strategy). Naming an emotion is neither.

---

## 5. Worked examples

**Example 1**

> "Honestly the nerves have been brutal all week - I've barely slept, stomach's a mess. But
> that's normal for me before a big one, it means I'm switched on. I know my plan and I'll
> stick to it."

| Construct | Label | Intensity | Span |
|---|---|---|---|
| somatic_anxiety | present | 3 | "I've barely slept, stomach's a mess" |
| cognitive_anxiety | present | 2 | "the nerves have been brutal all week" |
| interpretation_modifier | facilitative | - | "it means I'm switched on" |
| self_confidence | present | 2 | "I know my plan and I'll stick to it" |
| attentional_focus | focused | 2 | "I know my plan and I'll stick to it" |

*Why:* high somatic intensity ("barely", "mess") but explicitly read as helpful - this is
exactly the case where intensity alone would overstate risk. Note the same span supports two
constructs; that is allowed.

**Example 2**

> "There's a lot going on - exams, and selection is next month, and now this. Everyone wants
> something. I just want to get through it without embarrassing myself."

| Construct | Label | Intensity | Span |
|---|---|---|---|
| perceived_stress | present | 3 | "There's a lot going on"; "Everyone wants something" |
| motivation_orientation | avoidance | 2 | "without embarrassing myself" |
| cognitive_anxiety | present | 1 | "without embarrassing myself" |
| appraisal_orientation | none | 0 | - |

*Why:* demand-exceeds-resources, not outcome worry, so the headline label is stress not anxiety.
"Get through it without embarrassing myself" is avoidance motivation and carries mild outcome
worry. No self-versus-demand positioning, so appraisal is `none` - **not** `threat`, even
though it feels negative.

**Example 3**

> "Been at this fifteen years. I'll turn up and do the job. Not much else to say."

| Construct | Label | Intensity | Span |
|---|---|---|---|
| self_confidence | present | 1 | "I'll turn up and do the job" |
| everything else | - | 0 | - |

*Why:* terse and flat. It is tempting to read burnout into "not much else to say" - **do not**.
There is no exhaustion, devaluation, or reduced-accomplishment language. This is the
when-in-doubt rule in action.

**Example 4**

> "I've been avoiding the video from last time. Coach wants to go through it and I keep putting
> it off. If I have a start like that again I know I'll unravel."

| Construct | Label | Intensity | Span |
|---|---|---|---|
| coping_style | avoidance | 3 | "avoiding the video"; "keep putting it off" |
| resilience | - | 0 | - |
| *(flag)* | `low_resilience_explicit: true` | - | "I know I'll unravel" |
| cognitive_anxiety | present | 2 | "If I have a start like that again" |

*Why:* a described strategy of disengagement = avoidance coping, not distraction. Explicit
fragility gets `resilience = 0` **plus** the flag, not a negative score.

---

## 6. The when-in-doubt rule

> **If you are not confident a construct is expressed, label it 0 (or `none`).**

This is the single most important rule in this document, and it is deliberate rather than lazy.

The risk here is asymmetric. A missed label costs us a little recall. A **hallucinated** label
teaches the model to see anxiety, stress, or burnout in ordinary language - and a model that
over-reads distress in athlete text is precisely the harmful artefact this project must not
produce. Under-labelling is recoverable; over-labelling poisons both the dataset and the ethics
position of the paper.

Applied specifically:

- Do not infer a construct from **tone** alone. Terse ≠ burnt out. Enthusiastic ≠ confident.
- Do not infer from **topic**. Mentioning a rival is not distraction.
- Do not infer from **what usually follows**. Nerves do not imply threat appraisal.
- Apply this **most strictly** to `burnout_signal`, which is the most clinically loaded label
  in the taxonomy.

---

## 7. Uncertainty, disagreement, and escalation

- Mark a record `uncertain: true` when you labelled it but would not defend it. These records
  are routed to adjudication and are reported in the paper's agreement analysis.
- Mark a record `escalate: true` and **do not label it** when it is unreadable, off-topic, not
  athlete-authored, not pre-competition, or still contains identifying information.
- Never discuss specific records with the other annotator before both passes are complete -
  that inflates the agreement statistic and makes it worthless.
- Adjudication happens after both passes, with the project owner, against this document. If
  adjudication reveals a rule this document does not cover, **the fix is to amend this document
  and re-run the affected batch**, not to settle it verbally.

---

## 8. Quality checks before you submit a batch

- [ ] Every non-zero construct label has at least one span.
- [ ] Every span sits inside its record's text and contains no stray punctuation.
- [ ] No `mixed` label without a span for each pole.
- [ ] No interpretation modifier on an anxiety construct scored 0.
- [ ] No clinical language anywhere in your notes.
- [ ] Any record with surviving identifying information is flagged, not labelled.
- [ ] You applied the when-in-doubt rule at least once - if you labelled everything with
      confidence across a whole batch, re-check the batch.

---

## 9. Construct quick reference

Full definitions, citation anchors, and edge cases are in `config/taxonomy.yaml`.

| Construct | Type | Labels / range | Risk direction | Anchor |
|---|---|---|---|---|
| cognitive_anxiety | graded | 0–3 | raises | CSAI-2 [Martens1990; Cox2003] |
| somatic_anxiety | graded | 0–3 | raises | CSAI-2 [Martens1990; Cox2003] |
| self_confidence | graded | 0–3 | lowers | CSAI-2 [Martens1990; Cox2003] |
| motivation_orientation | categorical | approach / avoidance / mixed / none | avoidance raises | [Elliot2001; Deci2000] |
| perceived_stress | graded | 0–3 | raises | PSS [Cohen1983]; [Toth2025] |
| attentional_focus | categorical | focused / distracted / mixed / none | distracted raises | TAIS [Nideffer1976] |
| burnout_signal | graded | 0–3 | raises | ABQ [Raedeke2001]; [Madigan2020] |
| coping_style | categorical | task_focused / avoidance / mixed / none | avoidance raises | [Nicholls2007; Madigan2020] |
| resilience | graded | 0–3 | lowers | CD-RISC [Connor2003]; [Li2025] |
| appraisal_orientation | categorical | challenge / threat / mixed / none | threat raises | TCTSA [JonesMeijen2009]; [Toth2025] |
| *interpretation_modifier* | modifier | facilitative / debilitative / unclear | debilitative raises | [Jones1992; Cox2003] |

All bracketed keys resolve to entries in `paper/refs.bib`.

---

## 10. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-08 | Initial complete rubric. Phase 4. Taxonomy v2 locked; all 11 instrument anchors resolved to primary records with DOIs (except `Martens1990`, a pre-DOI book chapter, paired with `Cox2003` which has one). |

Construct set is **frozen at Phase 12** after the inter-annotator agreement check. Any
construct with poor agreement is a candidate to drop.
