.PHONY: install install-dev test run setup-db data docker-up docker-down package

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt

data:
	python scripts/generate_grocery_sales.py

setup-db:
	python src/smartretail/db/migrations/setup_database.py

run: setup-db
	python -m src.smartretail.server

test:
	python scripts/generate_grocery_sales.py
	pytest tests -m "not integration" --cov=src/smartretail

test-all:
	RUN_INTEGRATION_TESTS=1 pytest tests

docker-up:
	docker compose -f deploy/docker-compose.yml up --build

docker-down:
	docker compose -f deploy/docker-compose.yml down

# LOW-03: Safe packaging — never include .env or secrets in release archives.
# Usage: make package   → creates dist/smartretail-release.zip
dist: package
package:
	@echo "Building release archive (secrets excluded)..."
	@mkdir -p dist
	@zip -r dist/smartretail-release.zip . \
	  -x ".env" \
	  -x ".env.*" \
	  -x ".venv/*" \
	  -x ".git/*" \
	  -x ".github/*" \
	  -x "__pycache__/*" \
	  -x "*/__pycache__/*" \
	  -x "*.pyc" \
	  -x "*.pkl" \
	  -x "*.sig" \
	  -x "dist/*" \
	  -x "*.db" \
	  -x "*.sqlite" \
	  -x "logs/*" \
	  -x ".pytest_cache/*" \
	  -x "data/ml_models*"
	@echo "Release archive created: dist/smartretail-release.zip"
	@echo "Verifying .env is excluded..."
	@! unzip -l dist/smartretail-release.zip | grep -E "^\s*[0-9].*\.env$$" && echo "✅ .env excluded OK" || (echo "❌ WARNING: .env found in archive!" && exit 1)
