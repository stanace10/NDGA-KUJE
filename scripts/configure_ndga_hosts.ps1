$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
  throw "Please run this script from an Administrator PowerShell window."
}

$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"
$entries = @(
  "127.0.0.1 ndgakuje.org",
  "127.0.0.1 student.ndgakuje.org",
  "127.0.0.1 staff.ndgakuje.org",
  "127.0.0.1 it.ndgakuje.org",
  "127.0.0.1 bursar.ndgakuje.org",
  "127.0.0.1 vp.ndgakuje.org",
  "127.0.0.1 principal.ndgakuje.org",
  "127.0.0.1 cbt.ndgakuje.org",
  "127.0.0.1 election.ndgakuje.org"
)

$current = Get-Content -Path $hostsPath -Raw
$missing = @()
foreach ($entry in $entries) {
  if ($current -notmatch "(?m)^\s*$([regex]::Escape($entry))\s*$") {
    $missing += $entry
  }
}

if ($missing.Count -eq 0) {
  Write-Output "NDGA hosts entries are already configured."
} else {
  $appendBlock = "`r`n# NDGA local routing`r`n$($missing -join "`r`n")`r`n"
  $hostsItem = Get-Item -Path $hostsPath
  $wasReadOnly = $hostsItem.IsReadOnly
  if ($wasReadOnly) {
    $hostsItem.IsReadOnly = $false
  }
  try {
    [System.IO.File]::AppendAllText($hostsPath, $appendBlock, [System.Text.Encoding]::ASCII)
    Write-Output "Added $($missing.Count) NDGA hosts entries."
  } finally {
    if ($wasReadOnly) {
      (Get-Item -Path $hostsPath).IsReadOnly = $true
    }
  }
}

ipconfig /flushdns | Out-Null
Write-Output "DNS cache flushed."
Write-Output "Use: http://ndgakuje.org:8000/"
