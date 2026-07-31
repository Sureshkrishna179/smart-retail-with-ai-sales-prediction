# SmartRetail AI — local run (Windows PowerShell)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

# Determine Python executable (prefer .venv Python if available, fallback to py -3)
$PyExec = "py -3"
if (Test-Path "$Root\.venv\Scripts\python.exe") {
    $PyExec = "$Root\.venv\Scripts\python.exe"
}

Write-Host "Installing Python dependencies..."
& $PyExec -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path "data\grocery_sales_realistic.csv")) {
    Write-Host "Generating grocery sales dataset..."
    & $PyExec scripts\generate_grocery_sales.py
}

Write-Host "Checking MySQL setup..."
$env:PYTHONPATH="src"
& $PyExec src\smartretail\db\migrations\setup_database.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Starting server..."
Write-Host "Open http://localhost:8765/ in your browser."
Write-Host ""
& $PyExec -m smartretail.server
