#!/bin/bash
set -e

echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || true

echo "Applying database schemas and migrations..."
# Using migrate_schemas because django-tenants is used
python manage.py migrate_schemas --shared
python manage.py migrate_schemas

echo "Starting Gunicorn server for High Performance..."
# 4 workers and 4 threads per worker is a solid baseline for I/O bound Django apps
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 4 --threads 4 --timeout 120 --access-logfile - --error-logfile -
