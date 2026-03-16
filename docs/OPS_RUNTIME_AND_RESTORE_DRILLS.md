# Operations Runtime And Restore Drills

## Runtime checks

Use these before exam windows, results publication, or major deploys:

```bash
python manage.py ops_runtime_snapshot
curl http://127.0.0.1:8000/ops/readyz/
python manage.py verify_audit_chain
```

The runtime snapshot reports:
- database and cache readiness
- disk free space and used percentage
- current sync node role and node id
- sync backlog counts for `PENDING`, `RETRY`, `FAILED`, and `CONFLICT`
- recent audit visibility and missing audit hash count
- per-domain sync conflict playbooks

## Restore drills

Run a non-destructive drill regularly:

```bash
python manage.py run_restore_drill --output-dir backups/drills --keep-archive
```

What it does:
- creates a fresh NDGA backup archive
- validates archive structure and metadata
- confirms database dump and media manifest are present
- measures total drill time
- does not flush or restore the live database

## Safe LAN backups

For laptop wipe, Docker loss, or local-disk failure, create a host-side LAN recovery bundle:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup_lan_recovery_bundle.ps1
```

What it stores:
- PostgreSQL custom-format dump from the running `db` container
- media archive from the running `web` container
- NDGA app backup ZIP as a secondary fallback
- ops runtime snapshot and school-count snapshot
- manifest with SHA-256 hashes

Default storage behavior:
- prefers `OneDrive\NDGA Backups\lan-node` when OneDrive is available
- falls back to `backups\lan-node` inside the repo if OneDrive is unavailable
- keeps the newest 14 bundle folders unless you override `-KeepBundles`

Install a daily backup task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_lan_backup_task.ps1
```

Restore a saved LAN recovery bundle:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\restore_lan_recovery_bundle.ps1 -BundlePath "C:\Users\<you>\OneDrive\NDGA Backups\lan-node\YYYYMMDD_HHMMSS"
```

## Disaster playbooks

### 1. Cloud node degraded but LAN still active
- keep CBT and election runtime on the LAN node only
- run `python manage.py ops_runtime_snapshot` on the LAN node
- confirm sync backlog is growing but not failing hard
- restore cloud service first, then let queued sync replay

### 2. Sync conflict spike
- open the sync dashboard and inspect the per-record timeline
- use the conflict policy shown for the affected operation type
- results and finance conflicts should be reviewed before replay
- active CBT/election windows must remain single-authority

### 3. Backup confidence check before a term transition
- run `python manage.py verify_audit_chain`
- run `python manage.py run_restore_drill --output-dir backups/drills --keep-archive`
- store the generated drill archive off the server if the check passes

## Wrapper scripts

Windows:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\ops_runtime_snapshot.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restore_drill.ps1 -KeepArchive
powershell -ExecutionPolicy Bypass -File .\scripts\backup_lan_recovery_bundle.ps1
```

Linux:
```bash
bash ./scripts/ops_runtime_snapshot.sh
bash ./scripts/restore_drill.sh --keep-archive
```
