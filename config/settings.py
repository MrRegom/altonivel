"""Configuración del proyecto de facturación."""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


# --- Carga simple de .env (sin dependencias externas) ---
def _cargar_env(ruta: Path) -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / ".env")


def env(clave: str, defecto: str = "") -> str:
    return os.environ.get(clave, defecto)


def env_bool(clave: str, defecto: bool = False) -> bool:
    return env(clave, str(defecto)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-inseguro-cambiar-en-produccion")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "*").split(",") if h]
# Orígenes desde los que se envían formularios (obligatorio en producción).
# Ej: http://157.245.131.99:8090,https://facturas.altonivel.cl
CSRF_TRUSTED_ORIGINS = [o for o in env("DJANGO_CSRF_TRUSTED_ORIGINS").split(",") if o]

if not DEBUG and SECRET_KEY.startswith("dev-inseguro"):
    raise RuntimeError("Define DJANGO_SECRET_KEY en producción.")

# Solo con HTTPS (detrás de un proxy como Caddy o nginx con certificado).
if env_bool("DJANGO_HTTPS", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # apps del proyecto
    "core",
    "clientes",
    "catalogo",
    "ventas",
    "facturacion",
    "panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "panel.context_processors.marca",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("DJANGO_DB_PATH") or BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Localización Chile ---
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "panel:inicio"
LOGOUT_REDIRECT_URL = "login"
MEDIA_URL = "media/"
MEDIA_ROOT = env("DJANGO_MEDIA_ROOT") or BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Correo ---
# En desarrollo se imprime en consola. En producción, configurar SMTP por env.
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "facturacion@example.com")


# --- Emisión de DTE ---
# Opciones: "consola" (dev), "openfactura", "sii_directo" (a futuro).
EMISOR_BACKEND = env("EMISOR_BACKEND", "consola")

# Enviar automáticamente el DTE (PDF + XML) al correo del cliente
# cuando el SII lo acepta.
ENVIAR_DTE_AL_ACEPTAR = env_bool("ENVIAR_DTE_AL_ACEPTAR", True)

# Muestra un aviso "MODO PRUEBA" en el panel cuando las facturas no son reales.
MODO_PRUEBA = env_bool(
    "MODO_PRUEBA",
    EMISOR_BACKEND == "consola"
    or (EMISOR_BACKEND == "openfactura" and "dev-api" in env("OPENFACTURA_BASE_URL", "https://dev-api.haulmer.com")),
)

OPENFACTURA = {
    "API_KEY": env("OPENFACTURA_API_KEY"),
    "BASE_URL": env("OPENFACTURA_BASE_URL", "https://dev-api.haulmer.com"),
    "TIMEOUT": int(env("OPENFACTURA_TIMEOUT", "30")),
}
