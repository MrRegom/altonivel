"""Carga clientes, productos y cotizaciones de EJEMPLO para probar la app.

Los clientes son empresas ficticias (RUT válidos generados, correos
@ejemplo.cl). Los productos se basan en lo que vende Alto Nivel; los
precios son referenciales. Se puede ejecutar varias veces sin duplicar.

    python manage.py cargar_datos_ejemplo
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalogo.models import Producto
from clientes.models import Cliente
from core.rut import calcular_dv
from facturacion.montos import redondear
from ventas.models import Cotizacion, EstadoCotizacion, ItemCotizacion


def rut(cuerpo: int) -> str:
    return f"{cuerpo}-{calcular_dv(str(cuerpo))}"


CLIENTES = [
    dict(rut=rut(77452318), razon_social="Gamer Zone SpA", giro="Venta de videojuegos y accesorios",
         direccion="Av. Providencia 2150, local 12", comuna="Providencia", ciudad="Santiago",
         correo="compras.gamerzone@ejemplo.cl", telefono="+56 9 5555 0101", contacto="Camila Fuentes"),
    dict(rut=rut(76981204), razon_social="Estudio Pixel Creativo SpA", giro="Diseño gráfico y producción audiovisual",
         direccion="Los Leones 1300, of. 504", comuna="Providencia", ciudad="Santiago",
         correo="administracion.pixel@ejemplo.cl", telefono="+56 2 2555 0202", contacto="Matías Rojas"),
    dict(rut=rut(78103556), razon_social="Cibercafé Nexus Ltda", giro="Cibercafé y servicios de internet",
         direccion="Av. Valparaíso 820", comuna="Viña del Mar", ciudad="Viña del Mar",
         correo="nexus.cyber@ejemplo.cl", telefono="+56 9 5555 0303", contacto="Javiera Soto"),
    dict(rut=rut(65120447), razon_social="Corporación Colegio Tecnológico Andino", giro="Enseñanza básica y media",
         direccion="Av. Los Pajaritos 3400", comuna="Maipú", ciudad="Santiago",
         correo="adquisiciones.cta@ejemplo.cl", telefono="+56 2 2555 0404", contacto="Rodrigo Muñoz"),
    dict(rut=rut(79334801), razon_social="Constructora Los Robles Ltda", giro="Construcción de edificios",
         direccion="San Martín 456", comuna="Concepción", ciudad="Concepción",
         correo="finanzas.losrobles@ejemplo.cl", telefono="+56 41 255 0505", contacto="Patricia Lagos"),
    dict(rut=rut(77889010), razon_social="Herrera Streaming E.I.R.L.", giro="Creación de contenido digital",
         direccion="Barros Arana 210", comuna="Temuco", ciudad="Temuco",
         correo="contacto.herrera@ejemplo.cl", telefono="+56 9 5555 0606", contacto="Lucas Herrera"),
]

# (código, nombre, descripción, precio con IVA)
PRODUCTOS = [
    ("AN-NB-001", "Notebook Razer Blade 15 Advanced (usado)", "Notebook gamer, revisado y con garantía.", 1199990),
    ("AN-NB-002", 'MacBook Air 13,6" chip M2', "Apple MacBook Air con chip M2.", 1199990),
    ("AN-NB-003", 'MacBook Pro 16" 2019 Intel Core i7', "Apple MacBook Pro 16 pulgadas, Intel Core i7.", 1149990),
    ("AN-GPU-001", "Tarjeta de video ZOTAC GeForce RTX 4070 Twin Edge 12GB", "GDDR6X, ideal para juegos en 1440p.", 649990),
    ("AN-GPU-002", "Tarjeta de video ZOTAC GeForce RTX 4060 Ti 8GB", "GDDR6, DLSS 3.", 449990),
    ("AN-CPU-001", "Procesador Intel Core i7-14700K", "20 núcleos, hasta 5,6 GHz.", 399990),
    ("AN-CPU-002", "Procesador Intel Core i5-14600K", "14 núcleos, hasta 5,3 GHz.", 289990),
    ("AN-SSD-001", "SSD Samsung 970 EVO Plus 1TB NVMe M.2", "Hasta 3.500 MB/s de lectura.", 89990),
    ("AN-SRV-001", "Armado de PC gamer", "Armado, gestión de cables y pruebas de estrés.", 59990),
    ("AN-SRV-002", "Mantención y limpieza de PC o notebook", "Limpieza interna y cambio de pasta térmica.", 34990),
    ("AN-SRV-003", "Instalación de sistema operativo y drivers", "Windows, drivers y actualizaciones.", 24990),
    ("AN-ENV-001", "Despacho a regiones", "Envío por Chilexpress o Turbus.", 9990),
]

# (cliente por razón social, estado, días atrás, [(código, cantidad)])
COTIZACIONES = [
    ("Gamer Zone SpA", EstadoCotizacion.ACEPTADA, 2, [("AN-GPU-001", 2), ("AN-SRV-001", 2)]),
    ("Estudio Pixel Creativo SpA", EstadoCotizacion.ENVIADA, 1, [("AN-NB-003", 1), ("AN-SSD-001", 1)]),
    ("Cibercafé Nexus Ltda", EstadoCotizacion.BORRADOR, 0,
     [("AN-GPU-002", 4), ("AN-SRV-002", 4), ("AN-ENV-001", 1)]),
]


class Command(BaseCommand):
    help = "Carga clientes, productos y cotizaciones de ejemplo (no duplica)."

    @transaction.atomic
    def handle(self, *args, **options):
        for datos in CLIENTES:
            Cliente.objects.update_or_create(rut=datos["rut"], defaults=datos)

        productos = {}
        for codigo, nombre, descripcion, con_iva in PRODUCTOS:
            neto = redondear(Decimal(con_iva) / Decimal("1.19"))
            productos[codigo], _ = Producto.objects.update_or_create(
                codigo=codigo,
                defaults=dict(nombre=nombre, descripcion=descripcion, precio_neto=neto, activo=True),
            )

        hoy = timezone.localdate()
        creadas = 0
        for razon, estado, dias, lineas in COTIZACIONES:
            cliente = Cliente.objects.get(razon_social=razon)
            if cliente.cotizaciones.exists():
                continue
            fecha = hoy - timedelta(days=dias)
            cot = Cotizacion.objects.create(
                cliente=cliente, fecha=fecha, valida_hasta=fecha + timedelta(days=15), estado=estado,
                observaciones="Precios incluyen garantía. Despacho a convenir.",
                enviada_en=timezone.now() if estado != EstadoCotizacion.BORRADOR else None,
            )
            for codigo, cantidad in lineas:
                p = productos[codigo]
                ItemCotizacion.objects.create(
                    cotizacion=cot, producto=p, descripcion=p.nombre,
                    cantidad=Decimal(cantidad), precio_unitario=p.precio_neto, exento=p.exento,
                )
            creadas += 1

        self.stdout.write(self.style.SUCCESS(
            f"Listo: {len(CLIENTES)} clientes, {len(PRODUCTOS)} productos y {creadas} cotizaciones nuevas."
        ))
