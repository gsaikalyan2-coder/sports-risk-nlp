# Ethics & Data Governance Policy

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Version:** 1.0 — Phase 5, 2026-08-08
**Status:** Binding on all phases and all agents. No data may be collected, processed, labelled, or released except under this policy.
**Companion file:** `config/data_sources_allowlist.yaml` (machine-readable allow-list; enforced by `src/ingestion/` from Phase 7)

This document is written to be **cited directly in the paper's Ethics & Limitations section**.
Sections 2, 3, and 8 are drafted for that purpose.

---

## 1. Why this policy exists, and why it comes before the data

This project builds a system that reads an athlete's words and outputs a number labelled
*psychological risk*. That artefact is useful and it is also dangerous, and the danger is not
hypothetical or distant. A risk score attached to a named person can influence selection, funding,
contract, and media treatment. It can follow someone. It can be wrong in ways that are hard to
contest, because a number carries an authority that a sentence does not.

Building the guardrails **before** touching data is deliberate. Retrofitted ethics tends to
rationalise decisions already made. Phase 5 sits before Phase 7 ingestion precisely so that this
document constrains the corpus rather than describing it after the fact.

---

## 2. What this system is, and what it is not

### 2.1 Non-diagnosis statement *(paper-citable)*

> This system does not diagnose. It detects linguistic expression of validated
> sports-psychology constructs in text and combines them into an interpretable index. A high
> score means *this text expresses language associated with elevated pre-competition
> psychological risk*. It does not mean the author has an anxiety disorder, is clinically
> burnt out, or is unwell. No output of this system constitutes a clinical assessment, and no
> output should be used as one.

The system is not a clinical instrument. It has not been clinically validated, it was not
developed with a clinical population, and the constructs it detects — although drawn from
validated instruments — are being detected in **text**, not elicited through the instruments
themselves. The gap between "scores high on the CSAI-2" and "writes like someone who would" is
real and unquantified, and the paper must say so.

### 2.2 Intended use

- Research into the relationship between athlete language and psychological constructs.
- Decision-**support**: surfacing to a coach or practitioner that a passage may warrant a
  human conversation.
- A methods contribution: construct-grounded labelling and two-level interpretability.

### 2.3 Prohibited uses *(binding)*

The system must never be used to:

1. Diagnose, screen for, or infer any mental-health condition in any individual.
2. Inform **selection, roster, contract, funding, disciplinary, or medical decisions** about a
   real person.
3. Generate claims about a **named** athlete's psychological state, publicly or privately.
4. Monitor athletes without their knowledge, including by an institution over its own athletes.
5. Rank, league-table, or compare identified individuals by risk score.
6. Substitute for a conversation with a qualified professional.

These prohibitions are carried in the model card, the released README, and the dashboard UI —
not only here. A prohibition nobody reads is not a control.

### 2.4 Non-goal: this is not a duty-of-care mechanism

If deployed text genuinely indicated someone in distress, this system has no capacity to
respond, escalate, or help. It is not a safeguarding pathway and must not be presented as one.
Any real deployment would need a human-in-the-loop referral route designed by people qualified
to design it. That is out of scope for this project and is named as a limitation.

---

## 3. Data source allow-list *(paper-citable)*

Categories are enumerated machine-readably in `config/data_sources_allowlist.yaml`. Phase 7
ingestion **must** validate every source against that file and refuse anything unlisted. The
default for an unlisted source is **deny**.

### 3.1 Permitted

| # | Category | Conditions |
|---|---|---|
| **A1** | **Existing public research datasets** with an explicit licence permitting research use | Licence recorded in `provenance.json`; attribution preserved; redistribution only if the licence allows |
| **A2** | **Synthetic text** generated for this project | Marked `synthetic: true` in every record; never presented as real athlete speech; generation prompts version-controlled |
| **A3** | **Explicitly consented text** donated for this research | Written informed consent naming this project and its purpose; withdrawal right honoured (§7) |
| **A4** | **Officially published press-conference and post/pre-match interview transcripts** | Public, professional-capacity speech, published by the org or outlet; de-identified per §5; subject to §3.3 |

Per `CLAUDE.md` §10 (Q3, confirmed 2026-07-23): **A1 is the primary strategy.** The fallback, if
coverage proves thin, is a hybrid of **A2 for training volume plus a small real gold set**, to be
revisited at Phase 7.

### 3.2 Prohibited

| Category | Why |
|---|---|
| Scraping personal social-media accounts | Public ≠ consented. Personal posts are not professional-capacity speech and users do not anticipate psychological profiling. |
| Any text from an identifiable **minor** (under 18) | Youth athletes are a vulnerable population; profiling them requires ethics-board review and guardian consent that this project does not have. |
| Private communications — DMs, team chats, medical notes, counselling records, journals not donated under A3 | No consent, and the last two are special-category health data. |
| Any source whose licence forbids research use, or whose terms of service forbid the collection method | Legal exposure and reviewer challenge. |
| Text obtained by scraping behind authentication or a paywall | Circumvents access control. |
| Text about an athlete's **health, injury, or treatment** as its subject matter | Special-category data; outside the pre-competition psychological-language scope. |
| Any source that cannot produce a complete `provenance.json` | Unverifiable provenance is unpublishable. |

### 3.3 The public-figure question, resolved

Category A4 is the ethically hardest permission here and is documented deliberately rather than
assumed.

A professional athlete speaking at an official press conference is a public figure making
public, professional-capacity statements. Analysing that speech is standard practice in sports
media research. **But** the fact that speech is lawfully public does not make every downstream
use of it appropriate — and inferring psychological state is a substantially more intrusive use
than the speaker anticipated when answering a question about tactics.

Conditions on A4, all mandatory:

1. **De-identify anyway** (§5), even though the speaker is publicly known. The corpus stores no
   names.
2. **No individual-level published output.** Aggregate and worked examples only. Any example
   appearing in the paper, the dashboard, or a figure must be **synthetic or paraphrased beyond
   re-identification** — never a quotable real utterance tied to a real person.
3. **No named-athlete claim, ever**, including in informal discussion of results.
4. If a passage would embarrass or harm its speaker if attributed, it is excluded regardless of
   its research value.

If a reviewer, an ethics board, or the owner judges A4 too permissive, the project falls back to
**A1 + A2 + A3 only**. That reduces ecological validity and would be reported as a limitation —
it does not break the project.

### 3.4 Institutional review

This project should be checked against SRMIST's requirements for human-subjects and secondary-data
research **before** any A3 or A4 collection begins. If institutional review is required, obtain it;
if the work is exempt as secondary analysis of public/licensed data, **record the exemption
determination in writing** and cite it in the paper. An unrecorded assumption of exemption is a
reviewer challenge waiting to happen.

**Owner action required — this is not something the agents can resolve.**

---

## 4. Consent and licensing rules

- Every source directory in `data/raw/` carries a `provenance.json`: source identity, URL or
  citation, collection date, licence or consent basis, permitted uses, redistribution
  permission, and the allow-list category (A1–A4).
- **No provenance, no ingestion.** Phase 7's gate enforces this.
- Licences are recorded verbatim, not summarised.
- Where redistribution is not permitted, the release ships **derived artefacts only** —
  labels, span offsets, and retrieval instructions — never the source text. See §9.
- Consent under A3 is written, names this project specifically, states that text will be
  labelled for psychological constructs, and explains the withdrawal right.

---

## 5. De-identification policy

**Requirement:** every record passes de-identification before labelling, modelling, or human
review. No exceptions, no "it's already public" carve-out. This is the specification that
`src/preprocessing/deidentify.py` implements in Phase 8.

### 5.1 What is removed or replaced

| Category | Action |
|---|---|
| Person names — athletes, coaches, family, opponents, officials | Replace with typed placeholders: `[ATHLETE]`, `[COACH]`, `[TEAMMATE]`, `[OPPONENT]`, `[PERSON]` |
| Social handles, usernames, emails, phone numbers, URLs | `[HANDLE]`, `[CONTACT]`, `[URL]` |
| Team, club, school, and sponsor names | `[TEAM]`, `[ORG]` |
| Specific venues, cities, countries | `[LOCATION]` |
| Named competitions and event editions | `[EVENT]` |
| Exact dates | Replace with the relative field `time_to_competition` (Phase 7) |
| Jersey numbers, rankings, and other quasi-identifiers | `[ID]` |
| Any health, injury, or treatment detail | Removed entirely, not placeholdered |

### 5.2 Rules

- **Placeholders are typed, not blanked.** `[COACH]` preserves the linguistic structure the model
  needs; a blank destroys it.
- **De-identification is not reversible.** No mapping table from placeholder back to identity is
  created or stored. If one would be needed for a later analysis, that analysis is out of scope.
- **Quasi-identifier combinations count.** Sport plus event plus finishing position can re-identify
  as surely as a name. Where the combination is distinctive, generalise the field.
- **Manual audit on a stratified sample** every phase that touches data — automated NER misses
  nicknames, in-group references, and unusual spellings. Failures are logged.
- **Annotators flag, not fix.** A record with surviving identifiers is escalated per
  `docs/annotation_guidelines.md` §7, never quietly labelled.

### 5.3 Known limitation

Automated de-identification is imperfect, and this must be stated in the paper rather than
implied to be solved. Residual re-identification risk is highest for A4 press-conference text,
where a distinctive turn of phrase from a well-known athlete may be searchable even with names
removed. This is a principal reason for the §3.3 rule that **no real utterance is ever published
verbatim**.

---

## 6. Bias, fairness, and validity risks

Named honestly, because the paper is stronger for naming them than for being caught by a reviewer.

| Risk | Substance | Mitigation |
|---|---|---|
| **Language and cultural bias** | Emotional expression is culturally patterned. Understatement in one culture and intensity in another can carry identical internal states. A model trained mostly on one English-speaking sporting culture will systematically misread others. | Record language and region where known; report performance by stratum; state the bound explicitly. |
| **Construct validity gap** | The instruments were validated on **questionnaire responses**, not spontaneous speech. Detecting "CSAI-2 cognitive anxiety" in an interview is an analogical extension, not a measurement. | Frame throughout as *construct-grounded labelling of language*, never as administering the instrument. Report inter-annotator agreement as the reliability evidence available. |
| **Sport and gender skew** | Corpus availability will over-represent well-covered, well-funded, typically men's sports. | Report the corpus composition; do not claim generality beyond it. |
| **Media-training artefact** | Elite athletes are coached in what to say. Press-conference text may measure media training more than psychological state. | Named as a validity threat; a reason the corpus records source type per record. |
| **Silence is not absence** | An athlete who says nothing about anxiety may be highly anxious. The system sees expression, not state. | Encoded in the `when in doubt, label 0` rule; the score is explicitly a *language* index. |
| **Label noise from silver labels** | LLM-proposed labels inherit the labelling model's own cultural and linguistic priors. | Human gold anchor, confidence thresholds, Phase 12 refinement, agreement reporting. |
| **Automation bias** | A coach shown a calibrated-looking 0.78 will trust it more than the evidence warrants. | Dashboard shows spans and per-construct contributions, never a bare number; prohibited-use notice in the UI. |

---

## 7. Withdrawal, correction, and incident response

- **Withdrawal (A3):** a donor may withdraw at any time without giving a reason. Their records are
  removed from `data/`, and from any future release. Models already trained are **not** retrained
  retroactively, and consent language states this plainly rather than promising otherwise.
- **Correction:** any party may report a record as mis-sourced, under-de-identified, or wrongly
  labelled. Reports are logged and triaged before the next release.
- **Incident (suspected re-identification or leak):** stop processing, quarantine the affected
  records, notify the owner, record it in `docs/security.md`, and do not publish the affected
  subset. A near-miss is logged the same as a hit.
- **Contact route** must appear in the released README and model card, or none of the above is
  reachable in practice.

---

## 8. Limitations statement *(paper-citable draft)*

> This work has several limitations that bound its interpretation. First, the system detects
> **linguistic expression** of psychological constructs, not the constructs themselves; the
> relationship between how an athlete writes or speaks and their measured psychological state is
> assumed, not established, and no concurrent instrument administration was possible. Second, the
> source instruments were validated on questionnaire responses rather than spontaneous language,
> so our labels are construct-*grounded* rather than construct-*equivalent*. Third, the corpus is
> limited in language, culture, sport, and gender coverage, and emotional expression varies
> systematically along all four axes; performance should not be assumed to transfer beyond the
> reported strata. Fourth, elite athlete speech is subject to media training, which may attenuate
> or mask expression. Fifth, absence of construct language is not evidence of absence of the
> construct. Sixth, automated de-identification is imperfect and residual re-identification risk
> cannot be excluded. Finally, the risk index is **not clinically validated** and must not inform
> any decision about an individual.

---

## 9. Release policy

Before any public release of code, data, or model:

- [ ] Every released record de-identified and manually spot-audited.
- [ ] Source text released **only** where the licence permits; otherwise labels, span offsets, and
      retrieval instructions only.
- [ ] Model card (`docs/model_card.md`) complete: intended use, prohibited uses, training data
      composition, performance by stratum, known failure modes.
- [ ] Prohibited-use notice (§2.3) in the README, the model card, and the dashboard.
- [ ] No real athlete utterance quoted verbatim in the paper, figures, dashboard, or examples.
- [ ] Secret scan and dependency audit clean (`docs/security.md`).
- [ ] Every worked example in the paper is synthetic or paraphrased beyond re-identification.

---

## 10. Per-phase compliance checkpoints

| Phase | Obligation |
|---|---|
| 7 — Ingestion | Validate every source against `config/data_sources_allowlist.yaml`; write complete `provenance.json`; refuse unlisted sources |
| 8 — Preprocessing | Run de-identification per §5; manual audit of a stratified sample; log failures |
| 10 — Silver labelling | Labelling agent operates only on de-identified text; no raw text in prompts or logs |
| 11 — Gold annotation | Annotators briefed on §2 and `annotation_guidelines.md` §0; escalation route live |
| 15 — Risk fusion | Score presented only with per-construct contributions; never as a bare number |
| 17 — Expert validation | Experts see de-identified or synthetic examples only; brief them on prohibited uses |
| 21 — Dashboard & security | Prohibited-use notice in UI; PII audit; secret and dependency scan |
| 24/25 — Release & paper | §9 checklist complete; §8 limitations included |

---

## 11. Open items requiring owner decision

1. **Institutional review (§3.4)** — determine whether SRMIST requires review, or record the
   exemption in writing. **Blocking for A3 and A4 collection.**
2. **Confirm category A4** (press-conference text). Permitted here under strict conditions;
   if the owner prefers the conservative position, drop to A1 + A2 + A3 and record the
   reduced ecological validity as a limitation.
3. **Nominate a contact route** (§7) for withdrawal and incident reports before release.

---

## 12. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-08 | Initial policy. Phase 5. Allow-list A1–A4 defined with prohibitions; de-identification spec written for Phase 8; non-diagnosis, limitations, and prohibited-use statements drafted paper-ready. |
