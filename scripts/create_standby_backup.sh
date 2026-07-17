#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${1:-docker-compose.cloud.yml}"
ENV_FILE="${2:-.env.cloud}"
WEB_SERVICE="${3:-web}"
OUTPUT_DIR="${4:-backups/standby}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_PATH="$PROJECT_DIR/$COMPOSE_FILE"
ENV_PATH="$PROJECT_DIR/$ENV_FILE"
OUTPUT_PATH="$PROJECT_DIR/$OUTPUT_DIR"

if [ ! -f "$COMPOSE_PATH" ]; then
  echo "Compose file not found: $COMPOSE_PATH" >&2
  exit 1
fi
if [ ! -f "$ENV_PATH" ]; then
  echo "Env file not found: $ENV_PATH" >&2
  exit 1
fi

mkdir -p "$OUTPUT_PATH"

stamp="$(date '+%Y%m%d_%H%M%S')"
local_dir="$OUTPUT_PATH/$stamp"
remote_dir="/tmp/ndga_standby_$stamp"
mkdir -p "$local_dir"

compose() {
  docker compose --env-file "$ENV_PATH" -f "$COMPOSE_PATH" "$@"
}

backup_output="$(compose exec -T "$WEB_SERVICE" python manage.py backup_ndga --output-dir "$remote_dir")"
printf '%s\n' "$backup_output"

remote_archive="$(printf '%s\n' "$backup_output" | sed -n 's/^Backup created:[[:space:]]*//p' | tail -n 1)"
if [ -z "$remote_archive" ]; then
  echo "Could not resolve backup archive path from backup_ndga output." >&2
  exit 1
fi

container_id="$(compose ps -q "$WEB_SERVICE" | tr -d '\r')"
if [ -z "$container_id" ]; then
  echo "Could not resolve container id for service '$WEB_SERVICE'." >&2
  exit 1
fi

docker cp "$container_id:$remote_archive" "$local_dir/"
compose exec -T "$WEB_SERVICE" python manage.py ops_runtime_snapshot > "$local_dir/ops_runtime_snapshot.json"

cat > "$local_dir/manifest.txt" <<EOF
created_at=$stamp
compose_file=$COMPOSE_FILE
env_file=$ENV_FILE
web_service=$WEB_SERVICE
archive_path=$remote_archive
EOF

printf 'Standby backup created: %s\n' "$local_dir"
