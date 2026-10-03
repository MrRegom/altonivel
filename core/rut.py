"""Utilidades para validar y formatear el RUT chileno.

El RUT (Rol Único Tributario) usa dígito verificador con módulo 11.
En los DTE del SII el RUT del emisor y receptor va SIN puntos y CON
guión, con la K en mayúscula, por ejemplo: 76192083-9.
"""
from __future__ import annotations

import re


class RutInvalidoError(ValueError):
    """Se lanza cuando un RUT no es válido."""


def _limpiar(rut: str) -> str:
    return re.sub(r"[^0-9kK]", "", rut or "").upper()


def calcular_dv(cuerpo: str) -> str:
    """Calcula el dígito verificador para el cuerpo numérico del RUT."""
    suma = 0
    multiplo = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def es_valido(rut: str) -> bool:
    limpio = _limpiar(rut)
    if len(limpio) < 2:
        return False
    cuerpo, dv = limpio[:-1], limpio[-1]
    if not cuerpo.isdigit():
        return False
    return calcular_dv(cuerpo) == dv


def normalizar(rut: str) -> str:
    """Devuelve el RUT en el formato que espera el SII: 76192083-9."""
    limpio = _limpiar(rut)
    if not es_valido(limpio):
        raise RutInvalidoError(f"RUT inválido: {rut!r}")
    return f"{limpio[:-1]}-{limpio[-1]}"


def formatear(rut: str) -> str:
    """Formato legible con puntos y guión: 76.192.083-9."""
    normal = normalizar(rut)
    cuerpo, dv = normal.split("-")
    cuerpo_con_puntos = f"{int(cuerpo):,}".replace(",", ".")
    return f"{cuerpo_con_puntos}-{dv}"
