"""Emisor falso para desarrollo.

No envía nada al SII: asigna un folio secuencial en memoria de base de
datos y marca el documento como aceptado. Sirve para probar todo el flujo
de la app (cotizar -> facturar -> correo) sin una cuenta real ni
certificado. NUNCA usar en producción.
"""
from __future__ import annotations

import itertools

from facturacion.base import DTEData, DTEResult, EmisorDTE
from facturacion.constants import EstadoSII

_contador = itertools.count(1)


class EmisorConsola(EmisorDTE):
    nombre = "consola"

    def emitir(self, dte: DTEData) -> DTEResult:
        folio = next(_contador)
        xml = f"<!-- DTE simulado tipo {dte.tipo_dte} folio {folio} -->".encode()
        return DTEResult(
            exito=True,
            estado=EstadoSII.ACEPTADO,
            folio=folio,
            track_id=f"SIMUL-{folio}",
            xml_bytes=xml,
            pdf_bytes=None,
            mensaje="Documento simulado (backend consola).",
        )

    def consultar_estado(self, track_id: str) -> str:
        return EstadoSII.ACEPTADO
