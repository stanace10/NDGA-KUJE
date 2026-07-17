#!/bin/sh
set -eu

: "${DB_NAME:?DB_NAME is required}"
: "${DB_USER:?DB_USER is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

mkdir -p /run/pgbouncer /var/log/pgbouncer
chown -R postgres:postgres /run/pgbouncer /var/log/pgbouncer
rm -f /run/pgbouncer/pgbouncer.pid
envsubst < /etc/pgbouncer/pgbouncer.ini.template > /run/pgbouncer/pgbouncer.ini
printf '"%s" "%s"\n' "$DB_USER" "$DB_PASSWORD" > /run/pgbouncer/userlist.txt
chmod 600 /run/pgbouncer/userlist.txt
chown postgres:postgres /run/pgbouncer/pgbouncer.ini /run/pgbouncer/userlist.txt

exec su-exec postgres pgbouncer /run/pgbouncer/pgbouncer.ini
