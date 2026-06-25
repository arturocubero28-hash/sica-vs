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
import hmac

from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter
from app.models.cuenta import Tarjeta, Cuenta
from app.models.visita import EventoAcceso, AccesoFisico
from app.models.dispositivo import Dispositivo
from app.services.permisos import motivo_denegacion, tarjetas_con_permiso

acceso_bp = Blueprint("acceso", __name__)


def _err(code, message, status):
    return jsonify({"error": {"code": code, "message": message}}), status


def _dispositivo_autorizado():
    """
    Verifica el token del dispositivo (la Pi) en el header X-Device-Token.
    Por ahora compara contra una variable de entorno simple. Al desplegar se
    puede dar un token único por acceso físico.
    """
    token = request.headers.get("X-Device-Token", "")
    esperado = current_app.config.get("DEVICE_TOKEN", "sicavs-device-dev")
    # Comparación en tiempo constante para evitar timing attacks que permitirían
    # reconstruir el token carácter por carácter midiendo tiempos de respuesta.
    if not token or not esperado:
        return False
    return hmac.compare_digest(token, esperado)


def _dispositivo_actual():
    """
    Identifica la Pi por su token individual (header X-Device-Token) contra la
    tabla de dispositivos. Devuelve el Dispositivo si el token es válido y está
    activo, o None. Es la forma nueva (por-Pi); _dispositivo_autorizado() es el
    fallback legacy del token compartido.
    """
    token = request.headers.get("X-Device-Token", "")
    if not token:
        return None
    disp = Dispositivo.query.filter_by(token=token, activo=True).first()
    return disp


@acceso_bp.post("/validar-tarjeta")
@limiter.limit("60 per minute")
def validar_tarjeta():
    """
    Recibe {card_uid, acceso_id} y decide si se permite el acceso.
    Devuelve {permitido, motivo, ...} y registra el evento.
    """
    if not _dispositivo_autorizado():
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
        # Dirección: alterna entrada/salida según el último evento de la tarjeta
        direccion = "entrada"
        if tarjeta:
            ultimo = (EventoAcceso.query
                      .filter_by(tarjeta_id=tarjeta.id)
                      .order_by(EventoAcceso.ocurrido_en.desc())
                      .first())
            if ultimo and ultimo.direccion == "entrada":
                direccion = "salida"

        evento = EventoAcceso(
            origen="residente",
            direccion=direccion if permitido else "entrada",
            acceso_id=acceso.id,
            tarjeta_id=tarjeta.id if tarjeta else None,
            residente_id=residente.id if residente else None,
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

    # 2-4. Permiso (tarjeta activa, cuenta activa/sin mora, tipo compatible).
    #      Fuente única de verdad: app.services.permisos
    motivo = motivo_denegacion(tarjeta, acceso)
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
    accesos = accesos_q.all()

    # Tarjetas con permiso vigente (fuente única de verdad). Para el modelo de
    # copia local, la Pi recibe la lista completa de quién puede entrar; la
    # compatibilidad de tipo (peatonal/vehicular) la resuelve la Pi por tranca.
    tarjetas = tarjetas_con_permiso()
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

    # Registrar la última sincronización de esta Pi
    disp.ultima_sync = dt.datetime.utcnow()
    db.session.commit()

    return jsonify({"data": {
        "punto_acceso": disp.punto_acceso,
        "generado_en": dt.datetime.utcnow().isoformat() + "Z",
        "accesos": [a.to_dict() for a in accesos],
        "tarjetas": tarjetas_out,
    }})
