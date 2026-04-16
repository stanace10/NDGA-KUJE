# NDGA Deploy Readiness - 2026-04-15

## Current State

- Student finance `Pay Now` flow is working on LAN for both `Paystack` and `Flutterwave`.
- Public admissions payment initialization is already working on LAN.
- The pending dashboard migration issue is fixed and applied on LAN.
- The repository is still not push-ready because there is a large unreviewed diff across many app areas.

## Environment Checklist

### `.env.lan`

- `PAYSTACK_SECRET_KEY`: present, `TEST`
- `FLUTTERWAVE_SECRET_KEY`: present, `TEST`
- `SYNC_NODE_ROLE`: `LAN`
- `SYNC_CLOUD_ENDPOINT`: not set
- `SYNC_PULL_ENABLED`: `False`
- `SYNC_MANUAL_MODE`: `True`
- `SYNC_LAN_RESULTS_ONLY_MODE`: `True`

### `.env.cloud`

- `PAYSTACK_SECRET_KEY`: present, `TEST`
- `FLUTTERWAVE_SECRET_KEY`: not set
- `SYNC_NODE_ROLE`: `CLOUD`
- `SYNC_CLOUD_ENDPOINT`: set to cloud sync API
- `SYNC_PULL_ENABLED`: `True`
- `SYNC_MANUAL_MODE`: `True`

## Migration Status

- Fixed:
  - `apps/dashboard/migrations/0012_rename_dashboard_p_referen_fcd76f_idx_dashboard_p_referen_8f3f82_idx_and_more.py`
- Verified:
  - `python manage.py makemigrations --check --dry-run` returns `No changes detected` in LAN container

## Sync Audit

### What exists now

- Generic model sync supports:
  - `accounts.user`
  - `accounts.studentprofile`
  - `finance.payment`
  - `finance.receipt`
  - `finance.paymentgatewaytransaction`
- Dedicated student registration sync exists:
  - `queue_student_registration_sync(...)`
  - inbound handler `_apply_student_registration_event(...)`

### What blocks the intended cloud/LAN flow right now

- LAN cannot pull cloud updates because:
  - `SYNC_CLOUD_ENDPOINT` is blank on LAN
  - `SYNC_PULL_ENABLED=False` on LAN
- LAN is in results-only mode:
  - `SYNC_LAN_RESULTS_ONLY_MODE=True`
  - this blocks non-results generic sync and blocks inbound remote outbox
- Cloud does not have Flutterwave configured
- Public admission registrations are not yet part of generic model sync config:
  - `dashboard.publicsitesubmission` is not in `GENERIC_MODEL_SYNC_CONFIG`

### Result against the target flow

- Target wanted:
  - cloud -> LAN: students, payments, admission registrations
  - LAN -> cloud: receipts, results
- Current reality:
  - students: partially supported by dedicated registration sync
  - payments/receipts: model sync support exists, but LAN pull config blocks the workflow
  - admission registrations: not yet wired into sync model coverage
  - results: LAN results-only mode supports this direction better than the others

## Git Readiness

- Working tree is still heavily dirty
- `git diff --stat` shows a very large multi-area change set
- There are many modified files plus new files not yet reviewed as a release batch
- This should not be pushed to GitHub/AWS as-is without a final review pass

## Required Before GitHub And AWS

1. Replace test payment keys with live keys where production is intended.
2. Configure Flutterwave on cloud if both gateways must work there.
3. Decide whether LAN should remain results-only.
4. If not, disable `SYNC_LAN_RESULTS_ONLY_MODE` and configure:
   - `SYNC_CLOUD_ENDPOINT`
   - `SYNC_PULL_ENABLED=True`
5. Add admission registration sync coverage for `PublicSiteSubmission` if those records must move from cloud to LAN.
6. Review the large working tree and separate deployable changes from unfinished work.
7. Only after that: push to GitHub, then deploy to AWS.

## Recommended Release Order

1. Freeze public website + student portal scope.
2. Finalize env values for cloud and LAN.
3. Finalize sync policy for:
   - students
   - payments
   - receipts
   - admission registrations
4. Clean and review git diff.
5. Push to GitHub.
6. Deploy cloud.
7. Reconnect LAN sync to the cloud endpoint.
