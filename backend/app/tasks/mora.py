"""
Tareas Celery para SICA-VS:
  - generar_cuotas_mensuales: corre el 1ro de cada mes a las 00:05
  - revisar_mora: corre cada noche a la 01:00
La programación (beat_schedule) está centralizada en celery_app.py
"""
import datetime as dt
from app.tasks.celery_app import celery


# ── Generación automática de cuotas ───────────────────────────────────────────
@celery.task(name="tasks.generar_cuotas_mensuales")
def generar_cuotas_mensuales():
    """
    Genera una cuota por cada cuenta para el mes en curso.
    Usa UNIQUE (cuenta_id, periodo) para evitar duplicados.
    El vencimiento respeta el dia_pago configurado en cada cuenta.
    """
    import calendar
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuenta, Cuota

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        periodo = dt.date(hoy.year, hoy.month, 1)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]

        cuentas = Cuenta.query.filter_by(activa=True).all()
        creadas = 0

        for cuenta in cuentas:
            existe = Cuota.query.filter_by(
                cuenta_id=cuenta.id, periodo=periodo
            ).first()
            if existe:
                continue
            if not cuenta.tarifa:
                continue

            # Vencimiento según el día de pago de la cuenta
            dia = min(cuenta.dia_pago or 15, ultimo_dia)
            vencimiento = dt.date(hoy.year, hoy.month, dia)

            cuota = Cuota(
                cuenta_id=cuenta.id,
                periodo=periodo,
                monto=float(cuenta.tarifa.monto),
                fecha_vencimiento=vencimiento,
                estado="pendiente",
            )
            db.session.add(cuota)
            creadas += 1

        db.session.commit()
        return {"generadas": creadas, "total_cuentas": len(cuentas)}


# ── Revisión diaria de mora ────────────────────────────────────────────────────
@celery.task(name="tasks.revisar_mora")
def revisar_mora():
    """
    Revisa cuotas pendientes/vencidas y aplica la lógica de mora acordada:
      -1 día  → notificación (futuro: email)
       0 días → notificación
      +1, +2  → notificación de atraso
      +3 o +  → bloquear cuenta (estado='bloqueada', bloqueada=True)
    El desbloqueo ocurre cuando el admin aprueba un pago, no aquí.
    """
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuota, Cuenta

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        bloqueadas = 0
        procesadas = 0

        cuotas = Cuota.query.filter(
            Cuota.estado.in_(["pendiente", "vencida"])
        ).all()

        for cuota in cuotas:
            dias = (hoy - cuota.fecha_vencimiento).days
            cuenta = cuota.cuenta

            if dias >= 3:
                cuota.estado = "vencida"
                if not cuenta.bloqueada:
                    cuenta.estado = "bloqueada"
                    cuenta.bloqueada = True
                    bloqueadas += 1
            elif dias >= 0:
                cuota.estado = "vencida"

            procesadas += 1

        db.session.commit()
        return {"procesadas": procesadas, "cuentas_bloqueadas": bloqueadas}


# ── Vigilancia de arreglos de pago ────────────────────────────────────────────
@celery.task(name="tasks.revisar_arreglos")
def revisar_arreglos():
    """
    Revisa los abonos de arreglos activos. Si un abono pendiente supera su
    fecha pactada + los días de gracia del arreglo, el arreglo se marca
    INCUMPLIDO: las cuotas se descongelan (vuelven a vencidas) y la cuenta
    se bloquea de nuevo. Lo ya abonado NO se pierde.
    """
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import ArregloPago
    from app.api.arreglos import _descongelar_y_bloquear

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        incumplidos = 0
        vencidos_marcados = 0

        arreglos = ArregloPago.query.filter_by(estado="activo").all()
        for arreglo in arreglos:
            incumplio = False
            for abono in arreglo.abonos:
                if abono.estado != "pendiente":
                    continue
                dias_atraso = (hoy - abono.fecha_pactada).days
                if dias_atraso > 0:
                    # Marcar el abono como vencido (visual)
                    if abono.estado != "vencido":
                        abono.estado = "vencido"
                        vencidos_marcados += 1
                # ¿Supera los días de gracia? → incumplimiento del arreglo
                if dias_atraso > arreglo.dias_gracia:
                    incumplio = True

            if incumplio:
                _descongelar_y_bloquear(
                    arreglo, "incumplido",
                    f"Incumplimiento: abono vencido más de {arreglo.dias_gracia} días de gracia"
                )
                incumplidos += 1

        db.session.commit()
        return {"arreglos_incumplidos": incumplidos, "abonos_vencidos": vencidos_marcados}


# ── Limpieza de tokens revocados expirados ────────────────────────────────────
@celery.task(name="tasks.limpiar_tokens_revocados")
def limpiar_tokens_revocados():
    """
    Elimina de la blacklist los tokens cuya fecha de expiración ya pasó.
    Una vez expirados, el JWT ya no es válido por sí mismo, así que no
    hace falta seguir guardándolos. Mantiene la tabla pequeña.
    """
    from app import create_app
    from app.extensions import db
    from app.models.token_revocado import TokenRevocado

    app = create_app()
    with app.app_context():
        ahora = dt.datetime.now(dt.timezone.utc)
        borrados = TokenRevocado.query.filter(TokenRevocado.expira_en < ahora).delete()
        db.session.commit()
        return {"tokens_eliminados": borrados}
