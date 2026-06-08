# SmartRetail AI — local run (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

Write-Host "Installing Python dependencies..."
py -3 -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "data\grocery_sales_realistic.csv")) {
    Write-Host "Generating grocery sales dataset..."
    py -3 scripts\generate_grocery_sales.py
}

Write-Host "Checking MySQL setup..."
py -3 backend\setup_database.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Starting server — open the URL printed below in your browser."
Write-Host "Use http://localhost:<PORT>/  (not file:// on dashboard.html)"
Write-Host ""
py -3 backend\serve_dashboard.py
