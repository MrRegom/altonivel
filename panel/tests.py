import os
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

        self.user = User.objects.create_superuser("11111111-1", password="x", first_name="Admin")
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

    def test_buscar_cliente_por_rut_con_o_sin_formato(self):
        for q in ["761920839", "76.192.083-9", "76192083-9", "7619208"]:
            with self.subTest(q=q):
                resp = self.client.get(reverse("panel:clientes"), {"q": q})
                self.assertContains(resp, "Demo SpA")
        resp = self.client.get(reverse("panel:clientes"), {"q": "999999999"})
        self.assertNotContains(resp, "Demo SpA")

    def test_campo_rut_marcado_para_validador(self):
        resp = self.client.get(reverse("panel:cliente_nuevo"))
        self.assertContains(resp, "data-rut")


class UsuariosYAccesoTests(TestCase):
    CLAVE = "Clave-Segura-2026"

    def setUp(self):
        self.admin = User.objects.create_superuser("16233406-9", password=self.CLAVE, first_name="Reinaldo")
        self.vendedor = User.objects.create_user("12345678-5", password=self.CLAVE, first_name="Vendedor")

    def test_ingreso_con_rut_en_cualquier_formato(self):
        for rut in ["16233406-9", "16.233.406-9", "162334069"]:
            with self.subTest(rut=rut):
                resp = self.client.post(reverse("login"), {"username": rut, "password": self.CLAVE})
                self.assertRedirects(resp, reverse("panel:inicio"))
                self.client.logout()

    def test_ingreso_rechaza_rut_invalido_y_clave_incorrecta(self):
        resp = self.client.post(reverse("login"), {"username": "16233406-8", "password": self.CLAVE})
        self.assertContains(resp, "El RUT no es válido")
        resp = self.client.post(reverse("login"), {"username": "16233406-9", "password": "otra"})
        self.assertContains(resp, "RUT o contraseña incorrectos")

    def test_vendedor_no_accede_a_configuracion(self):
        self.client.force_login(self.vendedor)
        for nombre in ["panel:usuarios", "panel:usuario_nuevo", "panel:empresa"]:
            with self.subTest(nombre=nombre):
                self.assertRedirects(self.client.get(reverse(nombre)), reverse("panel:inicio"))
        self.assertNotContains(self.client.get(reverse("panel:inicio")), "Usuarios</a>")

    def test_admin_crea_usuario_que_ingresa_con_rut(self):
        self.client.force_login(self.admin)
        datos = {"rut": "7.654.321-6", "rol": "vendedor", "first_name": "Ana", "last_name": "Pérez",
                 "email": "ana@ejemplo.cl", "clave1": "Otra-Clave-2026", "clave2": "Otra-Clave-2026"}
        resp = self.client.post(reverse("panel:usuario_nuevo"), datos)
        self.assertRedirects(resp, reverse("panel:usuarios"))
        nuevo = User.objects.get(username="7654321-6")
        self.assertFalse(nuevo.is_superuser)
        self.client.logout()
        resp = self.client.post(reverse("login"), {"username": "76543216", "password": "Otra-Clave-2026"})
        self.assertRedirects(resp, reverse("panel:inicio"))

    def test_validaciones_al_crear(self):
        self.client.force_login(self.admin)
        base = {"rol": "vendedor", "first_name": "X", "clave1": "Otra-Clave-2026", "clave2": "Otra-Clave-2026"}
        resp = self.client.post(reverse("panel:usuario_nuevo"), {**base, "rut": "12.345.678-5"})
        self.assertContains(resp, "Ya existe un usuario con este RUT")
        resp = self.client.post(reverse("panel:usuario_nuevo"), {**base, "rut": "7654321-6", "clave2": "distinta"})
        self.assertContains(resp, "Las contraseñas no coinciden")

    def test_admin_no_puede_quitarse_su_rol(self):
        self.client.force_login(self.admin)
        datos = {"rut": "16233406-9", "rol": "vendedor", "first_name": "Reinaldo", "is_active": "on"}
        resp = self.client.post(reverse("panel:usuario_editar", args=[self.admin.pk]), datos)
        self.assertContains(resp, "No puedes quitarte el rol")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_admin_cambia_clave_de_otro_usuario(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("panel:usuario_clave", args=[self.vendedor.pk]),
                                {"new_password1": "Nueva-Clave-2026", "new_password2": "Nueva-Clave-2026"})
        self.assertRedirects(resp, reverse("panel:usuarios"))
        self.vendedor.refresh_from_db()
        self.assertTrue(self.vendedor.check_password("Nueva-Clave-2026"))

    def test_mi_clave(self):
        self.client.force_login(self.vendedor)
        resp = self.client.post(reverse("panel:mi_clave"), {
            "old_password": self.CLAVE, "new_password1": "Nueva-Clave-2026", "new_password2": "Nueva-Clave-2026"})
        self.assertRedirects(resp, reverse("panel:inicio"))

    def test_comando_admin_rut_convierte_superadmin_existente(self):
        from django.core.management import call_command

        User.objects.filter(pk=self.admin.pk).update(username="Reinaldo")
        call_command("admin_rut", "16.233.406-9", stdout=open(os.devnull, "w"))
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.username, "16233406-9")
        self.assertTrue(self.admin.is_superuser)


class FotosProductoTests(TestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        ajuste = override_settings(MEDIA_ROOT=media)
        ajuste.enable()
        self.addCleanup(ajuste.disable)
        self.client.force_login(User.objects.create_superuser("11111111-1", password="x"))

    @staticmethod
    def _png(ancho=1600, alto=1200):
        from io import BytesIO

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buf = BytesIO()
        Image.new("RGBA", (ancho, alto), (249, 82, 11, 255)).save(buf, "PNG")
        return SimpleUploadedFile("tarjeta.png", buf.getvalue(), content_type="image/png")

    def test_subir_foto_se_optimiza(self):
        from PIL import Image

        datos = {"nombre": "RTX", "precio_neto": "1000", "activo": "on", "imagen": self._png()}
        self.client.post(reverse("panel:producto_nuevo"), datos)
        p = Producto.objects.get()
        self.assertTrue(p.imagen.name.endswith(".jpg"))
        with Image.open(p.imagen.path) as img:
            self.assertEqual(img.format, "JPEG")
            self.assertLessEqual(max(img.size), 800)
        self.assertContains(self.client.get(reverse("panel:productos")), p.imagen.url)

    def test_quitar_foto(self):
        self.client.post(reverse("panel:producto_nuevo"),
                         {"nombre": "RTX", "precio_neto": "1000", "activo": "on", "imagen": self._png(200, 200)})
        p = Producto.objects.get()
        self.client.post(reverse("panel:producto_editar", args=[p.pk]),
                         {"nombre": "RTX", "precio_neto": "1000", "activo": "on", "quitar_imagen": "on"})
        p.refresh_from_db()
        self.assertFalse(p.imagen)

    def test_pdf_con_fotos(self):
        self.client.post(reverse("panel:producto_nuevo"),
                         {"nombre": "RTX", "precio_neto": "1000", "activo": "on", "imagen": self._png(300, 300)})
        p = Producto.objects.get()
        cliente = Cliente.objects.create(rut="76192083-9", razon_social="Demo SpA")
        cot = Cotizacion.objects.create(cliente=cliente)
        ItemCotizacion.objects.create(cotizacion=cot, producto=p, descripcion="RTX", precio_unitario=Decimal("1000"))
        resp = self.client.get(reverse("panel:cotizacion_pdf", args=[cot.pk]))
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn(b"/Image", resp.content)
