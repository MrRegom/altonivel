from django.contrib import admin

from .models import EmpresaEmisora


@admin.register(EmpresaEmisora)
class EmpresaEmisoraAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "rut", "giro", "comuna", "codigo_sucursal")
    fieldsets = (
        ("Identificación (igual que en el SII)", {
            "fields": ("rut", "razon_social", "giro", "actividades"),
        }),
        ("Dirección de emisión", {
            "fields": ("direccion", "comuna", "ciudad", "codigo_sucursal"),
        }),
        ("Contacto", {"fields": ("correo", "telefono", "sitio_web")}),
        ("Marca", {"fields": ("nombre_fantasia", "logo")}),
    )

    def has_add_permission(self, request):
        # Solo se permite un registro.
        return not EmpresaEmisora.objects.exists()
