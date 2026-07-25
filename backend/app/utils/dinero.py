"""
Utilidades para aritmética de dinero exacta.

O3.2 (Auditoría Día 42). Las columnas de monto en la base son Numeric(10,2),
así que SQLAlchemy las entrega como Decimal. Pero mucho código las convertía
a float (float(p.monto)) para sumarlas, y float redondea mal: el error se
acumula al sumar muchos registros en los reportes.

La regla es simple:
  - HACER LA ARITMÉTICA CON Decimal (exacta).
  - Convertir a float SOLO al serializar a JSON (json no tiene Decimal).

Estas funciones encapsulan ese patrón para no repetirlo ni equivocarse.
"""
from decimal import Decimal, ROUND_HALF_UP

# Dos decimales, redondeo bancario estándar (medio hacia arriba).
_CENTAVO = Decimal("0.01")

# Cero como Decimal, para inicializar acumuladores.
CERO = Decimal("0.00")


def a_decimal(valor) -> Decimal:
    """Convierte cualquier monto a Decimal de forma segura.

    Acepta Decimal (lo devuelve tal cual), int, y str. Para float pasa por
    str primero, porque Decimal(0.1) arrastra el error binario del float
    mientras que Decimal('0.1') es exacto. None se trata como cero.
    """
    if valor is None:
        return CERO
    if isinstance(valor, Decimal):
        return valor
    if isinstance(valor, float):
        return Decimal(str(valor))
    return Decimal(valor)


def redondear(valor) -> Decimal:
    """Redondea un Decimal (o convertible) a 2 decimales, medio hacia arriba."""
    return a_decimal(valor).quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def suma(iterable) -> Decimal:
    """Suma exacta de montos. Cada elemento se pasa por a_decimal().

    Reemplaza a sum(float(x) for x in ...). El resultado es Decimal exacto,
    listo para redondear() al serializar.
    """
    total = CERO
    for x in iterable:
        total += a_decimal(x)
    return total


def a_float(valor) -> float:
    """Convierte a float SOLO para serializar a JSON. Redondea antes para no
    arrastrar decimales largos al frontend."""
    return float(redondear(valor))
