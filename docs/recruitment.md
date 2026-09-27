# A3 recruitment - asking people to donate a pre-competition reflection

Companion to `docs/consent_form.md`. Category **A3**, `docs/ethics.md` §3.1.

## Why this document exists

OPEN-011 is the project's highest live risk: contribution #1 needs real pre-competition athlete
text and there is none. Two routes were tried and closed:

- **A1 public dataset** - Phase 7 surveyed four candidates, all post-match, all rejected on
  licensing or access. No corpus of pre-competition athlete text exists publicly.
- **A5 topic-scoped forum collection** - attempted 2026-08-12, `HTTP 403 Blocked` on every
  request. Reddit refuses unauthenticated programmatic reads and the block was treated as an
  answer (`docs/ethics.md` §3.5.5).

A3 is what remains without registering an API application. It is also the route that was
ethically cleanest from the start; it lost earlier only on recruitment lead time.

## What "enough" looks like

**You need far less than you think.** The purpose of A3 text is a *gold evaluation set*, not
training volume - `synth_precomp_v1` already supplies 4,000 synthetic records for training.

| donations | what it buys |
|---|---|
| **15–20** | A qualitative reality check: does the taxonomy survive contact with real pre-competition writing? Enough for a "we validated the construct schema against real text" paragraph. |
| **40–50** | A small real gold set. Enough for a genuine held-out evaluation and a κ if a second annotator exists. **This is the target.** |
| **100+** | Comfortable, but not necessary, and not achievable in the time remaining. |

At 40–50, one donation per person, this is a two-week ask if you start now and a zero-week ask if
you start in September.

## Where to ask

In rough order of yield per unit of effort:

1. **SRMIST sports teams and the gym.** Anyone who competes - athletics, swimming, cricket,
   football, badminton, chess, esports. A team WhatsApp group is one message to thirty people.
2. **Your own year group.** Many students compete at club level in something.
3. **A coach or PE staff member.** Highest value by far, because the same person may also solve
   **OPEN-025** (second annotator) and **OPEN-004** (Phase 17 expert rater). Three open items,
   one relationship.
4. **Amateur running/cycling clubs near campus.** Community clubs are often willing to help a
   student project.

**Do not post the ask on Reddit.** Not because it would be scraping - soliciting donations is not
collection - but because an unsolicited research request from a new account in those communities
is usually removed by moderators, and it burns the venue.

## The message

Short, honest, no hype. Longer asks get read less.

> **Subject: 10 minutes to help an undergrad research project?**
>
> Hi - I'm Saikalyan, a sophomore at SRMIST. I'm doing a research project on the language
> athletes use *before* a competition, aiming for a conference paper.
>
> I need people who compete in something to write **one short reflection (~150 words)** about an
> upcoming event - what's on your mind, how prep feels, what you're looking forward to or not.
> Takes about 10 minutes.
>
> A few things up front:
> - Your words are **never published word-for-word** and **no result about you personally** is
>   ever shown or shared. Everything is de-identified first and reported in aggregate.
> - Nobody who knows you sees it - not a coach, not your team.
> - It is **not** any kind of mental-health assessment. It's a language study.
> - You can withdraw any time, no reason needed.
> - You need to be 18+.
>
> Full details and the consent form are here: [link/attach `docs/consent_form.md`]
>
> If you're up for it, reply to this or email `sk8069@srmist.edu.in` (SRMIST) with subject
> `[SPORTS-RISK-NLP]`. And if it's not for you, no worries at all - a share with anyone who
> competes would help just as much.
>
> Thanks,
> Saikalyan

### If asking a coach or staff member

Add:

> I'd also value 30 minutes of your time on whether the psychological constructs I'm detecting
> make sense to someone who actually works with athletes. That would be a real contribution to
> the paper and I'd credit it properly.

That single sentence is the highest-leverage line in this document. It opens **OPEN-004** and
**OPEN-025** at the same time as OPEN-011.

## Rules while recruiting

- **Never pressure anyone**, and be especially careful with anyone you have any standing over.
- **Send the consent form before they write**, not after.
- **Anyone under 18 is declined**, politely and without exception (P2).
- **If someone writes about injury, illness, or a diagnosed condition, delete it** and tell them
  why. That is health data and it is out of scope (P6 / C4).
- **Do not chase.** One ask, one optional reminder.
- **Keep signed forms out of the repository.** They contain real names.

## Recording a donation

```bash
python scripts/run_donation.py --add donations_inbox.jsonl --source-id a3_donations_v1
python scripts/run_donation.py --verify-only --source-id a3_donations_v1
python scripts/run_preprocessing.py        # de-identify - required before any model use
```

The name↔`record_id` mapping lives outside the repo and is needed only to action a withdrawal.
Tracked as **OPEN-032**.
