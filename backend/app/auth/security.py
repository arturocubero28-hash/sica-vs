"""
Utilidades de autenticación: generación/verificación de JWT y
decoradores para proteger endpoints por rol.

El equipo usa estos decoradores así:

    from app.auth.security import token_required, roles_required

    @cuentas_bp.get("/")
    @token_required
    def listar(usuario_actual):
        ...

    @pagos_bp.put("/<uuid>/aprobar")
    @roles_required("admin", "super_admin")
    def aprobar(usuario_actual, uuid):
        ...
"""
import datetime as dt
import uuid as uuid_lib
from functools import wraps

import jwt
from flask import current_app, request, jsonify

from app.models.usuario import Usuario


def generar_token(usuario: Usuario, devolver_jti: bool = False):
    """Genera un JWT firmado con el id público y el rol del usuario."""
    jti = str(uuid_lib.uuid4())
    payload = {
        "sub": str(usuario.uuid_publico),
        "rol": usuario.rol,
        "jti": jti,   # identificador único del token (para revocación)
        "exp": dt.datetime.utcnow() + dt.timedelta(
            hours=current_app.config["JWT_EXPIRES_HOURS"]
        ),
        "iat": dt.datetime.utcnow(),
    }
    token = jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")
    if devolver_jti:
        exp = payload["exp"].replace(tzinfo=dt.timezone.utc)
        return token, jti, exp
    return token


def revocar_token(token, usuario_id=None):
    """
    Revoca un token: guarda su jti en la blacklist hasta que expire.
    Devuelve True si se revocó, False si el token era inválido.
    """
    from app.extensions import db
    from app.models.token_revocado import TokenRevocado
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return False
    jti = payload.get("jti")
    if not jti:
        return False
    if TokenRevocado.esta_revocado(jti):
        return True  # ya estaba revocado
    exp_ts = payload.get("exp")
    expira = (dt.datetime.fromtimestamp(exp_ts, tz=dt.timezone.utc)
              if exp_ts else dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=24))
    db.session.add(TokenRevocado(jti=jti, usuario_id=usuario_id, expira_en=expira))
    db.session.commit()
    return True


def _usuario_desde_request():
    """Extrae y valida el token. Acepta header Authorization o query param _auth (para imágenes)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
    else:
        # Para <img src> que no puede mandar headers, aceptar token por query
        token = request.args.get("_auth", "")
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET"], algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    # Verificar que el token no haya sido revocado (logout / blacklist)
    from app.models.token_revocado import TokenRevocado
    if TokenRevocado.esta_revocado(payload.get("jti")):
        return None
    # Guardar el jti actual para identificar "esta sesión" en el listado
    from flask import g
    g.jti_actual = payload.get("jti")
    return Usuario.query.filter_by(uuid_publico=payload["sub"], activo=True).first()


def token_required(f):
    """Exige un token válido. Inyecta usuario_actual como primer argumento."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        from flask import g
        usuario = _usuario_desde_request()
        if not usuario:
            return jsonify({"error": {"code": "no_autorizado",
                                      "message": "Token inválido o ausente"}}), 401
        g.usuario_actual = usuario   # disponible para el hook de auditoría
        return f(usuario, *args, **kwargs)
    return wrapper


def roles_required(*roles_permitidos):
    """
    Exige token válido Y que el rol del usuario esté permitido.

    Bases multi-residencial (Día 37): un usuario con rol 'supervisor' se
    trata como equivalente a 'admin' en CUALQUIER endpoint que acepte
    "admin" en roles_permitidos — sin tener que agregar "supervisor" a
    mano en cada uno de los @roles_required("admin", "super_admin") que
    ya existen por todo el código. Las pocas acciones donde supervisor SÍ
    debe distinguirse de admin (crear/gestionar otro supervisor, tocar al
    admin dueño) se resuelven aparte con puede_gestionar_rol(), no acá.

    De paso (adelanto de AUDIT-12, Auditoría Día 35): se agrega
    g.usuario_actual también en este decorador — antes solo lo hacía
    token_required(), así que cualquier operación protegida con
    roles_required() (la mayoría de las administrativas/privilegiadas)
    quedaba sin actor para el hook de auditoría.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            from flask import g
            usuario = _usuario_desde_request()
            if not usuario:
                return jsonify({"error": {"code": "no_autorizado",
                                          "message": "Token inválido o ausente"}}), 401
            permitido = usuario.rol in roles_permitidos
            if not permitido and usuario.rol == "supervisor" and "admin" in roles_permitidos:
                permitido = True
            if not permitido:
                return jsonify({"error": {"code": "prohibido",
                                          "message": "No tienes permiso para esta acción"}}), 403
            g.usuario_actual = usuario
            return f(usuario, *args, **kwargs)
        return wrapper
    return decorator
