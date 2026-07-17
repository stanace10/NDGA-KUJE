param(
    [string]$VhdPath = "C:\Users\szubb\AppData\Local\Docker\wsl\disk\docker_data.vhdx",
    [string]$DockerDesktopPath = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
    [string[]]$ContainerNames = @(
        "ndga-celery_worker-1",
        "ndga-celery_beat-1",
        "ndga-web-1",
        "ndga-db-1",
        "ndga-nginx-1",
        "ndga-grafana-1",
        "ndga-prometheus-1",
        "ndga-redis-1"
    ),
    [switch]$SkipRestart
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-VhdSizeGb {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "VHDX file not found: $Path"
    }

    $item = Get-Item $Path
    return [math]::Round($item.Length / 1GB, 2)
}

function Wait-ForDocker {
    param([int]$TimeoutSeconds = 120)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            docker version | Out-Null
            return
        }
        catch {
            Start-Sleep -Seconds 3
        }
    }

    throw "Docker did not become ready within $TimeoutSeconds seconds."
}

function Invoke-DiskPartCompact {
    param([string]$Path)

    $diskPartScript = [System.IO.Path]::GetTempFileName()
    try {
        @(
            "select vdisk file=""$Path"""
            "attach vdisk readonly"
            "compact vdisk"
            "detach vdisk"
            "exit"
        ) | Set-Content -Path $diskPartScript -Encoding ASCII

        diskpart /s $diskPartScript
    }
    finally {
        Remove-Item $diskPartScript -ErrorAction SilentlyContinue
    }
}

if (-not (Test-IsAdministrator)) {
    throw "Run this script from an Administrator PowerShell window."
}

Write-Host "Checking Docker VHDX path..."
$beforeSizeGb = Get-VhdSizeGb -Path $VhdPath
Write-Host "VHDX size before compaction: $beforeSizeGb GB"

$runningContainers = @()
foreach ($containerName in $ContainerNames) {
    $isRunning = docker ps --format "{{.Names}}" | Where-Object { $_ -eq $containerName }
    if ($isRunning) {
        $runningContainers += $containerName
    }
}

if ($runningContainers.Count -gt 0) {
    Write-Host "Stopping NDGA containers..."
    docker stop $runningContainers | Out-Null
}
else {
    Write-Host "No listed NDGA containers are currently running."
}

Write-Host "Shutting down WSL..."
wsl --shutdown
Start-Sleep -Seconds 3

Write-Host "Compacting Docker VHDX..."
try {
    Import-Module Hyper-V -ErrorAction Stop
    Optimize-VHD -Path $VhdPath -Mode Full
}
catch {
    Write-Warning "Optimize-VHD failed. Falling back to diskpart compaction."
    Invoke-DiskPartCompact -Path $VhdPath
}

$afterSizeGb = Get-VhdSizeGb -Path $VhdPath
Write-Host "VHDX size after compaction: $afterSizeGb GB"

if (-not $SkipRestart) {
    if (Test-Path $DockerDesktopPath) {
        Write-Host "Starting Docker Desktop..."
        Start-Process -FilePath $DockerDesktopPath | Out-Null
    }
    else {
        Write-Warning "Docker Desktop executable not found at $DockerDesktopPath"
    }

    Write-Host "Waiting for Docker to become ready..."
    Wait-ForDocker

    if ($runningContainers.Count -gt 0) {
        Write-Host "Restarting previously running NDGA containers..."
        docker start $runningContainers | Out-Null
    }
}
else {
    Write-Host "SkipRestart specified. Leaving Docker stopped."
}

Write-Host "Done."
