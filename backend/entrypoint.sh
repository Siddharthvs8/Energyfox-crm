#!/bin/bash
set -e

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

echo "Applying database migrations..."
# Single-tenant install (django-tenants was removed) — plain migrate.
python manage.py migrate --noinput

echo "Starting Gunicorn..."
# Sized for ~50 concurrent users on a t3.medium: (2 x vCPU) + 1 workers, a few
# threads each for I/O-bound Django. Tune WEB_CONCURRENCY / GUNICORN_THREADS via env.
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${WEB_CONCURRENCY:-5}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout 120 \
  --max-requests 1000 --max-requests-jitter 100 \
  --access-logfile - --error-logfile -
