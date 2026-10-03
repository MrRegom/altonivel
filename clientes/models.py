"""Modelo de clientes (receptores de los documentos)."""
from django.db import models

from core.models import TimeStampedModel
from core.rut import formatear, normalizar
from core.validators import validar_rut


class Cliente(TimeStampedModel):
    """Datos del receptor. Se ingresan una sola vez y se reutilizan."""

    rut = models.CharField(
        "RUT",
        max_length=12,
        unique=True,
        validators=[validar_rut],
        help_text="Ej: 76192083-9",
    )
    razon_social = models.CharField("Razón social", max_length=200)
    giro = models.CharField("Giro", max_length=200, blank=True)
    direccion = models.CharField("Dirección", max_length=200, blank=True)
    comuna = models.CharField("Comuna", max_length=100, blank=True)
    ciudad = models.CharField("Ciudad", max_length=100, blank=True)
    correo = models.EmailField("Correo electrónico", blank=True)
    telefono = models.CharField("Teléfono", max_length=30, blank=True)
    contacto = models.CharField("Nombre de contacto", max_length=120, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["razon_social"]

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.rut_formateado})"

    def save(self, *args, **kwargs):
        # Guardamos el RUT siempre normalizado al formato del SII.
        self.rut = normalizar(self.rut)
        super().save(*args, **kwargs)

    @property
    def rut_formateado(self) -> str:
        try:
            return formatear(self.rut)
        except Exception:
            return self.rut
