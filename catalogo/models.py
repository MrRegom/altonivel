"""Catálogo de productos y servicios."""
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import models

from core.models import TimeStampedModel


class Producto(TimeStampedModel):
    """Ítem reutilizable para armar cotizaciones rápido."""

    codigo = models.CharField(max_length=50, blank=True)
    nombre = models.CharField(max_length=200)
    descripcion = models.TextField(blank=True)
    precio_neto = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    exento = models.BooleanField(
        default=False, help_text="Marcar si el ítem no está afecto a IVA."
    )
    activo = models.BooleanField(default=True)
    imagen = models.ImageField("Foto", upload_to="productos/", blank=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["nombre"]

    def __str__(self) -> str:
        return self.nombre

    # Las fotos se guardan optimizadas: máximo 800 px por lado, en JPEG.
    LADO_MAXIMO = 800

    def save(self, *args, **kwargs):
        if self.imagen and not getattr(self.imagen, "_committed", True):
            self._optimizar_imagen()
        super().save(*args, **kwargs)

    def _optimizar_imagen(self):
        from PIL import Image, ImageOps

        with Image.open(self.imagen) as original:
            img = ImageOps.exif_transpose(original)
            img.thumbnail((self.LADO_MAXIMO, self.LADO_MAXIMO))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                fondo = Image.new("RGB", img.size, (255, 255, 255))
                fondo.paste(img, mask=img.split()[-1])
                img = fondo
            else:
                img = img.convert("RGB")
            salida = BytesIO()
            img.save(salida, "JPEG", quality=85, optimize=True)
        nombre = Path(self.imagen.name).stem + ".jpg"
        self.imagen = ContentFile(salida.getvalue(), name=nombre)
