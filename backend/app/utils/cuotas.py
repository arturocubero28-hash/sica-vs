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

    Modelo real del sistema (aclarado por el usuario el Día 55): el cron
    mensual corre el DÍA 1 de cada mes y genera la cuota de ESE mes, con
    período = 1° del mes y vencimiento = día de pago DE ESE MISMO MES +
    gracia. El "día de pago" es solo la fecha de vencimiento dentro del
    mes, NO cuándo empieza el ciclo.

    Por lo tanto, la primera cuota (activación a mitad de mes) se prorratea
    por los días que quedan DESDE HOY HASTA FIN DE MES (mes comercial de 30
    días), con período = mes actual y vencimiento = día de pago de este
    mismo mes + gracia. El 1° del mes siguiente, el cron ya genera la cuota
    completa normal.

    Regla de negocio (Opción A, confirmada): la responsabilidad arranca
    hoy, cada casa empieza limpia, sin mirar historial previo.

    Devuelve dict con periodo, monto, fecha_vencimiento, dias_restantes;
    o None si no corresponde (hoy es día 30/fin de mes comercial, no queda
    fracción). Recibe 'hoy' parametrizable para test.
    """
    if hoy is None:
        hoy = dt.date.today()

    # Días que quedan del mes, en mes comercial de 30 días. Ej: hoy es el 7
    # -> se cobran del 7 al 30 = 24 días (incluyendo hoy). Así el residente
    # paga desde el día que entra al sistema hasta fin de mes.
    efectivo_dia = min(hoy.day, 30)
    dias_restantes = 30 - efectivo_dia + 1  # incluye el día de hoy

    if dias_restantes <= 0:
        return None

    monto_diario = float(monto_tarifa) / 30
    monto_prorrateado = round(monto_diario * dias_restantes, 2)

    # Vencimiento: día de pago de ESTE MISMO MES + gracia (igual que el cron
    # mensual). Si el día de pago ya pasó este mes (ej. hoy 15, pago 11), la
    # cuota vence igual el 11 + gracia -- ya "nace vencida" en su ventana de
    # gracia, lo cual es correcto: el residente entró tarde y debe ponerse
    # al día. min() por si el mes no llega a ese día (febrero, etc.).
    ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
    dia_venc = min(dia_pago, ultimo_dia)
    fecha_pago = dt.date(hoy.year, hoy.month, dia_venc)
    vencimiento = fecha_pago + dt.timedelta(days=dias_gracia)

    periodo = dt.date(hoy.year, hoy.month, 1)

    return {
        "periodo": periodo,
        "monto": monto_prorrateado,
        "fecha_vencimiento": vencimiento,
        "dias_restantes": dias_restantes,
    }
