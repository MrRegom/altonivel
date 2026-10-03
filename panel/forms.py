from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
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
        fields = ["codigo", "nombre", "descripcion", "precio_neto", "exento", "activo", "imagen"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 3}),
            "imagen": forms.FileInput(attrs={"accept": "image/*"}),
        }
        labels = {"precio_neto": "Precio neto (sin IVA)", "codigo": "Código / SKU"}

    quitar_imagen = forms.BooleanField(label="Quitar foto", required=False)

    def save(self, commit=True):
        producto = super().save(commit=False)
        if self.cleaned_data.get("quitar_imagen") and not self.files.get("imagen"):
            producto.imagen = None
        if commit:
            producto.save()
        return producto


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


# ----------------------------------------------------------------------
# Ingreso y usuarios (el nombre de usuario es el RUT normalizado)
# ----------------------------------------------------------------------
Usuario = get_user_model()


class IngresoRutForm(AuthenticationForm):
    """Ingreso con RUT (con o sin puntos y guion) y contraseña."""

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "RUT o contraseña incorrectos.",
        "rut_invalido": "El RUT no es válido. Revisa el dígito verificador.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "RUT"

    def clean(self):
        rut = self.cleaned_data.get("username")
        if rut:
            try:
                self.cleaned_data["username"] = normalizar(rut)
            except RutInvalidoError:
                raise forms.ValidationError(self.error_messages["rut_invalido"], code="rut_invalido")
        return super().clean()


class UsuarioForm(forms.ModelForm):
    ROLES = [("vendedor", "Vendedor"), ("admin", "Administrador")]

    rut = forms.CharField(
        label="RUT", max_length=12,
        widget=forms.TextInput(attrs={"placeholder": "12345678-9", "data-rut": "", "autofocus": True}),
        help_text="Con este RUT inicia sesión.",
    )
    rol = forms.ChoiceField(
        label="Rol", choices=ROLES,
        help_text="El administrador además gestiona usuarios y los datos de la empresa.",
    )
    clave1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    clave2 = forms.CharField(label="Repetir contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "email", "is_active"]
        labels = {"first_name": "Nombre", "last_name": "Apellido", "email": "Correo", "is_active": "Activo"}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self.fields["first_name"].required = True
        if self.instance.pk:
            self.fields["rut"].initial = self.instance.username
            self.fields["rol"].initial = "admin" if self.instance.is_superuser else "vendedor"
            # La contraseña de un usuario existente se cambia en su propia pantalla.
            del self.fields["clave1"]
            del self.fields["clave2"]
        else:
            # Un usuario nuevo siempre queda activo (el campo no se muestra al crear).
            del self.fields["is_active"]

    def clean_rut(self):
        try:
            rut = normalizar(self.cleaned_data["rut"])
        except RutInvalidoError:
            raise forms.ValidationError("El RUT no es válido. Revisa el dígito verificador.")
        if Usuario.objects.filter(username=rut).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con este RUT.")
        return rut

    def clean(self):
        datos = super().clean()
        es_yo = self.editor is not None and self.instance.pk == self.editor.pk
        if es_yo and datos.get("rol") != "admin":
            self.add_error("rol", "No puedes quitarte el rol de administrador a ti mismo.")
        if es_yo and not datos.get("is_active", True):
            self.add_error("is_active", "No puedes desactivar tu propio usuario.")
        if "clave1" in self.fields:
            c1, c2 = datos.get("clave1"), datos.get("clave2")
            if c1 and c2 and c1 != c2:
                self.add_error("clave2", "Las contraseñas no coinciden.")
            elif c1:
                try:
                    password_validation.validate_password(c1, self.instance)
                except forms.ValidationError as exc:
                    self.add_error("clave1", exc)
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = self.cleaned_data["rut"]
        es_admin = self.cleaned_data["rol"] == "admin"
        usuario.is_superuser = es_admin
        usuario.is_staff = es_admin
        if "clave1" in self.fields:
            usuario.set_password(self.cleaned_data["clave1"])
        if commit:
            usuario.save()
        return usuario
