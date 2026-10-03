"""Interfaz de gestión: inicio, clientes, productos, cotizaciones y facturas."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from functools import wraps

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q, Sum, Value
from django.db.models.functions import Replace, Upper
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalogo.models import Producto
from clientes.models import Cliente
from facturacion.constants import EstadoSII, TipoDTE
from facturacion.exceptions import DatosInvalidosError, EmisionError
from facturacion.models import EmpresaEmisora
from ventas import services
from ventas.models import Cotizacion, DocumentoTributario, EstadoCotizacion

from .forms import (
    Usuario,
    UsuarioForm,
    ClienteForm,
    CotizacionForm,
    EmpresaEmisoraForm,
    ItemFormSet,
    ProductoForm,
)

POR_PAGINA = 20

# Documentos que cuentan como facturación real (no rechazados ni pendientes de envío).
ESTADOS_FACTURADOS = (EstadoSII.ENVIADO, EstadoSII.ACEPTADO, EstadoSII.ACEPTADO_REPAROS)


def _paginar(request, queryset):
    return Paginator(queryset, POR_PAGINA).get_page(request.GET.get("pagina"))


def _rut_sin_formato(campo: str):
    """Expresión SQL del RUT sin guion, para buscar '162334069' o '16.233.406-9' por igual."""
    return Upper(Replace(F(campo), Value("-"), Value("")))


def _filtro_rut(queryset, campo: str, q: str):
    """Anota el RUT sin formato y devuelve (queryset, Q) para buscar por RUT."""
    limpio = "".join(c for c in q if c.isalnum()).upper()
    if len(limpio) < 3 or not limpio[:-1].isdigit():
        return queryset, Q(pk__in=[])
    return queryset.annotate(_rut_busqueda=_rut_sin_formato(campo)), Q(_rut_busqueda__contains=limpio)


def _cotizaciones_con_items():
    return Cotizacion.objects.select_related("cliente").prefetch_related("items")


# ----------------------------------------------------------------------
# Inicio
# ----------------------------------------------------------------------
@login_required
def inicio(request):
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)

    cot_mes = list(_cotizaciones_con_items().filter(fecha__gte=inicio_mes))
    facturado_mes = (
        DocumentoTributario.objects.filter(
            fecha_emision__gte=inicio_mes, estado_sii__in=ESTADOS_FACTURADOS
        )
        .exclude(tipo_dte=TipoDTE.NOTA_CREDITO)
        .aggregate(total=Sum("total"), n=Count("id"))
    )
    por_facturar = list(
        _cotizaciones_con_items().filter(estado=EstadoCotizacion.ACEPTADA).order_by("-fecha")
    )
    atencion = DocumentoTributario.objects.select_related("cliente").filter(
        Q(estado_sii__in=[EstadoSII.PENDIENTE, EstadoSII.RECHAZADO, EstadoSII.ENVIADO])
        | (~Q(error_mensaje="") & Q(estado_sii__in=[EstadoSII.ACEPTADO, EstadoSII.ACEPTADO_REPAROS])),
        creado_en__gte=timezone.now() - timedelta(days=30),
    ).order_by("-creado_en")[:6]

    contexto = {
        "kpi": {
            "cotizado_mes": sum((c.total for c in cot_mes), Decimal("0")),
            "cotizaciones_mes": len(cot_mes),
            "facturado_mes": facturado_mes["total"] or 0,
            "facturas_mes": facturado_mes["n"],
            "por_facturar_monto": sum((c.total for c in por_facturar), Decimal("0")),
            "por_facturar": len(por_facturar),
            "esperando_sii": DocumentoTributario.objects.filter(estado_sii=EstadoSII.ENVIADO).count(),
        },
        "ultimas_cotizaciones": _cotizaciones_con_items().order_by("-creado_en")[:6],
        "por_facturar": por_facturar[:5],
        "atencion": atencion,
        "mes": hoy,
        "empresa_configurada": EmpresaEmisora.objects.exists(),
    }
    return render(request, "panel/inicio.html", contexto)


# ----------------------------------------------------------------------
# Clientes
# ----------------------------------------------------------------------
@login_required
def clientes_lista(request):
    q = request.GET.get("q", "").strip()
    clientes = Cliente.objects.annotate(
        n_cotizaciones=Count("cotizaciones", distinct=True)
    ).order_by("razon_social")
    if q:
        clientes, por_rut = _filtro_rut(clientes, "rut", q)
        clientes = clientes.filter(Q(razon_social__icontains=q) | por_rut | Q(correo__icontains=q))
    if request.GET.get("inactivos") != "1":
        clientes = clientes.filter(activo=True)
    return render(request, "panel/clientes/lista.html", {"pagina": _paginar(request, clientes), "q": q})


@login_required
def cliente_form(request, pk=None):
    cliente = get_object_or_404(Cliente, pk=pk) if pk else None
    form = ClienteForm(request.POST or None, instance=cliente)
    if request.method == "POST" and form.is_valid():
        cliente = form.save()
        messages.success(request, f"Cliente «{cliente.razon_social}» guardado.")
        siguiente = request.GET.get("next")
        if siguiente == "cotizacion":
            return redirect(f"/cotizaciones/nueva/?cliente={cliente.pk}")
        return redirect("panel:cliente_detalle", pk=cliente.pk)
    return render(request, "panel/clientes/form.html", {"form": form, "cliente": cliente})


@login_required
def cliente_detalle(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    cotizaciones = _cotizaciones_con_items().filter(cliente=cliente).order_by("-fecha", "-numero")
    documentos = cliente.documentos.order_by("-fecha_emision", "-folio")
    facturado = documentos.filter(estado_sii__in=ESTADOS_FACTURADOS).aggregate(t=Sum("total"))["t"] or 0
    return render(
        request,
        "panel/clientes/detalle.html",
        {"cliente": cliente, "cotizaciones": cotizaciones, "documentos": documentos, "facturado": facturado},
    )


# ----------------------------------------------------------------------
# Productos
# ----------------------------------------------------------------------
@login_required
def productos_lista(request):
    q = request.GET.get("q", "").strip()
    productos = Producto.objects.all()
    if q:
        productos = productos.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q))
    if request.GET.get("inactivos") != "1":
        productos = productos.filter(activo=True)
    return render(request, "panel/productos/lista.html", {"pagina": _paginar(request, productos), "q": q})


@login_required
def producto_form(request, pk=None):
    producto = get_object_or_404(Producto, pk=pk) if pk else None
    form = ProductoForm(request.POST or None, instance=producto)
    if request.method == "POST" and form.is_valid():
        producto = form.save()
        messages.success(request, f"Producto «{producto.nombre}» guardado.")
        return redirect("panel:productos")
    return render(request, "panel/productos/form.html", {"form": form, "producto": producto})


# ----------------------------------------------------------------------
# Cotizaciones
# ----------------------------------------------------------------------
@login_required
def cotizaciones_lista(request):
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    cotizaciones = _cotizaciones_con_items().order_by("-fecha", "-numero")
    if q:
        cotizaciones, por_rut = _filtro_rut(cotizaciones, "cliente__rut", q)
        filtro = Q(cliente__razon_social__icontains=q) | por_rut
        if q.isdigit():
            filtro |= Q(numero=int(q))
        cotizaciones = cotizaciones.filter(filtro)
    if estado:
        cotizaciones = cotizaciones.filter(estado=estado)
    conteo = dict(Cotizacion.objects.values_list("estado").annotate(n=Count("id")))
    estados = [(valor, nombre, conteo.get(valor, 0)) for valor, nombre in EstadoCotizacion.choices]
    return render(
        request,
        "panel/cotizaciones/lista.html",
        {"pagina": _paginar(request, cotizaciones), "q": q, "estado": estado, "estados": estados,
         "total": sum(conteo.values())},
    )


def _es_editable(cotizacion: Cotizacion) -> bool:
    return cotizacion.estado != EstadoCotizacion.FACTURADA and not cotizacion.documentos.exclude(
        estado_sii=EstadoSII.RECHAZADO
    ).exists()


def _productos_json():
    return {
        str(p.pk): {
            "nombre": p.nombre,
            "precio": int(p.precio_neto),
            "exento": p.exento,
        }
        for p in Producto.objects.filter(activo=True)
    }


@login_required
def cotizacion_form(request, pk=None):
    cotizacion = get_object_or_404(Cotizacion, pk=pk) if pk else Cotizacion()
    if pk and not _es_editable(cotizacion):
        messages.error(request, "Esta cotización ya fue facturada y no se puede modificar.")
        return redirect("panel:cotizacion_detalle", pk=pk)

    inicial = {}
    if not pk:
        hoy = timezone.localdate()
        inicial = {"fecha": hoy, "valida_hasta": hoy + timedelta(days=15)}
        if request.GET.get("cliente"):
            inicial["cliente"] = request.GET["cliente"]

    form = CotizacionForm(request.POST or None, instance=cotizacion, initial=inicial)
    formset = ItemFormSet(request.POST or None, instance=cotizacion, prefix="items")

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            cotizacion = form.save()
            formset.instance = cotizacion
            formset.save()
        messages.success(request, f"Cotización N°{cotizacion.numero} guardada.")
        return redirect("panel:cotizacion_detalle", pk=cotizacion.pk)

    return render(
        request,
        "panel/cotizaciones/form.html",
        {"form": form, "formset": formset, "cotizacion": cotizacion if pk else None,
         "productos": _productos_json()},
    )


@login_required
def cotizacion_detalle(request, pk):
    cotizacion = get_object_or_404(_cotizaciones_con_items(), pk=pk)
    documentos = cotizacion.documentos.order_by("-creado_en")
    return render(
        request,
        "panel/cotizaciones/detalle.html",
        {
            "c": cotizacion,
            "documentos": documentos,
            "editable": _es_editable(cotizacion),
            "puede_facturar": _es_editable(cotizacion)
            and cotizacion.estado != EstadoCotizacion.RECHAZADA,
            "solo_exentos": all(i.exento for i in cotizacion.items.all()),
        },
    )


@login_required
def cotizacion_pdf(request, pk):
    from ventas.pdf import cotizacion_pdf as generar

    cotizacion = get_object_or_404(_cotizaciones_con_items(), pk=pk)
    respuesta = HttpResponse(generar(cotizacion), content_type="application/pdf")
    disposicion = "attachment" if request.GET.get("descargar") else "inline"
    respuesta["Content-Disposition"] = f'{disposicion}; filename="cotizacion_{cotizacion.numero}.pdf"'
    return respuesta


@login_required
@require_POST
def cotizacion_enviar(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    try:
        services.enviar_cotizacion_por_correo(cotizacion)
        messages.success(request, f"Cotización enviada a {cotizacion.cliente.correo}.")
    except Exception as exc:
        messages.error(request, f"No se pudo enviar: {exc}")
    return redirect("panel:cotizacion_detalle", pk=pk)


@login_required
@require_POST
def cotizacion_estado(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    nuevo = request.POST.get("estado")
    permitidos = {EstadoCotizacion.ACEPTADA, EstadoCotizacion.RECHAZADA, EstadoCotizacion.BORRADOR}
    if nuevo not in permitidos or not _es_editable(cotizacion):
        messages.error(request, "No se puede cambiar el estado de esta cotización.")
    else:
        cotizacion.estado = nuevo
        cotizacion.save(update_fields=["estado", "actualizado_en"])
        messages.success(request, f"Cotización marcada como {cotizacion.get_estado_display().lower()}.")
    return redirect("panel:cotizacion_detalle", pk=pk)


@login_required
@require_POST
def cotizacion_emitir(request, pk):
    cotizacion = get_object_or_404(Cotizacion, pk=pk)
    try:
        tipo = int(request.POST.get("tipo_dte", TipoDTE.FACTURA_AFECTA))
    except ValueError:
        raise Http404
    if tipo not in (TipoDTE.FACTURA_AFECTA, TipoDTE.FACTURA_EXENTA):
        raise Http404
    try:
        doc = services.emitir_documento(cotizacion, tipo)
    except DatosInvalidosError as exc:
        for error in exc.errores:
            messages.error(request, error)
        return redirect("panel:cotizacion_detalle", pk=pk)
    except EmisionError as exc:
        messages.error(
            request,
            f"{exc} El documento quedó pendiente: puede reintentarlo sin riesgo de duplicarlo.",
        )
        doc = cotizacion.documentos.order_by("-creado_en").first()
        if doc:
            return redirect("panel:documento_detalle", pk=doc.pk)
        return redirect("panel:cotizacion_detalle", pk=pk)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("panel:cotizacion_detalle", pk=pk)

    if doc.estado_sii == EstadoSII.RECHAZADO:
        messages.error(request, f"El documento fue rechazado: {doc.error_mensaje}")
    else:
        messages.success(
            request, f"{doc.get_tipo_dte_display()} N°{doc.folio} emitida. Estado: {doc.get_estado_sii_display()}."
        )
    return redirect("panel:documento_detalle", pk=doc.pk)


@login_required
@require_POST
def cotizacion_duplicar(request, pk):
    original = get_object_or_404(_cotizaciones_con_items(), pk=pk)
    hoy = timezone.localdate()
    with transaction.atomic():
        copia = Cotizacion.objects.create(
            cliente=original.cliente,
            fecha=hoy,
            valida_hasta=hoy + timedelta(days=15),
            observaciones=original.observaciones,
        )
        for item in original.items.all():
            item.pk = None
            item.cotizacion = copia
            item.save()
    messages.success(request, f"Se creó la cotización N°{copia.numero} a partir de la N°{original.numero}.")
    return redirect("panel:cotizacion_editar", pk=copia.pk)


# ----------------------------------------------------------------------
# Documentos tributarios (facturas)
# ----------------------------------------------------------------------
@login_required
def documentos_lista(request):
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    documentos = DocumentoTributario.objects.select_related("cliente", "cotizacion").order_by(
        "-fecha_emision", "-folio"
    )
    if q:
        documentos, por_rut = _filtro_rut(documentos, "cliente__rut", q)
        filtro = Q(cliente__razon_social__icontains=q) | por_rut
        if q.isdigit():
            filtro |= Q(folio=int(q))
        documentos = documentos.filter(filtro)
    if estado:
        documentos = documentos.filter(estado_sii=estado)
    return render(
        request,
        "panel/documentos/lista.html",
        {"pagina": _paginar(request, documentos), "q": q, "estado": estado, "estados": EstadoSII.CHOICES},
    )


@login_required
def documento_detalle(request, pk):
    doc = get_object_or_404(DocumentoTributario.objects.select_related("cliente", "cotizacion"), pk=pk)
    return render(
        request,
        "panel/documentos/detalle.html",
        {
            "d": doc,
            "aceptado": doc.estado_sii in services.ESTADOS_ACEPTADOS,
            "puede_reintentar": doc.estado_sii == EstadoSII.PENDIENTE,
            "puede_actualizar": doc.estado_sii == EstadoSII.ENVIADO and doc.track_id,
        },
    )


@login_required
@require_POST
def documento_accion(request, pk, accion):
    doc = get_object_or_404(DocumentoTributario, pk=pk)
    try:
        if accion == "actualizar":
            services.actualizar_estado(doc)
            messages.success(request, f"Estado ante el SII: {doc.get_estado_sii_display()}.")
        elif accion == "reintentar":
            services.reintentar_emision(doc)
            messages.success(request, f"Documento emitido: folio {doc.folio} ({doc.get_estado_sii_display()}).")
        elif accion == "enviar":
            services.enviar_documento_por_correo(doc)
            messages.success(request, f"Documento enviado a {doc.cliente.correo}.")
        else:
            raise Http404
    except DatosInvalidosError as exc:
        for error in exc.errores:
            messages.error(request, error)
    except (EmisionError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect("panel:documento_detalle", pk=pk)


@login_required
def documento_archivo(request, pk, formato):
    doc = get_object_or_404(DocumentoTributario, pk=pk)
    archivo = {"pdf": doc.pdf, "xml": doc.xml}.get(formato)
    if not archivo:
        raise Http404("El documento no tiene ese archivo.")
    nombre = f"{doc.get_tipo_dte_display()} {doc.folio}.{formato}"
    return FileResponse(
        archivo.open("rb"),
        as_attachment=formato == "xml" or bool(request.GET.get("descargar")),
        filename=nombre,
        content_type="application/pdf" if formato == "pdf" else "application/xml",
    )


# ----------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------
def solo_admin(vista):
    """Restringe la vista a administradores (usuarios con rol Administrador)."""

    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, "Esta sección es solo para administradores.")
            return redirect("panel:inicio")
        return vista(request, *args, **kwargs)

    return envoltura


@solo_admin
def empresa(request):
    instancia = EmpresaEmisora.objects.first()
    form = EmpresaEmisoraForm(request.POST or None, request.FILES or None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Datos de la empresa guardados.")
        return redirect("panel:empresa")
    return render(request, "panel/empresa.html", {"form": form, "empresa": instancia})


# ----------------------------------------------------------------------
# Usuarios
# ----------------------------------------------------------------------
def formatear_busqueda_rut(limpio: str) -> str:
    """'162334069' -> '16233406-9' para buscar contra el RUT guardado."""
    if len(limpio) >= 8 and limpio[:-1].isdigit():
        return f"{limpio[:-1]}-{limpio[-1].upper()}"
    return limpio


@solo_admin
def usuarios_lista(request):
    q = request.GET.get("q", "").strip()
    usuarios = Usuario.objects.order_by("-is_active", "first_name", "last_name")
    if q:
        limpio = "".join(c for c in q if c.isalnum())
        usuarios = usuarios.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
            | Q(username__icontains=formatear_busqueda_rut(limpio))
        )
    return render(request, "panel/usuarios/lista.html", {"pagina": _paginar(request, usuarios), "q": q})


@solo_admin
def usuario_form(request, pk=None):
    usuario = get_object_or_404(Usuario, pk=pk) if pk else None
    form = UsuarioForm(request.POST or None, instance=usuario, editor=request.user)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        messages.success(request, f"Usuario {usuario.get_full_name() or usuario.username} guardado.")
        return redirect("panel:usuarios")
    return render(request, "panel/usuarios/form.html", {"form": form, "usuario": usuario})


@solo_admin
def usuario_clave(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    form = SetPasswordForm(usuario, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if usuario.pk == request.user.pk:
            update_session_auth_hash(request, usuario)
        messages.success(request, f"Contraseña de {usuario.get_full_name() or usuario.username} actualizada.")
        return redirect("panel:usuarios")
    return render(request, "panel/usuarios/clave.html", {"form": form, "usuario": usuario})


@login_required
def mi_clave(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        update_session_auth_hash(request, form.user)
        messages.success(request, "Tu contraseña fue actualizada.")
        return redirect("panel:inicio")
    return render(request, "panel/mi_clave.html", {"form": form})
