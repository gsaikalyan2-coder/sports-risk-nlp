# Plan: Phase 29 Public-Figure Inference — Decision Write-Up

## Summary
`docs/ethics.md` §15.4 lists four things that would have to be true before
`SRN_MATCHDAY_REAL_ATHLETES` could ever be unblocked. This plan produces the document that
walks through those four things and hands the owner a decision to make — it is not a plan to
build the feature, and it does not change the gate's state. The output is
`docs/phase29_decision_draft.md`, written this session (see below); this file just records
the reasoning and the review path.

## User Story
As the project owner,
I want a single document that lays out what unblocking public-figure inference would actually require, honestly and without a thumb on the scale,
So that I can make one deliberate, written, dated decision instead of the question staying open by default.

## Problem → Solution
Current: `docs/ethics.md` §15.4 states four conditions in one paragraph each, with no room to
actually work through any of them. → Desired: a standalone draft, outside the binding policy
document, that can be read, argued with, and either discarded or folded into `docs/ethics.md`
verbatim once a decision is made — never auto-adopted.

## Metadata
- **Complexity**: Small (one document, no code)
- **Source PRD**: N/A
- **PRD Phase**: N/A
- **Estimated Files**: 1 new document (`docs/phase29_decision_draft.md`), 0 code files

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `docs/ethics.md` | §2.3 (75-110ish), §13.4, §14.2, §15 | The exact binding language this draft has to engage with, not paraphrase loosely |
| P0 | `docs/ethics.md` | §7, §7.1 (410-456) | The existing withdrawal/correction/incident contact route — the only real precedent in this project for "a person asks us to stop," reusable for condition 3 |
| P1 | `CLAUDE.md` | §14 | The phase record, for consistency of framing and dates |
| P1 | `src/media/pressroom.py` | docstring, `ETHICS_GATE_ENV` | What the gate actually blocks, precisely, so the draft doesn't over- or under-state the feature's current behavior |

## Patterns to Mirror

### DECISION_RECORD_FORMAT
```markdown
# SOURCE: CLAUDE.md sec.10, "Confirmed Decisions (locked 2026-07-23)"
- **Q1 — Multi-agent framework: CrewAI.** Confirmed. Role-based, sophomore-friendly.
```
Every settled decision in this project is recorded as a dated, one-line verdict with a short
reason, in `CLAUDE.md` §10 or as an "Owner decision, <date>" callout inline in `docs/ethics.md`
(e.g. §14.1). The new document ends with a block in exactly this shape, left blank for the
owner to fill in — this plan does not fill it in.

### NEUTRAL PRESENTATION OF A CONTESTED POLICY QUESTION
No existing file in this project argues both sides of an ethics question — every prior
`docs/ethics.md` section states a rule and its rationale, not a debate. This document is
therefore new in kind, not just content, for this project: it must present the case for and
against reversing §2.3.3 fairly, then separate that from a clearly-labeled personal
recommendation, rather than writing the "against" case thinly to make the "for" case look
stronger (or vice versa).

## Files to Change

| File | Action | Justification |
|---|---|---|
| `docs/phase29_decision_draft.md` | CREATE | The decision document itself — see below, already drafted this session |

## NOT Building

- Any change to `docs/ethics.md` itself. The draft is a separate file so it can be read,
  marked up, and rejected without touching the binding policy document.
- Any change to `SRN_MATCHDAY_REAL_ATHLETES`'s default state, `src/media/pressroom.py`, or
  any test. This plan produces reading material, not a code change.
- A recommendation dressed up as a foregone conclusion. Section A of the draft states both
  directions' real costs before stating which way the author leans.

## Step-by-Step Tasks

### Task 1: Draft the document
- **ACTION**: Write `docs/phase29_decision_draft.md` (done this session; content below).
- **VALIDATE**: Read it back once — does it accurately quote §2.3.3 and §13.4, does it state
  a real (not hypothetical) contact route in the retention section, does the recommendation
  read as advisory rather than as an instruction?

### Task 2: Owner review (not automatable)
- **ACTION**: The owner reads the draft, and either (a) rejects it — nothing changes, the
  file can be deleted or kept as a record that the question was considered — or (b) accepts
  some or all of it — the accepted parts are folded into `docs/ethics.md` §15 as a
  superseding subsection, dated and signed the way §11 and §14.1 are.
- **VALIDATE**: N/A — this step has no automated check; it is a human decision.

## Validation Commands

None — this is a document, not code. The one check that applies:
```bash
grep -c "SRN_MATCHDAY_REAL_ATHLETES" src/media/pressroom.py
```
EXPECT: unchanged from before this plan (the gate itself is untouched).

## Acceptance Criteria
- [ ] `docs/phase29_decision_draft.md` exists and covers all four §15.4 conditions
- [ ] It quotes, rather than paraphrases, the binding policy text it engages with
- [ ] It states a real, existing contact route for condition 3, not an invented one
- [ ] It separates the neutral analysis from the author's own recommendation, labeled as such
- [ ] It ends with a blank, fillable decision-record block the owner completes, not one the plan pre-fills

## Notes
This is the one part of the two-part request that is fundamentally a judgment call belonging
to the owner. The draft is written to make that judgment call easier to make well, not to make
it for them.
