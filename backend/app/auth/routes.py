"""
Endpoints de autenticación.

  POST /api/v1/auth/login        { email, password, recordar? } -> { token, usuario, refresh_token? }
  POST /api/v1/auth/renovar      { refresh_token }        -> { token, refresh_token, usuario }
  GET  /api/v1/auth/me           (con token)              -> { usuario }
  POST /api/v1/auth/activar      { token, password }      -> activa cuenta y define contraseña
  POST /api/v1/auth/recuperar    { email }                -> envía token de recuperación
  POST /api/v1/auth/reset        { token, password }      -> define nueva contraseña
"""
import datetime as dt

import jwt
from flask import Blueprint, request, jsonify, current_app

from app.extensions import db, limiter, key_login
from app.config import Config
from app.models.usuario import Usuario
from app.auth.security import generar_token, token_required, revocar_token
from app.utils.passwords import ROLES_CREDENCIAL_LOCAL

auth_bp = Blueprint("auth", __name__)


def validar_password(password):
    """
    Valida la política mínima de contraseñas:
    - Al menos 8 caracteres
    - Al menos una letra mayúscula
    - Al menos un signo (carácter no alfanumérico)
    Devuelve None si es válida, o un mensaje de error si no.
    """
    import re
    if not password or len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres"
    if not re.search(r"[A-Z]", password):
        return "La contraseña debe incluir al menos una letra mayúscula"
    if not re.search(r"[^A-Za-z0-9]", password):
        return "La contraseña debe incluir al menos un signo (ej: ! @ # $ % & *)"
    return None


def _huella_password(usuario):
    """O1.4: huella corta del hash de contraseña actual del usuario.

    Se incrusta en los tokens de reset para hacerlos de un solo uso SIN
    necesidad de guardar tokens usados en la base: cuando el reset cambia la
    contraseña, el hash cambia, la huella deja de coincidir y el token queda
    automáticamente inválido. Un segundo intento con el mismo enlace falla.
    Se usa un tramo del hash (no el hash completo) para no exponerlo en el JWT.
    """
    if not usuario or not usuario.password_hash:
        return ""
    import hashlib
    return hashlib.sha256(usuario.password_hash.encode("utf-8")).hexdigest()[:16]


def _generar_token_temporal(email, proposito, horas=48, huella=None):
    """Genera un JWT de corta vida para activación o recuperación.

    Si se pasa 'huella' (O1.4), se incrusta para atar el token al estado
    actual de la contraseña, haciéndolo de un solo uso.
    """
    payload = {
        "sub": email,
        "proposito": proposito,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=horas),
    }
    if huella is not None:
        payload["huella"] = huella
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def _verificar_token_temporal(token_str, proposito_esperado):
    """Decodifica un token temporal y devuelve el email o None."""
    try:
        p = jwt.decode(token_str, current_app.config["JWT_SECRET"], algorithms=["HS256"])
        if p.get("proposito") != proposito_esperado:
            return None
        return p.get("sub")
    except jwt.PyJWTError:
        return None


def _huella_de_token(token_str):
    """Devuelve la huella incrustada en el token (o None si no tiene)."""
    try:
        p = jwt.decode(token_str, current_app.config["JWT_SECRET"], algorithms=["HS256"])
        return p.get("huella")
    except jwt.PyJWTError:
        return None


# ── Login ──────────────────────────────────────────────────────
@auth_bp.post("/login")
# Día 70 — DOS límites, y cada uno mide una cosa distinta:
#   por CUENTA  -> fuerza bruta contra un correo concreto (lo que de verdad
#                  importa frenar);
#   por IP      -> alguien barriendo muchas cuentas desde un mismo lugar.
# Antes solo existía el de IP, con el mismo valor estricto, y eso dejaba
# sin entrar a toda la caseta cuando un guardia se equivocaba: ahí varias
# personas comparten la salida a internet. Ver extensions.key_login.
@limiter.limit(lambda: Config.LOGIN_RATE_LIMIT, key_func=key_login)
@limiter.limit(lambda: Config.LOGIN_RATE_LIMIT_IP)
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Email y contraseña son obligatorios"}}), 400

    usuario = Usuario.query.filter_by(email=email).first()
    # Día 69 — una persona del padrón (censo) no tiene credenciales. Se
    # rechaza con el MISMO mensaje genérico que una credencial inválida, para
    # no revelar que ese correo existe en el sistema pero sin acceso: sería
    # enumeración de usuarios, justo lo que el pentest del Día 14 confirmó
    # que el login no permite.
    if usuario and not usuario.puede_iniciar_sesion:
        from flask import g
        g.email_intento = email[:120] if email else None
        return jsonify({"error": {"code": "credenciales_invalidas",
                                  "message": "Email o contraseña incorrectos"}}), 401

    if not usuario or not usuario.check_password(password):
        from flask import g
        g.email_intento = email[:120] if email else None
        return jsonify({"error": {"code": "credenciales_invalidas",
                                  "message": "Email o contraseña incorrectos"}}), 401

    if not usuario.activo:
        # AUDIT-12 — también capturamos el email para el log cuando el usuario
        # existe pero está inactivo: antes solo se capturaba en el caso de
        # credenciales inválidas, dejando este camino sin actor identificado.
        from flask import g
        g.email_intento = usuario.email
        return jsonify({"error": {"code": "usuario_inactivo",
                                  "message": "Tu usuario está inactivo. Revisá tu correo para activar tu cuenta."}}), 403

    usuario.ultimo_acceso = dt.datetime.utcnow()

    # Generar token y registrar la sesión activa (dispositivo)
    token, jti, expira = generar_token(usuario, devolver_jti=True)
    from app.models.sesion_activa import SesionActiva, describir_dispositivo
    ua = (request.user_agent.string or "")[:300]
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip:
        ip = ip.split(",")[0].strip()[:45]
    sesion = SesionActiva(
        usuario_id=usuario.id, jti=jti,
        dispositivo=describir_dispositivo(ua), user_agent=ua, ip=ip,
        expira_en=expira,
    )
    # Día 72 — la app pide "recordar": la sesión queda abierta hasta que la
    # persona la cierre (ver app/auth/sesiones.py). El panel web no lo pide
    # y sigue igual que antes.
    refresh = None
    if (data.get("recordar") is True and usuario.rol not in
            current_app.config["ROLES_SIN_SESION_PERSISTENTE"]):
        from app.auth.sesiones import emitir_refresh, vencimiento_sesion_app
        refresh = emitir_refresh(sesion)
        sesion.expira_en = vencimiento_sesion_app()
    db.session.add(sesion)
    db.session.commit()

    respuesta = {"token": token, "usuario": usuario.to_dict()}
    if refresh:
        respuesta["refresh_token"] = refresh
    return jsonify({"data": respuesta})


# ── Renovar la sesión de la app (Día 72) ───────────────────────
@auth_bp.post("/renovar")
@limiter.limit("30 per minute")
def renovar():
    """
    Cambia un token de renovación válido por un JWT nuevo y un token de
    renovación nuevo. No pide contraseña: es lo que permite que la app
    mantenga la sesión abierta como WhatsApp.

    Rotación: el token presentado deja de servir. Si la app vuelve a
    presentarlo dentro de REFRESH_GRACIA_SEGUNDOS (la respuesta anterior se
    perdió por la red) se le acepta. Si lo presenta DESPUÉS, alguien más lo
    tiene: se cierra la sesión entera.
    """
    from flask import g
    from app.auth import sesiones as S

    data = request.get_json(silent=True) or {}
    presentado = data.get("refresh_token") or ""
    if not isinstance(presentado, str):
        presentado = ""

    def _rechazo(code="sesion_invalida",
                 msg="Tu sesión se cerró. Iniciá sesión de nuevo."):
        return jsonify({"error": {"code": code, "message": msg}}), 401

    sesion, es_anterior = S.buscar_por_refresh(presentado)
    if not sesion or not sesion.persistente:
        return _rechazo()

    if es_anterior and not S.dentro_de_gracia(sesion):
        # Reuso de un token ya rotado fuera del margen: posible robo.
        S.cerrar_sesion_registro(sesion)
        db.session.commit()
        return _rechazo("sesion_revocada",
                        "Por seguridad se cerró tu sesión. Iniciá sesión de nuevo.")

    if S.con_zona(sesion.expira_en) < S.ahora_utc():
        S.cerrar_sesion_registro(sesion)
        db.session.commit()
        return _rechazo("sesion_vencida",
                        "Pasó mucho tiempo sin usar la app. Iniciá sesión de nuevo.")

    usuario = db.session.get(Usuario, sesion.usuario_id)
    if not usuario or not usuario.activo or not usuario.puede_iniciar_sesion:
        S.cerrar_sesion_registro(sesion)
        db.session.commit()
        return _rechazo()

    g.usuario_actual = usuario  # para el hook de auditoría

    token, jti, _exp = generar_token(usuario, devolver_jti=True)
    S.revocar_jti_anterior(sesion.jti, usuario.id)
    sesion.jti = jti
    nuevo_refresh = S.emitir_refresh(sesion)
    sesion.ultimo_uso = S.ahora_utc()
    sesion.expira_en = S.vencimiento_sesion_app()
    usuario.ultimo_acceso = dt.datetime.utcnow()
    db.session.commit()

    return jsonify({"data": {"token": token, "refresh_token": nuevo_refresh,
                             "usuario": usuario.to_dict()}})


# ── Me ─────────────────────────────────────────────────────────
@auth_bp.get("/me")
@token_required
def me(usuario_actual):
    return jsonify({"data": {"usuario": usuario_actual.to_dict()}})


# ── Cambiar contraseña (usuario autenticado) ───────────────────
@auth_bp.post("/cambiar-password")
@token_required
def cambiar_password(usuario_actual):
    data = request.get_json(silent=True) or {}
    actual = data.get("password_actual") or ""
    nueva = data.get("password_nueva") or ""

    # Si el usuario está obligado a cambiar (primer login), no exigimos la actual
    if not usuario_actual.debe_cambiar_password:
        if not usuario_actual.check_password(actual):
            return jsonify({"error": {"code": "password_incorrecta",
                                      "message": "La contraseña actual es incorrecta"}}), 400

    error = validar_password(nueva)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    usuario_actual.set_password(nueva)
    usuario_actual.debe_cambiar_password = False
    # Día 72 — con sesiones que duran meses, cambiar la contraseña tiene que
    # sacar a los demás dispositivos (si alguien se quedó con un teléfono,
    # pierde el acceso). Este dispositivo sigue con su sesión.
    from flask import g
    from app.auth.sesiones import cerrar_sesiones_de
    cerrar_sesiones_de(usuario_actual, excepto_jti=getattr(g, "jti_actual", None))
    db.session.commit()

    return jsonify({"data": {"message": "Contraseña actualizada correctamente",
                             "usuario": usuario_actual.to_dict()}})


# ── Código de emergencia (Día 69) ──────────────────────────────
# Para entrar cuando se quedó sin batería el teléfono y no puede mostrar su
# QR. El residente le dice al guardia su casa y este código; el guardia lo
# busca, ve su foto y su nombre, verifica contra la identificación, saca una
# foto de respaldo y abre. Todo queda en el historial.
#
# Reemplaza la propuesta de poner lectores biométricos en el portón: resuelve
# el mismo problema sin comprar nada y sin que nadie tenga que custodiar
# datos biométricos de 500 familias.
@auth_bp.get("/codigo-emergencia")
@token_required
@limiter.limit("30 per minute")
def estado_codigo_emergencia(usuario_actual):
    """Estado del código y, desde el Día 71, el código mismo para que su
    dueño pueda verlo en la app si lo olvidó (la app lo muestra oculto
    hasta que toca el ojo). Solo devuelve el código del usuario de la
    sesión, nunca el de otra persona.

    "codigo" viene en null si el código se creó antes de que se guardara
    la copia cifrada: la app le pide al residente que defina uno nuevo."""
    return jsonify({"data": {
        "configurado": usuario_actual.tiene_codigo_emergencia,
        "codigo": usuario_actual.codigo_emergencia_visible(),
        "actualizado_en": (usuario_actual.codigo_emergencia_actualizado.isoformat()
                           if usuario_actual.codigo_emergencia_actualizado else None),
    }})


@auth_bp.put("/codigo-emergencia")
@token_required
def definir_codigo_emergencia(usuario_actual):
    """
    El residente define o cambia su código de 6 dígitos.

    Se rechaza que sea igual a su contraseña: si fueran el mismo valor, un
    código que el guardia escucha en voz alta en el portón pasaría a ser
    también la llave de su cuenta.
    """
    data = request.get_json(silent=True) or {}
    codigo = (data.get("codigo") or "").strip()

    if not codigo.isdigit() or len(codigo) != 6:
        return jsonify({"error": {"code": "codigo_invalido",
                                  "message": "El código debe ser de 6 dígitos"}}), 400

    # Secuencias obvias: son las primeras que probaría cualquiera que quiera
    # adivinar un código ajeno sabiendo solo el número de casa.
    if codigo == codigo[0] * 6 or codigo in ("123456", "654321", "012345"):
        return jsonify({"error": {"code": "codigo_debil",
                                  "message": "Elegí un código menos obvio, no repitas el mismo "
                                             "dígito ni uses una secuencia"}}), 400

    if usuario_actual.check_password(codigo):
        return jsonify({"error": {"code": "codigo_igual_password",
                                  "message": "El código no puede ser igual a tu contraseña"}}), 400

    usuario_actual.set_codigo_emergencia(codigo)
    db.session.commit()
    return jsonify({"data": {"message": "Código de emergencia actualizado",
                             "configurado": True}})


# ── Actualizar perfil (nombre, teléfono) ───────────────────────
@auth_bp.put("/perfil")
@token_required
def actualizar_perfil(usuario_actual):
    data = request.get_json(silent=True) or {}
    if "nombre" in data and data["nombre"].strip():
        usuario_actual.nombre = data["nombre"].strip()
    if "apellido" in data and data["apellido"].strip():
        usuario_actual.apellido = data["apellido"].strip()
    if "telefono" in data:
        usuario_actual.telefono = data["telefono"].strip()
    db.session.commit()
    return jsonify({"data": {"usuario": usuario_actual.to_dict()}})


# ── Activación de cuenta ───────────────────────────────────────
@auth_bp.post("/activar")
@limiter.limit("10 per hour")
def activar_cuenta():
    """El residente recibe un link con un token. Aquí define su contraseña."""
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y contraseña son obligatorios"}}), 400
    error = validar_password(password)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    email = _verificar_token_temporal(token_str, "activacion")
    if not email:
        return jsonify({"error": {"code": "token_invalido",
                                  "message": "El enlace de activación es inválido o expiró"}}), 400

    # AUDIT-12 — capturar el email extraído del token para el log de auditoría.
    from flask import g as _g
    _g.email_intento = email[:120]

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        # Día 73 — el correo de activación ahora se manda ANTES de crear la
        # cuenta (es lo que confirma que la dirección existe), y la cuenta
        # se crea segundos después, cuando llega esa confirmación. Si la
        # persona abre el enlace en ese hueco, o si la administración no
        # terminó el registro, la cuenta todavía no está. "No se encontró
        # el usuario" sonaba a que algo estaba roto.
        return jsonify({"error": {"code": "cuenta_no_lista",
                                  "message": "Tu cuenta todavía no está lista. Esperá unos "
                                             "minutos y volvé a abrir el enlace. Si sigue "
                                             "sin funcionar, pedile a la administración que "
                                             "termine tu registro."}}), 404

    # Día 75 — el enlace sirve UNA vez. Antes se podía volver a usar durante
    # 48 h: cambiaba la clave y, peor, reactivaba a alguien que la
    # administración había desactivado o cuya casa había vuelto al padrón.
    if usuario.activado_en is not None or usuario.activo or usuario.suspendido_por_padron:
        return jsonify({"error": {"code": "ya_activada",
                                  "message": "Este enlace ya se usó: tu cuenta ya fue activada. "
                                             "Iniciá sesión con tu correo y tu clave; si no la "
                                             "recordás, usá «¿Olvidaste tu contraseña?»."}}), 409

    usuario.set_password(password)
    usuario.activo = True
    usuario.activado_en = dt.datetime.now(dt.timezone.utc)
    db.session.commit()

    token = generar_token(usuario)
    return jsonify({"data": {
        "message": "Cuenta activada correctamente",
        "token": token,
        "usuario": usuario.to_dict(),
    }})


# ── Solicitar recuperación de contraseña ───────────────────────
@auth_bp.post("/recuperar")
@limiter.limit("3 per hour")
def solicitar_recuperacion():
    """Genera un token de recuperación. En producción se envía por correo con Resend."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "El correo es obligatorio"}}), 400

    # AUDIT-12 — capturar el email para el log de auditoría, igual que en
    # el login. Este endpoint no requiere autenticación, así que g.usuario_actual
    # es None; sin esto, el log quedaría sin actor identificado.
    from flask import g as _g
    _g.email_intento = email[:120]

    usuario = Usuario.query.filter_by(email=email).first()

    # SEC-01: guardias y cajeros son credenciales locales de papel — su
    # única vía de reseteo es el panel admin (POST /usuarios/<id>/reset-password),
    # no la recuperación por correo. Se responde igual que si no existiera
    # el email, para no revelar el rol del usuario a quien hace la consulta.
    if usuario and usuario.rol in ROLES_CREDENCIAL_LOCAL:
        return jsonify({"data": {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}})

    # Día 69 — una persona del padrón (censo) no puede "recuperar" una
    # contraseña que nunca tuvo. Sin esta guarda, alguien del censo al que se
    # le hubiera cargado un correo podría fijarse una contraseña por acá y
    # entrar al sistema SIN pasar por la conversión formal que hace el
    # administrador. La respuesta es la misma de siempre, para no revelar nada.
    if usuario and not usuario.puede_iniciar_sesion:
        return jsonify({"data": {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}})

    # Siempre respondemos OK para no revelar si el email existe
    if not usuario:
        return jsonify({"data": {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}})

    # O1.4: el token se ata a la contraseña actual (huella). Cuando el reset
    # la cambie, esta huella dejará de coincidir y el enlace no servirá otra
    # vez — de un solo uso, sin guardar tokens usados en la base.
    token_reset = _generar_token_temporal(email, "reset", horas=2,
                                          huella=_huella_password(usuario))

    # Día 61 — implementado (antes era un TODO sin código real). Sin
    # escritura pendiente en esta función, se dispara ya mismo. Async vía
    # Celery para no demorar la respuesta HTTP con la llamada a Resend.
    try:
        from app.tasks.correo_task import encolar_correo_reset
        from app.models.residencial import Residencial
        residencial = Residencial.query.get(usuario.residencial_id) if usuario.residencial_id else None
        encolar_correo_reset(
            email, token_reset, residencial.nombre if residencial else "SICA-VS")
    except Exception:
        pass  # un correo que no sale no debe romper la respuesta al usuario

    respuesta = {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}
    # El token se devuelve en pantalla SOLO en desarrollo (no hay correos aún).
    # En producción esto sería una fuga crítica: cualquiera con un email válido
    # tomaría la cuenta sin acceder al correo. Por eso se condiciona al entorno.
    if current_app.config.get("ENV") != "production":
        respuesta["dev_token"] = token_reset

    return jsonify({"data": respuesta})


# ── Restablecer contraseña ─────────────────────────────────────
@auth_bp.post("/reset")
@limiter.limit("10 per hour")
def restablecer_password():
    data = request.get_json(silent=True) or {}
    token_str = data.get("token") or ""
    password = data.get("password") or ""

    if not token_str or not password:
        return jsonify({"error": {"code": "datos_incompletos",
                                  "message": "Token y nueva contraseña son obligatorios"}}), 400
    error = validar_password(password)
    if error:
        return jsonify({"error": {"code": "password_debil", "message": error}}), 400

    email = _verificar_token_temporal(token_str, "reset")
    if not email:
        return jsonify({"error": {"code": "token_invalido",
                                  "message": "El enlace de recuperación es inválido o expiró"}}), 400

    # AUDIT-12 — capturar el email extraído del token para el log de auditoría.
    from flask import g as _g
    _g.email_intento = email[:120]

    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        return jsonify({"error": {"code": "usuario_no_encontrado",
                                  "message": "No se encontró el usuario"}}), 404

    # O1.4: rechazar el token si ya fue usado (su huella no coincide con la
    # contraseña actual). Enlace de un solo uso, sin tabla de tokens usados.
    huella_token = _huella_de_token(token_str)
    if huella_token is not None and huella_token != _huella_password(usuario):
        return jsonify({"error": {"code": "token_usado",
                                  "message": "Este enlace ya fue utilizado o expiró. Solicitá uno nuevo."}}), 400

    usuario.set_password(password)
    if not usuario.activo:
        usuario.activo = True
    # Día 72 — restablecer la contraseña cierra TODAS las sesiones abiertas.
    from app.auth.sesiones import cerrar_sesiones_de
    cerrar_sesiones_de(usuario)
    db.session.commit()

    return jsonify({"data": {"message": "Contraseña restablecida correctamente. Ya puedes iniciar sesión."}})


# ── Cerrar sesión (revoca el token actual) ─────────────────────
@auth_bp.post("/logout")
@limiter.limit("30 per minute")
def logout():
    """
    Cierra la sesión de este dispositivo.

    Día 72 — ya no exige un JWT vigente. La app puede tener el JWT vencido
    (lo renueva sola) y aun así tiene que poder cerrar sesión de verdad: si
    solo se borrara el token del teléfono, el token de renovación seguiría
    vivo en el servidor. Por eso acepta cualquiera de los dos:
      - Authorization: Bearer <jwt>   (panel web y app)
      - { "refresh_token": "..." }     (app)
    Siempre responde 200: cerrar algo que ya estaba cerrado no es un error.
    """
    from flask import g
    from app.auth.sesiones import buscar_por_refresh, cerrar_sesion_registro
    from app.auth.security import _usuario_desde_request
    from app.models.sesion_activa import SesionActiva

    usuario = _usuario_desde_request()
    if usuario:
        g.usuario_actual = usuario
        auth = request.headers.get("Authorization", "")
        token = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else ""
        if token:
            revocar_token(token, usuario_id=usuario.id)
        jti = getattr(g, "jti_actual", None)
        if jti:
            SesionActiva.query.filter_by(jti=jti).delete()

    data = request.get_json(silent=True) or {}
    refresh = data.get("refresh_token")
    if isinstance(refresh, str) and refresh:
        sesion, _ = buscar_por_refresh(refresh)
        if sesion:
            cerrar_sesion_registro(sesion)

    db.session.commit()
    return jsonify({"data": {"message": "Sesión cerrada"}})


# ── Listar mis sesiones activas (dispositivos conectados) ──────
@auth_bp.get("/sesiones")
@token_required
def listar_sesiones(usuario_actual):
    from flask import g
    from app.models.sesion_activa import SesionActiva
    jti_actual = getattr(g, "jti_actual", None)
    sesiones = (SesionActiva.query
                .filter_by(usuario_id=usuario_actual.id)
                .order_by(SesionActiva.ultimo_uso.desc())
                .all())
    return jsonify({"data": [s.to_dict(jti_actual) for s in sesiones]})


# ── Cerrar una sesión específica ───────────────────────────────
@auth_bp.post("/sesiones/<int:sesion_id>/cerrar")
@token_required
def cerrar_sesion(usuario_actual, sesion_id):
    from app.models.sesion_activa import SesionActiva
    from app.models.token_revocado import TokenRevocado
    sesion = SesionActiva.query.filter_by(id=sesion_id, usuario_id=usuario_actual.id).first()
    if not sesion:
        return jsonify({"error": {"code": "no_encontrada",
                                  "message": "Sesión no encontrada"}}), 404
    # Revocar el token de esa sesión (blacklist) y borrar el registro
    if not TokenRevocado.esta_revocado(sesion.jti):
        db.session.add(TokenRevocado(jti=sesion.jti, usuario_id=usuario_actual.id,
                                     expira_en=sesion.expira_en))
    db.session.delete(sesion)
    db.session.commit()
    return jsonify({"data": {"message": "Sesión cerrada en ese dispositivo"}})


# ── Cerrar todas las otras sesiones (menos la actual) ──────────
@auth_bp.post("/sesiones/cerrar-otras")
@token_required
def cerrar_otras_sesiones(usuario_actual):
    from flask import g
    from app.models.sesion_activa import SesionActiva
    from app.models.token_revocado import TokenRevocado
    jti_actual = getattr(g, "jti_actual", None)
    otras = SesionActiva.query.filter(
        SesionActiva.usuario_id == usuario_actual.id,
        SesionActiva.jti != jti_actual,
    ).all()
    for s in otras:
        if not TokenRevocado.esta_revocado(s.jti):
            db.session.add(TokenRevocado(jti=s.jti, usuario_id=usuario_actual.id,
                                         expira_en=s.expira_en))
        db.session.delete(s)
    db.session.commit()
    return jsonify({"data": {"message": f"Se cerraron {len(otras)} sesiones", "cerradas": len(otras)}})
