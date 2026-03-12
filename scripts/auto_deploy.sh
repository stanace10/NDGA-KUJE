#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${NDGA_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BRANCH="${NDGA_DEPLOY_BRANCH:-main}"
PRIMARY_COMPOSE_FILE="${NDGA_COMPOSE_FILE:-$PROJECT_DIR/docker-compose.cloud.yml}"
OVERRIDE_COMPOSE_FILE="${NDGA_COMPOSE_OVERRIDE_FILE:-$PROJECT_DIR/docker-compose.cloud.override.yml}"
ENV_FILE="${NDGA_ENV_FILE:-$PROJECT_DIR/.env.cloud}"
WEB_SERVICE="${NDGA_WEB_SERVICE:-web}"
COMPOSE_FILES=("$PRIMARY_COMPOSE_FILE")

if [ -f "$OVERRIDE_COMPOSE_FILE" ]; then
  COMPOSE_FILES+=("$OVERRIDE_COMPOSE_FILE")
fi

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

compose() {
  local compose_args=()
  local compose_file
  for compose_file in "${COMPOSE_FILES[@]}"; do
    compose_args+=(-f "$compose_file")
  done
  docker compose --env-file "$ENV_FILE" "${compose_args[@]}" "$@"
}

cd "$PROJECT_DIR"

if [ ! -f "$ENV_FILE" ]; then
  log "Missing env file: $ENV_FILE"
  exit 1
fi
if [ ! -f "$PRIMARY_COMPOSE_FILE" ]; then
  log "Missing compose file: $PRIMARY_COMPOSE_FILE"
  exit 1
fi

log "Pulling latest code from origin/$BRANCH"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"

if [ ${#COMPOSE_FILES[@]} -gt 1 ]; then
  log "Using compose files: ${COMPOSE_FILES[*]}"
else
  log "Using compose file: ${COMPOSE_FILES[0]}"
fi

log "Rebuilding Docker services with $ENV_FILE"
compose up -d --build --remove-orphans

log "Waiting for $WEB_SERVICE to accept management commands"
ready=0
for attempt in $(seq 1 24); do
  if compose exec -T "$WEB_SERVICE" python manage.py check >/dev/null 2>&1; then
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
compose exec -T "$WEB_SERVICE" python manage.py migrate --noinput

log "Ensuring default leadership accounts"
compose exec -T "$WEB_SERVICE" python manage.py ensure_default_portal_accounts

log "Collecting static"
compose exec -T "$WEB_SERVICE" python manage.py collectstatic --noinput

log "Restarting application services"
compose restart web celery_worker celery_beat

log "Current compose status"
compose ps

log "Checking public health endpoint"
curl -fsSI https://ndgakuje.org/ops/healthz/

log "Deployment finished"


