"""Lógica de negocio de ventas: emisión, seguimiento y envíos por correo."""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from facturacion.base import DTEData, DTEResult, EmisorDTE, LineaDTE, Receptor
from facturacion.constants import EstadoSII, TipoDTE
from facturacion.exceptions import DatosInvalidosError, EmisionError
from facturacion.factory import get_emisor
from facturacion.models import EmpresaEmisora
from facturacion.montos import calcular_totales
from facturacion.validacion import validar_dte

from .models import Cotizacion, DocumentoTributario, EstadoCotizacion

logger = logging.getLogger(__name__)

ESTADOS_ACEPTADOS = (EstadoSII.ACEPTADO, EstadoSII.ACEPTADO_REPAROS)

# El proveedor recuerda la clave de idempotencia por 24 h. Pasado ese
# plazo, reintentar podría duplicar la factura: se exige revisión manual.
VENTANA_REINTENTO = timedelta(hours=23)


def _receptor_desde_cliente(cliente) -> Receptor:
    return Receptor(
        rut=cliente.rut,
        razon_social=cliente.razon_social,
        giro=cliente.giro,
        direccion=cliente.direccion,
        comuna=cliente.comuna,
        ciudad=cliente.ciudad,
        correo=cliente.correo,
        contacto=" ".join(filter(None, [cliente.contacto, cliente.telefono])),
    )


def _dte_desde_cotizacion(cotizacion: Cotizacion, tipo_dte: int) -> DTEData:
    lineas = [
        LineaDTE(
            descripcion=item.descripcion,
            cantidad=item.cantidad,
            precio_unitario=item.precio_unitario,
            exento=item.exento,
        )
        for item in cotizacion.items.all()
    ]
    return DTEData(
        tipo_dte=tipo_dte,
        emisor=EmpresaEmisora.actual().como_emisor(),
        receptor=_receptor_desde_cliente(cotizacion.cliente),
        lineas=lineas,
        fecha_emision=timezone.localdate(),
        nota=f"Según cotización N°{cotizacion.numero}",
    )


def emitir_documento(
    cotizacion: Cotizacion, tipo_dte: int = TipoDTE.FACTURA_AFECTA
) -> DocumentoTributario:
    """Emite un DTE a partir de una cotización y registra el resultado.

    El documento se guarda como PENDIENTE *antes* de llamar al proveedor.
    Así, si algo falla a mitad de camino, queda registro y se puede
    reintentar con la misma clave de idempotencia sin emitir dos veces.

    Lanza DatosInvalidosError si faltan datos (no se crea el documento) y
    EmisionError si la emisión quedó incierta (el documento queda PENDIENTE).
    """
    previo = (
        cotizacion.documentos.filter(tipo_dte=tipo_dte)
        .exclude(estado_sii=EstadoSII.RECHAZADO)
        .first()
    )
    if previo:
        raise ValueError(
            f"La cotización N°{cotizacion.numero} ya tiene un documento "
            f"({previo}, estado: {previo.get_estado_sii_display()})."
        )

    emisor = get_emisor()
    dte = _dte_desde_cotizacion(cotizacion, tipo_dte)
    errores = validar_dte(dte)
    if errores:
        raise DatosInvalidosError(errores)

    totales = calcular_totales(dte.lineas)
    documento = DocumentoTributario.objects.create(
        cotizacion=cotizacion,
        cliente=cotizacion.cliente,
        tipo_dte=tipo_dte,
        fecha_emision=dte.fecha_emision,
        monto_neto=totales.neto,
        monto_exento=totales.exento,
        iva=totales.iva,
        total=totales.total,
        estado_sii=EstadoSII.PENDIENTE,
        emisor_backend=emisor.nombre,
    )
    return _emitir(documento, emisor, dte)


def reintentar_emision(documento: DocumentoTributario) -> DocumentoTributario:
    """Reintenta un documento que quedó PENDIENTE por una falla de conexión."""
    if documento.estado_sii != EstadoSII.PENDIENTE:
        raise ValueError("Solo se pueden reintentar documentos pendientes de envío.")
    if documento.cotizacion is None:
        raise ValueError("El documento no tiene cotización de origen para reconstruirlo.")
    if timezone.now() - documento.creado_en > VENTANA_REINTENTO:
        raise ValueError(
            "Pasaron más de 23 horas desde el primer intento. Antes de reintentar, "
            "revise en el portal del proveedor si el documento se emitió, para no duplicarlo."
        )

    emisor = get_emisor(documento.emisor_backend)
    dte = _dte_desde_cotizacion(documento.cotizacion, documento.tipo_dte)
    dte.fecha_emision = documento.fecha_emision
    errores = validar_dte(dte)
    if errores:
        raise DatosInvalidosError(errores)
    return _emitir(documento, emisor, dte)


def _emitir(documento: DocumentoTributario, emisor: EmisorDTE, dte: DTEData) -> DocumentoTributario:
    dte.clave_idempotencia = str(documento.clave_idempotencia)
    try:
        resultado = emisor.emitir(dte)
    except EmisionError as exc:
        documento.error_mensaje = (
            f"No se pudo confirmar la emisión: {exc}. "
            "Use 'Reintentar emisión': no se duplicará el documento."
        )
        documento.save(update_fields=["error_mensaje", "actualizado_en"])
        raise

    _registrar_resultado(documento, resultado)
    if resultado.exito and documento.cotizacion_id:
        cotizacion = documento.cotizacion
        cotizacion.estado = EstadoCotizacion.FACTURADA
        cotizacion.save(update_fields=["estado", "actualizado_en"])
    _enviar_si_corresponde(documento)
    return documento


def _registrar_resultado(documento: DocumentoTributario, resultado: DTEResult) -> None:
    documento.estado_sii = resultado.estado
    documento.advertencias = "\n".join(resultado.advertencias)
    if not resultado.exito:
        documento.error_mensaje = resultado.mensaje
        documento.save()
        return

    documento.error_mensaje = ""
    documento.folio = resultado.folio
    documento.track_id = resultado.track_id
    nombre = f"dte_{documento.tipo_dte}_{resultado.folio}"
    if resultado.xml_bytes:
        documento.xml.save(f"{nombre}.xml", _content(resultado.xml_bytes), save=False)
    if resultado.pdf_bytes:
        documento.pdf.save(f"{nombre}.pdf", _content(resultado.pdf_bytes), save=False)
    documento.save()


def actualizar_estado(documento: DocumentoTributario) -> str:
    """Consulta el estado ante el SII y, si fue aceptado, envía el correo al cliente."""
    if documento.estado_sii != EstadoSII.ENVIADO or not documento.track_id:
        return documento.estado_sii

    emisor = get_emisor(documento.emisor_backend)
    nuevo = emisor.consultar_estado(documento.track_id)
    if nuevo != documento.estado_sii:
        documento.estado_sii = nuevo
        documento.save(update_fields=["estado_sii", "actualizado_en"])
    _enviar_si_corresponde(documento)
    return nuevo


def _enviar_si_corresponde(documento: DocumentoTributario) -> None:
    if not getattr(settings, "ENVIAR_DTE_AL_ACEPTAR", False):
        return
    if (
        documento.estado_sii not in ESTADOS_ACEPTADOS
        or documento.enviado_al_cliente_en
        or not documento.cliente.correo
    ):
        return
    try:
        enviar_documento_por_correo(documento)
    except Exception as exc:  # el documento ya está emitido; el correo se puede reenviar
        logger.exception("No se pudo enviar el DTE %s por correo", documento.pk)
        documento.error_mensaje = f"Emitido, pero falló el envío por correo: {exc}"
        documento.save(update_fields=["error_mensaje", "actualizado_en"])


def enviar_cotizacion_por_correo(cotizacion: Cotizacion) -> bool:
    """Envía la cotización al correo del cliente con el PDF adjunto."""
    if not cotizacion.cliente.correo:
        raise ValueError("El cliente no tiene correo registrado.")

    from .pdf import cotizacion_pdf

    mensaje = EmailMessage(
        subject=f"Cotización N°{cotizacion.numero}",
        body="Adjuntamos la cotización solicitada. Quedamos atentos.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[cotizacion.cliente.correo],
    )
    mensaje.attach(
        f"cotizacion_{cotizacion.numero}.pdf",
        cotizacion_pdf(cotizacion),
        "application/pdf",
    )
    enviados = mensaje.send()
    if enviados:
        cotizacion.estado = EstadoCotizacion.ENVIADA
        cotizacion.enviada_en = timezone.now()
        cotizacion.save(update_fields=["estado", "enviada_en", "actualizado_en"])
    return bool(enviados)


def enviar_documento_por_correo(documento: DocumentoTributario) -> bool:
    """Envía el DTE emitido (PDF + XML) al correo del cliente."""
    if not documento.cliente.correo:
        raise ValueError("El cliente no tiene correo registrado.")
    if documento.estado_sii not in ESTADOS_ACEPTADOS:
        raise ValueError(
            f"El documento aún no está aceptado por el SII "
            f"(estado: {documento.get_estado_sii_display()})."
        )

    mensaje = EmailMessage(
        subject=f"{documento.get_tipo_dte_display()} N°{documento.folio}",
        body="Adjuntamos su documento tributario electrónico.",
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[documento.cliente.correo],
    )
    nombre = f"{documento.get_tipo_dte_display()} {documento.folio}"
    if documento.pdf:
        with documento.pdf.open("rb") as f:
            mensaje.attach(f"{nombre}.pdf", f.read(), "application/pdf")
    if documento.xml:
        with documento.xml.open("rb") as f:
            mensaje.attach(f"{nombre}.xml", f.read(), "application/xml")
    enviados = mensaje.send()
    if enviados:
        documento.enviado_al_cliente_en = timezone.now()
        documento.save(update_fields=["enviado_al_cliente_en", "actualizado_en"])
    return bool(enviados)


def _content(data: bytes):
    from django.core.files.base import ContentFile

    return ContentFile(data)
