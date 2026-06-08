# Contributing to SmartRetail AI

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env
python scripts/generate_grocery_sales.py
python backend/setup_database.py
```

## Before you push

1. Run tests: `make test` or `.\scripts\run_tests.ps1`
2. Do not commit `.env`, `data/ml_models.pkl`, or IDE folders
3. Follow [docs/COMPANY_STANDARDS.md](docs/COMPANY_STANDARDS.md)
4. Keep changes focused; update README if you change layout or env vars

## Branch naming

- `feat/short-description`
- `fix/short-description`
- `docs/short-description`

## Pull requests

- Describe what changed and how to test
- Ensure CI passes (unit + integration jobs)
