# Phase 29 decision draft - public-figure inference

> **STATUS: DRAFT. NOT AN OWNER DECISION. Nothing in this document changes
> `docs/ethics.md`, and `SRN_MATCHDAY_REAL_ATHLETES` stays unset regardless of
> what this document says.** It exists to make the decision in `docs/ethics.md`
> §15.4 easier to make well - not to make it. Written 2026-09-19, following an
> owner request to see the four §15.4 conditions actually worked through.
>
> If you read this and decide "no": delete this file, or keep it as a record
> that the question was considered and declined - either is fine, and §15
> stands as written.
>
> If you read this and decide "yes," in whole or in part: the accepted parts
> get folded into `docs/ethics.md` §15 as a dated, signed subsection, the same
> way §14.1 records the Phase 28 decision. This file alone is not sufficient -
> policy lives in `docs/ethics.md`, not here.

---

## What's actually being decided

`src/media/pressroom.py::fetch_transcript` refuses to fetch a press conference
unless `SRN_MATCHDAY_REAL_ATHLETES` is set. Unblocking it means: this project
would fetch a real, named, public athlete's press-conference words and
photograph, from a link a reader chooses because it names someone, and produce
a single score presented as that person's result. Nothing about
de-identification changes this - `src/preprocessing/deidentify.py` removes
names *from the text being scored*; it does not remove the fact that the
reader picked the link and photo because of who they are of.

This is not a vague concern. `docs/ethics.md` §2.3.3 states, and has stated
since before Phase 29 existed:

> "The system must never be used to ... generate claims about a **named**
> athlete's psychological state, publicly or privately."

And §13.4, written when Phase 27 first added photo/video upload, already
considered and rejected the specific argument that a public recording is
different:

> "Media of a public figure from a press conference is **not** exempt. Public
> availability of a recording is not consent to psychological inference about
> the person in it, and §1's prohibition on claims about a named athlete's
> mental health applies unchanged and in full."

Unblocking Phase 29 means reversing this, not narrowing around it. That
distinction matters for what follows: a "public figure carve-out" that still
produces one score for one named person is not a carve-out, it is the thing
§13.4 already named and refused.

---

## A. Is public-figure inference in scope for this project at all?

### The case for reversing §2.3.3

- **It's a compelling demo.** "Paste a press conference, see the risk profile"
  is a more vivid pitch than "paste your own writing." For a project whose
  headline contribution is interpretability (`CLAUDE.md` §1, contribution #2),
  a demo that visibly works on a recognizable case is persuasive in a way a
  synthetic example is not.
- **The underlying method doesn't change.** The construct classifier, the
  fusion layer, and the explanation layer are unchanged whether the input is
  pasted text or a fetched transcript - the *text pipeline* is identical to
  what already runs on typed and uploaded words.
- **It is arguably "public interest" adjacent.** Athlete mental health is a
  live public conversation, and a tool that visibly engages with it (even
  synthetically) has a narrative hook a purely synthetic dataset does not.

### The case against

- **It contradicts the project's own stated non-goal.** `docs/ethics.md` §2.1
  states, as paper-citable text: "No output of this system constitutes a
  clinical assessment, and no output should be used as one." A dashboard that
  visibly names a real athlete and produces a score is not a diagnosis in a
  formal sense, but it is functionally indistinguishable from one to anyone
  who sees it - a screenshot does not carry the caveats with it.
- **Reviewer risk is not hypothetical.** `CLAUDE.md` §8 rule 4 states academic
  rigor is the project's top priority and to "prefer the option that is easier
  to justify to a reviewer." An IEEE reviewer who sees a deployed dashboard
  producing individualized psychological scores for named public figures,
  beside a paper claiming "research and decision-support only, no claims about
  a named athlete," has grounds to question the paper's own honesty about its
  system - this is a worse outcome than not having the feature.
  `docs/ethics.md` §2.3.3 exists specifically to prevent this gap between what
  the paper claims and what the deployed system does.
- **There is no real consent route, and Section B below shows one cannot
  realistically be built** in the time this project has (`CLAUDE.md` §0,
  8-week timeline, code freeze ~Week 7).
- **Precedent creep.** Every other real-world extension this project has made
  - Phase 27's uploads, Phase 28's facial cues - was gated behind the
  *uploader's own* consent for *their own* material. This is the first request
  to score a third party who has given no consent at all. Approving it changes
  what kind of project this is, not just what one page does.
- **It does not obviously serve the stated goal.** The project's contribution
  is a construct-grounded corpus and an interpretability method
  (`CLAUDE.md` §1), evaluated against `data/gold/` and the synthetic corpus.
  A live public-figure demo does not improve either of those; it is a
  presentation choice, not a research result.

### Author's recommendation (advisory, not a decision)

Decline. The demo value is real but small relative to the risk: it does not
move the paper's actual contributions forward, it directly undoes a policy the
project already wrote and reaffirmed once (Phase 28, §14.2), and the consent
gap in Section B below is not closable on this project's timeline. If the goal
is a more compelling live demo, the richer facial-cue display (the companion
plan, `richer-honest-facial-cue-display.plan.md`) gets more of that value
without this cost - it makes the *existing, consented* upload path more
informative rather than opening a new, non-consented one.

---

## B. What a real consent or notice route would require

For a person who uploads their own photo (Phase 28), consent is a checkbox the
uploader ticks about their own file - imperfect (it's an attestation, not
verification, per `docs/ethics.md` §14.2), but it is at least *addressed to
the right person*.

For a press conference, the person whose data is being processed is not the
person using the page. No checkbox the reader ticks can supply the athlete's
consent, because the athlete is not present in the transaction at all. Realistic
options, and why each falls short for a solo project on this timeline:

| Option | What it would take | Why it doesn't fit here |
|---|---|---|
| Direct consent from the athlete | Identify and contact the athlete or their management/federation per case, get a written yes | Not scalable to "paste any link"; defeats the feature's own premise |
| Opt-out registry | A public list athletes can join to exclude themselves | Requires the athlete to know this project exists first; shifts the burden onto the person being scored, backwards from how consent should work |
| Institutional/federation blanket agreement | A formal data-use agreement with a sports federation | Out of reach for an undergraduate research project's scope and timeline (`CLAUDE.md` §0) |
| No consent, notice-only | State on the page that athletes can request removal after the fact | This is not consent, it is a takedown route (Section C) wearing consent's name - acceptable as a mitigation, not as a substitute for §2.3.3's requirement |

**Conclusion for B:** no consent route available to this project actually
supplies the athlete's consent. The best available option is a notice-and-takedown
route, which is a different, weaker thing than what §2.3.3 requires, and that
gap should be named plainly rather than papered over with a checkbox that
looks like Phase 28's but isn't.

---

## C. Retention and takedown route

This project already has one real mechanism for "a person wants us to stop":
`docs/ethics.md` §7 and §7.1, built for corpus donors.

> "**Withdrawal (A3):** a donor may withdraw at any time without giving a
> reason. Their records are removed from `data/`... **Incident (suspected
> re-identification or leak):** stop processing, quarantine the affected
> records, notify the owner..."
>
> Contact: **Saikalyan - `sk8069@srmist.edu.in`**, secondary **Dr. Shankar
> Ram**, acknowledgement target **7 days**.

If Phase 29 is ever unblocked, the same route should extend to cover it, with
one addition specific to this case: because nothing is stored (§13.3, §14.4 -
no transcript, no photo, no derived score persists past one page render), a
"withdrawal" request has nothing in `data/` to remove. What it would need
instead:

1. A visible statement on the match-day page itself, not buried in a docs
   file, naming the same contact address and inviting any athlete (or their
   representative) to request that this feature not be used on them.
2. A mechanism the project can actually act on - since nothing is stored, this
   would have to be a maintained exclusion list checked before
   `fetch_transcript` proceeds (a real piece of code, not yet built, and out of
   scope for this document).
3. The same 7-day acknowledgement target as §7.1, extended explicitly to this
   case in the text of §7.1 itself, not left implicit.

None of this exists today. Building item 2 is a small but real implementation
task, and it is a **precondition**, not a follow-up - §15.4 condition 3 is not
satisfied by this section alone; it is satisfied once item 2 is built and
tested.

---

## D. What the paper would have to say

If this shipped, `docs/dashboard.md`'s "What the dashboard may never do" list
and the paper's limitations section would both need new, explicit lines. Draft
language, for reference only:

> "The deployed dashboard additionally accepts a link to a public press
> conference and a photograph, and reports a score for the named individual in
> them, under a notice-and-request-removal route rather than that
> individual's affirmative consent. This is a deliberate departure from this
> paper's otherwise strict prohibition on individualized claims about named
> persons (§2.3.3), made for demonstration purposes, and is not reflected in
> any reported corpus result, ablation, or evaluation figure."

Read that sentence as a reviewer would. If it reads as an admission the paper
would rather not have to make, that is itself evidence for Section A's
recommendation, not a separate finding.

If Phase 29 stays blocked (the default), no change to the paper is needed -
the current text-only-in-the-paper framing (`docs/ethics.md` §14.5.6) already
covers this correctly.

---

## Decision record (fill in if and when a decision is made)

```
Decision: [ ] Reversed -- Phase 29 unblocked, conditions below satisfied first
          [x] Declined -- Sec.2.3.3 and Sec.13.4 stand, this draft is a record only
          [ ] Partially adopted -- specify:

Date: 2026-09-20
Signed: Saikalyan

Rationale: Per Section A's own recommendation -- the demo value is real but
small relative to the risk. It does not advance the paper's actual
contributions (construct-grounded corpus + interpretability method), it
reverses a policy this project already wrote and reaffirmed once (Phase 28,
Sec.14.2), and Section B shows no real consent route is buildable on this
project's timeline. Sec.2.3.3 and Sec.13.4 remain in force unchanged;
SRN_MATCHDAY_REAL_ATHLETES stays permanently unset. This file is kept as a
record that the question was raised and deliberately declined, not deleted.

If reversed, confirm each before SRN_MATCHDAY_REAL_ATHLETES is ever set:
[ ] Section A's reversal is written into docs/ethics.md sec.15, dated and signed
[ ] Section B's notice-only route (weaker than consent) is stated explicitly
    in docs/ethics.md, not left implicit
[ ] Section C item 2 (exclusion-list mechanism) is built and tested
[ ] Section D's paper language is added to docs/dashboard.md and drafted for
    the paper's limitations section
```
