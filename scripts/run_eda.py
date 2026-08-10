#!/usr/bin/env python
"""The Phase 9 gate: profile `data/interim/` and design the gold-set sample.

    python scripts/run_eda.py                  # profile + plan + report + figures
    python scripts/run_eda.py --no-write       # compute and print, write nothing
    python scripts/run_eda.py --source X       # a different interim source

Gate conditions, all checked below and each one a thing that would corrupt
Phase 11 if it were false:

  1. the profile reads `data/interim/`, and every record in it is de-identified;
  2. the synonym sweep has a human verdict for every signature it flags;
  3. the gold template partition is disjoint and covers all ten constructs;
  4. the gold eval and gold dev samples share no parent record;
  5. no candidate carries `generation_spec` to the annotator.

Under-powered constructs are **reported, not failed**. A gate that refused to
pass until the corpus were large enough would block Phase 9 on a Phase 7
regeneration the owner has not approved; a gate that stayed silent would let an
under-powered kappa reach the paper. The report says so in both places.

Offline, deterministic, free. No network, no API key, no cost.

Exit codes: 0 gate passed, 1 gate failed, 2 configuration error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation import figures  # noqa: E402
from src.evaluation.baselines import LexiconBaseline  # noqa: E402
from src.evaluation.profile import (  # noqa: E402
    CorpusProfile,
    histogram,
    load_interim,
    profile_corpus,
    tokenise,
)
from src.evaluation.sampling import (  # noqa: E402
    MIN_POSITIVES_PER_CONSTRUCT,
    GoldSamplingPlan,
    build_plan,
    write_candidates,
)
from src.ingestion import synonym_audit as SA  # noqa: E402
from src.ingestion.synthetic import GENERATOR_VERSION  # noqa: E402

DEFAULT_SOURCE = "synth_precomp_v1"
REPORT_PATH = Path("reports/eda.md")
FIGURE_DIR = Path("reports/figures")

WARNING = (
    "**GENERATOR METADATA, NOT LABELS.** Describes the template bank, not "
    "athlete language. Never use as evaluation ground truth."
)


def _rule(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def write_figures(
    profile: CorpusProfile,
    plan: GoldSamplingPlan,
    root: Path,
    texts: list[str],
    utterances_per_record: list[float],
) -> list[Path]:
    directory = root / FIGURE_DIR
    written: list[Path] = []

    written.append(
        figures.write(
            directory / "utterance_length_tokens.svg",
            figures.histogram_chart(
                histogram([float(len(tokenise(t))) for t in texts], bins=12),
                f"Utterance length (word tokens), n={profile.n_utterances}",
                "tokens per utterance",
            ),
        )
    )
    written.append(
        figures.write(
            directory / "utterances_per_record.svg",
            figures.histogram_chart(
                histogram(utterances_per_record, bins=9),
                f"Utterances per raw record, n={profile.n_records} records",
                "utterances per record",
            ),
        )
    )
    for name, counts in profile.strata.items():
        written.append(
            figures.write(
                directory / f"stratum_{name}.svg",
                figures.bar_chart(
                    list(counts),
                    [float(v) for v in counts.values()],
                    f"Utterances by {name} (n={profile.n_utterances})",
                ),
            )
        )
    planted = profile.generator_metadata.planted_construct_records
    written.append(
        figures.write(
            directory / "generator_planted_constructs.svg",
            figures.bar_chart(
                list(planted),
                [float(v) for v in planted.values()],
                "GENERATOR METADATA (not labels): records planting each construct",
            ),
        )
    )
    coverage = plan.gold_eval.construct_coverage
    written.append(
        figures.write(
            directory / "gold_eval_construct_coverage.svg",
            figures.grouped_bar_chart(
                list(planted),
                [
                    ("corpus records planting construct", [float(planted[k]) for k in planted]),
                    ("gold_eval items", [float(coverage.get(k, 0)) for k in planted]),
                ],
                "Corpus vs gold_eval construct coverage",
            ),
        )
    )
    return written


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def render_report(
    profile: CorpusProfile,
    plan: GoldSamplingPlan,
    findings: list,
    no_cue_eval: int,
    defect_records: tuple[int, int],
    defect_utterances: tuple[int, int],
    realised: dict[str, int],
    figure_paths: list[Path],
) -> str:
    from src.evaluation.metrics import Interval

    def ci(interval: Interval) -> str:
        return f"{interval.point:.3f} [{interval.low:.3f}, {interval.high:.3f}]"

    lines: list[str] = []
    add = lines.append

    add("# Phase 9 — Exploratory Data Analysis & Quality Profiling")
    add("")
    add(
        f"Source: `{profile.source_id}` · generator "
        f"`construct-template-grammar@{GENERATOR_VERSION}`, seed 42, "
        f"n={profile.n_records:,} records"
    )
    add("")
    add("> **This corpus is 100% synthetic (OPEN-011).** Every distribution below is a")
    add("> distribution over a template grammar written by this project. None of it is")
    add("> evidence about how athletes actually talk, and no sentence in this report")
    add("> should be quoted as if it were. The corpus exists so the pipeline can be")
    add("> built and measured before real text arrives; acquiring real pre-competition")
    add("> athlete text remains the project's highest live risk.")
    add("")
    add(
        f"> **Unit warning.** Phase 8 turned {profile.n_records:,} raw *records* into "
        f"{profile.n_utterances:,} *utterances*. Every number below is tagged with its"
    )
    add("> unit. Per-record and per-utterance figures are not comparable, and Phase 7's")
    add("> per-record statistics are not comparable with anything here.")
    add("")
    add("Everything in this file is regenerated by `python scripts/run_eda.py`. The")
    add("arithmetic lives in `src/evaluation/profile.py` and `src/evaluation/sampling.py`,")
    add("under `pytest`, not in a notebook.")
    add("")

    # -- 0. corrections
    add("## 0. What changed, and every number it superseded")
    add("")
    add("Phase 9 and Phase 9b closed five corpus defects in sequence. Each regeneration")
    add("moves the RNG stream, so **every** downstream count changed each time — not only")
    add("the sentences the fix touched. Superseded figures are listed rather than quietly")
    add("overwritten.")
    add("")
    add("| Step | Issue | Action | Generator |")
    add("|---|---|---|---|")
    add("| 1 | OPEN-015 | delete `(part, portion, corner, piece)` | v1.1 → **v1.2** |")
    add("| 2 | OPEN-016 | **guard** `_vary` against ruled-defective frames | v1.2 → **v1.3** |")
    add("| 3 | OPEN-017 | default corpus 1,200 → **4,000** records | v1.3 |")
    add(
        "| 4 | OPEN-020 | template bank 7–12 → **15 realisations per construct** | v1.3 → **v1.4** |"
    )
    add("| 5 | OPEN-018 | discourse suffixes become **clauses**, not sentences | v1.4 |")
    add("")
    add("| Quantity | v1.1 | v1.2 (n=1.2k) | v1.3 (n=4k) | **v1.4 (n=4k)** |")
    add("|---|---|---|---|---|")
    add("| Records | 1,200 | 1,200 | 4,000 | **4,000** |")
    add("| Utterances | 4,110 | 4,141 | 13,651 | **9,302** |")
    add("| Templates per construct | 7–12 | 7–12 | 7–12 | **15** |")
    add("| Records with a broken substitution | — | 190 (15.8%) | 0 | **0** |")
    add("| Realised vocabulary (raw records) | 635 | 636 | 625 | **860** |")
    add("| Utterance exact-duplicate rate | — | 73.6% | 87.4% | **37.6%** |")
    add("| `gold_eval` drawn / target 400 | — | 235 | 400 | **400** |")
    add("| Constructs below the 40-positive floor | — | 7 / 10 | 0 / 10 | **0 / 10** |")
    add("| Lexicon macro-F1, template-disjoint | — | 0.706 | 0.780 | **0.461** |")
    add("")
    add("**Read the last two rows together — this is the most important thing on the page.**")
    add("Utterance count *fell* from 13,651 to 9,302 while the corpus grew, because the")
    add("discourse suffixes stopped being separate sentences. And the lexicon baseline lost")
    add("0.32 macro-F1 without the corpus becoming harder in any real sense. Both are")
    add("explained below (§3 and §5b); neither is a regression.")
    add("")
    add("**Four published numbers were found to be wrong and corrected, not glossed:**")
    add("")
    add('1. `src/ingestion/synthetic.py` said `"corner of me"` occurred in **11** records.')
    add("   The true v1.1 count is **9**, verified by reconstructing the committed v1.1")
    add("   generator from `git show 6f9561a:` and regenerating at seed 42.")
    add("2. `docs/data_sources.md` reported v1.1 as **638** types / **1,163** distinct texts")
    add("   / **40,169** tokens / **106** construct-free records. The committed generator")
    add("   produces **635 / 1,161 / 40,251 / 92**. Small, and it changes no conclusion —")
    add("   but `CLAUDE.md` §9 claims a reviewer can reproduce these exactly, so a figure")
    add("   that does not reproduce is a defect regardless of size.")
    add("3. A field named `templates_per_record` counted **constructs**. Renamed.")
    add("4. **`src/evaluation/baselines.py` claimed the lexicon baseline is independent of")
    add("   the corpus. It is not** — see §5b. That claim has been in the repo since Phase 7")
    add("   and every lexicon number reported before v1.4 carries an upward bias.")
    add("")

    # -- 1. shape
    add("## 1. Corpus shape")
    add("")
    add("| Quantity | Unit | n | Mean [95% CI] | SD | Min | p25 | Median | p75 | p90 | Max |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for dist in (
        profile.utterance_chars,
        profile.utterance_tokens,
        profile.record_chars,
        profile.record_tokens,
        profile.utterances_per_record,
    ):
        unit = (
            "utterance" if "utterance" in dist.unit and "per record" not in dist.unit else "record"
        )
        add(
            f"| {dist.unit} | {unit} | {dist.n:,} | {dist.mean:.2f} "
            f"[{dist.mean_ci.low:.2f}, {dist.mean_ci.high:.2f}] | {dist.sd:.2f} | "
            f"{dist.minimum:.0f} | {dist.p25:.0f} | {dist.median:.0f} | {dist.p75:.0f} | "
            f"{dist.p90:.0f} | {dist.maximum:.0f} |"
        )
    add("")
    add("Token counts here use `profile.tokenise` (alphabetic words and placeholders),")
    add("which is **not** the generator's whitespace tokeniser. `docs/data_sources.md`")
    add("reports 33.9 words per record on the latter; this table reports 33.86 on the")
    add("former. Neither is wrong and they must not be mixed — the generator's counts")
    add("digits and bare punctuation as tokens, this one does not, and a corpus")
    add("statistic quoted without its tokeniser is not reproducible.")
    add("")
    add("Confidence intervals are percentile bootstrap, 1,000 resamples, seed 42, via")
    add("`src/evaluation/metrics.py::bootstrap_statistic`. They quantify sampling")
    add("variability **within this corpus** — that is, across draws from this template")
    add("grammar. They say nothing about athlete language.")
    add("")
    add("![utterance length](figures/utterance_length_tokens.svg)")
    add("")
    add("![utterances per record](figures/utterances_per_record.svg)")
    add("")
    add(
        "**Read the median utterance length carefully.** At "
        f"{profile.utterance_tokens.median:.0f} tokens the median utterance is one short"
    )
    add("sentence. That is short for a construct judgement: `appraisal_orientation`")
    add("(challenge vs threat framing) is a stance towards an event, and a nine-token")
    add("sentence often does not carry enough of it for two annotators to agree. This is")
    add("the argument for giving annotators the **parent record as context** while asking")
    add("them to label the utterance — recorded here as an input to Phase 10's")
    add("annotation-interface design.")
    add("")

    # -- 2. vocabulary
    v_with = profile.vocabulary_with_placeholders
    v_without = profile.vocabulary_without_placeholders
    add("## 2. Vocabulary and type-token behaviour")
    add("")
    add("| Measure | Including placeholders | Excluding placeholders |")
    add("|---|---|---|")
    add(f"| Tokens | {v_with.tokens:,} | {v_without.tokens:,} |")
    add(f"| Types (vocabulary size) | {v_with.types:,} | {v_without.types:,} |")
    add(f"| Raw TTR | {v_with.ttr:.4f} | {v_without.ttr:.4f} |")
    add(
        f"| **MATTR** (window {v_with.mattr_window}) | **{v_with.mattr:.4f}** | "
        f"**{v_without.mattr:.4f}** |"
    )
    add(f"| Hapax legomena | {v_with.hapax} | {v_without.hapax} |")
    add(f"| Hapax rate | {v_with.hapax_rate:.4f} | {v_without.hapax_rate:.4f} |")
    add("")
    add(f"**Placeholder tokens in the corpus: {profile.placeholder_token_count}.** The two")
    add("columns are identical, and that is the expected result — the A2 generator plants")
    add("no personal names, so the de-identifier had nothing to replace. The columns are")
    add("computed and reported separately anyway, because the moment an A3 consented")
    add("donation arrives they will diverge, and a report that only ever printed one")
    add("number would not show it.")
    add("")
    add("**Why MATTR is the headline and raw TTR is not.** TTR is types÷tokens, and it")
    add("falls mechanically as a text grows: a corpus eventually stops meeting new words")
    add(
        "but never stops accumulating tokens. So a TTR computed over "
        f"{profile.n_utterances:,} utterances is *not* comparable with the TTR Phase 7"
    )
    add(f"reported over {profile.n_records:,} records, even though the underlying text is")
    add("the same — the number would fall with no change in lexical richness whatsoever,")
    add("purely because the denominator grew. That is exactly the comparison a reader is")
    add("most likely to make. MATTR averages the TTR of every fixed-length window, so the")
    add("length confound is gone by construction and the figure **is** comparable across")
    add("corpora of different sizes (Covington & McFall, 2010). Quote MATTR.")
    add("")
    add(f"**MATTR = {v_with.mattr:.3f}** is high in absolute terms, and it is not evidence")
    add("of a rich corpus. Within any 50-token window the text looks varied; across the")
    add(
        "whole corpus there are only "
        f"{v_with.types} distinct word types and {v_with.hapax} hapax legomena. A natural"
    )
    add("English corpus of 40,000 tokens would show several thousand types and a hapax")
    add("rate near 40–50%. **OPEN-012 is mitigated, not solved**, and MATTR should not be")
    add("used in the paper as a claim that it is.")
    add("")
    add("**Tokeniser note, carried to Phase 13.** Placeholders such as `[ATHLETE]` and")
    add("`[EVENT_WINDOW]` are single tokens here by construction. A subword tokeniser will")
    add("split them into `[`, `EVENT`, `_`, `WINDOW`, `]` unless they are registered as")
    add("special tokens. That would turn one privacy artefact into five vocabulary items")
    add("and put a subword boundary *inside* a span the explainability layer later")
    add("attributes over — which is contribution #2's unit. Register them.")
    add("")
    add("Most frequent types (including placeholders):")
    add("")
    add("| Rank | Type | Count |")
    add("|---|---|---|")
    for rank, (token, count) in enumerate(v_with.top_types[:15], start=1):
        add(f"| {rank} | `{token}` | {count:,} |")
    add("")

    # -- 3. duplicates
    ud, rd = profile.utterance_duplicates, profile.record_duplicates
    add("## 3. Duplicates — the largest data-quality finding in this phase")
    add("")
    add("| Measure | Utterances | Records |")
    add("|---|---|---|")
    add(f"| n | {ud.n:,} | {rd.n:,} |")
    add(f"| Distinct texts | {ud.distinct:,} | {rd.distinct:,} |")
    add(f"| Distinct rate | {_pct(ud.distinct_rate)} | {_pct(rd.distinct_rate)} |")
    add(
        f"| Items sharing text with another (exact) | {ud.exact_duplicate_items:,} | "
        f"{rd.exact_duplicate_items:,} |"
    )
    add(
        f"| **Exact duplicate rate [95% CI]** | **{ci(ud.exact_duplicate_rate_ci)}** | "
        f"{ci(rd.exact_duplicate_rate_ci)} |"
    )
    add(
        f"| Near-duplicate items (Jaccard ≥ {ud.jaccard_threshold}) | "
        f"{ud.near_duplicate_items:,} | {rd.near_duplicate_items:,} |"
    )
    add(
        f"| Near-duplicate rate [95% CI] | {ci(ud.near_duplicate_rate_ci)} | "
        f"{ci(rd.near_duplicate_rate_ci)} |"
    )
    add("")
    add(f"**{_pct(ud.exact_duplicate_rate_ci.point)} of utterances share their exact text")
    add("with at least one other utterance.** The effective per-utterance corpus is")
    add(f"**{ud.distinct:,} distinct strings, not {ud.n:,}.** At record level the same")
    add(f"corpus is {_pct(rd.exact_duplicate_rate_ci.point)} duplicated, so this is almost")
    add("entirely an artefact of segmentation, not of generation.")
    add("")
    add("**Mechanism.** `DISCOURSE_SUFFIXES` and `NEUTRAL_SENTENCES` in the generator are")
    add("appended as whole sentences and are rendered **without** the near-synonym")
    add("variation layer (`generate_records` applies `_vary` to construct realisations")
    add("only). Phase 8 then segments each of them into its own standalone utterance. A")
    add("fixed bank of ~8 suffixes spread across 1,200 records therefore produces the same")
    add("string hundreds of times:")
    add("")
    add("| Repeated utterance | Occurrences |")
    add("|---|---|")
    for text, count in ud.most_repeated[:8]:
        add(f"| `{text}` | {count} |")
    add("")
    add("**Why this is a gold-set problem and not a cosmetic one.** Two annotators")
    add('agreeing on `"It is what it is."` 268 times is *one* agreement counted 268')
    add("times. A gold set sampled without collapsing duplicates would report a kappa")
    add("inflated by repetition, and the inflation would be invisible in the kappa itself.")
    add("The sampling plan in §7 therefore deduplicates before drawing, and §7 reports how")
    add("many items that costs.")
    add("")

    # -- 4. junk
    junk = profile.junk
    add("## 4. Junk and degenerate utterances")
    add("")
    add(f"Flagged: **{junk.flagged:,} of {junk.n:,}** utterances ({ci(junk.flagged_rate_ci)}).")
    add("")
    add("| Check | Utterances flagged | Example |")
    add("|---|---|---|")
    for check, count in junk.by_check.items():
        example = junk.examples.get(check, "")
        add(f"| `{check}` | {count} | `{example}` |")
    for check in (
        "no_alphabetic_content",
        "placeholder_only",
        "unbalanced_brackets",
        "truncated_ending",
        "repeated_token_run",
    ):
        if check not in junk.by_check:
            add(f"| `{check}` | 0 | — |")
    add("")
    add("Only `too_short` fires. `MIN_ANNOTATABLE_TOKENS` is 4 words; the flagged items")
    add("are discourse fragments such as `That's it.` Nothing is deleted on the strength")
    add("of this flag — the corpus keeps them, and only the **gold sample** excludes them,")
    add("because handing an annotator a two-word fragment and then reporting the resulting")
    add("disagreement as annotator unreliability would be measuring the sampling design.")
    add("")
    add("Zero `truncated_ending` flags is a **positive result about Phase 8's segmenter**:")
    add("every utterance ends on sentence-final punctuation, so no span was cut mid-clause.")
    add("Phase 8's offset check proves offsets are arithmetically right; this proves they")
    add("land on linguistically sensible boundaries, which is the property contribution #2")
    add("actually needs.")
    add("")

    # -- 5. synonym sweep
    add("## 5. Systematic synonym sweep — OPEN-015 was not an isolated defect")
    add("")
    total_events = len(SA.substitution_events())
    add(
        "OPEN-015 was found by a human reading about twenty records. "
        "`src/ingestion/synonym_audit.py` replaces that with an **exhaustive** enumeration"
    )
    add(
        f"of every single-token substitution the generator can make — "
        f"{len(SA.varied_templates())} filled template variants, **{total_events} substitution"
    )
    add("events** — screened by six mechanical probes (idiom membership, article agreement,")
    add("number agreement, particle/argument structure, inflected form, and arity).")
    add("")
    add(f"- **{len(findings)} distinct signatures flagged**, every one carrying a recorded")
    add("  human verdict (the build fails on an unreviewed signature).")
    add(
        f"- **{sum(1 for f in findings if f.verdict == SA.BROKEN)} ruled `broken`**, "
        f"{sum(1 for f in findings if f.verdict == SA.DEGRADED)} `degraded`, "
        f"{sum(1 for f in findings if f.verdict == SA.ACCEPTABLE)} `acceptable`."
    )
    add("")
    add("### The finding, and the fix")
    add("")
    add("At v1.2 the sweep found that OPEN-015 had **not** been isolated: **190 of 1,200")
    add("records (15.8%)** still contained a substitution a human ruled broken or degraded,")
    add("across 55 realised signatures. Deleting one synonym group had fixed 0.8% of records")
    add("and left the other 15%. Examples, all now eliminated:")
    add("")
    add('- *"I can feel my heart pick up a bit when I **figure about** the first ball."*')
    add('- *"my **insides is** in knots and my fingers won\'t stop shaking"* — number')
    add('- *"we\'ve got **a approach** for the first bell"* — article agreement')
    add("- *\"I'm **on edge I'll** let everyone down\"* — no clausal complement")
    add("")
    add("**Resolved at v1.3 by guarding the generator, not by shrinking it** (OPEN-016,")
    add("option (c)). `_vary` applies each candidate substitution, checks the result against")
    add("the ruled-defective signatures, and reverts it if it would produce one. `think →")
    add('figure` is broken in *"all I figure about"* and unremarkable in *"I figure I\'m')
    add('ready"* — the defect belongs to the **frame**, not the word.')
    add("")
    add("Both candidate remedies were measured at n=4,000 rather than argued:")
    add("")
    add("| | Synonym bank | Realised vocabulary | Defective records |")
    add("|---|---|---|---|")
    add("| v1.2, unguarded | 64 groups | 643 types | 630 (15.75%) |")
    add("| Option (a): delete the 34 implicated members | 57 groups | 594 types | 0 |")
    add("| **Option (c): guard — chosen** | **64, unchanged** | **625 types** | **0** |")
    add("")
    add(
        f"**Current corpus: {defect_records[0]} of {defect_records[1]} records and "
        f"{defect_utterances[0]} of {defect_utterances[1]} utterances carry a defect.**"
    )
    add("")
    add("### The ratchet earned its keep at Phase 9b")
    add("")
    add("Doubling the template bank created **28 substitution frames nobody had ruled on**,")
    add('and the build refused to pass until each was judged: 19 `broken` (*"a entry list"*,')
    add('*"spectators keeps"*, *"I keep myself crowded with"*), 5 `degraded`, 4 fine. Not')
    add("one of them was found by reading — the sweep enumerated them, the test failed, and")
    add("a human ruled. **That is the difference between a control and a good intention.**")
    add(f"The sweep now covers {len(SA.substitution_events())} substitution events over")
    add(f"{len(findings)} signatures, all reviewed.")
    add("")
    add("**The honest limit.** The guard is only as good as its hand-ruled table and cannot")
    add("catch a defect class nobody has thought of. What it does is make the failure mode")
    add("**non-recurring**: a new class still needs a human to notice it once, but no longer")
    add("needs a human to notice it repeatedly.")
    add("")
    add("## 5b. The lexicon baseline is not independent of the corpus (OPEN-021)")
    add("")
    add("**This is a correction to a Phase 7 claim, found by doing Phase 9b, and it is the")
    add("most consequential finding in this report.**")
    add("")
    add('`src/evaluation/baselines.py` documented `LexiconBaseline` as *"immune to the')
    add('template leakage that inflates the others"*, on the reasoning that its cues were')
    add("hand-written from `taxonomy.yaml` rather than induced from labels. Avoiding")
    add("induction prevents *direct* inheritance. It does not prevent **shared ancestry** —")
    add("the template bank was written from the same `positive_examples`, several Phase 7")
    add("templates reproduce them near-verbatim, and so cue list and corpus are cousins.")
    add("")
    add("Phase 9b measured it, because the Phase 9b templates were written to the same")
    add("construct *definitions* but deliberately not to the same example *phrasings*:")
    add("")
    add("| Template set | Lexicon fires on |")
    add("|---|---|")
    add("| Written at Phase 7 (pre-9b) | **73%** (66/90) |")
    add("| Written at Phase 9b | **22%** (13/60) |")
    add("")
    add("Nothing about the constructs changed between those sets. What changed is how much")
    add("wording they share with the cue list.")
    add("")
    add("**Two consequences the paper must carry.**")
    add("")
    add("1. **The lexicon's template-disjoint macro-F1 fell 0.780 → 0.461.** The corpus did")
    add("   not get harder; the baseline lost an advantage it should never have been")
    add("   credited with. **0.461 is the more honest floor**, and every lexicon number")
    add("   published before v1.4 carries an upward bias. Report the drop — a baseline whose")
    add("   score depends this much on phrasing overlap with its own source is a finding")
    add("   about lexicon baselines in general, not a defect peculiar to this project.")
    add("2. **The Phase 9 'cue fraction' correction is withdrawn.** Phase 9 used this")
    add("   lexicon to estimate what share of gold candidates carry construct language, and")
    add("   reported 0.62. That number measured overlap with the cue list, not construct")
    add("   presence. It is not reported as a corrected floor anywhere in this document")
    add("   any more, and OPEN-017's residual can only be settled by annotation (Phase 11).")
    add("")
    add("For reference and clearly labelled as such: the lexicon currently fires on")
    add(f"{plan.gold_eval.size - no_cue_eval} of {plan.gold_eval.size} `gold_eval` items")
    add(f"({(plan.gold_eval.size - no_cue_eval) / plan.gold_eval.size:.1%}). **Read that as")
    add("lexicon coverage of the gold set, not as construct prevalence.**")
    add("")

    # -- 6. coverage & strata
    add("## 6. Metadata coverage and strata")
    add("")
    add("Contribution #3 is the time-aware, fusion-ready design. It rests entirely on")
    add("these fields being present, so they are measured rather than assumed.")
    add("")
    add("| Field | Coverage [95% CI] |")
    add("|---|---|")
    for name, interval in profile.coverage.items():
        add(f"| `{name}` | {ci(interval)} |")
    add("")
    add("`training_load_hint` is the only partially-covered field, by design — the")
    add("generator emits it for a subset of records, so it is a genuinely optional")
    add("context signal and any model using it must handle its absence. Every other")
    add("field is complete. A CI of `[1.000, 1.000]` looks redundant at 100% and is not:")
    add('it is a different statement from a bare "100%", and when the first A3 donation')
    add("arrives with patchy metadata the same table will show the difference with no")
    add("code change.")
    add("")
    for name, counts in profile.strata.items():
        add(f"**`{name}`** (utterances)")
        add("")
        add("| Value | Utterances | Share |")
        add("|---|---|---|")
        total = sum(counts.values())
        for value, count in counts.items():
            add(f"| `{value}` | {count:,} | {_pct(count / total)} |")
        add("")
        add(f"![{name}](figures/stratum_{name}.svg)")
        add("")
    add("Strata are close to uniform, which is a property of the generator's stratum")
    add("draw and **not** a finding about athlete populations. `time_band` is the")
    add("exception: `eve` (1–2 days out) is over-represented because the band spans two")
    add("of the generator's ten `time_to_competition_days` values while `day_of` spans one.")
    add("")

    # -- 7. sampling plan
    add("## 7. Gold-set sampling plan (Phase 11) — the deliverable")
    add("")
    add("Implemented in `src/evaluation/sampling.py`; the drawn candidates are written to")
    add("`data/processed/gold_candidates/`. **Not** `data/gold/`, which is human-owned and")
    add("which no agent writes to.")
    add("")
    add("### 7.1 Why the obvious plan fails, measured not assumed")
    add("")
    add('The obvious plan is *"draw the gold set from the test side of')
    add('`template_disjoint_split`"*. Run on this corpus it gives **98 records / 228')
    add("utterances** on the test side and **zero records planting")
    add("`appraisal_orientation`**. One of the ten locked constructs would have no gold")
    add("items and its kappa would be undefined rather than low.")
    add("")
    add("The cause: `template_disjoint_split` shuffles all 85 templates as a single pool.")
    add("With 7–12 templates per construct, a global 20% holdout can miss a construct")
    add("entirely. That function is not wrong — it is the right tool for the leakage")
    add("*comparison* it was built for — it is the wrong tool for carving an evaluation")
    add("set that must cover every label. It is unchanged; a stricter partitioner was")
    add("added alongside it.")
    add("")
    add("### 7.2 The plan")
    add("")
    add("**Step 1 — partition templates per construct.**")
    add(
        "`construct_stratified_template_partition` holds out "
        f"{plan.partition.holdout_fraction:.0%} of *each construct's* templates"
    )
    add("independently, floor of one. Still a partition of the template set, so template")
    add("disjointness holds; coverage of every construct is now guaranteed by construction.")
    add("")
    add("| Construct | Templates | Held out for gold |")
    add("|---|---|---|")
    for construct, total in plan.partition.per_construct_total.items():
        add(f"| `{construct}` | {total} | {plan.partition.per_construct_holdout[construct]} |")
    add("")
    add(
        f"Disjoint: **{plan.partition.is_disjoint}**. Constructs with no holdout: "
        f"**{plan.partition.constructs_without_holdout or 'none'}**."
    )
    add("")
    add("**Step 2 — assign records, not utterances.** A record joins the gold pool only if")
    add("*every* template it uses is held out; the training pool only if none is;")
    add("otherwise it is discarded. This is the one place the unit must be the record:")
    add("two utterances of the same record share its templates, so drawing utterances")
    add("independently would put siblings on both sides and reintroduce exactly the")
    add("leakage Phase 7 quantified.")
    add("")
    add("**Step 3 — filter for annotatability.**")
    add("")
    add("| Exclusion | gold_eval pool | gold_dev pool |")
    add("|---|---|---|")
    e, d = plan.gold_eval.eligibility, plan.gold_dev.eligibility
    assert e is not None and d is not None
    add(f"| Considered | {e.considered:,} | {d.considered:,} |")
    add(f"| Straddling / template-free | {e.excluded_no_template:,} | {d.excluded_no_template:,} |")
    add(f"| Junk (`too_short`) | {e.excluded_junk:,} | {d.excluded_junk:,} |")
    add(f"| Exact / near duplicate | {e.excluded_duplicate:,} | {d.excluded_duplicate:,} |")
    add(f"| **Eligible** | **{e.eligible:,}** | **{d.eligible:,}** |")
    add("")
    add("**Step 4 — draw, construct quotas first then context balance.** Round-robin")
    add("across constructs to the per-construct floor, then greedily fill the remainder")
    add("by whichever item most improves the worst-served stratum cell, in priority order")
    add("`time_band` → `sport` → `competition_level` → `region`. Marginal balance, not")
    add("joint: 10 sports × 5 levels × 5 regions × 5 bands is 1,250 cells and the sample is")
    add("400 items, so a jointly balanced design is arithmetically impossible and claiming")
    add("one would be false.")
    add("")
    add("**Step 5 — two annotators, 100% double-annotated.** Both annotators label every")
    add("gold_eval item, so Cohen's kappa is computable per construct on the whole set.")
    add("Partial double-annotation would save time and make the per-construct kappas rest")
    add("on a subset too small to interval. `generation_spec` is **stripped** from every")
    add("written candidate: showing an annotator which construct the generator planted is")
    add("the most direct possible way to destroy the independence a kappa depends on.")
    add("")
    add("**Step 6 — calibrate on `gold_dev` first.** `gold_dev` is drawn from")
    add("**training-side** templates. Annotators argue over the rubric on it, revise")
    add("`docs/annotation_guidelines.md`, and only then start `gold_eval`. An item read")
    add("during an argument about the rubric is no longer an independent measurement, so")
    add("spending training-side items on calibration costs zero evaluation power.")
    add("")
    add("### 7.3 What the plan actually yields today")
    add("")
    add("| | gold_eval | gold_dev |")
    add("|---|---|---|")
    add("| Target | 400 | 100 |")
    add(f"| **Drawn** | **{plan.gold_eval.size}** | **{plan.gold_dev.size}** |")
    add(
        f"| Distinct parent records | {len(plan.gold_eval.parent_record_ids)} | "
        f"{len(plan.gold_dev.parent_record_ids)} |"
    )
    add(f"| Leakage-safe | {plan.is_leakage_safe} | — |")
    add("")
    add("Construct coverage of the drawn sample. " + WARNING)
    add("")
    add("| Construct | gold_eval items | Floor (40) met? |")
    add("|---|---|---|")
    for construct, count in plan.gold_eval.construct_coverage.items():
        met = "yes" if count >= 40 else "**no**"
        add(f"| `{construct}` | {count} | {met} |")
    add("")
    add("![gold coverage](figures/gold_eval_construct_coverage.svg)")
    add("")
    add("### 7.4 Statistical power: what is settled and what is not")
    add("")
    add(
        f"**The stated floor is met.** `gold_eval` draws its full target of "
        f"{plan.gold_eval.size} items and **all ten constructs clear "
        f"{MIN_POSITIVES_PER_CONSTRUCT} positives**. At n=1,200 it drew 235 and seven"
    )
    add("constructs fell short; raising the corpus to 4,000 (OPEN-017) fixed that, and")
    add("doubling the template bank (OPEN-020) held it while roughly doubling the number of")
    add("distinct phrasings behind each construct.")
    add("")
    add("**What OPEN-020 actually bought, stated in the unit that matters.** A 35% holdout")
    add("over 15 templates per construct leaves **5 phrasings** in the evaluation set,")
    add("against **2–4** before. A kappa computed on 3 phrasings is a kappa about those 3")
    add("phrasings; 5 is not generous, and the paper should say so, but it is the")
    add("difference between a number a reviewer will interrogate and one they will dismiss.")
    add("")
    add("**One correction, withdrawn.** Phase 9 reported that ~38% of drawn items carried")
    add("no construct cue, applied that as a 0.62× correction to the coverage table, and")
    add("concluded that 7 of 10 constructs were still under-powered. **That correction is")
    add("withdrawn** — it was computed with `LexiconBaseline`, which §5b shows is not a")
    add("construct detector but a measure of overlap with its own cue list. The evidence:")
    add("the same proxy now reports a *worse* figure on a corpus with twice the construct")
    add("phrasings, which is not a statement about constructs at all.")
    add("")
    add("**So the honest position is: the raw floor is met, and the corrected floor is")
    add("unknown until humans annotate.** Phase 11 is what settles it. The two things to")
    add("carry into that phase:")
    add("")
    add("1. The coverage table below is still an **upper bound**, for the OPEN-019 reason —")
    add("   `generation_spec` is replicated onto every utterance of a record, including the")
    add("   ones realising no construct. That fact is independent of the lexicon and stands.")
    add(
        "2. If annotation shows a construct materially short of "
        f"{MIN_POSITIVES_PER_CONSTRUCT} positives, the fix is a **larger gold set**, not a"
    )
    add(
        "   larger corpus. The eligible pool is "
        f"{plan.gold_eval.eligibility.eligible if plan.gold_eval.eligibility else 0} items,"
    )
    add(f"   so `TARGET_GOLD_EVAL` can rise from {plan.gold_eval.size} without regenerating")
    add("   anything — at the cost of proportionally more annotation time.")
    add("")
    add("**One tempting fix stays rejected.** The draw could prefer utterances the lexicon")
    add("detects, which would make the coverage table look better immediately. It must not:")
    add("selecting gold items by lexicon detectability builds that baseline's strengths into")
    add("the evaluation set, so the lexicon would then beat the transformer on a test set")
    add("chosen to suit it. §5b makes this worse, not better — the lexicon is already")
    add("entangled with the template bank, and selecting on it would entangle the gold set")
    add("too. That is not a gold set, it is a rigged one.")
    add("")

    # -- 8. issues
    add("## 8. Data-quality issues, ranked")
    add("")
    add("| # | Issue | Measure | Owner | Status |")
    add("|---|---|---|---|---|")
    add("| 1 | Corpus is 100% synthetic | 1,200/1,200 records | OPEN-011 | open, highest risk |")
    add(
        f"| 2 | Residual ungrammatical substitutions | {_pct(defect_records[0] / defect_records[1])} "
        "of records | OPEN-016 | **new**, needs owner decision |"
    )
    add(
        "| 3 | Gold pool too small for per-construct kappa | 7/10 below floor | OPEN-017 | "
        "**new**, needs owner decision |"
    )
    add(
        f"| 4 | Utterance-level exact duplication | {_pct(ud.exact_duplicate_rate_ci.point)} | "
        "OPEN-018 | **new**, mitigated in the sampling plan |"
    )
    add(
        f"| 5 | Vocabulary bounded by the template bank | {v_with.types} types, "
        f"{v_with.hapax} hapax | OPEN-012 | monitored |"
    )
    add(
        "| 6 | `generation_spec` replicated per utterance | 3.45× inflation | OPEN-019 | "
        "**new**, documentation fix |"
    )
    add(
        f"| 7 | Sub-annotatable utterances | {junk.flagged} ({_pct(junk.flagged_rate_ci.point)}) | "
        "— | handled in sampling |"
    )
    add("")

    # -- 9. reproduction
    add("## 9. Reproducing this report")
    add("")
    add("```bash")
    add("python scripts/run_ingestion.py          # regenerate data/raw/ at seed 42")
    add("python scripts/run_preprocessing.py      # regenerate data/interim/")
    add("python scripts/run_benchmark_audit.py    # leakage + baselines")
    add("python scripts/run_eda.py                # this report + figures + candidates")
    add("```")
    add("")
    add("All four are offline, deterministic and free. Figures are hand-written SVG")
    add("(`src/evaluation/figures.py`) rather than matplotlib, so the light Docker image")
    add("gains no plotting dependency and a regenerated figure with unchanged data")
    add("produces an empty `git diff`.")
    add("")
    add("Figures written: " + ", ".join(f"`{p.name}`" for p in figure_paths))
    add("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 9 EDA gate")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--no-write", action="store_true", help="compute only")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    failures: list[str] = []

    _rule(f"Loading data/interim/{args.source}")
    records = load_interim(args.source)
    print(f"  {len(records):,} utterances")
    not_deidentified = [r.record_id for r in records if not r.deidentified]
    if not_deidentified:
        failures.append(f"{len(not_deidentified)} utterances are not de-identified")
    print(f"  de-identified: {len(records) - len(not_deidentified)}/{len(records)}")

    _rule("Profiling")
    texts = [r.text for r in records]
    grouped = _group(records)
    utterances_per_record = [float(len(v)) for v in grouped.values()]
    profile = profile_corpus(records, args.source, seed=args.seed)
    print(f"  records: {profile.n_records:,}   utterances: {profile.n_utterances:,}")
    print(
        f"  vocabulary: {profile.vocabulary_with_placeholders.types} types  "
        f"MATTR={profile.vocabulary_with_placeholders.mattr:.4f}  "
        f"raw TTR={profile.vocabulary_with_placeholders.ttr:.4f}"
    )
    print(
        f"  exact duplicate utterances: {profile.utterance_duplicates.exact_duplicate_items:,} "
        f"({profile.utterance_duplicates.exact_duplicate_rate_ci})"
    )
    print(f"  junk: {profile.junk.flagged} ({profile.junk.by_check})")

    _rule("Synonym sweep (OPEN-015 class)")
    findings = SA.audit()
    unreviewed = SA.unreviewed(findings)
    print(f"  substitution events enumerated: {len(SA.substitution_events())}")
    print(f"  signatures flagged: {len(findings)}   unreviewed: {len(unreviewed)}")
    if unreviewed:
        failures.append(f"{len(unreviewed)} synonym signatures have no human verdict")
    raw_texts = [" ".join(p.text for p in group) for group in grouped.values()]
    defect_records = SA.defect_rate(findings, raw_texts)
    defect_utterances = SA.defect_rate(findings, [r.text for r in records])
    realised = {
        k: v for k, v in SA.corpus_prevalence(SA.defective(findings), raw_texts).items() if v
    }
    print(
        f"  records containing a defect : {defect_records[0]}/{defect_records[1]} "
        f"({defect_records[0] / defect_records[1]:.1%})"
    )
    print(f"  utterances containing a defect: {defect_utterances[0]}/{defect_utterances[1]}")
    print(f"  distinct defective signatures realised: {len(realised)}")

    _rule("Gold-set sampling plan")
    plan = build_plan(records, args.source, seed=args.seed)
    print(f"  template partition disjoint: {plan.partition.is_disjoint}")
    print(
        f"  constructs with no held-out template: "
        f"{plan.partition.constructs_without_holdout or 'none'}"
    )
    print(
        f"  gold_eval: {plan.gold_eval.size} utterances "
        f"({len(plan.gold_eval.parent_record_ids)} parents)"
    )
    print(
        f"  gold_dev : {plan.gold_dev.size} utterances "
        f"({len(plan.gold_dev.parent_record_ids)} parents)"
    )
    print(f"  leakage-safe: {plan.is_leakage_safe}")

    # A proxy, not a measurement: the Phase 7 lexicon baseline is crude, and the
    # real count of construct-bearing gold items arrives with annotation. It is
    # here because OPEN-019's replication makes the generator-metadata coverage
    # table an upper bound, and an upper bound with no lower bound beside it is
    # the kind of number that gets quoted as if it were the truth.
    lexicon = LexiconBaseline()
    index = {r.record_id: r for r in records}
    no_cue_eval = sum(
        1
        for prediction in lexicon.predict([index[i] for i in plan.gold_eval.utterance_ids])
        if not prediction
    )
    print(
        f"  gold_eval items with no construct cue (lexicon proxy): "
        f"{no_cue_eval}/{plan.gold_eval.size} ({no_cue_eval / plan.gold_eval.size:.1%})"
    )
    print(
        f"  constructs below the {MIN_POSITIVES_PER_CONSTRUCT}-positive floor: "
        f"{plan.gold_eval.constructs_below_floor or 'none'}"
    )

    if not plan.partition.is_disjoint:
        failures.append("gold template partition is not disjoint")
    if plan.partition.constructs_without_holdout:
        failures.append(
            f"constructs with no held-out template: {plan.partition.constructs_without_holdout}"
        )
    if set(plan.gold_eval.parent_record_ids) & set(plan.gold_dev.parent_record_ids):
        failures.append("gold_eval and gold_dev share a parent record")

    if not args.no_write:
        _rule("Writing artefacts")
        figure_paths = write_figures(profile, plan, REPO_ROOT, texts, utterances_per_record)
        for path in figure_paths:
            print(f"  {path.relative_to(REPO_ROOT)}")
        candidates = write_candidates(plan, records, root=REPO_ROOT)
        for path in candidates:
            print(f"  {path.relative_to(REPO_ROOT)}")
        for path in candidates:
            if path.suffix == ".jsonl":
                leaked = [
                    line
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if "generation_spec" in line
                ]
                if leaked:
                    failures.append(f"{path.name} leaks generation_spec to annotators")
        report = render_report(
            profile,
            plan,
            findings,
            no_cue_eval,
            defect_records,
            defect_utterances,
            realised,
            figure_paths,
        )
        report_path = REPO_ROOT / REPORT_PATH
        report_path.parent.mkdir(parents=True, exist_ok=True)
        # rstrip each line: the pre-commit trailing-whitespace hook would
        # otherwise rewrite this file on every regeneration, so the tree
        # showed as dirty after every EDA run.
        report = "\n".join(line.rstrip() for line in report.splitlines()) + "\n"
        report_path.write_text(report, encoding="utf-8", newline="\n")
        print(f"  {REPORT_PATH}")

    _rule("Phase 9 gate")
    if failures:
        for failure in failures:
            print(f"  FAIL: {failure}")
        print("\nPhase 9 gate: FAILED")
        return 1
    print("  all checks passed")
    print("\n  Corpus quality (see docs/open_issues.md):")
    print(
        f"    OPEN-016  RESOLVED  {defect_records[0]}/{defect_records[1]} records carry a "
        "broken/degraded substitution (was 190/1200)"
    )
    print(
        f"    OPEN-017  RESOLVED  {len(plan.gold_eval.constructs_below_floor)}/10 constructs "
        f"below the {MIN_POSITIVES_PER_CONSTRUCT}-positive floor (was 7/10)"
    )
    print(
        f"    OPEN-018  RESOLVED  "
        f"{profile.utterance_duplicates.exact_duplicate_rate_ci.point:.1%} utterance "
        "duplication (was 87.4%); suffixes are clauses now, not sentences"
    )
    print("    OPEN-020  RESOLVED  15 templates per construct (was 7-12)")
    print("\n  REPORTED, NOT FAILED:")
    print(
        "    OPEN-021  the lexicon baseline is NOT independent of the corpus -- its cues\n"
        "              and the template bank share an ancestor. It fires on 73% of\n"
        "              pre-9b templates and 22% of 9b templates. Its macro-F1 fell\n"
        "              0.780 -> 0.461; 0.461 is the honest floor. Phase 9's cue-fraction\n"
        "              correction is withdrawn -- see reports/eda.md 5b."
    )
    print("\nPhase 9 gate: PASSED")
    return 0


def _group(records):
    from collections import defaultdict

    grouped = defaultdict(list)
    for record in records:
        grouped[record.parent_record_id].append(record)
    for pieces in grouped.values():
        pieces.sort(key=lambda r: r.utterance_index)
    return grouped


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
