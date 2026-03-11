#!/usr/bin/env bash
set -euo pipefail
python manage.py ops_runtime_snapshot "$@"
