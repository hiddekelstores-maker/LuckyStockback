#!/usr/bin/env bash
set -euo pipefail

cd backend
python manage.py migrate --noinput
python manage.py collectstatic --noinput || true
gunicorn stocknet.wsgi:application --bind 0.0.0.0:${PORT:-8000}
