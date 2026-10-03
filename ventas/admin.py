from django.contrib import admin, messages

from facturacion.constants import EstadoSII, TipoDTE
from facturacion.exceptions import DatosInvalidosError, EmisionError

from .models import Cotizacion, DocumentoTributario, ItemCotizacion
from . import services


def _informar_emision(modeladmin, request, doc):
    if doc.estado_sii == EstadoSII.RECHAZADO:
        modeladmin.message_user(
            request, f"Rechazado: {doc.error_mensaje}", messages.ERROR
        )
        return
    modeladmin.message_user(
        request,
        f"{doc.get_tipo_dte_display()} folio {doc.folio}: "
        f"{doc.get_estado_sii_display()} ({doc.emisor_backend}).",
    )
    if doc.advertencias:
        modeladmin.message_user(
            request, f"Advertencias del proveedor: {doc.advertencias}", messages.WARNING
        )


class ItemInline(admin.TabularInline):
    model = ItemCotizacion
    extra = 1
    fields = ("descripcion", "producto", "cantidad", "precio_unitario", "exento")


@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    list_display = ("numero", "cliente", "fecha", "estado", "total")
    list_filter = ("estado", "fecha")
    search_fields = ("numero", "cliente__razon_social", "cliente__rut")
    inlines = [ItemInline]
    readonly_fields = ("numero", "enviada_en")
    actions = ["accion_enviar_correo", "accion_emitir_factura", "accion_emitir_factura_exenta"]

    @admin.display(description="Total")
    def total(self, obj):
        return obj.total

    @admin.action(description="Enviar cotización por correo al cliente")
    def accion_enviar_correo(self, request, queryset):
        for cot in queryset:
            try:
                services.enviar_cotizacion_por_correo(cot)
                self.message_user(request, f"Cotización {cot.numero} enviada.")
            except Exception as exc:
                self.message_user(request, f"Error en {cot.numero}: {exc}", messages.ERROR)

    def _emitir(self, request, queryset, tipo_dte):
        for cot in queryset:
            try:
                doc = services.emitir_documento(cot, tipo_dte)
            except DatosInvalidosError as exc:
                self.message_user(
                    request,
                    f"Cotización {cot.numero}: faltan datos. " + " ".join(exc.errores),
                    messages.ERROR,
                )
            except EmisionError as exc:
                self.message_user(
                    request,
                    f"Cotización {cot.numero}: {exc}. El documento quedó pendiente; "
                    "puede reintentarlo desde Documentos tributarios.",
                    messages.ERROR,
                )
            except ValueError as exc:
                self.message_user(request, str(exc), messages.ERROR)
            else:
                _informar_emision(self, request, doc)

    @admin.action(description="Emitir factura electrónica (33)")
    def accion_emitir_factura(self, request, queryset):
        self._emitir(request, queryset, TipoDTE.FACTURA_AFECTA)

    @admin.action(description="Emitir factura exenta (34)")
    def accion_emitir_factura_exenta(self, request, queryset):
        self._emitir(request, queryset, TipoDTE.FACTURA_EXENTA)


@admin.register(DocumentoTributario)
class DocumentoTributarioAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "cliente", "tipo_dte", "folio", "estado_sii", "total", "fecha_emision",
        "enviado_al_cliente_en",
    )
    list_filter = ("tipo_dte", "estado_sii", "fecha_emision")
    search_fields = ("folio", "cliente__razon_social", "cliente__rut", "track_id")
    readonly_fields = (
        "track_id", "emisor_backend", "clave_idempotencia", "error_mensaje",
        "advertencias", "enviado_al_cliente_en",
    )
    actions = ["accion_actualizar_estado", "accion_reintentar", "accion_enviar_correo"]

    @admin.action(description="Actualizar estado ante el SII")
    def accion_actualizar_estado(self, request, queryset):
        for doc in queryset:
            try:
                services.actualizar_estado(doc)
                self.message_user(
                    request, f"{doc}: {doc.get_estado_sii_display()}."
                )
            except EmisionError as exc:
                self.message_user(request, f"{doc}: {exc}", messages.ERROR)

    @admin.action(description="Reintentar emisión (documentos pendientes)")
    def accion_reintentar(self, request, queryset):
        for doc in queryset:
            try:
                services.reintentar_emision(doc)
            except (EmisionError, ValueError) as exc:
                self.message_user(request, f"{doc}: {exc}", messages.ERROR)
            else:
                _informar_emision(self, request, doc)

    @admin.action(description="Enviar documento por correo al cliente")
    def accion_enviar_correo(self, request, queryset):
        for doc in queryset:
            try:
                services.enviar_documento_por_correo(doc)
                self.message_user(request, f"Documento {doc.folio} enviado.")
            except Exception as exc:
                self.message_user(request, f"Error: {exc}", messages.ERROR)
