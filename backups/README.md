# NDGA Backups

This folder is the repo-local standby location for NDGA backup artifacts.

Rules:
- Keep the folder in Git.
- Do not commit live backup archives, database dumps, media bundles, or student score exports.
- Only keep lightweight documentation and placeholders in Git.

Recommended usage:
- Local LAN standby backup:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\create_standby_backup.ps1 -ComposeFile docker-compose.lan.yml -EnvFile .env.lan`
- Cloud standby backup:
  - `bash ./scripts/create_standby_backup.sh docker-compose.cloud.yml .env.cloud`

What the standby scripts create:
- `backup_ndga` archive from the running `web` container
- `ops_runtime_snapshot.json`
- a small manifest file with timestamp and source stack

Output location:
- `backups/standby/<timestamp>/`

If you change laptop:
- pull the repo as usual
- copy the newest untracked backup archive folder into `backups/standby/`
- restore from that backup or from the safer OneDrive/LAN recovery bundle

Do not use Git as the only place for real backups.
Real backup archives should stay in:
- OneDrive backup folders
- cloud server backup storage
- external/off-device storage
