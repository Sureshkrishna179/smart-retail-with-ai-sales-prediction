# Project structure

```
smartretail-ai/
├── .github/workflows/     # CI (pytest on push)
├── backend/               # Python API, ML, database
│   ├── paths.py           # Root paths (single source of truth)
│   ├── serve_dashboard.py # HTTP server + REST API
│   ├── setup_database.py  # Schema + seed
│   ├── db_config.py       # MySQL pool
│   ├── ml_cache.py        # Model persistence
│   └── legacy/            # Optional Streamlit app
├── frontend/              # SPA (HTML/CSS/JS)
├── data/                  # CSV datasets + runtime ML cache
│   └── samples/           # Small demo CSV
├── deploy/                # Docker, Render, Railway configs
├── docs/                  # Standards, testing, deployment
├── scripts/               # Start, tests, data generator
├── tests/                 # pytest suite
├── requirements.txt       # Production deps
├── requirements-dev.txt   # Dev + test deps
├── pyproject.toml         # Project metadata + pytest config
├── Dockerfile             # → see deploy/Dockerfile
├── start.ps1 / start.bat  # Thin launchers (call scripts/)
└── README.md
```

## Conventions

- **Config**: `.env` at repo root only (never committed).
- **Imports**: Backend modules use `from paths import PROJECT_ROOT, ...`.
- **Run from root**: `python backend/serve_dashboard.py` with cwd = project root.
