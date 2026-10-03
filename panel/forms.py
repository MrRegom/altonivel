from django import forms
from django.forms import inlineformset_factory

from catalogo.models import Producto
from clientes.models import Cliente
from core.rut import RutInvalidoError, normalizar
from facturacion.models import EmpresaEmisora
from ventas.models import Cotizacion, ItemCotizacion


class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = [
            "rut", "razon_social", "giro", "direccion", "comuna", "ciudad",
            "correo", "telefono", "contacto", "activo",
        ]
        widgets = {
            "rut": forms.TextInput(attrs={"placeholder": "12345678-9", "autofocus": True, "data-rut": ""}),
            "giro": forms.TextInput(attrs={"maxlength": 200}),
        }
        help_texts = {
            "giro": "Obligatorio para facturar. En la factura se usan los primeros 40 caracteres.",
            "direccion": "Obligatoria para facturar.",
            "comuna": "Obligatoria para facturar.",
            "correo": "Aquí se envían cotizaciones y facturas.",
        }

    def clean_rut(self):
        try:
            rut = normalizar(self.cleaned_data["rut"])
        except RutInvalidoError:
            raise forms.ValidationError("El RUT no es válido. Revise el dígito verificador.")
        existe = Cliente.objects.filter(rut=rut).exclude(pk=self.instance.pk)
        if existe.exists():
            raise forms.ValidationError(f"Ya existe un cliente con este RUT: {existe.first().razon_social}.")
        return rut


class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ["codigo", "nombre", "descripcion", "precio_neto", "exento", "activo"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}
        labels = {"precio_neto": "Precio neto (sin IVA)", "codigo": "Código / SKU"}


class CotizacionForm(forms.ModelForm):
    class Meta:
        model = Cotizacion
        fields = ["cliente", "fecha", "valida_hasta", "observaciones"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "valida_hasta": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "observaciones": forms.Textarea(
                attrs={"rows": 3, "placeholder": "Condiciones, plazos de entrega, garantía…"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        activos = Cliente.objects.filter(activo=True)
        if self.instance.pk:
            activos = activos | Cliente.objects.filter(pk=self.instance.cliente_id)
        self.fields["cliente"].queryset = activos.order_by("razon_social")
        self.fields["cliente"].empty_label = "Seleccione un cliente…"


class ItemCotizacionForm(forms.ModelForm):
    class Meta:
        model = ItemCotizacion
        fields = ["producto", "descripcion", "cantidad", "precio_unitario", "exento"]
        widgets = {
            "descripcion": forms.TextInput(attrs={"placeholder": "Descripción del ítem"}),
            "cantidad": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
            "precio_unitario": forms.NumberInput(attrs={"step": "1", "min": "0"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].queryset = Producto.objects.filter(activo=True)
        self.fields["producto"].required = False
        self.fields["producto"].empty_label = "— Ítem libre —"


ItemFormSet = inlineformset_factory(
    Cotizacion,
    ItemCotizacion,
    form=ItemCotizacionForm,
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class EmpresaEmisoraForm(forms.ModelForm):
    class Meta:
        model = EmpresaEmisora
        widgets = {"rut": forms.TextInput(attrs={"placeholder": "12345678-9", "data-rut": ""})}
        fields = [
            "nombre_fantasia", "logo", "sitio_web",
            "rut", "razon_social", "giro", "actividades",
            "direccion", "comuna", "ciudad", "codigo_sucursal",
            "correo", "telefono",
        ]
