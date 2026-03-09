param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRemote,
    [string]$SourcePath = "",
    [Parameter(Mandatory = $true)]
    [string]$DestinationRemote,
    [string]$DestinationPath = "",
    [ValidateSet("copy", "sync")]
    [string]$Mode = "copy",
    [switch]$DryRun,
    [string]$LogDir = "backups\logs"
)

$ErrorActionPreference = "Stop"

$rcloneCmd = Get-Command rclone -ErrorAction SilentlyContinue
if (-not $rcloneCmd) {
    throw "rclone was not found in PATH. Install rclone and configure remotes first."
}

$src = ("{0}:{1}" -f $SourceRemote.Trim(), $SourcePath.Trim("/")).TrimEnd(":")
$dst = ("{0}:{1}" -f $DestinationRemote.Trim(), $DestinationPath.Trim("/")).TrimEnd(":")

New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $LogDir ("media_sync_{0}_{1}.log" -f $Mode, $stamp)

$args = @(
    $Mode,
    $src,
    $dst,
    "--create-empty-src-dirs",
    "--checkers=16",
    "--transfers=8",
    "--fast-list",
    "--log-file=$logPath",
    "--log-level=INFO"
)
if ($DryRun) {
    $args += "--dry-run"
}

Write-Output ("Running rclone {0} from {1} to {2}" -f $Mode, $src, $dst)
if ($DryRun) {
    Write-Output "Dry run is enabled; no changes will be written."
}
& $rcloneCmd.Source @args
if ($LASTEXITCODE -ne 0) {
    throw "rclone $Mode failed with exit code $LASTEXITCODE. Check $logPath"
}

Write-Output ("Media sync complete. Log: {0}" -f (Resolve-Path $logPath))
