"""Integración DIRECTA con los web services del SII (a futuro).

Este backend NO está implementado todavía. Documenta el camino completo
para cuando se decida integrar sin proveedor. Requiere trabajo
considerable y certificación previa ante el SII.

Pasos que debe cubrir esta implementación:

1. Autenticación
   - Pedir semilla:  CrSeed.jws  (maullin = certificación, palena = producción)
   - Firmar la semilla con el certificado digital (.pfx/.p12) del emisor.
   - Canjear por token:  GetTokenFromSeed.jws
2. Folios (CAF)
   - Solicitar/cargar los CAF por tipo de documento y llevar el control
     del rango de folios usados.
3. Construcción del DTE
   - Armar el XML según los XSD vigentes del SII (anexo técnico 2.5, 2026),
     codificación ISO-8859-1, en el orden exacto de campos.
4. Timbre electrónico (TED)
   - Firmar el TED con la llave privada incluida en el CAF y generar el
     código PDF417 para la representación impresa.
5. Firma del documento y del sobre (EnvioDTE) con XMLDSig.
6. Envío y seguimiento
   - Subir el sobre, consultar estado de envío y de DTE, manejar rechazos.
7. Intercambio con el receptor (acuse de recibo, aceptación/reclamo).

Bibliotecas de referencia para portar lógica: LibreDTE (PHP) y el módulo
l10n_cl de Odoo (Python).
"""
from __future__ import annotations

from facturacion.base import DTEData, DTEResult, EmisorDTE


class EmisorSIIDirecto(EmisorDTE):
    nombre = "sii_directo"

    def emitir(self, dte: DTEData) -> DTEResult:
        raise NotImplementedError(
            "La integración directa con el SII aún no está implementada. "
            "Ver el docstring de este módulo para el plan de trabajo."
        )

    def consultar_estado(self, track_id: str) -> str:
        raise NotImplementedError
