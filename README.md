# Facturación SII (Django)

App para cotizar y facturar con integración al SII, pensada para reemplazar
el flujo manual: cotizar → PDF → correo → (cliente acepta) → factura en el
SII → descargar → correo. Aquí todo eso queda en dos clics.

## Qué hace

- **Clientes**: se guardan una vez (RUT, razón social, giro, dirección, comuna, correo).
- **Catálogo**: productos/servicios con precio para armar cotizaciones rápido.
- **Cotizaciones**: se crean con ítems, calculan neto/IVA/total y se envían por correo en PDF.
- **Facturación**: desde una cotización se emite el DTE, se guardan PDF y XML y se envía al cliente.
- **Historial**: estados de cotización (borrador, enviada, aceptada, facturada) y de documento ante el SII.

## Arquitectura clave: emisión intercambiable

La app **no depende de un proveedor**. Toda la lógica de negocio habla con
una sola interfaz (`facturacion/base.py`, clase `EmisorDTE`). El backend se
elige con la variable `EMISOR_BACKEND`:

| Backend       | Para qué sirve                                            |
|---------------|-----------------------------------------------------------|
| `consola`     | Desarrollo. Simula la emisión sin SII ni certificado.     |
| `openfactura` | Emisión real vía API de OpenFactura (Haulmer). Probado en su ambiente de desarrollo. |
| `sii_directo` | A futuro: integración directa con los web services del SII (aún no implementado). |

Cambiar de proveedor o pasar a integración directa **no toca** los modelos ni
las vistas: solo se cambia el backend.

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: . .venv/bin/activate)
pip install -r requirements.txt

cp .env.example .env        # ajustar valores
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Entrar a http://localhost:8000/ (panel de Alto Nivel: inicio, cotizaciones,
facturas, clientes, productos y "Mi empresa"). El admin de Django sigue en
http://localhost:8000/admin/ para tareas técnicas. Con `EMISOR_BACKEND=consola` (por defecto) y el correo en modo
consola, se puede probar todo el flujo sin cuenta ni certificado real.

## Flujo de emisión

1. **Admin > Facturación electrónica > Empresa emisora**: cargar una vez los
   datos de quien factura, idénticos a Mi SII > Datos personales y tributarios
   (RUT, razón social, giro, código de actividad, dirección y código de sucursal).
2. **Cotizaciones > acción "Emitir factura electrónica (33)" / "Emitir factura exenta (34)"**.
   - Antes de enviar se validan los datos (ej: cliente sin giro o dirección).
   - El documento se guarda como *Pendiente* antes de llamar al proveedor. Si se
     corta la conexión, queda registrado y se usa **Reintentar emisión**: la
     clave de idempotencia evita emitir dos veces (válido por 24 h).
3. El documento queda *Enviado al SII*. Su estado se actualiza con la acción
   **Actualizar estado ante el SII** o con el comando (programarlo cada 5-10 min):

   ```bash
   python manage.py actualizar_estados_dte
   ```
4. Cuando el SII lo **acepta**, se envía automáticamente al correo del cliente
   con PDF y XML (`ENVIAR_DTE_AL_ACEPTAR=True`).

### Probar con OpenFactura sin cuenta

OpenFactura tiene un ambiente de desarrollo abierto con una empresa de prueba:

```bash
python manage.py cargar_emisor_demo   # carga la empresa demo como emisora
```

y en `.env`: `EMISOR_BACKEND=openfactura`,
`OPENFACTURA_API_KEY=928e15a2d14d4a6292345f04960f4bd3`,
`OPENFACTURA_BASE_URL=https://dev-api.haulmer.com`. Los folios son simulados.

Para producción: contratar OpenFactura, generar la API key de la empresa en su
plataforma, usar `https://api.haulmer.com` y reemplazar la empresa emisora por
los datos reales.

## Despliegue en servidor (Docker)

En el servidor (Ubuntu con Docker y Docker Compose):

```bash
git clone https://github.com/MrRegom/altonivel.git /opt/altonivel
cd /opt/altonivel && bash servidor.sh
docker compose exec web python manage.py admin_rut <tu-rut>
```

La app queda en `http://<ip-del-servidor>:8090`. Para actualizar después de
subir cambios a GitHub: `cd /opt/altonivel && bash servidor.sh`.

- `servidor.sh` crea `.env.produccion` la primera vez, con una clave secreta propia.
  Ahí se configuran el correo SMTP y la API key de OpenFactura.
- Base de datos, PDF y XML quedan en el volumen Docker `altonivel_data`.
- El contenedor `altonivel-estados` consulta al SII cada 5 minutos.
- Se ingresa con **RUT y contraseña**. `admin_rut` crea el superadministrador
  (o convierte uno existente). Los demás usuarios se crean en el panel:
  Configuración → Usuarios.

## Estructura

```
config/          Configuración del proyecto
core/            Base común: modelo con timestamps, utilidades de RUT (módulo 11)
clientes/        Modelo y admin de clientes
catalogo/        Productos y servicios
ventas/          Cotizaciones, ítems, documentos, lógica (services.py), PDF
panel/           Interfaz web (vistas, plantillas, CSS con la marca Alto Nivel)
facturacion/     Capa de emisión de DTE
  base.py          Interfaz EmisorDTE + tipos neutrales (DTEData, DTEResult)
  models.py        EmpresaEmisora (datos de quien factura)
  montos.py        Redondeo y totales según reglas del SII
  validacion.py    Validaciones previas y largos máximos de campos
  factory.py       Selecciona el backend según settings
  constants.py     Tipos de DTE e IVA
  providers/       consola, openfactura, sii_directo
```

## Seguridad

- El **certificado digital** (.pfx/.p12) y las claves van en variables de
  entorno o archivos fuera del repo. `.gitignore` ya excluye `*.pfx`, `*.p12`, `.env`.
- La app **no usa** el usuario y clave del portal del SII: firma con el
  certificado y consume folios CAF. Ese login no es el punto de integración.

## Pendientes para producción

1. Contratar OpenFactura, cargar la API key de producción y los datos reales
   de la empresa emisora.
2. Hacer una primera emisión real de bajo monto y verificarla en el SII.
3. (Opcional, más adelante) Implementar `sii_directo` siguiendo el plan del
   docstring en `facturacion/providers/sii_directo.py`.
