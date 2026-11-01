#!/usr/bin/env bash
# SmartRetail AI — company test runner (Linux/macOS)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "Installing dev dependencies..."
python3 -m pip install -q -r requirements-dev.txt

if [[ ! -f data/grocery_sales_realistic.csv ]]; then
  echo "Generating grocery sales data..."
  python3 scripts/generate_grocery_sales.py
fi

echo ""
echo "Running unit tests..."
python3 -m pytest tests -m "not integration" --cov=src/smartretail --cov-report=term-missing

if [[ "${RUN_INTEGRATION_TESTS:-}" == "1" ]]; then
  echo ""
  echo "Running integration tests (MySQL required)..."
  python3 -m pytest tests -m integration
else
  echo ""
  echo "Skipped integration tests. Set RUN_INTEGRATION_TESTS=1 to include MySQL/API DB checks."
fi

echo ""
echo "Done."
