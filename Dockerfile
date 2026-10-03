FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_DB_PATH=/app/data/db.sqlite3 \
    DJANGO_MEDIA_ROOT=/app/data/media

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Normaliza el script de entrada (por si viene con saltos de línea de Windows)
# y genera los estáticos dentro de la imagen.
RUN sed -i 's/\r$//' docker/entrypoint.sh \
 && chmod +x docker/entrypoint.sh \
 && DJANGO_SECRET_KEY=build DJANGO_DEBUG=False python manage.py collectstatic --noinput \
 && useradd --create-home --uid 1000 app \
 && mkdir -p /app/data/media \
 && chown -R app:app /app/data

USER app
VOLUME ["/app/data"]
EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "90", "--access-logfile", "-"]
