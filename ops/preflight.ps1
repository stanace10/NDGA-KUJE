param(
    [switch]$RunSmokeTest,
    [int]$SmokeUsers = 25,
    [string]$BaseUrl = "http://127.0.0.1"
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$compose = Join-Path $root "docker-compose.prod.yml"
$envFile = Join-Path $root ".env.lan"

function Step($message) { Write-Host "`n==> $message" -ForegroundColor Cyan }
function DC { & docker compose --env-file $envFile -f $compose @args; if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed: $args" } }

Set-Location $root
Step "Checking Docker Desktop"
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not reachable." }

Step "Checking WSL capacity"
$info = docker info --format '{{.NCPU}}|{{.MemTotal}}'
$parts = $info -split '\|'
if ([int]$parts[0] -lt 7) { throw "Docker exposes fewer than 7 CPUs." }
if ([int64]$parts[1] -lt 17GB) { throw "Docker exposes less than 17 GB RAM. Apply ops/.wslconfig.24gb.example and run wsl --shutdown." }

Step "Validating production Compose"
DC config --quiet

Step "Building immutable production images"
DC build

Step "Stopping the previous LAN application containers without deleting volumes"
$savedErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker compose -f docker-compose.lan.yml stop nginx web celery_worker celery_beat prometheus grafana 2>&1 | Out-Host
$stopCode = $LASTEXITCODE
$ErrorActionPreference = $savedErrorPreference
if ($stopCode -ne 0) { throw "Unable to stop the previous LAN application containers." }

Step "Starting PostgreSQL, split Redis and PgBouncer"
DC up -d --wait db redis_state redis_broker pgbouncer

Step "Running migrations, account checks and collectstatic"
DC up --no-deps migrate

Step "Starting exam-only web, critical worker and Nginx"
DC up -d --wait web celery_critical nginx

Step "Warming active exam manifests"
DC exec -T web python manage.py warm_exam_cache --hours 24

Step "Checking liveness and readiness"
$live = Invoke-RestMethod -Uri "$BaseUrl/healthz/live" -TimeoutSec 10
$ready = Invoke-RestMethod -Uri "$BaseUrl/healthz/ready" -TimeoutSec 15
if ($live.status -ne "ok") { throw "Liveness check failed." }
if ($ready.status -ne "ready") { throw "Readiness check failed: $($ready | ConvertTo-Json -Compress)" }

Step "Capturing service and resource state"
DC ps
docker stats --no-stream

if ($RunSmokeTest) {
    Step "Running Locust smoke test"
    python -m locust -f ops/locust/locustfile.py --headless -u $SmokeUsers -r 10 -t 2m --host $BaseUrl --only-summary
    if ($LASTEXITCODE -ne 0) { throw "Locust smoke test failed." }
}

Write-Host "`nNDGA EXAM PREFLIGHT PASSED" -ForegroundColor Green
