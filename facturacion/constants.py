"""Constantes tributarias del SII usadas en todo el proyecto."""
from decimal import Decimal

# Tasa de IVA vigente en Chile.
TASA_IVA = Decimal("0.19")


class TipoDTE:
    """Códigos de Documento Tributario Electrónico del SII."""

    FACTURA_AFECTA = 33
    FACTURA_EXENTA = 34
    BOLETA_AFECTA = 39
    BOLETA_EXENTA = 41
    GUIA_DESPACHO = 52
    NOTA_DEBITO = 56
    NOTA_CREDITO = 61

    CHOICES = [
        (FACTURA_AFECTA, "Factura electrónica (afecta)"),
        (FACTURA_EXENTA, "Factura electrónica exenta"),
        (BOLETA_AFECTA, "Boleta electrónica"),
        (BOLETA_EXENTA, "Boleta electrónica exenta"),
        (GUIA_DESPACHO, "Guía de despacho"),
        (NOTA_DEBITO, "Nota de débito"),
        (NOTA_CREDITO, "Nota de crédito"),
    ]


class EstadoSII:
    """Estado de un documento frente al SII."""

    PENDIENTE = "pendiente"      # aún no enviado
    ENVIADO = "enviado"          # enviado, esperando aceptación
    ACEPTADO = "aceptado"        # aceptado por el SII
    ACEPTADO_REPAROS = "aceptado_reparos"
    RECHAZADO = "rechazado"
    ANULADO = "anulado"

    CHOICES = [
        (PENDIENTE, "Pendiente de envío"),
        (ENVIADO, "Enviado al SII"),
        (ACEPTADO, "Aceptado"),
        (ACEPTADO_REPAROS, "Aceptado con reparos"),
        (RECHAZADO, "Rechazado"),
        (ANULADO, "Anulado"),
    ]
