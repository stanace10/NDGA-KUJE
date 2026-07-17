$ErrorActionPreference = "SilentlyContinue"

$root = Split-Path -Parent $PSScriptRoot
$pgBin = "C:\Program Files\PostgreSQL\16\bin"
$pgData = Join-Path $root ".postgres\data"

if (Test-Path $pgData) {
  & "$pgBin\pg_ctl.exe" -D $pgData stop -m fast | Out-Null
}

$redisService = Get-Service -Name "Redis" -ErrorAction SilentlyContinue
if ($redisService -and $redisService.Status -eq "Running") {
  Stop-Service -Name "Redis"
}

Write-Output "Stage 0 services stopped."

