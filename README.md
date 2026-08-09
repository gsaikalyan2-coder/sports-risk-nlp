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
pip install -r requirements-base.txt # light layer: agents, dashboard, dev tools
copy .env.example .env               # then fill in your OPENROUTER_API_KEY
pre-commit install
pytest && python scripts\hello.py    # expect: all tests pass, environment OK
python scripts\run_crew.py           # offline multi-agent run; free, deterministic
```

The heavy ML stack (torch, transformers, shap, wandb) is a separate layer and is not
needed until Phase 13:

```powershell
pip install -r requirements-ml.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

Containers (two images, light and training): **[`docs/docker.md`](docs/docker.md)**

```powershell
docker compose build app
docker compose run --rm app python scripts/hello.py
.\scripts\verify_docker.ps1          # focused Docker gate
.\scripts\verify_env.ps1             # full environment gate
```

## Layout

| Path | Purpose |
|---|---|
| `config/` | taxonomy, model routing, settings, data-source allow-list |
| `data/` | raw → interim → processed/silver → gold |
| `src/` | ingestion, preprocessing, taxonomy, labeling, models, risk, explainability, evaluation, agents |
| `dashboard/` | Streamlit demo |
| `reports/` | metrics, figures, explanations |
| `paper/` | IEEE LaTeX draft |
| `scripts/` | runners: `hello.py`, `run_crew.py`, `refresh_pricing.py`, `verify_*.ps1` |
| `logs/` | agent run logs + `cost_ledger.csv` |
| `docs/` | setup, docker, agents, annotation guidelines, related work, ethics, open issues |

## Cost control

Agent work routes through three OpenRouter cost tiers with a hard $20/month cap and an
append-only ledger at `logs/cost_ledger.csv`. **Offline is the default** — the smoke
crew runs deterministically with no API key and no spend, so tests and a reviewer
reproducing the artifact never cost anything. See **[`docs/agents.md`](docs/agents.md)**
and `config/model_routing.yaml`.

## Ethics

Uses public/licensed/synthetic, de-identified text. No mental-health claims about real
named individuals. See `docs/ethics.md`.
