# Ethics & Data Governance Policy

**Project:** Pre-Competition Psychological Risk Profiling of Athletes
**Version:** 1.1 — Phase 5, 2026-08-08 (header corrected at Phase 7; the 1.1 changelog entry was present but the header still read 1.0)
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
| Scraping personal social-media accounts — **account-centred** collection: user timelines, profile harvesting, or following named individuals across posts | Public ≠ consented. Personal posts are not professional-capacity speech and users do not anticipate psychological profiling. **Narrowed 2026-08-11 — see §3.5.** Topic-scoped collection from public pseudonymous forums is now permitted as category A5 under binding conditions. Account-centred collection remains prohibited without exception. |
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

**Owner decision, 2026-08-08: A4 is CONFIRMED and permitted**, under all four mandatory conditions
above. The conservative A1+A2+A3 fallback is **not** taken. Conditions 1–4 are therefore binding
requirements on Phase 7 ingestion and on every published artefact, not advisory notes:

- Phase 7 (`src/ingestion/`) must de-identify A4 text despite the speaker being publicly known.
- Phase 9 (dashboard) and the paper must use **synthetic or heavily paraphrased** examples only.
  A real, quotable press-conference utterance must never appear in any output, even
  de-identified — a distinctive quote is itself an identifier, findable by search.
- The exclusion test in condition 4 ("would this embarrass or harm the speaker if attributed")
  is applied at annotation time, not at publication time, and an excluded passage is dropped
  from the corpus rather than merely withheld from the paper.

Because A4 is the permission most likely to be questioned at review, §3.3 as a whole is written
to be cited in the paper. Do not weaken conditions 1–4 without revisiting this decision with the
owner and amending this section.

### 3.4 Institutional review — DETERMINED EXEMPT (documentary record pending)

**Determination:** the owner reports, following consultation at SRMIST, that this project is
**exempt** from institutional ethics review as secondary analysis of public, licensed, consented,
or synthetic text, with no primary human-subjects data collection and no clinical intervention.

**Recorded:** 2026-08-08, on the owner's report.
**Effect:** the block on A3 and A4 collection is **lifted**. Phase 7 ingestion may proceed across
all permitted categories.

**Still outstanding — one item, and it is not optional.** This determination is currently recorded
on the owner's verbal report. The paper needs the *documentary* form: an email, a letter, or a
committee reference number from whoever made the determination, naming the determining body and
the date.

Why this is worth chasing even though the answer is favourable: an exemption is a claim about
process, and IEEE reviewers and ethics editors ask for its provenance. "The author states the work
was exempt" is materially weaker than "exempt per SRMIST, determination dated X, reference Y", and
the gap is only fixable *before* submission. Obtaining it now, while the conversation is fresh,
costs one email. Reconstructing it in the first week of September, against a submission deadline,
costs considerably more.

**When obtained:** save it to `docs/ethics_review_exemption.*` (do not commit it if it contains
personal contact details — record the reference number here instead) and cite it in the paper's
Ethics section. Tracked as **OPEN-005** in `docs/open_issues.md`.

---

### 3.5 Category A5 — public pseudonymous forum text *(owner amendment, 2026-08-11)*

**This section amends a previously non-negotiable prohibition. It is written to be read by a
reviewer, including the parts that argue against the decision.**

#### What changed and why

Until 2026-08-11 the prohibition on "scraping personal social-media accounts" was absolute. Phase 7
(2026-08-09) had established that **no public corpus of pre-competition athlete text exists** — all
four surveyed candidates were post-match, which is the wrong side of the event for an anticipatory
taxonomy (`appraisal_orientation`, anticipatory `cognitive_anxiety`). That left the project with a
synthetic corpus and no real text, and contribution #1 depends on real text (**OPEN-011**).

Public pseudonymous forum communities for amateur endurance athletes — r/running, r/triathlon,
r/swimming, r/climbing and similar — contain genuinely **anticipatory** pre-competition writing
that exists nowhere else in accessible form. The owner has decided to permit topic-scoped
collection from these communities, as **category A5**, under the binding conditions in §3.5.3.

**The prohibition is narrowed, not repealed.** Account-centred collection — user timelines, profile
harvesting, following a named individual across posts, or assembling any per-author history —
remains prohibited without exception. A5 permits collecting *posts matched by topic*, never
*people matched by identity*. That distinction is the whole substance of this amendment: it is the
difference between studying a discourse and profiling a person.

#### 3.5.1 The argument for

1. **Anticipatory by nature.** A post written the night before a race is pre-competition text in the
   sense the taxonomy requires. Press material is not.
2. **Pseudonymous at source.** Handles are not legal names, so de-identification begins from a much
   better baseline than named-athlete material under A4.
3. **Documented research genre.** Reddit-based psychological NLP is established practice with a
   published ethics literature (the CLPsych shared tasks; Benton, Coppersmith & Dredze 2017,
   *Ethical Research Protocols for Social Media Health Research*). The conditions in §3.5.3 are
   drawn from that literature rather than invented here.
4. **Amateur, not elite.** Non-public-figure amateurs face no selection, contract, or reputational
   consequence from a research corpus, unlike the named professionals A4 covers.

#### 3.5.2 The argument against, recorded rather than resolved

**The original prohibition's stated reason is not fully answered by this amendment, and the paper
must say so.**

P1 objected that *"users do not anticipate psychological profiling."* Pseudonymity, API terms and
amateur status all address **identifiability**. None of them addresses **anticipation of use**.
Someone posting "terrified about my race tomorrow" in a running community expects encouragement
from other runners. They do not expect to be scored on a burnout index. That expectation gap is
real, it survives every safeguard below, and the honest position is that A5 accepts a residual
ethical cost rather than eliminating one.

Three further objections that the conditions mitigate but do not remove:

- **Pseudonymity is not anonymity.** A distinctive verbatim sentence is searchable and can
  re-identify an author. Condition C6 exists for this and is absolute.
- **No opportunity to withdraw before collection.** Unlike A3, subjects cannot decline in advance.
  C9 (honouring deletion) is a partial and retrospective substitute.
- **Selection bias.** People who post about pre-race nerves are not a random sample of athletes,
  which is a validity problem as well as an ethical one. It belongs in §6 and in the paper's
  limitations.

**If a reviewer finds this amendment unpersuasive, the fallback is A3** — recruiting the same
communities for *consented donation* rather than collecting from them. A3 is already permitted and
was unblocked on 2026-08-08. It remains available and is the ethically cleaner route; it was not
chosen because recruitment lead time is incompatible with the project's remaining schedule. That
reasoning is a resourcing constraint, not an ethical argument, and it is recorded here as such.

#### 3.5.3 Binding conditions — all mandatory, none advisory

| # | Condition |
|---|---|
| C1 | **Topic-scoped only.** Collection is by subreddit and pre-competition query. Never by author, never a user timeline, never a per-author history. |
| C2 | **Public and unauthenticated only.** Either **(a)** the official API via a registered application with declared research use, **or** **(b)** public read-only JSON endpoints with a descriptive User-Agent, single-threaded and rate-limited to ≤10 requests/minute. Rate limits respected either way. No login-walled, private, quarantined, or paywalled content (P5 stands). **Route (b) was added 2026-08-12 and carries a caveat — see §3.5.5.** |
| C3 | **Adults only.** Any post indicating a minor author, or drawn from a youth/school-age community, is excluded (P2 stands, unweakened). |
| C4 | **No health content.** Posts whose subject is injury, illness, treatment, medication, or a mental-health diagnosis are excluded at ingestion (P6 stands). Pre-competition nerves are in scope; a disclosed anxiety disorder is not. |
| C5 | **De-identification before use.** §5 pipeline runs before any text reaches a model. Usernames, handles, URLs, club and school names, locations, and race names that pin an individual are replaced. `deidentified` stays false until it has run. |
| C6 | **No verbatim publication, ever.** No collected sentence appears in the paper, dashboard, figures, or examples. Illustrations are synthetic or paraphrased beyond re-identification. A verbatim quote is an identifier. |
| C7 | **No individual-level output.** No per-author or per-post risk score is published, exported, or shown. Aggregate only. |
| C8 | **No contact.** Authors are never messaged, replied to, or approached about their inclusion. |
| C9 | **Deletion is honoured.** Posts deleted or removed upstream are dropped from the corpus at the next refresh and are not retained in derived artefacts where separable. |
| C10 | **No redistribution of source text.** Derived artefacts only — labels, statistics, models. The raw collection is not published. Post IDs may be released for reproducibility only if C6 and C9 remain satisfiable. |
| C11 | **Data minimisation.** Post body and coarse metadata only (subreddit, days-to-competition where stated, sport, level). No author metadata, karma, history, or cross-posting graph. |

Violation of any condition is an ingestion refusal, logged to `logs/ingestion_refusals.log`. The
fail-closed contract in `config/data_sources_allowlist.yaml` is unchanged and **no bypass flag may
be added to the checking path**.

#### 3.5.4 What this does not change

- **P1 still prohibits account-centred collection.** Narrowed in scope, not removed.
- **P2 (minors), P3 (private communications), P4 (licence/ToS), P5 (authenticated/paywalled),
  P6 (health content), P7 (provenance)** all stand unweakened and apply to A5 in full.
- **§2.1 non-diagnosis and §2.3 prohibited uses** are unaffected. A5 text may never be used to make
  a claim about any identifiable person.
- **Institutional review.** §3.4's exemption was determined for *secondary analysis of public,
  licensed, consented, and synthetic text*. A5 is public secondary analysis and is within the
  scope of that determination as written. **This should nonetheless be confirmed rather than
  assumed** — the exemption predates this amendment and the determining body did not see it.
  Tracked as **OPEN-030**; resolve before submission, alongside OPEN-005.

---
#### 3.5.5 C2 route (b) — unauthenticated public endpoints *(2026-08-12)*

**Why it was added.** The owner was unable to register a Reddit application. C2 as originally
drafted required one, which would have made A5 unusable in practice.

**The caveat, stated plainly because it does not go away.** Reddit's Data API Terms ask
programmatic users to register an application. Reading public `.json` endpoints without
registering is **a gray area, not a clearly permitted collection method.** Therefore:

> **P4 (licence or ToS forbids the collection method) is NOT automatically satisfied by route (b).**

This is a weaker compliance position than route (a), and the difference is a genuine one rather
than a formality. Consequences that follow:

1. **Route (a) is preferred wherever available.** Registering a script application is free and
   takes minutes. Route (b) exists because a specific person was blocked, not because it is
   equivalent.
2. **The paper must describe the collection method accurately** — "public read-only endpoints,
   unauthenticated, rate-limited to under 10 requests per minute" — and must not describe it as
   "via the Reddit API" if route (b) was used. Those are different claims.
3. **Volume stays low.** Route (b) is for assembling a small gold set (order 10²), not a training
   corpus. If the project ever needs volume, that is the point at which registering stops being
   optional.
4. **If Reddit's terms change, or access is refused or rate-limited as a signal, collection
   stops.** A block is an answer, not an obstacle to route around.

**Tracked as OPEN-031.** Before submission, either register an application and re-collect under
route (a), or state route (b) explicitly in the paper's ethics section. Do not leave it implicit.

##### Outcome, 2026-08-12: route (b) was attempted and is closed

Route (b) was exercised the day it was added. **Every request returned `HTTP 403 Blocked`** —
eight of eight communities, zero posts fetched, zero records written. Reddit refuses
unauthenticated programmatic reads.

Applying point 4 above without argument: **that is the answer, and collection under route (b)
stops.** No User-Agent rotation, no proxy, no browser impersonation, no retry schedule. Each of
those is circumvention of an access control, which is **P5**, and P5 stands unweakened under A5
(§3.5.4). A route granted on the condition that a block ends it does not get to treat the block
as a bug.

Route (b) is therefore **retained in the policy as written but recorded as non-functional**. It
is not removed, because the reasoning and its caveat are part of the project's audit trail and a
future reader should be able to see that the permissive route was tried, failed, and was not
worked around.

**The remaining routes for OPEN-011 are (a) a registered application, or A3 consented donation.**


**The cleaner alternative remains available and unblocked.** A3 consented donation needs no
credentials, no API, and no ToS judgement at all. It was not chosen because of recruitment lead
time (§3.5.2), and that remains a resourcing constraint rather than an ethical argument.


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

> **Implementation status (Phase 8, 2026-08-09).** Implemented as written; the spec below was
> not redesigned. Measured against `tests/fixtures/deid_cases.jsonl`: precision 100%, recall
> 100%, exact match 100% (34/34), **leak rate 0%**, negatives preserved 8/8, reported per
> difficulty band. Full numbers, the pass ordering, and the seven stated limitations are in
> **`docs/preprocessing.md`**. **A clean sweep of 34 self-authored cases is a weak claim and
> must not be presented as a strong one**: every case was written by this project, none of it
> is real athlete text (OPEN-011), and the score is an **upper bound** on real-text
> performance. §5.3 below stands unchanged and is the honest counterweight.

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
### 7.1 Contact route — NOMINATED

**Primary contact for withdrawal, correction, and incident reports:**

> **Saikalyan — `gsaikalyan2@gmail.com`**
> Subject line prefix: `[SPORTS-RISK-NLP]`
> Acknowledgement target: **7 days**. Withdrawal actioned before the next data release.

This address **must** appear verbatim in the released `README.md`, in `docs/model_card.md`, and in
the A3 consent form, or none of the mechanisms in §7 is reachable in practice and the withdrawal
right is decorative.

**Standing requirement — replace before any public release.** A personal webmail address is
acceptable for a project that has not yet released anything; it is **not** acceptable on a
published IEEE artefact, for two reasons that both bite at review time:

1. **Institutional accountability.** A withdrawal route should outlive the author's personal
   inbox and be traceable to the institution that determined the work exempt (§3.4). A Gmail
   address ties the project's only accountability mechanism to one individual's private account.
2. **Continuity.** A donor may withdraw consent two years after publication. The route has to
   still work.

Therefore, **before the corpus, code, or paper is released**, this section must be updated to:

- an **SRMIST institutional email address** for the owner, as primary; and
- a **named supervisor or lab contact** as secondary, so the route survives the owner's
  graduation.

Neither is recorded here yet, and neither has been invented — inventing a plausible-looking
institutional address would produce a route that silently fails, which is worse than an honest
interim one. Tracked as **OPEN-006** in `docs/open_issues.md`; it is a release blocker, not a
Phase 7 blocker, so it does not hold up ingestion.

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

## 11. Owner decisions — all three resolved 2026-08-08

| # | Item | Decision | Residual action |
|---|---|---|---|
| 1 | Institutional review (§3.4) | **EXEMPT** — secondary analysis of public/licensed/consented/synthetic text; no primary human-subjects collection. A3 and A4 collection **unblocked**. | Obtain the determination **in writing** (reference number or email) and cite it in the paper. **OPEN-005** — before submission. |
| 2 | Category A4, press-conference text (§3.3) | **CONFIRMED permitted** under all four mandatory conditions. Conservative A1+A2+A3 fallback **not** taken. | None. Conditions 1–4 are now binding on Phases 7, 9, and the paper. |
| 3 | Contact route (§7.1) | **NOMINATED** — `gsaikalyan2@gmail.com`, prefix `[SPORTS-RISK-NLP]`, 7-day acknowledgement. | Replace with an SRMIST institutional address + named supervisor **before any public release**. **OPEN-006** — release blocker, not a Phase 7 blocker. |

**Nothing in this section now blocks Phase 7 ingestion.** The two residual items are a
pre-submission item and a pre-release item respectively, both tracked in
`docs/open_issues.md`.

---

## 12. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-08-08 | Initial policy. Phase 5. Allow-list A1–A4 defined with prohibitions; de-identification spec written for Phase 8; non-diagnosis, limitations, and prohibited-use statements drafted paper-ready. |
| 1.1 | 2026-08-08 | All three §11 owner decisions resolved. §3.4 institutional review determined **exempt** (documentary record pending, OPEN-005). §3.3 category **A4 confirmed** permitted with conditions 1–4 made binding. §7.1 contact route **nominated** (interim personal address; institutional replacement required before release, OPEN-006). A3/A4 collection unblocked for Phase 7. |
