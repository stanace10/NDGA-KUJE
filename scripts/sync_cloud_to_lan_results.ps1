param(
    [string]$Container = "ndga-web-1",
    [int]$Limit = 200,
    [int]$MaxOutboxPages = 100
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

Write-Host "Pulling cloud-owned result rows into LAN..."
Invoke-Manage force_cloud_mirror `
    --limit $Limit `
    --max-outbox-pages $MaxOutboxPages `
    --skip-content `
    --allow-operation MODEL_RECORD_UPSERT `
    --allow-model results.resultsheet `
    --allow-model results.studentsubjectscore `
    --allow-model results.resultsubmission `
    --allow-model results.classresultstudentrecord `
    --allow-model results.classresultcompilation `
    --allow-model results.resultaccesspin

Write-Host "Current LAN sync queue summary:"
Invoke-Manage shell -c $summaryScript
