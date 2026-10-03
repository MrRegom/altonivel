#!/usr/bin/env bash
# Instala o actualiza la app EN EL SERVIDOR (se ejecuta allá, no en el PC).
#
# Primera vez:
#   git clone https://github.com/MrRegom/altonivel.git /opt/altonivel
#   cd /opt/altonivel && bash servidor.sh
#
# Actualizar después de subir cambios a GitHub:
#   cd /opt/altonivel && bash servidor.sh
#
# Puerto distinto:  APP_PORT=8091 bash servidor.sh
set -euo pipefail
cd "$(dirname "$0")"

APP_PORT="${APP_PORT:-8090}"
IP=$(hostname -I | awk '{print $1}')

echo "==> Descargando la última versión"
git pull --ff-only

# El puerto debe estar libre (salvo que ya sea de esta app).
if ss -ltn "( sport = :$APP_PORT )" | grep -q LISTEN \
   && ! docker ps --format '{{.Names}}' | grep -q '^altonivel-web$'; then
  echo "ERROR: el puerto $APP_PORT ya está en uso por otra aplicación. Usa: APP_PORT=<otro> bash servidor.sh" >&2
  exit 1
fi

# Primera vez: crea .env.produccion con una clave secreta propia del servidor.
if [ ! -f .env.produccion ]; then
  cp .env.produccion.example .env.produccion
  CLAVE=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
  sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$CLAVE|" .env.produccion
  sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=$IP|" .env.produccion
  sed -i "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=http://$IP:$APP_PORT|" .env.produccion
  chmod 600 .env.produccion
  echo "    Creado .env.produccion (edítalo para configurar el correo)."
fi

echo "==> Construyendo y levantando contenedores"
APP_PORT="$APP_PORT" docker compose up -d --build
docker compose exec -T web python manage.py cargar_emisor_demo >/dev/null 2>&1 || true
docker image prune -f >/dev/null
docker compose ps

echo
echo "==> Listo: http://$IP:$APP_PORT/"
if ! docker compose exec -T web python manage.py shell -c "from django.contrib.auth.models import User; exit(0 if User.objects.exists() else 1)" >/dev/null 2>&1; then
  echo "    Falta crear el usuario administrador:"
  echo "    docker compose exec web python manage.py admin_rut <tu-rut>"
fi
