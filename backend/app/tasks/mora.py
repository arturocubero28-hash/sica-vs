"""
Tareas Celery para SICA-VS:
  - generar_cuotas_mensuales: corre el 1ro de cada mes a las 00:05
  - revisar_mora: corre cada noche a la 01:00
La programación (beat_schedule) está centralizada en celery_app.py
"""
import datetime as dt
from app.tasks.celery_app import celery


@celery.task(name="tasks.avisar_cuotas_por_vencer")
def avisar_cuotas_por_vencer():
    """Envía un aviso preventivo por notificación push a los residentes cuya
    cuota vence pronto. Se avisa en dos momentos:
      - 3 días antes del vencimiento
      - el mismo día del vencimiento

    Corre una vez al día. Como filtra por fecha exacta (vence en exactamente
    3 días, o vence hoy), cada cuota recibe como máximo un aviso por momento.
    """
    from app.models.cuenta import Cuota
    from app.services import notificaciones as _notif
    from flask import has_app_context
    from app import create_app

    # Si ya hay contexto (llamada desde un endpoint), usarlo; si no (Celery), crear
    if has_app_context():
        return _avisar_cuotas_logica(Cuota, _notif)
    app = create_app()
    with app.app_context():
        return _avisar_cuotas_logica(Cuota, _notif)


def _avisar_cuotas_logica(Cuota, _notif):
    hoy = dt.date.today()
    en_3_dias = hoy + dt.timedelta(days=3)

    cuotas = Cuota.query.filter(
        Cuota.estado.in_(["pendiente", "vencida"]),
        Cuota.fecha_vencimiento.in_([hoy, en_3_dias]),
    ).all()

    avisadas = 0
    for cuota in cuotas:
        cuenta = cuota.cuenta
        if not cuenta:
            continue
        dias = (cuota.fecha_vencimiento - hoy).days
        monto_txt = f"L {float(cuota.monto):,.2f}"

        if dias == 3:
            titulo = "Tu cuota vence pronto"
            cuerpo = (f"La cuota de {monto_txt} vence en 3 días. "
                      f"Pagá a tiempo para evitar el bloqueo por mora.")
        else:  # dias == 0
            titulo = "Tu cuota vence hoy"
            cuerpo = (f"Hoy vence la cuota de {monto_txt}. "
                      f"Realizá tu pago para mantener tu cuenta al día.")

        try:
            _notif.notificar_cuenta(
                cuenta, titulo, cuerpo,
                {"tipo": "cuota_por_vencer", "dias": str(dias)},
            )
            avisadas += 1
        except Exception:
            pass

    return {"avisadas": avisadas}


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
        # Trae de una sola vez los cuenta_id que ya tienen cuota este periodo
        # (evita una query de existencia por cada cuenta — N+1).
        ya_tienen = {row[0] for row in db.session.query(Cuota.cuenta_id)
                     .filter(Cuota.periodo == periodo).all()}
        creadas = 0

        for cuenta in cuentas:
            if cuenta.id in ya_tienen:
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
def _mensaje_mora(dias, monto_txt):
    """Genera el aviso de mora que escala de tono según los días de atraso.
    Devuelve (titulo, cuerpo)."""
    if dias == 1:
        return ("Cuota vencida",
                f"Tu cuota de {monto_txt} venció ayer. Ponete al día para "
                f"evitar el bloqueo de tu cuenta.")
    elif dias == 2:
        return ("2 días de atraso",
                f"Llevás 2 días de atraso con {monto_txt}. Mañana tu cuenta "
                f"será bloqueada si no pagás.")
    elif dias < 7:
        return (f"Cuenta bloqueada · {dias} días de mora",
                f"Tu cuenta está bloqueada por {monto_txt} en mora ({dias} días). "
                f"Regularizá tu pago para recuperar el acceso.")
    elif dias < 15:
        return (f"{dias} días de mora acumulada",
                f"Ya son {dias} días de atraso ({monto_txt}). Acercate a "
                f"administración para regularizar tu situación.")
    else:
        return (f"Mora crítica · {dias} días",
                f"Tu cuenta lleva {dias} días de mora ({monto_txt}). "
                f"Contactá a administración a la brevedad.")


@celery.task(name="tasks.revisar_mora")
def revisar_mora():
    """
    Revisa cuotas pendientes/vencidas y aplica la lógica de mora acordada:
      -1 día  → notificación (futuro: email)
       0 días → notificación
      +1, +2  → notificación de atraso
      +3 o +  → bloquear cuenta (estado='bloqueada', bloqueada=True)
    El desbloqueo ocurre cuando el admin aprueba un pago, no aquí.
    Además envía un aviso de mora escalonado día a día (ver _mensaje_mora).
    """
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuota

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        bloqueadas = 0
        procesadas = 0
        cuentas_bloqueadas = []  # para notificar al final
        avisos_mora = {}         # cuenta_id -> {cuenta, dias, monto}

        cuotas = Cuota.query.filter(
            Cuota.estado.in_(["pendiente", "vencida"]),
            Cuota.fecha_vencimiento <= hoy,
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
                    cuentas_bloqueadas.append(cuenta)
            elif dias >= 0:
                cuota.estado = "vencida"

            # Aviso de mora ESCALONADO día a día (independiente del bloqueo).
            # Se acumula por cuenta para no mandar un push por cada cuota.
            if dias >= 1:
                avisos_mora.setdefault(cuenta.id, {
                    "cuenta": cuenta, "dias": dias, "monto": 0.0
                })
                # Guardar el mayor atraso y sumar el monto adeudado
                if dias > avisos_mora[cuenta.id]["dias"]:
                    avisos_mora[cuenta.id]["dias"] = dias
                avisos_mora[cuenta.id]["monto"] += float(cuota.monto)

            procesadas += 1

        db.session.commit()

        # Notificar a las cuentas recién bloqueadas por mora
        try:
            from app.services import notificaciones as _notif
            for cuenta in cuentas_bloqueadas:
                _notif.notificar_cuenta(
                    cuenta,
                    "Cuenta bloqueada por mora",
                    "Tu cuenta fue bloqueada por cuotas vencidas. "
                    "Regularizá tu pago para recuperar el acceso.",
                    {"tipo": "cuenta_bloqueada"},
                )
        except Exception:
            pass

        # Aviso de mora ESCALONADO: sube de tono según los días de atraso.
        # Corre cada noche, así que el residente recibe un recordatorio diario
        # que va escalando mientras no pague.
        avisados = 0
        try:
            from app.services import notificaciones as _notif
            for info in avisos_mora.values():
                cuenta = info["cuenta"]
                dias = info["dias"]
                monto_txt = f"L {info['monto']:,.2f}"
                titulo, cuerpo = _mensaje_mora(dias, monto_txt)
                _notif.notificar_cuenta(
                    cuenta, titulo, cuerpo,
                    {"tipo": "mora_diaria", "dias": str(dias)},
                )
                avisados += 1
        except Exception:
            pass

        return {"procesadas": procesadas, "cuentas_bloqueadas": bloqueadas,
                "avisos_mora": avisados}


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
    from app.models.sesion_activa import SesionActiva

    app = create_app()
    with app.app_context():
        ahora = dt.datetime.now(dt.timezone.utc)
        borrados = TokenRevocado.query.filter(TokenRevocado.expira_en < ahora).delete()
        sesiones = SesionActiva.query.filter(SesionActiva.expira_en < ahora).delete()
        db.session.commit()
        return {"tokens_eliminados": borrados, "sesiones_eliminadas": sesiones}
