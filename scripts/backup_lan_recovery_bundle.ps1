param(
    [string]$OutputRoot = "",
    [int]$KeepBundles = 14,
    [switch]$SkipAppArchive,
    [switch]$SkipMediaArchive,
    [switch]$SkipRuntimeSnapshot,
    [switch]$NoPrune
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

function Resolve-SafeOutputRoot {
    param(
        [string]$RequestedPath,
        [string]$RepoRoot
    )

    if ($RequestedPath) {
        return [System.IO.Path]::GetFullPath($RequestedPath)
    }
    if ($env:NDGA_SAFE_BACKUP_DIR) {
        return [System.IO.Path]::GetFullPath($env:NDGA_SAFE_BACKUP_DIR)
    }
    if ($env:OneDrive -and (Test-Path $env:OneDrive)) {
        return [System.IO.Path]::GetFullPath((Join-Path $env:OneDrive "NDGA Backups\lan-node"))
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot "backups\lan-node"))
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

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 8
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Get-FileMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$BundleRoot
    )

    $item = Get-Item $Path
    $hash = (Get-FileHash -Algorithm SHA256 -Path $Path).Hash.ToLowerInvariant()
    $bundleResolved = [System.IO.Path]::GetFullPath($BundleRoot)
    $itemResolved = [System.IO.Path]::GetFullPath($item.FullName)
    if ($itemResolved.StartsWith($bundleResolved, [System.StringComparison]::OrdinalIgnoreCase)) {
        $relativePath = $itemResolved.Substring($bundleResolved.Length).TrimStart("\", "/")
    }
    else {
        $relativePath = $item.Name
    }
    $relativePath = $relativePath -replace "\\", "/"
    return [ordered]@{
        relative_path = $relativePath
        size_bytes = [int64]$item.Length
        sha256 = $hash
    }
}

function Remove-OldBundles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootPath,
        [int]$KeepCount = 14
    )

    if ($KeepCount -lt 1) {
        return
    }
    $oldBundles = Get-ChildItem -Path $RootPath -Directory -ErrorAction SilentlyContinue |
        Sort-Object CreationTimeUtc -Descending |
        Select-Object -Skip $KeepCount
    foreach ($bundle in $oldBundles) {
        Remove-Item -Path $bundle.FullName -Recurse -Force
    }
}

$repoRoot = Get-RepoRoot
$envFilePath = Join-Path $repoRoot ".env.lan"
$envMap = Get-EnvFileMap -EnvFilePath $envFilePath
$dbName = if ($envMap.ContainsKey("DB_NAME")) { $envMap["DB_NAME"] } else { "ndga" }
$dbUser = if ($envMap.ContainsKey("DB_USER")) { $envMap["DB_USER"] } else { "ndga" }
$dbPassword = if ($envMap.ContainsKey("DB_PASSWORD")) { $envMap["DB_PASSWORD"] } else { "ndga" }
$safeOutputRoot = Resolve-SafeOutputRoot -RequestedPath $OutputRoot -RepoRoot $repoRoot
$storageMode = if ($safeOutputRoot -like "*OneDrive*") { "onedrive" } else { "local" }
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$bundleRoot = Join-Path $safeOutputRoot $stamp
$postgresDir = Join-Path $bundleRoot "postgres"
$mediaDir = Join-Path $bundleRoot "media"
$appDir = Join-Path $bundleRoot "app"
$opsDir = Join-Path $bundleRoot "ops"

New-Item -ItemType Directory -Path $postgresDir -Force | Out-Null
New-Item -ItemType Directory -Path $mediaDir -Force | Out-Null
New-Item -ItemType Directory -Path $appDir -Force | Out-Null
New-Item -ItemType Directory -Path $opsDir -Force | Out-Null

Push-Location $repoRoot
try {
    Invoke-DockerCompose -ComposeArgs @("up", "-d", "db", "redis", "web") | Out-Null

    $dbContainerId = Get-ComposeContainerId -ServiceName "db"
    $webContainerId = Get-ComposeContainerId -ServiceName "web"

    $remoteDumpPath = "/tmp/ndga_lan_$stamp.dump"
    $localDumpPath = Join-Path $postgresDir "ndga_lan_$stamp.dump"
    $dumpCommand = @(
        "PGPASSWORD=" + (ConvertTo-ShLiteral $dbPassword),
        "pg_dump",
        "-U", (ConvertTo-ShLiteral $dbUser),
        "-d", (ConvertTo-ShLiteral $dbName),
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-f", (ConvertTo-ShLiteral $remoteDumpPath)
    ) -join " "
    Invoke-DockerCompose -ComposeArgs @("exec", "-T", "db", "sh", "-lc", $dumpCommand) | Out-Null
    & docker cp "${dbContainerId}:$remoteDumpPath" $localDumpPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "docker cp failed while copying PostgreSQL dump."
    }
    Invoke-DockerCompose -ComposeArgs @("exec", "-T", "db", "rm", "-f", $remoteDumpPath) | Out-Null

    $mediaArchivePath = ""
    if (-not $SkipMediaArchive) {
        $remoteMediaPath = "/tmp/ndga_media_$stamp.tar.gz"
        $mediaArchivePath = Join-Path $mediaDir "ndga_media_$stamp.tar.gz"
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "sh", "-lc", "mkdir -p /app/media && tar -czf $remoteMediaPath -C /app/media .") | Out-Null
        & docker cp "${webContainerId}:$remoteMediaPath" $mediaArchivePath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed while copying media archive."
        }
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "rm", "-f", $remoteMediaPath) | Out-Null
    }

    $appArchivePath = ""
    if (-not $SkipAppArchive) {
        $remoteAppDir = "/tmp/ndga_app_backup_$stamp"
        $appBackupOutput = Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "python", "manage.py", "backup_ndga", "--output-dir", $remoteAppDir)
        $appBackupText = ($appBackupOutput | Out-String)
        $remoteAppArchive = ([regex]::Match($appBackupText, "Backup created:\s*(.+)", "IgnoreCase")).Groups[1].Value.Trim()
        if (-not $remoteAppArchive) {
            throw "Could not resolve remote NDGA app archive path from backup command output."
        }
        $appArchiveName = Split-Path -Leaf $remoteAppArchive
        $appArchivePath = Join-Path $appDir $appArchiveName
        & docker cp "${webContainerId}:$remoteAppArchive" $appArchivePath | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "docker cp failed while copying app backup archive."
        }
        Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "rm", "-rf", $remoteAppDir) | Out-Null
    }

    $runtimeSnapshotPath = ""
    $schoolSnapshotPath = ""
    if (-not $SkipRuntimeSnapshot) {
        $runtimeSnapshotPath = Join-Path $opsDir "ops_runtime_snapshot.json"
        $runtimeJson = Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "python", "manage.py", "ops_runtime_snapshot") | Out-String
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($runtimeSnapshotPath, $runtimeJson.Trim(), $utf8NoBom)

        $schoolSnapshotPath = Join-Path $opsDir "school_snapshot.json"
        $pythonSnapshot = "import json, os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.prod'); django.setup(); from apps.dashboard.views import _it_enrollment_snapshot; from apps.results.models import ResultSheet, StudentSubjectScore; from apps.cbt.models import Exam, ExamAttempt, QuestionBank, Question, ExamQuestion; from apps.setup_wizard.services import get_setup_state; enrollment = _it_enrollment_snapshot(); setup_state = get_setup_state(); payload = {'setup_state': setup_state.state, 'current_session': setup_state.current_session.name if setup_state.current_session_id else '', 'current_term': setup_state.current_term.name if setup_state.current_term_id else '', 'student_count': int(sum(int(row.get('count', 0) or 0) for row in enrollment.get('class_rows', []))), 'result_sheet_count': ResultSheet.objects.count(), 'score_count': StudentSubjectScore.objects.count(), 'exam_count': Exam.objects.count(), 'exam_attempt_count': ExamAttempt.objects.count(), 'exam_question_count': ExamQuestion.objects.count(), 'question_bank_count': QuestionBank.objects.count(), 'question_count': Question.objects.count()}; print(json.dumps(payload, indent=2, sort_keys=True))"
        $schoolJson = Invoke-DockerCompose -ComposeArgs @("exec", "-T", "web", "python", "-c", $pythonSnapshot) | Out-String
        [System.IO.File]::WriteAllText($schoolSnapshotPath, $schoolJson.Trim(), $utf8NoBom)
    }

    $gitCommit = ""
    try {
        $gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
    }
    catch {
        $gitCommit = ""
    }

    $manifest = [ordered]@{
        generated_at = (Get-Date).ToString("o")
        storage_mode = $storageMode
        storage_root = $safeOutputRoot
        bundle_root = $bundleRoot
        keep_bundles = [Math]::Max(1, $KeepBundles)
        git_commit = $gitCommit
        files = @()
    }

    $filesToRecord = @($localDumpPath)
    if ($mediaArchivePath) {
        $filesToRecord += $mediaArchivePath
    }
    if ($appArchivePath) {
        $filesToRecord += $appArchivePath
    }
    if ($runtimeSnapshotPath) {
        $filesToRecord += $runtimeSnapshotPath
    }
    if ($schoolSnapshotPath) {
        $filesToRecord += $schoolSnapshotPath
    }
    foreach ($path in $filesToRecord) {
        $manifest.files += Get-FileMetadata -Path $path -BundleRoot $bundleRoot
    }

    Write-JsonFile -Path (Join-Path $bundleRoot "manifest.json") -Payload $manifest

    if (-not $NoPrune) {
        Remove-OldBundles -RootPath $safeOutputRoot -KeepCount ([Math]::Max(1, $KeepBundles))
    }

    Write-Output "LAN recovery bundle created successfully."
    Write-Output ("Bundle path: {0}" -f $bundleRoot)
    Write-Output ("Storage mode: {0}" -f $storageMode)
    Write-Output ("PostgreSQL dump: {0}" -f $localDumpPath)
    if ($mediaArchivePath) {
        Write-Output ("Media archive: {0}" -f $mediaArchivePath)
    }
    if ($appArchivePath) {
        Write-Output ("App archive: {0}" -f $appArchivePath)
    }
    if ($runtimeSnapshotPath) {
        Write-Output ("Runtime snapshot: {0}" -f $runtimeSnapshotPath)
    }
    if ($schoolSnapshotPath) {
        Write-Output ("School snapshot: {0}" -f $schoolSnapshotPath)
    }
    Write-Output ("Manifest: {0}" -f (Join-Path $bundleRoot "manifest.json"))
}
finally {
    Pop-Location
}
