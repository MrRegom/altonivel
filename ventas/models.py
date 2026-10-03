"""Cotizaciones y documentos tributarios emitidos."""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from catalogo.models import Producto
from clientes.models import Cliente
from core.models import TimeStampedModel
from facturacion.constants import EstadoSII, TASA_IVA, TipoDTE
from facturacion.montos import redondear


class EstadoCotizacion(models.TextChoices):
    BORRADOR = "borrador", "Borrador"
    ENVIADA = "enviada", "Enviada al cliente"
    ACEPTADA = "aceptada", "Aceptada"
    RECHAZADA = "rechazada", "Rechazada"
    FACTURADA = "facturada", "Facturada"
    VENCIDA = "vencida", "Vencida"


class Cotizacion(TimeStampedModel):
    numero = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="cotizaciones"
    )
    fecha = models.DateField(default=timezone.localdate)
    valida_hasta = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=20, choices=EstadoCotizacion.choices, default=EstadoCotizacion.BORRADOR
    )
    observaciones = models.TextField(blank=True)
    enviada_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "cotización"
        verbose_name_plural = "cotizaciones"
        ordering = ["-fecha", "-numero"]

    def __str__(self) -> str:
        return f"Cotización N°{self.numero or '(borrador)'} - {self.cliente}"

    def save(self, *args, **kwargs):
        if self.numero is None:
            ultimo = Cotizacion.objects.aggregate(m=models.Max("numero"))["m"] or 0
            self.numero = ultimo + 1
        super().save(*args, **kwargs)

    # --- Totales calculados a partir de los ítems ---
    @property
    def monto_exento(self) -> Decimal:
        return sum((i.subtotal for i in self.items.all() if i.exento), Decimal("0"))

    @property
    def monto_neto(self) -> Decimal:
        return sum((i.subtotal for i in self.items.all() if not i.exento), Decimal("0"))

    @property
    def iva(self) -> Decimal:
        return redondear(self.monto_neto * TASA_IVA)

    @property
    def total(self) -> Decimal:
        return self.monto_neto + self.iva + self.monto_exento

    @property
    def esta_vigente(self) -> bool:
        if not self.valida_hasta:
            return True
        return timezone.localdate() <= self.valida_hasta


class ItemCotizacion(TimeStampedModel):
    cotizacion = models.ForeignKey(
        Cotizacion, on_delete=models.CASCADE, related_name="items"
    )
    producto = models.ForeignKey(
        Producto, on_delete=models.SET_NULL, null=True, blank=True
    )
    descripcion = models.CharField(max_length=255)
    cantidad = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    exento = models.BooleanField(default=False)

    class Meta:
        verbose_name = "ítem de cotización"
        verbose_name_plural = "ítems de cotización"

    def __str__(self) -> str:
        return f"{self.descripcion} x{self.cantidad}"

    @property
    def subtotal(self) -> Decimal:
        return redondear(self.cantidad * self.precio_unitario)


class DocumentoTributario(TimeStampedModel):
    """DTE emitido (o en proceso de emisión) ante el SII."""

    cotizacion = models.ForeignKey(
        Cotizacion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documentos",
    )
    cliente = models.ForeignKey(
        Cliente, on_delete=models.PROTECT, related_name="documentos"
    )
    tipo_dte = models.IntegerField(
        choices=TipoDTE.CHOICES, default=TipoDTE.FACTURA_AFECTA
    )
    folio = models.PositiveIntegerField(null=True, blank=True)
    fecha_emision = models.DateField(default=timezone.localdate)

    monto_neto = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    monto_exento = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    iva = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    estado_sii = models.CharField(
        max_length=20, choices=EstadoSII.CHOICES, default=EstadoSII.PENDIENTE
    )
    track_id = models.CharField(max_length=100, blank=True)
    emisor_backend = models.CharField(max_length=40, blank=True)
    # Se envía al proveedor en cada intento: reintentar nunca duplica la emisión.
    clave_idempotencia = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    error_mensaje = models.TextField(blank=True)
    advertencias = models.TextField(blank=True)

    xml = models.FileField(upload_to="dte/xml/", null=True, blank=True)
    pdf = models.FileField(upload_to="dte/pdf/", null=True, blank=True)

    enviado_al_cliente_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "documento tributario"
        verbose_name_plural = "documentos tributarios"
        ordering = ["-fecha_emision", "-folio"]

    def __str__(self) -> str:
        etiqueta = dict(TipoDTE.CHOICES).get(self.tipo_dte, "DTE")
        return f"{etiqueta} N°{self.folio or 's/folio'} - {self.cliente}"
