# Security Edge And Deployment Runbook

This runbook covers the non-app hardening steps for the NDGA portal and the current deployment posture.

## Current Hardening In Repo

- `.env.lan` and `.env.cloud` are now treated as local-only secret files and should not be committed.
- Payment webhooks now require signature checks.
- Manual finance delta export now supports token validation, IP allow-list checks, payload signing, and optional AES-256-GCM encryption.
- Cloud deployment no longer depends on a clean `git pull` on EC2. GitHub Actions now ships a deploy bundle directly to the server.
- Cloud PostgreSQL and Redis are no longer exposed on host loopback ports through `docker-compose.cloud.yml`. They stay on the Docker network for app containers only.
- Dependency audit is now automated in GitHub Actions with `pip-audit`.

## Cloudflare / WAF

Cloudflare itself is not enabled from Django code. It must be switched on at the DNS and edge level.

Recommended setup:

1. Put `ndgakuje.org` and `portal.ndgakuje.org` behind Cloudflare proxied DNS.
2. Enable:
   - WAF managed rules
   - bot fight mode
   - rate limiting for `/auth/login/`
   - rate limiting for `/finance/gateway/webhook/*`
3. Keep origin TLS in `Full (strict)` mode.
4. Restrict origin access so only Cloudflare and school LAN/manual sync IPs can reach the public web ports.

Recommended firewall posture on EC2:

- allow `80/443` only from Cloudflare proxy IP ranges
- allow SSH only from trusted admin IPs
- deny direct public access to database and Redis entirely

## Database Private-Network Isolation

Cloud database isolation is now enforced at the compose layer:

- `db` is no longer published to a host port
- `redis` is no longer published to a host port
- only app containers on the Docker network can reach them

Additional recommended host checks:

1. Confirm no system PostgreSQL or Redis service is listening publicly.
2. Confirm security groups do not open `5432` or `6379`.
3. Keep backups and restore drills separate from direct DB exposure.

## AES Manual Sync Transport

Manual finance delta export can now be encrypted with AES-256-GCM.

Required environment variables:

- `SYNC_PAYLOAD_ENCRYPTION_ENABLED=True`
- `SYNC_PAYLOAD_ENCRYPTION_KEY=<32-byte base64url key>`

These values belong in the local env files on LAN and cloud, not in git.

Optional rotation:

- `SYNC_PAYLOAD_ENCRYPTION_KEY_FALLBACKS=<comma-separated old keys>`

Notes:

- signing still runs alongside encryption
- LAN verifies signature first, then decrypts
- payloads remain manual and scoped, not full-database sync

Generate a new 32-byte key with Python:

```python
import base64, os
print(base64.urlsafe_b64encode(os.urandom(32)).decode())
```

## Deployment Flow

Current cloud deployment is bundle-based:

1. GitHub Actions checks out the repo.
2. It creates `ndga-deploy-bundle.tar.gz`.
3. The bundle is copied to EC2 over SSH.
4. `scripts/deploy_bundle.sh` extracts it into the project directory.
5. Docker rebuild, migrations, static collection, and health checks run.

This avoids deployment failure caused by:

- dirty remote git working trees
- missing GitHub credentials on the server
- manual archive copying from a local workstation

## Dependency Audit

GitHub Actions now runs `pip-audit` against `requirements.txt`.

Use it to catch:

- vulnerable Python packages
- outdated transitive security dependencies

Treat failures as deployment blockers for finance- or auth-related packages.
