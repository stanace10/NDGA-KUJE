# NDGA AI Enterprise Platform

NDGA is a governance-first school platform for Notre Dame Girls Academy, Kuje Abuja.

It covers:
- academic setup, attendance, results, PDFs, audit
- CBT with approval workflow, lockdown, theory marking, simulation support
- elections, finance, notifications, sync
- cloud + LAN deployment with app-level sync

## Runtime Files

Use these tracked env files:
- `.env.cloud` for AWS/cloud
- `.env.lan` for the school LAN node

Root deploy files:
- `Dockerfile`
- `docker-compose.cloud.yml`
- `docker-compose.lan.yml`
- `entrypoint.sh`
- `nginx.conf`
- `nginx.host.conf`

## Core URLs

- `ndgakuje.org`
- `student.ndgakuje.org`
- `staff.ndgakuje.org`
- `it.ndgakuje.org`
- `bursar.ndgakuje.org`
- `vp.ndgakuje.org`
- `principal.ndgakuje.org`
- `cbt.ndgakuje.org`
- `election.ndgakuje.org`

## Cloud Node

1. Fill `.env.cloud`
2. Start:

```bash
docker compose --env-file .env.cloud -f docker-compose.cloud.yml up -d --build
```

3. Verify:

```bash
docker compose --env-file .env.cloud -f docker-compose.cloud.yml ps
docker compose --env-file .env.cloud -f docker-compose.cloud.yml exec web python manage.py check
```

## LAN Node

1. Fill `.env.lan`
2. Start:

```powershell
docker compose --env-file .env.lan -f docker-compose.lan.yml up -d --build
```

3. Verify:

```powershell
docker compose --env-file .env.lan -f docker-compose.lan.yml exec web python manage.py check
```

## Data Bootstrap

Run on each fresh node after boot:

```bash
python manage.py purge_demo_users
python scripts/import_school_bootstrap.py --source-dir SCHOOL --session 2025/2026 --term SECOND
```

## Operations Rule

- teachers can author online
- LAN is the live authority for heavy CBT/election sessions
- cloud is the public portal and sync target
- LAN pushes attempts/results/events back through sync

## Useful Commands

```bash
python manage.py check
python manage.py verify_stage20
python manage.py ops_runtime_snapshot
python manage.py run_restore_drill --output-dir backups/drills --keep-archive
```

## Notes

- `README copy.md` is kept local for investor/print use and is not tracked by git.
- fill blank secrets only on the target machine; do not commit real secrets.
