import base64
from datetime import date
from decimal import Decimal
from unittest import mock

import requests
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings

from facturacion.base import DTEData, Emisor, LineaDTE, Receptor, Referencia
from facturacion.constants import EstadoSII, TipoDTE
from facturacion.exceptions import ConfiguracionError, EmisionError
from facturacion.models import EmpresaEmisora, validar_actividades
from facturacion.montos import calcular_totales, redondear
from facturacion.providers.openfactura import EmisorOpenFactura
from facturacion.validacion import validar_dte

OPENFACTURA_TEST = {"API_KEY": "clave-test", "BASE_URL": "https://dev.test", "TIMEOUT": 5}


def emisor():
    return Emisor(
        rut="76795561-8", razon_social="EMPRESA DEMO SPA", giro="SERVICIOS",
        actividades=[620200], direccion="CALLE 123", comuna="Santiago",
        codigo_sucursal="81303347",
    )


def dte(tipo=TipoDTE.FACTURA_AFECTA, lineas=None, **extra):
    return DTEData(
        tipo_dte=tipo,
        emisor=emisor(),
        receptor=Receptor(
            rut="76430498-5", razon_social="CLIENTE SPA",
            giro="ACTIVIDADES DE CONSULTORIA DE INFORMATICA Y DE GESTION",
            direccion="AV SIEMPRE VIVA 742", comuna="Providencia", correo="c@cliente.cl",
        ),
        lineas=lineas if lineas is not None else [
            LineaDTE("Servicio", Decimal("1"), Decimal("150")),
        ],
        fecha_emision=date(2026, 10, 3),
        **extra,
    )


class Respuesta:
    def __init__(self, status, data=None, text=""):
        self.status_code = status
        self._data = data
        self.text = text or str(data)

    def json(self):
        if self._data is None:
            raise ValueError("sin json")
        return self._data


class MontosTests(SimpleTestCase):
    def test_redondeo_mitad_hacia_arriba(self):
        self.assertEqual(redondear(Decimal("2.5")), Decimal("3"))
        self.assertEqual(redondear(Decimal("28.5")), Decimal("29"))
        self.assertEqual(redondear(Decimal("28.49")), Decimal("28"))

    def test_iva_de_neto_150_es_29(self):
        tot = calcular_totales([LineaDTE("x", Decimal("1"), Decimal("150"))])
        self.assertEqual((tot.neto, tot.iva, tot.total), (150, 29, 179))

    def test_totales_con_exentos(self):
        tot = calcular_totales([
            LineaDTE("a", Decimal("1"), Decimal("100000")),
            LineaDTE("b", Decimal("2"), Decimal("5000"), exento=True),
        ])
        self.assertEqual((tot.neto, tot.exento, tot.iva, tot.total), (100000, 10000, 19000, 129000))


class ValidacionTests(SimpleTestCase):
    def test_dte_completo_no_tiene_errores(self):
        self.assertEqual(validar_dte(dte()), [])

    def test_falta_giro_del_cliente(self):
        d = dte()
        d.receptor.giro = ""
        self.assertIn("Cliente: falta giro (obligatorio para facturar).", validar_dte(d))

    def test_factura_exenta_con_items_afectos(self):
        errores = validar_dte(dte(tipo=TipoDTE.FACTURA_EXENTA))
        self.assertTrue(any("exenta" in e for e in errores))

    def test_factura_afecta_solo_exentos(self):
        lineas = [LineaDTE("x", Decimal("1"), Decimal("100"), exento=True)]
        self.assertTrue(any("(34)" in e for e in validar_dte(dte(lineas=lineas))))

    def test_nota_credito_sin_referencia(self):
        self.assertTrue(any("referenciar" in e for e in validar_dte(dte(tipo=TipoDTE.NOTA_CREDITO))))

    def test_actividades(self):
        validar_actividades("620200, 479100")
        with self.assertRaises(ValidationError):
            validar_actividades("62020")
        with self.assertRaises(ValidationError):
            validar_actividades("111111,222222,333333,444444,555555")


@override_settings(OPENFACTURA=OPENFACTURA_TEST)
class OpenFacturaTests(SimpleTestCase):
    def setUp(self):
        self.session = mock.Mock()
        self.of = EmisorOpenFactura(session=self.session)

    def test_sin_api_key(self):
        with override_settings(OPENFACTURA={"API_KEY": ""}):
            with self.assertRaises(ConfiguracionError):
                EmisorOpenFactura()

    def test_payload_completo(self):
        p = self.of.construir_payload(dte(nota="Según cotización N°7"))
        enc = p["dte"]["Encabezado"]
        self.assertEqual(enc["IdDoc"], {"TipoDTE": 33, "Folio": 0, "FchEmis": "2026-10-03"})
        self.assertEqual(enc["Emisor"]["RUTEmisor"], "76795561-8")
        self.assertEqual(enc["Emisor"]["Acteco"], 620200)
        self.assertEqual(enc["Emisor"]["CdgSIISucur"], "81303347")
        self.assertEqual(enc["Totales"], {"MntNeto": 150, "TasaIVA": "19", "IVA": 29, "MntTotal": 179})
        # Giro del receptor recortado a 40 caracteres (límite del SII).
        self.assertEqual(len(enc["Receptor"]["GiroRecep"]), 40)
        self.assertEqual(p["dte"]["Detalle"][0], {
            "NroLinDet": 1, "NmbItem": "Servicio", "QtyItem": 1, "PrcItem": 150, "MontoItem": 150,
        })
        self.assertEqual(p["custom"], {"informationNote": "Según cotización N°7"})
        self.assertIn("XML", p["response"])

    def test_payload_exenta_y_descripcion_larga(self):
        larga = "Servicio " * 20
        p = self.of.construir_payload(dte(
            tipo=TipoDTE.FACTURA_EXENTA,
            lineas=[LineaDTE(larga, Decimal("1.5"), Decimal("1000"), exento=True)],
        ))
        item = p["dte"]["Detalle"][0]
        self.assertEqual(item["IndExe"], 1)
        self.assertEqual(item["QtyItem"], 1.5)
        self.assertEqual(len(item["NmbItem"]), 80)
        self.assertEqual(item["DscItem"], larga.strip())
        self.assertEqual(p["dte"]["Encabezado"]["Totales"], {"MntExe": 1500, "MntTotal": 1500})

    def test_payload_referencias(self):
        p = self.of.construir_payload(dte(
            tipo=TipoDTE.NOTA_CREDITO,
            referencias=[Referencia("33", "106", date(2026, 9, 1), codigo=1, razon="Anula factura")],
        ))
        self.assertEqual(p["dte"]["Referencia"], [{
            "NroLinRef": 1, "TpoDocRef": "33", "FolioRef": "106",
            "FchRef": "2026-09-01", "CodRef": "1", "RazonRef": "Anula factura",
        }])

    def test_emision_exitosa(self):
        self.session.request.return_value = Respuesta(200, {
            "TOKEN": "tok123", "FOLIO": 197297,
            "XML": base64.b64encode(b"<DTE/>").decode(),
            "PDF": base64.b64encode(b"%PDF").decode(),
            "WARNING": [{"RznSoc": "Razón Social no corresponde"}],
        })
        r = self.of.emitir(dte(clave_idempotencia="clave-1"))
        self.assertTrue(r.exito)
        self.assertEqual((r.folio, r.track_id, r.estado), (197297, "tok123", EstadoSII.ENVIADO))
        self.assertEqual((r.xml_bytes, r.pdf_bytes), (b"<DTE/>", b"%PDF"))
        self.assertEqual(r.advertencias, ["RznSoc: Razón Social no corresponde"])
        _, kwargs = self.session.request.call_args
        self.assertEqual(kwargs["headers"]["Idempotency-Key"], "clave-1")
        self.assertEqual(kwargs["headers"]["apikey"], "clave-test")

    def test_error_de_datos_devuelve_rechazado(self):
        self.session.request.return_value = Respuesta(400, {"error": {
            "message": "Faltan campos obligatorios en el DTE", "code": "OF-02",
            "details": [{"field": "RUTEmisor", "issue": "Requerido"}],
        }})
        r = self.of.emitir(dte())
        self.assertFalse(r.exito)
        self.assertEqual(r.estado, EstadoSII.RECHAZADO)
        self.assertEqual(r.mensaje, "OF-02 Faltan campos obligatorios en el DTE (RUTEmisor: Requerido)")

    def test_idempotencia_recupera_documento_ya_emitido(self):
        self.session.request.side_effect = [
            Respuesta(400, {"error": {
                "message": "Este DTE ya fue emitido (Idempotency-Key)", "code": "OF-06",
                "details": [{"field": "token", "issue": "tokABC"}],
            }}),
            Respuesta(200, {"json": {"Encabezado": {"IdDoc": {"Folio": "555"}}}}),
            Respuesta(200, {"xml": base64.b64encode(b"<x/>").decode()}),
            Respuesta(200, {"pdf": base64.b64encode(b"%PDF").decode()}),
            Respuesta(200, {"estado": "Aceptado", "token": "tokABC"}),
        ]
        r = self.of.emitir(dte(clave_idempotencia="clave-1"))
        self.assertTrue(r.exito)
        self.assertEqual((r.folio, r.track_id, r.estado), (555, "tokABC", EstadoSII.ACEPTADO))
        self.assertEqual(r.xml_bytes, b"<x/>")

    def test_fallas_transitorias_lanzan_excepcion(self):
        for resp in (Respuesta(429, {"statusCode": 429}), Respuesta(503, None, "caído")):
            self.session.request.return_value = resp
            with self.assertRaises(EmisionError):
                self.of.emitir(dte())
        self.session.request.side_effect = requests.ConnectionError("sin red")
        with self.assertRaises(EmisionError):
            self.of.emitir(dte())

    def test_api_key_invalida(self):
        self.session.request.return_value = Respuesta(401, {"statusCode": 401})
        with self.assertRaises(ConfiguracionError):
            self.of.emitir(dte())

    def test_consultar_estado(self):
        casos = {
            "Aceptado": EstadoSII.ACEPTADO,
            "Pendiente": EstadoSII.ENVIADO,
            "Rechazado": EstadoSII.RECHAZADO,
            "Aceptado con Reparo": EstadoSII.ACEPTADO_REPAROS,
        }
        for texto, esperado in casos.items():
            self.session.request.return_value = Respuesta(200, {"estado": texto})
            self.assertEqual(self.of.consultar_estado("tok"), esperado)


class EmpresaEmisoraTests(TestCase):
    def test_actual_sin_configurar(self):
        with self.assertRaises(ConfiguracionError):
            EmpresaEmisora.actual()

    def test_como_emisor(self):
        EmpresaEmisora.objects.create(
            rut="76.795.561-8", razon_social="X SPA", giro="G",
            actividades="620200, 479100", direccion="D", comuna="C",
        )
        em = EmpresaEmisora.actual().como_emisor()
        self.assertEqual(em.rut, "76795561-8")
        self.assertEqual(em.actividades, [620200, 479100])
