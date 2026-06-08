# Deployment guide

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_HOST` | Yes | MySQL host |
| `DB_USER` | Yes | MySQL user |
| `DB_PASSWORD` | Yes | MySQL password |
| `DB_NAME` | Yes | Database name (default `retail_sales_db`) |
| `PORT` | No | HTTP port (default `8765`) |
| `CORS_ORIGINS` | Yes | Must match public URL (comma-separated) |
| `JWT_SECRET` | Prod | Random 32+ byte hex secret |
| `REQUIRE_AUTH` | No | `1` to enforce login in production |
| `RATE_LIMIT_MAX` | No | API requests per minute per IP |

Copy `.env.example` to `.env` locally. On cloud hosts, set variables in the platform dashboard—never commit `.env`.

## Pre-deploy checklist

- [ ] `pip install -r requirements.txt` (not dev-only)
- [ ] `python scripts/generate_grocery_sales.py`
- [ ] `python backend/setup_database.py` (once per environment)
- [ ] `pytest tests -m "not integration"` passes
- [ ] `REQUIRE_AUTH=1` for public deployments
- [ ] `CORS_ORIGINS` matches your domain
- [ ] MySQL reachable from the app container/VM

## GitHub

Push to `main`; CI runs unit and integration tests (`.github/workflows/ci.yml`).

## Static frontend note

The SPA is served by the Python app from `frontend/`. You do not need a separate static host unless you split the API later.
