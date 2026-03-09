# NDGA AI Enterprise Platform

Full implementation README for:

- Notre Dame Girls Academy (NDGA), Kuje Abuja
- Hybrid Online + Offline Academic Governance System
- Date: March 5, 2026

This document combines:

- the original NDGA enterprise specification
- what has been implemented in this codebase
- additional upgrades added during build
- current deployment and operations plan (local LAN + cloud)

---

## 1) Project Identity

### What NDGA is

NDGA is an enterprise-grade school governance platform, not a generic school portal template.

It enforces strict role hierarchy and workflow state transitions across:

- academics
- attendance
- CBT + simulation practicals
- elections
- finance
- notifications
- audit/compliance

It is designed to run:

- fully on local LAN (offline-capable)
- fully online in cloud mode
- with sync continuity between local and cloud environments

### What NDGA is not

- not a single-page "all-in-one admin panel"
- not open registration SaaS
- not role-agnostic editing
- not exam-only CBT

---

## 2) Aims and Outcomes

Primary aims implemented in architecture and workflows:

1. Governance enforcement
- teachers cannot publish final results
- mandatory approvals are tracked and auditable
- role ownership is explicit and enforced

2. Hybrid reliability
- supports LAN-first operation with local persistence
- supports cloud mode and sync queue design
- no broken 404 UX for toggle-disabled modules (CBT/Election)

3. Advanced CBT model
- CA + exam + practical simulation workflows
- objective auto-marking, theory marking queue
- simulation scoring modes (AUTO / VERIFY / RUBRIC)

4. Election governance
- one vote per user per position
- audit + IP logging + analytics visibility restrictions

5. Finance governance
- structured charges/payments/expenses/salary model
- receipt generation and auditability

---

## 3) Current Delivery Rating (Internal Readiness)

This score reflects implementation readiness in this repository as of March 5, 2026.

- Governance + Role Access Control: `9.2/10`
- Academic Result Workflow: `9.0/10`
- CBT Core (authoring, runner, lockdown): `8.8/10`
- Simulation Practical Engine: `8.6/10`
- Offline + Sync Foundation: `8.5/10`
- Finance Module Maturity: `8.2/10`
- Election Module Maturity: `8.3/10`
- Production Hardening + Ops: `8.4/10`

Overall delivery score: `8.7/10`

Notes:

- Core governance and workflow backbone is strong.
- Remaining work is primarily UX refinement, expanded simulation catalog operations, and final production go-live hardening.

---

## 4) Role Model and Governance Chain

Roles:

- `IT_MANAGER`
- `DEAN`
- `FORM_TEACHER`
- `SUBJECT_TEACHER`
- `BURSAR`
- `VP` (Vice Principal)
- `PRINCIPAL`
- `STUDENT`

Core governance chain:

- Subject Teacher -> Dean -> Form Teacher -> VP -> Principal (oversight)

CBT publication chain:

- Teacher drafts -> Dean vets -> IT activates (high-stakes)

Special implemented rule:

- `FREE_TEST` CBT can go Teacher -> IT (no dean) because it is non-graded practice mode.

---

## 5) Portal and Subdomain Model

Configured portals:

- `ndgakuje.org` (landing)
- `student.ndgakuje.org`
- `staff.ndgakuje.org`
- `it.ndgakuje.org`
- `bursar.ndgakuje.org`
- `vp.ndgakuje.org`
- `principal.ndgakuje.org`
- `cbt.ndgakuje.org`
- `election.ndgakuje.org`

Behavior:

- role-smart redirects after login
- portal guards enforce role access
- CBT/Election can be toggled off without 404 leakage

---

## 6) What Has Been Achieved

## 6.1 Setup and Academic Foundations

- setup wizard from empty system to operational state
- session/term/calendar/class/subject mapping flow
- subject-teacher and form-teacher assignment constraints
- role-bound registration by IT only

## 6.2 Attendance and Results Workflow

- form teacher attendance ownership
- grade entry with CA and exam component validation
- dean review queue
- form compilation with governance gates
- VP publish workflow
- principal oversight and timeline visibility

## 6.3 PDF and Verification Layer

- report card and transcript PDF generation
- QR/hash verification records
- student and staff export routes

## 6.4 Notifications + Audit

- in-app notification center
- email provider abstraction (console/brevo adapters)
- audit logs for sensitive actions and workflow transitions

## 6.5 CBT Authoring, Vetting, Activation, Running

- teacher authoring home
- question bank + manual question creation
- exam creation flow with setup + builder pages
- dean review + IT activation queues
- student CBT runner + timer + navigation + submission
- objective auto-marking + writeback mapping
- theory marking queue with writeback after marking

## 6.6 Lockdown + Integrity

- violation tracking (focus/visibility/fullscreen/copy-paste)
- lock/unlock controls for IT
- violation audit metadata persistence

## 6.7 Simulation Practical Engine

- simulation wrapper registry (IT-managed)
- dean simulation wrapper approval
- attach simulation tasks to CBT
- scoring modes:
  - `AUTO`: callback score capture
  - `VERIFY`: evidence upload + teacher verify
  - `RUBRIC`: deterministic rubric scoring + import
- score import into CA/exam targets

## 6.8 Offline + Sync Foundation

- outbox queue model with retry/conflict states
- sync dashboard and status indicators
- USB transfer import/export path
- local/offline simulation asset serving strategy

## 6.9 Stage 20 Readiness Assets

- nginx/systemd/docker LAN deployment assets
- production env template
- deploy verification commands
- health/ready endpoints

---

## 7) New Additions Beyond Original Spec

The following were added during implementation refinement:

1. `FREE_TEST` CBT type
- objective-only, non-graded practice
- can be published by IT after teacher submission
- remains open for student practice scenarios

2. Per-question stimulus media
- image upload per question
- video upload per question
- optional shared stimulus span across multiple questions (e.g. "use this image/video for Q1-Q5")

3. Structured response interaction support
- objective
- multi-select
- short-answer
- labeling
- matching
- ordering (drag/drop ordering style answer capture)

4. Builder-side rich authoring helpers
- toolbar shortcuts for formatting and symbols placeholders
- faster teacher authoring workflow

5. CA duplication guard after completion
- once CA target attempt is completed/written, creating another CBT under same CA target for same assignment is blocked

6. Fresh launch reset command
- destructive reset with bootstrap IT account only for clean production onboarding

---

## 8) CBT Functional Status (Current)

### Implemented and working

- Manual authoring flow with multi-page setup/builder path
- Upload import + parser pipeline hooks
- AI draft flow scaffold with review steps
- Dean/IT approval chain
- Lock after non-draft status (teacher cannot edit/delete once submitted/approved/active)
- Attempt execution and marking flows
- Simulation integration with practical writeback

### Important policy behavior now

- Teacher can only edit/delete when exam status is `DRAFT`.
- Once submitted to dean or beyond, teacher is view-only.
- High-stakes CBT workflow remains governance-safe by design.
- Direct teacher -> IT bypass is currently enabled for `FREE_TEST` only.
- Simulation/high-stakes CBT still follows Teacher -> Dean -> IT activation chain.

---

## 9) Finance Module Status (Current)

Implemented foundations:

- charge definitions
- payment recording + receipts
- debtor/outstanding tracking
- expense + salary records
- summary metrics and trend services
- live payment gateway transaction pipeline:
  - initialize gateway links
  - callback/webhook verification
  - auto-record payment + receipt on verified success
- scheduled reminder engine:
  - periodic overdue/upcoming fee reminders
  - in-app notification + email dispatch
  - per-student per-day dispatch dedupe log
- inventory & asset tracking:
  - asset register (code/category/location/value)
  - stock movement log (in/out/return/write-off)
  - available vs total stock consistency checks

Operational direction:

- bursar-first workflow
- richer dashboards and messaging/reporting are being refined continuously

---

## 10) Election Module Status (Current)

Implemented foundations:

- election management structures
- role-based access boundaries
- visibility controls and audit hooks
- live analytics architecture path

Operational direction:

- continue polishing visual analytics and publication reports for production presentation quality

---

## 11) Tech Stack and Tools Used

Backend:

- Python `3.12`
- Django `5.2`
- Django Channels
- Celery
- PostgreSQL
- Redis

Frontend:

- Tailwind CSS
- HTMX
- Alpine.js
- server-rendered Django templates

Document/PDF/Audit:

- WeasyPrint
- qrcode
- audit logging model/services

Sync/Offline:

- sync queue + retry/conflict policy
- LAN docker artifacts
- local simulation media strategy

Simulation tooling support:

- PhET/local HTML5 library import tooling
- wrapper registry + manifest import flow

---

## 12) Repository Structure

- `core/` - project settings, ASGI/WSGI, app wiring
- `apps/` - domain apps (`accounts`, `academics`, `attendance`, `results`, `cbt`, `finance`, `elections`, `sync`, `notifications`, `audit`, etc.)
- `templates/` - portal and feature templates
- `assets/` + `static/` - frontend assets
- `deploy/` - nginx/systemd/docker deployment files
- `docs/` - stage and operations documentation

---

## 13) Local Development Setup

1. Create venv

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies

```powershell
python -m pip install -r requirements/dev.txt
npm install
```

3. Environment

```powershell
# .env is already the live environment file in this project.
# Update values directly before running locally or deploying.
```

4. Start local services

```powershell
# For host-side runserver, use either:
# - a standard PostgreSQL 16 install, or
# - repo-local portable binaries at .tools\PostgreSQL\16\bin
# The helper starts NDGA Postgres on 127.0.0.1:5433 by default.
powershell -ExecutionPolicy Bypass -File .\scripts\start_stage0_services.ps1
```

5. Build CSS / run app

```powershell
npm run build:css
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

If `.env` uses the default local database URL, it should point at:

```powershell
DATABASE_URL=postgresql://ndga:ndga@127.0.0.1:5433/ndga
```

---

## 14) Hosts Mapping (Subdomain Local Routing)

Add to hosts file:

```txt
127.0.0.1 ndgakuje.org
127.0.0.1 student.ndgakuje.org
127.0.0.1 staff.ndgakuje.org
127.0.0.1 it.ndgakuje.org
127.0.0.1 bursar.ndgakuje.org
127.0.0.1 vp.ndgakuje.org
127.0.0.1 principal.ndgakuje.org
127.0.0.1 cbt.ndgakuje.org
127.0.0.1 election.ndgakuje.org
```

Helper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure_ndga_hosts.ps1
```

---

## 15) Bootstrap and Utility Commands

Create/update IT manager:

```powershell
python manage.py create_it_manager --username admin@ndgakuje.org --password admin --email admin@ndgakuje.org --prune-others
```

Project checks:

```powershell
python manage.py check
python manage.py verify_stage0
python manage.py verify_stage20
```

Test suites:

```powershell
python manage.py test apps.cbt --keepdb
python manage.py test apps.finance --keepdb
```

Simulation catalog tooling:

```powershell
python manage.py sync_simulation_catalog --username admin@ndgakuje.org
python manage.py import_local_phet --actor admin@ndgakuje.org --all --approve
python manage.py import_simulation_manifest --actor admin@ndgakuje.org --manifest-file docs/simulations/waec_offline_manifest.json --source-root C:\NDGA\simulation_sources --approve
python manage.py build_mixed_sim_manifest --source-root C:\NDGA\simulation_sources --output-file docs/simulations/waec_mixed_manifest.generated.json
python manage.py build_mixed_sim_manifest --source-root C:\NDGA\simulation_sources --import-now --username admin@ndgakuje.org --approve --output-file docs/simulations/waec_mixed_manifest.generated.json
```

Backup/restore:

```powershell
python manage.py backup_ndga --output-dir backups
python manage.py restore_ndga backups\ndga_backup_YYYYMMDD_HHMMSS.zip

# Run scheduled finance reminders immediately
python manage.py send_finance_reminders --days-ahead 3
```

Fresh launch reset (destructive, keeps only IT bootstrap account):

```powershell
python manage.py reset_for_fresh_launch --yes-i-know --it-username admin@ndgakuje.org --it-password admin --it-email admin@ndgakuje.org --staff-id ITM-001
```

---

## 16) Online + Offline Operations Plan (Right Now)

## 16.1 Current practical model

Use a dual-mode approach:

1. Online mode (cloud)
- full portal access
- centralized operations
- media and data in cloud infra

2. Offline mode (LAN local node)
- local Django + Postgres + Redis
- attempts/votes/events written locally
- sync outbox retries to cloud when internet returns

## 16.2 Recommended LAN stack (Windows 11 school PC)

- Docker Compose LAN package in `deploy/docker/`
- local services:
  - nginx
  - django/gunicorn
  - postgres
  - redis
  - celery worker/beat
  - local media storage strategy

## 16.3 Sync behavior

- Local write -> outbox queue (`PENDING/RETRY/CONFLICT/FAILED/SYNCED`)
- Worker retries with capped backoff
- Idempotency key prevents duplicate replay
- Automatic cloud<->LAN incremental sync is enabled through the outbox feed plus the CBT content feed.
- Machine-to-machine sync endpoints:
  - `GET/HEAD /sync/api/` (health/token check)
  - `POST /sync/api/outbox/` (remote outbox ingest)
  - `GET /sync/api/outbox/feed/?after_id=<id>&limit=<n>` (generic incremental outbox feed)
  - `GET /sync/api/content/cbt/?after_id=<id>&limit=<n>` (incremental CBT authoring feed)
- Sync pull cursors are persisted (`SyncPullCursor`) so restarts continue from the last remote event id for both generic outbox events and CBT content.
- Sync-enabled writes from the explicit outbox producers and the models listed in `apps/sync/model_sync.py` enqueue to `SyncQueue`; CBT authoring changes also persist to `SyncContentChange` for the CBT feed.
- USB transfer fallback remains supported for emergency movement
- Media sync is event-driven, not raw Postgres or filesystem replication: sync payloads move record data, workflow state, and queued file/object references for sync-enabled records instead of mirroring `/media/` every few seconds.

## 16.4 Automatic mode configuration (no manual backup windows)

Set these in cloud and LAN environments:

- `SYNC_ENDPOINT_AUTH_TOKEN=<shared-secret>`
- `SYNC_CLOUD_ENDPOINT=https://<cloud-sync-host>/sync/api` on the LAN node; leave it empty on the cloud node to avoid self-pull
- `SYNC_PULL_ENABLED=True` on the LAN node; keep it `False` on the cloud node unless the cloud node must consume another upstream feed
- `SYNC_PULL_BATCH_LIMIT=200`
- `SYNC_PULL_MAX_PAGES_PER_RUN=4`
- `SYNC_PULL_TIMEOUT_SECONDS=5`
- `SYNC_PULL_BEAT_INTERVAL_SECONDS=5`
- `SYNC_PROCESS_BEAT_INTERVAL_SECONDS=5`
- `SYNC_AUTO_MIN_INTERVAL_SECONDS=5`
- `SYNC_NODE_ROLE=CLOUD` on cloud and `SYNC_NODE_ROLE=LAN` on the school LAN node
- `SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY=True`

Behavior:

- Every registered sync-enabled create/update/delete writes to the outbox automatically.
- Background workers process outbound and inbound batches every few seconds with retry/backoff.
- LAN pushes attempts/votes/simulation attempt events and all sync-enabled portal records through the outbox worker.
- LAN pulls generic remote changes plus teacher-created CBT updates automatically through feed workers.
- Both directions are idempotent, resumable, and largely invisible to users.

## 16.5 Conflict safety policy

- Keep high-stakes sessions single-active-source (LAN or cloud) per active window.
- On the LAN node, active CBT runtime and active election voting stay LAN-authoritative and remote writes are retried later instead of overriding the live session.
- Avoid simultaneous double-authority exam/vote sessions across both nodes.

## 16.6 Final deployment decision (cost-aware, launch-ready)

Use this as the production baseline for first public go-live:

1. Cloud node (online/public)
- OS: Ubuntu `24.04` on AWS EC2
- Size: `t3.small` recommended; use `t3.micro + 2GB swap` only if credit pressure is high
- Disk: `30GB gp3`
- App stack: `nginx + gunicorn + django + redis + celery`
- Database: PostgreSQL on the same EC2 initially (simple + low cost for first launch)
- Media: AWS S3 (`private bucket`) for cloud images/PDFs/assets

2. LAN node (offline exam authority)
- Windows 11 school server using Docker Compose from `deploy/docker/`
- runtime env file: `deploy/docker/.env.lan` (LAN writes locally to the `db` service and syncs outward through the app-level outbox)
- Services: `nginx + django + postgres + redis + celery (+ minio when needed)`
- Primary role: CBT + Election runtime and local writes during internet outage

3. Authority model
- LAN-authority modules: CBT attempts, CBT integrity events, election votes/events
- Cloud-first modules: portal browsing, staff workflows, messaging, setup/admin
- Bi-directional sync: automatic outbox push and incremental content pull (no manual operator backup windows)

### EC2 Docker deployment files

For the AWS Ubuntu cloud node, use the Docker deployment package in `deploy/docker/` with `deploy/docker/.env.cloud` on the server:

- `deploy/docker/docker-compose.cloud.yml`
- `deploy/docker/.env.cloud`
- `deploy/docker/Dockerfile.prod`
- `deploy/docker/entrypoint.prod.sh`
- `deploy/docker/nginx.prod.conf`
- `deploy/nginx/ndga.conf`

Recommended EC2 flow from the repo root:

1. Open `deploy/docker/.env.cloud` on the server and fill every blank secret before first boot. Keep `DJANGO_SETTINGS_MODULE=core.settings.prod`, `DB_HOST=db`, and the live domain/S3 values.
2. Start the stack:

```bash
docker compose --env-file deploy/docker/.env.cloud -f deploy/docker/docker-compose.cloud.yml up -d --build
```

3. Confirm services:

```bash
docker compose --env-file deploy/docker/.env.cloud -f deploy/docker/docker-compose.cloud.yml ps
```

4. Run first-boot commands if needed:

```bash
docker compose --env-file deploy/docker/.env.cloud -f deploy/docker/docker-compose.cloud.yml exec web python manage.py migrate --noinput
docker compose --env-file deploy/docker/.env.cloud -f deploy/docker/docker-compose.cloud.yml exec web python manage.py collectstatic --noinput
```

5. Point host nginx/Certbot to `127.0.0.1:8080` using `deploy/nginx/ndga.conf`.

Auto-deploy path:

- `scripts/auto_deploy.sh` now uses `deploy/docker/.env.cloud` and the cloud compose file directly.
- The GitHub Action in `.github/workflows/deploy-cloud.yml` SSHes into `~/NDGA`, `~/ndga`, or `~/ndga-platform` and runs that script on every push to `main`.
- On EC2, still enable Docker on boot with `sudo systemctl enable docker`.

Notes:

- The production entrypoint refuses to boot with `core.settings.local` or an empty/default development secret key.
- The production entrypoint automatically ensures the fixed `VP`, `Principal`, and `Bursar` accounts exist on first boot.
- Production settings accept either `DATABASE_URL` or the simpler `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` pattern.
- `AWS_REGION` is accepted as a fallback alias for `AWS_S3_REGION_NAME`.
- The cloud stack keeps Postgres and Redis bound to loopback only (`127.0.0.1`) when you use the bundled services.

## 16.7 DNS routing model (public + school LAN)

Use split-horizon DNS so the same domain works both inside and outside school:

1. Public internet DNS (Spaceship/Route53)
- `ndgakuje.org` and `*.ndgakuje.org` -> EC2 Elastic IP

2. School LAN DNS override (MikroTik static DNS)
- `ndgakuje.org` -> LAN server IP (example `192.168.88.10`)
- `student.ndgakuje.org` -> same LAN IP
- `staff.ndgakuje.org` -> same LAN IP
- `cbt.ndgakuje.org` -> same LAN IP
- `election.ndgakuje.org` -> same LAN IP

Result:
- Inside school network: users hit LAN node (fast, offline-capable)
- Outside school network: users hit cloud EC2

## 16.8 170-200 student no-lag checklist

Required for stable exam windows:

- Serve static/media with `nginx` (never Django dev/static serving in production)
- Run `collectstatic` on each deploy
- Keep Redis tuned (already defined in LAN compose and settings)
- Keep Celery prefetch low (`1`) for fair worker distribution
- Run `gunicorn` with enough workers for CPU/RAM budget
- Use DB connection pooling (`PgBouncer`) if concurrent session pressure rises
- Keep CBT/election heavy sessions single-active-source (LAN or cloud, not both)

## 16.9 Optional alternatives (not primary baseline)

- Supabase Postgres can be used later to reduce EC2 DB ops burden.
- Cloudinary can be used later for advanced image transforms/CDN workflows.
- Current recommended first-launch baseline remains EC2 Postgres + S3 because it aligns with the existing sync/offline model and reduces moving parts during first rollout.

---

## 17) Portable Backup and Migration Strategy

Database portability:

- use PostgreSQL custom dumps (`pg_dump -Fc`)
- restore with `pg_restore`

Media portability:

- keep media in object-style storage layout
- sync bucket-to-bucket or local-to-cloud using script tooling

Outcome:

- provider migration (AWS <-> Supabase-style Postgres/object storage) with minimal lock-in risk

---

## 18) Security and Governance Hardening

Implemented controls include:

- role-based middleware and portal guards
- strict session separation by portal/audience
- rate limiting on sensitive routes
- hardened headers and cookie policy controls
- upload scanning limits by file class
- first-class audit events for critical operations
- finance receipt integrity enforcement:
  - payment fields are immutable after receipt issuance
  - each receipt carries hash + HMAC signature metadata
  - integrity mismatch raises `RECEIPT_INTEGRITY_ALERT` audit failures
- CBT concurrency tuning defaults:
  - redis memory policy and pubsub buffer hardening in LAN compose
  - channels capacity/expiry env tuning
  - celery prefetch/acks/retry pool tuning for burst starts

---

## 19) Known Current Gaps / Next Work (Transparent)

1. Continue refining upload/AI extraction quality for difficult PDFs (especially scanned/equation-heavy docs).
2. Continue UX polishing for high-traffic portals (CBT runner, bursar analytics, election live views).
3. Expand simulation library curation per subject/topic to full WAEC practical coverage.
4. Final production cutover checklist execution and monitored dry-run.
5. Complete mobile-first optimization and role-critical phone workflows.
6. Add deeper sync observability and deterministic conflict-resolution playbooks.
7. Add immutable exam versioning + stronger integrity evidence bundle for dispute resolution.

---

## 20) Acceptance Snapshot

NDGA currently delivers the required core model:

- governance-first role chain
- hybrid architecture foundation
- advanced CBT with practical simulation path
- result workflow with dean/form/VP/publish control
- finance and election foundational enterprise modules
- auditability and hardening baseline

This codebase is now in a strong pre-go-live phase, with final UX polish + curated content population as the main remaining effort.

---

## 21) Maintainer Note

Operational rule remains:

- no public registration
- IT Manager seeds and controls system setup
- all critical approval transitions must stay auditable

For NDGA, governance integrity is the product.

---

## 22) Where NDGA Loses Points (Current)

These are the main reasons current score is not yet `9.5+`.

1. UX depth is still below target in key daily flows:
- teacher exam builder speed and clarity
- CBT runner ergonomics under pressure
- bursar finance reporting density and actionability

2. AI capability is present but not yet full production-grade:
- AI draft flow exists, but extraction/generation reliability for difficult files still needs hardening
- teacher trust depends on strong review UX + consistent output quality

3. Mobile-first strategy needs tighter definition and verification:
- student portal mobile behavior needs strict acceptance coverage
- teacher operational flows on phone/tablet need explicit task-level support guarantees
- CBT tablet mode and kiosk behavior require clear tested boundaries

---

## 23) UX / AI / Mobile Upgrade Plan

### 23.1 UX adoption plan (high impact)

- enforce 3-click completion target for common tasks:
  - mark attendance
  - input scores
  - submit CBT draft
- add persistent inline validation + autosave feedback in all high-volume forms
- role-based "Next Actions" queues on dashboards:
  - Dean pending reviews
  - IT activation queue
  - VP publish queue
  - Bursar collection/receipt actions

### 23.2 AI maturation plan

- keep deterministic parser first, AI as repair/classifier layer
- strict schema output for AI-generated question rows
- confidence + flagged-block review before commit
- improve extraction pipeline for:
  - equation-rich DOCX/PDF
  - scanned/low-quality sources with OCR fallback

### 23.3 Mobile-first execution plan

- declare mobile support matrix per role:
  - Student: full academic + notifications + finance visibility
  - Teacher: attendance + quick grade entry + CBT authoring essentials
  - Leadership: approvals, dashboards, oversight views
- add explicit responsive acceptance tests for top workflows
- optimize payloads and render cost for low-bandwidth school networks

---

## 24) Fastest Path to 10/10 (Top 5 Priorities)

1. Hard security controls:
- enforce 2FA for IT/Bursar/VP/Principal
- strengthen permission scopes beyond role-only checks
- introduce tamper-evident audit integrity for critical transitions

2. Bulletproof sync observability:
- per-record sync timeline (queued/retried/synced/conflict)
- conflict policy per domain (results, finance, attendance, elections)
- documented and scripted disaster recovery playbooks

3. Mobile-first UX + adoption polish:
- role-specific next-action dashboards
- reduced click depth + consistent autosave pattern
- teacher/student core tasks fully usable on phones/tablets

4. Court-proof exam integrity:
- immutable exam snapshots once activated
- attempt integrity bundle (events, timestamps, actor trail, session context)
- stronger runner resilience (resume-safe, crash-safe, controlled locking)

5. Go-live operations reliability:
- monitoring + alerting (queues, workers, sync failures, DB/disk health)
- restore drills with measured recovery objective
- final hardening checklist and rehearsed release runbook

---

## 25) Target Readiness Gate for Public Launch

NDGA can be treated as `10/10 operationally ready` when all are true:

- governance policy tests pass end-to-end on CI
- sync failure and recovery drills are validated on LAN and cloud
- mobile acceptance suite passes for Student + Teacher critical workflows
- immutable CBT activation and integrity bundle are in production
- security controls (2FA + audit integrity + backup restore proof) are signed off
