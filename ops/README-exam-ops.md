# NDGA exam production operations

This stack is the exam-day path: Nginx -> Gunicorn/Django -> Redis state and
PgBouncer -> PostgreSQL. It reuses the existing database, media and static
volumes. It does not run election/background beat jobs, Prometheus or Grafana
during an exam unless their optional profiles are explicitly selected.

## WSL/Docker allocation

Copy `ops/.wslconfig.24gb.example` to `%UserProfile%\.wslconfig`, then run
`wsl --shutdown` before starting Docker Desktop. The gaming PC currently needs
Docker to expose at least 7 CPUs and 17 GB RAM; `ops/preflight.ps1` checks this.

## Morning start

```powershell
cd C:\NDGA
powershell -ExecutionPolicy Bypass -File .\ops\preflight.ps1
```

Manual equivalent:

```powershell
docker compose --env-file .env.lan -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.lan -f docker-compose.prod.yml build
docker compose --env-file .env.lan -f docker-compose.prod.yml up -d --wait db redis_state redis_broker pgbouncer
docker compose --env-file .env.lan -f docker-compose.prod.yml up migrate
docker compose --env-file .env.lan -f docker-compose.prod.yml up -d --wait web celery_critical nginx
docker compose --env-file .env.lan -f docker-compose.prod.yml exec -T web python manage.py warm_exam_cache --hours 24
```

Do not start `celery_beat`, Grafana or Prometheus during the paper. To start
observability after the exam:

```powershell
docker compose --env-file .env.lan -f docker-compose.prod.yml --profile observability up -d prometheus grafana
```

## Live checks

```powershell
Invoke-RestMethod http://127.0.0.1/healthz/live
Invoke-RestMethod http://127.0.0.1/healthz/ready
docker compose --env-file .env.lan -f docker-compose.prod.yml ps
docker stats --no-stream
docker compose --env-file .env.lan -f docker-compose.prod.yml exec pgbouncer sh -lc 'PGPASSWORD=$DB_PASSWORD psql -h 127.0.0.1 -p 6432 -U $DB_USER pgbouncer -c "SHOW POOLS"'
```

## Load validation

Install Locust on the operator PC (`py -m pip install locust`) and prepare a
CSV based on `ops/locust/users.example.csv`. Each row must use a distinct test
student because production prevents multiple simultaneous sessions.

```powershell
$env:LOCUST_USERS_FILE='C:\NDGA\ops\locust\users.csv'
locust -f ops/locust/locustfile.py --headless -u 130 -r 30 -t 5m --host http://127.0.0.1
locust -f ops/locust/locustfile.py --headless -u 250 -r 50 -t 10m --host http://127.0.0.1
```

Pass criteria: error rate below 0.5%; login/start/question and answer-save p95
below 1 second; submit/result p95 below 5 seconds; no PostgreSQL “too many
clients”; no worker restarts; no Redis state OOM errors.

## Stop and rollback

```powershell
docker compose --env-file .env.lan -f docker-compose.prod.yml down
docker compose -f docker-compose.lan.yml up -d
```

The pre-change source and PostgreSQL dump are under `ops/rollback/pre-prod-*`.
To restore the database, stop all application containers, copy `database.dump`
into `ndga-db-1`, recreate the destination database, and run `pg_restore`.
Never use `down -v`; that would delete named data volumes.
