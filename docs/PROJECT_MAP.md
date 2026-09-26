# Project map

**Generated 2026-09-26 by `scripts/build_project_map.py`.** 364 tracked files, 3305 edges, 35 with no inbound edge.

## Regenerating this file

```bash
python scripts/build_project_map.py
```

Structural only -- stdlib `ast` plus literal path matching. No LLM, no network, no subagents, so it is free to re-run and its every edge is grep-checkable. Re-run it after any change that adds, deletes or renames a tracked file; the counts above are the file's own freshness check.

## What an edge means, and what it does not

`A -> B` means **file A names file B**, by Python import or by path. It does *not* follow that B is unused when nothing names it. Three kinds of live file carry zero inbound edges by construction:

* files referenced by **directory** rather than by name -- `reports/predictions/*.json`;
* files read by something **outside the repo** -- a `.gitkeep`, an IDE setting, a deploy script;
* the **record of decisions** -- handovers, phase prompts, plans. Nothing imports history.

An isolated-file sweep that ignored this would delete the project's audit trail and its reviewer-facing reproducibility cache. That is why the table below sorts by kind, and why `classify()` cannot return a delete verdict.

## Edges by kind

| Kind | Count | Meaning |
|---|---:|---|
| `doc-ref` | 1800 | a doc or handover naming another tracked file |
| `code-ref` | 748 | Python naming a tracked non-config file |
| `py-import` | 519 | Python import between tracked modules (includes test->src, page->src.dashboard) |
| `manifest-ref` | 117 | packaging or config file naming a tracked path |
| `code-config` | 75 | Python naming a tracked `*.yaml` |
| `script-report` | 39 | a `scripts/` runner naming its output under `reports/` |
| `code-data` | 7 | Python naming a tracked `*.jsonl` |

## Areas

| Area | Tracked files |
|---|---:|
| `src` | 113 |
| `(repo root)` | 60 |
| `reports` | 55 |
| `tests` | 41 |
| `scripts` | 29 |
| `docs` | 22 |
| `data` | 11 |
| `dashboard` | 9 |
| `config` | 7 |
| `.claude` | 4 |
| `assets` | 4 |
| `notebooks` | 2 |
| `paper` | 2 |
| `.streamlit` | 1 |
| `.vscode` | 1 |
| `logs` | 1 |
| `models` | 1 |
| `onboarding` | 1 |

## Most-referenced files

The repo's structural hubs -- change one and the blast radius is the count beside it.

| File | Inbound | Outbound |
|---|---:|---:|
| `docs/ethics.md` | 103 | 34 |
| `CLAUDE.md` | 93 | 62 |
| `config/taxonomy.yaml` | 75 | 3 |
| `PROJECT_PLAN.md` | 64 | 68 |
| `src/dashboard/view.py` | 38 | 13 |
| `docs/annotation_guidelines.md` | 37 | 2 |
| `src/preprocessing/audit.py` | 36 | 5 |
| `requirements-base.txt` | 35 | 4 |
| `src/models/dataset.py` | 35 | 14 |
| `src/security/audit.py` | 35 | 2 |
| `config/model_routing.yaml` | 32 | 4 |
| `requirements-ml.txt` | 32 | 4 |
| `data/interim/synth_precomp_v1/provenance.json` | 31 | 3 |
| `data/processed/silver/synth_precomp_v1/provenance.json` | 31 | 3 |
| `data/raw/synth_precomp_v1/provenance.json` | 31 | 3 |

## Two standing cautions

These are written here rather than derived, because neither is visible in the edge counts and both were found by reading. Keep them in this file; a hand-edit elsewhere would be erased by the next regeneration.

### `scripts/sync-dashboard.ps1` is load-bearing, not dead

It has zero inbound edges *and* no mention anywhere in the repo, which is the signature of dead code. It is the opposite. It is the deployment mechanism: it copies a named subset of this repo into the public `srn-dashboard` repo that feeds Streamlit Community Cloud, then commits and pushes. Its comments are the **only** written record of two things:

* **What is deliberately public.** Mirroring all of `src/` was quietly publishing the whole research tree -- `src/agents` (the OpenRouter routing layer), `src/annotation`, `src/labeling`, `src/reproducibility`, `src/security`, `src/taxonomy` -- into a public repository. Found by reading a dry run on 2026-09-15. The named-package list is the fix.
* **Why `packages.txt` is required.** Dropping it from a sync breaks the photo path *silently*: the app starts healthy, shows the uploader, and refuses every photo. Correct behaviour, indistinguishable from the feature being broken.

Deleting it would delete the public/private boundary along with it. The real defect is that nothing documents it -- fix that, not the file.

### `.claude.md` and `CLAUDE.md` both claim to be the single source of truth

Both are tracked. Both open with the same sentence. `.claude.md` was last updated at Phase 21 (`aee3711`); `CLAUDE.md` is current through Phase 30 and beyond. They are roughly 600 lines apart, and the string `.claude.md` appears in about twenty files including `src/dashboard/theme.py`, `tests/test_dashboard_pages.py` and three dashboard pages.

An agent told to read the single source of truth can land on the Phase-21 copy -- including its stale sec.11.3 flag default, which `CLAUDE.md` has since corrected. No file is being changed on the strength of this note; it is recorded so the next reader does not have to rediscover it.

## Files with no inbound edge

### committed reproducibility cache -- 7 file(s)

*keep -- tier B of docs/reproducibility.md; referenced by directory, never by name*

* `reports/predictions/random__lexicon.json`
* `reports/predictions/random__majority.json`
* `reports/predictions/random__tfidf_logreg.json`
* `reports/predictions/random__transformer.json`
* `reports/predictions/template_disjoint__lexicon.json`
* `reports/predictions/template_disjoint__majority.json`
* `reports/predictions/template_disjoint__tfidf_logreg.json`

### directory placeholder -- 11 file(s)

*keep -- zero-degree by design; it is what puts the directory in a clone*

* `dashboard/.gitkeep`
* `data/external/.gitkeep`
* `data/gold/.gitkeep`
* `data/interim/.gitkeep`
* `data/processed/silver/.gitkeep`
* `data/raw/.gitkeep`
* `logs/.gitkeep`
* `notebooks/.gitkeep`
* `paper/figures/.gitkeep`
* `reports/explain/.gitkeep`
* `scripts/.gitkeep`

### entry point -- 2 file(s)

*keep -- read from outside the graph, not from inside it*

* `.vscode/settings.json`
* `README.md`

### operator tooling -- 1 file(s)

*keep -- run by a human, never imported; see the cautions above*

* `scripts/build_project_map.py`

### provenance / audit trail -- 14 file(s)

*keep -- nothing imports the record of what was decided and why*

* `.claude/PRPs/plans/completed/phase29-decision-writeup.plan.md`
* `.claude/PRPs/reports/phase29-decision-writeup-report.md`
* `docs/phase32_implementation_plan.md`
* `handover_phase29_scenario_expansion.txt`
* `handover_phase_22b_dashboard.txt`
* `handover_phase_26_complete.txt`
* `handover_phase_27.txt`
* `handover_phase_28.txt`
* `handover_phase_29.txt`
* `phase13_prompt.md`
* `phase14_handover.md`
* `phase17_handover.md`
* `phase18_handover.md`
* `phase22_prompt.md`
