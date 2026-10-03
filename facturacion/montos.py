"""Cálculo de montos según las reglas del SII.

El SII redondea al entero más cercano y las mitades hacia arriba
(0,5 -> 1). Python por defecto redondea "al par" (2,5 -> 2), lo que
genera diferencias de $1 que el SII rechaza. Todo monto de un DTE debe
pasar por `redondear`.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from facturacion.constants import TASA_IVA


def redondear(valor) -> Decimal:
    return Decimal(valor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Totales:
    neto: Decimal
    exento: Decimal
    iva: Decimal
    total: Decimal


def calcular_totales(lineas: Iterable) -> Totales:
    """Totales a partir de líneas con atributos `monto` y `exento`.

    El IVA se calcula sobre el neto total (no línea a línea), igual que
    lo valida el SII: IVA = redondear(MntNeto * 0,19).
    """
    neto = Decimal("0")
    exento = Decimal("0")
    for linea in lineas:
        if linea.exento:
            exento += linea.monto
        else:
            neto += linea.monto
    iva = redondear(neto * TASA_IVA)
    return Totales(neto=neto, exento=exento, iva=iva, total=neto + iva + exento)
