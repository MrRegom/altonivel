"""Validaciones previas al envío y largos máximos de campos del SII.

Detectar los errores antes de enviar evita rechazos y deja un mensaje
claro para el usuario (ej: "falta el giro del cliente").
"""
from __future__ import annotations

from decimal import Decimal

from facturacion.base import DTEData
from facturacion.constants import TipoDTE

# Largos máximos según el formato de documentos electrónicos del SII.
LARGO_MAXIMO = {
    "RznSoc": 100,
    "GiroEmis": 80,
    "DirOrigen": 70,
    "CmnaOrigen": 20,
    "CiudadOrigen": 20,
    "RznSocRecep": 100,
    "GiroRecep": 40,
    "Contacto": 80,
    "CorreoRecep": 80,
    "DirRecep": 70,
    "CmnaRecep": 20,
    "CiudadRecep": 20,
    "NmbItem": 80,
    "DscItem": 1000,
    "RazonRef": 90,
}

MAX_ACTIVIDADES = 4

# Documentos que exigen datos completos del receptor (giro, dirección, comuna).
_EXIGEN_RECEPTOR_COMPLETO = {
    TipoDTE.FACTURA_AFECTA,
    TipoDTE.FACTURA_EXENTA,
    TipoDTE.NOTA_DEBITO,
    TipoDTE.NOTA_CREDITO,
}


def recortar(texto: str, campo: str) -> str:
    """Ajusta el texto al largo máximo que acepta el SII para ese campo."""
    return " ".join((texto or "").split())[: LARGO_MAXIMO[campo]]


def validar_dte(dte: DTEData) -> list[str]:
    """Devuelve la lista de problemas encontrados (vacía si está todo bien)."""
    errores: list[str] = []

    em = dte.emisor
    for valor, nombre in [
        (em.rut, "RUT"),
        (em.razon_social, "razón social"),
        (em.giro, "giro"),
        (em.direccion, "dirección"),
        (em.comuna, "comuna"),
    ]:
        if not (valor or "").strip():
            errores.append(f"Empresa emisora: falta {nombre}.")
    if not em.actividades:
        errores.append("Empresa emisora: falta el código de actividad económica.")
    elif len(em.actividades) > MAX_ACTIVIDADES:
        errores.append(
            f"Empresa emisora: máximo {MAX_ACTIVIDADES} códigos de actividad."
        )

    rec = dte.receptor
    if not (rec.rut or "").strip():
        errores.append("Cliente: falta RUT.")
    if not (rec.razon_social or "").strip():
        errores.append("Cliente: falta razón social.")
    if dte.tipo_dte in _EXIGEN_RECEPTOR_COMPLETO:
        for valor, nombre in [
            (rec.giro, "giro"),
            (rec.direccion, "dirección"),
            (rec.comuna, "comuna"),
        ]:
            if not (valor or "").strip():
                errores.append(f"Cliente: falta {nombre} (obligatorio para facturar).")

    if not dte.lineas:
        errores.append("El documento no tiene ítems.")
    for n, linea in enumerate(dte.lineas, start=1):
        if not (linea.descripcion or "").strip():
            errores.append(f"Ítem {n}: falta la descripción.")
        if linea.cantidad <= 0:
            errores.append(f"Ítem {n}: la cantidad debe ser mayor que cero.")
        if linea.precio_unitario < 0:
            errores.append(f"Ítem {n}: el precio no puede ser negativo.")

    if dte.lineas:
        hay_afectos = any(not l.exento for l in dte.lineas)
        if dte.tipo_dte == TipoDTE.FACTURA_EXENTA and hay_afectos:
            errores.append(
                "La factura exenta solo puede tener ítems exentos. "
                "Marque los ítems como exentos o emita factura afecta (33)."
            )
        if dte.tipo_dte == TipoDTE.FACTURA_AFECTA and not hay_afectos:
            errores.append(
                "Todos los ítems son exentos: corresponde emitir factura exenta (34)."
            )
        if sum((l.monto for l in dte.lineas), Decimal("0")) <= 0:
            errores.append("El total del documento debe ser mayor que cero.")

    if dte.tipo_dte in (TipoDTE.NOTA_CREDITO, TipoDTE.NOTA_DEBITO) and not dte.referencias:
        errores.append("Las notas de crédito y débito deben referenciar un documento.")

    return errores
