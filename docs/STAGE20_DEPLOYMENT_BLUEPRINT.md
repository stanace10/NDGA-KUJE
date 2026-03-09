# NDGA Stage 20 Deployment Blueprint

This blueprint is prepared for go-live planning only. It is not executed automatically by the project.

## 1. Target Topology

- Region: AWS `eu-west-1` (or closest low-latency region for Abuja users)
- OS: Ubuntu 24.04 LTS
- Edge: Nginx reverse proxy + Let's Encrypt TLS
- App runtime: Django ASGI via Gunicorn + Uvicorn workers
- Async workers: Celery worker + Celery beat
- Cache/broker/channels: Redis
- Primary database: PostgreSQL (AWS RDS PostgreSQL recommended)
- Media store: S3 (recommended) or Cloudinary
- Email provider: Brevo API

## 2. Domain/Subdomain Mapping

Use one apex domain and route by subdomain:

- `ndgakuje.org` (landing)
- `student.ndgakuje.org`
- `staff.ndgakuje.org`
- `it.ndgakuje.org`
- `bursar.ndgakuje.org`
- `vp.ndgakuje.org`
- `principal.ndgakuje.org`
- `cbt.ndgakuje.org`
- `election.ndgakuje.org`

## 3. App Process Layout (Single VM Pattern)

- `ndga-asgi.service` -> ASGI app (`core.asgi:application`)
- `ndga-celery-worker.service` -> Celery worker
- `ndga-celery-beat.service` -> Celery beat scheduler
- Nginx -> TLS termination, static file serving, proxy to ASGI

Reference templates:

- `deploy/nginx/ndga.conf`
- `deploy/systemd/ndga-asgi.service`
- `deploy/systemd/ndga-celery-worker.service`
- `deploy/systemd/ndga-celery-beat.service`

## 4. Data and Offline Sync Architecture

- Online cloud remains source-of-truth:
  - primary PostgreSQL in cloud
  - primary media store in cloud
- Offline nodes (CBT/Election LAN):
  - local PostgreSQL on node
  - local static/offline simulation assets
  - sync outbox (`SyncQueue`) pushes upstream when internet returns
- Conflict model:
  - attempts are append-only
  - votes use strict unique idempotency keys

## 5. Production Settings Module

Use:

```bash
DJANGO_SETTINGS_MODULE=core.settings.prod
```

Current production module supports:

- strict security flags + SSL proxy support
- media backend switching (`filesystem`, `s3`, `cloudinary`)
- structured logs (JSON/plain toggle)
- optional Sentry error reporting

## 6. Observability Baseline

- Liveness probe: `GET /ops/healthz/`
- Readiness probe: `GET /ops/readyz/` (DB + cache checks)
- Structured logs:
  - controlled by `DJANGO_LOG_JSON` and `DJANGO_LOG_LEVEL`
- Error capture:
  - Sentry integration enabled when `SENTRY_DSN` is set
- Audit retention:
  - `python manage.py prune_audit_events --days <N>`
  - default from `AUDIT_RETENTION_DAYS`

## 7. Stage 20 Validation Commands (Local Dry-Run)

```powershell
python manage.py check --deploy --settings=core.settings.prod
python manage.py verify_stage20 --settings=core.settings.prod
python manage.py test --noinput
python manage.py backup_ndga --output-dir backups
```

## 8. Deployment Strategy

- Start with one application VM + managed RDS + managed Redis
- Enable automated nightly backup (DB snapshot + `backup_ndga` archive)
- Add second app VM and load balancer after first stable run
- Keep offline CBT/Election nodes independent and sync-enabled

## 9. Portable Migration + LAN Runbook

For provider migration (AWS <-> Supabase), LAN Docker stack startup, and portable
`pg_dump -Fc`/media sync commands, use:

- `docs/OFFLINE_LAN_AND_PORTABLE_BACKUPS.md`
