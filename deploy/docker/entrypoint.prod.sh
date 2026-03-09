#!/usr/bin/env sh
set -e

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings.prod}"

if [ "$DJANGO_SETTINGS_MODULE" = "core.settings.local" ]; then
  echo "Refusing to start production container with core.settings.local" >&2
  exit 1
fi

if [ -z "${DJANGO_SECRET_KEY:-}" ] || [ "$DJANGO_SECRET_KEY" = "ndga-dev-only-secret-key-change-before-production" ]; then
  echo "DJANGO_SECRET_KEY must be set to a real production secret." >&2
  exit 1
fi

python manage.py migrate --noinput
python manage.py ensure_default_portal_accounts
python manage.py collectstatic --noinput

exec gunicorn core.asgi:application \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
