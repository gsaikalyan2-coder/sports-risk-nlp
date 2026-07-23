# Pre-Competition Psychological Risk Profiling of Athletes

Construct-grounded NLP that detects validated sports-psychology constructs in athlete
pre-competition text and fuses them into an interpretable **psychological risk index**.
Not sentiment analysis; not clinical diagnosis. Research / decision-support only.

- **Governing docs:** [`.claude.md`](.claude.md) (standing brief) · [`PROJECT_PLAN.md`](PROJECT_PLAN.md) (25-phase plan)
- **Stack:** Python 3.11 · CrewAI · OpenRouter · HuggingFace (DeBERTa/RoBERTa) · scikit-learn · SHAP · Streamlit · Docker

## Quickstart (WIP)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in your OPENROUTER_API_KEY
```

## Layout

| Path | Purpose |
|---|---|
| `config/` | taxonomy, model routing, settings |
| `data/` | raw → interim → processed/silver → gold |
| `src/` | ingestion, preprocessing, taxonomy, labeling, models, risk, explainability, evaluation, agents |
| `dashboard/` | Streamlit demo |
| `reports/` | metrics, figures, explanations |
| `paper/` | IEEE LaTeX draft |
| `_legacy/` | archived previous version (safe to delete once confirmed) |

## Ethics

Uses public/licensed/synthetic, de-identified text. No mental-health claims about real
named individuals. See `docs/ethics.md`.
