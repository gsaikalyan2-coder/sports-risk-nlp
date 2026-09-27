# .claude.md - Pre-Competition Psychological Risk Profiling of Athletes

> Single source of truth for this project. Claude (and any AI agent) must read
> this file before doing work. Everything below is a **proposal for a sophomore-level,
> IEEE-publishable rewrite** - items marked **[NEEDS PERMISSION]** must be confirmed by
> Saikalyan before they are locked in.

---

## 0. Project Identity

| Field | Value |
|---|---|
| **Title** | Pre-Competition Psychological Risk Profiling of Athletes |
| **Domain** | NLP × Sports Psychology (interpretable, construct-grounded ML) |
| **Owner** | Saikalyan, Sophomore, SRMIST |
| **Target venue** | IEEE conference (iTriply Explore) - full paper |
| **Timeline** | 8 weeks. Code frozen ~Week 7; paper draft by 1st week of September 2026 |
| **IDE** | VS Code (primary) |
| **Repo strategy** | Full rewrite from scratch. Old files deleted after a one-time backup branch |
| **Primary language** | Python 3.11 |

---

## 1. What Makes This Novel (not "just sentiment analysis")

Basic sentiment analysis outputs positive/negative/neutral. **This project does not do that.**
Instead it performs **construct-grounded, multi-dimensional psychological risk profiling**:
we detect *validated sports-psychology constructs* in athlete text and combine them into an
interpretable **pre-competition risk index**.

**The core idea in one sentence:** Given text an athlete produces before a competition
(interviews, press conferences, social posts, journals), predict a set of psychology constructs
grounded in validated instruments, then fuse them into an explainable risk score that flags
elevated pre-competition psychological risk.

**The constructs** are drawn from established sports-psychology instruments so the labels are
defensible in a paper (this is the academic-rigor anchor):

- **Cognitive anxiety** and **somatic anxiety** and **self-confidence** - from the CSAI-2 tradition,
  with an optional **interpretation direction** (facilitative vs. debilitative).
- **Motivation orientation** (approach vs. avoidance) - self-determination / achievement-goal theory.
- **Perceived stress / pressure**.
- **Attentional focus vs. distraction**.
- **Burnout / emotional exhaustion signals** - Athlete Burnout Questionnaire (ABQ) tradition.
- **Coping style** (task-focused vs. avoidance).
- **Resilience** - capacity to recover under pressure (mediator; Li2025).
- **Appraisal orientation** - challenge vs. threat framing of the competition (Tóth2025).

  *(Added 2026-08 from the evidence review - see `docs/related_work.md`. Final set frozen at Phase 12.)*

**Evidence-backed novelty (validated by the Phase 3 review - see `docs/related_work.md`).**
The literature confirms two open gaps this project targets: (a) no work bridges *validated
constructs* to athlete *text* with span-level, construct-specific labels - text studies stop at
sentiment / broad mental-health; (b) sports XAI explanations are almost never validated with
coaches or practitioners.

**The three-part contribution:**
1. **Construct-grounded athlete-text corpus** - span→construct labels bridging the survey↔text gap
   (with inter-annotator agreement reported). This is the core dataset contribution.
2. **Two-level interpretability with a measured faithfulness margin** - span→construct evidence + construct→risk
   weighting, with a small validation study asking coaches/sport-psych practitioners whether the
   explanations are sensible. *This directly fills the biggest gap and is the headline differentiator.*
3. **Time-aware, fusion-ready design** - pre-competition sampling records timing + light context so
   the corpus supports temporal/multimodal extensions; full temporal + multimodal modeling is Future Work.

Supporting these: an **agentic, cost-aware pipeline** (reproducible multi-agent system) as a methods
contribution, and **first-class ethics** (risk labels can stigmatize; research/decision-support only).

**Explicit non-goals / ethics guardrails (must appear in the paper):**
- This is **decision-support and research**, **not** clinical diagnosis of any real person.
- No claims about a named athlete's mental health. Use public/consented/synthetic/anonymized text.
- Report limitations, bias, and misuse risks. Frame as a screening/awareness tool for coaches/researchers.

---

## 2. System Architecture (NLP–Psychology Pipeline)

```
                    ┌─────────────────────────────────────────────────────┐
                    │            CONSTRUCT TAXONOMY (Sec. 3)               │
                    │  CSAI-2 / SDT / ABQ-grounded label schema + rubric   │
                    └─────────────────────────────────────────────────────┘
                                          │ governs
                                          ▼
 [1] Ingestion ──▶ [2] Preprocessing ──▶ [3] Weak/LLM Labeling ──▶ [4] Gold Verification
   raw text          clean, normalize        cheap LLM proposes         humans confirm a
   (interviews,      de-identify, segment     construct labels           stratified subset;
   pressers,         into utterances          (cost-aware routing)       measure IAA (kappa)
   social, journals)                                                          │
                                                                              ▼
 [7] Explainability ◀── [6] Risk Scoring ◀── [5] Construct Classifier ◀── labeled dataset
   span attribution        fuse construct        multi-label transformer
   attention / SHAP        probs → risk index    (fine-tuned) + baselines
        │                       │
        ▼                       ▼
 [8] Evaluation & Ablations ──▶ [9] Dashboard / Visualization ──▶ [10] IEEE Paper
   per-construct F1, calibration,   coach-facing profile view        reproducible artifact
   human-agreement, error analysis
```

**Layer responsibilities**

1. **Ingestion** - pull/import text into `data/raw/`. Records provenance + license per source.
2. **Preprocessing** - cleaning, sentence/utterance segmentation, de-identification (strip PII),
   language filtering. Output `data/interim/`.
3. **Weak/LLM Labeling** - a cheap LLM proposes construct labels + rationale per utterance
   (silver labels). Cost-aware routing (Sec. 5). Output `data/processed/silver/`.
4. **Gold Verification** - humans (Saikalyan + ≥1 peer) verify a stratified sample; compute
   inter-annotator agreement (Cohen's/Fleiss' kappa). Output `data/gold/`.
5. **Construct Classifier** - multi-label transformer fine-tuned on gold+silver, benchmarked
   against classical baselines (TF-IDF+LogReg/SVM) and a lexicon baseline.
6. **Risk Scoring** - deterministic + learned fusion of construct probabilities into a single
   0–1 risk index with per-construct contributions. Calibrated (Platt/temperature scaling).
7. **Explainability** - SHAP and/or attention rollout to attribute risk to text spans/constructs.
8. **Evaluation** - per-construct P/R/F1, macro/micro F1, calibration (ECE), human agreement,
   ablations (baseline vs transformer, with/without silver data, with/without risk fusion).
9. **Dashboard** - a simple Streamlit/HTML view: paste text → construct bars + risk gauge + highlighted spans.
10. **Paper** - LaTeX IEEE two-column, reproducible artifact (Docker + seeds + model card).

---

## 3. Construct Taxonomy (the academic backbone)

Maintained as `config/taxonomy.yaml` and documented in `docs/annotation_guidelines.md`.
Each construct has: definition, sports-psych citation anchor, positive/negative examples,
edge cases, and label type (present/absent + intensity 0–3). This rubric is what makes the
labels reproducible and reviewer-defensible. **Do not invent constructs outside this file.**

---

## 4. Specialized AI Agents (AI-First Engineering)

Work is decomposed across specialized agents so several can run **in parallel**. Each agent has
a narrow contract: inputs, outputs, and a "definition of done." Orchestration follows a Kanban
work-item model (see `PROJECT_PLAN.md`), with **merge gates** - nothing lands without passing
its acceptance check.

| Agent | Responsibility | Reads | Writes | Model tier |
|---|---|---|---|---|
| **Literature Agent** | Related-work sweep, novelty positioning, citation harvesting | web/arXiv | `docs/related_work.md`, `paper/refs.bib` | premium (reasoning) |
| **Taxonomy/Psych Agent** | Ground constructs in instruments, write annotation rubric | papers, `taxonomy.yaml` | `docs/annotation_guidelines.md` | premium |
| **Harvester Agent** | Ingest text, record provenance/license, de-identify | sources | `data/raw/`, `data/interim/` | cheap |
| **Labeling Agent** | Propose construct labels + rationale (silver) | `data/interim/` | `data/processed/silver/` | cheap→mid (routed) |
| **Annotation-QA Agent** | Flag low-confidence/conflicting labels for human review | silver | review queue | cheap |
| **Modeling Agent** | Train/tune baselines + transformer, log runs | gold+silver | `models/`, run logs | local GPU / mid |
| **Evaluation Agent** | Metrics, calibration, ablations, error analysis | `models/`, gold | `reports/`, figures | cheap |
| **Explainability Agent** | SHAP/attention attribution, example cards | `models/` | `reports/explain/` | mid |
| **Security/Ethics Agent** | Secret/dep scan, PII audit, ethics & limitations draft | repo, data | `docs/security.md`, `docs/ethics.md` | mid |
| **Paper Agent** | Assemble IEEE draft from artifacts | everything | `paper/` | premium |

**Rules for all agents**
- Every agent writes a short run log to `logs/` (what it did, cost, artifacts produced).
- Agents never overwrite `data/gold/` - that is human-owned.
- Any agent touching real athlete data must run the de-identification step first.
- Prefer the smallest model that passes the acceptance check (Sec. 5).

---

## 5. Cost-Aware LLM Strategy **[NEEDS PERMISSION]**

Bulk work (labeling thousands of utterances, preprocessing) must not use premium models.
Route by task difficulty:

- **Cheap tier** (bulk labeling, cleaning, dedup): a small/cheap model.
- **Mid tier** (ambiguous labels, explanations): a mid model.
- **Premium tier** (novelty analysis, paper writing, hard adjudication): a strong reasoning model.

**Controls:** prompt caching for repeated system/rubric prompts; batch requests; a hard
monthly budget with a running cost log (`logs/cost_ledger.csv`); automatic downgrade when a
cheap model's confidence is high, escalation only on low confidence.

**Provider options to confirm (Q2):** OpenRouter (one key, many models, easy routing) vs.
direct provider APIs vs. local/free models (Hugging Face + Ollama) to spend ₹0 on inference.

---

## 6. Tool Recommendations **[ALL NEED PERMISSION]**

| Concern | Recommended default | Alternatives | Ask |
|---|---|---|---|
| Language / env | Python 3.11 + `venv` + `pip` | conda, uv | default ok? |
| Multi-agent orchestration | **CrewAI** (gentler for a sophomore) | AutoGen, LangGraph | **Q1** |
| Containerization | Docker + docker-compose | Podman | default ok? |
| LLM access / cost | **OpenRouter** + caching | direct APIs, local HF/Ollama | **Q2** |
| Transformer training | Hugging Face `transformers` + `datasets` | Flair, spaCy | default ok? |
| Base model | DeBERTa-v3-base / RoBERTa-base | domain BERT, DistilBERT (lighter) | default ok? |
| Classical baselines | scikit-learn (TF-IDF + LogReg/SVM) | - | default ok? |
| Explainability | SHAP + attention rollout | LIME, Captum | default ok? |
| Experiment tracking | Weights & Biases (free tier) | MLflow, CSV logs | default ok? |
| Dashboard | Streamlit | Gradio, Flask | default ok? |
| Data acquisition | **[NEEDS PERMISSION]** | scrape / public datasets / synthetic | **Q3** |
| AutoML benchmark (optional) | DataRobot | scikit-learn only | optional |
| Paper | LaTeX (IEEE template) + Overleaf | Word | default ok? |
| Vector store (only if RAG added) | Chroma / FAISS | - | later |

---

## 7. File Structure (rewrite target)

```
sports-risk-nlp/
├── .claude.md                  # this file
├── README.md
├── PROJECT_PLAN.md             # 25-phase blueprint
├── pyproject.toml / requirements.txt
├── .env.example                # keys as placeholders; real .env is gitignored
├── .gitignore
├── Dockerfile
├── docker-compose.yml          # agent services + dashboard
├── config/
│   ├── taxonomy.yaml           # construct schema (Sec. 3)
│   ├── brain_atlas.yaml        # [Phase 26] construct → network map, one citation per row
│   ├── model_routing.yaml      # cost-aware tiers (Sec. 5)
│   └── settings.yaml
├── data/
│   ├── raw/                    # untouched, with provenance.json per source
│   ├── interim/                # cleaned, de-identified
│   ├── processed/silver/       # LLM/weak labels
│   ├── gold/                   # human-verified (human-owned, never auto-written)
│   └── external/
├── src/
│   ├── ingestion/
│   ├── preprocessing/          # includes deidentify.py
│   ├── taxonomy/
│   ├── labeling/               # cost-aware LLM labeling
│   ├── models/                 # baselines + transformer
│   ├── risk/                   # construct → risk fusion + calibration
│   ├── biosignals/             # [Phase 26] simulated EEG/cardio sources + pure features
│   ├── explainability/
│   ├── evaluation/
│   └── agents/                 # CrewAI/AutoGen agent + crew definitions
├── notebooks/                  # EDA, error analysis (exploration only)
├── dashboard/                  # Streamlit app (multipage: app.py + pages/)
├── reports/                    # metrics, figures, explanations
├── paper/                      # IEEE LaTeX, refs.bib, figures
├── tests/                      # pytest
├── scripts/                    # one-off runners
├── logs/                       # agent run logs + cost_ledger.csv
└── docs/                       # annotation_guidelines, related_work, ethics, security
```

---

## 8. How Claude Should Respond On This Project (tailoring rules)

1. **Teach while doing.** Saikalyan is a sophomore. Explain *why* before *how*; define jargon
   the first time it appears; prefer one clear path over many options.
2. **Ask before locking tools.** Any framework/library/model/data decision that isn't already
   confirmed in this file must be confirmed via a question before it's treated as final.
3. **Small, verifiable steps.** Produce runnable increments with a way to check they worked
   (a test, a printout, a screenshot). End non-trivial work with a verification step.
4. **Academic rigor is the priority.** Every modeling choice should be defensible in a paper.
   When in doubt, prefer the option that is easier to justify to a reviewer.
5. **Ethics is not optional.** Never infer mental-health status of a real named person; always
   route real data through de-identification; keep the limitations/ethics framing current.
6. **Cost discipline.** Default to the cheapest model that passes the acceptance check; log cost.
7. **Reproducibility.** Fixed seeds, pinned versions, Dockerized runs, a model card per model.
8. **Be concise and direct in chat** (Saikalyan's stated preference); put depth in files/docs.
9. **Never commit secrets.** Keys live only in `.env` (gitignored); `.env.example` holds placeholders.
10. **Update this file** when a decision is confirmed, so it stays the single source of truth.

---

## 9. Definition of "Publication-Ready"

- A documented dataset with reported inter-annotator agreement.
- Transformer beats classical + lexicon baselines on macro-F1, with ablations.
- Calibrated, interpretable risk index with worked examples.
- Reproducible artifact (Docker + seeds + model card + released code).
- Complete IEEE draft: abstract, intro, related work, method, dataset, experiments, results,
  ablation, ethics & limitations, conclusion, references.

---

## 10. Confirmed Decisions (locked 2026-07-23)

- **Q1 - Multi-agent framework: CrewAI.** ✅ Confirmed. Role-based, sophomore-friendly.
- **Q2 - LLM access: OpenRouter** with cost-tier routing + caching + budget ledger. ✅ Confirmed.
- **Q3 - Data: existing public/licensed datasets first.** ✅ Confirmed 2026-07-23. Fallback if
  coverage is thin: hybrid synthetic-for-training + small real gold set (revisit at Phase 7).
  → **REVISITED AND RESOLVED at Phase 7, 2026-08-09. The fallback was taken.** The survey
  found **no public corpus of pre-competition athlete text** - every athlete-speech corpus
  located is post-match, which is the wrong side of the event for an anticipatory taxonomy
  (`appraisal_orientation`, anticipatory `cognitive_anxiety`). Four candidates were surveyed
  and all four rejected: Cornell tennis transcripts (no licence stated), iMiGUE-Speech
  (gated behind an unsigned agreement), ASAP Sports direct (terms unverifiable), YouTube
  captions (API requires channel-owner OAuth). Full table in `docs/data_sources.md` §4.
  **Owner decision: synthetic-first (A2), pre-competition framing retained, full taxonomy
  retained.** Real-text acquisition routes declined for now - tracked as **OPEN-011**, which
  is the project's live highest risk because contribution #1 needs real athlete text.
- **Optional** DataRobot AutoML benchmark - only if a DataRobot account is available (Phase 16).
  → **Reconfirmed at Phase 7, 2026-08-09.** No DataRobot account, SDK, endpoint, or token
  exists. Ingestion stays local and offline. Uploading athlete text to a third-party cloud
  is a `docs/ethics.md` governance decision, not a tooling one, and it would break the
  "a reviewer reproduces the artifact with no account" property established in Phase 6.
- **Expansions selected (stretch, park until core is done):** Temporal risk trajectory,
  Multimodal audio/prosody, Team-level aggregation, Outcome-linkage validation.
  → **Scope guidance:** core pipeline (Phases 1–25) ships first. Of the four, **Outcome-linkage
  validation** is the highest-value add if outcome data exists; the other three are documented as
  **"Future Work"** in the paper unless time in Week 8 allows. Do not start any expansion before Phase 19.

Still using defaults from §6 (Python 3.11, Docker, HF transformers, DeBERTa/RoBERTa, scikit-learn,
SHAP, W&B, Streamlit, LaTeX). Flag if you want to change any.
```

---

## 11. Cognitive Layer - V1 / V3 / V5 (planned, not built)

> **Status: plan only.** Nothing in this section exists in the repository yet. It is written so a
> fresh session can build it without re-deciding anything. Owner decisions of 2026-09-13 are
> recorded in §11.1 and are binding on the sections below.

### 11.1 Owner decisions (locked 2026-09-13)

| Question | Decision |
|---|---|
| What V1 / V3 / V5 are | **V1** = construct→brain network atlas · **V3** = cognitive load from HRV + webcam oculometrics · **V5** = closed-loop neurofeedback session |
| Data source | **Simulated only, behind a hardware-ready seam.** No headset, no strap, no participant. |
| V5 scope | **Demo mode only, no human subject.** The loop closes against a simulated signal. |
| Documents updated | This file, `PROJECT_PLAN.md` (new Phase 26), `handover_phase_26_cognitive_layer.txt` |
| Documents deliberately *not* updated | `docs/ethics.md`, `docs/model_card.md` - see the gate in §11.2 |

### 11.2 The constraint that governs this whole section

`data/gold/` is empty and no number in this repository is an accuracy. The cognitive layer makes
that problem **worse**, not better, because a brain graphic is the most over-read object in sports
technology and a simulated one is indistinguishable from a measured one at a glance.

Three rules, enforced by construction rather than by convention:

1. **A simulated source cannot be constructed without stamping itself.** `SimulatedSource` raises on
   an empty provenance string, exactly as `ScoreSurface` raises without `PROVISIONAL_STAMP` and
   `Band` raises without its caveat. A panel renders the stamp or it does not render.
2. **The risk index does not move.** All three features write into `LinearRiskScorer`'s existing
   `context` mapping with `context_weights={}`. The text-only path is already a separate, tested code
   path (`src/risk/fusion.py` §"score"), and the existing test that the index is numerically identical
   with and without context becomes the regression guard for the entire layer.
3. **The atlas is a hypothesis, not an image.** Every node carries "hypothesised association, not
   imaging" in text, not in a tooltip. No node is ever labelled with an activation value.

**Ethics gate (blocking).** `docs/ethics.md` and `docs/model_card.md` were deliberately left
untouched because nothing here touches a human. **The moment any real physiological signal from any
person enters this code - including the owner's own - both documents must be updated first**, with a
consent route, a retention rule, and a statement that physiological data is a different privacy class
from synthetic text. V5 additionally requires ethics approval and a clinician in the loop before it
runs against a person, because a closed feedback loop is an intervention rather than an observation.
A `# BLOCKED UNTIL ETHICS SIGN-OFF` guard in `src/biosignals/sources.py` refuses any non-simulated
source until that happens.

### 11.3 Shared architecture (built once, used by all three)

The layer copies the architecture the dashboard already proved, rather than inventing one.

- **`src/biosignals/` - a new pure-Python package.** No ML stack, no Streamlit import, fully unit
  tested. Same shape as `src/dashboard/`: a `Protocol` with swappable backends, frozen dataclasses,
  guards in `__post_init__`.
- **`BiosignalSource` Protocol** mirroring `PredictionBackend`. `SimulatedEEGSource` and
  `SimulatedCardioOculoSource` ship now; `MuseSource` / `OpenBCISource` / `PolarH10Source` drop in
  later behind the same interface with no page change.
- **Feature flag.** `SRN_COGNITIVE_LAYER`. **Planned as off-by-default; shipped
  on-by-default, and the code is right.** `theme.cognitive_layer_enabled()` treats unset as ON and
  only an explicit off value turns the layer off, because a default of off meant three deployments
  in a row rendered a dashboard with three pages silently missing - the app correct and looking
  broken. The reversal is argued in that function's docstring, which is the binding statement; this
  bullet is the plan it supersedes, kept so the change reads as deliberate rather than as drift.
  Nothing about the layer's honesty rests on the default: the stamps, the ethics gate in
  `src/biosignals/sources.py` and the activation screen never consult it.
- **Widget placement.** Navigation order becomes **Dashboard → Score my own text → Brain atlas →
  Cognitive load → Neurofeedback (demo)**. Each feature is a page *and* exposes a compact summary
  tile built through the existing `src/dashboard/widgets.py::Widget` contract, so the same three
  features can appear as tiles appended after the existing grid on the dashboard.

**Files created once, shared by all three features**

| File | Change |
|---|---|
| `src/biosignals/__init__.py` | new - public surface, mirrors `src/dashboard/__init__.py` |
| `src/biosignals/sources.py` | new - `BiosignalSource` Protocol, `BiosignalWindow` frozen dataclass, `SimulatedEEGSource`, `SimulatedCardioOculoSource`, mandatory `SIMULATED_STAMP`, ethics guard |
| `src/biosignals/features.py` | new - pure functions: band power, RR→HF-HRV, pupil z-score, blink rate, load index. No I/O |
| `src/dashboard/neurovis.py` | new - SVG/HTML renderers for all three panels, theme-token driven, light+dark |
| `src/dashboard/copy.py` | modified - plain-English copy for the three features, screened at import by the existing `_screen()` walk |
| `src/dashboard/theme.py` | modified - three extra panel surface entries in `motion._SURFACES` style; no new colour outside the documented palettes |
| `src/dashboard/__init__.py` | modified - export the new renderers |
| `tests/test_biosignals.py` | new - source, feature and stamp tests |
| `tests/test_neurovis.py` | new - render-surface and honesty tests for all three panels |
| `tests/test_dashboard_pages.py` | modified - the existing shell rules must walk the three new pages too |
| `.env.example` | modified - document `SRN_COGNITIVE_LAYER` |

---

## 11.4 V1 - Construct → Brain Network Atlas

### Feature overview
Maps each of the ten detected constructs onto the brain network the sports-psychology and cognitive
neuroscience literature associates with it, and lights that network in proportion to the construct's
detection strength and its signed push on the risk index. It converts the existing text decomposition
into an anatomical vocabulary a coach or a reviewer reads instantly - **without measuring anything
new**. It is the project's highest-impact demo asset and its highest misreading risk.

### Widget specification
- **Page:** `dashboard/pages/3_Brain_atlas.py` - third in nav, after Dashboard and Score.
- **Component:** `neurovis.atlas_panel(view, *, mode)` → one self-contained HTML document mounted
  with `st.components.v1.html`, same pattern as `motion_panel`.
- **State:** reads `st.session_state["mode"]` (appearance) and `["example_id"]` / `["policy_label"]`
  so the atlas shows the same record the dashboard is showing. Writes nothing.
- **Props:** a `DashboardView` and a mode string. No new numbers are computed in the page.
- **UI behaviour:** node radius and glow ∝ `ConstructBar.probability`; node hue = sign of
  `contribution` (coral raises, deep green lowers, hairline for inert); edge weight ∝ min of the two
  endpoint probabilities; inert constructs keep the dashed ring and the literal word "inert". Hovering
  a node reveals the construct, its two numbers, and the citation anchor. A persistent caption under
  the figure reads *"hypothesised association, not imaging"*.
- **Summary tile:** "Networks engaged - N of 10", appended after the existing dashboard grid.

### Files affected
| File | Change |
|---|---|
| `config/brain_atlas.yaml` | **new** - construct → network(s) map, one citation per row, mirroring the `instrument_anchor` convention already used in `config/taxonomy.yaml` |
| `src/dashboard/neurovis.py` | **new** (shared) - `atlas_panel()`, `atlas_height()` |
| `src/dashboard/atlas_map.py` | **new** - loads and validates `brain_atlas.yaml`; refuses a construct with no citation |
| `dashboard/pages/3_Brain_atlas.py` | **new** - the page shell, renderer only |
| `src/dashboard/copy.py` | **modified** - `ATLAS_PLAIN`, `ATLAS_CAVEAT`, per-network plain names |
| `tests/test_neurovis.py` | **new** - atlas honesty tests |
| `reports/cognitive_concepts.html` | **existing** - the approved visual reference for this panel |

### Implementation steps
1. Write `config/brain_atlas.yaml`: for each of the ten constructs, one or two networks with a short
   rationale and a citation key that resolves in `paper/refs.bib`. **Do not invent a mapping for a
   construct with no defensible source** - leave it unmapped and let the loader mark it "unmapped".
2. Build `atlas_map.py` to load, validate and freeze that file. Validation refuses: a construct absent
   from the taxonomy, a mapping with an empty citation, and any numeric field (there are none - this
   file carries no values).
3. Add `atlas_panel()` to `neurovis.py`: reads only `view.bars`, emits SVG, takes all colour from
   `theme.palette(mode)`.
4. Add the copy strings, which the existing import-time screen will check for forbidden vocabulary.
5. Build the page shell - imports only from `src.dashboard`, constructs no view, renders the stamp
   before any expander.
6. Add the summary tile via `widgets.Widget` so the dashboard grid can carry it.
7. Write the tests in §Testing below before wiring the flag on.

### Dependencies & integration points
- **Consumes:** `DashboardView.bars`, `plain.CONSTRUCTS`, `theme.palette`, `widgets.Widget`.
- **Depends on nothing new at runtime** - no biosignal source, no hardware. V1 can ship alone.
- **Cross-feature:** none. V3 and V5 do not read the atlas; the atlas does not read them.

### Testing & validation
- Every construct in the live taxonomy has a row in `brain_atlas.yaml`, or is explicitly `unmapped`.
- Every mapped row carries a citation key that exists in `paper/refs.bib`.
- The rendered panel contains the string "hypothesised association, not imaging".
- The panel contains no activation-shaped vocabulary: assert absence of "activity", "activation",
  "fMRI", "measured" in the rendered surface.
- Inert constructs render the dashed ring, the muted hue **and** the word "inert" - three channels, as
  `charts.py` already requires.
- Node intensities equal `ConstructBar.probability` to 3 dp - the panel introduces no number the view
  does not carry.
- Renders identically with the webfont blocked (SVG carries no font file).

---

## 11.5 V3 - Cognitive Load (HRV + webcam oculometrics)

### Feature overview
A live load index from two cheap, non-invasive channels: heart-rate variability as a parasympathetic
index and webcam-derived pupil and blink behaviour as an effort/attention proxy. Today it runs on a
simulated source; the same panel accepts a Polar H10 and a webcam later without changing. It is the
fastest route to a *real* athlete because nobody objects to a chest strap.

### Widget specification
- **Page:** `dashboard/pages/4_Cognitive_load.py` - fourth in nav.
- **Component:** `neurovis.load_panel(window, *, mode)` where `window` is a frozen
  `BiosignalWindow`.
- **State:** `st.session_state["mode"]`; a session-scoped rolling buffer of the last N windows held in
  a `deque` inside the source object, never in Streamlit state.
- **Props:** a `BiosignalWindow` and a mode string.
- **UI behaviour:** RR-interval tachogram and pupil trace on a shared time axis with blink ticks; one
  load meter on the **same uncalibrated-ranking footing as the risk index** - no bands, no
  thresholds, the caption states "ranking only, not calibrated". Three supporting rows: HF-HRV,
  pupil effort, blink rate. A visible "SIMULATED" chip.
- **Summary tile:** "Load index" with its stamp, appended after the grid.

### Files affected
| File | Change |
|---|---|
| `src/biosignals/sources.py` | **new** (shared) - `SimulatedCardioOculoSource` |
| `src/biosignals/features.py` | **new** (shared) - `hf_hrv()`, `pupil_effort()`, `blink_rate()`, `load_index()` |
| `src/dashboard/neurovis.py` | **modified** - `load_panel()`, `load_height()` |
| `dashboard/pages/4_Cognitive_load.py` | **new** - page shell |
| `src/dashboard/copy.py` | **modified** - `LOAD_PLAIN`, `LOAD_NOT_CALIBRATED` |
| `tests/test_biosignals.py` | **new** - feature-function tests with known inputs |
| `requirements-base.txt` | **modified** - `neurokit2` only when a real source lands; **not now** |

### Implementation steps
1. Define `BiosignalWindow` (frozen): timestamp, source name, provenance stamp, and a mapping of
   named scalar features. Refuses construction without a stamp.
2. Implement `SimulatedCardioOculoSource`: plausible RR series with a slow arousal drift, pupil
   z-scores correlated to that drift, Poisson blinks. Seeded, so a screenshot is reproducible.
3. Implement the four pure feature functions with hand-checked fixtures (a constant RR series must
   give HF-HRV ≈ 0; a doubling of variance must raise it monotonically).
4. Implement `load_index()` as an explicit weighted sum with the weights named in the docstring -
   **no learned weights, nothing fitted**, because there is no outcome to fit against.
5. Build `load_panel()` and the page shell.
6. Wire the features into `LinearRiskScorer.context` at zero weight and assert the index is unchanged.

### Dependencies & integration points
- **Consumes:** `src/biosignals/*`, `theme`, `copy`.
- **Feeds:** the `context` mapping of `LinearRiskScorer`, at weight 0.
- **Cross-feature:** **V5 depends on V3's source and feature layer.** Build V3 first; V5 reuses
  `BiosignalWindow` and the band-power path rather than defining its own.

### Testing & validation
- A `BiosignalWindow` without a stamp raises.
- Feature functions match hand-computed values on fixed fixtures.
- The load index is monotone in each input, holding the others fixed.
- The panel renders "ranking only" and "not calibrated", and contains **no band label** - assert the
  absence of "low", "moderate", "high", "elevated" as standalone labels.
- With `context_weights={}`, `LinearRiskScorer.score()` returns bit-identical output with and without
  the context mapping - reuses the existing Phase 15 test.
- The source is seeded: two runs with the same seed produce identical windows.

---

## 11.6 V5 - Closed-Loop Neurofeedback (demo mode)

### Feature overview
An attention-training visual driven by a live alpha/theta ratio: a ring that expands while the
athlete holds the target state and contracts when attention drifts, with time-in-target and
longest-hold reported for the session. **In this phase the loop closes against a simulated signal and
no human is being trained** - it is a demonstration of the mechanism, not an intervention.

### Widget specification
- **Page:** `dashboard/pages/5_Neurofeedback_demo.py` - fifth in nav. The filename carries `_demo`
  deliberately; the nav label must read "Neurofeedback (demo)".
- **Component:** `neurovis.neurofeedback_panel(session, *, mode)`.
- **State:** a `NeurofeedbackSession` dataclass (elapsed, time-in-target, longest hold, target
  threshold) held in `st.session_state["nf_session"]`; Start / Stop / Reset buttons.
- **UI behaviour:** ring radius ∝ alpha/theta ratio; ring colour switches at the target threshold;
  a dashed reference circle marks the target; a trace below shows the ratio against the threshold
  line. Session stats update once per tick. A red banner states the demo-mode limitation at all times.
- **Summary tile:** "Time in target" for the last demo session.

### Files affected
| File | Change |
|---|---|
| `src/biosignals/session.py` | **new** - `NeurofeedbackSession` state machine; pure, no Streamlit |
| `src/biosignals/sources.py` | **modified** - `SimulatedEEGSource` gains the band-power path V5 needs |
| `src/dashboard/neurovis.py` | **modified** - `neurofeedback_panel()` |
| `dashboard/pages/5_Neurofeedback_demo.py` | **new** - page shell |
| `src/dashboard/copy.py` | **modified** - `NF_PLAIN`, `NF_DEMO_ONLY`, `NF_ETHICS_GATE` |
| `tests/test_biosignals.py` | **modified** - session state machine tests |
| `docs/ethics.md` | **NOT modified now - blocking gate before any human use** (§11.2) |

### Implementation steps
1. Implement `NeurofeedbackSession` as a pure state machine: `tick(ratio) -> SessionState`. All
   session arithmetic lives here so it is testable without a browser.
2. Add the band-power path to `SimulatedEEGSource` (alpha and theta from the same simulated series).
3. Build `neurofeedback_panel()`; the animation is CSS/JS inside the iframe, with the final state
   painted by a classic script first so a blocked CDN costs the motion and nothing else - the defect
   already found and fixed once in `motion.py`.
4. Build the page shell with the demo-mode banner rendered **before** any control, not after.
5. Add the ethics guard: the page refuses to render if the configured source is not a
   `SimulatedSource`.

### Dependencies & integration points
- **Consumes:** `src/biosignals/sources.py` and `features.py` - **V5 cannot be built before V3's
  source layer exists.** This is the only hard cross-feature dependency in the layer.
- **Consumes:** `theme`, `copy`, the `motion.py` two-script pattern.
- **Blocks on:** ethics approval and a clinician before any non-simulated use.

### Testing & validation
- The session state machine: time-in-target and longest-hold are correct on a hand-written ratio
  sequence; a reset clears both.
- The panel renders its demo-mode banner, and the banner text appears **before** the first control in
  the page source (same ordering rule as the provenance stamp).
- The page raises if handed a non-simulated source - assert the guard, not just its absence.
- The panel renders fully with the animation module removed (classic-script fallback).
- No band or threshold language leaks into the summary tile.

---

## 11.7 Build order and cross-feature dependencies

```
shared: src/biosignals/{sources,features}.py + src/dashboard/neurovis.py
   │
   ├── V1  Brain atlas          (independent - can ship alone, needs no source)
   ├── V3  Cognitive load       (needs sources + features)
   │      └── V5  Neurofeedback (needs V3's source + feature layer)
```

Recommended order: **shared → V1 → V3 → V5.** V1 first because it is independent, demos well, and
exercises `neurovis.py` before the biosignal layer is on the critical path.

### Definition of done for the layer
- `SRN_COGNITIVE_LAYER` set to an explicit off value ⇒ the dashboard is byte-identical to
  Phase 24 output. (Written as "unset ⇒ off"; the shipped default is on - see §11.3.)
- All existing tests green (74 at the time of writing), plus the new suites.
- No number on any new surface is absent from a stamped source or a `DashboardView`.
- Every new page passes the existing shell rules in `tests/test_dashboard_pages.py`.

---

## 12. Phase 27 - Media input, admission gates and the register test (built 2026-09-15)

> **Status: built, tested and deployed.** Unlike §11, which was written as a plan
> before any code existed, this section records what is in the repository.

### 12.1 Owner decisions (locked 2026-09-15)

| Question | Decision |
|---|---|
| Junk text on the live-scoring page | **Refuse.** No score, no band, no view constructed. |
| Photo and video upload | **Yes.** Words are recovered and scored as typed words are. |
| What the media engine reads | **Both** the words (OCR / speech) and a non-verbal channel. |
| Non-verbal channel default | **Off** (`context_weights={}`). Visible toggle on the page. |
| A reader that looks at a real face | **Blocked at construction** until `docs/ethics.md` §13 is satisfied. |
| "Irrelevant" media | Judged on the **recovered words**, never on the picture. |
| Off-register text | **Scored and flagged loudly**, not refused. |
| OCR engine | Upstream Tesseract, invoked directly. No Python wrapper. |

### 12.2 The four steps, and which of them is a gate

```
 upload ──▶ [1] admit the file ──▶ [2] recover words ──▶ [3] admit the words ──▶ [4] judge register
            bytes, not extension     OCR / speech          is this language?       advisory only
            REFUSES                  REFUSES if unreadable REFUSES                 FLAGS, never refuses
                                                                                         │
                                                                                         ▼
                                                                          scored exactly as typed text
```

Steps 1–3 refuse, and a refusal means **no `DashboardView` is constructed**, so
no number exists to screenshot. Step 4 decorates.

### 12.3 The 0.50 problem - the defect this whole phase is shaped around

`LexiconBackend` will score anything. Hand it keyboard mash, or an empty string
from a missing OCR engine, or a car-park sign: nothing matches, all ten
probabilities are 0.0, the weighted sum is 0.0, and the logistic squash returns
an index of **exactly 0.50** - a psychological score of 50 out of 100, with a
band, a stamp and ten tiles beneath it. Every step is arithmetically correct and
the screen is a lie.

Three components exist because of this one failure, arriving by three doors:

* `gibberish.admit` - the paste box door.
* `NullExtractor` returning `ok=False` rather than `""` - the missing-backend door.
* `mediaio.read_upload` re-running the text gate on machine-read words - the
  OCR-of-something-that-is-not-prose door.

**Rule for any future input path: an input that cannot be read produces no
number. Never a zero, never a default, never a midpoint.**

### 12.4 New modules

| File | Responsibility |
|---|---|
| `src/media/admission.py` | Is this a readable photo or video? Magic numbers and header parsing, pure Python, no image library. |
| `src/media/extract.py` | Words out of a file. `TextExtractor` Protocol; `TesseractOCR`, `WhisperTranscriber`, `NullExtractor`. |
| `src/media/relevance.py` | Register test. Measured on `gold_dev` / `gold_eval`. Advisory. |
| `src/media/nonverbal.py` | Face/voice channel. Stamped, zero-weighted, ethics-gated. |
| `src/dashboard/gibberish.py` | Is pasted or recovered text language at all? |
| `src/dashboard/mediaio.py` | **The only door** between `dashboard/` and `src.media`. |

`src/dashboard/mediaio.py` exists because `tests/test_dashboard_pages.py`
enforces that a module under `dashboard/` imports from `src.dashboard` and
nowhere else under `src.`. Routing the media layer through one bridge keeps that
rule true rather than making an exception for one feature.

### 12.5 Rules for this layer

1. **The risk index is produced from words.** Anything read off a face or a voice
   enters through `LinearRiskScorer.context`, whose weights default to empty.
   `tests/test_media.py` asserts bit-identical output with and without context.
   This is the Phase 15 text-only guarantee restated, and it is what lets the
   paper stay text-only while the page offers uploads.
2. **No gate may claim a capability the project has not measured.** The register
   test judges words because a picture classifier would need a labelled image set
   and a reported error rate that do not exist. If a future phase wants one, it
   ships with a number or it does not ship.
3. **Every recovered passage carries `MACHINE-READ`; every non-verbal reading
   carries `NOT A MEASUREMENT`.** Both are enforced in `__post_init__`, in the
   same way `ScoreSurface` requires `PROVISIONAL` and `BiosignalWindow` requires
   `SIMULATED`.
4. **Nothing is retained.** No disk, no log, no cache, no temp file - OCR streams
   bytes on stdin. See `docs/ethics.md` §13.3.
5. **Optional backends are genuinely optional.** A clean checkout has no OCR
   engine and no speech model, and in that state the media path refuses honestly.
   Deployment installs them via `packages.txt` (Streamlit Community Cloud) and the `Dockerfile`.

### 12.6 What is deliberately not built

* A visual classifier for "this photograph contains an athlete". See rule 2.
* Any real facial or vocal analysis. `GatedRealReader` raises.
* Word-error-rate evaluation of OCR or speech recognition. Not measured here, so
  not claimed here.
* A relevance gate over *pasted* text. The register test runs on media only,
  because that is what was asked for; extending it to the paste box is a
  one-line change and a decision nobody has made.


## 13. Phase 28 - facial cues in the index (built 2026-09-16)

> **Status: built.** Supersedes §12.5 rule 1 and §12.6 bullet 2.

### 13.1 Owner decisions (locked 2026-09-16)

| Question | Decision |
|---|---|
| Read facial cues from uploaded photos | **Yes**, under an uploader consent attestation |
| Do they move the risk index | **Yes, always**, when a face was actually read |
| Engine | `hsemotion-onnx` (Apache-2.0), chosen for Streamlit Community Cloud: no PyTorch |
| Face location | OpenCV Haar cascade, `opencv-python-headless` |
| Features | `negative_valence`, `arousal` - named for the picture, never for a person |
| Weights | Declared: +0.20, +0.10. Not fitted; there is no outcome to fit against |
| Ethics gate | Discharged for facial cues in `docs/ethics.md` §14, before the code landed |

### 13.2 The rules this layer adds

1. **Consent is a construction precondition.** `FaceCueReader(consent=False)`
   raises `NonVerbalEthicsGate`. There is no object to call, so no path leads
   from an unticked box to a face being read.
2. **Only a measured reading carries weight.** `FACE_WEIGHTS` is keyed on the two
   face features only. The simulated reader's three features are not keys, and
   `fusion.score` adds a term only for a name in both mappings, so a missing
   library, a missing face or a missing consent tick can never become a number.
   This is the Phase 27 0.50 rule applied to a new door: an input that cannot be
   read produces no number, never a zero and never a default.
3. **Both scores are on the page.** Text-only beside combined, whenever the face
   moved the index.
4. **The §14.3 limitation renders above the score, outside any expander,** in the
   error style, so it survives a screenshot.
5. **The paper stays text-only in its numbers.** No face-derived figure appears in
   any table, figure or claim; where the paper describes the deployed page it
   must say that uploads are scored from text plus two facial cues under consent.

### 13.3 What is deliberately still not built

* Voice or prosody analysis. The video path still yields words only.
* Any identification, matching, embedding or storage of a face.
* A measured error rate for the cues. None exists, so none is claimed.

## 14. Phase 29 - match-day profile: built, blocked by default (2026-09-19)

> **Status: code and tests exist; the feature is inert in every checkout and
> every deployment until an explicit environment flag is set. It was found on
> review, before the code was committed, to be the exact case this project's own
> written ethics policy already prohibits. This section documents the finding
> and the gate, not an owner decision to ship the feature.**

### 14.1 What was requested and what was built

Owner request, 2026-09-19: given a link to a press conference and a photograph
of the athlete in it, produce the ten-construct metrics and one final score for
that specific person. `src/media/pressroom.py` fetches the video's published
caption track (or, if installed locally, transcribes the audio with
`faster-whisper`) and `src/dashboard/matchday.py` combines that transcript with
the Phase 28 facial-cue channel into one profile, rendered by
`dashboard/pages/6_Match_day_profile.py`. Every step de-identifies the
transcript, stamps every number `MACHINE-READ` or `NOT A MEASUREMENT`, and
refuses rather than defaulting when a channel is missing - the same discipline
as every other phase in this document.

### 14.2 Why it is blocked, in the project's own words

This is not a new judgment call. `docs/ethics.md` already says, in writing,
before this phase existed:

* §2.3.3 (binding, since the policy's first version): the system must never be
  used to "generate claims about a **named** athlete's psychological state,
  publicly or privately."
* §13.4: "Media of a public figure from a press conference is **not** exempt.
  Public availability of a recording is not consent to psychological inference
  about the person in it."
* §14.2 (Phase 28, 2026-09-16): "Third-party and public-figure material remains
  prohibited... A press photograph of a named athlete is exactly the case the
  first bullet of §13.5 forbids, and ticking the box does not make it
  permitted."

A match-day profile is, by construction, a specific real person's press
conference plus their photograph, reduced to "one final score." That is the
prohibited act, not a nearby one, regardless of de-identification inside the
text pipeline - de-identifying the transcript's *content* does not de-identify
*who the reader is looking up*. Unlike Phase 28's face-cue reader, there is no
consent checkbox that fixes this: the athlete in someone else's press-conference
recording never agreed to anything, and §13.4 already anticipated and rejected
the "it's public, so it's fine" argument before this phase made it.

### 14.3 The gate

`src/media/pressroom.py::fetch_transcript` refuses unconditionally - before any
network call - unless the environment variable `SRN_MATCHDAY_REAL_ATHLETES` is
set. This is the same shape as `GatedRealReader` in `src/media/nonverbal.py`
before Phase 28 discharged it for facial cues, applied to a case that (unlike
Phase 28) this document does not currently discharge. `docs/ethics.md` §15
carries the full compliance record and the condition for ever unblocking it.
The flag is **off by default** everywhere, including the deployed Streamlit
Community Cloud app, and is documented in `.env.example` rather than set there.

### 14.4 What would have to be true before this is ever turned on

None of these exist yet, and none is created by this section:

1. A deliberate, dated owner decision that public-figure inference is in scope
   for this project at all - a reversal of §2.3.3 and §13.4, not a carve-out
   squeezed under them, argued in writing with the reviewer-facing consequence
   stated (a paper claiming "research and decision-support only" while its
   deployed dashboard names a specific athlete and scores them is not a
   position a reviewer will let pass unchallenged).
2. If that reversal is made: a real consent or notice route for the athlete
   named in the link, not an attestation by the person pasting the URL about
   somebody else.
3. A retention and takedown route matching `docs/ethics.md` §7 for a specific,
   identifiable person who did not submit anything.
4. The §14.3 (Phase 28) facial-cue limitation, restated for a photograph the
   uploader may not have taken themselves.

Until all four exist and are written into `docs/ethics.md`, the flag stays
unset in every environment this project controls.

### 14.6 Owner decision recorded (2026-09-20)

The question was put to the owner via `docs/phase29_decision_draft.md`, worked
through against all four §14.4 conditions. **Decision: Declined.** §2.3.3 and
§13.4 stand unchanged; `SRN_MATCHDAY_REAL_ATHLETES` stays permanently unset.
See §15 below for what was built instead.

## 15. Phase 30 - Scenario-driven match-day profile (synthetic, built 2026-09-20)

> **Status: built.** With Phase 29's real-athlete path declined (§14.6), the
> Match-day profile page needed something honest to score. This phase adds a
> scenario the reader picks from dropdowns instead of a real link.

### 15.1 What was requested and what was built

Owner request, 2026-09-20: more sports, more competition-timing options, and
pressure/life-context scenarios (injury, breakup, a strong past season, etc.)
in the Match-day page's dropdowns, such that a different combination produces
a meaningfully different score rather than a different label on the same
generic text.

`src/ingestion/scenarios.py` adds a `life_context -> construct bias` table
(`SCENARIO_BIAS`) that decides which of the ten constructs a scenario plants
and at what intensity or label, then reuses `src/ingestion/synthetic.py`'s own
realisation banks and framing/variation helpers UNCHANGED to render the text.
`src/dashboard/matchday.py::build_scenario_profile` scores the result through
the ordinary `build_view`/`LexiconBackend` pipeline - no change to scoring
itself. `dashboard/pages/6_Match_day_profile.py` renders the three dropdowns
and a "Generate & score" button, placed before the real-link path's gate so it
always renders regardless of §14's block.

### 15.2 Why "timing," not "during or after the event"

`synthetic.py`'s own docstring records that the Phase 7 source survey
deliberately excluded post-match text: it expresses relief, disappointment and
attribution, constructs outside this project's taxonomy. Offering a
during/after option here would need new taxonomy work this feature does not
do. `TIMINGS` (`week_before` / `morning_of` / `immediately_before`) therefore
stays entirely on the pre-competition side, varying only the distance from the
event - the owner-approved resolution to this scope conflict.

### 15.3 Grounding, and what stayed untouched

Every construct named in `SCENARIO_BIAS` cites the same `config/taxonomy.yaml`
instrument anchor that construct already carries in `synthetic.py`'s own
realisation bank (e.g. `injury_comeback`'s `resilience` entry cites CD-RISC
[Connor2003], the same anchor `taxonomy.yaml` gives that construct generally)
- the mapping is grounded in the same instruments, not invented fresh.
`src/ingestion/synthetic.py` has zero diff: its version-history comments warn
that changing its construct-drawing or realisation internals reshuffles the
RNG stream for every existing seeded corpus artefact, so the bias table lives
in a new module that imports those internals rather than editing them.

### 15.4 Verification

`tests/test_scenarios.py` (14 tests): input validation, determinism (same
scenario + seed → identical text), and a statistical check over 30 seeds that
a different `life_context` at the same sport/timing changes the planted
construct set at least 90% of the time. An end-to-end check through the real
`LexiconBackend` (same sport, same timing, five life contexts) produced scores
of 50 / 62 / 27 / 82 / 73 - confirming the score moves for a real, auditable
reason rather than a cosmetic one.

### 14.5 What is deliberately still not built

* Any UI path that sets `SRN_MATCHDAY_REAL_ATHLETES` from inside the app. It is
  an environment variable an operator sets outside the running process,
  deliberately, once, matching how `SRN_COGNITIVE_LAYER` works.
* A consent checkbox for the press-conference link. §14.2 above is why: no
  checkbox available to the page's reader can supply the athlete's consent.
* Any use of the speech-recognition fallback (`yt-dlp` + `faster-whisper`) in
  the deployed Streamlit Community Cloud app. Both are installed locally only
  (§6 below); the caption route is the only one `requirements-base.txt` ships.

## 16. Phases 31–32 - abstention measurement, cue widening, evidence coverage (built 2026-09-21/23)

> **Status: built and tested.** Written 2026-09-23, late: §8 rule 10 says this file is
> updated when a decision is confirmed, and Phases 31 and 32 both shipped without a
> section. The lateness is the finding - a rule that is only obeyed when convenient is
> not a rule, and the four mis-cited figures in §16.3 are what it cost.

### 16.1 Owner decisions (locked 2026-09-21/22)

| Question | Decision |
|---|---|
| Fix the 0.50 problem by removing the §12.3 refusal rule | **No.** Measured at +0.2% of corpus traffic; the rule stands |
| How to lower the silence rate instead | **Widen the demo cue list only** (`DASHBOARD_EXTRA_CUES`), from the generator's own taxonomy-anchored realisation banks, never from corpus text |
| Does the widened list enter any committed figure | **No.** `LexiconBaseline` and macro-F1 0.462 are untouched; the widened list has no measured score |
| Ship the Evidence Coverage widget behind a flag | **No flag.** It introduces no source, no signal, no dependency and no new number |
| Retain the pre-build mockup after the panel lands | **Yes**, as the design contract |

### 16.2 What was built

**Phase 31** - `src/evaluation/abstention.py` measures the three refusal gates for the
first time and computes the counterfactual index each refused input would have received.
The measurement contradicted `§12.3`'s prose: an index of exactly 0.50 is reached three
ways and the gates close only the narrowest (`refused` 0.2%; `no_detection` 58.6%;
`all_inert` 12.4%). `reports/abstention.md` is the artifact.

**Phase 32** - `config/instruments.yaml` + `src/dashboard/{instruments,coverage,coverage_panel}.py`
+ `dashboard/pages/7_Evidence_coverage.py` project one already-scored `DashboardView` onto
the eight instruments behind the taxonomy and report, per subscale, `evidenced` / `inert` /
`silent`. It computes no new number and cannot move the risk index. `docs/phase32_implementation_plan.md`
is the plan; `docs/dashboard.md` and `docs/model_card.md` carry the standing documentation.

### 16.3 The rule these phases add, and the rule they broke

**A coverage figure is meaningless without the cue list that produced it.** The project
runs two detectors - the frozen `CONSTRUCT_CUES` every committed figure was measured with,
and that list widened by `DASHBOARD_EXTRA_CUES` for the deployed page only. Their silence
rates over the same corpus are **58.8%** and **20.2%**: a factor of three.

Phase 32 quoted "20.2%" on six lines across five files without naming the list, including
in the paragraph
of `docs/model_card.md` that states the rule, while the surrounding evaluation uses the
frozen list. Both figures now travel together and both are measured in one place -
`reports/abstention.md` §4, added 2026-09-23 so the number has a reproducible source rather
than a commit message. (§3 of that report reads 58.6% for the frozen list because it files
the single refused text under `refused`; §4 counts the detector, §3 counts the pipeline.)

**The corrected headline.** The plan claimed a realistic passage speaks to "a quarter of the
instrument set", from three hand-picked passages. Measured over every text: `gold_dev` mean
**0.62 of 8** (0: 40, 1: 58, 2: 2), `gold_eval` mean **0.56 of 8**. A typical text speaks to
zero or one instrument and 40% of `gold_dev` speaks to none. The starker number is the true
one and it is the better one for the paper.

### 16.4 What is deliberately not built

* A measured score for the widened cue list. Coverage is measured; precision is not, and it
  cannot be until `data/gold/` is annotated (OPEN-025).
* Coverage aggregated across several texts from one athlete over time - the natural next
  phase, and Future Work until the temporal hook is claimed.
* Any scoring of a subscale. The moment a subscale carries a number this stops being a
  limitations display and becomes an unvalidated psychometric instrument.
* Any reproduction or paraphrase of an instrument item. CSAI-2, ABQ, CD-RISC and TAIS are
  copyrighted; every prompt derives from this project's own `config/taxonomy.yaml` definitions.

## 17. Phase 34 - three read-only surfaces (built 2026-09-26)

> **Status: built and tested.** Three pages that show what the project already
> computes, from angles it had no surface for. None adds a model, a weight, a
> channel or a claim, and none touches a person - which is why none of them needed
> an ethics decision and why `docs/ethics.md` is untouched.

### 17.1 What was asked for and what was built

Owner request, 2026-09-26: visually appealing features, unrelated to the
compare-two-texts page. Three were proposed and all three built:

| Feature | Page | What it shows |
|---|---|---|
| **Sentence ribbon** | `dashboard/pages/7_Sentence_ribbon.py` | One passage cut into sentences, each scored on its own, drawn as a contour |
| **Corpus constellation** | `dashboard/pages/8_Corpus_constellation.py` | All 4,000 synthetic records as dots, in lanes by the construct the generator planted |
| **Taxonomy card deck** | `dashboard/pages/9_Taxonomy_cards.py` | `config/taxonomy.yaml` as ten designed cards: definition, anchor, examples, edge cases |

### 17.2 The one rule all three are shaped around

§12.3 again, three new doors. `LexiconBackend` scores anything, and an all-zero
decomposition squashes to **exactly 0.50** - a number that is arithmetically
correct and, drawn, is a lie. Each surface meets it differently and each refuses
it structurally rather than by convention:

* **`ribbon.SentenceBand` cannot hold a number it did not earn.** `detected` and
  `surface` must agree at construction. A sentence the detector said nothing about
  gets no column - just a hatched footing and the words "nothing detected".
* **`scripts/build_corpus_cloud.py` never writes an index for an undetected
  record.** 1,486 of 4,000 records match no cue; they are counted, excluded and
  reported on the figure instead of stacking into a false spike at the midpoint.
* **`corpus_cloud.CloudLane` refuses a median without scored records**, and the
  reverse. The same rule one level up.
* **The deck carries no number at all**, and therefore no stamp. A test asserts the
  absence of any score-shaped value in the rendered HTML.

A *real* 0.50 still exists and is marked rather than hidden: a sentence whose only
detected constructs are inert genuinely sums to zero, and is drawn hatched with
"counted as zero". Two different facts, two different markings.

### 17.3 New modules

| File | Responsibility |
|---|---|
| `src/dashboard/ribbon.py` | Segment a passage, score each sentence, refuse rather than degrade |
| `src/dashboard/corpus_cloud.py` | Load, validate and freeze `reports/corpus_cloud.json` |
| `src/dashboard/taxonomy_cards.py` | Load, validate and freeze `config/taxonomy.yaml` as cards |
| `src/dashboard/deck.py` | The deck as a host-page fragment; no iframe, no numbers |
| `scripts/build_corpus_cloud.py` | Builds the committed artifact. ~3 minutes, offline, no record text, no timestamp |
| `reports/corpus_cloud.json` | Committed. Per-lane counts, medians and sampled dots over 4,000 records |

`charts.py` gains `sentence_ribbon` and `corpus_cloud_chart`; `theme.app_css` gains
the deck's card geometry; `copy.py` gains the `RIBBON_*`, `CLOUD_*` and `DECK_*`
strings, screened at import as usual.

### 17.4 Rules this layer adds

1. **No new arithmetic anywhere.** Every number comes from `build_view` - the ribbon
   calls it per sentence, the builder called it per record. Nothing here fits a
   weight, invents a scale or averages an index.
2. **The lexicon floor is named on the ribbon page.** Per-sentence scoring needs a
   backend that can read new text, `ReplayBackend.predict` refuses by design, so
   every column is the floor and the page says so rather than implying otherwise.
3. **A lane is what the generator planted, never what the detector picked.** A lane
   chosen by the detector would be the detector marking its own work.
4. **The deck page has no `st.expander`, deliberately.** It shows no reading, so it
   has no provenance to hide behind one and no stamp to put above one.
5. **The four midpoint lanes are explained on the figure**, not only in prose: they
   are the conservative default working as designed, and an unexplained flat row
   reads as a broken detector.

### 17.5 One existing test was changed, and why

`tests/test_dashboard_pages.py::test_every_page_that_shows_a_number_shows_the_stamp_before_any_expander`
matched `st.expander` as a **substring of the page source**, so page 9's docstring -
which explains why that page deliberately has no expander - failed the rule for
mentioning it. The check now reads the syntax tree for a real call, which is
strictly more precise and leaves every existing page passing. The `app.py`
exemption in `STAMP_ABOVE_FOLD_EXEMPT` is untouched.

### 17.6 What is deliberately not built

* **No interaction.** Streamlit renders these figures as static SVG in markdown, so
  a clickable dot cannot route back to a page. Dropped rather than faked.
* **No density estimate on the constellation.** A kernel bandwidth is an invented
  constant; dots need no parameter to justify.
* **No radar or spider chart of the ten constructs.** It implies a calibrated
  profile that does not exist.
* **No re-scoring of the corpus on page load.** Three minutes is not a page load,
  and a cached three-minute computation is a stale cache nobody can date.

## 18. Phase 35 - interface changes and a full light/dark sweep (2026-09-27)

> **Status: built, tested, verified in a running browser.** Six owner instructions, of
> which one was a question rather than a change. Recorded here on the day, which §16.3
> says is the rule that only counts when it is kept.

### 18.1 Owner decisions (locked 2026-09-27)

| Question | Decision |
|---|---|
| The "Synthetic text only..." strip across the top of four pages | **Removed.** Constant, both stylesheets' rules, and the dismiss control all deleted |
| Em dashes in the project's prose | **Replaced with `-`** everywhere except three functional or data sites (§18.3) |
| Photo / video upload and the facial-cue consent tick on "Score my own text" | **Removed completely.** `src/media/` stays in the tree, called by nothing |
| Light and dark control | **On every page**, through one helper, not eleven inlined radios |
| Light / dark colour defects | **Measured in the running app**, not eyeballed. Three found, three fixed |

### 18.2 Where the provenance the strip carried now lives

The removed strip said the corpus is synthetic and the system makes no claim about an
identifiable person. Deleting it removes a *reminder*, not the record: the same facts are
still carried by `RiskScore.provenance`, by `PROVISIONAL_STAMP` above the fold on every
page that shows a number, by `Band.describe()`, and by the provenance expander at the foot
of each page. Nothing that was load-bearing was removed; the strip was the one surface
stating it that no mechanism required.

### 18.3 The three em dashes that stayed, and why

A blanket replacement would have been wrong in exactly three places, and the difference is
whether the character is prose or data:

* `src/preprocessing/normalize.py` - the em dash **is** what the regex normalises.
* `src/ingestion/substitution_verdicts.py` - it is a member of an edge-punctuation set.
* `src/ingestion/synthetic.py` - realisation-bank text. Changing it changes every generated
  record, which desyncs `reports/corpus_cloud.json`, the silver artefacts and the explain
  reports from the generator that claims to produce them. That is a corpus regeneration, not
  a copy edit.

**Asked again on 2026-09-27, costed, and declined.** The sentence that stood here said the
regeneration was "available on request as one run of `scripts/build_corpus_cloud.py` plus
the ingestion scripts". That was wrong by about ten CPU-hours, and the correction is the
useful part of this entry. What it actually costs, from `docs/reproducibility.md` and
`src/reproducibility/manifest.py`:

* `corpus_records` is pinned to SHA-256 `fa09f5ad...` and `utterances` to `87a796ca...`,
  both enforced by `tests/test_reproducibility.py`. Changing one character of corpus text
  invalidates both.
* It cannot be applied to the artefacts as a character swap, because it changes
  tokenisation. `reports/explain/attributions.json` alone carries 11,522 token offsets,
  and those are recomputed rather than rewritten.
* Tier C - retrain the transformer and regenerate its prediction cache - is **~10 CPU-hours**,
  and the metrics `docs/reproducibility.md` declares byte-identical against this corpus
  (lexicon `0.4617...`, transformer `0.5877...`, delta `0.1259...`, memorisation gap
  `0.2342...`) can move underneath the Phase 23 paper.

**Owner decision, 2026-09-27: leave it.** Twenty-two em dashes survive, every one of them
inside quoted athlete speech - the one register in this repository where a dash is ordinary
prose rather than a house-style slip. A reader who meets one on the dashboard is meeting a
deliberate exception, not a missed file. The price of removing it is re-declaring the
reproduction manifest's hashes and every headline number the paper reports, and that price
buys punctuation.

### 18.4 The light/dark defects, and how they were found

Not by reading the stylesheet. A contrast audit was run in the live app over every element
on all twelve pages, inside the component iframes as well, in both modes - 24 sweeps. Three
defects, all of them invisible to the existing tests and to a screenshot of a resting page:

1. **The open select list.** Streamlit portals it to `<body>`, outside the widget's testid,
   so every rule in `app_css` and `claude_css` stopped at the closed control. In dark mode a
   navy select opened a white sheet of near-black options over a dark page.
2. **The running indicator.** `[data-testid="stStatusWidget"]` is painted from
   `.streamlit/config.toml`, one static file that cannot follow a runtime mode: "Running" and
   "Stop" rendered at **1.15:1** for the seconds a dark page was rerunning.
3. **The coverage panel's weakest glyph.** `STATE_TOKENS` painted silent and refused in
   `hairline`, a *border* token: **1.41:1** on the light canvas, **1.44:1** on the dark one.
   The weakest state was not faint, it was gone. Both now take `muted`, and the three states
   stay apart by glyph and by row text class - the non-colour separation used everywhere else.

`tests/test_dashboard_pages.py` gained two rules so each stays fixed.

**What was NOT changed, deliberately.** The SVG figures keep light-mode ink on a white card
in dark mode. That is `DARK["figure-surface"]` working as designed - a figure is a printed
media card - and an audit that reads `color` instead of `fill` reports it as a defect. It is
not one. And the brand coral sits at 2.61:1 on white wherever it carries text (`tchip`, the
demo-mode banner, the evidenced glyph). It is identical in both modes, it is the one token
both design specifications say does not move, and it is a brand decision rather than a
light/dark bug. Flagged here rather than silently retuned.

### 18.5 The polarity question, answered

Asked: are the four unresolved constructs always counted as zero under Conservative,
Optimistic and Pessimistic? **No - only under Conservative.** See §18.6 for the measurement.

### 18.6 Measured, not asserted

With all four polar constructs detected at 0.90 and no sub-labels supplied:

| Policy | Contribution of each of the four | Raw sum | Index |
|---|---|---|---|
| Conservative (`NEUTRAL`, the paper's) | `0.000` | +0.750 | 0.679 |
| Pessimistic | `+0.900` | +4.350 | 0.987 |
| Optimistic | `-0.900` | -2.850 | 0.055 |

`LinearRiskScorer._signed_weight` returns `(0.0, True)` only under `NEUTRAL`; the other two
return `(+magnitude, True)` and `(-magnitude, True)`. The second element stays `True` in all
three cases - the polarity really is unresolved whatever the policy - but `view.py` derives
inertness from the *weight*, not from that flag, so under the two exploratory policies
nothing renders as inert and all ten constructs move the index. That is the behaviour
`POLICY_NOTES` already describes, and it is now measured rather than trusted.
