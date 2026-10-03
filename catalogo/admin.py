from django.contrib import admin

from .models import Producto


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "precio_neto", "exento", "activo")
    search_fields = ("nombre", "codigo")
    list_filter = ("activo", "exento")
