"""
Módulo de control de acceso físico — /api/v1/acceso/

Este es el endpoint que el agente de cada acceso (la Raspberry Pi) consulta
cuando alguien pasa su tarjeta RFID. La Pi lee el UID de la tarjeta y pregunta
al servidor si debe abrir la tranca o el torniquete.

Flujo:
  1. La Pi lee el card_uid y envía POST /acceso/validar-tarjeta {card_uid, acceso_id}
  2. El servidor valida en capas: tarjeta existe, activa, cuenta al día,
     y que el tipo de acceso de la tarjeta permita ese acceso físico
  3. Responde permitir/denegar + motivo. Si permite y el acceso físico tiene
     un relay configurado, incluye "orden_pulso" {relay_pin, pulso_ms}: la Pi
     cierra el contacto seco en ese pin durante esos milisegundos.
  4. Registra el intento como EventoAcceso (origen="residente") para el historial

La lógica de permisos: una tarjeta 'peatonal' (corto alcance) solo abre
accesos peatonales (torniquetes). Una tarjeta 'vehicular' (largo alcance) abre
ambos. Es una jerarquía: vehicular incluye peatonal.

NOTA: el disparo físico del relé lo hace la Pi según la respuesta; el modo
offline (cache local de tarjetas) es una fase posterior. Por ahora la
autenticación del dispositivo es un token simple en el header; se endurece al
desplegar.
"""
import datetime as dt

from flask import Blueprint, request, jsonify

from app.extensions import db, limiter
from app.auth.security import roles_required
from app.models.cuenta import Tarjeta, Cuenta, TarjetaVirtual, CredencialBLE
from app.models.visita import EventoAcceso, AccesoFisico
from app.models.dispositivo import Dispositivo
from app.models.camara import Camara
from app.services.permisos import motivo_denegacion, tarjetas_con_permiso
from app.utils.residencial import residencial_id_heredado

acceso_bp = Blueprint("acceso", __name__)


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _dispositivo_actual():
    """
    Identifica la Pi por su token individual (header X-Device-Token) contra la
    tabla de dispositivos. Devuelve el Dispositivo si el token es válido y está
    activo, o None.

    DEVICE-06 (Auditoría Día 35): la comparación es contra el HASH guardado
    en la base (token_hash), nunca contra un token en claro — la base de
    datos nunca contiene el token real de ninguna Pi. Antes existía además
    un fallback legacy (_dispositivo_autorizado) con un único token global
    compartido por variable de entorno, usado solo por /validar-tarjeta —
    se eliminó: ahora ese endpoint también identifica la Pi individual,
    igual que /sincronizar y /reportar.
    """
    token = request.headers.get("X-Device-Token", "")
    if not token:
        return None
    from app.models.dispositivo import hash_token
    disp = Dispositivo.query.filter_by(token_hash=hash_token(token), activo=True).first()
    return disp


@acceso_bp.post("/validar-tarjeta")
@limiter.limit("60 per minute")
def validar_tarjeta():
    """
    Recibe {card_uid, acceso_id} y decide si se permite el acceso.
    Devuelve {permitido, motivo, ...} y registra el evento.

    DEVICE-06: antes usaba el token global compartido (_dispositivo_autorizado).
    Ahora identifica la Pi individual igual que /sincronizar y /reportar —
    el evento queda atribuido a qué dispositivo exacto lo generó.
    """
    disp = _dispositivo_actual()
    if not disp:
        return _err("dispositivo_no_autorizado",
                    "Dispositivo no autorizado para validar accesos", 401)

    data = request.get_json(silent=True) or {}
    card_uid = (data.get("card_uid") or "").strip()
    acceso_id = data.get("acceso_id")

    if not card_uid:
        return _err("datos_incompletos", "card_uid es obligatorio", 400)

    # El acceso físico contra el que se valida (la tranca/torniquete)
    acceso = AccesoFisico.query.get(acceso_id) if acceso_id else None
    if not acceso or not acceso.activo:
        return _err("acceso_invalido", "Acceso físico no encontrado o inactivo", 400)

    def responder(permitido, motivo, tarjeta=None, residente=None):
        """Registra el evento y arma la respuesta."""
        # Dirección: la define la tranca (cada tranca es de entrada o de salida).
        # Ya no se adivina alternando: es un estándar del sistema tener una
        # tranca por dirección en cada punto.
        direccion = acceso.direccion or "entrada"

        evento = EventoAcceso(
            origen="residente",
            direccion=direccion,
            acceso_id=acceso.id,
            tarjeta_id=tarjeta.id if tarjeta else None,
            residente_id=residente.id if residente else None,
            dispositivo_id=disp.id,
            sincronizado=True,
        )
        db.session.add(evento)
        db.session.commit()

        resp = {
            "permitido": permitido,
            "motivo": motivo,
            "direccion": direccion if permitido else None,
            "acceso": acceso.nombre,
        }
        if residente and residente.usuario:
            resp["residente"] = f"{residente.usuario.nombre} {residente.usuario.apellido}"
        if tarjeta:
            resp["tipo_acceso"] = tarjeta.tipo_acceso
        # Orden de pulso para la Raspberry Pi: solo si el acceso está permitido
        # y este acceso físico tiene un relay configurado. La Pi cierra el
        # contacto seco en 'relay_pin' durante 'pulso_ms' milisegundos.
        if permitido and acceso.relay_pin is not None:
            resp["orden_pulso"] = {
                "relay_pin": acceso.relay_pin,
                "pulso_ms": acceso.pulso_ms or 800,
            }
        return jsonify({"data": resp}), 200

    # 1. La tarjeta existe
    tarjeta = Tarjeta.query.filter_by(card_uid=card_uid).first()
    if not tarjeta:
        return responder(False, "Tarjeta no registrada")

    # 2-4. Permiso (tarjeta activa, cuenta activa/sin mora, tipo compatible,
    #      y misma residencial que esta Pi — bases multi-residencial Día 37).
    #      Fuente única de verdad: app.services.permisos
    motivo = motivo_denegacion(tarjeta, acceso, residencial_id=disp.residencial_id)
    if motivo:
        return responder(False, motivo, tarjeta, tarjeta.residente)

    # Todo en orden: acceso permitido
    return responder(True, "Acceso permitido", tarjeta, tarjeta.residente)


@acceso_bp.get("/sincronizar")
@limiter.limit("30 per minute")
def sincronizar():
    """
    La Raspberry Pi descarga aquí su copia local para validar accesos sin
    depender de internet en cada lectura.

    Se autentica con su token individual (header X-Device-Token). Devuelve solo
    lo de SU punto de acceso (deducido del token, no del cuerpo, para que no se
    pueda falsificar):
      - tarjetas: las que tienen permiso vigente (card_uid, tipo_acceso, nombre)
      - accesos:  las trancas de su punto, con relay_pin y pulso_ms
      - generado_en: sello de tiempo para que la Pi sepa si su copia está al día
    """
    disp = _dispositivo_actual()
    if not disp:
        return _err("dispositivo_no_autorizado",
                    "Dispositivo no autorizado o revocado", 401)

    # Trancas del punto de esta Pi (si la Pi no tiene punto, no devuelve trancas)
    accesos_q = AccesoFisico.query.filter_by(activo=True)
    if disp.punto_acceso:
        accesos_q = accesos_q.filter_by(punto_acceso=disp.punto_acceso)
    # Bases multi-residencial (Día 37): además del punto, la Pi solo recibe
    # trancas de SU residencial. Si la Pi no tiene residencial asignada
    # (disp.residencial_id es None), no se filtra — comportamiento idéntico
    # al de siempre, para no romper nada mientras no se asignen dispositivos.
    if disp.residencial_id is not None:
        accesos_q = accesos_q.filter_by(residencial_id=disp.residencial_id)
    accesos = accesos_q.all()

    # Tarjetas físicas con permiso vigente (ya filtradas por residencial si aplica)
    tarjetas = tarjetas_con_permiso(residencial_id=disp.residencial_id)
    tarjetas_out = []
    for t in tarjetas:
        nombre = None
        if t.residente and t.residente.usuario:
            nombre = f"{t.residente.usuario.nombre} {t.residente.usuario.apellido}"
        tarjetas_out.append({
            "card_uid": t.card_uid,
            "tipo_acceso": t.tipo_acceso,
            "residente": nombre,
        })

    # Tarjetas virtuales (QR permanentes que rotan cada 24h)
    # ROTATION-07 (Auditoría Día 35): antes se comparaba la hora ACTUAL del
    # servidor en UTC contra un rango fijo ("es medianoche y faltan menos
    # de 10 min") — pero la rotación real ocurre a medianoche hora de
    # Honduras (UTC-6), así que la ventana de gracia quedaba activa a las
    # 6:00 AM en vez de a medianoche. Ahora se compara contra la fecha de
    # expiración GUARDADA en cada fila al momento de rotar
    # (codigo_anterior_valido_hasta/token_anterior_valido_hasta) — sin
    # ninguna suposición de zona horaria ni de "qué hora es ahora".
    ahora = dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    virtuales_q = TarjetaVirtual.query.filter_by(estado="activa")
    if disp.residencial_id is not None:
        from app.models.cuenta import Unidad
        virtuales_q = (virtuales_q
                       .join(Cuenta, TarjetaVirtual.cuenta_id == Cuenta.id)
                       .join(Unidad, Cuenta.unidad_id == Unidad.id)
                       .filter(Unidad.residencial_id == disp.residencial_id))
    virtuales = virtuales_q.all()
    for tv in virtuales:
        nombre = None
        if tv.residente and tv.residente.usuario:
            nombre = f"{tv.residente.usuario.nombre} {tv.residente.usuario.apellido}"
        tarjetas_out.append({
            "card_uid": tv.codigo_hoy,
            "tipo_acceso": tv.tipo_acceso,
            "residente": nombre,
            "es_virtual": True,
        })
        # Código anterior válido solo hasta su fecha de expiración guardada
        if tv.codigo_anterior and tv.codigo_anterior_valido_hasta and ahora < tv.codigo_anterior_valido_hasta:
            tarjetas_out.append({
                "card_uid": tv.codigo_anterior,
                "tipo_acceso": tv.tipo_acceso,
                "residente": nombre,
                "es_virtual": True,
            })

    # Credenciales BLE (Bluetooth). El lector BLE valida el desafío-respuesta
    # con la clave secreta; la Pi solo necesita conocer los tokens válidos y
    # sus claves para pasárselas al lector.
    ble_q = CredencialBLE.query.filter_by(estado="activa")
    if disp.residencial_id is not None:
        from app.models.cuenta import Unidad
        ble_q = (ble_q
                 .join(Cuenta, CredencialBLE.cuenta_id == Cuenta.id)
                 .join(Unidad, Cuenta.unidad_id == Unidad.id)
                 .filter(Unidad.residencial_id == disp.residencial_id))
    credenciales_ble = ble_q.all()
    ble_out = []
    for c in credenciales_ble:
        nombre = None
        if c.residente and c.residente.usuario:
            nombre = f"{c.residente.usuario.nombre} {c.residente.usuario.apellido}"
        ble_out.append({
            "token": c.token_hoy,
            "clave_secreta": c.clave_secreta,
            "contador": c.contador,
            "tipo_acceso": c.tipo_acceso,
            "residente": nombre,
        })
        if c.token_anterior and c.token_anterior_valido_hasta and ahora < c.token_anterior_valido_hasta:
            ble_out.append({
                "token": c.token_anterior,
                "clave_secreta": c.clave_secreta,
                "contador": c.contador,
                "tipo_acceso": c.tipo_acceso,
                "residente": nombre,
            })

    # Registrar la última sincronización de esta Pi
    disp.ultima_sync = dt.datetime.utcnow()
    db.session.commit()

    return jsonify({"data": {
        "punto_acceso": disp.punto_acceso,
        "generado_en": dt.datetime.utcnow().isoformat() + "Z",
        "accesos": [a.to_dict() for a in accesos],
        "tarjetas": tarjetas_out,
        "credenciales_ble": ble_out,
    }})


@acceso_bp.post("/reportar")
@limiter.limit("60 per minute")
def reportar_eventos():
    """
    La Raspberry Pi reporta aquí los accesos que registró localmente.

    Se autentica con su token (X-Device-Token). Acepta una lista de eventos
    (la Pi puede acumular varios si estuvo sin conexión y mandarlos juntos).

    Cada evento del cuerpo:
      - id_externo: identificador único generado por la Pi (idempotencia)
      - card_uid:   tarjeta que pasó
      - acceso_id:  id de la tranca por la que pasó (define la dirección)
      - ocurrido_en: ISO 8601, cuándo pasó realmente (opcional; default ahora)

    La dirección NO la manda la Pi: la pone el servidor según la tranca, en
    coherencia con el estándar de dirección fija por tranca.

    Devuelve cuántos se guardaron y cuántos se ignoraron por duplicado.
    """
    disp = _dispositivo_actual()
    if not disp:
        return _err("dispositivo_no_autorizado",
                    "Dispositivo no autorizado o revocado", 401)

    body = request.get_json(silent=True) or {}
    eventos = body.get("eventos")
    if not isinstance(eventos, list):
        return _err("formato_invalido",
                    "Se espera un objeto con la lista 'eventos'", 400)

    guardados = 0
    duplicados = 0
    ignorados = 0

    for ev in eventos:
        id_externo = (ev.get("id_externo") or "").strip()
        if not id_externo:
            ignorados += 1
            continue

        # Idempotencia: si ya existe ese id_externo, no se vuelve a registrar.
        if EventoAcceso.query.filter_by(id_externo=id_externo).first():
            duplicados += 1
            continue

        acceso = AccesoFisico.query.get(ev.get("acceso_id")) if ev.get("acceso_id") else None
        if not acceso:
            ignorados += 1
            continue

        # Seguridad: la Pi solo puede reportar trancas de su propio punto.
        if disp.punto_acceso and acceso.punto_acceso and acceso.punto_acceso != disp.punto_acceso:
            ignorados += 1
            continue

        # Bases multi-residencial (Día 37): si la Pi tiene una residencial
        # asignada, solo puede reportar eventos de trancas de esa misma
        # residencial — mismo criterio de defensa que ya existía para el
        # punto de acceso, extendido al nuevo nivel de aislamiento.
        if disp.residencial_id is not None and acceso.residencial_id != disp.residencial_id:
            ignorados += 1
            continue

        tarjeta = Tarjeta.query.filter_by(card_uid=(ev.get("card_uid") or "")).first()

        # Cuándo ocurrió realmente (lo que reporta la Pi), no cuándo se recibió.
        ocurrido = None
        if ev.get("ocurrido_en"):
            try:
                ocurrido = dt.datetime.fromisoformat(ev["ocurrido_en"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ocurrido = None

        evento = EventoAcceso(
            origen="residente",
            direccion=acceso.direccion or "entrada",   # la define la tranca
            acceso_id=acceso.id,
            tarjeta_id=tarjeta.id if tarjeta else None,
            residente_id=tarjeta.residente_id if tarjeta and tarjeta.residente_id else None,
            dispositivo_id=disp.id,  # DEVICE-06: trazabilidad de qué Pi lo generó
            ocurrido_en=ocurrido or dt.datetime.utcnow(),
            sincronizado=True,
            id_externo=id_externo,
        )
        db.session.add(evento)
        guardados += 1

    disp.ultima_sync = dt.datetime.utcnow()
    db.session.commit()

    return jsonify({"data": {
        "guardados": guardados,
        "duplicados": duplicados,
        "ignorados": ignorados,
        "recibidos": len(eventos),
    }})


# =====================================================================
# AGENTE DE CÁMARAS (Raspberry Pi tipo='camara')
#
# Programa separado del agente de accesos (misma tabla dispositivos_pi,
# mismo mecanismo de token/revocación, pero un ejecutable Python distinto
# que corre en su propia Pi). Reusa _dispositivo_actual() para autenticarse.
# =====================================================================

@acceso_bp.get("/camaras/config")
@limiter.limit("30 per minute")
def config_camaras_agente():
    """
    El agente de cámaras descarga aquí la lista de cámaras que le tocan
    (las asignadas a su dispositivo_id) con sus credenciales RTSP, para
    poder conectarse al NVR por su cuenta.

    Se autentica con su token individual (header X-Device-Token), igual
    que el agente de accesos. Solo devuelve las cámaras asignadas a ESTE
    dispositivo (no todas las de la residencial).
    """
    disp = _dispositivo_actual()
    if not disp:
        return _err("dispositivo_no_autorizado",
                    "Dispositivo no autorizado o revocado", 401)
    if disp.tipo != "camara":
        return _err("tipo_incorrecto",
                    "Este dispositivo no es un agente de cámaras", 403)

    camaras = Camara.query.filter_by(dispositivo_id=disp.id, activa=True).all()

    return jsonify({"data": {
        "generado_en": dt.datetime.utcnow().isoformat() + "Z",
        "camaras": [c.to_dict(incluir_credenciales=True) for c in camaras],
    }})


@acceso_bp.post("/camaras/heartbeat")
@limiter.limit("30 per minute")
def heartbeat_agente_camaras():
    """
    El agente de cámaras llama esto periódicamente (ej. cada 30s) para que
    el servidor sepa que sigue conectado. El Centro de Monitoreo usa
    ultimo_heartbeat para mostrar 'agente conectado / desconectado'.
    """
    disp = _dispositivo_actual()
    if not disp:
        return _err("dispositivo_no_autorizado",
                    "Dispositivo no autorizado o revocado", 401)

    disp.ultimo_heartbeat = dt.datetime.utcnow()
    db.session.commit()
    return jsonify({"data": {"ok": True}})


# =====================================================================
# ADMIN: gestión operativa de puntos de acceso (ACCESS-04, Auditoría Día 35)
#
# Un "punto de acceso" es un lugar físico de la residencial (ej. "Portón
# Principal") que puede tener una tranca peatonal, una vehicular, o ambas
# (entrada + salida vehicular por separado). Cada tranca individual sigue
# siendo una fila en accesos_fisicos, agrupada por el campo punto_acceso.
#
# División de responsabilidad deliberada:
#   - El ADMIN gestiona aquí lo operativo: nombre del punto, qué trancas
#     tiene (peatonal / entrada vehicular / salida vehicular), activar o
#     desactivar. Esto es equivalente a dar de alta una casa o un residente
#     — no requiere conocimiento técnico.
#   - relay_pin y pulso_ms (el cableado real a la Raspberry Pi) siguen
#     existiendo SOLO en el panel de desarrollador. Un admin sin
#     conocimiento técnico que cambie un pin GPIO por error podría dejar
#     una tranca sin funcionar o dos trancas apuntando al mismo pin.
#   - Por la misma razón, el admin NUNCA borra un punto de verdad — solo
#     lo desactiva. El historial de accesos que ya pasó por ahí no se
#     pierde nunca.
# =====================================================================

# Marcador para trancas creadas antes de existir el concepto de "punto de
# acceso" (ej. desde el panel de desarrollador antiguo), que en la base
# real tienen punto_acceso = NULL. Se agrupan bajo esta etiqueta para que
# no desaparezcan silenciosamente de la lista del admin, y se permite
# asignarles un nombre real desde el mismo panel.
SIN_PUNTO = "(sin nombre de punto)"


def _trancas_del_punto(nombre_punto):
    """Busca las trancas de un punto por nombre. Si el nombre es SIN_PUNTO,
    busca las que tienen punto_acceso=NULL en la base."""
    if nombre_punto == SIN_PUNTO:
        return AccesoFisico.query.filter(AccesoFisico.punto_acceso.is_(None)).all()
    return AccesoFisico.query.filter_by(punto_acceso=nombre_punto).all()


def _punto_a_dict(nombre_punto, trancas):
    """Agrupa las trancas individuales (filas AccesoFisico) de un mismo
    punto_acceso en un solo objeto para el admin y para el guardia."""
    peatonal = next((t for t in trancas if t.tipo == "peatonal"), None)
    veh_entrada = next((t for t in trancas if t.tipo == "vehicular" and t.direccion == "entrada"), None)
    veh_salida = next((t for t in trancas if t.tipo == "vehicular" and t.direccion == "salida"), None)
    return {
        "punto_acceso": nombre_punto,
        "sin_nombre": nombre_punto == SIN_PUNTO,
        "activo": any(t.activo for t in trancas),
        "tiene_peatonal": peatonal is not None,
        "tiene_vehicular_entrada": veh_entrada is not None,
        "tiene_vehicular_salida": veh_salida is not None,
        "trancas": [t.to_dict() for t in trancas],
    }


@acceso_bp.get("/puntos")
@roles_required("admin", "super_admin", "guardia")
def listar_puntos_acceso(usuario_actual):
    """
    Lista los puntos de acceso agrupados por punto_acceso. Un guardia
    también puede consultar esta lista (para elegir en cuál está); un
    admin la usa para gestionarlos.

    Bases multi-residencial (Día 37): se filtra por la residencial del
    usuario que consulta, cuando la tiene asignada. Si no la tiene (ej.
    super_admin, o un usuario creado antes de este cambio), se muestra
    todo sin filtrar — igual que el comportamiento de siempre. Hoy, con
    una sola residencial en Villas del Sol, el resultado es idéntico
    filtrado o sin filtrar.
    """
    solo_activos = request.args.get("solo_activos", "true").lower() != "false"
    q = AccesoFisico.query
    if solo_activos:
        q = q.filter_by(activo=True)
    if usuario_actual.residencial_id is not None:
        q = q.filter_by(residencial_id=usuario_actual.residencial_id)
    trancas = q.order_by(AccesoFisico.punto_acceso, AccesoFisico.tipo).all()

    agrupado = {}
    for t in trancas:
        clave = t.punto_acceso or SIN_PUNTO
        agrupado.setdefault(clave, []).append(t)

    puntos = [_punto_a_dict(nombre, lista) for nombre, lista in agrupado.items()]
    return jsonify({"data": puntos})


@acceso_bp.post("/puntos")
@roles_required("admin", "super_admin")
def crear_punto_acceso(usuario_actual):
    """
    Crea un punto de acceso nuevo con las trancas que el admin indique.
    Ej: { "nombre": "Portón Secundario", "peatonal": true,
          "vehicular_entrada": true, "vehicular_salida": true }
    Cada tranca marcada como true se crea como una fila AccesoFisico con
    relay_pin=NULL — el desarrollador la configura después al instalar
    el hardware real.
    """
    body = request.get_json(silent=True) or {}
    nombre = (body.get("nombre") or "").strip()
    if not nombre:
        return _err("nombre_requerido", "El nombre del punto de acceso es obligatorio", 400)
    if len(nombre) > 80:
        return _err("nombre_largo", "El nombre no puede superar 80 caracteres", 400)

    # Bases multi-residencial (Día 37): el punto hereda la residencial del
    # admin/supervisor que lo crea. El chequeo de nombre duplicado se
    # acota a esa misma residencial cuando existe — así, el día que haya
    # una segunda residencial, cada una puede tener su propio "Portón
    # Principal" sin chocar. Hoy, con una sola, el resultado es idéntico
    # al chequeo global de antes.
    residencial_id = residencial_id_heredado(usuario_actual)
    dup_q = AccesoFisico.query.filter_by(punto_acceso=nombre)
    if residencial_id is not None:
        dup_q = dup_q.filter_by(residencial_id=residencial_id)
    if dup_q.first():
        return _err("nombre_duplicado", "Ya existe un punto de acceso con ese nombre", 400)

    quiere_peatonal = bool(body.get("peatonal"))
    quiere_veh_entrada = bool(body.get("vehicular_entrada"))
    quiere_veh_salida = bool(body.get("vehicular_salida"))
    if not (quiere_peatonal or quiere_veh_entrada or quiere_veh_salida):
        return _err("sin_trancas", "Elegí al menos una tranca para el punto de acceso", 400)

    creadas = []
    if quiere_peatonal:
        t = AccesoFisico(nombre=f"{nombre} — Peatonal", tipo="peatonal",
                          direccion="entrada", punto_acceso=nombre, activo=True,
                          residencial_id=residencial_id)
        db.session.add(t)
        creadas.append(t)
    if quiere_veh_entrada:
        t = AccesoFisico(nombre=f"{nombre} — Entrada vehicular", tipo="vehicular",
                          direccion="entrada", punto_acceso=nombre, activo=True,
                          residencial_id=residencial_id)
        db.session.add(t)
        creadas.append(t)
    if quiere_veh_salida:
        t = AccesoFisico(nombre=f"{nombre} — Salida vehicular", tipo="vehicular",
                          direccion="salida", punto_acceso=nombre, activo=True,
                          residencial_id=residencial_id)
        db.session.add(t)
        creadas.append(t)

    db.session.commit()
    return jsonify({"data": _punto_a_dict(nombre, creadas)}), 201


@acceso_bp.put("/puntos/<nombre_punto>")
@roles_required("admin", "super_admin")
def editar_punto_acceso(usuario_actual, nombre_punto):
    """
    Edita lo operativo de un punto: nombre nuevo, o activar/desactivar
    todas sus trancas de una vez. NO permite tocar relay_pin ni pulso_ms
    — eso sigue siendo exclusivo del panel de desarrollador.
    """
    trancas = _trancas_del_punto(nombre_punto)
    if not trancas:
        return _err("no_encontrado", "Punto de acceso no encontrado", 404)

    body = request.get_json(silent=True) or {}

    if "activo" in body:
        activo = bool(body["activo"])
        for t in trancas:
            t.activo = activo

    nuevo_nombre = None
    if "nombre" in body:
        nuevo_nombre = (body["nombre"] or "").strip()
        if not nuevo_nombre:
            return _err("nombre_requerido", "El nombre no puede quedar vacío", 400)
        if len(nuevo_nombre) > 80:
            return _err("nombre_largo", "El nombre no puede superar 80 caracteres", 400)
        if nuevo_nombre != nombre_punto and AccesoFisico.query.filter_by(punto_acceso=nuevo_nombre).first():
            return _err("nombre_duplicado", "Ya existe un punto de acceso con ese nombre", 400)
        for t in trancas:
            t.punto_acceso = nuevo_nombre
            # Mantener el nombre descriptivo de cada tranca en sincronía
            sufijo = t.nombre.split("—")[-1].strip() if "—" in t.nombre else t.tipo
            t.nombre = f"{nuevo_nombre} — {sufijo}"

    db.session.commit()
    return jsonify({"data": _punto_a_dict(nuevo_nombre or nombre_punto, trancas)})


@acceso_bp.get("/puntos/<nombre_punto>/historial-count")
@roles_required("admin", "super_admin")
def historial_count_punto(usuario_actual, nombre_punto):
    """Cuántos eventos de acceso tiene un punto — informativo antes de desactivarlo."""
    trancas = _trancas_del_punto(nombre_punto)
    if not trancas:
        return _err("no_encontrado", "Punto de acceso no encontrado", 404)
    ids = [t.id for t in trancas]
    n = EventoAcceso.query.filter(EventoAcceso.acceso_id.in_(ids)).count()
    return jsonify({"data": {"eventos": n}})
