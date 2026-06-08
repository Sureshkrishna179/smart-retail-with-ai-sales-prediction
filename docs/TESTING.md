# Testing Guide — SmartRetail AI

## Quick start

**Windows**

```powershell
.\scripts\run_tests.ps1
```

**Linux / macOS**

```bash
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh
```

**Manual**

```bash
pip install -r requirements-dev.txt
python scripts/generate_grocery_sales.py
pytest tests -m "not integration"
```

## Integration tests (MySQL)

1. Ensure MySQL is running and `.env` matches your instance.
2. Run `python backend/setup_database.py` once.
3. Enable integration suite:

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
.\scripts\run_tests.ps1
```

## What each test file does

| File | Scope |
|------|--------|
| `test_smoke.py` | Repo layout, imports, CSV presence |
| `test_festivals.py` | Pongal/weekend multiplier logic |
| `test_validation.py` | API input validators |
| `test_ml_grocery.py` | Train/predict on `grocery_sales_realistic.csv` |
| `test_integration.py` | HTTP server + optional MySQL |

## CI

GitHub Actions workflow `.github/workflows/ci.yml`:

- **test** job: unit tests on Ubuntu without MySQL.
- **integration** job: MySQL 8 service + full integration markers.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Missing data/grocery_sales_realistic.csv` | Run `python scripts/generate_grocery_sales.py` |
| Import errors in scripts | Run commands from repository root |
| Integration skipped | Set `RUN_INTEGRATION_TESTS=1` and check `.env` |
| Import `serve_dashboard` fails | Run pytest from project root (see `pytest.ini` pythonpath) |
