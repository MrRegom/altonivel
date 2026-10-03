"""Catálogo de productos y servicios."""
from django.db import models

from core.models import TimeStampedModel


class Producto(TimeStampedModel):
    """Ítem reutilizable para armar cotizaciones rápido."""

    codigo = models.CharField(max_length=50, blank=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio_neto = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    exento = models.BooleanField(
        default=False, help_text="Marcar si el ítem no está afecto a IVA."
    )
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre
