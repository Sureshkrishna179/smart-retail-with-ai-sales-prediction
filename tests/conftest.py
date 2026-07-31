"""Shared pytest fixtures for SmartRetail AI."""

import os
import sys
from pathlib import Path

import pytest

SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture
def project_root():
    return PROJECT_ROOT


@pytest.fixture
def grocery_csv_path(project_root):
    path = project_root / "data" / "grocery_sales_realistic.csv"
    if not path.exists():
        pytest.skip("Run scripts/generate_grocery_sales.py first")
    return path


@pytest.fixture
def grocery_csv_text(grocery_csv_path):
    return grocery_csv_path.read_text(encoding="utf-8")


def mysql_available():
    """Return True if MySQL is reachable with project .env settings."""
    try:
        from smartretail.db.connection import get_connection
        conn = get_connection()
        if conn and conn.is_connected():
            conn.close()
            return True
        return False
    except Exception:
        return False


@pytest.fixture
def requires_mysql():
    if not mysql_available():
        pytest.skip("MySQL not available — set DB_* in .env for integration tests")
