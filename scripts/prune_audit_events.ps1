$ErrorActionPreference = "Stop"

param(
  [int]$Days = 2555,
  [switch]$DryRun
)

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$pythonCmd = if (Test-Path $venvPython) { $venvPython } else { "python" }

$args = @("manage.py", "prune_audit_events", "--days", "$Days")
if ($DryRun) {
  $args += "--dry-run"
}

& $pythonCmd @args
if ($LASTEXITCODE -ne 0) {
  throw "Audit prune command failed."
}
