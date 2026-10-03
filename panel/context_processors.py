from django.conf import settings

from facturacion.models import EmpresaEmisora


def marca(request):
    """Nombre y logo de la empresa para el encabezado de todas las páginas."""
    if not request.user.is_authenticated:
        return {"marca_nombre": "Alto Nivel", "marca_logo": None}
    modo_prueba = getattr(settings, "MODO_PRUEBA", False)
    empresa = EmpresaEmisora.objects.first()
    return {
        "marca_nombre": (empresa.nombre_visible if empresa else "") or "Alto Nivel",
        "marca_logo": empresa.logo.url if empresa and empresa.logo else None,
        "modo_prueba": modo_prueba,
    }
