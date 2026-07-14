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
    El día de pago y los días de gracia vienen de ConfigResidencial
    (configuración global del admin). La fecha de vencimiento es
    dia_pago + dias_gracia (ej. si pago es el 1 y gracia es 7,
    la cuota vence el 7 del mes).
    """
    import calendar
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuenta, Cuota, ConfigResidencial

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        periodo = dt.date(hoy.year, hoy.month, 1)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]

        cfg = ConfigResidencial.get()

        cuentas = Cuenta.query.filter_by(activa=True).all()
        ya_tienen = {row[0] for row in db.session.query(Cuota.cuenta_id)
                     .filter(Cuota.periodo == periodo).all()}
        creadas = 0

        for cuenta in cuentas:
            if cuenta.id in ya_tienen:
                continue
            if not cuenta.tarifa:
                continue

            # Fecha de vencimiento = día de pago + días de gracia
            dia_pago = min(cfg.dia_pago, ultimo_dia)
            fecha_pago = dt.date(hoy.year, hoy.month, dia_pago)
            vencimiento = fecha_pago + dt.timedelta(days=cfg.dias_gracia)

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

        # Obtener los días de gracia configurados por la administración
        from app.models.cuenta import ConfigResidencial
        cfg = ConfigResidencial.get()
        dias_gracia = cfg.dias_gracia  # default 7

        for cuota in cuotas:
            dias = (hoy - cuota.fecha_vencimiento).days
            cuenta = cuota.cuenta

            if dias >= dias_gracia:
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


@celery.task(name="tasks.rotar_tarjetas_virtuales")
def rotar_tarjetas_virtuales():
    """
    Rotación diaria de los códigos QR permanentes (tarjetas virtuales).
    Corre a las 00:00 todos los días.

    Después de rotar, notifica a Google Wallet para que actualice los pases
    en segundo plano — el residente no necesita abrir la app.
    """
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import TarjetaVirtual
    import secrets, datetime as dt

    app = create_app()
    with app.app_context():
        tarjetas = TarjetaVirtual.query.filter_by(estado="activa").all()
        total = 0
        ids_actualizados = []
        for tv in tarjetas:
            tv.codigo_anterior = tv.codigo_hoy
            while True:
                nuevo = "SV" + str(secrets.randbelow(10**10)).zfill(10)
                if not TarjetaVirtual.query.filter_by(codigo_hoy=nuevo).first():
                    break
            tv.codigo_hoy = nuevo
            tv.rotado_en = dt.datetime.utcnow()
            ids_actualizados.append(str(tv.uuid_publico))
            total += 1
        db.session.commit()

        # Notificar a Google Wallet (si está configurado)
        _notificar_wallet_actualizacion.delay(ids_actualizados)

        return f"Rotadas {total} tarjetas virtuales"


@celery.task(name="tasks.notificar_wallet_actualizacion")
def _notificar_wallet_actualizacion(uuids: list):
    """
    Llama a la Google Wallet API para marcar cada pase como desactualizado.
    Google Wallet luego llama al callback del servidor para obtener el QR nuevo.
    Si no está configurado Google Cloud, simplemente no hace nada.
    """
    from app import create_app
    import json

    app = create_app()
    with app.app_context():
        service_key = app.config.get("GOOGLE_SERVICE_ACCOUNT_KEY")
        issuer_id = app.config.get("GOOGLE_ISSUER_ID")
        if not service_key or not issuer_id:
            return "Google Wallet no configurado — skip"

        try:
            import google.auth.crypt
            import google.auth.transport.requests
            import google.oauth2.service_account
            import requests as req

            creds = google.oauth2.service_account.Credentials.from_service_account_info(
                json.loads(service_key),
                scopes=["https://www.googleapis.com/auth/wallet_object.issuer"])
            session = google.auth.transport.requests.AuthorizedSession(creds)

            actualizados = 0
            for uuid_str in uuids:
                object_id = f"{issuer_id}.tv_{uuid_str}"
                url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericObject/{object_id}"
                # PATCH con expire_time = ahora → Google sabe que debe pedir el refresh
                resp = session.patch(url, json={"state": "ACTIVE"})
                if resp.status_code in (200, 404):
                    actualizados += 1

            return f"Wallet notificado: {actualizados}/{len(uuids)} pases"
        except Exception as e:
            return f"Error notificando Wallet: {e}"
