# NDGA Go-Live Checklist

## A. Infrastructure

- [ ] Ubuntu server provisioned and hardened (SSH keys only, firewall enabled)
- [ ] PostgreSQL provisioned (RDS or Supabase) with private networking rules
- [ ] Redis provisioned for cache/channels/celery
- [ ] S3 bucket (or Cloudinary account) created for media
- [ ] Brevo sender domain and API key configured

## B. Domain + TLS

- [ ] Domain purchased on Spaceship
- [ ] DNS records created for apex + required subdomains
- [ ] Nginx deployed with NDGA host map
- [ ] Let's Encrypt certificates issued for all portal hosts
- [ ] HTTPS redirect validated

## C. Application Configuration

- [ ] `DJANGO_SETTINGS_MODULE=core.settings.prod`
- [ ] `DJANGO_SECRET_KEY` set to a strong secret
- [ ] `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` set correctly
- [ ] `SESSION_COOKIE_SECURE=True` and `CSRF_COOKIE_SECURE=True`
- [ ] `NOTIFICATIONS_EMAIL_PROVIDER=brevo` and `BREVO_API_KEY` set
- [ ] `MEDIA_STORAGE_BACKEND` selected and credentials configured
- [ ] `SYNC_CLOUD_ENDPOINT` and `SYNC_ENDPOINT_AUTH_TOKEN` configured

## D. Data Protection + Recovery

- [ ] Run migration on production DB
- [ ] Create IT bootstrap account
- [ ] Run first backup archive (`backup_ndga`)
- [ ] Run first PostgreSQL custom dump (`pg_dump_custom.ps1` / `pg_dump -Fc`)
- [ ] Validate PostgreSQL restore (`pg_restore_custom.ps1` / `pg_restore`)
- [ ] Configure scheduled backups (DB snapshots + media)
- [ ] Configure media bucket sync backup (`media_sync_rclone.ps1` or equivalent)
- [ ] Validate restore process in a staging environment

## E. Observability

- [ ] `DJANGO_LOG_JSON=True` enabled
- [ ] Central log ingestion enabled (CloudWatch/ELK/etc.)
- [ ] Sentry DSN configured and test error received
- [ ] `/ops/healthz/` and `/ops/readyz/` wired into monitoring
- [ ] Audit retention schedule configured (`prune_audit_events`)

## F. NDGA Functional Gates

- [ ] Stage 0-19 test suite passes
- [ ] Subdomain routing and role guards validated
- [ ] CBT/Election forced re-auth validated
- [ ] Offline-to-online sync tested for CBT attempts and election votes
- [ ] Result workflow validated end-to-end (Teacher -> Dean -> Form -> VP/IT -> Publish)
- [ ] Receipt/report/election PDFs and QR verification validated

## G. Launch Readiness

- [ ] Stakeholder UAT signoff completed
- [ ] Rollback plan documented
- [ ] Incident contacts and escalation flow documented
- [ ] Deployment window approved
