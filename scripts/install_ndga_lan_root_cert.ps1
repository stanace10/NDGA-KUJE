$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$candidateCertPaths = @(
    (Join-Path $repoRoot "certs\\lan\\ndga-lan-root.crt"),
    (Join-Path $repoRoot "certs\\lan\\ndga-lan.crt")
)
$certPath = $candidateCertPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $certPath) {
    throw "NDGA LAN root certificate not found. Checked: $($candidateCertPaths -join ', ')"
}

$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certPath)
$existing = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
if ($existing) {
    Write-Host "NDGA LAN certificate is already trusted for this Windows user."
    exit 0
}

Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null
Write-Host "NDGA LAN certificate installed successfully for the current Windows user from $certPath."
