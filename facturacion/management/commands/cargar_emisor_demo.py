"""Carga como empresa emisora la empresa de PRUEBA de OpenFactura.

Sirve solo para el ambiente de desarrollo (dev-api.haulmer.com), junto
con la API key pública que OpenFactura publica en su documentación.
NUNCA usar en producción: ahí van los datos reales de la empresa.
"""
from django.core.management.base import BaseCommand

from facturacion.models import EmpresaEmisora

DEMO = {
    "rut": "76795561-8",
    "razon_social": "HAULMER CHILE SPA",
    "giro": "VENTA AL POR MENOR EN EMPRESAS DE VENTA A DISTANCIA VÍA INTERNET; COMERCIO ELEC",
    "actividades": "479100",
    "direccion": "ARTURO PRAT 527 CURICO",
    "comuna": "Curicó",
    "codigo_sucursal": "81303347",
}
API_KEY_DEMO = "928e15a2d14d4a6292345f04960f4bd3"


class Command(BaseCommand):
    help = "Configura la empresa de prueba de OpenFactura como emisora (solo desarrollo)."

    def handle(self, *args, **options):
        empresa = EmpresaEmisora.objects.first()
        if empresa and empresa.rut != DEMO["rut"]:
            self.stderr.write(self.style.ERROR(
                f"Ya hay una empresa emisora real configurada ({empresa}). No se modificó."
            ))
            return
        if empresa:
            for campo, valor in DEMO.items():
                setattr(empresa, campo, valor)
            empresa.save()
        else:
            EmpresaEmisora.objects.create(**DEMO)
        self.stdout.write(self.style.SUCCESS("Empresa de prueba cargada."))
        self.stdout.write(
            "En .env usa:\n"
            "  EMISOR_BACKEND=openfactura\n"
            f"  OPENFACTURA_API_KEY={API_KEY_DEMO}\n"
            "  OPENFACTURA_BASE_URL=https://dev-api.haulmer.com"
        )
