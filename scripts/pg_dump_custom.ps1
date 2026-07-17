param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$OutputDir = "backups\postgres",
    [string]$Tag = "ndga",
    [switch]$SchemaOnly
)

$ErrorActionPreference = "Stop"

function Redact-DatabaseUrl {
    param([string]$Url)
    if (-not $Url) {
        return ""
    }
    return ($Url -replace "://([^:@/]+):([^@/]+)@", "://$1:***@")
}

if (-not $DatabaseUrl) {
    throw "Database URL is required. Pass -DatabaseUrl or set DATABASE_URL."
}

$pgDumpCmd = Get-Command pg_dump -ErrorAction SilentlyContinue
if (-not $pgDumpCmd) {
    throw "pg_dump was not found in PATH. Install PostgreSQL client tools first."
}

New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dumpName = "{0}_{1}.dump" -f $Tag, $stamp
$dumpPath = Join-Path $OutputDir $dumpName

$args = @(
    "--format=custom",
    "--no-owner",
    "--no-privileges",
    "--dbname=$DatabaseUrl",
    "--file=$dumpPath"
)
if ($SchemaOnly) {
    $args += "--schema-only"
}

Write-Output "Running pg_dump custom backup..."
Write-Output ("Target file: {0}" -f (Resolve-Path $OutputDir))
& $pgDumpCmd.Source @args
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump failed with exit code $LASTEXITCODE."
}

$manifestPath = Join-Path $OutputDir ("{0}_{1}.json" -f $Tag, $stamp)
$manifest = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    dump_file = $dumpName
    schema_only = [bool]$SchemaOnly
    database_url = (Redact-DatabaseUrl -Url $DatabaseUrl)
    command = "pg_dump -Fc --no-owner --no-privileges"
}
$manifest | ConvertTo-Json -Depth 4 | Out-File -FilePath $manifestPath -Encoding utf8

Write-Output ("Database export complete: {0}" -f (Resolve-Path $dumpPath))
Write-Output ("Manifest written: {0}" -f (Resolve-Path $manifestPath))
