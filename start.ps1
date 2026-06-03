# SmartRetail AI — start the dashboard server (Windows)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Checking MySQL setup..."
py -3 backend/setup_database.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Starting server (open the URL printed below)..."
py -3 backend/serve_dashboard.py
