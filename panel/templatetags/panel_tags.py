"""Filtros de formato para pesos chilenos, RUT y estados."""
from decimal import Decimal, InvalidOperation

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.rut import RutInvalidoError, formatear
from facturacion.constants import EstadoSII

register = template.Library()


def _miles(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


@register.filter
def clp(valor) -> str:
    """$1.234.567"""
    try:
        numero = int(Decimal(valor or 0))
    except (InvalidOperation, TypeError, ValueError):
        return ""
    signo = "-" if numero < 0 else ""
    return f"{signo}${_miles(abs(numero))}"


@register.filter
def cantidad(valor) -> str:
    """1 / 1,5 (sin ceros de más)."""
    try:
        numero = Decimal(valor).normalize()
    except (InvalidOperation, TypeError, ValueError):
        return ""
    entero, _, dec = f"{numero:f}".partition(".")
    return _miles(int(entero)) + (f",{dec}" if dec else "")


@register.filter
def rut(valor) -> str:
    try:
        return formatear(valor)
    except (RutInvalidoError, ValueError, AttributeError):
        return valor or ""


_TONO_COTIZACION = {
    "borrador": "gris",
    "enviada": "azul",
    "aceptada": "verde",
    "rechazada": "rojo",
    "facturada": "naranjo",
    "vencida": "gris",
}

_TONO_SII = {
    EstadoSII.PENDIENTE: "amarillo",
    EstadoSII.ENVIADO: "azul",
    EstadoSII.ACEPTADO: "verde",
    EstadoSII.ACEPTADO_REPAROS: "amarillo",
    EstadoSII.RECHAZADO: "rojo",
    EstadoSII.ANULADO: "gris",
}


@register.simple_tag
def badge_cotizacion(cotizacion):
    return format_html(
        '<span class="badge badge--{}">{}</span>',
        _TONO_COTIZACION.get(cotizacion.estado, "gris"),
        cotizacion.get_estado_display(),
    )


@register.simple_tag
def badge_sii(documento):
    return format_html(
        '<span class="badge badge--{}">{}</span>',
        _TONO_SII.get(documento.estado_sii, "gris"),
        documento.get_estado_sii_display(),
    )


@register.simple_tag(takes_context=True)
def activo(context, *prefijos):
    """Marca el enlace del menú correspondiente a la sección actual."""
    ruta = context["request"].path
    for p in prefijos:
        if (p == "/" and ruta == "/") or (p != "/" and ruta.startswith(p)):
            return "is-active"
    return ""


@register.simple_tag(takes_context=True)
def url_con(context, **params):
    """Querystring actual cambiando/agregando parámetros (para paginación y filtros)."""
    query = context["request"].GET.copy()
    for clave, valor in params.items():
        if valor in (None, ""):
            query.pop(clave, None)
        else:
            query[clave] = valor
    return "?" + query.urlencode() if query else "?"


# Íconos de trazo (estilo Lucide, licencia ISC).
_ICONOS = {
    "inicio": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "cotizacion": '<path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "factura": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8"/><path d="M12 17.5v-11"/>',
    "clientes": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "productos": '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    "empresa": '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
    "admin": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "salir": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "mas": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "buscar": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "enviar": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "descargar": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "actualizar": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "copiar": '<rect width="14" height="14" x="8" y="8" rx="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    "editar": '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>',
    "ver": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "alerta": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "menu": '<path d="M4 12h16"/><path d="M4 6h16"/><path d="M4 18h16"/>',
    "quitar": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2"/>',
    "rayo": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "flecha": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "llave": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "correo": '<rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
}


@register.simple_tag
def icono(nombre, clase=""):
    return format_html(
        '<svg class="icono {}" viewBox="0 0 24 24" aria-hidden="true">{}</svg>',
        clase,
        mark_safe(_ICONOS.get(nombre, "")),
    )
