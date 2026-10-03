#!/bin/sh
set -e

mkdir -p /app/data/media
python manage.py migrate --noinput

exec "$@"
