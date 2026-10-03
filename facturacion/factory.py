"""Selecciona el backend de emisión según la configuración."""
from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from facturacion.base import EmisorDTE
from facturacion.exceptions import ConfiguracionError

_BACKENDS = {
    "consola": "facturacion.providers.consola.EmisorConsola",
    "openfactura": "facturacion.providers.openfactura.EmisorOpenFactura",
    "sii_directo": "facturacion.providers.sii_directo.EmisorSIIDirecto",
}


def _importar(ruta: str):
    from importlib import import_module

    modulo, clase = ruta.rsplit(".", 1)
    return getattr(import_module(modulo), clase)


@lru_cache(maxsize=None)
def get_emisor(nombre: str | None = None) -> EmisorDTE:
    """Devuelve el emisor indicado o, si no se indica, el de settings.EMISOR_BACKEND.

    Pasar `nombre` sirve para consultar documentos emitidos con un backend
    anterior (ej: facturas de OpenFactura después de pasar a sii_directo).
    """
    nombre = nombre or getattr(settings, "EMISOR_BACKEND", "consola")
    ruta = _BACKENDS.get(nombre)
    if not ruta:
        raise ConfiguracionError(
            f"EMISOR_BACKEND desconocido: {nombre!r}. "
            f"Opciones: {', '.join(_BACKENDS)}"
        )
    return _importar(ruta)()
