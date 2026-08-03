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


def _bloqueado_por_suspension(usuario):
    """
    Día 50 — sistema de suscripciones. Chequeo centralizado: si la
    residencial del usuario está suspendida (venció su plan y ya pasó el
    período de gracia), se bloquea el acceso a TODA la API para
    cualquier rol bajo esa residencial — admin, supervisor, guardia,
    cajero, residente. Vive acá (no en cada endpoint) para que se
    aplique automáticamente a todo lo protegido con @token_required o
    @roles_required, sin tener que acordarse de agregarlo en cada uno.

    super_admin y desarrollador son roles de PLATAFORMA, no de un
    cliente — nunca deben quedar bloqueados por la suscripción de un
    cliente, sin importar qué residencial estén mirando en un momento
    dado. Import perezoso (adentro de la función) para no arriesgar un
    import circular en un módulo que se carga muy temprano.

    Devuelve None si puede pasar; si no, devuelve la respuesta de error
    lista para que el decorador la retorne directo.
    """
    if usuario.rol in ("super_admin", "desarrollador"):
        return None
    if not usuario.residencial_id:
        return None
    from app.models.residencial import Residencial
    residencial = Residencial.query.get(usuario.residencial_id)
    if residencial and residencial.esta_suspendida():
        return jsonify({"error": {"code": "suscripcion_suspendida",
                                  "message": "El servicio de tu residencial está suspendido por falta de pago. "
                                             "Contactá a tu administrador."}}), 402
    return None


def token_required(f):
    """Exige un token válido. Inyecta usuario_actual como primer argumento."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        from flask import g
        usuario = _usuario_desde_request()
        if not usuario:
            return jsonify({"error": {"code": "no_autorizado",
                                      "message": "Token inválido o ausente"}}), 401
        bloqueo = _bloqueado_por_suspension(usuario)
        if bloqueo:
            return bloqueo
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
            bloqueo = _bloqueado_por_suspension(usuario)
            if bloqueo:
                return bloqueo
            g.usuario_actual = usuario
            return f(usuario, *args, **kwargs)
        return wrapper
    return decorator


def requiere_funcion_plan(funcion):
    """
    Día 51 — niveles de plan (Básico/Premium) por flags de función. Bloquea
    un endpoint completo si el plan de la residencial del usuario no
    incluye esa función (hoy: 'cuotas' o 'notificaciones').

    Se apila DEBAJO de @token_required o @roles_required — esos ya
    resolvieron usuario_actual antes de llegar acá, por eso este
    decorador lo recibe como primer argumento en vez de volver a validar
    el token desde cero. Uso:

        @cuotas_bp.get("/mias")
        @token_required
        @requiere_funcion_plan("cuotas")
        def ver_mis_cuotas(usuario_actual):
            ...

    Sin plan asignado, plan_permite() ya devuelve True (mismo criterio
    de "sin plan = sin restricción" que el resto del sistema de
    suscripciones) — este decorador no necesita repetir esa lógica.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(usuario_actual, *args, **kwargs):
            from app.utils.residencial import plan_permite
            if not plan_permite(usuario_actual.residencial_id, funcion):
                return jsonify({"error": {"code": "funcion_no_incluida",
                                          "message": "Tu plan actual no incluye esta función — "
                                                     "hablá con tu proveedor para subir de plan."}}), 402
            return f(usuario_actual, *args, **kwargs)
        return wrapper
    return decorator
