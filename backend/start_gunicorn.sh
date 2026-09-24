#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

# Activate virtual environment
source "$DIR/venv/bin/activate"

# Apply pending migrations
python manage.py migrate --noinput

# Start Gunicorn using the config file
exec gunicorn -c gunicorn.conf.py core.wsgi:application
