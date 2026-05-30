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
from functools import wraps

import jwt
from flask import current_app, request, jsonify

from app.models.usuario import Usuario


def generar_token(usuario: Usuario) -> str:
    """Genera un JWT firmado con el id público y el rol del usuario."""
    payload = {
        "sub": str(usuario.uuid_publico),
        "rol": usuario.rol,
        "exp": dt.datetime.utcnow() + dt.timedelta(
            hours=current_app.config["JWT_EXPIRES_HOURS"]
        ),
        "iat": dt.datetime.utcnow(),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


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
    return Usuario.query.filter_by(uuid_publico=payload["sub"], activo=True).first()


def token_required(f):
    """Exige un token válido. Inyecta usuario_actual como primer argumento."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        usuario = _usuario_desde_request()
        if not usuario:
            return jsonify({"error": {"code": "no_autorizado",
                                      "message": "Token inválido o ausente"}}), 401
        return f(usuario, *args, **kwargs)
    return wrapper


def roles_required(*roles_permitidos):
    """Exige token válido Y que el rol del usuario esté permitido."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            usuario = _usuario_desde_request()
            if not usuario:
                return jsonify({"error": {"code": "no_autorizado",
                                          "message": "Token inválido o ausente"}}), 401
            if usuario.rol not in roles_permitidos:
                return jsonify({"error": {"code": "prohibido",
                                          "message": "No tienes permiso para esta acción"}}), 403
            return f(usuario, *args, **kwargs)
        return wrapper
    return decorator
