"""Adaptador para la API de OpenFactura (Haulmer).

Referencia: https://docsapi-openfactura.haulmer.com/

Ambientes:
- Desarrollo: https://dev-api.haulmer.com (sin cuenta; usa API keys
  públicas de empresas de prueba y folios simulados, sin validez).
- Producción: https://api.haulmer.com (API key de la empresa real).

OpenFactura gestiona los folios (CAF) y el envío al SII. La emisión
devuelve un TOKEN de seguimiento; el estado ante el SII se consulta con
ese token (normalmente se resuelve en menos de 3 minutos).
"""
from __future__ import annotations

import base64
from decimal import Decimal

import requests
from django.conf import settings

from facturacion.base import DTEData, DTEResult, EmisorDTE
from facturacion.constants import TASA_IVA, EstadoSII, TipoDTE
from facturacion.exceptions import ConfiguracionError, EmisionError
from facturacion.montos import calcular_totales
from facturacion.validacion import recortar

RUTA_DOCUMENTO = "/v2/dte/document"

# Estados que devuelve OpenFactura en /document/{token}/status.
_ESTADOS = {
    "aceptado": EstadoSII.ACEPTADO,
    "aceptado con reparo": EstadoSII.ACEPTADO_REPAROS,
    "aceptado con reparos": EstadoSII.ACEPTADO_REPAROS,
    "rechazado": EstadoSII.RECHAZADO,
    "pendiente": EstadoSII.ENVIADO,
}

# Código de error de OpenFactura cuando la Idempotency-Key ya fue usada:
# el documento YA está emitido y la respuesta trae su token.
_ERROR_IDEMPOTENCIA = "OF-06"


def _numero(valor: Decimal):
    """Entero si no tiene decimales; si no, float (el SII acepta hasta 6)."""
    valor = Decimal(valor)
    if valor == valor.to_integral_value():
        return int(valor)
    return float(round(valor, 6))


class EmisorOpenFactura(EmisorDTE):
    nombre = "openfactura"

    def __init__(self, session: requests.Session | None = None) -> None:
        cfg = getattr(settings, "OPENFACTURA", {})
        self.api_key = cfg.get("API_KEY", "")
        self.base_url = cfg.get("BASE_URL", "https://dev-api.haulmer.com").rstrip("/")
        self.timeout = cfg.get("TIMEOUT", 30)
        self.session = session or requests.Session()
        if not self.api_key:
            raise ConfiguracionError(
                "Falta OPENFACTURA_API_KEY. Defínela en el archivo .env."
            )

    # ------------------------------------------------------------------
    # Construcción del JSON
    # ------------------------------------------------------------------
    def construir_payload(self, dte: DTEData) -> dict:
        em, rec = dte.emisor, dte.receptor

        id_doc = {
            "TipoDTE": dte.tipo_dte,
            "Folio": 0,  # OpenFactura asigna el folio
            "FchEmis": dte.fecha_emision.isoformat(),
        }
        if dte.forma_pago:
            id_doc["FmaPago"] = dte.forma_pago

        emisor = {
            "RUTEmisor": em.rut,
            "RznSoc": recortar(em.razon_social, "RznSoc"),
            "GiroEmis": recortar(em.giro, "GiroEmis"),
            "Acteco": em.actividades[0] if len(em.actividades) == 1 else em.actividades,
            "DirOrigen": recortar(em.direccion, "DirOrigen"),
            "CmnaOrigen": recortar(em.comuna, "CmnaOrigen"),
        }
        if em.ciudad:
            emisor["CiudadOrigen"] = recortar(em.ciudad, "CiudadOrigen")
        if em.codigo_sucursal:
            emisor["CdgSIISucur"] = em.codigo_sucursal
        if em.correo:
            emisor["CorreoEmisor"] = em.correo
        if em.telefono:
            emisor["Telefono"] = em.telefono

        receptor = {
            "RUTRecep": rec.rut,
            "RznSocRecep": recortar(rec.razon_social, "RznSocRecep"),
            "GiroRecep": recortar(rec.giro, "GiroRecep"),
            "DirRecep": recortar(rec.direccion, "DirRecep"),
            "CmnaRecep": recortar(rec.comuna, "CmnaRecep"),
        }
        if rec.contacto:
            receptor["Contacto"] = recortar(rec.contacto, "Contacto")
        if rec.correo:
            receptor["CorreoRecep"] = recortar(rec.correo, "CorreoRecep")
        if rec.ciudad:
            receptor["CiudadRecep"] = recortar(rec.ciudad, "CiudadRecep")

        es_exenta = dte.tipo_dte == TipoDTE.FACTURA_EXENTA
        detalle = []
        for n, linea in enumerate(dte.lineas, start=1):
            item = {
                "NroLinDet": n,
                "NmbItem": recortar(linea.descripcion, "NmbItem"),
                "QtyItem": _numero(linea.cantidad),
                "PrcItem": _numero(linea.precio_unitario),
                "MontoItem": int(linea.monto),
            }
            # Si la descripción no cabe en NmbItem, va completa en DscItem.
            if len(" ".join(linea.descripcion.split())) > len(item["NmbItem"]):
                item["DscItem"] = recortar(linea.descripcion, "DscItem")
            if linea.exento or es_exenta:
                item["IndExe"] = 1
            detalle.append(item)

        tot = calcular_totales(dte.lineas)
        totales: dict = {}
        if tot.neto:
            totales["MntNeto"] = int(tot.neto)
        if tot.exento:
            totales["MntExe"] = int(tot.exento)
        if tot.neto:
            totales["TasaIVA"] = str(int(TASA_IVA * 100))
            totales["IVA"] = int(tot.iva)
        totales["MntTotal"] = int(tot.total)

        cuerpo = {
            "Encabezado": {
                "IdDoc": id_doc,
                "Emisor": emisor,
                "Receptor": receptor,
                "Totales": totales,
            },
            "Detalle": detalle,
        }
        if dte.referencias:
            cuerpo["Referencia"] = [
                {
                    "NroLinRef": n,
                    "TpoDocRef": str(ref.tipo_documento),
                    "FolioRef": str(ref.folio),
                    "FchRef": ref.fecha.isoformat(),
                    **({"CodRef": str(ref.codigo)} if ref.codigo else {}),
                    **({"RazonRef": recortar(ref.razon, "RazonRef")} if ref.razon else {}),
                }
                for n, ref in enumerate(dte.referencias, start=1)
            ]

        payload = {
            "response": ["XML", "PDF", "FOLIO", "RESOLUCION"],
            "dte": cuerpo,
        }
        if dte.nota:
            payload["custom"] = {"informationNote": dte.nota}
        return payload

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _request(self, metodo: str, ruta: str, *, clave: str = "", **kwargs):
        headers = {"apikey": self.api_key, "Content-Type": "application/json"}
        if clave:
            headers["Idempotency-Key"] = clave
        try:
            return self.session.request(
                metodo,
                f"{self.base_url}{ruta}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise EmisionError(f"Error de conexión con OpenFactura: {exc}") from exc

    @staticmethod
    def _error(resp) -> dict:
        try:
            return resp.json().get("error") or {}
        except ValueError:
            return {}

    @staticmethod
    def _describir_error(resp, error: dict) -> str:
        if not error:
            return f"HTTP {resp.status_code}: {resp.text[:300]}"
        detalles = "; ".join(
            f"{d.get('field')}: {d.get('issue')}" for d in error.get("details") or []
        )
        texto = f"{error.get('code', '')} {error.get('message', '')}".strip()
        return f"{texto} ({detalles})" if detalles else texto

    def _verificar(self, resp) -> None:
        """Lanza EmisionError en errores no atribuibles a los datos del DTE."""
        if resp.status_code in (401, 403):
            raise ConfiguracionError(
                "OpenFactura rechazó la API key. Revisa OPENFACTURA_API_KEY y "
                "que corresponda al ambiente de OPENFACTURA_BASE_URL."
            )
        if resp.status_code == 429:
            raise EmisionError("OpenFactura: límite de peticiones excedido, reintente en unos segundos.")
        if resp.status_code >= 500:
            raise EmisionError(f"OpenFactura no disponible (HTTP {resp.status_code}).")

    # ------------------------------------------------------------------
    # Interfaz EmisorDTE
    # ------------------------------------------------------------------
    def emitir(self, dte: DTEData) -> DTEResult:
        resp = self._request(
            "POST", RUTA_DOCUMENTO, clave=dte.clave_idempotencia, json=self.construir_payload(dte)
        )
        self._verificar(resp)

        if resp.status_code < 400:
            return self._resultado_exitoso(resp.json())

        error = self._error(resp)
        if error.get("code") == _ERROR_IDEMPOTENCIA:
            token = next(
                (d.get("issue") for d in error.get("details") or [] if d.get("field") == "token"),
                "",
            )
            if token:
                return self.recuperar(token)

        return DTEResult(
            exito=False,
            estado=EstadoSII.RECHAZADO,
            mensaje=self._describir_error(resp, error),
            datos_crudos=error,
        )

    def _resultado_exitoso(self, data: dict) -> DTEResult:
        advertencias = [
            f"{campo}: {texto}"
            for w in data.get("WARNING") or []
            for campo, texto in (w.items() if isinstance(w, dict) else [("", w)])
        ]
        return DTEResult(
            exito=True,
            estado=EstadoSII.ENVIADO,
            folio=int(data["FOLIO"]) if data.get("FOLIO") else None,
            track_id=str(data.get("TOKEN", "")),
            xml_bytes=base64.b64decode(data["XML"]) if data.get("XML") else None,
            pdf_bytes=base64.b64decode(data["PDF"]) if data.get("PDF") else None,
            mensaje="Recibido por OpenFactura; pendiente de aceptación del SII.",
            advertencias=advertencias,
            datos_crudos={k: v for k, v in data.items() if k not in ("XML", "PDF", "TIMBRE", "LOGO")},
        )

    def _obtener(self, token: str, valor: str) -> dict:
        resp = self._request("GET", f"{RUTA_DOCUMENTO}/{token}/{valor}")
        self._verificar(resp)
        if resp.status_code >= 400:
            raise EmisionError(
                f"OpenFactura: no se pudo obtener '{valor}' del documento: "
                f"{self._describir_error(resp, self._error(resp))}"
            )
        return resp.json()

    def recuperar(self, token: str) -> DTEResult:
        """Reconstruye el resultado de un documento ya emitido a partir de su token."""
        encabezado = self._obtener(token, "json").get("json", {}).get("Encabezado", {})
        folio = encabezado.get("IdDoc", {}).get("Folio")
        xml = self._obtener(token, "xml").get("xml")
        pdf = self._obtener(token, "pdf").get("pdf")
        return DTEResult(
            exito=True,
            estado=self.consultar_estado(token),
            folio=int(folio) if folio else None,
            track_id=token,
            xml_bytes=base64.b64decode(xml) if xml else None,
            pdf_bytes=base64.b64decode(pdf) if pdf else None,
            mensaje="Documento ya emitido anteriormente; recuperado por su token.",
        )

    def consultar_estado(self, track_id: str) -> str:
        estado = str(self._obtener(track_id, "status").get("estado", "")).strip().lower()
        if estado not in _ESTADOS:
            raise EmisionError(f"Estado desconocido devuelto por OpenFactura: {estado!r}")
        return _ESTADOS[estado]
