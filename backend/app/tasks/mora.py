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
            # Día 62: antes decía "para evitar el bloqueo por mora", pero el
            # bloqueo NO ocurre al vencer -- ocurre recién al agotarse los
            # días de gracia posteriores. Se corrige el texto para no
            # asustar de más ni desinformar sobre cuándo se corta.
            cuerpo = (f"La cuota de {monto_txt} vence en 3 días. "
                      f"Pagá a tiempo para evitar entrar en mora.")
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

    MODELO DE COBRO (Día 62 — corregido y unificado; antes había una
    ambigüedad real que hacía que una cuenta pudiera "nacer en mora"):

      1 de agosto        → se genera la cuota de agosto (período = agosto).
      día_pago de SEPT.  → vence. Ese día se avisa "hoy es tu día de pago".
                           Hasta acá, sin mora.
      +1 día             → empieza la mora. Alertas diarias avisando
                           cuántos días faltan para el corte.
      +dias_gracia       → al vencerse los días exactos de gracia, se
                           corta el servicio (bloqueo de accesos).

    Es decir: el residente paga un mes YA CONSUMIDO, con vencimiento en el
    mes siguiente. El "día de pago" es un día DEL MES SIGUIENTE al período
    de la cuota (por defecto el 1; configurable por el admin).

    IMPORTANTE — significado de fecha_vencimiento: guarda SOLO el día de
    pago (cuándo empieza la mora), NO el día del corte. Antes de hoy este
    campo guardaba día_pago + dias_gracia mezclados en un solo valor, lo
    que hacía imposible distinguir "está en mora" de "hay que cortarle el
    servicio" -- y encima revisar_mora() sumaba OTROS 3 días fijos encima,
    una segunda gracia implícita que nadie había configurado. Ahora el
    corte se calcula donde se necesita, sumando los días de gracia reales
    a esta fecha.

    El día de pago y los días de gracia vienen de ConfigResidencial, UNA
    POR RESIDENCIAL (Día 54 — antes era una sola config global, aplicada
    por igual a las cuentas de TODAS las residenciales del sistema).
    """
    import calendar
    from app import create_app
    from app.extensions import db
    from app.models.cuenta import Cuenta, Cuota, ConfigResidencial, Unidad

    app = create_app()
    with app.app_context():
        hoy = dt.date.today()
        periodo = dt.date(hoy.year, hoy.month, 1)

        # Día 62 — el vencimiento cae en el MES SIGUIENTE al período.
        if hoy.month == 12:
            anio_venc, mes_venc = hoy.year + 1, 1
        else:
            anio_venc, mes_venc = hoy.year, hoy.month + 1
        ultimo_dia_venc = calendar.monthrange(anio_venc, mes_venc)[1]

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
            # Vencimiento = día de pago DEL MES SIGUIENTE. Sin sumar la
            # gracia acá: la gracia es lo que va DESPUÉS del vencimiento,
            # y se aplica en revisar_mora() para decidir el corte.
            # min() por si el mes siguiente no llega a ese día (ej. día 30
            # configurado y el mes siguiente es febrero).
            dia_pago = min(cfg.dia_pago, ultimo_dia_venc)
            vencimiento = dt.date(anio_venc, mes_venc, dia_pago)

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
def _mensaje_mora(dias, monto_txt, dias_gracia=None):
    """
    Genera el aviso de mora que escala de tono según los días de atraso.
    Devuelve (titulo, cuerpo).

    Día 62 — reescrito: los mensajes anteriores tenían hardcodeado el
    modelo viejo ("mañana tu cuenta será bloqueada" en el día 2, "cuenta
    bloqueada" desde el día 3), que asumía 3 días fijos de gracia sin
    importar lo que el admin hubiera configurado. Con 7 días de gracia,
    por ejemplo, el residente recibía "cuenta bloqueada" al 3er día
    aunque su cuenta siguiera perfectamente activa -- un aviso falso.

    Ahora los mensajes se arman con los días de gracia REALES de esa
    cuenta: mientras esté dentro de la gracia, se avisa cuántos días le
    quedan antes del corte; una vez superada, se avisa que el servicio
    está suspendido.
    """
    if dias_gracia is None:
        dias_gracia = 0

    # Dentro de la ventana de gracia: todavía tiene servicio.
    if dias <= dias_gracia:
        restantes = dias_gracia - dias + 1  # incluye hoy
        if restantes == 1:
            cuando = "hoy es tu último día"
        else:
            cuando = f"te quedan {restantes} días"
        titulo = "Cuota vencida" if dias == 1 else f"{dias} días de atraso"
        return (titulo,
                f"Tu cuota de {monto_txt} está vencida ({dias} "
                f"{'día' if dias == 1 else 'días'} de atraso). Para evitar la "
                f"suspensión de visitas y accesos, {cuando} para ponerte al día.")

    # Ya superó la gracia: servicio suspendido.
    if dias < 15:
        return (f"Servicio suspendido · {dias} días de mora",
                f"Tu acceso a la residencial y la generación de visitas están "
                f"suspendidos por {monto_txt} en mora ({dias} días). Regularizá "
                f"tu pago para recuperar el acceso.")
    return (f"Mora crítica · {dias} días",
            f"Tu cuenta lleva {dias} días de mora ({monto_txt}) con el servicio "
            f"suspendido. Contactá a administración a la brevedad.")


@celery.task(name="tasks.revisar_mora")
def revisar_mora():
    """
    Revisa cuotas vencidas y aplica el modelo de cobro (Día 62).

    Con día de pago el 5 de septiembre y 3 días de gracia configurados:

      5 de sept  (día 0)  → día de pago. Aviso "hoy vence tu cuota".
                            Todavía NO es mora.
      6 de sept  (día 1)  → 1er día de mora. Aviso de atraso, avisando
                            en cuántos días se suspende el servicio.
      7, 8       (2 y 3)  → sigue en mora, con servicio. Últimos días de
                            la gracia configurada.
      9 de sept  (día 4)  → se agotaron los 3 días completos de gracia
                            → SE CORTA el servicio (cuenta bloqueada).

    Es decir: el corte ocurre cuando los días de atraso SUPERAN los días
    de gracia (dias > dias_gracia), no cuando los igualan -- con 3 días de
    gracia, el residente los usa completos (días 1, 2 y 3) y recién al 4°
    se le corta. Antes esto era `dias >= dias_gracia`, que cortaba un día
    antes de tiempo, comiéndose el último día de gracia.

    fecha_vencimiento guarda SOLO el día de pago (ver
    generar_cuotas_mensuales), así que `dias` es directamente los días de
    mora reales, sin gracias implícitas mezcladas.

    El desbloqueo ocurre cuando el admin aprueba un pago, no acá.
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
            dias_gracia = (cuenta.dias_gracia if cuenta.dias_gracia is not None
                           else _dias_gracia_de(unidad.residencial_id if unidad else None))

            # Día 62 — corregido un error de un día: era `dias >=
            # dias_gracia`, que cortaba el servicio EN el último día de
            # gracia en vez de después de agotarla. Con 3 días de gracia,
            # el residente debe poder usar los 3 completos (días 1, 2 y 3
            # de mora) y recién al día 4 se le corta.
            if dias > dias_gracia:
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
            # Día 62: se guarda también dias_gracia, para que el mensaje
            # pueda decir cuántos días le quedan antes del corte real (en
            # vez de asumir un modelo fijo de 3 días como antes).
            if dias >= 1:
                avisos_mora.setdefault(cuenta.id, {
                    "cuenta": cuenta, "dias": dias, "monto": 0.0,
                    "dias_gracia": dias_gracia,
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
            titulo, cuerpo = _mensaje_mora(dias, monto_txt, info.get("dias_gracia"))
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
