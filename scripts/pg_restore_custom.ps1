param(
    [Parameter(Mandatory = $true)]
    [string]$DumpPath,
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [switch]$Clean,
    [int]$Jobs = 1
)

$ErrorActionPreference = "Stop"

function Redact-DatabaseUrl {
    param([string]$Url)
    if (-not $Url) {
        return ""
    }
    return ($Url -replace "://([^:@/]+):([^@/]+)@", "://$1:***@")
}

if (-not (Test-Path $DumpPath)) {
    throw "Dump file not found: $DumpPath"
}
if (-not $DatabaseUrl) {
    throw "Database URL is required. Pass -DatabaseUrl or set DATABASE_URL."
}

$pgRestoreCmd = Get-Command pg_restore -ErrorAction SilentlyContinue
if (-not $pgRestoreCmd) {
    throw "pg_restore was not found in PATH. Install PostgreSQL client tools first."
}

$resolvedDump = (Resolve-Path $DumpPath).Path
$jobsValue = [Math]::Max(1, $Jobs)

$args = @(
    "--no-owner",
    "--no-privileges",
    "--dbname=$DatabaseUrl",
    "--jobs=$jobsValue"
)
if ($Clean) {
    $args += @("--clean", "--if-exists")
}
$args += $resolvedDump

Write-Output "Running pg_restore..."
Write-Output ("Source dump: {0}" -f $resolvedDump)
Write-Output ("Target database: {0}" -f (Redact-DatabaseUrl -Url $DatabaseUrl))
& $pgRestoreCmd.Source @args
if ($LASTEXITCODE -ne 0) {
    throw "pg_restore failed with exit code $LASTEXITCODE."
}

Write-Output "Database restore complete."
