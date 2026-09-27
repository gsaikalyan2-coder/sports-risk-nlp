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
pip install -r requirements-base.lock.txt  # light layer, EXACT pins (Phase 22)
copy .env.example .env               # then fill in your OPENROUTER_API_KEY
pre-commit install
pytest && python scripts\hello.py    # expect: all tests pass, environment OK
python scripts\run_crew.py           # offline multi-agent run; free, deterministic
```

The heavy ML stack (torch, transformers, shap, wandb) is a separate layer and is not
needed until Phase 13:

```powershell
pip install -r requirements-ml.lock.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

## Reproducing the results

Minutes, no GPU, no API key. **Clone into a new directory** - the checker refuses
to grade a run performed in a tree that already holds the generated artefacts.

```powershell
git clone <repo-url> sports-risk-nlp-repro; cd sports-risk-nlp-repro
pip install -r requirements-base.lock.txt
python scripts\run_ingestion.py --count 4000 --seed 42
python scripts\run_preprocessing.py
python scripts\run_baselines.py --seed 42
python scripts\run_evaluation.py --seed 42 --resamples 1000
python scripts\run_reproduction.py --verify --root . --tiers A,B
```

Per-artefact strengths (byte-identical vs the ±0.010 retrain tolerance) and the
full list of what *cannot* be reproduced: **[`docs/reproducibility.md`](docs/reproducibility.md)**.
Release README: **[`ARTIFACT.md`](ARTIFACT.md)**.

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
| `docs/` | setup, docker, agents, annotation guidelines, related work, ethics, security, reproducibility, model card, open issues |

## Cost control

Agent work routes through three OpenRouter cost tiers with a hard $20/month cap and an
append-only ledger at `logs/cost_ledger.csv`. **Offline is the default** - the smoke
crew runs deterministically with no API key and no spend, so tests and a reviewer
reproducing the artifact never cost anything. See **[`docs/agents.md`](docs/agents.md)**
and `config/model_routing.yaml`.

## Ethics

Uses public/licensed/synthetic, de-identified text. No mental-health claims about real
named individuals. See `docs/ethics.md`.

## Contact - withdrawal, correction, incident reports

**`sk8069@srmist.edu.in`** (SRMIST institutional address)
Supervisor / secondary contact: **Dr. Shankar Ram**, SRMIST
Subject-line prefix: `[SPORTS-RISK-NLP]` · Acknowledgement target: **7 days**

`docs/ethics.md` §7.1 requires this route to appear on every reader-facing
surface. It is the mechanism behind §7's withdrawal and correction rights: if it
is not reachable from the document a reader actually has, those rights are
decorative. Note that the released corpus is 100% synthetic (OPEN-011), so no
real person's text is presently subject to withdrawal - the route exists so that
it already works on the day that stops being true.
