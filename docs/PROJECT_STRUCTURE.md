# Project Structure

```
smartretail-ai/
├── .github/
│   └── workflows/
│       └── ci.yml                     # Automated CI pipeline (lint + pytest)
├── docs/
│   ├── COMPANY_STANDARDS.md          # Architecture & coding guidelines
│   ├── DEPLOYMENT.md                 # Production deployment guide
│   ├── PROJECT_STRUCTURE.md          # Project architectural layout
│   └── TESTING.md                    # Testing & coverage guidelines
├── files/
│   ├── products.csv                  # 100 grocery SKU catalog
│   ├── sales_data.csv                # 913k-row benchmark dataset
│   ├── stores.csv                    # Store branch metadata
│   ├── tn_calendar_2026.csv          # 29 Indian festival calendar
│   └── output/                       # Pre-trained models & validation reports
├── frontend/
│   ├── css/
│   │   └── styles.css                # Dual-Theme CSS design tokens
│   ├── js/
│   │   └── main.js                   # SPA reactive business logic & Chart.js
│   ├── dashboard.html                # High-density operational SPA dashboard
│   └── README.md                     # Frontend design specification
├── scripts/
│   ├── check_db.py                   # Database connection diagnostic utility
│   ├── forecast_lgbm.py              # Offline benchmark forecasting pipeline
│   ├── generate_grocery_sales.py     # Synthetic data generator
│   ├── start.bat / start.ps1         # Windows launchers
│   └── run_tests.sh / run_tests.ps1  # Test runner scripts
├── src/
│   ├── paths.py                      # Root path constants
│   └── smartretail/
│       ├── api/                      # REST handlers, validators, middleware
│       │   ├── handlers/             # Endpoint implementations (ML, Sales, etc.)
│       │   ├── middleware/           # Rate limiting, auth, security headers
│       │   └── validators/           # Input validation schemas
│       ├── db/                       # MySQL pool & migrations
│       │   ├── connection.py         # Threaded connection pool
│       │   └── migrations/           # Database setup and schema DDL
│       ├── etl/                      # In-memory ETL ingestion pipeline
│       ├── ml/                       # Dual-Core ML forecasting engine
│       │   ├── predictor.py          # Dual-Core prediction router
│       │   ├── product_tokenizer.py  # Two-Way Surrogate Tokenizer
│       │   ├── trainer.py            # HGBR & Random Forest trainers
│       │   └── cache.py              # Model caching
│       ├── config.py                 # Environment configuration (Pydantic)
│       └── server.py                 # Zero-dependency HTTP server (port 8765)
├── tests/                            # 43 automated unit & integration tests
├── .editorconfig
├── .env.example                      # Safe credential template
├── .gitignore                        # Hardened ignore rules
├── CONTRIBUTING.md
├── LICENSE                           # MIT License
├── Makefile                          # Developer command shortcuts
├── pyproject.toml                    # Modern Python package spec
├── requirements.txt                  # Production dependencies
├── requirements-dev.txt              # Testing & development dependencies
└── README.md                         # Project documentation & benchmark metrics
```

## Conventions

- **Config**: `.env` at repo root only (never committed, see `.env.example`).
- **Imports**: Modules use absolute package imports: `from smartretail.ml import ...`.
- **Run from root**: `python -m smartretail.server` with `PYTHONPATH=src` (default port `8765`).
