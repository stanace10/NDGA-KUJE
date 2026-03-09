param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath,
    [switch]$SkipFlush,
    [switch]$KeepMedia
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
$managePy = Join-Path $repoRoot "manage.py"

if (-not (Test-Path $pythonExe)) {
    throw "Python virtualenv not found at $pythonExe"
}
if (-not (Test-Path $ArchivePath)) {
    throw "Backup archive not found: $ArchivePath"
}

$args = @($managePy, "restore_ndga", $ArchivePath)
if ($SkipFlush) {
    $args += "--skip-flush"
}
if ($KeepMedia) {
    $args += "--keep-media"
}

& $pythonExe @args
