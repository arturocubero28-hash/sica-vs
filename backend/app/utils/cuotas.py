"""
Utilidades de cuotas — lógica compartida de prorrateo.

Día 55 — Sprint 2b: la generación de la primera cuota prorrateada existía
solo dentro de crear_cuenta (alta de una casa a mitad de mes). El wizard
de "activar cuotas al subir de plan" necesita exactamente el mismo cálculo
para todas las casas de golpe, así que se extrae acá para no duplicarlo.
"""
import calendar
import datetime as dt


def calcular_cuota_prorrateada(monto_tarifa, dia_pago, hoy=None):
    """
    Calcula la primera cuota prorrateada de una casa que empieza a pagar a
    mitad de mes (alta nueva, o activación de cuotas al subir de plan).

    MODELO DE COBRO (Día 62 — corregido; ver también generar_cuotas_mensuales
    en tasks/mora.py, que sigue exactamente el mismo criterio):

      - El MONTO se prorratea por los días que quedan del mes ACTUAL, desde
        hoy hasta fin de mes (mes comercial de 30 días). Ej: alta el 16 ->
        se cobran 15 días de agosto.
      - El VENCIMIENTO cae en el MES SIGUIENTE, en el día de pago
        configurado -- igual que cualquier otra cuota. El residente paga un
        mes ya consumido.

    Esto corrige un problema real encontrado en producción (Día 62): antes
    el vencimiento se calculaba en el MISMO mes del alta, así que si el día
    de pago ya había pasado (ej. alta el 16, día de pago el 7), la cuenta
    NACÍA EN MORA -- el residente quedaba en atraso por una fecha que ya
    había pasado antes de que su cuenta existiera, sin ninguna posibilidad
    real de pagar a tiempo.

    IMPORTANTE: fecha_vencimiento guarda SOLO el día de pago (cuándo empieza
    la mora), NO el día del corte de servicio. El corte se calcula donde se
    necesita (revisar_mora en tasks/mora.py), sumando los días de gracia a
    esta fecha. Por eso esta función ya NO recibe dias_gracia: dejó de
    usarlo al cambiar el modelo, y se quitó para no dejar un parámetro
    muerto que confundiera a quien lea el código más adelante.

    Regla de negocio (Opción A, confirmada el Día 55): la responsabilidad
    arranca hoy, cada casa empieza limpia, sin mirar historial previo.

    Devuelve dict con periodo, monto, fecha_vencimiento, dias_restantes;
    o None si no corresponde (hoy es día 30/fin de mes comercial, no queda
    fracción). Recibe 'hoy' parametrizable para test.
    """
    if hoy is None:
        hoy = dt.date.today()

    # Días que quedan del mes ACTUAL, en mes comercial de 30 días. El día de
    # la propia alta NO se cobra -- se cobra desde el día SIGUIENTE hasta
    # fin de mes. Ej: alta el 17 -> se cobran del 18 al 30 = 13 días.
    # (Día 62, corregido: antes incluía el día de hoy, cobrando un día de
    # más -- el usuario confirmó en producción que el día de alta debe
    # quedar libre.)
    efectivo_dia = min(hoy.day, 30)
    dias_restantes = 30 - efectivo_dia

    if dias_restantes <= 0:
        return None

    monto_diario = float(monto_tarifa) / 30
    monto_prorrateado = round(monto_diario * dias_restantes, 2)

    # Vencimiento: día de pago DEL MES SIGUIENTE (mismo criterio que el
    # cron mensual). min() por si el mes siguiente no llega a ese día
    # (ej. día 30 configurado y el mes siguiente es febrero).
    if hoy.month == 12:
        anio_venc, mes_venc = hoy.year + 1, 1
    else:
        anio_venc, mes_venc = hoy.year, hoy.month + 1
    ultimo_dia_venc = calendar.monthrange(anio_venc, mes_venc)[1]
    dia_venc = min(dia_pago, ultimo_dia_venc)
    vencimiento = dt.date(anio_venc, mes_venc, dia_venc)

    periodo = dt.date(hoy.year, hoy.month, 1)

    return {
        "periodo": periodo,
        "monto": monto_prorrateado,
        "fecha_vencimiento": vencimiento,
        "dias_restantes": dias_restantes,
    }
