from django.test import SimpleTestCase

from core.rut import calcular_dv, es_valido, formatear, normalizar, RutInvalidoError


class RutTests(SimpleTestCase):
    def test_dv_conocidos(self):
        self.assertEqual(calcular_dv("76192083"), "9")
        self.assertEqual(calcular_dv("12345678"), "5")

    def test_validos_e_invalidos(self):
        self.assertTrue(es_valido("76.192.083-9"))
        self.assertTrue(es_valido("761920839"))
        self.assertFalse(es_valido("76192083-0"))
        self.assertFalse(es_valido("abc"))

    def test_normalizar_y_formatear(self):
        self.assertEqual(normalizar("76.192.083-9"), "76192083-9")
        self.assertEqual(formatear("761920839"), "76.192.083-9")

    def test_normalizar_invalido_lanza(self):
        with self.assertRaises(RutInvalidoError):
            normalizar("11111111-2")
