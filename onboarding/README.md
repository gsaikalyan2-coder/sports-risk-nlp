# Annotator onboarding

You have been asked to be the **second annotator** on a study of how athletes talk before
competing. Thank you — this document is everything you need, and it is honest about the size
of the ask.

*(Structure borrowed from the `sciknoworg/ALD-E-ImageMiner` annotation project's onboarding
convention.)*

---

## 1. What the project is, in one paragraph

We are building a dataset that marks where in an athlete's pre-competition text specific,
**defined** sports-psychology constructs appear — anxiety, confidence, stress, coping style
and six others, each drawn from a validated instrument such as the CSAI-2 or the ABQ. A model
is trained on it and produces an interpretable risk score with the evidence highlighted. Your
annotations are the ground truth everything is measured against.

## 2. What you are and are not doing

**You are labelling language, not people.**

A label means *"this span of text expresses this construct."* It does **not** mean the writer
has that psychological state, and it certainly does not mean they have a disorder. You are not
diagnosing anyone, and if you happen to be a clinician, that is not the role here.

Three non-negotiable rules:

1. **Label the text in front of you.** No outside knowledge about anyone.
2. **Never write a clinical term in a note** — not "depressed", not "burnt out as a person".
   Describe the language.
3. **If a record contains identifying information, stop and flag it.** Do not annotate it.
   Tell the project owner. The text has been through automatic de-identification, so anything
   surviving is a defect we need to know about immediately.

**The corpus you will see is synthetic** — generated from templates, not written by real
athletes. That does not lower the standard: the rubric is the same, and the agreement number
your work produces is what makes the dataset publishable.

## 3. The commitment, stated honestly

| | |
|---|---|
| Calibration batch (`gold_dev`) | 100 items |
| Evaluation batch (`gold_eval`) | 400 items |
| Per item | up to 10 constructs, each needing an intensity and a highlighted span |
| Time per item | **unknown — you and the owner will measure it on `gold_dev`** |

Nobody has timed this yet. That is deliberate: you will time the calibration pass, and if 400
items turns out to be unreasonable, the construct set gets trimmed before the evaluation batch
rather than after. Say so if it is too much. An annotator who rushes the last 200 items
produces a worse dataset than one who annotates 200 carefully.

## 4. Setup

```bash
git clone <the repo>
cd sports-risk-nlp
pip install potato-annotation==2.7.1

python scripts/run_annotation.py --build --batch gold_dev
cd annotation/gold_dev
potato start config.yaml
```

Open <http://localhost:8000> and log in with **your own annotator id** (the owner will add you
to `config/annotators.yaml`; it will be something like `A2`).

Keep **`docs/annotation_guidelines.md` open beside you the whole time.** It is the rubric. Do
not annotate from memory — the whole point of an agreement study is that two people applied
the *same written rules*.

## 5. How to annotate one item

The screen shows the **full record** at the top with one sentence highlighted, and that
highlighted sentence again below as the thing you are labelling.

1. **Read the whole record first.** Context changes labels. This is why it is shown.
2. **Mark spans, then name them.** Find the evidence, then decide which construct it is —
   doing it the other way round is how annotators talk themselves into labels.
3. Select the **minimal span** a reader could not remove without losing the evidence. Usually a
   clause. Exclude trailing punctuation.
4. Set the **intensity** for each construct you marked: 1 mild, 2 moderate, 3 strong. Leave it
   at 0 for everything you did not mark.
5. Spans may **overlap**, and one span may carry **several constructs**. That is expected.
6. For the four categorical constructs, mark the pole (`approach` / `avoidance`, etc.). If both
   poles are genuinely present, **mark a span for each** — that is what records "mixed".
7. **When in doubt, do not label.** This is the single most important rule. A missed label
   costs a little recall; an invented one teaches the model to read distress into ordinary
   language, which is the one thing this project must not produce. Apply it most strictly to
   `burnout_signal`.
8. Tick **uncertain** if you labelled it but would not defend it. That is useful information,
   not a failure.
9. Tick **ESCALATE** and label nothing if the item is unreadable, off-topic, not about an
   upcoming competition, or contains identifying information.

Most items will have **one or two** constructs. Many will have **none** — logistics, travel,
small talk. Marking nothing is a correct answer and a common one.

## 6. The two rules that protect the statistic

1. **Do not discuss specific records with the other annotator until you have both finished.**
   Not "just this one". Discussing items inflates the agreement number, it cannot be undone,
   and it makes the headline result of the paper worthless. Questions about the *rubric* are
   fine and encouraged — questions about a specific item are not.
2. **Do `gold_dev` completely before anyone opens `gold_eval`.** After `gold_dev` you and the
   owner will compare, argue, and amend the guidelines. That argument is supposed to happen,
   and `gold_dev` exists to absorb it.

## 7. When you finish a batch

```bash
python scripts/run_annotation.py --ingest --batch gold_dev --annotator <your-id>
```

This checks every span really is a substring of its sentence and that your intensities and
spans agree with each other. If something is inconsistent it will tell you which item and why,
and write nothing until you fix it in Potato and re-run. That is not you being marked — it is
the tool catching the errors that are invisible in a spreadsheet.

## 8. Your name will not be in the paper

Annotator ids are pseudonyms (`A1`, `A2`). The paper reports per-annotator agreement
statistics, and a published table that names two students is a disclosure nobody agreed to.
If you would like to be credited, say so — that is your call, not a default.

## 9. Questions worth asking

- "What is the difference between `cognitive_anxiety` and `perceived_stress` again?" →
  guidelines §4 has five discriminating questions; they cover most confusion.
- "Is this `mixed` or `none`?" → if you cannot decide, it is `none`. `mixed` means both poles
  are genuinely there with evidence for each.
- "This feels negative but nothing fits." → then nothing is the answer. Do not infer from tone.
