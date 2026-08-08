# Pre-Competition Psychological Risk Profiling of Athletes

Construct-grounded NLP that detects validated sports-psychology constructs in athlete
pre-competition text and fuses them into an interpretable **psychological risk index**.
Not sentiment analysis; not clinical diagnosis. Research / decision-support only.

- **Governing docs:** [`.claude.md`](.claude.md) (standing brief) · [`PROJECT_PLAN.md`](PROJECT_PLAN.md) (25-phase plan)
- **Stack:** Python 3.11 · CrewAI · OpenRouter · HuggingFace (DeBERTa/RoBERTa) · scikit-learn · SHAP · Streamlit · Docker

## Quickstart

Full instructions, Docker, pre-commit hooks and troubleshooting: **[`docs/setup.md`](docs/setup.md)**.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # then fill in your OPENROUTER_API_KEY
pre-commit install
pytest && python scripts\hello.py    # expect: all tests pass, environment OK
```

Container: `docker compose build && docker compose run --rm app python scripts/hello.py`
Verify everything at once (Windows): `.\scripts\verify_env.ps1`

## Layout

| Path | Purpose |
|---|---|
| `config/` | taxonomy, model routing, settings |
| `data/` | raw → interim → processed/silver → gold |
| `src/` | ingestion, preprocessing, taxonomy, labeling, models, risk, explainability, evaluation, agents |
| `dashboard/` | Streamlit demo |
| `reports/` | metrics, figures, explanations |
| `paper/` | IEEE LaTeX draft |
| `scripts/` | one-off runners (`hello.py` env check, `verify_env.ps1`) |
| `docs/` | setup, taxonomy guidelines, related work, ethics, security |

## Ethics

Uses public/licensed/synthetic, de-identified text. No mental-health claims about real
named individuals. See `docs/ethics.md`.
