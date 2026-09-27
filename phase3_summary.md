# Phase 3 Summary - Related Work & Novelty Positioning

**Date:** 2026-08-08
**Status:** ✅ Complete. Acceptance gate passed.

## What Phase 3 required

| Gate | Status |
|---|---|
| Written gap statement in `docs/related_work.md` | ✅ already present (owner's 2026-08 evidence review) |
| ≥14 references | ✅ 14 domain + 5 method = 19 |
| `paper/refs.bib` exists; every entry resolves to a primary source with a DOI (or `[UNRESOLVED]`) | ✅ created; 0 unresolved |
| Identical citation keys across `related_work.md` and `refs.bib` | ✅ verified programmatically, both directions |

## What was done this session

1. **Resolved all 14 Consensus links to primary publisher records.** Each was verified by web
   search plus a Crossref or publisher-page lookup. Full author lists, exact titles, venues,
   volume/issue/pages and DOIs captured.
2. **Created `paper/refs.bib`** - 19 BibTeX entries, keys identical to `docs/related_work.md`.
3. **Rewrote the References section of `docs/related_work.md`** - now a four-column table
   (key / note / primary source / DOI), plus a separate method-reference table. The
   "secondary citation records" caveat is removed and replaced with a resolved-status note.
4. **Added 5 method citations** (the plan flagged this as a thin spot): Devlin2019 (BERT),
   He2021 (DeBERTa), Guo2017 (temperature scaling / calibration), Lundberg2017 (SHAP),
   Cohen1960 (kappa for inter-annotator agreement).

## Two corrections worth knowing about

- **`Toth2025` was mis-attributed.** The Consensus record credited "Tóth / Nuetzel". Those are
  the *handling editor* and a *reviewer* of the Frontiers article, not the authors. The real
  authors are **Nogueira, Morais, Mansell & Gomes**. This is exactly the class of error that
  kills a paper at review, and it is why this resolution step mattered. The key is retained
  for continuity; `refs.bib` and the table both carry the correction and a visible ⚠ flag.
- **Three keys were ASCII-ised** - `Domínguez-González2024` → `Dominguez-Gonzalez2024`,
  `Biró2024` → `Biro2024`, `Tóth2025` → `Toth2025`. BibTeX citation keys must be ASCII;
  accented keys break `\cite{}` in LaTeX. All in-text mentions in `related_work.md` were
  updated to match.

## On DOIs for conference papers

Three method references (He2021/ICLR, Guo2017/ICML, Lundberg2017/NeurIPS) have **no publisher
DOI** - these venues do not mint them. Their arXiv / PMLR / NeurIPS proceedings pages *are* the
primary records, so they are cited with `url` + a `note`. This is standard practice and is not
an unresolved citation. **Unresolved count: 0.**

## Files changed

- `paper/refs.bib` - new, 19 entries.
- `docs/related_work.md` - References section rewritten; keys ASCII-ised; caveat removed;
  method-reference table and a "still thin" list for Phase 23 added.
- `phase3_summary.md` - this file.
- `phase4_handover.md` - handover for the next phase.

## Verification performed

- `bibtexparser` parses `paper/refs.bib` cleanly → 19 entries, 0 duplicate keys.
- Key set diff between `refs.bib` and `docs/related_work.md` is empty in **both** directions.
- Only the 3 conference papers lack a `doi` field, as expected and documented.

## Not touched (correctly)

- `config/taxonomy.yaml` - that is Phase 4.
- Any `data/` directory.

## Known thin spots carried into later phases

- Multi-label text-classification methodology beyond a backbone citation.
- A weak-supervision / programmatic-labelling anchor (Snorkel-style) for Phase 6.
- **CSAI-2 and ABQ instrument citations** - needed in **Phase 4** so every construct in
  `config/taxonomy.yaml` has a real instrument anchor, not just a descriptive definition.
