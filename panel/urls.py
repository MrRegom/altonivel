from django.urls import path

from . import views

app_name = "panel"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("clientes/", views.clientes_lista, name="clientes"),
    path("clientes/nuevo/", views.cliente_form, name="cliente_nuevo"),
    path("clientes/<int:pk>/", views.cliente_detalle, name="cliente_detalle"),
    path("clientes/<int:pk>/editar/", views.cliente_form, name="cliente_editar"),
    path("productos/", views.productos_lista, name="productos"),
    path("productos/nuevo/", views.producto_form, name="producto_nuevo"),
    path("productos/<int:pk>/editar/", views.producto_form, name="producto_editar"),
    path("cotizaciones/", views.cotizaciones_lista, name="cotizaciones"),
    path("cotizaciones/nueva/", views.cotizacion_form, name="cotizacion_nueva"),
    path("cotizaciones/<int:pk>/", views.cotizacion_detalle, name="cotizacion_detalle"),
    path("cotizaciones/<int:pk>/editar/", views.cotizacion_form, name="cotizacion_editar"),
    path("cotizaciones/<int:pk>/pdf/", views.cotizacion_pdf, name="cotizacion_pdf"),
    path("cotizaciones/<int:pk>/enviar/", views.cotizacion_enviar, name="cotizacion_enviar"),
    path("cotizaciones/<int:pk>/estado/", views.cotizacion_estado, name="cotizacion_estado"),
    path("cotizaciones/<int:pk>/emitir/", views.cotizacion_emitir, name="cotizacion_emitir"),
    path("cotizaciones/<int:pk>/duplicar/", views.cotizacion_duplicar, name="cotizacion_duplicar"),
    path("facturas/", views.documentos_lista, name="documentos"),
    path("facturas/<int:pk>/", views.documento_detalle, name="documento_detalle"),
    path("facturas/<int:pk>/<str:accion>/", views.documento_accion, name="documento_accion"),
    path("facturas/<int:pk>/archivo/<str:formato>/", views.documento_archivo, name="documento_archivo"),
    path("configuracion/empresa/", views.empresa, name="empresa"),
    path("configuracion/usuarios/", views.usuarios_lista, name="usuarios"),
    path("configuracion/usuarios/nuevo/", views.usuario_form, name="usuario_nuevo"),
    path("configuracion/usuarios/<int:pk>/", views.usuario_form, name="usuario_editar"),
    path("configuracion/usuarios/<int:pk>/clave/", views.usuario_clave, name="usuario_clave"),
    path("mi-clave/", views.mi_clave, name="mi_clave"),
]
