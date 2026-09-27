# Reproducibility

**What a reviewer can rerun, how strong each claim is, and what nobody can rerun.**

Phase 22 deliverable. The machine-readable form of everything below is
`src/reproducibility/manifest.py::PLAN`; the checker is
`python scripts/run_reproduction.py`. If this document and the plan ever
disagree, the plan is right - it is the one a test can iterate over.

> **PROVISIONAL - planted-label corpus-property measurement, NOT accuracy.**
> `data/gold/` is empty (OPEN-025); no real athlete text exists (OPEN-011).
> Reproducing a number here proves the pipeline is deterministic. It proves
> nothing about athletes.

---

## 1. The short version

```bash
git clone <repo-url> sports-risk-nlp-repro && cd sports-risk-nlp-repro
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements-base.lock.txt

python scripts/run_ingestion.py --count 4000 --seed 42
python scripts/run_preprocessing.py
python scripts/run_baselines.py --seed 42
python scripts/run_evaluation.py --seed 42 --resamples 1000
```

Minutes, no GPU, no API key, no torch. That reproduces **every headline number
in the paper** - and the next section is the part a reviewer should read before
believing that sentence.

To have the checker do it and grade the result:

```bash
python scripts/run_reproduction.py --verify --root . --tiers A,B
```

Exit 0 gate passed · 1 gate failed · 2 the run was refused (see §5).

---

## 2. Four tiers, and why they are separate

| tier | what it does | cost | needs | strength of claim |
|---|---|---|---|---|
| **A** | regenerate the corpus, preprocess, refit the classical and lexicon baselines | minutes | base lock | **byte-identical** |
| **B** | rescore every system from the committed prediction caches; rebuild `reports/results.json` | seconds | base lock | **byte-identical** |
| **C** | retrain the transformer and regenerate its prediction cache | ~10 CPU-hours | ML lock | **within ±0.010 absolute macro-F1** |
| **D** | anything gold-derived - κ, human agreement | - | a second annotator | **not reproducible by anyone** |

**Tier B is the one to understand.** `reports/predictions/` is *committed*. A
fresh clone therefore reproduces the transformer's macro-F1, its bootstrap
interval, the +0.126 delta over the lexicon floor and the +0.234 memorisation
gap - with no torch, no `models/` and no corpus - because the transformer's
predictions arrived with the clone. That is a genuinely useful property: it
means the scoring, the bootstrap and the ablations are all independently
checkable in seconds. It is *not* evidence that the checkpoint retrains to the
same place. Only tier C is, and it is kept in its own row precisely so a cheap
green tick cannot be read as the expensive one.

---

## 3. Byte-identical versus within-tolerance, per artefact

Applying one word to every artefact would understate what this repository can
promise and overstate it in the same table. Phase 13 asserts the classical
baselines at **full float precision, not `approx`** - calling those "within
tolerance" would be a weaker claim than the code already makes. A distilroberta
fine-tune on a different CPU, BLAS build and torch build will not land on the
same float, and demanding that it does would produce a gate failing for reasons
unrelated to the claim.

| artefact | strength | measured against |
|---|---|---|
| `corpus_records` | byte-identical | SHA-256 `fa09f5ad…` |
| `utterances` | byte-identical | SHA-256 `87a796ca…` |
| `lexicon_template_disjoint_macro_f1` | byte-identical | 0.4617285842599597 |
| `tfidf_template_disjoint_macro_f1` | byte-identical | 0.22208037080486936 |
| `tfidf_random_macro_f1` | byte-identical | 0.9994594594594595 |
| `transformer_template_disjoint_macro_f1` | byte-identical | 0.5877114720181955 |
| `transformer_vs_lexicon_delta` | byte-identical | 0.1259828877582358 |
| `memorisation_gap_transformer` | byte-identical | 0.23423985163237282 |
| `transformer_random_macro_f1` | byte-identical | 0.8219513236505683 |
| `retrained_transformer_macro_f1` | **±0.010 absolute macro-F1** | 0.5877114720181955 |
| `inter_annotator_kappa` | **not reproducible** | OPEN-025 |
| `human_agreement_scores` | **not reproducible** | OPEN-025 |

### Where ±0.010 comes from, and when it was chosen

Declared **2026-08-24, before any re-run**, and frozen: the declaration records
the SHA-256 of the plan that made it, and any verification carrying a different
hash fails the gate. A tolerance widened after the delta is known is fitted to
that run, not a gate on it, and here that is refused mechanically rather than
promised in prose. The claim row is `reproduction_tolerance` in
`src/evaluation/ablations.py::CLAIMS`, added - per Phase 19's corollary - before
the sentence was written anywhere.

The number itself is bounded on both sides:

* It must be **small enough not to launder a regression**: 0.010 is under a
  thirteenth of the +0.126 delta the headline claim rests on.
* It must be **large enough not to fail on noise**: the reported bootstrap
  interval on 0.588 is [0.546, 0.622], a half-width of ~0.038. A run drifting
  less than measurement noise must not fail.

Both bounds are asserted in `tests/test_reproducibility.py`, so the tolerance
cannot drift out of that band unnoticed.

---

## 4. What this path does **not** reproduce

Stated here and printed by every run of the checker, because a one-command path
that quietly skips things claims more than it delivers.

* **Everything gold-derived.** `data/gold/` is empty and no second annotator was
  ever recruited (OPEN-025). `src/models/dataset.py` refuses `--gold` rather
  than falling back to silver. No κ, no human-agreement figure. Not a step a
  reviewer can run; not a step the author can run either.
* **The transformer, on tiers A and B.** See §2.
* **Any property of real athlete text.** The corpus is 100% synthetic template
  grammar (OPEN-011). Reproducing it proves the generator is deterministic.
* **Independence of the lexicon floor.** OPEN-021: the lexicon shares ancestry
  with the template bank via `taxonomy.yaml` examples. The caveat travels with
  the 0.462 floor wherever it is quoted.
* **The de-identification recall figure against real text.** The Phase 8 fixture
  measures the failure modes we thought to write down, on a generator that
  plants no identifiers. 0% leak rate is an upper bound.
* **Bit-exact transformer training across hardware.** Not claimed and not
  achievable. Same machine, same seed, same numbers is.

---

## 5. Why the checker refuses to run in your working tree

`handover_phase_21.txt` predicted this phase's defect before the phase began:

> The reproduction will be verified by a person who already has the artefacts
> that make it reproduce.

`data/` and `models/` are gitignored, so a genuine clone has neither. A step
that silently reads one of them passes for the author and fails for the first
reviewer. So `scripts/run_reproduction.py` inspects the tree first and **exits 2
rather than measuring** if it finds generated artefacts present - a warning is
something a tired person scrolls past; a refusal is not.

Note what a genuine clone *does* carry, because it is not nothing:
`data/raw/*/provenance.json`, `data/interim/*/{provenance,preprocessing}.json`,
`data/processed/gold_candidates/sampling_plan.json`, and all of
`reports/predictions/`. Treating a populated `data/interim/` directory as
contamination - which the first version of this check did - rejects every honest
clone. The generated artefacts are `records.jsonl` and `utterances.jsonl`; the
manifests beside them ship on purpose.

**`docker compose run app` is not a fresh tree.** Every compose service
bind-mounts `.:/app`, so the container sees the host working tree, `data/` and
`models/` included. Verify from a clone in a new directory, or build and run
without the mount.

---

## 6. Pinning: the locks, and the flag that is not optional

Before Phase 22 neither image installed a lock. `Dockerfile` installed
`requirements-base.txt` (12 floors) and `Dockerfile.train` installed
`requirements-ml.txt` (7 floors), while the only auditable file - the 180-pin
`requirements.lock.txt` - was the one nothing used. `torch>=2.2` resolves to a
different answer every build, so the artifact's reproducibility statement
described the owner's Windows venv rather than either container (SEC-07).

Now:

| file | installed by | pins |
|---|---|---|
| `requirements-base.lock.txt` | `Dockerfile`, tiers A and B | 162 |
| `requirements-ml.lock.txt` | `Dockerfile.train`, tier C | 20 + the base lock |

Both are partitioned from `requirements.lock.txt` by a **computed** dependency
closure (`pip install --dry-run --report` with the lock as a constraint file),
not by hand. The base lock resolves with **zero unpinned extras** - verified
2026-08-24 - which is the property that makes "pinned" true rather than
aspirational.

```bash
pip install -r requirements-ml.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

The flag is not optional and not a convenience. `torch==2.13.0+cpu` is a PEP 440
*local version* served by the PyTorch CPU wheel index and by no default index,
so the command fails outright without it. Documenting it in a comment is what
the repository used to do, and that is exactly how a "one-command path" ends up
being a two-command path where the second command lives in someone's memory.
`src/reproducibility/plan.py::Step` now **refuses to construct** a step that
installs a local-version lock without the flag (`MissingExtraIndex`).

Measured while building the locks, and worth keeping: resolving the ML layer
*without* the extra index - i.e. taking torch from PyPI - additionally pulls 19
`nvidia-*` / `cuda-*` / `triton` packages, several GB of CUDA runtime a CPU-only
container never loads. That is what the flag buys.

### Two gaps the lock had (SEC-11)

`requirements.lock.txt` was captured by `pip freeze` on Windows on 2026-08-09,
and that has consequences a reader should know about:

* **`uvloop` was missing.** A Linux-only transitive dependency of `uvicorn`, so
  a Windows freeze cannot see it - and installing the lock in a Linux container
  pulled it *unpinned*. Now pinned in the base lock with a platform marker.
* **`sentencepiece` was missing entirely.** `requirements-ml.txt` requires it
  (microsoft/deberta-v3-base ships a SentencePiece vocabulary; omitting it
  produces the misleading tiktoken error recorded as OPEN-029). It was added to
  `requirements-ml.txt` on 2026-08-11, two days *after* the lock was captured,
  and nothing noticed. The single file backing the reproducibility claim was
  missing a required dependency for fifteen days.

---

## 7. Line endings, and a provenance gap worth reporting

Verifying in a real clone on Linux turned up something no test had:
`records.jsonl` matched the owner's tree byte-for-byte, and `utterances.jsonl`
did not - identical content, exactly 9,302 bytes apart, one CR per line.

The two stores' code was **identical**; both used `open("w", encoding="utf-8")`,
which translates `\n` to `\r\n` on Windows. The difference was that the corpus
had been generated in the Linux container on 2026-08-10 and the utterances on
Windows on 2026-08-12, and **nothing in the repository recorded which artefact
came from which environment.** The numbers were unaffected. The byte-identity
claim was not.

`src/evaluation/sampling.py` already used `newline="\n"`; the other writers did
not. They do now - `src/ingestion/store.py`, `src/preprocessing/store.py`,
`src/labeling/store.py`, and the manifest writers alongside them - and
`tests/test_reproducibility.py` asserts it at source level, because a functional
check passes on Linux whether or not the fix is present and so would assert
nothing about the platform where the defect lives.

**Consequence for the owner:** regenerate `data/interim/` once, or its bytes
will not match `FILE_DIGESTS`. The content is unchanged.

---

## 8. What the checker refuses to call a pass

Learned by running it and reading the output, not by writing tests:

1. **A verification in a contaminated tree** - refused, exit 2.
2. **A verification whose plan hash has moved since declaration** - the
   tolerance was edited after the fact.
3. **A declared artefact with no verdict** - silence about an artefact is how a
   path claims more than it delivers, so silence is a failure condition.
4. **A pass that reproduced nothing.** With no tiers selected, every artefact is
   honestly marked skipped, every other check is satisfied, and the gate went
   green having done nothing. Phase 18's corollary in a new costume.
5. **An artefact skipped inside an attempted tier** - a tier is exercised or not
   selected.
6. **A step that exited non-zero**, even one producing no artefacts. On the
   first real run the `env` step failed and the gate passed on the strength of
   the later steps, because a step with no artefacts had no way to report
   failure.

Numbers 4 and 6 were both found by rendering the report and reading it. That is
Phase 20's lesson arriving twice more in one phase, and it is the reason the
verification step is not optional.

---

## 9. Related

* `docs/model_card.md` §9 - the same path from the model's side.
* `docs/security.md` - SEC-07 and SEC-11, the pinning findings.
* `docs/findings.md` - what the numbers mean.
* `docs/docker.md` - the two images.
* `ARTIFACT.md` - the anonymized release README.
