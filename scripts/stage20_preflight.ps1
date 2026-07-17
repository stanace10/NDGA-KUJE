$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$pythonCmd = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Output "Running Stage 20 preflight checks with production settings..."

& $pythonCmd manage.py check --deploy --settings=core.settings.prod
if ($LASTEXITCODE -ne 0) { throw "check --deploy failed" }

& $pythonCmd manage.py verify_stage20 --settings=core.settings.prod
if ($LASTEXITCODE -ne 0) { throw "verify_stage20 failed" }

Write-Output "Stage 20 preflight passed."
