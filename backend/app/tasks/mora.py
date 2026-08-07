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
        # Día 51 — niveles de plan: si la residencial de esta cuenta tiene
        # un plan que no incluye cuotas, no se manda el aviso. En rigor no
        # debería ni haber cuotas generadas para residenciales así, pero
        # este chequeo cubre el caso de una residencial que tenía cuotas
        # y bajó de plan después.
        #
        # Cuenta.unidad_id es solo una columna FK, sin relación ORM
        # definida en el modelo -- se consulta Unidad directo en vez de
        # asumir un cuenta.unidad que no existe.
        from app.utils.residencial import plan_permite
        from app.models.cuenta import Unidad
        unidad = Unidad.query.get(cuenta.unidad_id)
        if unidad and not plan_permite(unidad.residencial_id, "cuotas"):
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
            # Encolado (async) en vez de enviar directo -- así cada aviso se
            # reparte como una tarea separada entre los 12 procesos del
            # worker, en paralelo, en vez de mandarse uno por uno en fila
            # dentro de esta misma tarea (que es lo que causaba el atraso
            # real que notó el usuario en las pruebas de hoy).
            _notif.notificar_cuenta_async(
                cuenta.id, titulo, cuerpo,
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
    El día de pago y los días de gracia vienen de ConfigResidencial,
    UNA POR RESIDENCIAL (Día 54 — antes era una sola config global,
    aplicada por igual a las cuentas de TODAS las residenciales del
    sistema, sin importar lo que cada una hubiera configurado). La
    fecha de vencimiento es dia_pago + dias_gracia (ej. si pago es el 1
    y gracia es 7, la cuota vence el 7 del mes).
    """
    import calendar
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuenta, Cuota, ConfigResidencial, Unidad

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        periodo = dt.date(hoy.year, hoy.month, 1)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]

        cuentas = Cuenta.query.filter_by(activa=True).all()
        ya_tienen = {row[0] for row in db.session.query(Cuota.cuenta_id)
                     .filter(Cuota.periodo == periodo).all()}
        creadas = 0

        # Día 54: residencial_id de cada cuenta, precargado en una sola
        # consulta (Cuenta no tiene relación ORM a Unidad, solo la FK) --
        # y una config por residencial, resuelta bajo demanda y cacheada
        # en este diccionario para no repetir la consulta por cada cuenta.
        unidad_a_residencial = {u.id: u.residencial_id for u in Unidad.query.all()}
        configs_por_residencial = {}

        def _config_de(cuenta):
            rid = unidad_a_residencial.get(cuenta.unidad_id)
            if rid not in configs_por_residencial:
                configs_por_residencial[rid] = ConfigResidencial.get(rid)
            return configs_por_residencial[rid]

        for cuenta in cuentas:
            if cuenta.id in ya_tienen:
                continue
            if not cuenta.tarifa:
                continue

            cfg = _config_de(cuenta)
            # Fecha de vencimiento = día de pago + días de gracia.
            # Día 55: la cuenta puede tener su propio dias_gracia (override
            # individual); si es NULL, usa el global de la residencial.
            dia_pago = min(cfg.dia_pago, ultimo_dia)
            fecha_pago = dt.date(hoy.year, hoy.month, dia_pago)
            gracia = cuenta.dias_gracia if cuenta.dias_gracia is not None else cfg.dias_gracia
            vencimiento = fecha_pago + dt.timedelta(days=gracia)

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

        # Día 54 — bug real: antes se usaba UNA sola ConfigResidencial
        # global para decidir los días de gracia de TODAS las cuentas del
        # sistema, sin importar su residencial. Ahora se resuelve por
        # residencial, cacheada para no repetir la consulta por cuenta.
        from app.models.cuenta import ConfigResidencial
        configs_por_residencial = {}

        def _dias_gracia_de(residencial_id):
            if residencial_id not in configs_por_residencial:
                configs_por_residencial[residencial_id] = ConfigResidencial.get(residencial_id)
            return configs_por_residencial[residencial_id].dias_gracia

        for cuota in cuotas:
            dias = (hoy - cuota.fecha_vencimiento).days
            cuenta = cuota.cuenta
            if not cuenta:
                continue

            # Día 51 — niveles de plan: si la residencial de esta cuenta
            # tiene un plan que no incluye cuotas, no se bloquea la cuenta
            # ni se manda ningún aviso de mora. Es el corazón del pedido
            # del usuario: un plan Básico no debe tener el control
            # automático de accesos por pago corriendo en absoluto.
            from app.utils.residencial import plan_permite
            from app.models.cuenta import Unidad
            unidad = Unidad.query.get(cuenta.unidad_id)
            if unidad and not plan_permite(unidad.residencial_id, "cuotas"):
                continue

            # Día 55: respeta el override de días de gracia por casa
            # (cuenta.dias_gracia); si es NULL, usa el global de la
            # residencial. Mismo criterio que la generación de cuotas.
            # (Nota: el conteo de mora acá sobre fecha_vencimiento es un
            # comportamiento preexistente que no se toca en este cambio;
            # solo se sustituye de dónde sale el número de días de gracia.)
            dias_gracia = (cuenta.dias_gracia if cuenta.dias_gracia is not None
                           else _dias_gracia_de(unidad.residencial_id if unidad else None))

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
                _notif.notificar_cuenta_async(
                    cuenta.id,
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
        from app.services import notificaciones as _notif
        for info in avisos_mora.values():
            cuenta = info["cuenta"]
            dias = info["dias"]
            monto_txt = f"L {info['monto']:,.2f}"
            titulo, cuerpo = _mensaje_mora(dias, monto_txt)
            try:
                # Encolado (async): cada aviso se reparte como tarea propia
                # entre los procesos del worker, en paralelo -- antes se
                # mandaba uno por uno en fila dentro de este mismo ciclo,
                # lo que causaba que las últimas cuentas de la lista
                # recibieran su aviso varios minutos después que las
                # primeras (encontrado el Día 50, en pruebas reales).
                _notif.notificar_cuenta_async(
                    cuenta.id, titulo, cuerpo,
                    {"tipo": "mora_diaria", "dias": str(dias)},
                )
                avisados += 1
            except Exception:
                # Un fallo en UNA cuenta ya no corta el resto del ciclo --
                # antes el try/except envolvía todo el for, así que una
                # sola falla dejaba sin avisar a todas las cuentas
                # restantes de la lista, en silencio.
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
        pases_a_notificar = []
        ahora = dt.datetime.utcnow()
        # ROTATION-07: el código anterior vale 10 minutos EXACTOS desde este
        # instante (no "hasta que sean las 00:10 UTC" — eso fue el bug).
        valido_hasta = ahora + dt.timedelta(minutes=10)
        for tv in tarjetas:
            tv.codigo_anterior = tv.codigo_hoy
            tv.codigo_anterior_valido_hasta = valido_hasta
            while True:
                nuevo = "SV" + str(secrets.randbelow(10**10)).zfill(10)
                if not TarjetaVirtual.query.filter_by(codigo_hoy=nuevo).first():
                    break
            tv.codigo_hoy = nuevo
            tv.rotado_en = ahora
            # ROTATION-07: se necesita el código NUEVO acá, no solo el uuid —
            # la tarea de Wallet tiene que poder mandarlo en el PATCH.
            pases_a_notificar.append({"uuid": str(tv.uuid_publico), "codigo": nuevo})
            total += 1
        db.session.commit()

        # Notificar a Google Wallet (si está configurado)
        _notificar_wallet_actualizacion.delay(pases_a_notificar)

        # Rotar también los tokens BLE
        _rotar_credenciales_ble()

        return f"Rotadas {total} tarjetas virtuales"


def _rotar_credenciales_ble():
    """Rota los tokens BLE a medianoche, igual que las tarjetas virtuales.
    El token anterior queda válido 10 min exactos desde la rotación
    (ROTATION-07: fecha explícita, no una comparación de hora del servidor)."""
    from app.models.cuenta import CredencialBLE
    import secrets

    ahora = dt.datetime.utcnow()
    valido_hasta = ahora + dt.timedelta(minutes=10)
    creds = CredencialBLE.query.filter_by(estado="activa").all()
    for c in creds:
        c.token_anterior = c.token_hoy
        c.token_anterior_valido_hasta = valido_hasta
        while True:
            nuevo = "BLE" + secrets.token_hex(8).upper()
            if not CredencialBLE.query.filter_by(token_hoy=nuevo).first():
                break
        c.token_hoy = nuevo
        c.rotado_en = ahora
    db.session.commit()


@celery.task(name="tasks.notificar_wallet_actualizacion")
def _notificar_wallet_actualizacion(pases: list):
    """
    Empuja el QR nuevo a cada pase de Google Wallet ya emitido, vía PATCH
    directo a la Wallet REST API — este es el mecanismo real de
    actualización de pases genéricos (no un callback que Google inicia;
    ver la nota en tarjeta_virtual.py sobre el endpoint que existía antes
    y se eliminó por no cumplir ninguna función real).

    ROTATION-07 (Auditoría Día 35) — tres bugs corregidos acá:
      1. object_id: antes se armaba con un formato DISTINTO al que se usa
         al crear el pase (tarjeta_virtual.py) — la tarea nunca encontraba
         el objeto real. Ahora usa la misma función centralizada
         (app.services.wallet.wallet_object_id) en ambos lugares.
      2. El PATCH solo mandaba {"state": "ACTIVE"} — nunca tocaba el
         código QR real (barcode.value). Ahora manda el codigo_hoy nuevo
         de cada tarjeta, que es lo único que de verdad hace falta
         actualizar.
      3. Un 404 se contaba como "actualizado" — en realidad significa que
         ese residente nunca agregó el pase a su Wallet (normal, no todos
         lo usan) o que el pase no existe. Ahora se reporta aparte, sin
         inflar el conteo de éxitos.

    'pases' es una lista de {"uuid": str, "codigo": str} — el código NUEVO
    que le corresponde a cada tarjeta después de rotar.

    Si no está configurado Google Cloud, simplemente no hace nada.
    """
    from app import create_app
    from app.services.wallet import wallet_object_id
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

            creds = google.oauth2.service_account.Credentials.from_service_account_info(
                json.loads(service_key),
                scopes=["https://www.googleapis.com/auth/wallet_object.issuer"])
            session = google.auth.transport.requests.AuthorizedSession(creds)

            actualizados = 0
            sin_pase = 0     # 404 — el residente nunca agregó este pase a su Wallet (normal)
            errores = 0      # cualquier otra respuesta — esto sí es un problema real a revisar

            for p in pases:
                object_id = wallet_object_id(issuer_id, p["uuid"])
                url = f"https://walletobjects.googleapis.com/walletobjects/v1/genericObject/{object_id}"
                resp = session.patch(url, json={
                    "barcode": {"type": "QR_CODE", "value": p["codigo"]},
                })
                if resp.status_code == 200:
                    actualizados += 1
                elif resp.status_code == 404:
                    sin_pase += 1
                else:
                    errores += 1

            return (f"Wallet: {actualizados} actualizados, {sin_pase} sin pase en Wallet, "
                    f"{errores} con error (de {len(pases)} totales)")
        except Exception as e:
            return f"Error notificando Wallet: {e}"


@celery.task(name="tasks.expirar_visitas_vencidas")
def expirar_visitas_vencidas():
    """
    Marca como 'expirada' cualquier visita activa cuyo valido_hasta ya pasó
    y nadie la usó. Antes esto era perezoso: solo se marcaba si alguien
    intentaba validar el QR después de vencido — si nadie lo intentaba, la
    visita seguía apareciendo como 'activa' para siempre en la lista del
    residente, aunque ya no sirviera para nada (encontrado en pruebas del
    Día 36, reportado por el usuario).

    Corre cada hora. No toca visitas 'usada', 'revocada' ni las que ya
    están adentro (esas se resuelven por su propio flujo de salida).
    """
    from app import create_app
    from app.extensions import db
    from app.models.visita import Visita, EventoAcceso
    import datetime as dt

    app = create_app()
    with app.app_context():
        ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

        candidatas = (Visita.query
                      .filter(Visita.estado == "activa")
                      .filter(Visita.valido_hasta.isnot(None))
                      .filter(Visita.valido_hasta < ahora)
                      .all())

        total = 0
        for visita in candidatas:
            # No expirar si está actualmente adentro — que termine su salida primero
            ultimo = (EventoAcceso.query.filter_by(visita_id=visita.id)
                      .order_by(EventoAcceso.ocurrido_en.desc()).first())
            si_adentro = bool(ultimo and ultimo.direccion == "entrada")
            if si_adentro:
                continue

            visita.estado = "expirada"
            if visita.qr:
                visita.qr.revocado = True
            total += 1

        db.session.commit()
        return f"Expiradas {total} visitas vencidas"
