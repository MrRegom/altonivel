"""Generación de PDF para cotizaciones.

Renderiza una plantilla HTML y la convierte a PDF con xhtml2pdf, que es
100% Python. La plantilla usa solo tablas y CSS simple para que se vea
igual en cualquier motor.
"""
from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string


def _logo_path():
    """Logo subido en "Mi empresa" o, si no hay, el logotipo de Alto Nivel."""
    from django.contrib.staticfiles import finders

    from facturacion.models import EmpresaEmisora

    empresa = EmpresaEmisora.objects.first()
    if empresa and empresa.logo:
        ruta = Path(empresa.logo.path)
        if ruta.exists():
            return empresa, str(ruta)
    return empresa, finders.find("panel/img/logotipo.png")


def cotizacion_html(cotizacion) -> str:
    empresa, logo = _logo_path()
    hay_fotos = any(i.producto_id and i.producto.imagen for i in cotizacion.items.all())
    return render_to_string(
        "ventas/cotizacion_pdf.html",
        {"c": cotizacion, "empresa": empresa, "logo": logo, "hay_fotos": hay_fotos},
    )


def _resolver_recurso(uri, rel):
    # Permite que xhtml2pdf lea archivos locales (logo) y de MEDIA.
    if uri.startswith(settings.MEDIA_URL):
        return str(Path(settings.MEDIA_ROOT) / uri[len(settings.MEDIA_URL):])
    return uri


def html_a_pdf(html: str) -> bytes:
    from xhtml2pdf import pisa

    salida = io.BytesIO()
    resultado = pisa.CreatePDF(
        html, dest=salida, encoding="utf-8", link_callback=_resolver_recurso
    )
    if resultado.err:
        raise RuntimeError("No se pudo generar el PDF de la cotización.")
    return salida.getvalue()


def cotizacion_pdf(cotizacion) -> bytes:
    return html_a_pdf(cotizacion_html(cotizacion))
