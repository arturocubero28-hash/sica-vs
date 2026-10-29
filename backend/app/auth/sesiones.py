"""
Día 72 — sesión persistente de la app (estilo WhatsApp).

Antes la app guardaba solo el JWT, que vence a las 12 horas: al abrirla al
día siguiente el servidor respondía 401 y la persona tenía que volver a
escribir su contraseña. Ahora, cuando la app inicia sesión con
"recordar": true, recibe además un TOKEN DE RENOVACIÓN:

  - Es aleatorio (no es un JWT) y del servidor solo se guarda su SHA-256.
  - Cuando el JWT vence, la app llama a POST /auth/renovar con ese token y
    recibe un JWT nuevo + un token de renovación nuevo (rotación). El
    anterior deja de servir.
  - La sesión dura mientras la app se siga usando. Se cierra cuando:
      · la persona toca "Cerrar sesión",
      · la cierra desde "dispositivos conectados" en otro equipo,
      · cambia o restablece su contraseña,
      · el admin desactiva su usuario,
      · pasan SESION_APP_DIAS sin abrir la app.

La huella de la app NO tiene nada que ver con esto: solo desbloquea la
pantalla en el teléfono. La sesión vive en el servidor.
"""
import datetime as dt
import hashlib
import secrets

from flask import current_app

from app.extensions import db


def ahora_utc():
    return dt.datetime.now(dt.timezone.utc)


def con_zona(fecha):
    """SQLite devuelve fechas sin zona; Postgres con zona. Se normaliza."""
    if fecha is None:
        return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=dt.timezone.utc)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def vencimiento_sesion_app():
    return ahora_utc() + dt.timedelta(days=current_app.config["SESION_APP_DIAS"])


def emitir_refresh(sesion) -> str:
    """Genera un token de renovación nuevo para la sesión y rota el anterior.
    Devuelve el token en claro: es la única vez que existe fuera del teléfono."""
    token = secrets.token_urlsafe(48)
    sesion.refresh_anterior_hash = sesion.refresh_hash
    sesion.refresh_hash = hash_refresh(token)
    sesion.refresh_rotado_en = ahora_utc()
    sesion.persistente = True
    return token


def _revocar_jti(jti, usuario_id, expira_en=None):
    from app.models.token_revocado import TokenRevocado
    if not jti or TokenRevocado.esta_revocado(jti):
        return
    if expira_en is None:
        expira_en = ahora_utc() + dt.timedelta(
            hours=current_app.config["JWT_EXPIRES_HOURS"])
    db.session.add(TokenRevocado(jti=jti, usuario_id=usuario_id,
                                 expira_en=con_zona(expira_en)))


def cerrar_sesion_registro(sesion):
    """Cierra UNA sesión: su JWT a la lista negra y el registro (con su
    token de renovación) se borra. No hace commit."""
    _revocar_jti(sesion.jti, sesion.usuario_id, sesion.expira_en)
    db.session.delete(sesion)


def cerrar_sesiones_de(usuario, excepto_jti=None) -> int:
    """Cierra todas las sesiones de un usuario (menos la indicada).
    Se usa al cambiar o restablecer la contraseña: si alguien se quedó con
    un teléfono, deja de tener acceso. No hace commit."""
    from app.models.sesion_activa import SesionActiva
    q = SesionActiva.query.filter(SesionActiva.usuario_id == usuario.id)
    if excepto_jti:
        q = q.filter(SesionActiva.jti != excepto_jti)
    sesiones = q.all()
    for s in sesiones:
        cerrar_sesion_registro(s)
    return len(sesiones)


def buscar_por_refresh(token: str):
    """Devuelve (sesion, es_anterior). es_anterior=True si el token es el
    que ya fue rotado (reintento o posible robo: decide quien llama)."""
    from app.models.sesion_activa import SesionActiva
    if not token or len(token) > 200:
        return None, False
    h = hash_refresh(token)
    s = SesionActiva.query.filter_by(refresh_hash=h).first()
    if s:
        return s, False
    s = SesionActiva.query.filter_by(refresh_anterior_hash=h).first()
    if s:
        return s, True
    return None, False


def dentro_de_gracia(sesion) -> bool:
    rotado = con_zona(sesion.refresh_rotado_en)
    if not rotado:
        return False
    margen = dt.timedelta(seconds=current_app.config["REFRESH_GRACIA_SEGUNDOS"])
    return ahora_utc() - rotado <= margen


def revocar_jti_anterior(jti, usuario_id):
    """Al renovar, el JWT anterior de esa sesión deja de valer."""
    _revocar_jti(jti, usuario_id)
