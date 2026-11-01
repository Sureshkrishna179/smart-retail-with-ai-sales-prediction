# SmartRetail AI — Company Engineering Standards

This document defines how teams build, test, secure, and operate the SmartRetail AI grocery retail platform.

## 1. Project structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md). Summary:

| Path | Purpose |
|------|---------|
| `src/smartretail/` | API server, DB setup, ML (`paths.py` for roots) |
| `frontend/` | Dashboard SPA |
| `data/` | Datasets; `samples/` for demos |
| `deploy/` | Docker, Render, Railway |
| `tests/` | pytest suite |
| `scripts/` | Start, tests, generators |
| `docs/` | Standards, deployment |

## 2. Naming and code style

- **Python**: PEP 8, 4-space indent, `snake_case` functions, `PascalCase` classes.
- **JavaScript**: camelCase for functions/variables; match existing `app.js` patterns.
- **Files**: lowercase with underscores for Python; kebab or lowercase for static assets.
- **Secrets**: never commit `.env`; use `.env.example` as the template only.
- **Comments**: explain business rules (festivals, stock thresholds), not obvious syntax.

## 3. Data standards (grocery retail)

### Sales training CSV

Required columns (exact headers):

```text
Date,Product,Sales_Qty
```

- **Date**: `YYYY-MM-DD`, one row per product per day.
- **Product**: SKU name matching catalog in `setup_database.py` (e.g. `Rice 1kg`, `Milk 500ml`).
- **Sales_Qty**: positive integer units sold.

### Canonical dataset

- **Primary**: `data/grocery_sales_realistic.csv` — full-year, 26 SKUs, festival/weekend/pay-day patterns.
- **Legacy sample**: `data/samples/sample_sales_data.csv` — 8 aggregate products for quick demos.
- **Regenerate**: `python scripts/generate_grocery_sales.py` (deterministic seed `42`).

### Product catalog

- Categories: Grocery, Beverages, Snacks, Personal Care, Spices, Dairy, Cleaning.
- Units: `kg`, `litre`, `pack`, `packet`, `bottle`, `piece` (validated on API).
- Low-stock alerts: `current_stock < min_stock_level`.

## 4. Security standards

- Passwords: PBKDF2-HMAC-SHA256 (`100_000` iterations), stored as `salt:hash`.
- API: rate limiting, CORS allowlist, CSP and security headers on all responses.
- Input validation on every POST body (`validate_*` in `serve_dashboard.py`).
- JWT via `JWT_SECRET`; set `REQUIRE_AUTH=1` in production.
- Roles: `Admin`, `Manager`, `Staff` — enforced when `REQUIRE_AUTH=1`; restock/add-product require Manager+.
- Audit log written on login, billing, restock, add-product, create-user.

## 5. Testing standards

### Required before merge

```powershell
.\scripts\run_tests.ps1
```

```bash
./scripts/run_tests.sh
```

### Test layers

| Layer | Marker | What it covers |
|-------|--------|----------------|
| Unit | (default) | Festivals, validation, ML on CSV, smoke/layout |
| Integration | `@pytest.mark.integration` | HTTP API, MySQL (set `RUN_INTEGRATION_TESTS=1`) |

### Coverage expectations

- New business logic in `serve_dashboard.py` must include unit tests.
- DB-dependent features need integration tests or documented skip reason.
- CI runs unit tests on every push; integration job uses MySQL service container.

## 6. Running the application

1. Copy `.env.example` → `.env` and set MySQL credentials.
2. `py -3 src/smartretail/db/migrations/setup_database.py` — schema + seed catalog.
3. `.\start.ps1` or `py -3 src/smartretail/server.py` — open printed URL.

## 7. Git and release

- Conventional commits encouraged: `feat:`, `fix:`, `test:`, `docs:`.
- No force-push to `main`/`master`.
- Do not commit credentials, customer PII, or production dumps.
- Tag releases as `vMAJOR.MINOR.PATCH` after CI green.

## 8. Observability

- Server logs request paths via `log_message`.
- DB connection status printed at startup.
- Failed transactions return JSON `error` with HTTP 4xx/5xx (no stack traces to clients).

## 9. ML operations

- Minimum 5 CSV rows per product to train; 10+ DB rows recommended for DB training.
- Models held in memory (`_models`); retrain after major catalog or sales changes.
- Document accuracy from `accuracy_by_product` in API responses when reporting to stakeholders.
