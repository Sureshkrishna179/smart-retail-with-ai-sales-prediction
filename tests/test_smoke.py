"""Smoke tests: project layout, dependencies, and data files."""

from pathlib import Path

import pytest


def test_project_structure(project_root: Path):
    required = [
        "src/smartretail/server.py",
        "src/smartretail/api/handlers/ml.py",
        "src/smartretail/config.py",
        "frontend/dashboard.html",
        "frontend/app.js",
        "requirements.txt",
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


def test_smartretail_ml_imports():
    from smartretail.api.handlers import ml  # noqa: F401

    assert hasattr(ml, "is_festival_period")
    assert hasattr(ml, "train_model_from_csv")
