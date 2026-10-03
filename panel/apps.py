from django.apps import AppConfig


class PanelConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "panel"
    verbose_name = "Panel de gestión"

    def ready(self):
        from django.contrib import admin

        admin.site.site_header = "Alto Nivel"
        admin.site.site_title = "Alto Nivel"
        admin.site.index_title = "Administración"
        # El enlace "Ver sitio" se reemplaza por "Volver al panel" (templates/admin/base_site.html).
        admin.site.site_url = None
