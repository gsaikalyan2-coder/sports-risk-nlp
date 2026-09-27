# Related Work & Novelty Positioning

> Status: **drafted from the owner's evidence review (Phase 3 substantially complete).**
> Refine wording for the paper in Phase 23. Citation keys map to the reference list at the bottom.

## Summary of the gap (one paragraph)

Validated sport-psychology constructs - competitive anxiety, self-confidence, stress appraisal,
coping, motivation orientation, resilience, and burnout - are well studied through psychometric
surveys, and explainable ML is emerging in sports, but **no line of work bridges validated
constructs to athlete *text* with span-level, construct-specific labels, and almost none validates
its explanations with coaches or sport psychologists.** Text-based studies stop at sentiment or
broad mental-health prediction [Zhao2024, Floyd2021, Biro2024]; psychology studies stay in
cross-sectional self-report [Dominguez-Gonzalez2024, Li2025, Daumiller2021]; and sports XAI rarely
tests whether explanations are meaningful to practitioners [Kranzinger2025]. This project targets
that intersection: a **construct-grounded athlete-text corpus + two-level interpretability
(span→construct, construct→risk) whose faithfulness margin is measured, and which a
pilot review found sensible. Practitioner validation remains outstanding (OPEN-004).**

## 1. Pre-competition psychological constructs

These are the variables the risk index should center, each with repeated links to athlete functioning:

- **Competitive anxiety ↔ self-confidence.** Negatively related; older / higher-level players show
  stronger psychological resources [Dominguez-Gonzalez2024].
- **Competitive pressure → anxiety, mediated by resilience, moderated by coping** [Li2025].
- **Coping.** Avoidance coping predicts *increasing* burnout over six months [Madigan2020].
- **Achievement goals.** Mastery-approach goals relate to lower burnout and psychosomatic stress
  [Daumiller2021].
- **Emotion appraisal.** Pre-competition emotions differ not only in intensity but in **performance
  interpretation (facilitative vs. debilitative) and challenge vs. threat appraisal** [Toth2025].
- **Psychological skills training** context for these constructs [Park2023].

→ Taxonomy impact: adds **resilience**, **appraisal orientation (challenge/threat)**, and an
**interpretation-direction** modifier to the original construct set (see `config/taxonomy.yaml`).

## 2. Limitations of existing work (what we beat)

- **Cross-sectional, self-report designs** - good for associations, weak for causal/dynamic inference;
  authors explicitly recommend longitudinal/experimental tracking and behavioral/coach/physiological
  data [Li2025, Daumiller2021].
- **Small, narrow, or unbalanced samples** by age, level, geography, or sport
  [Dominguez-Gonzalez2024, Raju2026, Jiacheng2025].
- **Single retrospective datasets without external/prospective validation** [Jiacheng2025, Raju2026].
- **Text stays at sentiment / broad diagnosis**, not athlete-specific validated constructs
  [Floyd2021, Zhao2024, Biro2024].

## 3. NLP on athlete / sports text

LLM and text-analysis methods are being applied to athlete and sports wellbeing text, but at the
sentiment or broad mental-health level rather than construct-specific profiling
[Zhao2024, Floyd2021, Biro2024].

## 4. Explainable ML in sport

Interpretable models (e.g., SHAP-based injury-risk prediction) exist [Jiacheng2025], and a scoping
review finds XAI in sport is present but with **narrow explanation methods that are rarely validated
with coaches or practitioners** [Kranzinger2025]. Multimodal fusion for athlete-state prediction is
emerging and argues current models miss temporal/multimodal structure [Feng2025, Qin2025, Raju2026].

## 5. Our positioning (three-part contribution)

1. **Construct-grounded athlete-text corpus** - span→construct labels mapping text to CSAI-2-style
   anxiety/confidence, stress/pressure, coping, motivation orientation, attentional disruption,
   resilience, appraisal orientation, and ABQ-style burnout. Bridges the survey↔text gap.
2. **Two-level interpretability with a measured faithfulness margin** - span→construct evidence + construct→risk
   weighting, with a small validation study asking coaches/sport-psychology practitioners whether the
   explanations are sensible. Directly fills the Interpretability-Validation gap.
3. **Time-aware, fusion-ready design** - pre-competition sampling records timing and light context so
   the corpus supports temporal/multimodal extensions; full temporal + multimodal modeling is Future Work.

Ethics is treated as a first-class concern because risk labels can stigmatize athletes and change
coaching behavior [Jiacheng2025]; the system is research/decision-support, not diagnosis.

## References (key → primary source)

> **Status (resolved 2026-08-08, Phase 3):** all 14 sources below were resolved from their
> original Consensus records to primary publisher records via Crossref / publisher pages.
> Full BibTeX lives in `paper/refs.bib`; the keys here are identical to the keys there.
> Three keys were ASCII-ised (`Dominguez-Gonzalez2024`, `Biro2024`, `Toth2025`) because
> BibTeX citation keys must be ASCII.

| Key | Note | Primary source | DOI |
|---|---|---|---|
| Zhao2024 | LLM for athlete mental-health diagnosis; framed as sentiment analysis | Adv. Educ. Humanit. Soc. Sci. Res. 12(1):342 (2024) | [10.56028/aehssr.12.1.342.2024](https://doi.org/10.56028/aehssr.12.1.342.2024) |
| Floyd2021 | COVID-19 & student-athlete emotional well-being via NLP | Front. Sports Act. Living 3:710289 (2021) | [10.3389/fspor.2021.710289](https://doi.org/10.3389/fspor.2021.710289) |
| Dominguez-Gonzalez2024 | Sport psychological profile; anxiety vs. confidence; flow | Sports 12(1):20 (2024) | [10.3390/sports12010020](https://doi.org/10.3390/sports12010020) |
| Li2025 | Competitive pressure; resilience (mediator), coping (moderator) | Sci. Rep. 15:35467 (2025) | [10.1038/s41598-025-19213-1](https://doi.org/10.1038/s41598-025-19213-1) |
| Madigan2020 | Avoidance coping → rising burnout over 6 months | Psychol. Sport Exerc. 48:101666 (2020) | [10.1016/j.psychsport.2020.101666](https://doi.org/10.1016/j.psychsport.2020.101666) |
| Daumiller2021 | Mastery-approach goals → lower burnout / psychosomatic stress | Int. J. Sport Exerc. Psychol. 20(2):416–435 (2021) | [10.1080/1612197X.2021.1877326](https://doi.org/10.1080/1612197X.2021.1877326) |
| Toth2025 | Pre-competition emotion: interpretation & challenge/threat appraisal ⚠ | Front. Sports Act. Living 7:1636826 (2025) | [10.3389/fspor.2025.1636826](https://doi.org/10.3389/fspor.2025.1636826) |
| Park2023 | Psychological skills training - bibliometric analysis | Healthcare 11(2):259 (2023) | [10.3390/healthcare11020259](https://doi.org/10.3390/healthcare11020259) |
| Kranzinger2025 | Scoping review: XAI in sport rarely practitioner-validated | Discov. Artif. Intell. 6(1):5 (2025, online) | [10.1007/s44163-025-00709-8](https://doi.org/10.1007/s44163-025-00709-8) |
| Jiacheng2025 | SHAP-based interpretable ML injury risk; ethics/stigma | Sci. Rep. 15:40252 (2025) | [10.1038/s41598-025-24144-y](https://doi.org/10.1038/s41598-025-24144-y) |
| Raju2026 | ML framework for athletic injury prediction; sample/validation limits | BMC Sports Sci. Med. Rehabil. 18:107 (2026) | [10.1186/s13102-025-01502-x](https://doi.org/10.1186/s13102-025-01502-x) |
| Biro2024 | Real-time AI text analysis for athlete burnout | IEEE SAMI 2024, 253–258 | [10.1109/SAMI60510.2024.10432817](https://doi.org/10.1109/SAMI60510.2024.10432817) |
| Feng2025 | Multimodal fusion (XLNet + generative) for athlete state | Alexandria Eng. J. 129:925–936 (2025) | [10.1016/j.aej.2025.07.021](https://doi.org/10.1016/j.aej.2025.07.021) |
| Qin2025 | Predictive athlete performance modelling with biometrics | Sci. Rep. 15:16365 (2025) | [10.1038/s41598-025-01438-9](https://doi.org/10.1038/s41598-025-01438-9) |

> ⚠ **Correction found while resolving `Toth2025`.** The Consensus record credited
> "Tóth / Nuetzel"; those are in fact the *handling editor* and a *reviewer*. The actual
> authors are **Nogueira, Morais, Mansell & Gomes**. The key is kept for continuity but
> the paper must cite the real authors. `paper/refs.bib` has the corrected entry.

## Method references (added 2026-08-08)

Anchors for the modelling and evaluation sections, which the Phase 3 sweep did not cover.

| Key | Note | Primary source | DOI / canonical record |
|---|---|---|---|
| Devlin2019 | BERT - transformer fine-tuning for text classification | NAACL-HLT 2019, 4171–4186 | [10.18653/v1/N19-1423](https://doi.org/10.18653/v1/N19-1423) |
| He2021 | DeBERTa - candidate backbone (CLAUDE.md §6) | ICLR 2021 | [arXiv:2006.03654](https://arxiv.org/abs/2006.03654) - no publisher DOI |
| Guo2017 | Calibration of neural nets; temperature scaling for the risk index | ICML 2017, PMLR 70:1321–1330 | [PMLR v70/guo17a](https://proceedings.mlr.press/v70/guo17a.html) - no publisher DOI |
| Lundberg2017 | SHAP - span/feature attribution for the explainability layer | NeurIPS 30 (2017) | [NeurIPS 2017 proceedings](https://papers.nips.cc/paper_files/paper/2017/hash/8a20a8621978632d76c43dfd28b67767-Abstract.html) - no publisher DOI |
| Cohen1960 | Cohen's kappa - inter-annotator agreement for the gold set | Educ. Psychol. Meas. 20(1):37–46 | [10.1177/001316446002000104](https://doi.org/10.1177/001316446002000104) |

> ICLR / ICML / NeurIPS papers carry no publisher DOI. Their arXiv / PMLR / NeurIPS
> proceedings entries **are** the primary records, so these are resolved, not unresolved.

**Unresolved:** none. All 14 original references and all 5 method references resolved.

## Still thin (for Phase 23)

- Multi-label text classification methodology beyond a backbone citation.
- A weak-supervision / LLM-labelling anchor (e.g. Snorkel-style programmatic labelling).
- A sports-psych instrument citation trail for CSAI-2 and the ABQ - needed in Phase 4 so
  every construct in `config/taxonomy.yaml` has a real instrument anchor.
