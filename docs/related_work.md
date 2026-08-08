# Related Work & Novelty Positioning

> Status: **drafted from the owner's evidence review (Phase 3 substantially complete).**
> Refine wording for the paper in Phase 23. Citation keys map to the reference list at the bottom.

## Summary of the gap (one paragraph)

Validated sport-psychology constructs — competitive anxiety, self-confidence, stress appraisal,
coping, motivation orientation, resilience, and burnout — are well studied through psychometric
surveys, and explainable ML is emerging in sports, but **no line of work bridges validated
constructs to athlete *text* with span-level, construct-specific labels, and almost none validates
its explanations with coaches or sport psychologists.** Text-based studies stop at sentiment or
broad mental-health prediction [Zhao2024, Floyd2021, Biró2024]; psychology studies stay in
cross-sectional self-report [Domínguez-González2024, Li2025, Daumiller2021]; and sports XAI rarely
tests whether explanations are meaningful to practitioners [Kranzinger2025]. This project targets
that intersection: a **construct-grounded athlete-text corpus + two-level interpretability
(span→construct, construct→risk) that is expert-validated.**

## 1. Pre-competition psychological constructs

These are the variables the risk index should center, each with repeated links to athlete functioning:

- **Competitive anxiety ↔ self-confidence.** Negatively related; older / higher-level players show
  stronger psychological resources [Domínguez-González2024].
- **Competitive pressure → anxiety, mediated by resilience, moderated by coping** [Li2025].
- **Coping.** Avoidance coping predicts *increasing* burnout over six months [Madigan2020].
- **Achievement goals.** Mastery-approach goals relate to lower burnout and psychosomatic stress
  [Daumiller2021].
- **Emotion appraisal.** Pre-competition emotions differ not only in intensity but in **performance
  interpretation (facilitative vs. debilitative) and challenge vs. threat appraisal** [Tóth2025].
- **Psychological skills training** context for these constructs [Park2023].

→ Taxonomy impact: adds **resilience**, **appraisal orientation (challenge/threat)**, and an
**interpretation-direction** modifier to the original construct set (see `config/taxonomy.yaml`).

## 2. Limitations of existing work (what we beat)

- **Cross-sectional, self-report designs** — good for associations, weak for causal/dynamic inference;
  authors explicitly recommend longitudinal/experimental tracking and behavioral/coach/physiological
  data [Li2025, Daumiller2021].
- **Small, narrow, or unbalanced samples** by age, level, geography, or sport
  [Domínguez-González2024, Raju2026, Jiacheng2025].
- **Single retrospective datasets without external/prospective validation** [Jiacheng2025, Raju2026].
- **Text stays at sentiment / broad diagnosis**, not athlete-specific validated constructs
  [Floyd2021, Zhao2024, Biró2024].

## 3. NLP on athlete / sports text

LLM and text-analysis methods are being applied to athlete and sports wellbeing text, but at the
sentiment or broad mental-health level rather than construct-specific profiling
[Zhao2024, Floyd2021, Biró2024].

## 4. Explainable ML in sport

Interpretable models (e.g., SHAP-based injury-risk prediction) exist [Jiacheng2025], and a scoping
review finds XAI in sport is present but with **narrow explanation methods that are rarely validated
with coaches or practitioners** [Kranzinger2025]. Multimodal fusion for athlete-state prediction is
emerging and argues current models miss temporal/multimodal structure [Feng2025, Qin2025, Raju2026].

## 5. Our positioning (three-part contribution)

1. **Construct-grounded athlete-text corpus** — span→construct labels mapping text to CSAI-2-style
   anxiety/confidence, stress/pressure, coping, motivation orientation, attentional disruption,
   resilience, appraisal orientation, and ABQ-style burnout. Bridges the survey↔text gap.
2. **Two-level, expert-validated interpretability** — span→construct evidence + construct→risk
   weighting, with a small validation study asking coaches/sport-psychology practitioners whether the
   explanations are sensible. Directly fills the Interpretability-Validation gap.
3. **Time-aware, fusion-ready design** — pre-competition sampling records timing and light context so
   the corpus supports temporal/multimodal extensions; full temporal + multimodal modeling is Future Work.

Ethics is treated as a first-class concern because risk labels can stigmatize athletes and change
coaching behavior [Jiacheng2025]; the system is research/decision-support, not diagnosis.

## References (key → source)

| Key | Note | Link |
|---|---|---|
| Zhao2024 | LLM potential for (sports) text; sentiment/broad level | https://consensus.app/papers/exploring-the-potential-of-large-language-model-in-zhao-wang/eb5ceb30749b51a7a9bf12c8499ae2c7/ |
| Floyd2021 | COVID-19 & emotional wellbeing; text sentiment | https://consensus.app/papers/a-tale-of-two-cities-covid19-and-the-emotional-wellbeing-of-floyd-gulavani/d93e6592a3f253239013fb2d2512e0da/ |
| Domínguez-González2024 | Sport psychological profile; anxiety vs. confidence | https://consensus.app/papers/analysis-of-the-sports-psychological-profile-competitive-dom%C3%ADnguez-gonz%C3%A1lez-reigal/0475719ca0dc5d689706415575b7f587/ |
| Li2025 | Competitive pressure, resilience (mediator), coping (moderator) | https://consensus.app/papers/competitive-pressure-psychological-resilience-and-li-ren/52a00ab55bd65523ad3fae3d0a80d924/ |
| Madigan2020 | Avoidance coping → rising burnout over 6 months | https://consensus.app/papers/coping-tendencies-and-changes-in-athlete-burnout-over-time-madigan-rumbold/002b24d50dad5507a421a27ab07490d3/ |
| Daumiller2021 | Mastery-approach goals → lower burnout/psychosomatic stress | https://consensus.app/papers/elite-athletes%E2%80%99-achievement-goals-burnout-levels-daumiller-rinas/42dce3d71dcd5d4c97f398a5fee021d5/ |
| Tóth2025 | Pre-competition emotion: interpretation & challenge appraisal | https://consensus.app/papers/emotional-profile-of-athletes-before-competition-t%C3%B3th-nuetzel/50662089f54f50018c21e16ed460e8ed/ |
| Park2023 | Psychological skills training for athletes | https://consensus.app/papers/psychological-skills-training-for-athletes-in-sports-web-park-jeon/21022eab135359f68e963b887c740b17/ |
| Kranzinger2025 | Scoping review: XAI in sport rarely practitioner-validated | https://consensus.app/papers/a-scoping-review-of-explainable-artificial-intelligence-kranzinger-halmich/0020ea4bbe0052b99b85328615a25379/ |
| Jiacheng2025 | SHAP-based interpretable ML injury risk; ethics/stigma | https://consensus.app/papers/shapbased-interpretable-machine-learning-for-injury-risk-ma-liu/068b2aae853e5c049d3c61ef32f97384/ |
| Raju2026 | ML framework for athletic prediction; sample/validation limits | https://consensus.app/papers/machine-learning-framework-for-predicting-athletic-raju-singamaneni/43b1961fa29a5bed80774318d2b8c793/ |
| Biró2024 | Real-time AI text analysis | https://consensus.app/papers/realtime-artificial-intelligence-text-analysis-for-bir%C3%B3-janosi-rancz/c9798252702d5576897dc27ef59e8dd8/ |
| Feng2025 | Multimodal fusion for athlete-state prediction | https://consensus.app/papers/multimodal-fusion-for-athlete-state-prediction-feng-sun/baf694c0d1b5567f98eaae1d51b787b8/ |
| Qin2025 | Predictive athlete performance modeling (ML) | https://consensus.app/papers/predictive-athlete-performance-modeling-with-machine-qin-isleem/9541badc0d0d55428697e4afa1025de7/ |

> **Note:** these are secondary citation records (Consensus links). Before submission (Phase 23/24),
> resolve each to its primary DOI / publisher entry and store in `paper/refs.bib`.
