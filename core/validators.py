"""Validadores de formularios y modelos."""
from django.core.exceptions import ValidationError

from .rut import RutInvalidoError, es_valido


def validar_rut(valor: str) -> None:
    if not es_valido(valor):
        raise ValidationError("El RUT ingresado no es válido.")
