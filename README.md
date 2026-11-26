# 🛒 SmartRetail AI — Dual-Core Sales Forecasting & Retail Operations System

> **ML-powered demand forecasting, POS billing, inventory management, and multi-tenant ETL for Indian grocery retail — driven by a Dual-Core ML engine, a 30-festival cultural calendar engine, and automatic MySQL-to-in-memory fallback.**

[![CI](https://github.com/Sureshkrishna179/smart-retail-with-ai-sales-prediction/actions/workflows/ci.yml/badge.svg)](https://github.com/Sureshkrishna179/smart-retail-with-ai-sales-prediction/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

---

## 📌 Overview & Business Impact

Small-format Indian supermarkets face sharp demand spikes around regional festivals, paydays, and weekends while managing perishable staples without dedicated data teams. **SmartRetail AI** solves this end-to-end inside a lightweight, single-command Python backend and dark/light SPA dashboard.

| Challenge | How SmartRetail AI Solves It | Technical Mechanism |
|-----------|------------------------------|---------------------|
| **Festival & shopping-rush volatility** | **Event Window Engine** models demand build-up and tail effects around regional & national events | ±5-day lead/tail windows across **30 calendar events** + **+15% weekend stacking** (`FESTIVALS`, `get_demand_multiplier`) |
| **Long-term growth vs. seasonal noise** | **Core A: Detrended HGBR (v2)** separates per-SKU growth trends from daily seasonality/event residuals | Log-linear OLS trend (`expm1`) + 15-feature `HistGradientBoostingRegressor` across **500 Store × SKU series** |
| **Custom store CSV onboarding & privacy** | **Core B: In-Memory RandomForest + Tokenizer** trains dynamically on uploaded CSVs without exposing raw SKU names internally | `ProductTokenizer` surrogate IDs (`UP001+`), 10 calendar + lag features, chronological 80/20 holdout |
| **Zero-DB / resilient operations** | **Decoupled Fallback Mode** keeps the dashboard, POS register, ML forecasting, and reports working even when MySQL is offline | `smartretail.db.inmemory_store` auto-seeded from `files/products.csv` |
| **Disparate POS file formats** | **Universal Multi-Tenant ETL** ingests `.csv`, `.xlsx`, `.xls`, and `.json` streams without touching disk | `POST /api/v1/etl/upload` with schema normalization, ACL contract, and chunked SQL upserts |

---

## 🏗️ System Architecture

```text
┌─────────────────────────────────────┐         ┌───────────────────────────────────────────────┐
│  Frontend SPA (frontend/)           │  HTTP   │  Backend — Python ThreadingHTTPServer (8765)  │
│  • dashboard.html (Dark/Light UI)   │────────▶│  • Zero web framework dependencies (stdlib)   │
│  • js/main.js & Chart.js 4.4        │◀────────│  • 21 REST Endpoints + Router + Rate Limiter  │
│  • css/styles.css                   │  JSON   │  • PyJWT Auth + RBAC + Input Validators       │
└─────────────────────────────────────┘         └───────────────────────┬───────────────────────┘
                                                                        │
          ┌─────────────────────────────┬───────────────────────────────┼─────────────────────────────┐
          ▼                             ▼                               ▼                             ▼
┌───────────────────┐       ┌───────────────────────┐       ┌───────────────────────┐     ┌───────────────────────┐
│  Dual-Core ML     │       │  Festival & Calendar  │       │  Universal ETL        │     │  MySQL 8.0 + Fallback │
│  • Core A: HGBR   │       │  • 30 ML Event Windows│       │  • .csv/.xlsx/.json   │     │  • Connection Pool(5) │
│    (15 features)  │       │  • 35 DB Seed Events  │       │  • Dynamic Col Map    │     │  • 6 Core Tables +    │
│  • Core B: RF     │       │  • ±5-Day Windows     │       │  • 50MB In-Memory     │     │    Sales_History      │
│    (10 features + │       │  • Weekend Stacking   │       │  • Bulk Upsert        │     │  • In-Memory Store    │
│    UPxxx Token)   │       │    (+15% Compound)    │       │    (5,000-row batch)  │     │    (Zero-DB Fallback) │
└───────────────────┘       └───────────────────────┘       └───────────────────────┘     └───────────────────────┘
```

---

## 🤖 Dual-Core Machine Learning Engine

SmartRetail AI routes predictions automatically (`mode="auto"`) or explicitly (`mode="core_a"`) across two complementary forecasting engines:

### Core A — Detrended HistGradientBoostingRegressor (`v2`)
- **Modules:** [`src/smartretail/ml/trainer.py`](src/smartretail/ml/trainer.py), [`src/smartretail/ml/predictor.py`](src/smartretail/ml/predictor.py)
- **Training Dataset:** Benchmark multi-store dataset (`files/sales_data.csv` — **913,000 rows** across **5 stores × 100 SKUs**).
- **Trend + Residual Decomposition:**
  1. Fits a per-series log-linear OLS slope & intercept (`log1p(Units_Sold)` vs. elapsed days).
  2. Computes `Residual = Units_Sold - Trend_Value`.
  3. Trains a pooled `HistGradientBoostingRegressor` (`loss="absolute_error"`, `max_iter=300`) across all 500 series using **15 features**:
     - **Calendar (5):** `day_of_week`, `month`, `day_of_month`, `year`, `week_of_year`
     - **Events & Promos (3):** `Is_Festival`, `Is_Promotion`, `Discount_Percent`
     - **Annual Residual Lags (2):** `lag_365_residual`, `rolling_mean_365_residual`
     - **Categorical Encodings (5):** `Store_ID_enc`, `Product_ID_enc`, `Category_enc`, `City_enc`, `Region_enc`
  4. Final prediction reconstructs demand as `max(0, Trend_Value(target_date) + Residual_Prediction)`.

#### Verified Benchmark Evaluation (`files/output/evaluation_report.txt`)
Evaluated on **182,500 out-of-sample rows** (Train: 2021–2024 | Validation: 2025 across 500 Store × Product series):

| Model | MAE | RMSE | WAPE | SMAPE |
|-------|-----|------|------|-------|
| Seasonal Naive | 6.164 | 9.302 | 21.61% | 22.91% |
| Plain HGBR (raw) | 4.786 | 7.244 | 16.77% | 17.12% |
| **Detrended HGBR (Core A)** | **3.567** | **5.594** | **12.50%** | **12.50%** |

- **25.46% MAE reduction** compared to Plain HGBR on raw units.

---

### Core B — In-Memory Multi-SKU RandomForest + Privacy Tokenizer
- **Modules:** [`src/smartretail/api/handlers/ml.py`](src/smartretail/api/handlers/ml.py), [`src/smartretail/ml/product_tokenizer.py`](src/smartretail/ml/product_tokenizer.py), [`src/smartretail/ml/cache.py`](src/smartretail/ml/cache.py)
- **Trigger:** Upload any custom sales CSV via `POST /api/train` (auto-detects `Date, Product, Sales_Qty`, `Product_ID, Units_Sold`, or flexible date/sku/qty column names).
- **How It Works:**
  1. **Privacy Encoding:** `ProductTokenizer` maps raw SKU names to deterministic surrogate IDs (`UP001`, `UP002`, ...) internally before modeling, then restores original product names in responses.
  2. **Daily Aggregation:** Groups duplicate same-day transactions per SKU and sorts chronologically.
  3. **10-Feature Pipeline:**
     - **Calendar & Domain (7):** `Year`, `Month`, `Day`, `DayOfWeek`, `IsWeekend`, `IsPayDay`, `DaysToFestival`
     - **Autoregressive Demand Signals (3):** `lag_1`, `rolling_3_mean`, `rolling_7_mean`
  4. **Zero-Leakage Validation:** Strict **80/20 chronological train/test split** reports per-SKU **MAE, RMSE, R², and WAPE-based Accuracy**, then refits on 100% of data for forward forecasting (up to **730 days**).
  5. **Forecast Dampening & Boosts:** Steps multi-day lag buffers forward using `0.75 * RF_Predict + 0.25 * DOW_Mean`, then applies ±5-day festival and +15% weekend multipliers.
  6. **State Reset:** Retraining Core A or calling `POST /api/reset-core-b` cleanly purges Core B models from memory.

---

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (CI and Docker run on Python 3.11)
- **MySQL 8.0+** *(Optional — if MySQL is unavailable, the server runs automatically in In-Memory Fallback mode for local demos)*

### 1. Clone & Configure Environment
```powershell
git clone https://github.com/Sureshkrishna179/smart-retail-with-ai-sales-prediction.git
cd smart-retail-with-ai-sales-prediction

# Create your local .env from the safe template
copy .env.example .env
# Edit .env with your DB credentials and generate random >=32-char keys for JWT_SECRET & ML_CACHE_SIGN_KEY
```

### 2. Install Dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
*(Or use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` without activating.)*

### 3. Run the Application

**Fastest Single-Command Launch (works with or without MySQL):**
```powershell
# Using root launcher (automatically adds src/ to sys.path)
python server.py
```
*(On Windows with `.venv`, run `.\.venv\Scripts\python.exe server.py` or double-click `run.bat`. Or with module syntax: `$env:PYTHONPATH="src"; python -m smartretail.server`.)*

**Full Windows Bootstrap (installs deps, generates sample CSV if missing, runs MySQL migrations, starts server):**
```powershell
.\scripts\start.ps1        # PowerShell
# or: scripts\start.bat    # Command Prompt
```

**Manual Database Setup (Optional, for persistent MySQL):**
```powershell
python scripts/generate_grocery_sales.py
$env:PYTHONPATH="src"; python src/smartretail/db/migrations/setup_database.py
```

Open **`http://localhost:8765/`** in your browser *(do not open `frontend/dashboard.html` directly as a file)*.

---

## 🔌 REST API Endpoints (`21` Routes)

All `/api/*` routes pass through sliding-window rate limiting (`60 req/min` default, `5 req/min` default on `/api/login` unless configured otherwise in `.env`), CORS origin filtering, HTTP security headers, and JWT/RBAC enforcement (`REQUIRE_AUTH=1`).

| Domain | Endpoints | Roles | Key Responsibilities |
|--------|-----------|-------|----------------------|
| **Auth** | `POST /api/login` | Public | PBKDF2-HMAC-SHA256 verification + PyJWT (`HS256`) token issuance (with in-memory demo fallback) |
| **Products** | `GET /api/products`, `POST /api/add-product` | Auth / Admin, Manager | Product catalog lookup & validated SKU creation (`price`, `stock`, `category`, `unit`) |
| **Inventory** | `GET /api/inventory-alerts`, `POST /api/restock` | Auth / Admin, Manager | Low-stock threshold monitoring & atomic stock replenishment + `inventory_log` |
| **POS & Reports** | `POST /api/billing`, `GET /api/reports`, `GET /api/csv-template` | Auth | Atomic transactional cart checkout, 12-month revenue analytics, sample CSV download |
| **Dual-Core ML** | `POST /api/train`, `POST /api/predict`, `GET /api/model-info`, `GET /api/trained-products`, `POST /api/reset-core-b` | Auth | Core A HGBR / Core B CSV RF training, 1–730 day forecasting, tokenizer mappings, metrics, Core B reset |
| **Users & Audit** | `GET /api/users`, `POST /api/create-user`, `POST /api/toggle-user`, `GET /api/audit-log` | Admin | Staff account management (strong password enforcement) & last-50 audit log view |
| **System** | `GET /api/db-status`, `GET /api/festivals`, `GET /api/products-csv` | Auth | MySQL health status, festival multiplier calendar, benchmark SKU catalog |
| **Universal ETL** | `POST /api/v1/etl/upload` | Auth | Multipart stream upload (`.csv`, `.xlsx`, `.xls`, `.json`, max 50MB) → normalized `Sales_History` upsert |

---

## 🔒 Security Architecture

| OWASP Risk | Implemented Controls |
|------------|----------------------|
| **A01: Broken Access Control** | PyJWT (`HS256`) verification + `@require_auth(allowed_roles=...)` RBAC (`Admin`, `Manager`, `Staff`, `Viewer`) |
| **A02: Cryptographic Failures** | PBKDF2-HMAC-SHA256 (**600,000 iterations**, 16-byte random salt, timing-safe `hmac.compare_digest`) |
| **A03: Injection** | Parameterized SQL (`%s` placeholders) across `db/connection.py`, handlers, and `Sales_History` batch upserts |
| **A04: Insecure Design** | Dedicated pure-function payload validators, strong password policy (12+ chars, upper/digit/special), 10MB JSON & 50MB ETL upload caps |
| **A05: Security Misconfiguration** | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, CSP, `Permissions-Policy`, explicit `CORS_ORIGINS` allowlist, sliding-window `RateLimiter` |
| **A08: Software & Data Integrity** | HMAC-SHA256 signed joblib model cache (`rf_models.joblib` + `rf_models.sig` via `ML_CACHE_SIGN_KEY`) |
| **A09: Security Logging & Failures** | MySQL `audit_log` tracking on user/admin/stock events + UUID-tagged `safe_error` responses (hides Python tracebacks) |
| **DB Least Privilege & CI Scans** | `setup_database.py` creates restricted `retail_app@localhost`; CI runs `bandit` (SAST), `pip-audit` (SCA), and `Trivy` |

> **Auth Toggle:** Set `REQUIRE_AUTH=1` in `.env` for production JWT enforcement, or `REQUIRE_AUTH=0` for open local/demo access.

---

## 🐳 Deployment & CI/CD

### Deployment Configs in Repository
| Target | Config File | Command / Notes |
|--------|-------------|-----------------|
| **Docker** | [`Dockerfile`](Dockerfile) | `docker build -t smartretail-ai .` → `docker run -p 8765:8765 --env-file .env smartretail-ai` *(Runs `python:3.11-slim` as non-root `appuser` with `/dashboard.html` healthcheck)* |
| **Render** | [`render.yaml`](render.yaml) | Blueprint auto-configures Python service (`pip install -r requirements.txt` → `python -m smartretail.server`) with generated `JWT_SECRET` & `ML_CACHE_SIGN_KEY` |
| **PaaS / Procfile** | [`Procfile`](Procfile) | `web: python -m smartretail.server` |
| **CI/CD & Cloud Run** | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | Runs unit tests + coverage, security scans (`bandit`, `pip-audit`, Trivy), MySQL 8.0 integration suite, and Cloud Run deploy workflow on `main` |

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for step-by-step Render, Koyeb, free cloud MySQL (Aiven / TiDB), and instant public tunneling instructions.

---

## 📁 Project Structure

```text
Project AI Sales/
├── server.py                              # Root single-command launcher (adds src/ to sys.path)
├── run.bat                                # Windows double-click / cmd launcher (py -3 server.py)
├── Dockerfile                             # python:3.11-slim non-root container + /dashboard.html healthcheck
├── render.yaml                            # Render.com Blueprint service definition
├── Procfile                               # Web process entry point (python -m smartretail.server)
├── Makefile                               # Shortcuts for install, data, setup-db, run, test, package
├── pyproject.toml                         # Project metadata, pytest config (pythonpath = ["src"]), Ruff rules
├── requirements.txt                       # 9 production dependencies
├── requirements-dev.txt                   # Dev, pytest, coverage, bandit, pip-audit dependencies
├── .env.example                           # Environment variable template (never commit .env)
├── src/
│   ├── paths.py                           # Filesystem root anchors & directory initialization
│   └── smartretail/
│       ├── config.py                      # Immutable Settings dataclass (sole os.getenv reader)
│       ├── server.py                      # ThreadingHTTPServer, static SPA serving, router & rate limiter
│       ├── api/
│       │   ├── router.py                  # Method+path router with UUID-tagged safe_error handler
│       │   ├── utils.py                   # JSON body reader (10MB payload cap)
│       │   ├── handlers/                  # auth, products, inventory, sales, ml, users, system
│       │   ├── middleware/                # auth (@require_auth), cors, rate_limiter, security_headers
│       │   └── validators/                # Pure input validation functions (core, products)
│       ├── db/
│       │   ├── connection.py              # MySQLConnectionPool (size 5) & atomic transactions
│       │   ├── inmemory_store.py          # Thread-safe decoupled CSV fallback store
│       │   └── migrations/setup_database.py # Idempotent schema DDL + 45 products + 35 festivals + least-privilege user
│       ├── etl/
│       │   └── ingestion.py               # Stream ETL (.csv/.xlsx/.xls/.json), column mapping, ACL, Sales_History load
│       ├── ml/
│       │   ├── trainer.py                 # Core A Detrended HGBR trainer (15 features, 500 series)
│       │   ├── predictor.py               # Core A inference engine & trend extrapolation
│       │   ├── product_tokenizer.py       # Bidirectional SKU privacy tokenizer (UP001+)
│       │   └── cache.py                   # HMAC-SHA256 signed joblib model persistence
│       └── services/
│           └── auth_service.py            # PBKDF2-HMAC-SHA256 hashing & PyJWT issue/verify
├── frontend/
│   ├── dashboard.html                     # Single-page dashboard shell
│   ├── js/main.js                         # Dashboard logic, Chart.js visualizations & API client
│   ├── app.js                             # Legacy frontend helper entrypoint
│   └── css/styles.css                     # Dark/light theme styles
├── data/
│   ├── grocery_sales_realistic.csv        # Generated 1-year multi-SKU daily sales CSV
│   ├── database_dump.sql                  # Full MySQL dump for portability
│   └── samples/sample_sales_data.csv      # 8-product sample upload CSV
├── files/
│   ├── products.csv                       # Canonical 100 grocery SKU catalog
│   ├── sales_data.csv                     # 913,000-row 5-store × 100-SKU benchmark dataset
│   ├── stores.csv                         # 5 store branch metadata records
│   ├── tn_calendar_2026.csv               # 365-day Tamil Nadu calendar reference
│   └── output/                            # Pre-trained sales_forecaster.model & evaluation_report.txt
├── scripts/                               # Launchers (start.ps1/bat), test runners, DB dump/cloud migration, CSV generators
├── tests/                                 # 8 test modules (43 tests: unit + optional MySQL integration)
├── docs/                                  # COMPANY_STANDARDS.md, DEPLOYMENT.md, PROJECT_STRUCTURE.md, TESTING.md
└── .github/workflows/ci.yml               # GitHub Actions: pytest, Bandit/pip-audit/Trivy, MySQL 8.0 integration, Cloud Run deploy
```

---

## 🧪 Testing

The test suite contains **43 tests across 8 modules** (36 offline unit/functional tests + 7 MySQL-marked integration tests).

```powershell
# Unit & functional tests only (no MySQL required)
.\.venv\Scripts\python.exe -m pytest tests -m "not integration" --cov=src/smartretail

# Integration tests (requires running MySQL + configured .env)
$env:RUN_INTEGRATION_TESTS="1"; .\.venv\Scripts\python.exe -m pytest tests -m integration

# Windows / Unix helper runners
.\scripts\run_tests.ps1
# ./scripts/run_tests.sh
```

| Test Module | Tests | Coverage Focus |
|-------------|-------|----------------|
| `test_smoke.py` | 10 | Project layout, data CSV schemas, package imports |
| `test_validation.py` | 8 | Product, billing, restock, prediction (730-day cap), and password validators |
| `test_ml_grocery.py` | 7 | Core B CSV training, chronological 80/20 split, WAPE/RMSE/MAE metrics, forecasts |
| `test_etl_ingestion.py` | 5 | Multi-format stream extraction, ACL contract enforcement, tenant scoping |
| `test_integration.py` | 5 | Live HTTP endpoint behavior & MySQL integration |
| `test_festivals.py` | 4 | Festival window detection, lead/tail spans, weekend multiplier stacking |
| `test_login.py` | 2 | PBKDF2 authentication, JWT claims & expiry checks |
| `test_product_tokenizer.py` | 2 | Surrogate ID encoding/decoding roundtrips (`UP001+`) |

See [`docs/TESTING.md`](docs/TESTING.md) for troubleshooting and CI details.

---

## 🗺️ Roadmap

- [x] Dual-Core ML architecture (Core A Detrended HGBR v2 + Core B Custom CSV RandomForest)
- [x] Autoregressive lag & rolling features (`lag_1`, `rolling_3_mean`, `rolling_7_mean`, `lag_365_residual`, `rolling_mean_365_residual`)
- [x] Strict chronological 80/20 holdout validation (MAE, RMSE, R², WAPE, SMAPE)
- [x] Privacy-preserving `ProductTokenizer` (`UP001+`) & Festival Event Window Engine (30 ML windows, 35 seeded DB festivals)
- [x] Universal Multi-Tenant Stream ETL endpoint (`/api/v1/etl/upload`)
- [x] Zero-DB In-Memory Decoupled Fallback store (`inmemory_store.py`)
- [x] OWASP hardening (PBKDF2 600K, PyJWT, RBAC, CSP, rate limiting, HMAC model cache)
- [x] Single-command local launcher (`server.py`, `run.bat`), Docker container, and GitHub Actions CI + security scans
- [ ] Enforce account lockout (`failed_attempts` / `locked_until`) directly in `/api/login`
- [ ] Multi-tenant row isolation across core POS, products, and inventory tables
- [ ] Shared external state / Redis cache for multi-instance horizontal scaling
- [ ] Async background worker queue for large-scale ML retraining jobs
- [ ] Versioned database schema migrations (e.g., Alembic)

---

## 📄 License

MIT License — see [`LICENSE`](LICENSE) for details.
