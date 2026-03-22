param(
    [string]$Container = "ndga-web-1",
    [int]$Limit = 100,
    [int]$Loops = 10
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

function Invoke-Manage {
    param(
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]]$Args
    )

    & docker exec $Container python manage.py @Args
    if ($LASTEXITCODE -ne 0) {
        throw "manage.py command failed: $($Args -join ' ')"
    }
}

$summaryScript = @"
from apps.sync.models import SyncQueue, SyncQueueStatus
from django.db.models import Count

counts = {row["status"]: row["count"] for row in SyncQueue.objects.values("status").annotate(count=Count("id"))}
print({
    "pending": counts.get(SyncQueueStatus.PENDING, 0),
    "retry": counts.get(SyncQueueStatus.RETRY, 0),
    "failed": counts.get(SyncQueueStatus.FAILED, 0),
    "conflict": counts.get(SyncQueueStatus.CONFLICT, 0),
})
"@

Write-Host "Repairing CBT writebacks on LAN before push..."
Invoke-Manage repair_cbt_result_writebacks

Write-Host "Pushing LAN CBT-owned rows to cloud..."
Invoke-Manage sync_drain --limit $Limit --loops $Loops --reset-failed

Write-Host "Current LAN sync queue summary:"
Invoke-Manage shell -c $summaryScript
