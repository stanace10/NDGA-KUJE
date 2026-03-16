param(
    [Parameter(Mandatory = $true)]
    [string]$BundlePath,
    [switch]$SkipMedia,
    [switch]$SkipReadinessCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-RepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Get-EnvFileMap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$EnvFilePath
    )

    $values = @{}
    foreach ($line in Get-Content $EnvFilePath) {
        $trimmed = $line.Trim()
        if (-not $trimmed) {
            continue
        }
        if ($trimmed.StartsWith("#")) {
            continue
        }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }
        $values[$parts[0].Trim()] = $parts[1].Trim()
    }
    return $values
}

function ConvertTo-ShLiteral {
    param(
        [AllowEmptyString()]
        [string]$Value
    )

    return "'" + $Value + "'"
}

function Invoke-DockerCompose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ComposeArgs
    )

    & docker compose --env-file .env.lan -f docker-compose.lan.yml @ComposeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($ComposeArgs -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Get-ComposeContainerId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ServiceName
    )

    $containerId = (Invoke-DockerCompose -ComposeArgs @("ps", "-q", $ServiceName) | Select-Object -Last 1).Trim()
    if (-not $containerId) {
        throw "Could not resolve container id for service '$ServiceName'."
    }
    return $containerId
}

$repoRoot = Get-RepoRoot
$envFilePath = Join-Path $repoRoot ".env.lan"
$envMap = Get-EnvFileMap -EnvFilePath $envFilePath
$dbName = if ($envMap.ContainsKey("DB_NAME")) { $envMap["DB_NAME"] } else { "ndga" }
$dbUser = if ($envMap.ContainsKey("DB_USER")) { $envMap["DB_USER"] } else { "ndga" }
$dbPassword = if ($envMap.ContainsKey("DB_PASSWORD")) { $envMap["DB_PASSWORD"] } else { "ndga" }
$resolvedBundlePath = (Resolve-Path $BundlePath).Path
$postgresDump = Get-ChildItem -Path (Join-Path $resolvedBundlePath "postgres") -Filter *.dump -File -ErrorAction SilentlyContinue | Select-Object -First 1
$mediaArchive = Get-ChildItem -Path (Join-Path $resolvedBundlePath "media") -Filter *.tar.gz -File -ErrorAction SilentlyContinue | Select-Object -First 1
$appArchive = Get-ChildItem -Path (Join-Path $resolvedBundlePath "app") -Filter *.zip -File -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $postgresDump -and -not $appArchive) {
    throw "Bundle is missing both PostgreSQL dump and NDGA app archive. Nothing to restore."
}

Push-Location $repoRoot
try {
    Invoke-DockerCompose -ComposeArgs @("up", "-d", "db", "redis") | Out-Null
    Invoke-DockerCompose -ComposeArgs @("stop", "nginx", "web", "celery_worker", "celery_beat") | Out-Null

    if ($postgresDump) {
        $dbContainerId = Get-ComposeContainerId -ServiceName "db"
        $remoteDumpPath = "/tmp/restore_ndga_lan.dump"
        & docker cp $postgresDump.FullName "${dbContainerId}:$remoteDumpPath" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed while uploading PostgreSQL dump to the db container."
        }

        $restoreCommand = @(
            "PGPASSWORD=" + (ConvertTo-ShLiteral $dbPassword),
            "pg_restore",
            "--clean",
            "--if-exists",
            "--exit-on-error",
            "--no-owner",
            "--no-privileges",
            "-U", (ConvertTo-ShLiteral $dbUser),
            "-d", (ConvertTo-ShLiteral $dbName),
            (ConvertTo-ShLiteral $remoteDumpPath)
        ) -join " "
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "db", "sh", "-lc", $restoreCommand) | Out-Null
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "db", "rm", "-f", $remoteDumpPath) | Out-Null
    }

    Invoke-DockerCompose -ComposeArgs @("up", "-d", "web") | Out-Null
    $webContainerId = Get-ComposeContainerId -ServiceName "web"

    if ($mediaArchive -and -not $SkipMedia) {
        $remoteMediaPath = "/tmp/restore_ndga_media.tar.gz"
        & docker cp $mediaArchive.FullName "${webContainerId}:$remoteMediaPath" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed while uploading media archive to the web container."
        }
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "sh", "-lc", "rm -rf /app/media/* && mkdir -p /app/media && tar -xzf $remoteMediaPath -C /app/media") | Out-Null
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "rm", "-f", $remoteMediaPath) | Out-Null
    }
    elseif (-not $postgresDump -and $appArchive) {
        $remoteArchivePath = "/tmp/restore_ndga_bundle.zip"
        & docker cp $appArchive.FullName "${webContainerId}:$remoteArchivePath" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed while uploading NDGA app archive to the web container."
        }
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "python", "manage.py", "restore_ndga", $remoteArchivePath) | Out-Null
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "rm", "-f", $remoteArchivePath) | Out-Null
    }

    Invoke-DockerCompose -ComposeArgs @("up", "-d", "celery_worker", "celery_beat", "nginx") | Out-Null
    Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "python", "manage.py", "check") | Out-Null

    if (-not $SkipReadinessCheck) {
        $ready = Invoke-WebRequest -Uri "http://127.0.0.1/ops/readyz/" -UseBasicParsing -TimeoutSec 30
        Write-Output ("Readyz status: {0}" -f [int]$ready.StatusCode)
        Write-Output $ready.Content
    }

    Write-Output "LAN recovery bundle restored successfully."
    Write-Output ("Bundle path: {0}" -f $resolvedBundlePath)
    if ($postgresDump) {
        Write-Output ("PostgreSQL dump restored: {0}" -f $postgresDump.FullName)
    }
    if ($mediaArchive -and -not $SkipMedia) {
        Write-Output ("Media archive restored: {0}" -f $mediaArchive.FullName)
    }
    elseif ($SkipMedia) {
        Write-Output "Media restore was skipped."
    }
    elseif ($appArchive -and -not $postgresDump) {
        Write-Output ("Fallback NDGA archive restored: {0}" -f $appArchive.FullName)
    }
}
finally {
    Pop-Location
}
