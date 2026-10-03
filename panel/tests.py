import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from catalogo.models import Producto
from clientes.models import Cliente
from facturacion.models import EmpresaEmisora
from ventas.models import Cotizacion, DocumentoTributario, EstadoCotizacion, ItemCotizacion


class PanelTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=media, EMISOR_BACKEND="consola")
        ajuste.enable()
        self.addCleanup(ajuste.disable)

        self.user = User.objects.create_user("vendedor", password="x")
        self.client.force_login(self.user)
        EmpresaEmisora.objects.create(
            rut="76795561-8", razon_social="EMPRESA DEMO SPA", giro="SERVICIOS",
            actividades="620200", direccion="CALLE 123", comuna="Santiago",
            nombre_fantasia="Alto Nivel",
        )
        self.cliente = Cliente.objects.create(
            rut="76192083-9", razon_social="Demo SpA", correo="demo@demo.cl",
            giro="Comercio", direccion="Av. Uno 100", comuna="Providencia",
        )
        self.producto = Producto.objects.create(nombre="Tarjeta de video", precio_neto=Decimal("450000"))

    def _cotizacion(self):
        cot = Cotizacion.objects.create(cliente=self.cliente)
        ItemCotizacion.objects.create(
            cotizacion=cot, descripcion="Tarjeta de video", cantidad=Decimal("2"),
            precio_unitario=Decimal("450000"),
        )
        return cot

    def test_requiere_ingresar(self):
        self.client.logout()
        resp = self.client.get(reverse("panel:inicio"))
        self.assertRedirects(resp, f"{reverse('login')}?next=/")

    def test_paginas_cargan(self):
        cot = self._cotizacion()
        urls = [
            reverse("panel:inicio"),
            reverse("panel:clientes"),
            reverse("panel:cliente_nuevo"),
            reverse("panel:cliente_detalle", args=[self.cliente.pk]),
            reverse("panel:productos"),
            reverse("panel:producto_nuevo"),
            reverse("panel:cotizaciones"),
            reverse("panel:cotizacion_nueva"),
            reverse("panel:cotizacion_detalle", args=[cot.pk]),
            reverse("panel:cotizacion_editar", args=[cot.pk]),
            reverse("panel:documentos"),
            reverse("panel:empresa"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_crear_cliente_normaliza_rut_y_rechaza_invalido(self):
        datos = {"rut": "77.111.222-6", "razon_social": "Nuevo SpA", "activo": "on"}
        self.client.post(reverse("panel:cliente_nuevo"), datos)
        self.assertTrue(Cliente.objects.filter(rut="77111222-6").exists())

        resp = self.client.post(reverse("panel:cliente_nuevo"), {**datos, "rut": "77111222-1"})
        self.assertContains(resp, "El RUT no es válido")

    def test_crear_cotizacion_con_items(self):
        datos = {
            "cliente": self.cliente.pk, "fecha": "2026-10-03", "valida_hasta": "2026-10-18",
            "observaciones": "",
            "items-TOTAL_FORMS": "2", "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
            "items-0-producto": self.producto.pk, "items-0-descripcion": "Tarjeta de video",
            "items-0-cantidad": "1", "items-0-precio_unitario": "450000",
            "items-1-producto": "", "items-1-descripcion": "Instalación",
            "items-1-cantidad": "1", "items-1-precio_unitario": "150", "items-1-exento": "on",
        }
        resp = self.client.post(reverse("panel:cotizacion_nueva"), datos)
        cot = Cotizacion.objects.get()
        self.assertRedirects(resp, reverse("panel:cotizacion_detalle", args=[cot.pk]))
        self.assertEqual(cot.items.count(), 2)
        self.assertEqual(cot.total, Decimal("450000") + Decimal("85500") + Decimal("150"))

    def test_cotizacion_sin_items_no_se_guarda(self):
        datos = {
            "cliente": self.cliente.pk, "fecha": "2026-10-03",
            "items-TOTAL_FORMS": "0", "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1", "items-MAX_NUM_FORMS": "1000",
        }
        resp = self.client.post(reverse("panel:cotizacion_nueva"), datos)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Cotizacion.objects.exists())

    def test_pdf_de_cotizacion(self):
        resp = self.client.get(reverse("panel:cotizacion_pdf", args=[self._cotizacion().pk]))
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_flujo_aceptar_y_emitir(self):
        cot = self._cotizacion()
        self.client.post(reverse("panel:cotizacion_estado", args=[cot.pk]), {"estado": "aceptada"})
        cot.refresh_from_db()
        self.assertEqual(cot.estado, EstadoCotizacion.ACEPTADA)

        resp = self.client.post(reverse("panel:cotizacion_emitir", args=[cot.pk]), {"tipo_dte": "33"})
        doc = DocumentoTributario.objects.get()
        self.assertRedirects(resp, reverse("panel:documento_detalle", args=[doc.pk]))
        cot.refresh_from_db()
        self.assertEqual(cot.estado, EstadoCotizacion.FACTURADA)
        # Ya facturada: no se puede editar.
        resp = self.client.get(reverse("panel:cotizacion_editar", args=[cot.pk]))
        self.assertRedirects(resp, reverse("panel:cotizacion_detalle", args=[cot.pk]))

    def test_emitir_con_cliente_incompleto_muestra_errores(self):
        self.cliente.giro = ""
        self.cliente.save()
        cot = self._cotizacion()
        resp = self.client.post(
            reverse("panel:cotizacion_emitir", args=[cot.pk]), {"tipo_dte": "33"}, follow=True
        )
        self.assertContains(resp, "Cliente: falta giro")
        self.assertFalse(DocumentoTributario.objects.exists())

    def test_duplicar_cotizacion(self):
        cot = self._cotizacion()
        self.client.post(reverse("panel:cotizacion_duplicar", args=[cot.pk]))
        copia = Cotizacion.objects.exclude(pk=cot.pk).get()
        self.assertEqual(copia.items.count(), 1)
        self.assertEqual(copia.estado, EstadoCotizacion.BORRADOR)
