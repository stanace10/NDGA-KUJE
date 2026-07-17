param(
    [string]$ComposeFile = "docker-compose.lan.yml",
    [string]$EnvFile = ".env.lan",
    [string]$WebService = "web",
    [string]$OutputDir = "backups\\standby"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposePath = Join-Path $RepoRoot $ComposeFile
$EnvPath = Join-Path $RepoRoot $EnvFile
$OutputPath = Join-Path $RepoRoot $OutputDir

if (-not (Test-Path $ComposePath)) {
    throw "Compose file not found: $ComposePath"
}
if (-not (Test-Path $EnvPath)) {
    throw "Env file not found: $EnvPath"
}

New-Item -ItemType Directory -Force $OutputPath | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$localDir = Join-Path $OutputPath $stamp
New-Item -ItemType Directory -Force $localDir | Out-Null

$composeArgs = @("--env-file", $EnvPath, "-f", $ComposePath)
$remoteDir = "/tmp/ndga_standby_$stamp"

$backupOutput = docker compose @composeArgs exec -T $WebService python manage.py backup_ndga --output-dir $remoteDir
$backupText = ($backupOutput | Out-String)
$match = [regex]::Match($backupText, "Backup created:\s*(.+)", "IgnoreCase")
if (-not $match.Success) {
    throw "Could not resolve backup archive path from backup_ndga output."
}

$remoteArchive = $match.Groups[1].Value.Trim()
$containerId = (docker compose @composeArgs ps -q $WebService).Trim()
if (-not $containerId) {
    throw "Could not resolve container id for service '$WebService'."
}

docker cp "${containerId}:$remoteArchive" "$localDir\"

$runtimeSnapshotPath = Join-Path $localDir "ops_runtime_snapshot.json"
(docker compose @composeArgs exec -T $WebService python manage.py ops_runtime_snapshot) | Out-File -Encoding utf8 $runtimeSnapshotPath

$manifestPath = Join-Path $localDir "manifest.txt"
@(
    "created_at=$stamp"
    "compose_file=$ComposeFile"
    "env_file=$EnvFile"
    "web_service=$WebService"
    "archive_path=$remoteArchive"
) | Out-File -Encoding utf8 $manifestPath

Write-Output "Standby backup created: $localDir"
