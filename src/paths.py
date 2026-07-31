"""
paths.py — Centralized project path definitions for SmartRetail AI
"""

from pathlib import Path

# Root directory of the repository (parent of src)
SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent

ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
GROCERY_CSV = DATA_DIR / "grocery_sales_realistic.csv"
MODEL_CACHE_DIR = DATA_DIR / "ml_models"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
