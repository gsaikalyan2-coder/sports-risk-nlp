# Phase 14 Handover - Pre-Competition Psychological Risk Profiling of Athletes

**Prepared:** 2026-08-12
**Phase completed:** 14 - Transformer fine-tuning
**Next phase:** 16 - (optional) AutoML benchmark, then 17 - Explainability + expert validation
**Self-contained:** a new session should be able to continue from this file alone.

---

## Part A - Project summary

**Goal.** Detect validated sports-psychology constructs (CSAI-2 / SDT / ABQ tradition) in athlete
text and fuse them into an interpretable pre-competition risk index. Target: IEEE conference full
paper. Owner: Saikalyan, sophomore, SRMIST. Single source of truth: `CLAUDE.md`. Roadmap:
`PROJECT_PLAN.md`. Open items: `docs/open_issues.md`.

**Timeline.** 8 weeks. Code freeze ~Week 7; paper draft first week of September 2026. As of
2026-08-12 there are roughly **three weeks to code freeze**.

**Phase status.**

| Phases | Status |
|---|---|
| 1–13 | Complete - scoping, literature, taxonomy, ethics, ingestion, preprocessing, synthetic corpus, silver labelling, annotation tooling, classical baselines |
| **14** | **Complete - transformer fine-tuned, gate PASSED** |
| 15 | Complete - risk fusion + per-construct calibration (`src/risk/`, `reports/calibration.md`) |
| 16 | Not started - optional, no DataRobot account, likely skipped |
| 17–25 | Not started |

**The one sentence that governs how every number in this project is read:** `data/gold/` is empty,
so **no result anywhere in this repository is an accuracy.** Everything measured so far is a
corpus property of a synthetic template grammar.

---

## Part B - What happened this session

### 1. Phase 14 built and executed

`src/models/transformer.py` - multi-label transformer behind the same `Baseline` interface as the
Phase 13 classical models, so the gate scores both through one harness. Thresholds tuned on a
template-disjoint validation slice carved from *training* data. `scripts/run_transformer.py` - the
gate, comparing against the Phase 13 bar read from `reports/baselines.json` (not hardcoded) with a
**paired bootstrap**, not a point comparison.

**Results (`reports/transformer.json`, `reports/transformer.md`):**

| | value |
|---|---|
| best configuration | `distilroberta-base`, lr 2e-5, batch 16, 6 epochs, len 128 (best epoch 5) |
| macro-F1, template-disjoint | **0.588** [0.549, 0.624] |
| macro-F1, random split | 0.905 |
| **memorisation gap** | **+0.317** (TF-IDF+LinearSVC gapped +0.819) |
| vs lexicon bar 0.462 | **+0.126**, paired bootstrap **p = 0.000** |
| **gate** | **PASS** |

**What the gate passing means:** a pretrained encoder recovers more of the planted template grammar
than a cue lexicon does, across held-out templates. **It is not evidence the model detects
psychological constructs in athlete text.** `PROJECT_PLAN.md` Phase 14's gate is satisfied;
`CLAUDE.md` §9 publication-readiness is not, and cannot be until a real gold set exists.

### 2. Three findings worth carrying into the paper

1. **Threshold tuning made results worse in all six configurations** (−0.014 to −0.112). Best
   untuned (0.639) beats best tuned (0.588). Ten parameters fitted on 355 validation records were
   fitting noise. Argues for dropping per-construct thresholds entirely.
2. **Top three configurations are statistically indistinguishable** (0.588 / 0.582 / 0.558, CIs
   overlapping). Report as "no configuration clearly dominated".
3. **The memorisation gap is the headline contribution.** +0.317 vs TF-IDF's +0.819 - a pretrained
   encoder generalises across held-out templates where bag-of-ngrams collapses. Measured, not
   asserted.

### 3. Performance work (after the first run took ~19 min/epoch)

`max_length` 256 → **128** (measured: longest record ~125 subword tokens, median ~50); fixed
padding → **dynamic padding** with per-batch trimming; `use_safetensors=True` (the first run
downloaded the model twice); **live progress output** with loss and ETA. Combined ~5× less CPU
work. Sweep restructured: grid runs on the template-disjoint split only, random foil runs for the
winner - the memorisation gap is a corpus property, not a hyperparameter one.

### 4. Ethics amendment - A5, then its collapse

`docs/ethics.md` **§3.5** - prohibition **P1 narrowed** (not repealed) to permit **topic-scoped**
collection from public pseudonymous forums as category **A5**, with 11 binding conditions.
Account-centred collection remains prohibited absolutely. §3.5.2 records the argument *against*,
including that P1's actual objection - *authors do not anticipate psychological profiling* - is
**not** answered by pseudonymity.

`src/ingestion/reddit.py` enforces C1 **structurally**: there is no `author` parameter on any entry
point, so an account-centred request cannot be expressed. Tests assert this against the signatures.

**It produced no data.** Route (b) (unauthenticated public JSON, added when the owner could not
register an API application) returned **`HTTP 403 Blocked` on all eight communities**. Per §3.5.5
point 4, written before the attempt, the block was treated as an answer: no User-Agent rotation, no
proxy, no browser impersonation. See **OPEN-031**.

### 5. Pivot to A3 consented donation

`docs/consent_form.md` (v1.0), `docs/recruitment.md`, `scripts/run_donation.py`. Consent, adult,
health and minor gates all verified firing; **donor names verified not to reach `data/`**.

### 6. Files changed

**New:** `src/models/transformer.py`, `src/ingestion/reddit.py`, `scripts/run_transformer.py`,
`scripts/diagnose_transformer.py`, `scripts/run_reddit.py`, `scripts/run_donation.py`,
`tests/test_transformer.py`, `tests/test_reddit.py`, `docs/consent_form.md`,
`docs/recruitment.md`, `reports/transformer.{json,md}`, `phase14_handover.md`

**Modified:** `docs/ethics.md` (§3.5 + §3.5.5), `config/data_sources_allowlist.yaml` (v3, A5 added,
P1 narrowed), `docs/model_card.md` (§5 populated), `docs/open_issues.md` (OPEN-029 resolved;
OPEN-030/031/032 raised), `.gitignore`, `pyproject.toml`, `requirements-ml.txt`,
`src/models/__init__.py`

---

## Part C - Open items, by urgency

| # | Item | Status |
|---|---|---|
| 1 | **OPEN-011 - no real athlete text.** A1 exhausted (Phase 7), A5 blocked by Reddit (OPEN-031). **A3 is the remaining route** and materials are built. Nothing collected yet. | **highest risk** |
| 2 | **OPEN-025 - no second annotator.** κ needs two people; contribution #1 unmet without it. The ask is ~3 hours on the 100-item `gold_dev` set, in two sittings. Owner currently intends to annotate solo, which **cannot** close this. | **critical, 3 phases overdue** |
| 3 | **OPEN-004 - no expert rater.** Phase 17 is the headline contribution and has the longest lead time. | overdue |
| 4 | OPEN-030 - ethics exemption predates the A5 amendment | before submission |
| 5 | OPEN-005 - exemption documentary record not obtained | before submission |
| 6 | OPEN-006 - personal webmail is the only contact route | release blocker |
| 7 | OPEN-031 - A5 amendment paid its ethical cost and produced nothing; revert or report? | decision |
| 8 | OPEN-032 - A3 donor mapping must stay out of git | before first donation |
| 9 | OPEN-012 / OPEN-021 / OPEN-028 | known, documented |

**One person could close items 1, 2 and 3 simultaneously:** an SRMIST coach or sport-psych
practitioner can donate/broker text, be annotator A2, and serve as the Phase 17 expert rater. This
has been deferred across five phases. `docs/recruitment.md` has the ask.

---

## Part D - Immediate next steps

1. **Commit Phase 14** (Part E below).
2. **Send the A3 recruitment message this week** - `docs/recruitment.md`. Target 40–50 donations.
3. **Ask one person to be annotator A2** - any careful person, no sports-psych expertise needed.
4. **Then Phase 17** (explainability + expert validation), the headline contribution.

**Paper framing decision, due by code freeze.** If real gold never arrives, the honest paper is a
*methods + corpus-design + negative-result* contribution, with the memorisation gap as the headline
finding. Decide by Week 7 rather than discovering it.

---

## Part E - Commit sequence

Pre-commit stashes unstaged changes, and if hooks then modify staged files the restore conflicts
and **all fixes roll back**. Stage everything first.

```bash
# 1. Baseline the SHA-256 training fingerprints (false positives, not secrets).
#    ^models/ is excluded: 482 MB, gitignored, never committed.
detect-secrets scan --baseline .secrets.baseline \
  --exclude-files '\.secrets\.baseline|\.env\.example|^data/|^paper/|^\.git/|^models/'
detect-secrets audit .secrets.baseline      # 'n' for each

# 2. Stop tracking run logs (gitignore cannot touch already-staged files)
git rm --cached logs/transformer_*.json

# 3. Stage everything so pre-commit has nothing to stash
git add -A

# 4. Commit (hooks may rewrite files and abort once; re-add and repeat)
git commit -m "feat(phase14): transformer fine-tuning, gate PASSED

distilroberta-base lr2e-5 bs16 ep6: macro-F1 0.588 [0.549,0.624]
template-disjoint vs lexicon 0.462; +0.126, paired bootstrap p=0.000.
Memorisation gap +0.317 against TF-IDF's +0.819.

Threshold tuning degraded macro-F1 in all 6 configs; best untuned 0.639
beats best tuned 0.588. Recorded as a finding, not tuned away.

Corpus property, not accuracy. data/gold/ still empty (OPEN-025)."

git add -A
git commit -m "feat(ingestion): A5 harvester + A3 donation path

ethics.md 3.5: P1 narrowed to prohibit account-centred collection only;
A5 added for topic-scoped public forum text under 11 binding conditions.
C1 enforced structurally -- no author parameter exists on any entry point.

A5 route (b) returned 403 on all 8 communities and was abandoned per
3.5.5 point 4 rather than worked around (OPEN-031). A3 consented
donation is the remaining route: consent form, recruitment plan, and
run_donation.py with consent/adult/health/minor gates verified."

git add -A
git commit -m "docs: Phase 14 handover, model card, open items

OPEN-029 resolved with observed numbers. OPEN-030/031/032 raised."
```

**Verify after committing:**

```bash
git log --oneline -3
git status --short          # expect clean
python -m pytest -q         # full suite
```

---

## Part F - Environment notes for the next session

- **Python 3.11** (`datetime.UTC` is used; it does not exist on 3.10).
- `pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu` -
  the CPU wheel index matters; default PyPI torch is the CUDA build.
- `sentencepiece` is required for DeBERTa-v3 and is pinned. Without it the failure is an
  un-Googleable tiktoken `ValueError`; `load_tokenizer` translates it.
- **No HF token is needed.** The warning about unauthenticated requests is a rate-limit notice.
- Full sweep on CPU: ~5 hours at distilroberta size. One config, one epoch: ~10 minutes.
- `scripts/diagnose_transformer.py` isolates a native crash one flushed step at a time.
- **`pytest` excludes `-m slow` by default** (`pyproject.toml` `addopts`). The default run is
  offline, deterministic and free. The one network-dependent test - the fine-tune smoke test - runs
  only with `pytest -m slow`, and skips rather than fails when the hub is unreachable. A red report
  that means "someone else's server is down" trains people to ignore red reports.
- **`TransformerBaseline.load()`** reloads a saved checkpoint with its tuned thresholds and refuses
  a construct-order mismatch. Phase 17 needs this; without it, explainability would have to retrain
  (~5 hours) to get back a model already on disk.

**Do not:** report any number as accuracy; write to `data/gold/`; weaken the `--gold` refusal; add a
bypass flag to the ingestion checking path; work around a 403.
