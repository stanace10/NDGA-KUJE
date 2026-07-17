# NDGA Cloud Clean Redeploy Runbook

Use this when the LAN build is correct and the cloud student portal/public website must be rebuilt from the current code.

## Safety rule

Do not delete the live cloud database or media until you have a verified backup. A clean rebuild should be:

1. Backup current cloud database and media.
2. Deploy the current LAN code to GitHub.
3. Pull/build the new code on AWS.
4. Restore/import the clean database and media that should be shown on cloud.
5. Run migrations, collect static files, and verify PDF rendering.
6. Enable only the public website and student portal on cloud.

## Local repository note

This copied `C:\NDGA` folder currently contains an empty `.git` directory, so normal `git status`, `git remote`, `git push`, and branch operations will fail until Git is re-initialized or a fresh clone is used.

Recommended local repair:

```powershell
cd C:\NDGA
Remove-Item -Recurse -Force .git
git init
git remote add origin https://github.com/stanace10/NDGA-KUJE.git
git add .
git commit -m "Production LAN build for cloud student portal"
git branch -M main
git push -u origin main --force-with-lease
```

Only use `--force-with-lease` when you intentionally want GitHub to match this folder and you have already backed up anything important from the GitHub repository.

## AWS clean pull/build

On AWS:

```bash
cd /opt
sudo mkdir -p ndga
sudo chown -R "$USER":"$USER" ndga
cd ndga
git clone https://github.com/stanace10/NDGA-KUJE.git app
cd app
cp .env.cloud.example .env.cloud
nano .env.cloud
docker compose -f docker-compose.cloud.yml down
docker compose -f docker-compose.cloud.yml build --no-cache
docker compose -f docker-compose.cloud.yml up -d
docker compose -f docker-compose.cloud.yml exec web python manage.py migrate --noinput
docker compose -f docker-compose.cloud.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.cloud.yml exec web python manage.py check --deploy
```

## Required cloud environment settings

Make sure `.env.cloud` contains the real values for:

```text
SYNC_NODE_ROLE=CLOUD
CLOUD_STAFF_OPERATIONS_LAN_ONLY=True
CLOUD_STUDENT_PORTAL_LIMITED=True
CLOUD_STUDENT_FINANCE_DISABLED=False
MANUAL_UPDATE_REMOTE_BASE_URL=https://student.ndgakuje.org
MANUAL_UPDATE_TOKEN=<same-secret-token-on-LAN-and-cloud>
MEDIA_STORAGE_BACKEND=filesystem
```

If using S3 media, set `MEDIA_STORAGE_BACKEND=s3` and configure the AWS bucket variables.

## Cloud portal policy

Cloud should expose:

- Public website
- Student portal
- Student result/PDF pages
- Student attendance/media needed by the portal

Cloud should not expose operational portals:

- IT Manager
- Staff
- Dean
- Form Teacher
- Hostel
- VP/Principal management
- CBT operations
- Elections operations
- Finance/bursar operations

The current Django middleware enforces this when:

```text
SYNC_NODE_ROLE=CLOUD
CLOUD_STAFF_OPERATIONS_LAN_ONLY=True
CLOUD_STUDENT_PORTAL_LIMITED=True
```

## PDF engine verification

The Dockerfile installs the WeasyPrint runtime libraries. Verify after deployment:

```bash
docker compose -f docker-compose.cloud.yml exec web python - <<'PY'
from weasyprint import HTML
HTML(string="<h1>NDGA PDF OK</h1>").write_pdf("/tmp/ndga-pdf-ok.pdf")
print("PDF OK")
PY
```

If this fails, rebuild the image after confirming these Debian packages are installed: `libcairo2`, `libfontconfig1`, `libpango-1.0-0`, `libpangoft2-1.0-0`, `libgdk-pixbuf-2.0-0`, `libffi8`, `shared-mime-info`, and `fonts-dejavu-core`.

## Publish results to cloud

On LAN, IT Manager should use:

```text
IT Manager Portal -> Publish Results
```

Filter by session, term, and class, then push the selected class result to LAN/cloud. First and Second Term result pushes should update portal records only and should not send parent emails. Third Term/Cumulative parent messaging should be sent only after final approval.

