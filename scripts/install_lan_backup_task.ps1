param(
    [string]$TaskName = "NDGA LAN Safe Backup",
    [string]$DailyAt = "11:30 PM",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$backupScript = (Resolve-Path (Join-Path $PSScriptRoot "backup_lan_recovery_bundle.ps1")).Path
$actionArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"{0}"' -f $backupScript)
)
if ($OutputRoot) {
    $actionArgs += @("-OutputRoot", ('"{0}"' -f $OutputRoot))
}

$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]::Parse($DailyAt))
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ($actionArgs -join " ")
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Write-Output ("Scheduled task installed: {0}" -f $TaskName)
Write-Output ("Runs daily at: {0}" -f $DailyAt)
Write-Output ("Command: powershell.exe {0}" -f ($actionArgs -join " "))
