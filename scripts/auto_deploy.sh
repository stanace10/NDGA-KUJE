#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${NDGA_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BRANCH="${NDGA_DEPLOY_BRANCH:-main}"
COMPOSE_FILE="${NDGA_COMPOSE_FILE:-$PROJECT_DIR/deploy/docker/docker-compose.cloud.yml}"
ENV_FILE="${NDGA_ENV_FILE:-$PROJECT_DIR/deploy/docker/.env.cloud}"
WEB_SERVICE="${NDGA_WEB_SERVICE:-web}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cd "$PROJECT_DIR"

if [ ! -f "$ENV_FILE" ]; then
  log "Missing env file: $ENV_FILE"
  exit 1
fi

log "Pulling latest code from origin/$BRANCH"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

log "Rebuilding Docker services with $ENV_FILE"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build --remove-orphans

log "Waiting for $WEB_SERVICE to accept management commands"
ready=0
for attempt in $(seq 1 24); do
  if docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" python manage.py check >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done
if [ "$ready" -ne 1 ]; then
  log "Web service did not become ready in time"
  exit 1
fi

log "Running migrations"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" python manage.py migrate --noinput

log "Ensuring default leadership accounts"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" python manage.py ensure_default_portal_accounts

log "Collecting static"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T "$WEB_SERVICE" python manage.py collectstatic --noinput

log "Deployment finished"
