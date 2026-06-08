"""Smoke tests: project layout, dependencies, and data files."""

from pathlib import Path

import pytest


def test_project_structure(project_root: Path):
    required = [
        "backend/serve_dashboard.py",
        "backend/setup_database.py",
        "backend/db_config.py",
        "backend/paths.py",
        "frontend/dashboard.html",
        "frontend/app.js",
        "requirements.txt",
        "deploy/Dockerfile",
        "deploy/docker-compose.yml",
        "scripts/start.ps1",
        ".env.example",
        "LICENSE",
        "CONTRIBUTING.md",
    ]
    for rel in required:
        assert (project_root / rel).is_file(), f"Missing required file: {rel}"


def test_grocery_sales_csv_exists_and_valid(project_root: Path):
    path = project_root / "data" / "grocery_sales_realistic.csv"
    assert path.is_file(), "Missing data/grocery_sales_realistic.csv"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "Date,Product,Sales_Qty"
    assert len(lines) > 9000, "Expected full-year multi-SKU grocery data"


def test_sample_sales_csv_header(project_root: Path):
    path = project_root / "data" / "samples" / "sample_sales_data.csv"
    assert path.is_file()
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first == "Date,Product,Sales_Qty"


@pytest.mark.parametrize(
    "module_name",
    ["pandas", "numpy", "sklearn", "jwt", "dotenv", "mysql.connector"],
)
def test_core_dependencies_import(module_name: str):
    __import__(module_name)


def test_serve_dashboard_imports():
    import serve_dashboard  # noqa: F401 — backend on pythonpath

    assert hasattr(serve_dashboard, "is_festival_period")
    assert hasattr(serve_dashboard, "train_model_from_csv")
