"""
Utilidades de cuotas — lógica compartida de prorrateo.

Día 55 — Sprint 2b: la generación de la primera cuota prorrateada existía
solo dentro de crear_cuenta (alta de una casa a mitad de mes). El wizard
de "activar cuotas al subir de plan" necesita exactamente el mismo cálculo
para todas las casas de golpe, así que se extrae acá para no duplicarlo.
"""
import calendar
import datetime as dt


def calcular_cuota_prorrateada(monto_tarifa, dia_pago, dias_gracia, hoy=None):
    """
    Calcula la primera cuota prorrateada de una casa que empieza a pagar a
    mitad de mes (alta nueva, o activación de cuotas al subir de plan).

    Regla (Opción A, confirmada con el usuario): se cobra proporcionalmente
    desde HOY hasta el fin del ciclo actual, usando SIEMPRE mes comercial de
    30 días — así en meses de 31 días no se cobra de más. El primer cobro
    completo del ciclo normal lo hace después el cron mensual.

    Devuelve un dict con periodo, monto, fecha_vencimiento y dias_restantes,
    o None si no corresponde generar cuota (ej. hoy es el día de pago o
    antes — el ciclo normal ya la cubre, no hay fracción que prorratear).

    - monto_tarifa: monto mensual completo de la tarifa.
    - dia_pago: día del mes en que se cobra (1..28).
    - dias_gracia: días después del pago antes de que venza.
    - hoy: fecha de referencia (default: hoy real). Parametrizable para test.
    """
    if hoy is None:
        hoy = dt.date.today()

    # Si todavía no pasó el día de pago de este mes, el ciclo normal cubre
    # el período completo — no hay fracción que prorratear.
    if hoy.day <= dia_pago:
        return None

    # Mes comercial de 30 días, también para contar los días restantes.
    efectivo_dia = min(hoy.day, 30)
    posicion_en_ciclo = ((efectivo_dia - dia_pago) % 30) + 1  # 1..30
    dias_restantes = 30 - posicion_en_ciclo

    if dias_restantes <= 0:
        return None

    monto_diario = float(monto_tarifa) / 30
    monto_prorrateado = round(monto_diario * dias_restantes, 2)

    # El vencimiento se ancla al PRÓXIMO día de pago + gracia (el ciclo que
    # esta cuota parcial cubre termina en el próximo día de pago).
    if hoy.month == 12:
        prox_pago = dt.date(hoy.year + 1, 1, dia_pago)
    else:
        ultimo_dia_prox = calendar.monthrange(hoy.year, hoy.month + 1)[1]
        prox_pago = dt.date(hoy.year, hoy.month + 1, min(dia_pago, ultimo_dia_prox))

    periodo = dt.date(hoy.year, hoy.month, 1)
    vencimiento = prox_pago + dt.timedelta(days=dias_gracia)

    return {
        "periodo": periodo,
        "monto": monto_prorrateado,
        "fecha_vencimiento": vencimiento,
        "dias_restantes": dias_restantes,
    }
