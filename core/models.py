"""Modelos base reutilizables por el resto de las apps."""
from django.db import models


class TimeStampedModel(models.Model):
    """Agrega marcas de creación y actualización a cualquier modelo."""

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
