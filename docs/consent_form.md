# Consent form — donating a pre-competition reflection

**Study:** Pre-Competition Psychological Risk Profiling of Athletes
**Researcher:** Saikalyan, undergraduate student, SRM Institute of Science and Technology (SRMIST)
**Contact:** `gsaikalyan2@gmail.com` — subject line `[SPORTS-RISK-NLP]`
**Form version:** 1.0 (2026-08-12) — allow-list category **A3**, `docs/ethics.md` §3.1, §4, §7

> **Read this before you write anything.** If any part is unclear, email and ask. Do not donate
> text you would be uncomfortable seeing analysed by a computer program and described, in
> aggregate, in an academic paper.

---

## 1. What the study is

I am building a research system that reads text an athlete writes *before* a competition and
detects psychological constructs in the language — things like anxiety, confidence, motivation,
and how a person frames the upcoming event. The system combines those into an interpretable
"risk" index intended for research and for supporting conversations, not for making decisions
about anyone.

It is an undergraduate research project aimed at an IEEE conference paper.

## 2. What I am asking you to do

Write **one short reflection (roughly 80–250 words)** about an upcoming competition — a race,
meet, match, or event you have coming up, or one you remember clearly.

Useful prompts, though you can ignore them and write freely:

- What is on your mind about this event?
- What are you looking forward to, and what are you not?
- How is your preparation feeling?

Along with it, tell me:

- roughly **how many days** until the event (or how many days it was, if you're recalling one)
- your **sport**
- your **competition level** — one of: club, regional, national, international, elite

**Time:** 10–15 minutes. **Payment:** none — this is unfunded student research.

## 3. What happens to your words

1. Your text is **de-identified** before anything reads it. Names, usernames, contact details,
   URLs, locations, club and school names, and event names that would pin you down are replaced
   with placeholders. This runs automatically and is checked against a test set.
2. It is stored in a private research repository, **not published as raw text**.
3. It may be **labelled** — by me, and by one other person — for the psychological constructs
   above.
4. It may be used to **train and evaluate** machine-learning models within this project.
5. Findings are reported **in aggregate**. Statistics, model scores, and charts.

## 4. What will never happen

- **Your text will never be published word-for-word.** Not in the paper, not in a figure, not in
  a demo. A distinctive sentence is searchable and could identify you, so any example shown
  publicly will be synthetic or rewritten past the point of recognition.
- **No score about you as an individual will ever be published or shown to anyone.**
- **Nobody who knows you gets your text or any result about you** — not a coach, not a teammate,
  not a club, not your institution.
- **No diagnosis.** This system does not and cannot assess your mental health. It detects patterns
  in language. A high score means "this text uses language associated with pre-competition
  pressure" — nothing more. It is not a clinical instrument and has never been clinically
  validated.
- **Your text will not be sold, shared with any company, or redistributed.**

## 5. Who can take part

- You must be **18 or older.**
- You must be writing about **your own** competition, in your own words.
- Please **do not write about injury, illness, medical treatment, medication, or a diagnosed
  condition.** That is health data, it needs protections this project does not have, and any
  donation containing it will be deleted rather than used. If those things are what's actually on
  your mind before this event, this study is not the right place for it.

## 6. Risks, honestly

The main risk is **re-identification**: if you describe an unusual event or an unusual personal
detail, someone determined could in principle work out who you are, even after de-identification.
The protections in §3 and §4 exist to make that unlikely. They cannot make it impossible.

Writing about pre-competition nerves may also bring up feelings you would rather not sit with.
You can stop at any point.

## 7. Your rights

- **Taking part is voluntary.** You can decline, and you can stop while writing.
- **You can withdraw at any time**, without giving a reason. Email the address above. Your text
  is removed from the dataset and from any future release.
- **One limit on withdrawal, stated plainly rather than glossed:** if a model has already been
  trained using your text, **that model will not be retrained** to remove your contribution.
  Retraining retroactively is not something this project can do. What withdrawal guarantees is
  that your text is deleted and is not used in anything built from that point on.
- **You can ask for a copy** of what I hold from you.
- **You can ask what the study found**, once it is written up.

Contact for all of the above:

> **`gsaikalyan2@gmail.com`** — subject line `[SPORTS-RISK-NLP]`
> I aim to acknowledge within **7 days**. Withdrawals are actioned before the next release.

*(Interim contact. This project intends to replace it with an institutional SRMIST address and a
named supervisor before anything is published, so the route outlives one personal inbox —
`docs/ethics.md` §7.1, OPEN-006.)*

## 8. Ethics review

SRMIST determined this work **exempt** from full institutional ethics review, as secondary
analysis of public, licensed, consented, and synthetic text (`docs/ethics.md` §3.4). The
documentary record of that determination is still being obtained (OPEN-005).

---

## 9. Your consent

Please copy the block below into your email or the form, and complete it. **Typing your name in
the last line is your signature.**

```
I confirm that:

[ ] I am 18 years of age or older.
[ ] I have read and understood this form, version 1.0.
[ ] I have had the chance to ask questions.
[ ] I understand taking part is voluntary and I can withdraw at any time.
[ ] I understand that if a model has already been trained using my text, that model
    will not be retrained, and that withdrawal means deletion plus no future use.
[ ] I understand my words will never be published verbatim and no individual score
    about me will be published.
[ ] I understand this is not a clinical or diagnostic assessment.
[ ] I confirm my text does not describe injury, illness, medical treatment, or a
    diagnosed condition.
[ ] I consent to my text being de-identified, labelled for psychological constructs,
    and used to train and evaluate models in this research project.

Sport:              ____________________
Competition level:  ____________________   (club / regional / national / international / elite)
Days to the event:  ____________________

Name:  ____________________
Date:  ____________________
```

---

### Note for the researcher, not the donor

Keep signed forms **outside the repository**. The consent record contains a real name and is
exactly the kind of file `.gitignore` will not save you from if it is committed once. Store the
donation text in `data/raw/<source_id>/` under an `A3_consented_donation` descriptor, and keep the
name↔`record_id` mapping in a separate file that is never committed — it is needed only to action
a withdrawal.

Every `requires` field in `config/data_sources_allowlist.yaml` under `A3_consented_donation` must
be satisfiable from the completed form: written consent naming this project, the construct-labelling
purpose stated, the withdrawal right explained and honoured, donor is an adult, institutional
review resolved, and the §7.1 contact route present.
