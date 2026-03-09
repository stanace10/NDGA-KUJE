# NDGA Offline LAN + Portable Backups Runbook

This runbook gives an operations-safe path for:

- PostgreSQL backups you can move between AWS and Supabase.
- Media bucket migration with no app code changes.
- LAN-first operation on a Windows 11 school server.
- Clean sync behavior when internet drops/returns.

## 1) Portable PostgreSQL backup (custom format)

Export:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pg_dump_custom.ps1 `
  -DatabaseUrl "postgresql://user:pass@host:5432/ndga" `
  -OutputDir "backups\postgres" `
  -Tag "ndga_prod"
```

Restore:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\pg_restore_custom.ps1 `
  -DumpPath ".\backups\postgres\ndga_prod_YYYYMMDD_HHMMSS.dump" `
  -DatabaseUrl "postgresql://user:pass@new-host:5432/ndga" `
  -Clean
```

Notes:

- Uses `pg_dump -Fc` and `pg_restore`.
- Keeps PostgreSQL portability between providers.
- Existing app-level archive backup (`backup_ndga`) remains available for full local snapshots.

## 2) Portable media migration (AWS/Supabase/MinIO)

Use `rclone` remotes so migration stays provider-agnostic.

Copy (safe migration without deleting target objects):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\media_sync_rclone.ps1 `
  -SourceRemote "awsprod" -SourcePath "ndga-media" `
  -DestinationRemote "supabaseprod" -DestinationPath "ndga-media" `
  -Mode copy
```

Mirror (destination becomes exact match of source):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\media_sync_rclone.ps1 `
  -SourceRemote "supabaseprod" -SourcePath "ndga-media" `
  -DestinationRemote "awsprod" -DestinationPath "ndga-media" `
  -Mode sync
```

## 3) LAN server stack (Windows 11, Docker)

Files added:

- `deploy/docker/docker-compose.lan.yml`
- `deploy/docker/Dockerfile.lan`
- `deploy/docker/nginx.lan.conf`
- root `.env` on the LAN machine

Start:

```powershell
docker compose -f .\deploy\docker\docker-compose.lan.yml --env-file .\.env up -d --build
```

This runs:

- `postgres`, `redis`, `minio`
- Django web (`gunicorn` + `uvicorn`)
- `celery_worker`, `celery_beat`
- `nginx`

## 3A) Cloud EC2 stack (Ubuntu, Docker)

Files used for the public cloud node:

- `deploy/docker/docker-compose.cloud.yml`
- `deploy/docker/Dockerfile.prod`
- `deploy/docker/entrypoint.prod.sh`
- `deploy/docker/nginx.prod.conf`
- `deploy/nginx/ndga.conf`

Start on EC2 from the repo root after creating a real root `.env` on the server:

```bash
docker compose -f deploy/docker/docker-compose.cloud.yml up -d --build
```

The root `.env` should include `DJANGO_SETTINGS_MODULE=core.settings.prod`, a real `DJANGO_SECRET_KEY`, your live database/Redis values, and the active S3 or email provider credentials.

This runs:

- `db`, `redis` when you keep the bundled services enabled
- Django web (`gunicorn` + `uvicorn`)
- `celery_worker`, `celery_beat`
- internal Docker `nginx` on `127.0.0.1:8080`

The production entrypoint also auto-creates the fixed `VP`, `Principal`, and `Bursar` accounts if they do not already exist. Host nginx/Certbot should then proxy HTTPS traffic to `127.0.0.1:8080` using `deploy/nginx/ndga.conf`.

## 4) Cloud <-> LAN sync policy

Current implementation uses a full-app outbox for sync-enabled writes:

- queued in `apps.sync.SyncQueue`
- processed automatically in the background every few seconds
- pushed/pulled when internet returns
- retry/backoff + idempotency + conflict statuses
- LAN active-session authority for CBT runtime and election voting

To avoid conflicts for CBT/Election:

1. Operate one writer mode per window:
   - LAN exam window: LAN owns CBT runtime writes; cloud-side active-session writes are deferred.
   - LAN election window: LAN owns vote writes while the election is open locally.
   - Cloud authoring window: cloud writes, LAN pulls updates before the next LAN runtime window.
2. Keep role/state toggles aligned (`CBT_ENABLED`, `ELECTION_ENABLED`).
3. Set `SYNC_NODE_ROLE=LAN` on the school node and `SYNC_NODE_ROLE=CLOUD` on the public cloud node.

## 5) Cloud -> LAN teacher CBT/question updates

Operationally safe flow:

1. Teachers/dean finalize CBT content in cloud.
2. IT exports portable backup set:
   - DB custom dump (`pg_dump_custom.ps1`)
   - Media sync (`media_sync_rclone.ps1`) if needed.
3. LAN IT restores DB/media before exam window.
4. LAN exam window opens; student attempts sync back through `SyncQueue`.

This ensures teacher-authored CBT content reaches LAN with no manual row editing and no split-write conflicts.

## 6) AWS -> Supabase (or reverse) migration checklist

1. Freeze writes briefly (maintenance window).
2. Run DB export (`pg_dump_custom.ps1`).
3. Restore to destination (`pg_restore_custom.ps1 -Clean`).
4. Sync media bucket (`media_sync_rclone.ps1`).
5. Update env vars:
   - `DATABASE_URL`
   - media backend credentials (`MEDIA_STORAGE_BACKEND`, bucket keys, endpoint).
6. Run smoke checks:
   - `python manage.py check`
   - login + CBT authoring + receipt PDF + student report download.
7. Re-open writes.

## 7) Scheduled backup baseline

- Nightly:
  - `pg_dump_custom.ps1`
  - media `rclone copy` to secondary location
- Weekly restore drill in staging using:
  - `pg_restore_custom.ps1`
  - app-level `restore_ndga` archive test (optional full snapshot validation)
