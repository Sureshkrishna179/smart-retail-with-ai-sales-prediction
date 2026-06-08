# SmartRetail AI — company test runner (Windows)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Installing dev dependencies..."
py -3 -m pip install -q -r requirements-dev.txt

if (-not (Test-Path "data\grocery_sales_realistic.csv")) {
    Write-Host "Generating grocery sales data..."
    py -3 scripts\generate_grocery_sales.py
}

Write-Host ""
Write-Host "Running unit tests..."
py -3 -m pytest tests -m "not integration" --cov=backend --cov-report=term-missing

$runIntegration = $env:RUN_INTEGRATION_TESTS -eq "1"
if ($runIntegration) {
    Write-Host ""
    Write-Host "Running integration tests (MySQL required)..."
    py -3 -m pytest tests -m integration
} else {
    Write-Host ""
    Write-Host "Skipped integration tests. Set RUN_INTEGRATION_TESTS=1 to include MySQL/API DB checks."
}

Write-Host ""
Write-Host "Done."
