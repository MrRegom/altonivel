import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from clientes.models import Cliente
from facturacion.base import DTEResult, EmisorDTE
from facturacion.constants import EstadoSII, TipoDTE
from facturacion.exceptions import DatosInvalidosError, EmisionError
from facturacion.models import EmpresaEmisora
from ventas.models import Cotizacion, DocumentoTributario, EstadoCotizacion, ItemCotizacion
from ventas import services


class EmisorFalso(EmisorDTE):
    """Simula un proveedor: registra las llamadas y responde lo que se le indique."""

    nombre = "falso"

    def __init__(self, respuestas=None, estado="aceptado"):
        self.respuestas = list(respuestas or [])
        self.estado = estado
        self.llamadas = []

    def emitir(self, dte):
        self.llamadas.append(dte)
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def consultar_estado(self, track_id):
        return self.estado


def exito(folio=10, estado=EstadoSII.ENVIADO):
    return DTEResult(
        exito=True, estado=estado, folio=folio, track_id=f"tok{folio}",
        xml_bytes=b"<DTE/>", pdf_bytes=b"%PDF-1.4",
    )


class BaseVentas(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        EmpresaEmisora.objects.create(
            rut="76795561-8", razon_social="EMPRESA DEMO SPA", giro="SERVICIOS",
            actividades="620200", direccion="CALLE 123", comuna="Santiago",
        )
        self.cliente = Cliente.objects.create(
            rut="76192083-9", razon_social="Demo SpA", correo="demo@demo.cl",
            giro="Comercio", direccion="Av. Uno 100", comuna="Providencia",
        )

    def _cotizacion_con_items(self):
        cot = Cotizacion.objects.create(cliente=self.cliente)
        ItemCotizacion.objects.create(
            cotizacion=cot, descripcion="Servicio",
            cantidad=Decimal("1"), precio_unitario=Decimal("100000"),
        )
        ItemCotizacion.objects.create(
            cotizacion=cot, descripcion="Insumo exento",
            cantidad=Decimal("2"), precio_unitario=Decimal("5000"), exento=True,
        )
        return cot

    def _con_emisor(self, emisor):
        patcher = mock.patch("ventas.services.get_emisor", return_value=emisor)
        patcher.start()
        self.addCleanup(patcher.stop)
        return emisor


class CotizacionTests(BaseVentas):
    def test_totales(self):
        cot = self._cotizacion_con_items()
        self.assertEqual(cot.monto_neto, Decimal("100000"))
        self.assertEqual(cot.monto_exento, Decimal("10000"))
        self.assertEqual(cot.iva, Decimal("19000"))
        self.assertEqual(cot.total, Decimal("129000"))

    def test_iva_redondea_mitad_hacia_arriba(self):
        cot = Cotizacion.objects.create(cliente=self.cliente)
        ItemCotizacion.objects.create(
            cotizacion=cot, descripcion="x", cantidad=Decimal("1"), precio_unitario=Decimal("150"),
        )
        self.assertEqual(cot.iva, Decimal("29"))

    def test_numero_correlativo(self):
        c1 = Cotizacion.objects.create(cliente=self.cliente)
        c2 = Cotizacion.objects.create(cliente=self.cliente)
        self.assertEqual(c2.numero, c1.numero + 1)


class EmisionTests(BaseVentas):
    def test_emision_backend_consola(self):
        cot = self._cotizacion_con_items()
        doc = services.emitir_documento(cot)
        cot.refresh_from_db()
        self.assertTrue(doc.folio)
        self.assertEqual(doc.emisor_backend, "consola")
        self.assertEqual(doc.total, Decimal("129000"))
        self.assertEqual(cot.estado, EstadoCotizacion.FACTURADA)

    def test_emision_exitosa_guarda_archivos_y_espera_al_sii(self):
        emisor = self._con_emisor(EmisorFalso([exito(folio=42)]))
        cot = self._cotizacion_con_items()
        doc = services.emitir_documento(cot)
        self.assertEqual((doc.folio, doc.track_id, doc.estado_sii), (42, "tok42", EstadoSII.ENVIADO))
        self.assertEqual(doc.xml.read(), b"<DTE/>")
        self.assertEqual(emisor.llamadas[0].clave_idempotencia, str(doc.clave_idempotencia))
        self.assertEqual(emisor.llamadas[0].nota, f"Según cotización N°{cot.numero}")
        # Aún no aceptado por el SII: no se envía correo.
        self.assertEqual(len(mail.outbox), 0)

    def test_datos_incompletos_no_crea_documento(self):
        self._con_emisor(EmisorFalso())
        self.cliente.giro = ""
        self.cliente.save()
        with self.assertRaises(DatosInvalidosError):
            services.emitir_documento(self._cotizacion_con_items())
        self.assertFalse(DocumentoTributario.objects.exists())

    def test_falla_de_red_deja_pendiente_y_reintento_usa_misma_clave(self):
        emisor = self._con_emisor(EmisorFalso([EmisionError("timeout"), exito(folio=7)]))
        cot = self._cotizacion_con_items()
        with self.assertRaises(EmisionError):
            services.emitir_documento(cot)

        doc = DocumentoTributario.objects.get()
        self.assertEqual(doc.estado_sii, EstadoSII.PENDIENTE)
        self.assertIn("Reintentar", doc.error_mensaje)

        with mock.patch("ventas.services.get_emisor", return_value=emisor):
            services.reintentar_emision(doc)
        doc.refresh_from_db()
        self.assertEqual((doc.folio, doc.estado_sii, doc.error_mensaje), (7, EstadoSII.ENVIADO, ""))
        claves = {d.clave_idempotencia for d in emisor.llamadas}
        self.assertEqual(claves, {str(doc.clave_idempotencia)})

    def test_no_reintenta_pasadas_23_horas(self):
        self._con_emisor(EmisorFalso([EmisionError("timeout")]))
        with self.assertRaises(EmisionError):
            services.emitir_documento(self._cotizacion_con_items())
        doc = DocumentoTributario.objects.get()
        DocumentoTributario.objects.filter(pk=doc.pk).update(
            creado_en=timezone.now() - timedelta(hours=30)
        )
        doc.refresh_from_db()
        with self.assertRaisesMessage(ValueError, "23 horas"):
            services.reintentar_emision(doc)

    def test_no_permite_emitir_dos_veces_la_misma_cotizacion(self):
        self._con_emisor(EmisorFalso([exito(), exito()]))
        cot = self._cotizacion_con_items()
        services.emitir_documento(cot)
        with self.assertRaisesMessage(ValueError, "ya tiene un documento"):
            services.emitir_documento(cot)

    def test_rechazado_permite_corregir_y_emitir_de_nuevo(self):
        rechazo = DTEResult(exito=False, estado=EstadoSII.RECHAZADO, mensaje="OF-10 Validación")
        self._con_emisor(EmisorFalso([rechazo, exito()]))
        cot = self._cotizacion_con_items()
        doc = services.emitir_documento(cot)
        self.assertEqual((doc.estado_sii, doc.error_mensaje), (EstadoSII.RECHAZADO, "OF-10 Validación"))
        cot.refresh_from_db()
        self.assertNotEqual(cot.estado, EstadoCotizacion.FACTURADA)
        services.emitir_documento(cot)
        self.assertEqual(DocumentoTributario.objects.count(), 2)


class EstadoYCorreoTests(BaseVentas):
    def test_al_aceptarse_se_envia_correo_una_sola_vez(self):
        emisor = self._con_emisor(EmisorFalso([exito(folio=99)], estado=EstadoSII.ACEPTADO))
        doc = services.emitir_documento(self._cotizacion_con_items())

        with mock.patch("ventas.services.get_emisor", return_value=emisor):
            self.assertEqual(services.actualizar_estado(doc), EstadoSII.ACEPTADO)
            services.actualizar_estado(doc)

        self.assertEqual(len(mail.outbox), 1)
        adjuntos = [nombre for nombre, *_ in mail.outbox[0].attachments]
        self.assertEqual(adjuntos, ["Factura electrónica (afecta) 99.pdf", "Factura electrónica (afecta) 99.xml"])
        doc.refresh_from_db()
        self.assertIsNotNone(doc.enviado_al_cliente_en)

    def test_no_envia_correo_si_no_esta_aceptado(self):
        self._con_emisor(EmisorFalso([exito()]))
        doc = services.emitir_documento(self._cotizacion_con_items())
        with self.assertRaisesMessage(ValueError, "aún no está aceptado"):
            services.enviar_documento_por_correo(doc)
