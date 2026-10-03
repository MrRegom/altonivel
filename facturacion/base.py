"""Contrato común de todos los emisores de DTE.

La app de ventas SOLO conoce esta interfaz. Cambiar de proveedor
(OpenFactura, SimpleAPI) o pasar a integración directa con el SII no
requiere tocar la lógica de negocio: se cambia el backend en settings.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from facturacion.montos import redondear


@dataclass
class Emisor:
    """Datos de la empresa que emite, tal como están registrados en el SII."""

    rut: str
    razon_social: str
    giro: str
    actividades: list[int]
    direccion: str
    comuna: str
    ciudad: str = ""
    codigo_sucursal: str = ""
    correo: str = ""
    telefono: str = ""


@dataclass
class Receptor:
    rut: str
    razon_social: str
    giro: str = ""
    direccion: str = ""
    comuna: str = ""
    ciudad: str = ""
    correo: str = ""
    contacto: str = ""


@dataclass
class LineaDTE:
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    exento: bool = False

    @property
    def monto(self) -> Decimal:
        return redondear(self.cantidad * self.precio_unitario)


@dataclass
class Referencia:
    """Documento al que hace referencia el DTE (obligatorio en notas de crédito/débito).

    `codigo`: 1 = anula documento, 2 = corrige texto, 3 = corrige montos.
    """

    tipo_documento: str
    folio: str
    fecha: date
    codigo: Optional[int] = None
    razon: str = ""


@dataclass
class DTEData:
    """Datos neutrales de un DTE, independientes del proveedor."""

    tipo_dte: int
    emisor: Emisor
    receptor: Receptor
    lineas: list[LineaDTE]
    fecha_emision: date
    #: 1 = contado, 2 = crédito, 3 = sin costo. None = no se informa.
    forma_pago: Optional[int] = None
    referencias: list[Referencia] = field(default_factory=list)
    #: Texto libre que se muestra en la representación impresa (ej: cotización de origen).
    nota: str = ""
    #: Clave única por documento: permite reintentar sin emitir dos veces.
    clave_idempotencia: str = ""


@dataclass
class DTEResult:
    """Resultado neutral de una emisión."""

    exito: bool
    estado: str
    folio: Optional[int] = None
    track_id: str = ""
    xml_bytes: Optional[bytes] = None
    pdf_bytes: Optional[bytes] = None
    mensaje: str = ""
    advertencias: list[str] = field(default_factory=list)
    datos_crudos: dict = field(default_factory=dict)


class EmisorDTE(ABC):
    """Interfaz que todo backend de emisión debe implementar.

    Convención de errores:
    - Datos rechazados (el documento NO se emitió): devolver DTEResult(exito=False).
    - Falla transitoria o resultado incierto (red, timeout, 5xx, límite de
      peticiones): lanzar EmisionError. El documento queda pendiente y se
      puede reintentar con la misma `clave_idempotencia`.
    """

    #: nombre corto del backend, se guarda en el documento emitido.
    nombre = "base"

    @abstractmethod
    def emitir(self, dte: DTEData) -> DTEResult:
        """Emite el DTE y devuelve folio, XML y PDF timbrados."""

    @abstractmethod
    def consultar_estado(self, track_id: str) -> str:
        """Consulta el estado del documento ante el SII (valor de EstadoSII)."""
