param(
    [string]$OutputDir = "backups"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$managePy = Join-Path $repoRoot "manage.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtualenv not found at $pythonExe"
}

& $pythonExe $managePy backup_ndga --output-dir $OutputDir
