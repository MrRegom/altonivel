from django.contrib import admin

from .models import Cliente


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("razon_social", "rut_formateado", "comuna", "correo", "activo")
    search_fields = ("razon_social", "rut", "correo")
    list_filter = ("activo", "comuna")
