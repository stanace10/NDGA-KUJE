$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$pgBinCandidates = @()
if ($env:NDGA_POSTGRES_BIN) {
  $pgBinCandidates += $env:NDGA_POSTGRES_BIN
}
$pgBinCandidates += @(
  (Join-Path $root ".tools\PostgreSQL\16\bin"),
  "$env:LOCALAPPDATA\Programs\PostgreSQL\16\bin",
  "C:\Program Files\PostgreSQL\16\bin"
)
$pgBin = $pgBinCandidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
$pgData = Join-Path $root ".postgres\data"
$pgLog = Join-Path $root ".postgres\postgres.log"
$pwFile = Join-Path $root ".postgres\pgpass.txt"
$pgPort = if ($env:NDGA_POSTGRES_PORT) { [int]$env:NDGA_POSTGRES_PORT } else { 5433 }
if ($pgPort -le 0 -or $pgPort -gt 65535) {
  throw "Invalid NDGA_POSTGRES_PORT value: $pgPort"
}

function Test-TcpPort($HostName, $Port, $TimeoutMs = 1000) {
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    $connected = $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    if ($connected -and $client.Connected) {
      $client.EndConnect($async) | Out-Null
      $client.Close()
      return $true
    }
    $client.Close()
    return $false
  } catch {
    return $false
  }
}

if (!$pgBin) {
  $checked = ($pgBinCandidates | Where-Object { $_ }) -join ", "
  throw "PostgreSQL binaries not found. Checked: $checked. Install PostgreSQL 16 locally, set NDGA_POSTGRES_BIN, or extract portable binaries into .tools\PostgreSQL\16\bin before using python manage.py runserver."
}

if (!(Test-Path $pgData)) {
  New-Item -ItemType Directory -Force (Split-Path -Parent $pgData) | Out-Null
  "ndga" | Set-Content -Path $pwFile
  & "$pgBin\initdb.exe" -D $pgData -U ndga -A scram-sha-256 --pwfile=$pwFile | Out-Null
}

$redisService = Get-Service -Name "Redis" -ErrorAction SilentlyContinue
$redisRunning = $false
if ($redisService) {
  if ($redisService.Status -ne "Running") {
    Start-Service -Name "Redis"
    $redisService.Refresh()
  }
  $redisRunning = $redisService.Status -eq "Running"
} else {
  $redisRunning = Test-TcpPort -HostName "127.0.0.1" -Port 6379
}

$pgStatus = & "$pgBin\pg_ctl.exe" -D $pgData status
if ($LASTEXITCODE -ne 0) {
  & "$pgBin\pg_ctl.exe" -D $pgData -l $pgLog -o "-p $pgPort" start | Out-Null
}

$env:PGPASSWORD = "ndga"
$dbExists = & "$pgBin\psql.exe" -U ndga -h 127.0.0.1 -p $pgPort -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='ndga';"
if ($LASTEXITCODE -ne 0) {
  throw "Unable to connect to NDGA local PostgreSQL on port $pgPort. Check .postgres\\postgres.log."
}
if ($dbExists -and $dbExists.Trim() -ne "1") {
  & "$pgBin\createdb.exe" -U ndga -h 127.0.0.1 -p $pgPort ndga | Out-Null
}

Write-Output "Stage 0 services started."
Write-Output "- PostgreSQL: 127.0.0.1:$pgPort (user=ndga, db=ndga)"
if ($redisRunning) {
  Write-Output "- Redis: 127.0.0.1:6379"
} else {
  Write-Output "- Redis: not running (optional for basic runserver; required for cache/channels/celery features)"
}
