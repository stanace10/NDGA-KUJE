# Manual Update Runbook

NDGA now uses a strict LAN-first manual update model. This replaces automatic sync.

## Ownership

- `LAN` is the operational source of truth for:
  - staff and admin work
  - student profile updates
  - attendance entry and correction
  - result entry, vetting, approval, and publication
  - CBT authoring and school operations
  - bursary processing and receipts
  - internal admissions review
- `Cloud` is for:
  - the public website
  - student portal access
  - student online payment events
  - public admission registration intake

## What Moves From LAN To Cloud

Push these manually when school work has been confirmed:

- published results
- attendance updates
- student profile and enrolment updates
- theory and other staff-entered academic record changes that affect published student output
- bursary receipts

Command:

```powershell
docker exec ndga-web-1 python manage.py push_lan_updates_to_cloud
```

## What Moves From Cloud To LAN

Pull these manually into LAN:

- student payment records
- public admission registrations
- public admission payment status

Commands:

```powershell
docker exec ndga-web-1 python manage.py pull_cloud_payments_delta
docker exec ndga-web-1 python manage.py pull_cloud_admissions_delta
```

Combined command:

```powershell
docker exec ndga-web-1 python manage.py pull_cloud_updates_to_lan
```

## Hard Rules

- Do not re-enable background sync.
- Do not use cloud as a second staff/admin operations database.
- Do not expose staff, admin, bursar, CBT, or election portals on cloud.
- Do not push draft result rows to cloud.
- Do not pull staff/admin workflow data back from cloud.

## Goal

- LAN remains the school's working system.
- Cloud stays limited to public and student-facing access.
- Payments and public admissions still flow back into LAN deliberately.
- Result, attendance, profile, and receipt updates move to cloud deliberately.
