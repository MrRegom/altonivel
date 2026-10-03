"""Datos de la empresa emisora (quien factura)."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel
from core.rut import normalizar
from core.validators import validar_rut
from facturacion.base import Emisor
from facturacion.exceptions import ConfiguracionError
from facturacion.validacion import MAX_ACTIVIDADES


def _parsear_actividades(texto: str) -> list[int]:
    return [int(c) for c in (texto or "").replace(";", ",").replace(" ", "").split(",") if c]


def validar_actividades(valor: str) -> None:
    codigos = (valor or "").replace(";", ",").replace(" ", "").split(",")
    codigos = [c for c in codigos if c]
    if not codigos:
        raise ValidationError("Ingrese al menos un código de actividad económica.")
    if len(codigos) > MAX_ACTIVIDADES:
        raise ValidationError(f"El SII permite máximo {MAX_ACTIVIDADES} códigos.")
    for c in codigos:
        if not (c.isdigit() and len(c) == 6):
            raise ValidationError(f"Código inválido: {c!r}. Deben ser 6 dígitos (ej: 620200).")


class EmpresaEmisora(TimeStampedModel):
    """Empresa que emite los documentos. Debe existir un solo registro.

    Los datos deben coincidir EXACTAMENTE con los registrados en el SII
    (Mi SII > Datos personales y tributarios).
    """

    rut = models.CharField("RUT", max_length=12, validators=[validar_rut], help_text="Ej: 76192083-9")
    razon_social = models.CharField(
        "Razón social", max_length=100, help_text="Tal como aparece en el SII."
    )
    giro = models.CharField("Giro", max_length=80)
    actividades = models.CharField(
        "Códigos de actividad económica",
        max_length=30,
        validators=[validar_actividades],
        help_text="Código(s) de 6 dígitos del SII, separados por coma. Máximo 4.",
    )
    direccion = models.CharField("Dirección", max_length=70)
    comuna = models.CharField("Comuna", max_length=20)
    ciudad = models.CharField("Ciudad", max_length=20, blank=True)
    codigo_sucursal = models.CharField(
        "Código de sucursal SII",
        max_length=10,
        blank=True,
        help_text="Código de la dirección desde donde se factura (Mi SII > Direcciones). Ej: 88482059.",
    )
    correo = models.EmailField("Correo", max_length=80, blank=True)
    telefono = models.CharField("Teléfono", max_length=20, blank=True)
    nombre_fantasia = models.CharField(
        "Nombre de fantasía", max_length=80, blank=True,
        help_text="Nombre comercial que se muestra en la app y en las cotizaciones (ej: Alto Nivel).",
    )
    logo = models.ImageField("Logo", upload_to="empresa/", blank=True)
    sitio_web = models.CharField("Sitio web", max_length=100, blank=True)

    class Meta:
        verbose_name = "empresa emisora"
        verbose_name_plural = "empresa emisora"

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.rut})"

    @property
    def nombre_visible(self) -> str:
        return self.nombre_fantasia or self.razon_social

    def clean(self):
        if not self.pk and EmpresaEmisora.objects.exists():
            raise ValidationError("Ya existe una empresa emisora. Edite la existente.")

    def save(self, *args, **kwargs):
        self.rut = normalizar(self.rut)
        super().save(*args, **kwargs)

    @classmethod
    def actual(cls) -> "EmpresaEmisora":
        empresa = cls.objects.first()
        if empresa is None:
            raise ConfiguracionError(
                "No hay empresa emisora configurada. Cárguela en el admin "
                "(Facturación electrónica > Empresa emisora)."
            )
        return empresa

    def como_emisor(self) -> Emisor:
        return Emisor(
            rut=self.rut,
            razon_social=self.razon_social,
            giro=self.giro,
            actividades=_parsear_actividades(self.actividades),
            direccion=self.direccion,
            comuna=self.comuna,
            ciudad=self.ciudad,
            codigo_sucursal=self.codigo_sucursal,
            correo=self.correo,
            telefono=self.telefono,
        )
